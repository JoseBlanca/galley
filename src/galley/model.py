"""The formats of the files between stages, and the functions that write and read them.

Every format is a frozen dataclass: tuples for sequences, StrEnum for finite
sets, floats for positions in PDF points with the origin at the top left of
the page, page indices from 0 (architecture sections 7 and 8). Each of the
four JSON files, pages.json, words.json, lines.json and blocks.json, has a
`write_<file>` and a `read_<file>`; the edits files under `edits/` have
`write_edits` and `read_edits`. No stage writes or parses these files by
itself.
"""

import bisect
import collections
import dataclasses
import difflib
import functools
import hashlib
import itertools
import json
import math
import os
import re
import threading
import types
import typing
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from galley.errors import EditError, InputFileError

# 2 since the plan clean-text, 17 November 2026: the front matter in
# pages.json and words.json, the re-read regions in lines.json
# (architecture section 8).
PAGES_FORMAT_VERSION = 2
WORDS_FORMAT_VERSION = 2
LINES_FORMAT_VERSION = 2
# 2 since the second plan of structure, 16 November 2026 (architecture section 8).
BLOCKS_FORMAT_VERSION = 2
EDITS_FORMAT_VERSION = 1


@dataclass(frozen=True, slots=True)
class Box:
    """A rectangle on a page, in PDF points, origin at the top left, `top`
    growing downwards. Written in JSON as a list of four numbers."""

    x0: float
    top: float
    x1: float
    bottom: float


# pages.json


class PageKind(StrEnum):
    """What a page is, as analyze finds it: blank, text, a plate (mostly a
    picture), excluded by the config, or front matter: a page before the
    book's text that would otherwise be a text page (front-matter spec)."""

    BLANK = "blank"
    TEXT = "text"
    PLATE = "plate"  # mostly a picture
    EXCLUDED = "excluded"
    FRONT_MATTER = "front_matter"  # before the front-matter end, dropped


class TextSource(StrEnum):
    """Where a page's words come from: the book's own text layer, galley's
    OCR, or none (blank, excluded and front-matter pages, and plates without
    a text layer)."""

    TEXT_LAYER = "text_layer"
    OCR = "ocr"
    NONE = "none"  # blank, excluded and front-matter pages


class OcrVerdict(StrEnum):
    """The outcome of the audit of the book's text layer (architecture
    section 7b) when the run goes on."""

    LAYER_KEPT = "layer_kept"  # the layer scored as well as Tesseract
    LAYER_DOUBTFUL = "layer_doubtful"  # below, but not clearly; the run goes on


@dataclass(frozen=True, slots=True)
class SampledPage:
    """A page of the OCR audit, scored as the share of its words found in
    the word list, from 0 to 1, for the text layer and for Tesseract."""

    page_index: int
    layer_score: float
    tesseract_score: float


@dataclass(frozen=True, slots=True)
class OcrAudit:
    """The audit of the book's own text layer (architecture section 7b)."""

    sampled: tuple[SampledPage, ...]
    verdict: OcrVerdict


@dataclass(frozen=True, slots=True, kw_only=True)
class PageInfo:
    """What analyze found about one page.

    `text_layer_score` is the share of the layer's words found in the word
    list, from 0 to 1, or None without a layer. `blank_checked_by_ocr` is
    true for a page without a text layer that the OCR audit read and found
    blank.
    """

    index: int
    width_pt: float
    height_pt: float
    kind: PageKind
    text_source: TextSource
    text_layer_score: float | None
    exclude_regions: tuple[Box, ...]
    blank_checked_by_ocr: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class PagesFile:
    """pages.json, written by analyze. `ocr_audit` is None when the config's
    `ocr` is `trust` or `redo`, and in the walking skeleton."""

    format_version: int = PAGES_FORMAT_VERSION
    source_pdf_sha256: str
    pages: tuple[PageInfo, ...]
    ocr_audit: OcrAudit | None


# words.json


@dataclass(frozen=True, slots=True)
class Word:
    """A word as its source gave it. `ocr_confidence` is Tesseract's, from 0
    to 100, or None for a word of the text layer."""

    text: str
    box: Box
    ocr_confidence: float | None


@dataclass(frozen=True, slots=True)
class Figure:
    """A picture cut from a page. `image` is its path relative to the book
    folder, with `/` as separator; `dpi` is the resolution it was rendered at."""

    box: Box
    image: str
    dpi: int


@dataclass(frozen=True, slots=True, kw_only=True)
class PageWords:
    """The words of one page, in the order the source gave them, and its figures."""

    index: int
    text_source: TextSource
    words: tuple[Word, ...]
    figures: tuple[Figure, ...]


class RemovalReason(StrEnum):
    """Why a stage took text out of the book. A stage spec adds a reason
    when it removes a new kind of text."""

    EXCLUDED_PAGE = "excluded_page"
    EXCLUDED_REGION = "excluded_region"
    FRONT_MATTER = "front_matter"  # a word of a page before the book's text
    RUNNING_HEAD = "running_head"
    PAGE_NUMBER = "page_number"
    SIGNATURE_MARK = "signature_mark"
    PLATE_TEXT = "plate_text"  # stray text-layer characters on a plate
    STRAY_MARK = "stray_mark"  # a line with no letter or digit above a running head
    GUIDE_WORDS = "guide_words"  # "BUR CON" under the running head of an index page


@dataclass(frozen=True, slots=True, kw_only=True)
class Removal:
    """Text a stage took out of the book on purpose, with where it was and why."""

    page_index: int
    box: Box
    text: str
    reason: RemovalReason


@dataclass(frozen=True, slots=True, kw_only=True)
class WordsFile:
    """words.json, written by extract. `removals` holds the words of
    excluded pages and regions and of front-matter pages, one per word."""

    format_version: int = WORDS_FORMAT_VERSION
    source_pdf_sha256: str
    pages: tuple[PageWords, ...]
    removals: tuple[Removal, ...]


# lines.json


@dataclass(frozen=True, slots=True)
class Line:
    """A line of one region of a page, its words left to right."""

    box: Box
    words: tuple[Word, ...]


@dataclass(frozen=True, slots=True)
class Region:
    """A part of a page whose lines are read one after the other."""

    box: Box
    lines: tuple[Line, ...]


