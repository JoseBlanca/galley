"""In-page figures (docs/specs/figures.md, section 5): a figure's region
kept out of the survey and the body stream, its caption found by its label
row, and its figure block placed after the paragraph printed before it.

layout gives each in-page figure that holds words a region whose box is
the figure's box. structure takes those regions out of the page before it
looks at it, and removes their words as `figure_text`. A caption is found
on rows of the page's other lines: a row that opens
a run of words with a caption label and lies next to a figure, below,
above or beside it, and the rows that follow it on the caption's side.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import assert_never

from galley.body_measures import rows_of
from galley.model import (
    Box,
    Figure,
    FigureKind,
    Line,
    PageLayout,
    Region,
    Removal,
    RemovalReason,
    box_holds_middle,
)
from galley.structure._foot import LinePlace, line_at
from galley.structure._lines import Piece, PlacedLine
from galley.structure._measures import (
    Edges,
    box_of,
    middle,
    words_box,
    words_removal,
)
from galley.structure._regions import HeadLine, head_line

# Figures spec section 1: the words that name a caption's label, in lower
# case, and a numeral's characters: digits and the letters of a roman
# numeral the OCR also reads for 1 ("li." for 11, "2i." for 21).
_LABEL_NAMES = frozenset({"figure", "fig.", "fig", "plate", "map"})
_NUMERAL_CHARACTERS = frozenset("0123456789ivxlcIVXLC")
_NUMERAL_ENDINGS = (".", ",")
_NUMERAL_MAX_CHARACTERS = 6
# Figures spec section 1: Turney's numbered captions ("13. The", "14 (a)")
# open with a numeral of at most 3 characters, its "." counted.
_SHORT_NUMERAL_MAX_CHARACTERS = 3
# A word in brackets has a letter or more between them ("(a)", "(top)").
_BRACKETED_MIN_CHARACTERS = 3
# A numbered label is a numeral and the word after it.
_NUMBERED_LABEL_WORDS = 2

# Figures spec section 5, "structure: the caption", rule 1: a label row
# below a figure has its top from 6 pt above the figure's bottom to 24 pt
# below it, one above its bottom from 24 pt above the figure's top to 6 pt
# below it, and its label's first word's middle between the figure's
# sides moved 6 pt outwards (measured: Haynes' captions 5.4 to 8.1 pt
# below, Turney's 5.3 to 14.7, Kadesh's maps 3.5 pt above the bottom to
# 11.7 below; with 12 pt at the sides, "at" and "of" of the text beside
# Kadesh's maps 33 and 41 joined their captions).
_NEAR_INSIDE_PT = 6.0
_NEAR_OUTSIDE_PT = 24.0
_SIDES_SLACK_PT = 6.0
# Rule 2: below or above, the label row's words that follow the caption's
# at less than 13 pt are the caption's too (measured: a caption's words are
# at most 10.0 pt apart in Kadesh, Haynes and Turney, Kadesh 45's spaced
# capitals; the text set beside Kadesh's maps starts 16.9 to 80 pt after
# the caption's last word).
_FOLLOWING_WORD_MAX_PT = 13.0
# Rule 1, beside: the label's first word 0 to 30 pt right of the figure,
# or the row's last word 0 to 30 pt left of it (measured: Haynes 10.4 to
# 17.3 pt, Turney 6.5 to 20.0).
_BESIDE_MAX_PT = 30.0
# Rule 3: a caption's next row has its top at most 20 pt below the top of
# the row before (measured: 10.9 to 14.7 pt within a caption, 23.6 pt and
# more after a Haynes caption), and lies between the figure's sides moved
# 12 pt outwards, or within 3 pt of the label row's left side (Haynes'
# captions are as wide as the column, wider than some pictures).
_NEXT_ROW_MAX_PT = 20.0
_NEXT_ROW_SIDES_SLACK_PT = 12.0
_SAME_LEFT_PT = 3.0


def _is_numeral(text: str) -> bool:
    """Whether `text` is a numeral (figures spec section 1): 1 to 6 digits
    or letters i, v, x, l, c in either case, with or without a "." or ","
    after them."""
    bare = text[:-1] if text.endswith(_NUMERAL_ENDINGS) else text
    return 0 < len(bare) <= _NUMERAL_MAX_CHARACTERS and all(
        character in _NUMERAL_CHARACTERS for character in bare
    )


def _is_capitalised(text: str) -> bool:
    """Whether `text` starts with a capital letter and then a small one."""
    return len(text) > 1 and text[0].isupper() and text[1].islower()


def _is_bracketed(text: str) -> bool:
    return (
        len(text) >= _BRACKETED_MIN_CHARACTERS
        and text.startswith("(")
        and text.endswith(")")
    )


def is_caption_label(words: tuple[str, ...]) -> bool:
    """Whether the run of words `words`, left to right, opens with a
    caption label (figures spec section 1): "figure", "fig.", "fig",
    "plate" or "map", in any case, as its first or second word, followed by
    a numeral; or a numeral of at most 3 characters ending in "." followed
    by a word of a capital letter and then a small one, or a numeral of at
    most 3 characters followed by a word in brackets."""
    named = any(
        len(words) > position + 1
        and words[position].lower() in _LABEL_NAMES
        and _is_numeral(words[position + 1])
        for position in (0, 1)
    )
    if named:
        return True
    if (
        len(words) < _NUMBERED_LABEL_WORDS
        or len(words[0]) > _SHORT_NUMERAL_MAX_CHARACTERS
        or not _is_numeral(words[0])
    ):
        return False
    return (words[0].endswith(".") and _is_capitalised(words[1])) or _is_bracketed(
        words[1]
    )


# The page's figure regions.


@dataclass(frozen=True, slots=True)
class SplitPage:
    """A page with its in-page figures' regions taken apart (figures spec
    section 5, "structure: removing the figure text"): `text` is the page
    without them, its other regions in their order; `figures` are its
    in-page figures in the order of pages.json, and `regions` the region of
    each, None for a figure that holds no word."""

    text: PageLayout
    figures: tuple[Figure, ...]
    regions: tuple[Region | None, ...]


def split_figure_regions(page: PageLayout) -> SplitPage:
    """`page` split into its text and its in-page figures' regions: a region
    whose box is one of the page's in-page figure boxes is that figure's
    region (the first such region, for each figure)."""
    figures = tuple(
        figure for figure in page.figures if figure.kind is FigureKind.IN_PAGE
    )
    boxes = frozenset(figure.box for figure in figures)
    return SplitPage(
        text=PageLayout(
            page.index,
            tuple(region for region in page.regions if region.box not in boxes),
            page.figures,
        ),
        figures=figures,
        regions=tuple(
            next((region for region in page.regions if region.box == figure.box), None)
            for figure in figures
        ),
    )


def text_page(page: PageLayout) -> PageLayout:
    """`page` without its in-page figures' regions, which take no part in
    structure's survey (figures spec section 5)."""
    return split_figure_regions(page).text


