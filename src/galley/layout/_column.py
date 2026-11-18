"""The steps of layout that place a page's words by its body column, which
both the laying out of a page and the re-reading of its small print take
(docs/specs/layout.md, section 3; docs/specs/reocr.md, section 4).

`BookMeasures` holds the numbers measured over the whole book.
`split_at_column` places the body column (step 1) and takes the outer
margin words out of it (step 2); `without_cut_in_notes` finds the notes
cut into the column beside its shortened lines and takes them out (step
2b), and `in_cut_in_zone` and `ends_short_of_inset` are its test of the
place of a cut-in note's word, which re-reading shares; `running_head_row_count` finds
the running-head region (step 3); `is_small_row` is the test of a row of
small type that the footnote band (step 4) and the small-print page
share. Positions are PDF points from the page's top left.
"""

import re
import statistics
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from typing import Final, assert_never

from galley.body_measures import edge_counts, group_rows, median_word_height
from galley.model import Line, Word

__all__ = [
    "BookMeasures",
    "ColumnSplit",
    "ColumnWords",
    "Side",
    "ends_short_of_inset",
    "has_letter_or_digit",
    "in_cut_in_zone",
    "is_small_row",
    "running_head_row_count",
    "split_at_column",
    "wide_rows_edges",
    "without_cut_in_notes",
]


# The book's measures (layout spec section 3, "The book's measures").

# The rows, the commonest edge, the pages measured and the body word
# height and pitch are body_measures' (architecture section 12).
# Guessed: a full line is the column width.
_WIDE_ROW_SHARE: Final[float] = 0.8
# Guessed, not measured: a page places its column itself when 3 of its rows
# are wide; a common edge has a third of the commonest edge's rows and lies
# more than 4 pt from the others (twice the commonest edge's 2 pt).
_PAGE_EDGE_ROWS: Final[int] = 3
_COMMON_EDGE_SHARE: Final[float] = 3.0
_COMMON_EDGE_APART_PT: Final[float] = 4.0


@dataclass(frozen=True, slots=True, kw_only=True)
class BookMeasures:
    """The numbers measured over a whole book that lay out each of its
    pages, in points (layout spec section 3).

    `column_width` is the width of the body column; `body_word_height` the
    median height of a body line's words; `body_line_pitch` the median
    distance from the top of one row to the top of the next.
    `usual_left_edge` is the left edge of the body column on a page that
    has no row wide enough to place it, by the parity of the page index:
    0 for even pages, 1 for odd. `cut_in_inset_left` and
    `cut_in_inset_right` are how far inside the column's left and right
    edges the body lines beside a margin note cut into the column start or
    end, to 0.1 pt; None on a side where the book has no such notes.
    """

    column_width: float
    body_word_height: float
    body_line_pitch: float
    usual_left_edge: frozendict[int, float]
    cut_in_inset_left: float | None
    cut_in_inset_right: float | None


def _common_edges(edges: Iterable[float]) -> tuple[float, ...]:
    """The common edges of `edges` (layout spec section 3, step 1): the
    commonest value, then the commonest of the values apart from every
    edge found, and so on, while a value has `_COMMON_EDGE_SHARE` of the
    first one's count."""
    by_count = sorted(
        edge_counts(edges).items(),
        key=lambda value_count: (-value_count[1], value_count[0]),
    )
    if not by_count:
        return ()
    least = by_count[0][1] / _COMMON_EDGE_SHARE
    peaks: list[float] = []
    for value, count in by_count:
        if count < least:
            break
        if all(abs(value - peak) > _COMMON_EDGE_APART_PT for peak in peaks):
            peaks.append(value)
    return tuple(peaks)


def wide_rows_edges(
    rows: tuple[Line, ...], column_width: float
) -> tuple[float, float] | None:
    """The left and right edges of the body column on a page of `rows`,
    from its wide rows (step 1): of the common edges of their left sides
    and of their right sides, the pair whose distance is nearest
    `column_width`, the smaller left and then right on a tie. None when
    too few rows are wide."""
    wide = tuple(
        row for row in rows if row.box.x1 - row.box.x0 >= _WIDE_ROW_SHARE * column_width
    )
    if len(wide) < _PAGE_EDGE_ROWS:
        return None
    return min(
        (
            (left, right)
            for left in _common_edges(row.box.x0 for row in wide)
            for right in _common_edges(row.box.x1 for row in wide)
        ),
        key=lambda pair: (abs(pair[1] - pair[0] - column_width), pair[0], pair[1]),
    )


