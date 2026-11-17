"""The pure parts of layout's re-reading of small print (docs/specs/reocr.md).

Layout re-reads with Tesseract four kinds of region of a page, each a
**region read**: a page printed wholly in small type (a small-print
page), one note band of an outer margin, one crop of the notes cut into
the column, and, when the config asks, the footnote band. For each it
keeps Tesseract's words in place of the text layer's only when their
reading score, known words minus unknown words, is higher (reocr spec,
section 3).

This module decides, with no PDF and no Tesseract: whether a page is a
small-print page (`is_small_print_page`); where each kind of region is
cropped (`small_print_crop`, `margin_strip` and `note_bands`,
`cut_in_crops`, `footnote_band_crop`); which of Tesseract's words a
cut-in crop keeps and which layer words each region replaces (the
`..._reading` functions); and, per page, which regions are kept, each
layer word replaced by one record at most, in the order of the records
(`page_rereads`). Positions are PDF points from the page's top left,
except where a name or a docstring says pixels.
"""

import itertools
import math
from collections.abc import Iterable
from dataclasses import dataclass, replace
from typing import Final, assert_never

from PIL import Image

from galley.body_measures import group_rows
from galley.hyphens import LINE_END_HYPHENS
from galley.layout._column import (
    BookMeasures,
    ColumnSplit,
    Side,
    ends_short_of_inset,
    in_cut_in_zone,
    is_small_row,
    running_head_row_count,
    split_at_column,
    without_cut_in_notes,
)
from galley.model import (
    Box,
    PageWords,
    Reread,
    RereadKind,
    Word,
    folded_letters_and_digits,
    is_under_ocr_word,
    matched_ocr_positions,
    may_read,
    replaced_layer_words,
    take_out_once,
    word_middle,
)
from galley.ocr import OCR_DPI
from galley.pdfium import POINTS_PER_INCH
from galley.wordlist import is_known_word

__all__ = [
    "NOTE_PSM",
    "SMALL_PRINT_PSM",
    "CutInCrop",
    "RegionReading",
    "cut_in_crops",
    "cut_in_reading",
    "footnote_band_crop",
    "footnote_band_reading",
    "is_small_print_page",
    "margin_note_reading",
    "margin_note_sides",
    "margin_strip",
    "note_bands",
    "page_rereads",
    "pixel_box",
    "reading_score",
    "small_print_crop",
    "small_print_reading",
]

# Tesseract's page segmentation modes (reocr spec, section 3): a
# small-print page is read as a whole page, whose blocks Tesseract finds
# (3); a note band, a cut-in crop or a footnote band as one block of lines
# of the same type (6).
SMALL_PRINT_PSM: Final[int] = 3
NOTE_PSM: Final[int] = 6

# The reading score (reocr spec, section 1, "Reading score"): measured on
# Stubbs and Domesday, section 3.
_QUOTATION_MARKS: Final[str] = "‘’“”\"'"
_CURLY_APOSTROPHE: Final[str] = "’"

# The small-print page (reocr spec, section 3, kind 1): measured on the six
# books; the share lies in a gap from 0.78 to 0.86.
_SMALL_PRINT_LEAST_WORDS: Final[int] = 50
_SMALL_PRINT_ROWS_PER_100: Final[int] = 85
_COUNTED_ROW_LEAST_WORDS: Final[int] = 2

# A side of a book has outer margin notes when at least 10 in 100 of its
# pages of 50 words or more have at least 2 known words among that side's
# margin words (reocr spec, section 3, kind 2): measured, Gierke 97 and 88
# of 271 pages, Domesday 154 and 165 of 538; Stubbs at most 1, Mariéjol 3,
# Haskins and Kadesh 0.
_MARGIN_SIDE_LEAST_WORDS: Final[int] = 50
_MARGIN_SIDE_LEAST_KNOWN: Final[int] = 2
_MARGIN_SIDE_PAGES_PER_100: Final[int] = 10

# A region over no layer word is kept only with this many known words of
# Tesseract's (reocr spec, section 3): "af", read over nothing on Gierke
# page 120, is one; "Medieval Thought.", on page 88, two.
_OVER_NOTHING_LEAST_KNOWN: Final[int] = 2
# Or with one sure single word (reocr spec, section 3): 4 letters or more,
# every word read at a confidence of 80 or more. Measured on whole Stubbs,
# Domesday and Gierke on 17 November 2026: every such word at 80 or more
# with no layer word that may read it is a printed note word ("Coronation."
# 97, Stubbs page 63; the lowest "enemies." 81, page 95); "af" is 69, and
# the page numbers and table heads at 88 to 97 have fewer letters.
_SURE_WORD_LEAST_LETTERS: Final[int] = 4
_SURE_WORD_LEAST_CONFIDENCE: Final[float] = 80.0