# The captions.


class _Side(StrEnum):
    """Where a caption lies next to its figure (rule 1)."""

    BELOW = "below"
    ABOVE = "above"
    RIGHT = "right"
    LEFT = "left"


_BESIDE = frozenset({_Side.RIGHT, _Side.LEFT})


type WordPlace = tuple[int, int, int]
"""A word of a page, as (region number, line number, word number)."""


@dataclass(frozen=True, slots=True)
class _RowWord:
    """A word of a row: the place of its line, the line, and its number in
    the line."""

    line_place: LinePlace
    line: Line
    word_number: int

    @property
    def place(self) -> WordPlace:
        return (*self.line_place, self.word_number)

    @property
    def box(self) -> Box:
        return self.line.words[self.word_number].box

    @property
    def text(self) -> str:
        return self.line.words[self.word_number].text


@dataclass(frozen=True, slots=True)
class _Row:
    """A row of a page's lines (structure spec section 18, rule 3), each
    line with its place, and the row's words left to right."""

    lines: tuple[tuple[LinePlace, Line], ...]
    box: Box
    words: tuple[_RowWord, ...]


def _row(lines: tuple[tuple[LinePlace, Line], ...]) -> _Row:
    words = tuple(
        sorted(
            (
                _RowWord(place, line, number)
                for place, line in lines
                for number in range(len(line.words))
            ),
            key=lambda word: word.box.x0,
        )
    )
    return _Row(lines, box_of(tuple(line.box for _, line in lines)), words)


@dataclass(frozen=True, slots=True)
class _LabelRow:
    row: int
    figure: int
    side: _Side