# Measured: a word that crosses the column's edge is a body word; a word 2
# pt outside it took 64 of Domesday's 181,400 body words and 11 of Haskins'
# 60,900 into a margin.
_MARGIN_WORD_PT: Final[float] = 2.0
# Measured on the six whole books on 15 November 2026: a word whose middle
# lies 2 pt left of the left edge, whose row's next word starts a pitch
# inside the edge, beside a margin word of 2 letters, is a margin note's
# word in 23 of 23 checked (176 such words in Domesday, 95 in Gierke, none
# in the other four). 1 letter moves the same words; with no test of
# letters 3 more move, among them a list's "The" beside its number "44"
# (Gierke page 62).
_MARGIN_NOTE_LETTERS: Final[int] = 2

# Measured: the 5th percentile of the gap below the running head is 1.42
# pitches or more in the four evaluation books.
_RUNNING_HEAD_GAP_PITCHES: Final[float] = 1.3
# Measured on the whole books' words.json on 17 November 2026 (layout spec
# section 3, step 3): Stubbs' skew sets the date at the end of its head a
# row of its own 0.2 to 0.5 pitch below the rest of the head (pages 20,
# 100, 152, 158, 186, 202 and 210).
_HEAD_SKEW_PITCHES: Final[float] = 0.5
# Measured on 17 November 2026 (layout spec section 3, step 2): Turney's
# notes at the back hang their numbers 6 to 14 pt left of their text, left
# of the page's left edge; a number up to 15 pt from the word right of it
# stays in that word's line, on a page where 2 numbers do (18 November
# 2026, after review: one alone was an OCR speck read as a digit, on
# Gierke's 115 and 160 and Domesday's 443). So kept: Turney 99, Gierke 28
# (its contents, pages 62 and 65), none in the other books.
_HANGING_NUMBER = re.compile(r"[0-9]{1,3}")
_HANGING_NUMBER_GAP_PT: Final[float] = 15.0
_HANGING_NUMBERS_LEAST: Final[int] = 2


def _column_edges(
    rows: tuple[Line, ...], page_index: int, measures: BookMeasures
) -> tuple[float, float]:
    """The left and right edges of the body column on the page of `rows`,
    in points (step 1): the page's own, or, when too few rows are wide,
    the usual left edge of the page index's parity and that plus the
    column width."""
    edges = wide_rows_edges(rows, measures.column_width)
    if edges is None:
        left = measures.usual_left_edge[page_index % 2]
        return left, left + measures.column_width
    return edges


def _word_reaching_from_left_margin(
    row: Line, left: float, left_margin: tuple[Word, ...], pitch: float
) -> Word | None:
    """The first word of `row`, a row of the column's words, when it is a
    margin note's word whose box runs on into the column (step 2), else
    None: it holds a letter or a digit, its middle lies `_MARGIN_WORD_PT`
    or more left of `left`, the row has a second word that starts `pitch`
    or more right of `left`, and a word of `left_margin` with
    `_MARGIN_NOTE_LETTERS` letters lies within `pitch` above or below
    it."""
    first, *rest = sorted(row.words, key=lambda word: word.box.x0)
    reaches = (
        any(char.isalnum() for char in first.text)
        and (first.box.x0 + first.box.x1) / 2 <= left - _MARGIN_WORD_PT
        and bool(rest)
        and rest[0].box.x0 - left >= pitch
        and any(
            sum(char.isalpha() for char in word.text) >= _MARGIN_NOTE_LETTERS
            and word.box.top < first.box.bottom + pitch
            and word.box.bottom > first.box.top - pitch
            for word in left_margin
        )
    )
    return first if reaches else None