@dataclass(frozen=True, slots=True)
class PageLayout:
    """The regions of one page in reading order, and its figures, copied
    from words.json."""

    index: int
    regions: tuple[Region, ...]
    figures: tuple[Figure, ...]


class RereadKind(StrEnum):
    """What region of a page layout read again with Tesseract (reocr spec,
    section 3)."""

    SMALL_PRINT_PAGE = "small_print_page"  # read whole below its running head
    MARGIN_NOTE = "margin_note"  # one note band of an outer margin
    CUT_IN_NOTE = "cut_in_note"  # one crop of notes cut into the column
    FOOTNOTE_BAND = "footnote_band"  # one page's footnote band


@dataclass(frozen=True, slots=True, kw_only=True)
class Reread:
    """A region of a page that layout read again with Tesseract, recorded
    whether its reading was kept or not (reocr spec, section 4).

    `box` is the crop, in points. `layer_words` are the words of words.json
    the reading would replace, `ocr_words` Tesseract's, with boxes in points
    and their confidence. `layer_score` and `ocr_score` are each reading's
    known words minus its unknown words. When `kept`, `ocr_words` stand in
    lines.json in place of `layer_words`; otherwise the record changes
    nothing. `dropped_junk_count` is the number of Tesseract's words of no
    letter or digit, not punctuation or a sign the books print, dropped
    before `ocr_words` (reocr spec, section 4).
    """

    page_index: int
    kind: RereadKind
    box: Box
    layer_words: tuple[Word, ...]
    ocr_words: tuple[Word, ...]
    layer_score: int
    ocr_score: int
    kept: bool
    dropped_junk_count: int = 0


# A kept Reread replaces a layer word that is the same printed word as one
# of its Tesseract words (reocr spec, section 4). (a) Its middle lies inside
# that word's box widened by 2 pt up and down and 1 pt across: the layer's
# lines lie off Tesseract's up or down, not its words across, and with 2 pt
# across a word Tesseract did not read was taken by its neighbour ("The"
# beside the list number "7" on Gierke page 62, "224" on Domesday page
# 548). Measured on 17 November 2026 on the kept
# records of whole Stubbs, Domesday, Gierke and Haskins, the middle of a
# layer word lies within 2 pt of the box of Tesseract's word of the same
# text for 95 in 100 of Domesday's pairs and 92 of Gierke's, and the middle
# of a Tesseract word lies at least 2.9 pt above the box of the line below
# it for 99 in 100 words, so that a word Tesseract did not read stays out
# of its neighbour's reach. (b) Its letters and digits, case-folded, equal
# those of a Tesseract word whose middle lies within 16 pt above or below,
# the nearest that no other layer word of that text has matched: in the
# same measurement the middles of 99 in 100 of Domesday's pairs lie within
# 8.2 pt of each other, and Gierke's layer reads note lines up to 15 pt off
# Tesseract's ("tium" on page 265, "ality." on 248); with 12 pt, 5 of
# Gierke's 415 kept margin-note records still read a word twice.
_UNDER_OCR_WORD_UP_DOWN_PT = 2.0
_UNDER_OCR_WORD_ACROSS_PT = 1.0
_SAME_TEXT_REACH_PT = 16.0
# (c) Its letters, 3 or more, are alike to those of such a Tesseract word,
# by difflib's ratio, 0.6 or more: the layer's garbled copy of a note word
# it reads a few points off the ink ("fllght'" below "flight.", Domesday
# page 76). Measured on 17 November 2026 on the kept margin-note records of
# whole Domesday and Gierke: 53 copies at 0.6 or more, none of them a word
# Tesseract missed but numbers, which rule (c) leaves to (a) and (b); from
# 0.5 to 0.6, 10 copies and 4 body words at the column's edge ("for" beside
# "lord", Domesday page 310).
# A layer word glued over two or three Tesseract words is the same printed
# words as they ("of,96" where Tesseract read "of," "96", Stubbs' index page
# 312): each Tesseract word's middle lies inside its box widened by 1 pt.
_GLUED_WORD_COUNTS = (2, 3)
_GLUED_WIDEN_PT = 1.0
_ALIKE_LEAST_LETTERS = 3
_ALIKE_LEAST_RATIO = 0.6


def word_middle(word: Word) -> tuple[float, float]:
    """The middle of `word`'s box, (across, down) in points."""
    return (word.box.x0 + word.box.x1) / 2, (word.box.top + word.box.bottom) / 2


def _is_under(word: Word, ocr_word: Word) -> bool:
    x, y = word_middle(word)
    return (
        ocr_word.box.x0 - _UNDER_OCR_WORD_ACROSS_PT
        <= x
        <= ocr_word.box.x1 + _UNDER_OCR_WORD_ACROSS_PT
        and ocr_word.box.top - _UNDER_OCR_WORD_UP_DOWN_PT
        <= y
        <= ocr_word.box.bottom + _UNDER_OCR_WORD_UP_DOWN_PT
    )


def is_under_ocr_word(word: Word, ocr_words: Sequence[Word]) -> bool:
    """Whether the middle of `word`, a word of the text layer, lies inside
    the box of one of `ocr_words`, Tesseract's, widened by 2 pt up and down
    and 1 pt across (reocr spec, section 4). Boxes in points."""
    return any(_is_under(word, ocr_word) for ocr_word in ocr_words)


def folded_letters_and_digits(text: str) -> str:
    """The letters and digits of `text`, case-folded."""
    return "".join(character for character in text if character.isalnum()).casefold()


def _letter_count(text: str) -> int:
    return sum(character.isalpha() for character in text)


def _folded_letters(text: str) -> str:
    """The letters of `text`, case-folded."""
    return "".join(character for character in text if character.isalpha()).casefold()


def _are_alike(layer_text: str, ocr_text: str) -> bool:
    """Whether the case-folded letters of `layer_text` and `ocr_text` are
    alike, by difflib's ratio."""
    layer_letters = _folded_letters(layer_text)
    ocr_letters = _folded_letters(ocr_text)
    return (
        difflib.SequenceMatcher(None, layer_letters, ocr_letters).ratio()
        >= _ALIKE_LEAST_RATIO
    )


def _overlap_up_and_down(first: Word, second: Word) -> bool:
    return first.box.top < second.box.bottom and second.box.top < first.box.bottom