def _within_sides(across: float, box: Box, slack: float) -> bool:
    return box.x0 - slack <= across <= box.x1 + slack


def _side(row: _Row, label: _RowWord, box: Box) -> _Side | None:
    """Where the row whose label opens at `label` lies next to the figure
    of `box` (rule 1), None when it is not next to it."""
    under_figure = _within_sides(middle(label.box), box, _SIDES_SLACK_PT)
    if (
        under_figure
        and box.bottom - _NEAR_INSIDE_PT <= row.box.top <= box.bottom + _NEAR_OUTSIDE_PT
    ):
        return _Side.BELOW
    if (
        under_figure
        and box.top - _NEAR_OUTSIDE_PT <= row.box.bottom <= box.top + _NEAR_INSIDE_PT
    ):
        return _Side.ABOVE
    if not box.top <= row.box.top <= box.bottom:
        return None
    if 0 <= label.box.x0 - box.x1 <= _BESIDE_MAX_PT:
        return _Side.RIGHT
    if (
        all(word.box.x1 <= box.x0 for word in row.words)
        and 0 <= box.x0 - row.words[-1].box.x1 <= _BESIDE_MAX_PT
    ):
        return _Side.LEFT
    return None


def _next_to(row: _Row, box: Box) -> _Side | None:
    """Where `row` lies next to the figure of `box` as a label row: the side
    of the first run of its words that opens with a caption label and lies
    next to the figure, None when no run does."""
    texts = tuple(word.text for word in row.words)
    return next(
        (
            side
            for start, word in enumerate(row.words)
            if is_caption_label(texts[start:])
            and (side := _side(row, word, box)) is not None
        ),
        None,
    )


def _gap(box: Box, other: Box) -> float:
    """The distance between two boxes, 0 when they overlap."""
    across = max(0.0, other.x0 - box.x1, box.x0 - other.x1)
    down = max(0.0, other.top - box.bottom, box.top - other.bottom)
    return math.hypot(across, down)


def _label_rows(rows: Sequence[_Row], boxes: Sequence[Box]) -> tuple[_LabelRow, ...]:
    """The label rows of the page, each with the figure it goes to: of two
    figures it is next to, the one whose box is nearer to the row's."""
    found = []
    for number, row in enumerate(rows):
        sides = tuple(
            (figure, side)
            for figure, box in enumerate(boxes)
            if (side := _next_to(row, box)) is not None
        )
        if sides:
            figure, side = min(sides, key=lambda pair: _gap(row.box, boxes[pair[0]]))
            found.append(_LabelRow(number, figure, side))
    return tuple(found)


def _with_following_words(
    words: tuple[_RowWord, ...], inside: tuple[bool, ...]
) -> tuple[_RowWord, ...]:
    """The `words` of a row, left to right, that are `inside` the figure's
    sides, with the words that follow them on either side, each less than
    `_FOLLOWING_WORD_MAX_PT` from the word before it (rule 2)."""
    taken = list(inside)
    for number in range(1, len(words)):
        if taken[number - 1] and _follows(words[number - 1], words[number]):
            taken[number] = True
    for number in range(len(words) - 2, -1, -1):
        if taken[number + 1] and _follows(words[number], words[number + 1]):
            taken[number] = True
    return tuple(word for word, kept in zip(words, taken, strict=True) if kept)


def _follows(left: _RowWord, right: _RowWord) -> bool:
    """Whether `right` follows `left` on a caption's line: less than
    `_FOLLOWING_WORD_MAX_PT` from it."""
    return right.box.x0 - left.box.x1 < _FOLLOWING_WORD_MAX_PT


def _label_words(row: _Row, box: Box, side: _Side) -> tuple[_RowWord, ...]:
    """The words of a label row that are the caption's (rule 2): below or
    above, those between the figure's sides moved 6 pt outwards and the
    words that follow them; on the right or left, those on that side."""
    match side:
        case _Side.BELOW | _Side.ABOVE:
            return _with_following_words(
                row.words,
                tuple(
                    _within_sides(middle(word.box), box, _SIDES_SLACK_PT)
                    for word in row.words
                ),
            )
        case _Side.RIGHT:
            return tuple(word for word in row.words if middle(word.box) > box.x1)
        case _Side.LEFT:
            return tuple(word for word in row.words if middle(word.box) < box.x0)
        case _:
            assert_never(side)