def has_letter_or_digit(row: Line) -> bool:
    """Whether a word of `row` holds a letter or a digit."""
    return any(char.isalnum() for word in row.words for char in word.text)


def _median_top(row: Line) -> float:
    """The median of the tops of `row`'s words, in points: the row's top
    for step 3, which an em dash or a word boxed tall does not move."""
    return statistics.median(word.box.top for word in row.words)


def running_head_row_count(rows: tuple[Line, ...], pitch: float) -> int:
    """How many of the column's `rows`, from the top, form the running-head
    region (step 3): the head row, the first with a letter or a digit, the
    rows above it, and the rows right below it whose tops lie less than
    `_HEAD_SKEW_PITCHES` times `pitch` below its top, when the next row
    with a letter or a digit has its top at least
    `_RUNNING_HEAD_GAP_PITCHES` times `pitch` below the head row's. A
    row's top is the median of its words' tops. 0 when there is no such
    region."""
    first = next(
        (index for index, row in enumerate(rows) if has_letter_or_digit(row)), None
    )
    if first is None:
        return 0
    head_top = _median_top(rows[first])
    end = first + 1
    while (
        end < len(rows)
        and _median_top(rows[end]) - head_top < _HEAD_SKEW_PITCHES * pitch
    ):
        end += 1
    below = next((row for row in rows[end:] if has_letter_or_digit(row)), None)
    if below is None:
        return 0
    gap = _median_top(below) - head_top
    return end if gap >= _RUNNING_HEAD_GAP_PITCHES * pitch else 0


# Measured: the median height of a line's words over the book's is at
# most 0.85 for 57 of Haskins' 57 lines of notes and 8 of its 6,144 lines
# of body (layout spec section 2).
_SMALL_ROW_SHARE: Final[float] = 0.85


@dataclass(frozen=True, slots=True, kw_only=True)
class ColumnSplit:
    """A page's words after steps 1 and 2: the body column's left and
    right edges, in points, the margin words of each side, and the words
    left in the column."""

    left: float
    right: float
    left_margin: tuple[Word, ...]
    right_margin: tuple[Word, ...]
    column: tuple[Word, ...]


def split_at_column(
    words: tuple[Word, ...], page_index: int, measures: BookMeasures
) -> ColumnSplit:
    """The words of a page placed by its body column (steps 1 and 2)."""
    left, right = _column_edges(group_rows(words), page_index, measures)
    # Each word goes to one group, also one whose box is inverted (x0 right
    # of x1), which would otherwise lie in both margins.
    outside_left = tuple(
        word for word in words if word.box.x1 <= left - _MARGIN_WORD_PT
    )
    right_margin = tuple(
        word
        for word in words
        if word.box.x1 > left - _MARGIN_WORD_PT
        and word.box.x0 >= right + _MARGIN_WORD_PT
    )
    in_column = tuple(
        word
        for word in words
        if word.box.x1 > left - _MARGIN_WORD_PT
        and word.box.x0 < right + _MARGIN_WORD_PT
    )
    # A note's word whose box runs on into the column goes to the left
    # margin; compared by identity, since two words may be equal.
    reaching = {
        id(word)
        for row in group_rows(in_column)
        if (
            word := _word_reaching_from_left_margin(
                row, left, outside_left, measures.body_line_pitch
            )
        )
        is not None
    }
    left_margin = (
        *outside_left,
        *(word for word in in_column if id(word) in reaching),
    )
    column = tuple(word for word in in_column if id(word) not in reaching)
    hanging = _hanging_numbers(left_margin, column)
    # The column keeps the order of the page's words, its hanging numbers
    # among them.
    kept = hanging | {id(word) for word in column}
    return ColumnSplit(
        left=left,
        right=right,
        left_margin=tuple(word for word in left_margin if id(word) not in hanging),
        right_margin=right_margin,
        column=tuple(word for word in words if id(word) in kept),
    )


