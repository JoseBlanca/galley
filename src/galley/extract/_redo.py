"""The words of a page read by Tesseract under `ocr = "redo"` (extract spec
section 9): Tesseract's words, with the layer's note references and caption
numbers put back where Tesseract lost them, the layer's words of the lines
Tesseract skipped kept among them, and each word given the height of the
type from the layer word over it.

Pure functions over the page's two readings; extract's worker calls
`ocr_page_words` and logs what it says.
"""

import difflib
import statistics
from dataclasses import replace
from typing import Final, NamedTuple

from galley.caption_labels import LABEL_NAMES, is_numeral, is_well_formed_numeral
from galley.model import Box, Word
from galley.note_references import after_last_letter, glued_reference

# Extract spec section 9, "Note references put back from the layer": a
# Tesseract word and a layer word are over each other when they overlap by
# half the lower height and half the narrower width; a third of the height
# took 4 wrong references on Kadesh. The two words' letters may differ in
# one place ("Higels" under "Hugels", page 26), not more ("find" under
# "flui", page 13, where the page prints no reference).
_OVER_EACH_OTHER_SHARE: Final[float] = 0.5
_REFERENCE_LETTERS_DIFFERING_MAX: Final[int] = 1

# Extract spec section 9, "Layer words Tesseract missed", measured on the
# whole Kadesh book on 19 November 2026. The page's offset is the median
# over pairs of words of 3 or more letters and digits whose middles are
# less than 12 pt apart: the layer's boxes sit 1.2 to 5.4 pt below
# Tesseract's, and 12 pt, about a body line pitch (12.96), keeps a word of
# the next line out of the pairs.
_OFFSET_PAIR_MIN_CHARACTERS: Final[int] = 3
_OFFSET_PAIR_DISTANCE_PT: Final[float] = 12.0
# A Tesseract word covers a layer word when they overlap by a quarter of
# the lower height (half took many words Tesseract read, 167 against 103).
_COVER_HEIGHT_SHARE: Final[float] = 0.25
# "A word read as junk": a Tesseract word of confidence below 1 does not
# cover a layer word whose letters Tesseract reads elsewhere on the page
# with confidence 60 or more, and that are neither inside its letters nor
# 0.5 alike to them (difflib's ratio). On Kadesh, 19 November 2026, it keeps
# 10 printed words ("chariotry", page 44) of the 128 layer words that only
# such words cover; 72 are 0.5 alike or inside, misreadings of the same word.
_JUNK_CONFIDENCE_BELOW: Final[float] = 1.0
_READ_ELSEWHERE_CONFIDENCE_LEAST: Final[float] = 60.0
_MISREADING_LEAST_LIKENESS: Final[float] = 0.5
# A layer word is the copy of an unclaimed Tesseract word with its letters
# and digits less than 16 pt across from it; a word of a short row, also
# 16 pt up or down (the layer boxes page 41's "behind" 14 pt below
# Tesseract's, and page numbers 10 to 12 pt off).
_COPY_DISTANCE_PT: Final[float] = 16.0
# A kept word holds 2 letters or more; on a row of fewer than 3 kept words,
# 4 letters or more, and letters at least 0.7 of its characters: on Kadesh
# the lone words and pairs below these were the layer's junk ("US", "inn",
# "•J4", "AA/^AA^", ".L+JI") or a page number, the longer ones printed
# words ("FftAigou" for "FRANÇOIS", "throueh").
_KEPT_MIN_LETTERS: Final[int] = 2
_SHORT_ROW_MAX_WORDS: Final[int] = 2
_SHORT_ROW_MIN_LETTERS: Final[int] = 4
_SHORT_ROW_LETTERS_SHARE_MIN: Final[float] = 0.7
# Extract spec section 9, "Word heights from the layer": a layer word taller
# than 1.5 times the 90th percentile of the page's layer word heights gives
# no height. On Kadesh the layer's boxes over hieroglyph rows are 16 to 35
# pt tall, its text's 7 to 13, and the 90th percentile is 10.4 to 11.3 on
# every page; the median is the notes' 7.1 on pages 11 and 15, whose notes
# outnumber the text, and would keep the text's 11 pt out.
_HEIGHT_GIVER_MAX_SHARE: Final[float] = 1.5
_HEIGHT_QUANTILES: Final[int] = 10