# The crops (reocr spec, section 3). Measured on Stubbs and Domesday, or set
# so that a crop holds its words with a little white around them.
_BELOW_HEAD_PT: Final[float] = 1.0
_STRIP_PAGE_EDGE_PT: Final[float] = 4.0
_STRIP_COLUMN_PT: Final[float] = 4.0
_STRIP_ABOVE_BELOW_PT: Final[float] = 4.0
_CUT_IN_WIDEN_PITCHES: Final[float] = 2.5
_CUT_IN_CROP_OUTSIDE_PT: Final[float] = 3.0
_FOOTNOTE_BAND_PT: Final[float] = 3.0

# The note bands of a margin strip, in pixels at 300 dpi (reocr spec,
# section 3, kind 2), as the Gierke measurement of 16 November 2026 found
# them.
_INK_BELOW: Final[int] = 140
_INKED_ROW_MORE_THAN: Final[int] = 1
_BAND_GAP_MOST_PX: Final[int] = 18
_BAND_LEAST_HEIGHT_PX: Final[int] = 12
_BAND_LEAST_INK_PX: Final[int] = 150
_BAND_LEAST_WIDTH_PX: Final[int] = 25
_BAND_MARGIN_PX: Final[int] = 6
_INK: Final[int] = 255

# A note band may replace the margin words whose middle lies within 12 pt
# above or below it: the layer's lines lie up to 12 pt off Tesseract's
# (model.replaced_layer_words).
_BAND_REACH_PT: Final[float] = 12.0
# A body line's last word may end up to 2 pt past the column's edge (layout
# spec, section 3, step 2: a word 2 pt outside is a margin word); "of" at
# the end of a body line beside a note on Domesday page 74 ends 1 pt past.
_INTO_MARGIN_PT: Final[float] = 2.0

# The filters of a cut-in crop (reocr spec, section 3, kind 3), measured
# on Stubbs: a body line runs on to within 3 pt of the crop's side toward
# the inset; a note word's place is layout's (_column.in_cut_in_zone and
# _column.ends_short_of_inset).
_CUT_IN_LINE_AT_INSET_PT: Final[float] = 3.0


# The reading score


def _normalized(text: str) -> str:
    """`text` with quotation marks stripped from both ends and "’" inside
    taken as "'", as the word list writes "henry's"."""
    return text.strip(_QUOTATION_MARKS).replace(_CURLY_APOSTROPHE, "'")


def _has_letter_or_digit(text: str) -> bool:
    return any(character.isalnum() for character in text)


# A word's part of the reading score (reocr spec, section 1).
_KNOWN_SCORE: Final[int] = 1
_UNKNOWN_SCORE: Final[int] = -1
_PUNCTUATION_SCORE: Final[int] = 0


def _word_score(text: str, lower_case_words: frozenset[str]) -> int:
    """`_KNOWN_SCORE` for a known word, `_UNKNOWN_SCORE` for an unknown one
    (it holds a letter or a digit), `_PUNCTUATION_SCORE` for punctuation."""
    if is_known_word(text, lower_case_words):
        return _KNOWN_SCORE
    return _UNKNOWN_SCORE if _has_letter_or_digit(text) else _PUNCTUATION_SCORE


def _broken_word_score(
    first: str, second: str, lower_case_words: frozenset[str]
) -> int:
    """The score of a word broken at a line end, `first` ending in a
    hyphen: `_KNOWN_SCORE` when each part is known, otherwise the score of
    the joined word."""
    stem = first[:-1]
    if is_known_word(stem, lower_case_words) and is_known_word(
        second, lower_case_words
    ):
        return _KNOWN_SCORE
    return _word_score(stem + second, lower_case_words)


def _is_broken_pair(first: str, second: str) -> bool:
    return (
        first[-1:] in LINE_END_HYPHENS
        and _has_letter_or_digit(first)
        and second[:1].isalpha()
    )