def _next_row_words(
    row: _Row, box: Box, side: _Side, label_left: float
) -> tuple[_RowWord, ...]:
    """The words of `row` that a caption on `side` of the figure of `box`
    takes as its next row (rule 3), none when the row is not on that side:
    below or above, the whole row when it lies between the figure's sides
    moved 12 pt outwards or its left side is within 3 pt of `label_left`,
    the left side of the label row's words; on the right or left, the
    row's words on that side, as rule 2 takes them."""
    match side:
        case _Side.BELOW | _Side.ABOVE:
            on_side = (
                row.box.x0 >= box.x0 - _NEXT_ROW_SIDES_SLACK_PT
                and row.box.x1 <= box.x1 + _NEXT_ROW_SIDES_SLACK_PT
            ) or abs(row.box.x0 - label_left) <= _SAME_LEFT_PT
            return row.words if on_side else ()
        case _Side.RIGHT | _Side.LEFT:
            return _label_words(row, box, side)
        case _:
            assert_never(side)


def _caption_line(words: Sequence[_RowWord]) -> Line:
    """The line of one line's caption words, all of it when it gives them
    all."""
    line = words[0].line
    if len(words) == len(line.words):
        return line
    kept = tuple(word.line.words[word.word_number] for word in words)
    return Line(words_box(kept), kept)


def _row_lines(words: Sequence[_RowWord]) -> tuple[Line, ...]:
    """The caption lines of a row's caption `words`, one per line of the
    row that gives any, from the left."""
    by_line: dict[LinePlace, list[_RowWord]] = {}
    for word in words:
        by_line.setdefault(word.line_place, []).append(word)
    return tuple(
        _caption_line(sorted(line_words, key=lambda word: word.word_number))
        for line_words in sorted(
            by_line.values(), key=lambda line_words: line_words[0].line.box.x0
        )
    )


@dataclass(frozen=True, slots=True)
class Captions:
    """The captions of a page's in-page figures (figures spec section 5,
    "structure: the caption"): for each figure in order, its caption lines
    from the top down and each row from the left, none when it has no
    caption; and the places of the words they took."""

    lines: tuple[tuple[Line, ...], ...]
    taken: frozenset[WordPlace]


def figure_captions(
    lines: Sequence[tuple[LinePlace, Line]], boxes: Sequence[Box]
) -> Captions:
    """The captions of the figures of `boxes` among a page's `lines`, each
    with its place, which are the lines left once its running head and
    page numbers are removed, outside the figures' regions (figures spec
    section 5, rules 1 to 3): a label row next to a figure gives the
    caption the words of rule 2, and each next row from the top down gives
    it its words on the caption's side (`_next_row_words`), while its top is
    at most `_NEXT_ROW_MAX_PT` below the top of the caption's row before and
    they open with no caption label; beside the figure, a row with no word
    on the caption's side is passed over. Several label rows of one figure
    give one caption in the order of their tops."""
    rows = tuple(_row(row) for row in rows_of(lines, lambda pair: pair[1].box))
    label_rows = _label_rows(rows, boxes)
    label_numbers = frozenset(label.row for label in label_rows)
    used: set[int] = set(label_numbers)
    caption_rows: list[list[tuple[int, tuple[_RowWord, ...]]]] = [[] for _ in boxes]
    for label in label_rows:
        box = boxes[label.figure]
        words = _label_words(rows[label.row], box, label.side)
        if not words:
            continue
        caption_rows[label.figure].append((label.row, words))
        label_left = min(word.box.x0 for word in words)
        before_top = rows[label.row].box.top
        for number in range(label.row + 1, len(rows)):
            row = rows[number]
            if number in used or row.box.top - before_top > _NEXT_ROW_MAX_PT:
                break
            words = _next_row_words(row, box, label.side, label_left)
            if not words and label.side in _BESIDE:
                # A row with no word on a beside caption's side is passed
                # over (rule 3).
                continue
            if not words or is_caption_label(tuple(word.text for word in words)):
                break
            used.add(number)
            caption_rows[label.figure].append((number, words))
            before_top = row.box.top
    return Captions(
        lines=tuple(
            tuple(
                line
                for _, words in sorted(rows_of_figure, key=lambda row: row[0])
                for line in _row_lines(words)
            )
            for rows_of_figure in caption_rows
        ),
        taken=frozenset(
            word.place
            for rows_of_figure in caption_rows
            for _, words in rows_of_figure
            for word in words
        ),
    )