class OcrPageWords(NamedTuple):
    """An `ocr` page's words (extract spec section 9) and what the layer
    gave them: `words`, Tesseract's in its order with the kept layer words
    among them; `taken`, each Tesseract word whose text took the layer's
    note reference or caption number, with its new text; `kept`, the layer
    words kept."""

    words: tuple[Word, ...]
    taken: tuple[tuple[Word, str], ...]
    kept: tuple[Word, ...]


def ocr_page_words(
    tesseract_words: tuple[Word, ...],
    layer_words: tuple[Word, ...],
    figure_boxes: tuple[Box, ...],
) -> OcrPageWords:
    """The words of an `ocr` page whose Tesseract words are `tesseract_words`
    (not empty) and whose layer's are `layer_words`, with its in-page
    figures' `figure_boxes` (extract spec section 9): the references and
    caption numbers put back, then the missed layer words kept, then the
    heights given, the page's offset taken once."""
    offset = layer_offset(tesseract_words, layer_words)
    texts = with_caption_numbers(
        with_layer_references(tesseract_words, layer_words), layer_words
    )
    outside = outside_figures(layer_words, figure_boxes)
    words = with_layer_heights(
        with_missed_layer_words(texts, outside, offset=offset),
        outside,
        offset=offset,
    )
    return OcrPageWords(
        words=words,
        taken=tuple(
            (before, after.text)
            for before, after in zip(tesseract_words, texts, strict=True)
            if before.text != after.text
        ),
        kept=tuple(word for word in words if word.ocr_confidence is None),
    )


def outside_figures(
    layer_words: tuple[Word, ...], figure_boxes: tuple[Box, ...]
) -> tuple[Word, ...]:
    """The words of `layer_words` whose box overlaps none of `figure_boxes`
    (extract spec section 9, condition 3 of the missed words)."""
    return tuple(
        word
        for word in layer_words
        if not any(_overlap_box(box, word.box) for box in figure_boxes)
    )


def with_layer_references(
    ocr_words: tuple[Word, ...], layer_words: tuple[Word, ...]
) -> tuple[Word, ...]:
    """`ocr_words`, a page's words as Tesseract read them, each that
    takes the layer's note reference (extract spec section 9) with its
    text changed, in the same order."""
    return tuple(
        _with_layer_reference(ocr_word, layer_word)
        if (layer_word := _one_over(ocr_word, ocr_words, layer_words)) is not None
        else ocr_word
        for ocr_word in ocr_words
    )


def _one_over(
    ocr_word: Word, ocr_words: tuple[Word, ...], layer_words: tuple[Word, ...]
) -> Word | None:
    """The one layer word over `ocr_word` when no other word of `ocr_words`
    is over it too (extract spec section 9, condition 2); else None."""
    over = tuple(word for word in layer_words if _over(ocr_word, word))
    if len(over) != 1 or sum(_over(other, over[0]) for other in ocr_words) != 1:
        return None
    return over[0]


def _over(ocr_word: Word, layer_word: Word) -> bool:
    return are_over_each_other(ocr_word.box, layer_word.box)


def _with_layer_reference(ocr_word: Word, layer_word: Word) -> Word:
    """`ocr_word` with the reference glued to `layer_word`, the one layer
    word over it, when the two words meet conditions 1, 3 and 4 of extract
    spec section 9; else `ocr_word` as it is."""
    ocr_letters = _letters(ocr_word.text)
    layer_letters = _letters(layer_word.text)
    if (
        glued_reference(layer_word.text) is None
        or _has_digit(ocr_word.text)
        or not ocr_letters
        or len(ocr_letters) != len(layer_letters)
        or sum(one != other for one, other in zip(ocr_letters, layer_letters))
        > _REFERENCE_LETTERS_DIFFERING_MAX
    ):
        return ocr_word
    text = ocr_word.text[
        : len(ocr_word.text) - len(after_last_letter(ocr_word.text))
    ] + after_last_letter(layer_word.text)
    return replace(ocr_word, text=text)