def reading_score(words: Iterable[Word], lower_case_words: frozenset[str]) -> int:
    """The reading score of `words`: its known words minus its unknown
    words (reocr spec, section 1).

    A word is known when `wordlist.is_known_word` accepts it against
    `lower_case_words`, the book language's word list in lower case;
    unknown when it holds a letter or a digit and is not known; neither
    when it is punctuation. Before counting, quotation marks are stripped
    from both ends of each word and "’" inside it is taken as "'"; a word
    ending in a hyphen followed by a word starting with a letter is a word
    broken at a line end and counts once, as known when the two joined, or
    each part, are known, otherwise as the joined word.
    """
    return sum(_word_scores(words, lower_case_words))


def _word_scores(
    words: Iterable[Word], lower_case_words: frozenset[str]
) -> tuple[int, ...]:
    """The score of each word of `words` as `reading_score` counts them: 1
    known, -1 unknown, 0 neither, a word broken at a line end once."""
    texts = tuple(_normalized(word.text) for word in words)
    scores = []
    position = 0
    while position < len(texts):
        text = texts[position]
        if position + 1 < len(texts) and _is_broken_pair(text, texts[position + 1]):
            scores.append(
                _broken_word_score(text, texts[position + 1], lower_case_words)
            )
            position += 2
        else:
            scores.append(_word_score(text, lower_case_words))
            position += 1
    return tuple(scores)


# The small-print page


def is_small_print_page(page: PageWords, measures: BookMeasures) -> bool:
    """Whether `page` is printed wholly in small type, such as a page of an
    index (reocr spec, section 1, "Small-print page"): it has at least 50
    words, and of the body column's rows of two words or more below the
    running-head region, at least 85 in 100 are small rows, whose median
    word height is at most 0.85 of `measures.body_word_height`.

    The column's words are those layout leaves in it after its steps 1, 2
    and 2b (layout spec, section 3), the outer margin notes and the cut-in
    notes taken out, and the running-head region is that of its step 3,
    all on the layer's words. A page with no such row is not one.
    """
    if len(page.words) < _SMALL_PRINT_LEAST_WORDS:
        return False
    split = split_at_column(page.words, page.index, measures)
    rows = group_rows(without_cut_in_notes(split, measures).column)
    head_count = running_head_row_count(rows, measures.body_line_pitch)
    counted = tuple(
        row for row in rows[head_count:] if len(row.words) >= _COUNTED_ROW_LEAST_WORDS
    )
    small = sum(is_small_row(row, measures) for row in counted)
    return bool(counted) and small * 100 >= _SMALL_PRINT_ROWS_PER_100 * len(counted)


# The sides with outer margin notes


def margin_note_sides(
    pages: Iterable[tuple[int, ColumnSplit]], lower_case_words: frozenset[str]
) -> frozenset[Side]:
    """The sides of a book whose outer margins hold notes (reocr spec,
    section 3, kind 2), from `pages`, each page's word count and its words
    placed by its body column (layout steps 1 and 2): a side has them when
    at least 10 in 100 of the pages of 50 words or more have at least 2
    known words, by `lower_case_words`, among that side's margin words."""
    counted = tuple(
        split for count, split in pages if count >= _MARGIN_SIDE_LEAST_WORDS
    )

    def has_notes(margin_words: Iterable[tuple[Word, ...]]) -> bool:
        with_notes = sum(
            sum(is_known_word(word.text, lower_case_words) for word in words)
            >= _MARGIN_SIDE_LEAST_KNOWN
            for words in margin_words
        )
        return bool(counted) and (
            with_notes * 100 >= _MARGIN_SIDE_PAGES_PER_100 * len(counted)
        )

    return frozenset(
        side
        for side, margin_words in (
            (Side.LEFT, tuple(split.left_margin for split in counted)),
            (Side.RIGHT, tuple(split.right_margin for split in counted)),
        )
        if has_notes(margin_words)
    )


# Pixels and points


def pixel_box(box: Box, dpi: int) -> tuple[int, int, int, int]:
    """The pixels of a render at `dpi` that hold `box`, as Pillow's crop
    box: left, top, right and bottom, the right and bottom excluded."""
    scale = dpi / POINTS_PER_INCH
    return (
        math.floor(box.x0 * scale),
        math.floor(box.top * scale),
        math.ceil(box.x1 * scale),
        math.ceil(box.bottom * scale),
    )


# The crops


def small_print_crop(
    *, page_width: float, page_height: float, head_bottom: float | None
) -> Box:
    """The crop of a small-print page (reocr spec, section 3, kind 1): the
    page's full width, from 1 pt below `head_bottom`, the bottom of the
    lowest word of the running-head region, or from the page's top when
    there is none, to the page's foot."""
    top = 0.0 if head_bottom is None else head_bottom + _BELOW_HEAD_PT
    return Box(0.0, top, page_width, page_height)