def _hanging_number(
    number: Word, left_margin: tuple[Word, ...], column: tuple[Word, ...]
) -> bool:
    """Whether `number`, a word of `left_margin`, hangs before a line of
    `column`'s words (step 2): 1 to 3 digits, on a row that is not the
    first with a letter or a digit (the head row of step 3), whose next
    word right of it starts at most `_HANGING_NUMBER_GAP_PT` right of the
    number's right side, with no other margin word between them but
    digits."""
    if _HANGING_NUMBER.fullmatch(number.text) is None:
        return False
    rows = group_rows((*column, number))
    place = next(
        place
        for place, row in enumerate(rows)
        if any(word is number for word in row.words)
    )
    head = next(
        (place for place, row in enumerate(rows) if has_letter_or_digit(row)), None
    )
    right = tuple(
        word
        for word in rows[place].words
        if word is not number and word.box.x0 > number.box.x0
    )
    if place == head or not right:
        return False
    start = min(word.box.x0 for word in right)
    row = rows[place].box
    # A number the OCR split ("5" "1") hangs whole: digits between count
    # as none.
    between = any(
        other is not number
        and _HANGING_NUMBER.fullmatch(other.text) is None
        and other.box.x0 >= number.box.x1
        and other.box.x1 <= start
        and other.box.top < row.bottom
        and other.box.bottom > row.top
        for other in left_margin
    )
    return start - number.box.x1 <= _HANGING_NUMBER_GAP_PT and not between


def _hanging_numbers(
    left_margin: tuple[Word, ...], column: tuple[Word, ...]
) -> frozenset[int]:
    """The identities of the words of `left_margin` that stay in the column
    as hanging numbers (step 2): those `_hanging_number` takes, when it
    takes at least `_HANGING_NUMBERS_LEAST` on the page."""
    hanging = frozenset(
        id(number)
        for number in left_margin
        if _hanging_number(number, left_margin, column)
    )
    return hanging if len(hanging) >= _HANGING_NUMBERS_LEAST else frozenset()


# Measured on Stubbs' whole book on 16 November 2026 (layout spec section
# 3, step 2b): a cut row has a word within 3 pt of the inset, after a gap
# of 8 pt (the body's word spaces are 8.1 pt at the 95th percentile) or
# first in its row, and its words from there span half the column, which
# keeps out a speck at the inset (";", page 51). Cut rows chain within 1.6
# pitches (with 2.6, 53 more body words moved); a chain needs 2 cut rows
# (with 1, 47 more) and a shortened row, with nothing 4 pt short of the
# inset (without one, 56 more). A note word's middle lies within 1 pt of
# its zone. With these, 1,314 words moved: 767 aligned to a margin note of
# the reference, 73 to the body (this code moved 1,324 there). A word less
# than 5 pt from a body word of its row stays, as a word of a sentence does
# (the body's word spaces are 4.5 pt at the median; "issued as his", page
# 33): with it 1,318 words move, and 0.940 of those aligned are note words
# by the evaluation tool of 16 November 2026, 0.936 without it.
_CUT_ROW_INSET_PT: Final[float] = 3.0
_CUT_ROW_GAP_PT: Final[float] = 8.0
_CUT_ROW_SPAN_SHARE: Final[float] = 0.5
_CUT_IN_CHAIN_PITCHES: Final[float] = 1.6
_CUT_IN_CHAIN_ROWS: Final[int] = 2
_CUT_IN_STRIP_PT: Final[float] = 4.0
_CUT_IN_ZONE_PT: Final[float] = 1.0
_CUT_IN_BODY_GAP_PT: Final[float] = 5.0


@dataclass(frozen=True, slots=True)
class _SideWord:
    """A word of the column seen from one side of it, in points: on the
    left, `start` and `end` are its left and right sides; on the right,
    its right and left sides negated, so that the rules of the left side
    read the right side mirrored. `index` is its place among the column's
    words."""

    index: int
    start: float
    end: float
    top: float
    bottom: float


class Side(StrEnum):
    """A side of the body column: that of an outer margin, and of a note
    cut into the column."""

    LEFT = "left"
    RIGHT = "right"