def with_caption_numbers(
    ocr_words: tuple[Word, ...], layer_words: tuple[Word, ...]
) -> tuple[Word, ...]:
    """`ocr_words`, each that follows a caption word on its line and is no
    numeral as printed taking the numeral of the layer word over it
    (extract spec section 9, "Caption numbers from the layer")."""
    return tuple(
        replace(ocr_word, text=layer_word.text)
        if position > 0
        and ocr_words[position - 1].text.lower() in LABEL_NAMES
        and _overlap(
            ocr_words[position - 1].box.top,
            ocr_words[position - 1].box.bottom,
            ocr_word.box.top,
            ocr_word.box.bottom,
        )
        > 0
        and not _has_digit(ocr_word.text)
        and not is_well_formed_numeral(ocr_word.text)
        and (layer_word := _one_over(ocr_word, ocr_words, layer_words)) is not None
        and is_numeral(layer_word.text)
        else ocr_word
        for position, ocr_word in enumerate(ocr_words)
    )


def layer_offset(ocr_words: tuple[Word, ...], layer_words: tuple[Word, ...]) -> float:
    """How far the layer's boxes sit below Tesseract's on a page (extract
    spec section 9): the median, over the pairs of a layer word and a word
    of `ocr_words` that carries a confidence with the same letters and
    digits, `_OFFSET_PAIR_MIN_CHARACTERS` or more, overlapping in width,
    with middles less than `_OFFSET_PAIR_DISTANCE_PT` apart up or down, of
    the layer word's middle less the Tesseract word's; 0 without a pair."""
    differences = tuple(
        _middle(layer_word.box) - _middle(ocr_word.box)
        for layer_word in layer_words
        if len(_letters_and_digits(layer_word.text)) >= _OFFSET_PAIR_MIN_CHARACTERS
        for ocr_word in ocr_words
        if ocr_word.ocr_confidence is not None
        and _letters_and_digits(ocr_word.text) == _letters_and_digits(layer_word.text)
        and _overlap(
            ocr_word.box.x0, ocr_word.box.x1, layer_word.box.x0, layer_word.box.x1
        )
        > 0
        and abs(_middle(layer_word.box) - _middle(ocr_word.box))
        < _OFFSET_PAIR_DISTANCE_PT
    )
    return statistics.median(differences) if differences else 0.0


def with_missed_layer_words(
    ocr_words: tuple[Word, ...], layer_words: tuple[Word, ...], *, offset: float
) -> tuple[Word, ...]:
    """`ocr_words`, a page's words as Tesseract read them, with the layer
    words Tesseract missed (extract spec section 9) put among them, each
    with its box moved up by `offset`, the page's. Each goes before the
    first word of `ocr_words` whose top is lower than its own, in the
    order of `layer_words`."""
    moved = tuple(_moved_up(layer_word, offset) for layer_word in layer_words)
    unclaimed = tuple(
        ocr_word
        for ocr_word in ocr_words
        if not any(
            _letters_and_digits(layer_word.text) == _letters_and_digits(ocr_word.text)
            and _covers(ocr_word.box, layer_word.box)
            for layer_word in moved
        )
    )
    read_well = frozenset(
        _letters(ocr_word.text)
        for ocr_word in ocr_words
        if ocr_word.ocr_confidence is not None
        and ocr_word.ocr_confidence >= _READ_ELSEWHERE_CONFIDENCE_LEAST
    )
    candidates = tuple(
        layer_word
        for layer_word in moved
        if len(_letters(layer_word.text)) >= _KEPT_MIN_LETTERS
        and not any(
            _covers(ocr_word.box, layer_word.box)
            and not _read_as_junk(layer_word, ocr_word, read_well)
            for ocr_word in ocr_words
        )
    )
    missed = tuple(
        layer_word
        for layer_word in candidates
        if _is_kept(layer_word, _row_count(layer_word, candidates), unclaimed)
    )
    return _placed_among(ocr_words, missed)