def margin_strip(
    side: Side,
    *,
    left: float,
    right: float,
    column_top: float,
    lowest: float,
    page_width: float,
) -> Box:
    """The strip of an outer margin on `side` in which its note bands are
    found (reocr spec, section 3, kind 2): from 4 pt inside the page's
    edge to 4 pt outside the column's edge, `left` or `right`, and from 4
    pt above `column_top`, the top of the column's first word, to 4 pt
    below `lowest`, the bottom of the page's lowest word."""
    top = column_top - _STRIP_ABOVE_BELOW_PT
    bottom = lowest + _STRIP_ABOVE_BELOW_PT
    match side:
        case Side.LEFT:
            return Box(_STRIP_PAGE_EDGE_PT, top, left - _STRIP_COLUMN_PT, bottom)
        case Side.RIGHT:
            return Box(
                right + _STRIP_COLUMN_PT, top, page_width - _STRIP_PAGE_EDGE_PT, bottom
            )
        case _:
            assert_never(side)


def note_bands(
    strip: Image.Image, *, dpi: int
) -> tuple[tuple[int, int, int, int], ...]:
    """The note bands of `strip`, a margin strip rendered at `dpi`, top to
    bottom, each as a Pillow crop box in pixels of `strip` (reocr spec,
    section 3, kind 2). ValueError when `dpi` is not `ocr.OCR_DPI`, 300,
    at which the sizes below were measured.

    A pixel is ink when darker than 140 of 255; a pixel row with more than
    one ink pixel is inked; inked rows apart by at most 18 blank rows are
    one band. A band less than 12 px high, with fewer than 150 ink pixels,
    or whose ink is less than 25 px wide is a speck or the scan's edge and
    is left out. Each band is cropped to its ink plus 6 px, inside the
    strip.
    """
    if dpi != OCR_DPI:
        msg = (
            f"a margin strip rendered at {dpi} dpi: note bands are found at "
            f"{OCR_DPI} dpi, at which their sizes in pixels were measured"
        )
        raise ValueError(msg)
    mask = strip.convert("L").point(lambda value: _INK if value < _INK_BELOW else 0)
    width, height = mask.size
    pixels = mask.tobytes()
    ink_by_row = tuple(
        pixels[row * width : (row + 1) * width].count(_INK) for row in range(height)
    )
    inked = tuple(
        row for row, ink in enumerate(ink_by_row) if ink > _INKED_ROW_MORE_THAN
    )
    spans: list[tuple[int, int]] = []
    for row in inked:
        if spans and row - spans[-1][1] - 1 <= _BAND_GAP_MOST_PX:
            spans[-1] = (spans[-1][0], row)
        else:
            spans.append((row, row))
    bands = []
    for first, last in spans:
        ink_box = mask.crop((0, first, width, last + 1)).getbbox()
        if (
            ink_box is None
            or last - first + 1 < _BAND_LEAST_HEIGHT_PX
            or sum(ink_by_row[first : last + 1]) < _BAND_LEAST_INK_PX
            or ink_box[2] - ink_box[0] < _BAND_LEAST_WIDTH_PX
        ):
            continue
        bands.append(
            (
                max(0, ink_box[0] - _BAND_MARGIN_PX),
                max(0, first - _BAND_MARGIN_PX),
                min(width, ink_box[2] + _BAND_MARGIN_PX),
                min(height, last + 1 + _BAND_MARGIN_PX),
            )
        )
    return tuple(bands)


@dataclass(frozen=True, slots=True)
class CutInCrop:
    """A crop of notes cut into the column (reocr spec, section 3, kind 3):
    its `box` in points, and the cut-in `zones` it was made from, each
    (top, bottom) in points."""

    box: Box
    zones: tuple[tuple[float, float], ...]


def _crop_sides(side: Side, edge: float, inset: float) -> tuple[float, float]:
    """The left and right sides of a cut-in crop on `side`, whose column
    edge is `edge` and whose cut-in inset is `inset`: from 3 pt outside
    the edge to 3 pt short of the inset."""
    match side:
        case Side.LEFT:
            return (
                edge - _CUT_IN_CROP_OUTSIDE_PT,
                edge + inset - _CUT_IN_CROP_OUTSIDE_PT,
            )
        case Side.RIGHT:
            return (
                edge - inset + _CUT_IN_CROP_OUTSIDE_PT,
                edge + _CUT_IN_CROP_OUTSIDE_PT,
            )
        case _:
            assert_never(side)