def in_any_figure(line: Line, boxes: Sequence[Box]) -> bool:
    """Whether the middle of each word of `line` lies inside one of the
    figure `boxes`, edges included (figures spec section 5: a head line
    printed inside a picture)."""
    return bool(line.words) and all(
        any(box_holds_middle(box, word.box) for box in boxes) for word in line.words
    )


# The page's figures.


@dataclass(frozen=True, slots=True)
class PageFigure:
    """A figure of a page as its figure block shows it (structure spec
    section 18; figures spec section 5): the path of its image, its box on
    the page, and its caption lines from the top down, none when it has no
    caption."""

    image: str
    box: Box
    caption: Piece

    @property
    def origin_box(self) -> Box:
        """The box that holds the figure and its caption, its block's
        origin: a plate's box, the whole page, holds its caption."""
        return box_of((self.box, *(line.line.box for line in self.caption.lines)))


@dataclass(frozen=True, slots=True)
class PageFigures:
    """What a page's in-page figures take from it (figures spec section 5):
    the places of the lines of its head line printed inside a figure,
    removed; the removals of those lines and of the figures' regions, as
    `figure_text`; the places of the words the captions took out of the
    page's lines; and the figures with their captions, in the order of
    pages.json."""

    head_places: frozenset[LinePlace]
    removals: tuple[Removal, ...]
    taken: frozenset[WordPlace]
    figures: tuple[PageFigure, ...]


def _head_inside_figures(
    head: HeadLine | None, removed: frozenset[LinePlace], boxes: tuple[Box, ...]
) -> tuple[LinePlace, ...]:
    """The places of the lines of the page's head line `head` when each of
    its words lies inside an in-page figure of `boxes` and structure spec
    section 3 did not remove it (`removed`): lettering printed at a
    picture's top; none otherwise."""
    if head is None or not boxes:
        return ()
    places = (
        (0, len(head.region.lines) - 1),
        *((number, 0) for number in head.beside),
    )
    if any(place in removed for place in places) or not in_any_figure(head.line, boxes):
        return ()
    return places


def page_figures(
    split: SplitPage, removed: frozenset[LinePlace], closed: frozenset[int]
) -> PageFigures:
    """The figure text, captions and figures of the page of `split`, whose
    lines at `removed` structure spec sections 3 and 4 removed and whose
    regions `closed` an index takes (figures spec section 5): its head line
    when printed inside a figure and every line of the figures' regions
    are removed as `figure_text`, and each figure's caption is found among
    the other lines (`figure_captions`)."""
    page = split.text
    boxes = tuple(figure.box for figure in split.figures)
    head_places = _head_inside_figures(head_line(page), removed, boxes)
    left = removed | frozenset(head_places)
    captions = figure_captions(
        tuple(
            ((region_number, line_number), line)
            for region_number, region in enumerate(page.regions)
            if region_number not in closed
            for line_number, line in enumerate(region.lines)
            if (region_number, line_number) not in left
        ),
        boxes,
    )
    return PageFigures(
        head_places=frozenset(head_places),
        removals=tuple(
            words_removal(
                page.index, line_at(page, place).words, RemovalReason.FIGURE_TEXT
            )
            for place in head_places
        )
        + tuple(
            words_removal(page.index, line.words, RemovalReason.FIGURE_TEXT)
            for region in split.regions
            if region is not None
            for line in region.lines
        ),
        taken=captions.taken,
        figures=tuple(
            PageFigure(
                figure.image,
                figure.box,
                Piece(
                    tuple(
                        PlacedLine(
                            page.index,
                            line,
                            Edges(figure.box.x0, figure.box.x1),
                            Edges(figure.box.x0, figure.box.x1),
                        )
                        for line in caption
                    )
                ),
            )
            for figure, caption in zip(split.figures, captions.lines, strict=True)
        ),
    )


def without_taken(
    line: Line, place: LinePlace, taken: frozenset[WordPlace]
) -> Line | None:
    """`line`, at `place`, without the words a caption took; None when it
    took them all."""
    kept = tuple(
        word for number, word in enumerate(line.words) if (*place, number) not in taken
    )
    if len(kept) == len(line.words):
        return line
    if not kept:
        return None
    return Line(words_box(kept), kept)