def _read_as_junk(layer_word: Word, ocr_word: Word, read_well: frozenset[str]) -> bool:
    """Whether `ocr_word`, covering `layer_word`, is junk Tesseract read
    there in place of it (extract spec section 9, "A word read as junk"):
    its confidence is below 1, `layer_word`'s letters are among
    `read_well`, those of the page's words of confidence 60 or more, and
    they are neither inside `ocr_word`'s letters nor 0.5 alike to them."""
    letters = _letters(layer_word.text)
    ocr_letters = _letters(ocr_word.text)
    return (
        ocr_word.ocr_confidence is not None
        and ocr_word.ocr_confidence < _JUNK_CONFIDENCE_BELOW
        and letters in read_well
        and letters not in ocr_letters
        and difflib.SequenceMatcher(None, letters, ocr_letters).ratio()
        < _MISREADING_LEAST_LIKENESS
    )


def _row_count(layer_word: Word, candidates: tuple[Word, ...]) -> int:
    """The number of `candidates`, `layer_word` among them, on its row: those
    that overlap it in height by half its height."""
    box = layer_word.box
    return sum(
        _overlap(box.top, box.bottom, other.box.top, other.box.bottom)
        >= (box.bottom - box.top) / 2
        for other in candidates
    )


def _is_kept(layer_word: Word, row_count: int, unclaimed: tuple[Word, ...]) -> bool:
    """Whether `layer_word`, a candidate on a row of `row_count` candidates,
    is kept: no copy of a word of `unclaimed` (on its line, or within 16 pt
    up or down on a short row), and on a short row a word of 4 letters or
    more, mostly letters (extract spec section 9)."""
    short_row = row_count <= _SHORT_ROW_MAX_WORDS
    letters = len(_letters(layer_word.text))
    if short_row and (
        letters < _SHORT_ROW_MIN_LETTERS
        or letters < _SHORT_ROW_LETTERS_SHARE_MIN * len(layer_word.text)
    ):
        return False
    box = layer_word.box
    return not any(
        _letters_and_digits(ocr_word.text) == _letters_and_digits(layer_word.text)
        and _gap(ocr_word.box.x0, ocr_word.box.x1, box.x0, box.x1) <= _COPY_DISTANCE_PT
        and (
            _overlap(ocr_word.box.top, ocr_word.box.bottom, box.top, box.bottom) > 0
            or (
                short_row
                and _gap(ocr_word.box.top, ocr_word.box.bottom, box.top, box.bottom)
                <= _COPY_DISTANCE_PT
            )
        )
        for ocr_word in unclaimed
    )


def _placed_among(
    ocr_words: tuple[Word, ...], missed: tuple[Word, ...]
) -> tuple[Word, ...]:
    """`ocr_words` with each of `missed` before the first of them whose top
    is lower than its own, or at the end."""
    places = tuple(
        next(
            (
                position
                for position, ocr_word in enumerate(ocr_words)
                if ocr_word.box.top > layer_word.box.top
            ),
            len(ocr_words),
        )
        for layer_word in missed
    )
    return tuple(
        word
        for position in range(len(ocr_words) + 1)
        for word in (
            *(
                layer_word
                for layer_word, place in zip(missed, places, strict=True)
                if place == position
            ),
            *ocr_words[position : position + 1],
        )
    )


def with_layer_heights(
    ocr_words: tuple[Word, ...], layer_words: tuple[Word, ...], *, offset: float
) -> tuple[Word, ...]:
    """`ocr_words` with each word that carries a confidence and that a
    layer word of `layer_words`, moved up by `offset`, covers given that
    layer word's height about its own middle, so that it keeps Tesseract's
    middle (extract spec section 9, "Word heights from the layer"). Of
    the covering layer words, those no taller than
    `_HEIGHT_GIVER_MAX_SHARE` times the 90th percentile of the page's layer
    word heights count; among them those with the word's letters and digits, if any;
    and of those the one whose overlap with it is the largest share of its
    own box."""
    if not layer_words:
        return ocr_words
    tallest = (
        _HEIGHT_GIVER_MAX_SHARE
        * statistics.quantiles(
            (word.box.bottom - word.box.top for word in layer_words),
            n=_HEIGHT_QUANTILES,
            method="inclusive",
        )[-1]
    )
    givers = tuple(
        moved
        for layer_word in layer_words
        if (moved := _moved_up(layer_word, offset)).box.bottom - moved.box.top
        <= tallest
    )
    return tuple(
        word
        if word.ocr_confidence is None
        else _with_height_of(
            word, tuple(giver for giver in givers if _covers(word.box, giver.box))
        )
        for word in ocr_words
    )