def cut_in_crops(
    zones: tuple[tuple[float, float], ...],
    side: Side,
    *,
    edge: float,
    inset: float,
    pitch: float,
    head_bottom: float | None,
) -> tuple[CutInCrop, ...]:
    """The crops of the cut-in `zones` of one side of a page, top to bottom
    (reocr spec, section 3, kind 3).

    Each zone, (top, bottom), is widened by 2.5 `pitch`es above and
    below, never above 1 pt below `head_bottom`, the bottom of the lowest
    word of the running-head region; across, a crop runs from 3 pt outside
    the column's `edge` on `side` to 3 pt short of the cut-in `inset`
    inside it. Zones whose widened crops overlap are one crop.
    """
    left, right = _crop_sides(side, edge, inset)
    ceiling = -math.inf if head_bottom is None else head_bottom + _BELOW_HEAD_PT
    widen = _CUT_IN_WIDEN_PITCHES * pitch
    merged: list[tuple[float, float, tuple[tuple[float, float], ...]]] = []
    for zone in sorted(zones):
        top = max(zone[0] - widen, ceiling)
        bottom = zone[1] + widen
        if merged and top <= merged[-1][1]:
            last_top, last_bottom, last_zones = merged[-1]
            merged[-1] = (last_top, max(last_bottom, bottom), (*last_zones, zone))
        else:
            merged.append((top, bottom, (zone,)))
    return tuple(
        CutInCrop(Box(left, top, right, bottom), crop_zones)
        for top, bottom, crop_zones in merged
    )


def footnote_band_crop(
    band_words: tuple[Word, ...], *, left: float, right: float
) -> Box:
    """The crop of a page's footnote band, whose words are `band_words`,
    not empty (reocr spec, section 3, kind 4): from 3 pt outside the
    column's `left` edge to 3 pt outside its `right` edge, and from 3 pt
    above the band's highest word to 3 pt below its lowest."""
    return Box(
        left - _FOOTNOTE_BAND_PT,
        min(word.box.top for word in band_words) - _FOOTNOTE_BAND_PT,
        right + _FOOTNOTE_BAND_PT,
        max(word.box.bottom for word in band_words) + _FOOTNOTE_BAND_PT,
    )


# The words a region replaces


@dataclass(frozen=True, slots=True, kw_only=True)
class RegionReading:
    """A region read, before the choice between its two readings (reocr
    spec, section 4).

    `kind` and `box`, the crop in points, are those of its record; `side`
    is the side of a margin note band or a cut-in crop, None for the
    others. `ocr_words` are Tesseract's words, after the filters of a
    cut-in crop. `layer_words` are the layer words it may replace; it
    replaces those under a word of Tesseract's it keeps
    (`model.replaced_layer_words`).
    """

    kind: RereadKind
    side: Side | None
    box: Box
    ocr_words: tuple[Word, ...]
    layer_words: tuple[Word, ...]


def _inside(point: tuple[float, float], box: Box) -> bool:
    x, y = point
    return box.x0 <= x <= box.x1 and box.top <= y <= box.bottom


def _overlap(first: Box, second: Box) -> bool:
    return (
        first.x0 < second.x1
        and second.x0 < first.x1
        and first.top < second.bottom
        and second.top < first.bottom
    )


def small_print_reading(
    box: Box,
    ocr_words: tuple[Word, ...],
    *,
    page_words: tuple[Word, ...],
    head_words: tuple[Word, ...],
) -> RegionReading:
    """A small-print page read in the crop `box`, with Tesseract's
    `ocr_words`: it may replace every word of the page, `page_words`, but
    those of the running-head region, `head_words`, its margins and its
    band included."""
    return RegionReading(
        kind=RereadKind.SMALL_PRINT_PAGE,
        side=None,
        box=box,
        ocr_words=ocr_words,
        layer_words=take_out_once((page_words,), head_words)[0],
    )