def _side_words(
    row: Line, side: Side, index_of: dict[int, int]
) -> tuple[_SideWord, ...]:
    """The words of `row` seen from `side`, in the order of their
    start; `index_of` gives a word's place by its identity."""
    match side:
        case Side.LEFT:
            side_words = (
                _SideWord(
                    index_of[id(word)],
                    word.box.x0,
                    word.box.x1,
                    word.box.top,
                    word.box.bottom,
                )
                for word in row.words
            )
        case Side.RIGHT:
            side_words = (
                _SideWord(
                    index_of[id(word)],
                    -word.box.x1,
                    -word.box.x0,
                    word.box.top,
                    word.box.bottom,
                )
                for word in row.words
            )
        case _:
            assert_never(side)
    return tuple(sorted(side_words, key=lambda word: word.start))


def _is_cut_row(row: tuple[_SideWord, ...], at: float, least_span: float) -> bool:
    """Whether `row`, seen from its side, is cut at the inset
    `at` (step 2b, rule 1): a word starts within `_CUT_ROW_INSET_PT` of
    `at`, first in the row or after a gap of `_CUT_ROW_GAP_PT`, and the
    row's words from it on span `least_span` or more."""
    return any(
        abs(word.start - at) <= _CUT_ROW_INSET_PT
        and (
            position == 0
            or word.start - max(before.end for before in row[:position])
            >= _CUT_ROW_GAP_PT
        )
        and max(after.end for after in row[position:]) - word.start >= least_span
        for position, word in enumerate(row)
    )


def _cut_in_zones(
    rows: tuple[tuple[_SideWord, ...], ...], at: float, least_span: float, pitch: float
) -> tuple[tuple[float, float], ...]:
    """The cut-in zones of a page's `rows`, seen from one side, as (top,
    bottom) in points (step 2b, rule 2): each chain of at least
    `_CUT_IN_CHAIN_ROWS` cut rows, each within `_CUT_IN_CHAIN_PITCHES`
    pitches of the one before, that holds a shortened row, trimmed to its
    first and last shortened rows."""
    chains: list[list[tuple[_SideWord, ...]]] = []
    for row in rows:
        if not _is_cut_row(row, at, least_span):
            continue
        top = min(word.top for word in row)
        if chains and top - min(word.top for word in chains[-1][-1]) <= (
            _CUT_IN_CHAIN_PITCHES * pitch
        ):
            chains[-1].append(row)
        else:
            chains.append([row])
    strip_end = at - _CUT_IN_STRIP_PT
    zones = []
    for chain in chains:
        shortened = tuple(
            position
            for position, row in enumerate(chain)
            if all(word.end > strip_end for word in row)
        )
        if len(chain) < _CUT_IN_CHAIN_ROWS or not shortened:
            continue
        first, last = chain[shortened[0]], chain[shortened[-1]]
        zones.append(
            (min(word.top for word in first), max(word.bottom for word in last))
        )
    return tuple(zones)


def _cut_in_inset(side: Side, measures: BookMeasures) -> float | None:
    match side:
        case Side.LEFT:
            return measures.cut_in_inset_left
        case Side.RIGHT:
            return measures.cut_in_inset_right
        case _:
            assert_never(side)


def _seen_from(side: Side, edge: float) -> float:
    """The column's `edge` on `side` as `_SideWord` sees it: the right edge
    negated."""
    match side:
        case Side.LEFT:
            return edge
        case Side.RIGHT:
            return -edge
        case _:
            assert_never(side)


@dataclass(frozen=True, slots=True, kw_only=True)
class _CutIn:
    """The cut-in zones of one side of a page, as (top, bottom) in points,
    and the places among the column's words of the notes' words."""

    zones: tuple[tuple[float, float], ...]
    note_indices: frozenset[int]


def _cut_in(
    column: tuple[Word, ...], side: Side, edge: float, measures: BookMeasures
) -> _CutIn:
    """The cut-in zones and notes of `column`'s words at `side`, whose
    column edge is `edge` (step 2b, rules 1 to 3)."""
    inset = _cut_in_inset(side, measures)
    if inset is None:
        return _CutIn(zones=(), note_indices=frozenset())
    index_of = {id(word): index for index, word in enumerate(column)}
    rows = tuple(_side_words(row, side, index_of) for row in group_rows(column))
    at = _seen_from(side, edge) + inset
    zones = _cut_in_zones(
        rows, at, _CUT_ROW_SPAN_SHARE * measures.column_width, measures.body_line_pitch
    )
    in_zones = frozenset(
        word.index
        for row in rows
        for word in row
        if ends_short_of_inset(column[word.index], side, edge, inset)
        and in_cut_in_zone(column[word.index], zones)
    )
    return _CutIn(
        zones=zones,
        note_indices=frozenset(
            index for row in rows for index in _apart_from_body(row, in_zones)
        ),
    )