def _under_line(layer_words: Sequence[Word], ocr_word: Word) -> tuple[int, ...]:
    """The positions in `layer_words` of the words under `ocr_word` that
    are of its printed line: taken nearest first, by the distance of their
    middles from its middle up or down, each whose box overlaps, up and
    down, those of every word taken before it."""
    ocr_middle = word_middle(ocr_word)[1]
    under = sorted(
        (index for index, word in enumerate(layer_words) if _is_under(word, ocr_word)),
        key=lambda index: (abs(word_middle(layer_words[index])[1] - ocr_middle), index),
    )
    line: list[int] = []
    for index in under:
        if all(
            _overlap_up_and_down(layer_words[index], layer_words[other])
            for other in line
        ):
            line.append(index)
    return tuple(sorted(line))


def _lies_over(ocr_word: Word, word: Word) -> bool:
    """Whether the middle of `ocr_word` lies inside the box of `word`
    widened by 1 pt."""
    x, y = word_middle(ocr_word)
    return (
        word.box.x0 - _GLUED_WIDEN_PT <= x <= word.box.x1 + _GLUED_WIDEN_PT
        and word.box.top - _GLUED_WIDEN_PT <= y <= word.box.bottom + _GLUED_WIDEN_PT
    )


def _glued_over(word: Word, ocr_words: Sequence[Word]) -> tuple[int, ...]:
    """The positions in `ocr_words` of two or three Tesseract words that
    follow each other there, each lying over `word`, a layer word, whose
    letters and digits, joined, are those of `word`: the words the layer
    glued into `word`. The first such group, of two words before three;
    () when there is none."""
    folded = folded_letters_and_digits(word.text)
    if not folded:
        return ()
    for count in _GLUED_WORD_COUNTS:
        for start in range(len(ocr_words) - count + 1):
            group = ocr_words[start : start + count]
            if all(_lies_over(ocr_word, word) for ocr_word in group) and (
                "".join(folded_letters_and_digits(ocr_word.text) for ocr_word in group)
                == folded
            ):
                return tuple(range(start, start + count))
    return ()


def may_read(word: Word, ocr_word: Word) -> bool:
    """Whether `ocr_word`, Tesseract's, may be a reading of the printed
    word that `word`, a word of the text layer, reads, by one of the rules
    of `replaced_layer_words` taken alone, whatever other words match:
    `word` lies under it, or, within 16 pt above or below, its letters and
    digits are those of `word`, or its letters are alike to those of a
    `word` of 3 letters or more. Boxes in points."""
    if _is_under(word, ocr_word):
        return True
    if abs(word_middle(ocr_word)[1] - word_middle(word)[1]) > _SAME_TEXT_REACH_PT:
        return False
    return (
        bool(folded_letters_and_digits(word.text))
        and folded_letters_and_digits(word.text)
        == folded_letters_and_digits(ocr_word.text)
    ) or (
        _letter_count(word.text) >= _ALIKE_LEAST_LETTERS
        and _are_alike(word.text, ocr_word.text)
    )


def _pairing(
    layer_words: Sequence[Word], ocr_words: Sequence[Word]
) -> tuple[tuple[bool, ...], frozenset[int]]:
    """Which of `layer_words` the rules of `replaced_layer_words` match,
    and the positions in `ocr_words` of the Tesseract words they match."""
    # (a): a Tesseract word with layer words under it reads the printed
    # words of one line, whatever the texts, and pairs with no other.
    under_line = {
        index for ocr_word in ocr_words for index in _under_line(layer_words, ocr_word)
    }
    # (a) also: a layer word glued over two or three Tesseract words, which
    # read it and pair with no other.
    glued = {
        index: positions
        for index, word in enumerate(layer_words)
        if (positions := _glued_over(word, ocr_words))
    }
    under = tuple(
        index in under_line or index in glued for index in range(len(layer_words))
    )
    taken = {
        position
        for position, ocr_word in enumerate(ocr_words)
        if any(_is_under(word, ocr_word) for word in layer_words)
    } | {position for positions in glued.values() for position in positions}
    # (b): the pairs of a layer word and a Tesseract word of its text, the
    # nearest first, each word in one pair at most.
    pairs = sorted(
        (
            abs(word_middle(ocr_word)[0] - word_middle(word)[0])
            + abs(word_middle(ocr_word)[1] - word_middle(word)[1]),
            index,
            position,
        )
        for index, word in enumerate(layer_words)
        if not under[index] and folded_letters_and_digits(word.text)
        for position, ocr_word in enumerate(ocr_words)
        if position not in taken
        and folded_letters_and_digits(ocr_word.text)
        == folded_letters_and_digits(word.text)
        and abs(word_middle(ocr_word)[1] - word_middle(word)[1]) <= _SAME_TEXT_REACH_PT
    )
    matched = list(under)
    for _, index, position in pairs:
        if not matched[index] and position not in taken:
            matched[index] = True
            taken.add(position)
    # (c): the pairs of a layer word of 3 letters or more and a Tesseract
    # word whose letters are alike, the nearest first, each word in one
    # pair at most.
    alike_pairs = sorted(
        (
            abs(word_middle(ocr_word)[0] - word_middle(word)[0])
            + abs(word_middle(ocr_word)[1] - word_middle(word)[1]),
            index,
            position,
        )
        for index, word in enumerate(layer_words)
        if not matched[index] and _letter_count(word.text) >= _ALIKE_LEAST_LETTERS
        for position, ocr_word in enumerate(ocr_words)
        if position not in taken
        and abs(word_middle(ocr_word)[1] - word_middle(word)[1]) <= _SAME_TEXT_REACH_PT
        and _are_alike(word.text, ocr_word.text)
    )
    for _, index, position in alike_pairs:
        if not matched[index] and position not in taken:
            matched[index] = True
            taken.add(position)
    return tuple(matched), frozenset(taken)