def margin_note_reading(
    side: Side,
    box: Box,
    ocr_words: tuple[Word, ...],
    *,
    page_words: tuple[Word, ...],
    edge: float,
) -> RegionReading:
    """A note band of the outer margin on `side`, cropped at `box`, with
    Tesseract's `ocr_words`. It may replace the words of `page_words` whose
    middle lies within 12 pt above or below the band and that reach 2 pt
    or more into that side's margin, past the column's left `edge` or its
    right `edge` (the margin words and the words that cross the edge so
    far), or lie under one of `ocr_words` (`model.is_under_ocr_word`), as
    the layer's stray letters at the column's edge."""
    match side:
        case Side.LEFT:
            in_margin = tuple(
                word
                for word in page_words
                if word.box.x0 <= edge - _INTO_MARGIN_PT
                or is_under_ocr_word(word, ocr_words)
            )
        case Side.RIGHT:
            in_margin = tuple(
                word
                for word in page_words
                if word.box.x1 >= edge + _INTO_MARGIN_PT
                or is_under_ocr_word(word, ocr_words)
            )
        case _:
            assert_never(side)
    return RegionReading(
        kind=RereadKind.MARGIN_NOTE,
        side=side,
        box=box,
        ocr_words=ocr_words,
        layer_words=tuple(
            word
            for word in in_margin
            if box.top - _BAND_REACH_PT
            <= word_middle(word)[1]
            <= box.bottom + _BAND_REACH_PT
        ),
    )


def _reaches_inset_side(word: Word, side: Side, crop: Box) -> bool:
    """Whether `word` ends within 3 pt of the side of `crop` toward the
    inset: a body line runs on past it."""
    match side:
        case Side.LEFT:
            return word.box.x1 >= crop.x1 - _CUT_IN_LINE_AT_INSET_PT
        case Side.RIGHT:
            return word.box.x0 <= crop.x0 + _CUT_IN_LINE_AT_INSET_PT
        case _:
            assert_never(side)


def cut_in_reading(
    side: Side,
    crop: CutInCrop,
    ocr_lines: tuple[tuple[Word, ...], ...],
    *,
    edge: float,
    inset: float,
    cut_in_words: tuple[Word, ...],
    column_words: tuple[Word, ...],
) -> RegionReading:
    """A crop of notes cut into the column on `side`, read by Tesseract as
    `ocr_lines`, its words grouped by its lines (reocr spec, section 3,
    kind 3, and section 4).

    `edge` is the column's edge on `side` and `inset` the book's cut-in
    inset there; `cut_in_words` are the side's words layout took out as
    cut-in notes, and `column_words` those it left in the column. A word of
    the column the crop may replace has its vertical middle within 1 pt of
    a zone of the crop and ends 4 pt or more short of the inset; every
    other column word overlapping the crop is a body word. Of Tesseract's
    words, a line with a word ending within 3 pt of the crop's side toward
    the inset is dropped, and so is a word overlapping a body word. The
    crop may replace the cut-in words in its zones, give or take 1 pt, and
    the column words it may replace; never a body word.
    """
    replaceable = tuple(
        word
        for word in column_words
        if in_cut_in_zone(word, crop.zones)
        and ends_short_of_inset(word, side, edge, inset)
    )
    body = tuple(
        word
        for word in take_out_once((column_words,), replaceable)[0]
        if _overlap(word.box, crop.box)
    )
    ocr_words = tuple(
        word
        for line in ocr_lines
        if not any(_reaches_inset_side(word, side, crop.box) for word in line)
        for word in line
        if not any(_overlap(word.box, body_word.box) for body_word in body)
    )
    return RegionReading(
        kind=RereadKind.CUT_IN_NOTE,
        side=side,
        box=crop.box,
        ocr_words=ocr_words,
        layer_words=(
            *(word for word in cut_in_words if in_cut_in_zone(word, crop.zones)),
            *replaceable,
        ),
    )


def footnote_band_reading(
    box: Box, ocr_words: tuple[Word, ...], *, band_words: tuple[Word, ...]
) -> RegionReading:
    """A page's footnote band, cropped at `box`, with Tesseract's
    `ocr_words`: it may replace the band's words, `band_words`."""
    return RegionReading(
        kind=RereadKind.FOOTNOTE_BAND,
        side=None,
        box=box,
        ocr_words=ocr_words,
        layer_words=band_words,
    )


# The records of a page

# Tesseract's junk (reocr spec, section 4): a word of no letter or digit is
# dropped unless each character is punctuation or a sign the books print. In
# the kept records of whole Stubbs, Domesday and Gierke it read a pencil
# curve or a stain as "|", "¥", "\\", "©", "@", "~", "_", "¢" (34 tokens).
_PRINTED_SIGNS: Final[frozenset[str]] = frozenset(".,;:!?'\"‘’“”()[]-–—§&£$%*†‡¶/")