def in_cut_in_zone(word: Word, zones: tuple[tuple[float, float], ...]) -> bool:
    """Whether the vertical middle of `word` lies in one of `zones`, the
    cut-in zones of a side, each (top, bottom) in points, give or take
    `_CUT_IN_ZONE_PT` (step 2b, rule 3)."""
    middle = (word.box.top + word.box.bottom) / 2
    return any(
        top - _CUT_IN_ZONE_PT <= middle <= bottom + _CUT_IN_ZONE_PT
        for top, bottom in zones
    )


def ends_short_of_inset(word: Word, side: Side, edge: float, inset: float) -> bool:
    """Whether `word` ends `_CUT_IN_STRIP_PT` or more short of the cut-in
    `inset` of `side`, whose column edge is `edge`, in points: the place of
    a cut-in note's word (step 2b, rule 3)."""
    match side:
        case Side.LEFT:
            return word.box.x1 <= edge + inset - _CUT_IN_STRIP_PT
        case Side.RIGHT:
            return word.box.x0 >= edge - inset + _CUT_IN_STRIP_PT
        case _:
            assert_never(side)


@dataclass(frozen=True, slots=True, kw_only=True)
class ColumnWords:
    """The words of a page's body column after step 2b: `column`, those
    left in it, in their order; `left_cut_in` and `right_cut_in`, the words
    of the notes cut into it at each side, in their order; and each side's
    cut-in zones, (top, bottom) in points."""

    column: tuple[Word, ...]
    left_cut_in: tuple[Word, ...]
    right_cut_in: tuple[Word, ...]
    left_zones: tuple[tuple[float, float], ...]
    right_zones: tuple[tuple[float, float], ...]


def without_cut_in_notes(split: ColumnSplit, measures: BookMeasures) -> ColumnWords:
    """The column's words of `split` with the notes cut into it taken out
    (step 2b), on each side where the book has a cut-in inset."""
    left = _cut_in(split.column, Side.LEFT, split.left, measures)
    right = _cut_in(split.column, Side.RIGHT, split.right, measures)
    notes = left.note_indices | right.note_indices
    return ColumnWords(
        column=tuple(
            word for index, word in enumerate(split.column) if index not in notes
        ),
        left_cut_in=tuple(split.column[index] for index in sorted(left.note_indices)),
        right_cut_in=tuple(split.column[index] for index in sorted(right.note_indices)),
        left_zones=left.zones,
        right_zones=right.zones,
    )


def is_small_row(row: Line, measures: BookMeasures) -> bool:
    """Whether `row` is a row of small type: the median height of its words
    is at most `_SMALL_ROW_SHARE` of the body word height (step 4)."""
    return median_word_height(row.words) <= _SMALL_ROW_SHARE * measures.body_word_height


def _apart_from_body(
    row: tuple[_SideWord, ...], in_zones: frozenset[int]
) -> frozenset[int]:
    """The places of the words of `row` that are in `in_zones`
    and lie `_CUT_IN_BODY_GAP_PT` or more from every body word of the row
    (step 2b, rule 3): a word not in `in_zones` is a body word, and so is
    a word of `in_zones` that lies nearer than that to one."""
    notes = {word.index for word in row if word.index in in_zones}
    while True:
        body = tuple(word for word in row if word.index not in notes)
        near = {
            word.index
            for word in row
            if word.index in notes
            and any(
                max(other.start - word.end, word.start - other.end)
                < _CUT_IN_BODY_GAP_PT
                for other in body
            )
        }
        if not near:
            return frozenset(notes)
        notes -= near