def replaced_layer_words(
    layer_words: Sequence[Word], ocr_words: Sequence[Word]
) -> tuple[Word, ...]:
    """The words of `layer_words`, the text layer's words a region read
    again may replace, that a kept Reread with Tesseract's `ocr_words`
    replaces, in their order: each the same printed word as one of
    `ocr_words` (reocr spec, section 4).

    A layer word is matched (a) when its middle lies inside the box of
    one of `ocr_words` widened by 2 pt up and down and 1 pt across, and
    it is of that word's printed line: the layer words under it taken
    nearest first, by their middles up or down, each whose box overlaps,
    up and down, those of all taken before it; or when its letters and
    digits are those of two or three consecutive `ocr_words` joined, each
    with its middle inside its box widened by 1 pt, a word the layer
    glued; or else (b) when its letters and digits, case-folded and not empty, equal
    those of one of `ocr_words` whose middle lies within 16 pt above or
    below its own and that no other layer word has matched;
    or else (c) when it has 3 letters or more and its case-folded letters
    are alike, by difflib's ratio of 0.6 or more, to those of one of
    `ocr_words` within 16 pt above or below that (a) and (b) left
    unmatched. A Tesseract word is matched in (a) by any layer word under
    it, whatever its text, and by a layer word glued over it; in (b) and (c) the pairs of a layer word and a
    Tesseract word are taken nearest first, by the distance of their
    middles across plus up or down, each word in one pair at most. A layer
    word matched by none stays in the layer. Boxes in points.
    """
    matched, _ = _pairing(layer_words, ocr_words)
    return tuple(
        word
        for word, is_matched in zip(layer_words, matched, strict=True)
        if is_matched
    )


def matched_ocr_positions(
    layer_words: Sequence[Word], ocr_words: Sequence[Word]
) -> frozenset[int]:
    """The positions in `ocr_words`, Tesseract's, of the words that read a
    word of `layer_words` by the rules of `replaced_layer_words`: those
    with a layer word under them or glued over them, and those paired by
    (b) or (c)."""
    _, positions = _pairing(layer_words, ocr_words)
    return positions


def take_out_once(
    groups: tuple[tuple[Word, ...], ...], taken: Iterable[Word]
) -> tuple[tuple[Word, ...], ...]:
    """`groups` of words less the words of `taken`, each word of `taken`
    taken out once, from the first group that holds it, the others in
    their order."""
    left = collections.Counter(taken)
    result = []
    for group in groups:
        kept = []
        for word in group:
            if left[word] > 0:
                left[word] -= 1
            else:
                kept.append(word)
        result.append(tuple(kept))
    return tuple(result)


def words_after_rereads(
    words: tuple[Word, ...], rereads: tuple[Reread, ...]
) -> tuple[Word, ...]:
    """The words of a page as lines.json holds them: `words`, the page's
    words of words.json, less the `layer_words` of each kept record of
    `rereads`, the page's records, each taken out once, in their order;
    then the `ocr_words` of each kept record, in the records' order. A
    record not kept changes nothing (reocr spec, section 4)."""
    kept = tuple(reread for reread in rereads if reread.kept)
    (staying,) = take_out_once(
        (words,), (word for reread in kept for word in reread.layer_words)
    )
    return (*staying, *(word for reread in kept for word in reread.ocr_words))


@dataclass(frozen=True, slots=True, kw_only=True)
class LinesFile:
    """lines.json, written by layout. Every word of words.json is in exactly
    one line or among the `layer_words` of exactly one kept Reread, and
    every word of a line is a word of words.json or among the `ocr_words`
    of a kept Reread. `rereads` lists every region read again, in page
    order."""

    format_version: int = LINES_FORMAT_VERSION
    source_pdf_sha256: str
    pages: tuple[PageLayout, ...]
    rereads: tuple[Reread, ...]


# blocks.json


class BlockKind(StrEnum):
    """What the text of a block is, never how it is printed (architecture
    section 8)."""

    HEADING = "heading"  # a chapter's or a section's, its label in Block.label
    PARAGRAPH = "paragraph"
    QUOTE = "quote"  # a passage quoted from another text, in prose
    VERSE = "verse"  # lines of a poem, separated by line feeds in the text
    CHAPTER_SUMMARY = "chapter_summary"  # a chapter's topics under its heading
    FIGURE = "figure"
    MARGIN_NOTE = "margin_note"
    INDEX_ENTRY = "index_entry"


class Emphasis(StrEnum):
    """The emphasis of a span; only none for now (no italics yet)."""

    NONE = "none"


@dataclass(frozen=True, slots=True)
class Span:
    """A run of a block's text. A span with a `note_ref` is a note reference:
    `note_ref` is the id of the note, and its text the reference as printed
    or as the OCR read it, which may differ from the note's marker."""

    text: str
    emphasis: Emphasis
    note_ref: str | None


@dataclass(frozen=True, slots=True)
class Origin:
    """Where a block, or its part on one page, was printed."""

    page_index: int
    box: Box


@dataclass(frozen=True, slots=True, kw_only=True)
class Block:
    """A block of the book: a heading, paragraph, quote, verse, chapter
    summary, figure, margin note or index entry.

    `id` is `b-p<page index, 4 digits>-<n, 3 digits>`; `level` is a
    heading's, from 1, an index entry's depth, 1 for an entry and 2 for a
    sub-entry, and None otherwise; `label` is a heading's chapter
    label as printed ("CHAPTER III.", "V"), whose title is in the spans,
    and None for a heading without one and for every other kind; `figure`
    is the image path of a figure block; `origin` has one entry per page
    the block was printed on.
    """

    id: str
    kind: BlockKind
    level: int | None
    label: str | None
    spans: tuple[Span, ...]
    figure: str | None
    origin: tuple[Origin, ...]


class NoteKind(StrEnum):
    """Where a note was printed: at the foot of its page, or with the
    others in a section of their own at the end of the book or of a
    chapter."""

    FOOTNOTE = "footnote"
    ENDNOTE = "endnote"


@dataclass(frozen=True, slots=True, kw_only=True)
class Note:
    """A footnote or endnote. `id` is `n-p<page index, 4 digits>-<n, 3
    digits>`, for the n-th note that starts on that page; `marker` is as
    printed at the start of the note, or as the OCR read it, and empty when
    it has none; `blocks` are its paragraphs, quotes or verse, with each
    margin note printed beside one of them as a block just before it;
    `referenced` is false when no reference to it was found."""

    id: str
    kind: NoteKind
    marker: str
    blocks: tuple[Block, ...]
    origin: tuple[Origin, ...]
    referenced: bool