# An underscore at either end of a Tesseract word is junk glued to it
# (reocr spec, section 4): "_and" on Gierke page 88; no book prints one.
_GLUED_JUNK: Final[str] = "_"


def _without_glued_junk(word: Word) -> Word:
    """`word`, Tesseract's, without the underscores at its ends."""
    return replace(word, text=word.text.strip(_GLUED_JUNK))


def _is_junk(text: str) -> bool:
    """Whether `text`, a word of Tesseract's, is junk: it has no letter or
    digit and a character that is not punctuation or a printed sign."""
    return not _has_letter_or_digit(text) and not set(text) <= _PRINTED_SIGNS


# A later region drops a Tesseract word that an earlier kept region read
# within 16 pt above or below, as model.replaced_layer_words pairs words of
# one text (reocr spec, section 4).
_READ_BEFORE_REACH_PT: Final[float] = 16.0


def _read_before(word: Word, earlier: Iterable[Word]) -> bool:
    """Whether a word of `earlier`, Tesseract's words of the page's earlier
    kept regions, has the letters and digits of `word`, case-folded and not
    empty, with its middle within 16 pt above or below `word`'s."""
    folded = folded_letters_and_digits(word.text)
    return bool(folded) and any(
        folded_letters_and_digits(other.text) == folded
        and abs(word_middle(other)[1] - word_middle(word)[1]) <= _READ_BEFORE_REACH_PT
        for other in earlier
    )


def _kind_rank(kind: RereadKind) -> int:
    """The place of `kind` among a page's records (reocr spec, section 4)."""
    match kind:
        case RereadKind.SMALL_PRINT_PAGE:
            return 0
        case RereadKind.MARGIN_NOTE:
            return 1
        case RereadKind.CUT_IN_NOTE:
            return 2
        case RereadKind.FOOTNOTE_BAND:
            return 3
        case _:
            assert_never(kind)


def _record_order(reading: RegionReading) -> tuple[int, float, bool]:
    return (_kind_rank(reading.kind), reading.box.top, reading.side is Side.RIGHT)


def _scores_higher(ocr_scores: tuple[int, ...], layer_scores: tuple[int, ...]) -> bool:
    """Whether Tesseract's reading, scored word by word as `ocr_scores`,
    wins over the layer's, `layer_scores` (reocr spec, section 3): a
    higher reading score, or the same with more known words."""
    ocr_score, layer_score = sum(ocr_scores), sum(layer_scores)
    return ocr_score > layer_score or (
        ocr_score == layer_score
        and ocr_scores.count(_KNOWN_SCORE) > layer_scores.count(_KNOWN_SCORE)
    )


# The marks stripped from the ends of a layer word before it is taken as a
# known word as printed (reocr spec, section 4).
_END_MARKS: Final[str] = ".,;:!?()" + _QUOTATION_MARKS


def _is_known_as_printed(text: str, lower_case_words: frozenset[str]) -> bool:
    """Whether `text`, a layer word, is a known word as printed: known
    (`wordlist.is_known_word`), and nothing but letters, digits,
    apostrophes and hyphens once the marks . , ; : ! ? ( ) and quotation
    marks are stripped from its ends ("lo/.," is not, though "lo" is in
    the word list)."""
    return is_known_word(text, lower_case_words) and all(
        character.isalnum() or character in "-'’"
        for character in text.strip(_END_MARKS)
    )


def _is_sure_single_word(
    ocr_words: tuple[Word, ...],
    ocr_scores: tuple[int, ...],
    page_words: tuple[Word, ...],
) -> bool:
    """Whether `ocr_words`, Tesseract's reading of a region over no layer
    word, scored word by word as `ocr_scores`, holds one sure single word
    (reocr spec, section 3): one known word, of 4 letters or more, and
    beside it only punctuation, every word read at a confidence of 80 or
    more, no word broken at a line end,
    and no word of `page_words`,
    the page's layer, that may read one of them (`model.may_read`)."""
    if any(
        _is_broken_pair(_normalized(first.text), _normalized(second.text))
        for first, second in itertools.pairwise(ocr_words)
    ):
        return False
    known = tuple(
        word
        for word, score in zip(ocr_words, ocr_scores, strict=True)
        if score == _KNOWN_SCORE
    )
    return (
        len(known) == 1
        and _UNKNOWN_SCORE not in ocr_scores
        and sum(character.isalpha() for character in known[0].text)
        >= _SURE_WORD_LEAST_LETTERS
        and all(
            word.ocr_confidence is not None
            and word.ocr_confidence >= _SURE_WORD_LEAST_CONFIDENCE
            for word in ocr_words
        )
        and not any(
            may_read(layer_word, ocr_word)
            for layer_word in page_words
            for ocr_word in ocr_words
        )
    )