def _with_height_of(ocr_word: Word, covering: tuple[Word, ...]) -> Word:
    """`ocr_word` with the height of the layer word of `covering` that
    gives it (`with_layer_heights`), about its own middle; as it is when
    `covering` is empty."""
    same = tuple(
        word
        for word in covering
        if _letters_and_digits(word.text) == _letters_and_digits(ocr_word.text)
    )
    pool = same or covering
    if not pool:
        return ocr_word
    box = ocr_word.box
    giver = max(pool, key=lambda word: _overlap_share(box, word.box)).box
    half_height = (giver.bottom - giver.top) / 2
    middle = _middle(box)
    return replace(
        ocr_word, box=Box(box.x0, middle - half_height, box.x1, middle + half_height)
    )


def _overlap_share(box: Box, layer_box: Box) -> float:
    """The area `box` and `layer_box` share, as a share of `layer_box`'s."""
    area = (layer_box.x1 - layer_box.x0) * (layer_box.bottom - layer_box.top)
    shared = _overlap(box.x0, box.x1, layer_box.x0, layer_box.x1) * _overlap(
        box.top, box.bottom, layer_box.top, layer_box.bottom
    )
    return shared / area if area > 0 else 0.0


def _covers(ocr_box: Box, layer_box: Box) -> bool:
    """Whether a Tesseract word's box covers a layer word's, already moved
    by the offset: they overlap in width, and in height by
    `_COVER_HEIGHT_SHARE` of the lower height (extract spec section 9)."""
    height_overlap = _overlap(
        ocr_box.top, ocr_box.bottom, layer_box.top, layer_box.bottom
    )
    return (
        _overlap(ocr_box.x0, ocr_box.x1, layer_box.x0, layer_box.x1) > 0
        and height_overlap > 0
        and height_overlap
        >= _COVER_HEIGHT_SHARE
        * min(ocr_box.bottom - ocr_box.top, layer_box.bottom - layer_box.top)
    )


def are_over_each_other(one: Box, other: Box) -> bool:
    """Whether two word boxes overlap by `_OVER_EACH_OTHER_SHARE` of the
    lower height and of the narrower width (extract spec section 9)."""
    height_overlap = _overlap(one.top, one.bottom, other.top, other.bottom)
    width_overlap = _overlap(one.x0, one.x1, other.x0, other.x1)
    return (
        height_overlap > 0
        and width_overlap > 0
        and height_overlap
        >= _OVER_EACH_OTHER_SHARE * min(one.bottom - one.top, other.bottom - other.top)
        and width_overlap
        >= _OVER_EACH_OTHER_SHARE * min(one.x1 - one.x0, other.x1 - other.x0)
    )


def _moved_up(layer_word: Word, offset: float) -> Word:
    box = layer_word.box
    return replace(
        layer_word, box=Box(box.x0, box.top - offset, box.x1, box.bottom - offset)
    )


def _overlap_box(one: Box, other: Box) -> bool:
    """Whether two boxes share some area."""
    return (
        _overlap(one.x0, one.x1, other.x0, other.x1) > 0
        and _overlap(one.top, one.bottom, other.top, other.bottom) > 0
    )


def _middle(box: Box) -> float:
    return (box.top + box.bottom) / 2


def _overlap(start: float, end: float, other_start: float, other_end: float) -> float:
    """The length two intervals share, 0 when they do not meet."""
    return max(0.0, min(end, other_end) - max(start, other_start))


def _gap(start: float, end: float, other_start: float, other_end: float) -> float:
    """The distance between two intervals, 0 when they meet."""
    return max(0.0, max(start, other_start) - min(end, other_end))


def _letters(text: str) -> str:
    return "".join(character.lower() for character in text if character.isalpha())


def _letters_and_digits(text: str) -> str:
    return "".join(character.lower() for character in text if character.isalnum())


def _has_digit(text: str) -> bool:
    return any(character.isdigit() for character in text)