class ChangeReason(StrEnum):
    """Why structure changed words without losing a letter: a hyphen join,
    with the hyphen dropped on evidence, dropped without it (guessed), or
    kept in a compound; a join in a margin note of two parts whose hyphen
    the OCR lost or read as a full stop; or a note marker split off the
    word it was glued to."""

    HYPHEN_JOIN = "hyphen_join"
    NOTE_MARKER = "note_marker"
    HYPHEN_JOIN_GUESSED = "hyphen_join_guessed"  # dropped without evidence
    HYPHEN_KEPT = "hyphen_kept"  # "Anglo-" "Saxon" to "Anglo-Saxon"
    HYPHEN_LOST = "hyphen_lost"  # "move." "ment," to "movement," in a margin note


@dataclass(frozen=True, slots=True, kw_only=True)
class WordChange:
    """Words structure changed without losing a letter: `before` became
    `after`. `page_index` is the page of the first word of `before`, also
    when a hyphen join runs over a page break."""

    page_index: int
    before: tuple[str, ...]
    after: tuple[str, ...]
    reason: ChangeReason


class PageNumberPosition(StrEnum):
    """Where a page number is printed: in the running head or at the foot."""

    HEAD = "head"
    FOOT = "foot"


@dataclass(frozen=True, slots=True)
class PageNumber:
    """The page number printed on a page, as a string ("47", "xiv")."""

    page_index: int
    text: str
    position: PageNumberPosition


@dataclass(frozen=True, slots=True, kw_only=True)
class BlocksFile:
    """blocks.json, written by structure. `removals` holds only what
    structure removed; the removals of words.json are not repeated."""

    format_version: int = BLOCKS_FORMAT_VERSION
    source_pdf_sha256: str
    blocks: tuple[Block, ...]
    notes: tuple[Note, ...]
    removals: tuple[Removal, ...]
    word_changes: tuple[WordChange, ...]
    page_numbers: tuple[PageNumber, ...]


# edits/<author>.jsonl


@dataclass(frozen=True, slots=True, kw_only=True)
class Edit:
    """A change to the text of one block: `old`, found exactly once in the
    block's text, becomes `new`. `block_sha256` is block_sha256 of the block
    as structure wrote it."""

    format_version: int = EDITS_FORMAT_VERSION
    block_id: str
    block_sha256: str
    old: str
    new: str
    author: str
    reason: str


# Not a file: what pdfium.render returns.


@dataclass(frozen=True, slots=True, kw_only=True)
class RenderedPage:
    """A page rendered at `dpi`: 8-bit grayscale pixels, row by row."""

    page_index: int
    dpi: int
    width_px: int
    height_px: int
    pixels: bytes


# Writing and reading. Both follow the dataclasses' field types, so that a
# float field is written as a float whatever number it was given, and
# reading rebuilds the tuples, enums and boxes that JSON turned into lists
# and strings.

_JSON_INDENT = 1  # spec section 3
_STAGE_OF_FILE = frozendict(
    {
        "pages.json": "analyze",
        "words.json": "extract",
        "lines.json": "layout",
        "blocks.json": "structure",
    }
)


@functools.cache
def _fields(cls: type) -> tuple[tuple[str, object], ...]:
    # A dataclass's annotations are its fields, in their order.
    return tuple(typing.get_type_hints(cls).items())


def _optional_type(annotation: object) -> object | None:
    """The X of an `X | None` annotation; None for any other annotation."""
    if not isinstance(annotation, types.UnionType):
        return None
    others = tuple(
        arg for arg in typing.get_args(annotation) if arg is not types.NoneType
    )
    return others[0] if len(others) == 1 else None


def _tuple_item_type(annotation: object) -> object | None:
    """The X of a `tuple[X, ...]` annotation; None for any other annotation."""
    if typing.get_origin(annotation) is not tuple:
        return None
    return typing.get_args(annotation)[0]


def _json_float(number: float) -> float:
    """The float written for `number`: an int as the equal float, and -0.0
    as 0.0 (adding 0.0 does it), so that equal numbers give equal bytes."""
    return float(number) + 0.0


def _mapping_types(annotation: object) -> tuple[object, object] | None:
    """The K and V of a `frozendict[K, V]` annotation; None for any other."""
    if typing.get_origin(annotation) is not frozendict:
        return None
    key_type, value_type = typing.get_args(annotation)
    return key_type, value_type


def _encode(annotation: object, value: object) -> object:
    """The JSON value of `value`, whose type is `annotation`."""
    if value is None:
        return None
    if annotation is Box and isinstance(value, Box):
        return [
            _json_float(coordinate)
            for coordinate in (value.x0, value.top, value.x1, value.bottom)
        ]
    if annotation is float and isinstance(value, int | float):
        return _json_float(value)
    if isinstance(value, StrEnum):
        return value.value
    if (item_type := _tuple_item_type(annotation)) is not None and isinstance(
        value, tuple
    ):
        return [_encode(item_type, item) for item in value]
    if (optional := _optional_type(annotation)) is not None:
        return _encode(optional, value)
    if (mapping := _mapping_types(annotation)) is not None and isinstance(
        value, frozendict
    ):
        # Keys in their order, so that equal mappings give equal bytes; an
        # int key is written as its string (architecture section 8).
        return {str(key): _encode(mapping[1], value[key]) for key in sorted(value)}
    if isinstance(annotation, type) and dataclasses.is_dataclass(annotation):
        return {
            name: _encode(field_type, getattr(value, name))
            for name, field_type in _fields(annotation)
        }
    return value


class _FieldError(Exception):
    """A JSON value that does not fit its field, at `json_path` (such as
    `pages[3].words[12].box`; empty for the file as a whole). The reader
    adds the file and raises it again as InputFileError or EditError."""

    def __init__(self, problem: str, json_path: str = "") -> None:
        super().__init__(f"{json_path}: {problem}" if json_path else problem)


# How much of a wrong value an error message quotes; guessed, not measured.
_FOUND_CHARACTERS = 40


def _found(value: object) -> str:
    # repr for a _KeyGivenTwice inside a value of the wrong type.
    text = json.dumps(value, ensure_ascii=False, default=repr)
    if len(text) > _FOUND_CHARACTERS:
        return text[:_FOUND_CHARACTERS] + "..."
    return text


def _join(json_path: str, name: str) -> str:
    return f"{json_path}.{name}" if json_path else name