def page_rereads(
    page_index: int,
    readings: tuple[RegionReading, ...],
    lower_case_words: frozenset[str],
    *,
    page_words: tuple[Word, ...],
) -> tuple[Reread, ...]:
    """The records of the regions of page `page_index` read again, in the
    order of the records (reocr spec, section 4): a small-print page; else
    the margin note bands, top to bottom with the left side first at the
    same top, then the cut-in crops likewise, then the footnote band.

    Tesseract's junk, a word of no letter or digit that is not punctuation
    or a printed sign, is dropped first and counted in the record, and so
    are the underscores at the ends of a word, each word stripped counted
    once. The
    regions are taken in that order. A word of Tesseract's whose middle
    lies inside the crop of an earlier kept region is dropped, and so is
    one that reads no layer word the region may still replace and whose
    letters and digits are those of a Tesseract word of an earlier kept
    region within 16 pt above or below, so that no printed word is read in
    by two regions. Of the layer words a region
    may replace, it replaces those under one of its words of Tesseract's
    (`model.replaced_layer_words`) that an earlier kept region does not
    replace; the others stay in the layer. A region is kept when its
    words of Tesseract's are not empty and score higher than the layer
    words it replaces, by `reading_score` against `lower_case_words`, or
    the same with more known words, and, when it replaces no layer word, hold at least 2 known words, or one
    known word of 4 letters or more, all its words read at a confidence
    of 80 or more, that no word of `page_words`, the page's text layer,
    may read (`model.may_read`). A
    region where both readings are empty, before the junk is dropped, is
    not recorded. ValueError when
    a small-print page comes with another region: no other region of such
    a page is read.
    """
    ordered = sorted(readings, key=_record_order)
    if len(ordered) > 1 and ordered[0].kind is RereadKind.SMALL_PRINT_PAGE:
        msg = (
            f"page {page_index} is read as a small-print page and as "
            f"{len(ordered) - 1} other regions; a small-print page is read whole"
        )
        raise ValueError(msg)

    def is_known(text: str) -> bool:
        return _is_known_as_printed(text, lower_case_words)

    earlier_crops: list[Box] = []
    earlier_ocr_words: list[Word] = []
    replaced: list[Word] = []
    records = []
    for reading in ordered:
        read = tuple(
            word
            for word in reading.ocr_words
            if not any(_inside(word_middle(word), crop) for crop in earlier_crops)
        )
        not_junk = tuple(word for word in read if not _is_junk(word.text))
        outside_crops = tuple(_without_glued_junk(word) for word in not_junk)
        stripped_count = sum(
            word.text != stripped.text
            for word, stripped in zip(not_junk, outside_crops, strict=True)
        )
        replaceable = take_out_once((reading.layer_words,), replaced)[0]
        matched = matched_ocr_positions(replaceable, outside_crops, is_known=is_known)
        ocr_words = tuple(
            word
            for position, word in enumerate(outside_crops)
            if position in matched or not _read_before(word, earlier_ocr_words)
        )
        layer_words = replaced_layer_words(replaceable, ocr_words, is_known=is_known)
        if not layer_words and not read:
            continue
        layer_scores = _word_scores(layer_words, lower_case_words)
        layer_score = sum(layer_scores)
        ocr_scores = _word_scores(ocr_words, lower_case_words)
        ocr_score = sum(ocr_scores)
        kept = _scores_higher(ocr_scores, layer_scores) and (
            bool(layer_words)
            or ocr_scores.count(_KNOWN_SCORE) >= _OVER_NOTHING_LEAST_KNOWN
            or _is_sure_single_word(ocr_words, ocr_scores, page_words)
        )
        if kept:
            replaced.extend(layer_words)
            earlier_crops.append(reading.box)
            earlier_ocr_words.extend(ocr_words)
        records.append(
            Reread(
                page_index=page_index,
                kind=reading.kind,
                box=reading.box,
                layer_words=layer_words,
                ocr_words=ocr_words,
                layer_score=layer_score,
                ocr_score=ocr_score,
                kept=kept,
                dropped_junk_count=len(read) - len(not_junk) + stripped_count,
            )
        )
    return tuple(records)