def _number(value: object, json_path: str) -> float:
    _check_keys_once(value, json_path)
    # JSON true and false are bools, which Python counts as ints; they are
    # not numbers here. An int is read as the equal float. Python's json
    # reads NaN and Infinity, which are not JSON and no writer makes.
    if isinstance(value, bool) or not isinstance(value, int | float):
        problem = f"expected a number, found {_found(value)}"
        raise _FieldError(problem, json_path)
    if not math.isfinite(value):
        problem = f"expected a finite number, found {_found(value)}"
        raise _FieldError(problem, json_path)
    return float(value)


_BOX_COORDINATES = 4


def _decode_box(value: object, json_path: str) -> Box:
    # A box with x0 >= x1 or top >= bottom is read as it is: boxes in these
    # files come from the text layer or OCR, and a stage, not the reader,
    # decides what such a word is. config.py refuses one, since the owner
    # draws those boxes by hand.
    if not isinstance(value, list) or len(value) != _BOX_COORDINATES:
        problem = f"expected a box of four numbers, found {_found(value)}"
        raise _FieldError(problem, json_path)
    x0, top, x1, bottom = (
        _number(coordinate, f"{json_path}[{position}]")
        for position, coordinate in enumerate(value)
    )
    return Box(x0, top, x1, bottom)


def _scalar_description(annotation: object) -> str | None:
    """What a JSON value of an int, bool or str field must be; None for
    other fields. Such a value is read as it is, checked by its exact type,
    so that true is not an int."""
    if annotation is int:
        return "an integer"
    if annotation is bool:
        return "true or false"
    if annotation is str:
        return "a string"
    return None


@dataclass(frozen=True, slots=True)
class _KeyGivenTwice:
    """What the JSON parser makes, in place of the object, of an object that
    has `key` twice; the decoder raises it with the object's path."""

    key: str


def _object_pairs(
    pairs: list[tuple[str, object]],
) -> dict[str, object] | _KeyGivenTwice:
    """The object_pairs_hook of json.loads: the object, or the first key it
    has twice. Python's json would keep the last value without a word."""
    content: dict[str, object] = {}
    for key, value in pairs:
        if key in content:
            return _KeyGivenTwice(key)
        content[key] = value
    return content


def _check_keys_once(value: object, json_path: str) -> None:
    if isinstance(value, _KeyGivenTwice):
        problem = "given twice"
        raise _FieldError(problem, _join(json_path, value.key))


def _decode(annotation: object, value: object, json_path: str) -> object:
    """The value of type `annotation` that `_encode` wrote as `value`.

    Raises _FieldError at the first value that does not fit."""
    _check_keys_once(value, json_path)
    if (optional := _optional_type(annotation)) is not None:
        return None if value is None else _decode(optional, value, json_path)
    if annotation is Box:
        return _decode_box(value, json_path)
    if annotation is float:
        return _number(value, json_path)
    if (description := _scalar_description(annotation)) is not None:
        if type(value) is not annotation:
            problem = f"expected {description}, found {_found(value)}"
            raise _FieldError(problem, json_path)
        if isinstance(value, str) and _SURROGATE.search(value):
            problem = "holds a surrogate (\\ud800 to \\udfff), which is not text"
            raise _FieldError(problem, json_path)
        return value
    if isinstance(annotation, type) and issubclass(annotation, StrEnum):
        return _decode_enum(annotation, value, json_path)
    if (item_type := _tuple_item_type(annotation)) is not None:
        if not isinstance(value, list):
            problem = f"expected a list, found {_found(value)}"
            raise _FieldError(problem, json_path)
        return tuple(
            _decode(item_type, item, f"{json_path}[{position}]")
            for position, item in enumerate(value)
        )
    if (mapping := _mapping_types(annotation)) is not None:
        return _decode_mapping(mapping, value, json_path)
    if isinstance(annotation, type) and dataclasses.is_dataclass(annotation):
        return _decode_dataclass(annotation, value, json_path)
    # A field type of this module that the reader does not know: a defect
    # of model.py, not of the file.
    message = f"model.py cannot read a field of type {annotation!r}"
    raise TypeError(message)


def _decode_mapping(
    mapping: tuple[object, object], value: object, json_path: str
) -> frozendict[object, object]:
    key_type, value_type = mapping
    if not isinstance(value, dict):
        problem = f"expected an object, found {_found(value)}"
        raise _FieldError(problem, json_path)
    return frozendict(
        {
            _decode_key(key_type, key, json_path): _decode(
                value_type, item, _join(json_path, key)
            )
            for key, item in value.items()
        }
    )


def _decode_key(key_type: object, key: str, json_path: str) -> object:
    """A mapping's key: an int written as its string, or a string."""
    if key_type is str:
        return key
    if key_type is int:
        # Only the string str() writes, so that reading and writing again
        # gives the same bytes: "01" and "1.0" are not keys.
        if not _INT_KEY.fullmatch(key):
            problem = f"key {key!r} is not an integer"
            raise _FieldError(problem, json_path)
        return int(key)
    message = f"model.py cannot read a mapping key of type {key_type!r}"
    raise TypeError(message)


_INT_KEY = re.compile("-?(0|[1-9][0-9]*)")


def _decode_enum[E: StrEnum](enum: type[E], value: object, json_path: str) -> E:
    members = tuple(member.value for member in enum)
    if not isinstance(value, str) or value not in members:
        problem = f"expected one of {', '.join(members)}, found {_found(value)}"
        raise _FieldError(problem, json_path)
    return enum(value)


def _decode_dataclass[T](cls: type[T], value: object, json_path: str) -> T:
    if not isinstance(value, dict):
        problem = f"expected an object, found {_found(value)}"
        raise _FieldError(problem, json_path)
    fields = _fields(cls)
    names = tuple(name for name, _ in fields)
    for name in names:
        if name not in value:
            problem = "missing"
            raise _FieldError(problem, _join(json_path, name))
    for key in value:
        if key not in names:
            problem = f"not a field of {cls.__name__}"
            raise _FieldError(problem, _join(json_path, str(key)))
    return cls(
        **{
            name: _decode(field_type, value[name], _join(json_path, name))
            for name, field_type in fields
        }
    )


def _decode_file[T](
    cls: type[T], content: object, current_version: int, rerun: str
) -> T:
    """The value of `cls` in the parsed JSON `content` of a file of format
    version `current_version`. Raises _FieldError at the first problem; a
    format version error ends with `rerun`, what to do to remake the file
    ("; run `galley2epub structure` again"), empty when nothing does."""
    _check_keys_once(content, "")
    if not isinstance(content, dict):
        problem = f"is not a JSON object but {_found(content)}"
        raise _FieldError(problem)
    if "format_version" not in content:
        problem = (
            f"has no format_version; this galley reads format version {current_version}"
        )
        raise _FieldError(problem)
    version = content["format_version"]
    if type(version) is not int:
        problem = (
            f"format_version is {_found(version)}, not an integer; "
            f"this galley reads format version {current_version}"
        )
        raise _FieldError(problem)
    if version != current_version:
        problem = (
            f"is format version {version}; "
            f"this galley reads format version {current_version}{rerun}"
        )
        raise _FieldError(problem)
    return _decode_dataclass(cls, content, "")


# A surrogate code point (U+D800 to U+DFFF) cannot be encoded as UTF-8; a
# lone one gets into a str from a bad text layer or a bad decoding.
_SURROGATE = re.compile("[\ud800-\udfff]")


def _surrogate_path(content: object, json_path: str) -> str | None:
    """The path of the first string in the JSON `content` that holds a
    surrogate; None when no string does."""
    if isinstance(content, str):
        return json_path if _SURROGATE.search(content) else None
    if isinstance(content, dict):
        children = tuple(
            (_join(json_path, str(key)), value) for key, value in content.items()
        )
    elif isinstance(content, list):
        children = tuple(
            (f"{json_path}[{position}]", item) for position, item in enumerate(content)
        )
    else:
        return None
    for child_path, child in children:
        if (found := _surrogate_path(child, child_path)) is not None:
            return found
    return None


def _utf8(text: str, content: object, json_path: str) -> bytes:
    """`text`, the JSON of `content`, as UTF-8. Raises ValueError naming the
    field that holds a surrogate: a defect, or bad input, of the stage that
    made the value."""
    try:
        return text.encode("utf-8")
    except UnicodeEncodeError as err:
        message = (
            f"{_surrogate_path(content, json_path)}: holds a surrogate, "
            "which UTF-8 cannot encode"
        )
        raise ValueError(message) from err


def _replace_file(path: Path, data: bytes) -> None:
    """Writes `data` to a temporary file beside `path`, then moves it over
    `path`, so that a failed write leaves the old file as it was. The
    temporary name is unique to the process and the thread."""
    temporary = path.with_name(
        f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp"
    )
    try:
        temporary.write_bytes(data)
    except OSError:
        temporary.unlink(missing_ok=True)
        raise
    temporary.replace(path)


def _write_json(path: Path, value: object) -> None:
    content = _encode(type(value), value)
    text = (
        json.dumps(content, ensure_ascii=False, allow_nan=False, indent=_JSON_INDENT)
        + "\n"
    )
    _replace_file(path, _utf8(text, content, ""))


def _read_json[T](path: Path, cls: type[T], current_version: int, stage: str) -> T:
    """The value of `cls` in the JSON file at `path`, written by `stage`,
    every field checked. Raises InputFileError at the first problem."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as err:
        message = f"{path} does not exist; run `galley2epub {stage}` to write it"
        raise InputFileError(message) from err
    except UnicodeDecodeError as err:
        message = f"{path} is not UTF-8 text: {err}"
        raise InputFileError(message) from err
    try:
        content = json.loads(text, object_pairs_hook=_object_pairs)
    except json.JSONDecodeError as err:
        message = (
            f"{path} is not valid JSON: {err.msg} at line {err.lineno}, "
            f"column {err.colno}"
        )
        raise InputFileError(message) from err
    try:
        return _decode_file(
            cls, content, current_version, f"; run `galley2epub {stage}` again"
        )
    except _FieldError as err:
        message = f"{path}: {err}"
        raise InputFileError(message) from err


def write_pages(path: Path, pages: PagesFile) -> None:
    """Writes pages.json: UTF-8 JSON, keys in field order, indent 1."""
    _write_json(path, pages)


def read_pages(path: Path) -> PagesFile:
    """Reads pages.json as write_pages wrote it."""
    return _read_json(path, PagesFile, PAGES_FORMAT_VERSION, "analyze")


def write_words(path: Path, words: WordsFile) -> None:
    """Writes words.json: UTF-8 JSON, keys in field order, indent 1."""
    _write_json(path, words)


def read_words(path: Path) -> WordsFile:
    """Reads words.json as write_words wrote it."""
    return _read_json(path, WordsFile, WORDS_FORMAT_VERSION, "extract")


def write_lines(path: Path, lines: LinesFile) -> None:
    """Writes lines.json: UTF-8 JSON, keys in field order, indent 1."""
    _write_json(path, lines)


def read_lines(path: Path) -> LinesFile:
    """Reads lines.json as write_lines wrote it."""
    return _read_json(path, LinesFile, LINES_FORMAT_VERSION, "layout")


def write_blocks(path: Path, blocks: BlocksFile) -> None:
    """Writes blocks.json: UTF-8 JSON, keys in field order, indent 1."""
    _write_json(path, blocks)


def has_index_depth(block: Block) -> bool:
    """Whether `block`, an index entry, has its depth, a level from 1
    (architecture section 8)."""
    return block.level is not None and block.level >= 1


def read_blocks(path: Path) -> BlocksFile:
    """Reads blocks.json as write_blocks wrote it. Raises InputFileError,
    naming the file and the block, also when a block that is not a heading
    has a label, an index entry has no depth from 1, or a block that is
    neither a heading nor an index entry has a level."""
    blocks = _read_json(path, BlocksFile, BLOCKS_FORMAT_VERSION, "structure")
    for block in (
        *blocks.blocks,
        *(block for note in blocks.notes for block in note.blocks),
    ):
        if block.label is not None and block.kind is not BlockKind.HEADING:
            message = (
                f"{path}: block {block.id} is a {block.kind.value} and has the "
                f"label {block.label!r}; only a heading has a label"
            )
            raise InputFileError(message)
        if block.kind is BlockKind.INDEX_ENTRY and not has_index_depth(block):
            message = (
                f"{path}: block {block.id} is an index entry with the depth "
                f"{block.level!r}, not one from 1 (architecture section 8); a "
                "blocks.json written before index entries had a depth needs "
                "`galley2epub structure` run again"
            )
            raise InputFileError(message)
        if block.level is not None and block.kind not in _KINDS_WITH_LEVEL:
            message = (
                f"{path}: block {block.id} is a {block.kind.value} and has the "
                f"level {block.level!r}; only a heading and an index entry have one"
            )
            raise InputFileError(message)
    return blocks


# Architecture section 8: a heading's level, and an index entry's depth.
_KINDS_WITH_LEVEL = frozenset({BlockKind.HEADING, BlockKind.INDEX_ENTRY})


# The hashes.


def pdf_sha256(pdf: Path) -> str:
    """The SHA-256 of the PDF file's bytes, 64 lowercase hex digits."""
    return hashlib.sha256(pdf.read_bytes()).hexdigest()


def check_source_pdf(
    path: Path, file_pdf_sha256: str, expected_pdf_sha256: str
) -> None:
    """Raises InputFileError when the file at `path`, whose
    `source_pdf_sha256` is `file_pdf_sha256`, was made from another PDF
    than the one whose hash is `expected_pdf_sha256`. The message names the stage
    to run again."""
    if file_pdf_sha256 == expected_pdf_sha256:
        return
    stage = _STAGE_OF_FILE.get(path.name)
    rerun = (
        f"run `galley2epub {stage}` again"
        if stage is not None
        else "run the stage that writes it again"
    )
    message = (
        f"{path} was made from another PDF (SHA-256 {file_pdf_sha256}, "
        f"expected {expected_pdf_sha256}); {rerun}"
    )
    raise InputFileError(message)


def read_checked_pages(pages_json: Path, pdf: Path) -> PagesFile:
    """Reads pages.json and checks that it was made from `pdf`; raises
    InputFileError naming analyze when it was not."""
    pages = read_pages(pages_json)
    check_source_pdf(pages_json, pages.source_pdf_sha256, pdf_sha256(pdf))
    return pages


def read_checked_input[T: WordsFile | LinesFile | BlocksFile](
    pages_json: Path, pdf: Path, input_path: Path, read_input: Callable[[Path], T]
) -> tuple[PagesFile, T]:
    """Reads pages.json with read_checked_pages, then the stage's input file
    at `input_path` with `read_input`, and checks that the input was made
    from the PDF pages.json was made from; raises InputFileError naming the
    stage that writes the stale file. Returns both files."""
    pages = read_checked_pages(pages_json, pdf)
    stage_input = read_input(input_path)
    check_source_pdf(input_path, stage_input.source_pdf_sha256, pages.source_pdf_sha256)
    return pages, stage_input


def block_text(block: Block) -> str:
    """The text of a block: its spans' text concatenated, with nothing between."""
    return "".join(span.text for span in block.spans)


def note_places(
    block_first_pages: Sequence[int | None], note_first_pages: Sequence[int]
) -> tuple[int, ...]:
    """Where each note is written among the blocks (structure spec, section
    6, "Order"): for each note, given by the page index of its first
    origin, how many of the blocks, given in their order by the page index
    of their first origin, are written before it: all up to the last block
    whose first page is the note's or an earlier one; none when there is no
    such block. A block without an origin (None) is passed over. structure
    numbers the blocks by it and markdown writes the notes by it."""
    by_first_page = sorted(
        (page_index, position)
        for position, page_index in enumerate(block_first_pages, start=1)
        if page_index is not None
    )
    first_pages = tuple(page_index for page_index, _ in by_first_page)
    last_positions = tuple(
        itertools.accumulate((position for _, position in by_first_page), max)
    )

    def place(page_index: int) -> int:
        on_or_before = bisect.bisect_right(first_pages, page_index)
        return last_positions[on_or_before - 1] if on_or_before else 0

    return tuple(place(page_index) for page_index in note_first_pages)


_BLOCK_SHA256_DIGITS = 12  # architecture section 8, the checksum an Edit carries


def block_sha256(block: Block) -> str:
    """The first 12 hex digits of the SHA-256 of the block's text in UTF-8,
    the checksum an Edit carries."""
    return hashlib.sha256(block_text(block).encode("utf-8")).hexdigest()[
        :_BLOCK_SHA256_DIGITS
    ]


def write_edits(path: Path, edits: tuple[Edit, ...]) -> None:
    """Writes an edits file: JSON Lines, one edit per line, UTF-8, with
    `format_version` first on every line."""
    data = b"".join(_edit_line(edit, position) for position, edit in enumerate(edits))
    _replace_file(path, data)


def _edit_line(edit: Edit, position: int) -> bytes:
    content = _encode(Edit, edit)
    text = json.dumps(content, ensure_ascii=False, allow_nan=False) + "\n"
    return _utf8(text, content, f"edits[{position}]")


_BYTE_ORDER_MARK = "\ufeff"


def read_edits(path: Path) -> tuple[Edit, ...]:
    """The edits of an edits file, in the order of its lines.

    Raises EditError, naming the file, for a file that is not UTF-8 or
    starts with a byte-order mark; and naming the line too, for a blank
    line, a line that is not JSON, a format_version other than 1, or an
    object with a missing, unknown or mistyped field. A missing file is the
    caller's concern: architecture section 10 counts it as no edits."""
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as err:
        message = f"{path} is not UTF-8 text: {err}"
        raise EditError(message) from err
    if text.startswith(_BYTE_ORDER_MARK):
        # Edits may be written by hand, and some editors add the mark.
        message = (
            f"{path} starts with a byte-order mark; "
            "save it as UTF-8 without a byte-order mark"
        )
        raise EditError(message)
    # Split on newlines only: str.splitlines also splits on characters such
    # as U+2028, which json.dumps leaves unescaped inside a string.
    lines = text.split("\n")
    if lines[-1] == "":
        lines = lines[:-1]
    return tuple(
        _edit_from_line(path, line_number, line)
        for line_number, line in enumerate(lines, start=1)
    )


def _edit_from_line(path: Path, line_number: int, line: str) -> Edit:
    where = f"{path}, line {line_number}"
    if line.strip() == "":
        message = f"{where}: blank line"
        raise EditError(message)
    try:
        content = json.loads(line, object_pairs_hook=_object_pairs)
    except json.JSONDecodeError as err:
        message = f"{where}: not valid JSON: {err.msg} at column {err.colno}"
        raise EditError(message) from err
    try:
        return _decode_file(Edit, content, EDITS_FORMAT_VERSION, "")
    except _FieldError as err:
        message = f"{where}: {err}"
        raise EditError(message) from err
