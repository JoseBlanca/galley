"""layout: each page's words grouped into regions and lines, in reading order.

The rules are those of docs/specs/layout.md. `measure_book` takes the
book's measures over all its pages: the width of the body column, the
height of a body word, the distance between rows, the usual left edge of
the column, and the cut-in insets, how far inside the column the body
lines beside a margin note set into the column start or end (of the six
sample books, only Stubbs has them); the height and the distance are taken
by `galley.body_measures`, which structure shares, and so are the rows:
`body_measures.group_rows` groups words into lines by the walking
skeleton's rule, a word joining the line of the word that started it, its
anchor, when the word's vertical centre lies within the anchor's top and
bottom. `layout_page` places the body column on the page, takes the words
outside it, and the words of the notes set into it beside its shortened
lines, as margin regions, the first row set apart at the top as the
running-head region and the small rows at the foot as the footnote band,
cuts the body and the band into two columns where a gutter runs down them,
and puts a drop capital first in the line beside it. `run` measures the
book, then lays out its pages in parallel.
"""

import bisect
import logging
import math
from collections.abc import Iterable
from dataclasses import dataclass, replace
from enum import StrEnum
from itertools import groupby
from statistics import median
from typing import Final, assert_never

from galley.body_measures import (
    body_measures,
    commonest,
    edge_counts,
    group_rows,
    measured_page_positions,
    measured_pages,
    median_word_height,
)
from galley.book_folder import BookFolder, Stage, delete_stage_outputs
from galley.config import BookConfig
from galley.errors import FidelityBoundary
from galley.fidelity import check_stage
from galley.model import (
    Box,
    Line,
    LinesFile,
    PageLayout,
    PageWords,
    Region,
    Word,
    WordsFile,
    read_checked_input,
    read_words,
    write_lines,
)
from galley.parallel import DEFAULT_WORKERS, map_pages

__all__ = ["BookMeasures", "layout_page", "measure_book", "run"]

_logger = logging.getLogger(__name__)


def _enclosing_box(boxes: tuple[Box, ...]) -> Box:
    """The smallest box that holds every box of `boxes`, which is not empty."""
    return Box(
        min(box.x0 for box in boxes),
        min(box.top for box in boxes),
        max(box.x1 for box in boxes),
        max(box.bottom for box in boxes),
    )


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


def _wide_rows_edges(
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


def _commonest_left_edge(rows: tuple[Line, ...]) -> float:
    """The commonest left side of `rows`, which are not empty."""
    return commonest(row.box.x0 for row in rows)


def _column_width_of_page(rows: tuple[Line, ...]) -> float:
    """The commonest right side of `rows` minus their commonest left side;
    `rows` is not empty."""
    return commonest(row.box.x1 for row in rows) - _commonest_left_edge(rows)


def _usual_left_edges(
    pages: tuple[PageWords, ...],
    rows_by_page: tuple[tuple[Line, ...], ...],
    measured: tuple[tuple[Line, ...], ...],
    column_width: float,
) -> frozendict[int, float]:
    """The usual left edge for even (0) and odd (1) page indices: the median
    of the left edges step 1 finds on the pages of that parity that place
    their column themselves, else the
    other parity's, else the median of the commonest left edges of the
    `measured` pages."""
    found = tuple(
        (page.index % 2, edges[0])
        for page, rows in zip(pages, rows_by_page, strict=True)
        if (edges := _wide_rows_edges(rows, column_width)) is not None
    )
    either_parity = (
        median(edge for _, edge in found)
        if found
        else median(_commonest_left_edge(rows) for rows in measured)
    )

    def of_parity(parity: int) -> float:
        lefts = tuple(edge for edge_parity, edge in found if edge_parity == parity)
        return median(lefts) if lefts else either_parity

    return frozendict({0: of_parity(0), 1: of_parity(1)})


def measure_book(
    words: WordsFile, *, workers: int = DEFAULT_WORKERS
) -> BookMeasures | None:
    """The measures of the book of `words` (layout spec section 3), taken
    from the rows of its pages of at least 15 rows, or of 3 rows when it
    has none of 15. None when no page has 3 rows: its pages are then laid
    out as one region each. The cut-in insets are measured once every
    measured page's column is placed. The pages are worked on in `workers`
    threads; the result does not depend on their number."""

    def page_rows(page: PageWords) -> tuple[Line, ...]:
        return group_rows(page.words)

    rows_by_page = map_pages(page_rows, words.pages, workers)
    measured = measured_pages(rows_by_page)
    # The measured pages are their own measured pages: body_measures takes
    # the same rows from them as from every page.
    body = body_measures(measured)
    if body is None:
        return None
    column_width = median(_column_width_of_page(rows) for rows in measured)
    without_insets = BookMeasures(
        column_width=column_width,
        body_word_height=body.body_word_height,
        body_line_pitch=body.body_line_pitch,
        usual_left_edge=_usual_left_edges(
            words.pages, rows_by_page, measured, column_width
        ),
        cut_in_inset_left=None,
        cut_in_inset_right=None,
    )
    measured_words = tuple(
        words.pages[position] for position in measured_page_positions(rows_by_page)
    )

    def page_insets(page: PageWords) -> tuple[tuple[int, ...], tuple[int, ...]]:
        return _row_insets(_split_at_column(page.words, page.index, without_insets))

    insets = map_pages(page_insets, measured_words, workers)
    return replace(
        without_insets,
        cut_in_inset_left=_cut_in_inset(
            tuple(inset for left, _ in insets for inset in left)
        ),
        cut_in_inset_right=_cut_in_inset(
            tuple(inset for _, right in insets for inset in right)
        ),
    )


# Measured on the six whole books and the six excerpts on 16 November 2026
# (layout spec section 3, "The book's measures"): Stubbs' cut-in insets lie
# 60.4 and 59.0 pt inside its column, with 394 and 359 rows within 2 pt of
# them and at most 40 rows 6 to 12 pt to either side (this code, on the
# books of that day, measures 60.3 and 59.3 pt, 397 and 362 rows); no other
# book has a peak more than 1.3 times its neighbours'. The floor of 10 rows lets the
# Stubbs excerpt, 17 and 13 rows, pass; the other excerpts have at most 11
# rows at their peak, against 9 beside it.
_CUT_IN_INSET_TENTHS: Final[int] = 10
_CUT_IN_INSET_LEAST_TENTHS: Final[int] = 300
_CUT_IN_INSET_MOST_TENTHS: Final[int] = 1000
_CUT_IN_PEAK_TENTHS: Final[int] = 20
_CUT_IN_NEIGHBOURS_NEAR_TENTHS: Final[int] = 60
_CUT_IN_NEIGHBOURS_FAR_TENTHS: Final[int] = 120
_CUT_IN_PEAK_ROWS: Final[int] = 10
_CUT_IN_PEAK_TIMES_NEIGHBOURS: Final[int] = 4


def _row_insets(split: _ColumnSplit) -> tuple[tuple[int, ...], tuple[int, ...]]:
    """The left and right insets of the rows of `split`'s column words, in
    tenths of a point: how far each row starts right of the left edge and
    ends left of the right edge."""
    rows = group_rows(split.column)
    return (
        tuple(_tenths(row.box.x0 - split.left) for row in rows),
        tuple(_tenths(split.right - row.box.x1) for row in rows),
    )


def _tenths(points: float) -> int:
    return round(points * _CUT_IN_INSET_TENTHS)


def _cut_in_inset(insets: tuple[int, ...]) -> float | None:
    """The cut-in inset of one side of a book, in points, from the `insets`
    of the rows of its measured pages, in tenths of a point (layout spec
    section 3): of the insets from 30 to 100 pt, the one with the most rows
    within 2 pt of it, the smaller on a tie, when those rows are at least
    10 and 4 times the rows 6 to 12 pt smaller and 4 times those 6 to 12 pt
    larger. None otherwise."""
    ordered = sorted(insets)

    def rows_between(least: int, most: int) -> int:
        return bisect.bisect_right(ordered, most) - bisect.bisect_left(ordered, least)

    def rows_at(peak: int) -> int:
        return rows_between(peak - _CUT_IN_PEAK_TENTHS, peak + _CUT_IN_PEAK_TENTHS)

    candidates = sorted(
        {
            inset
            for inset in ordered
            if _CUT_IN_INSET_LEAST_TENTHS <= inset <= _CUT_IN_INSET_MOST_TENTHS
        }
    )
    if not candidates:
        return None
    # The candidates are in increasing order, and max keeps the first of a
    # tie.
    peak = max(candidates, key=rows_at)
    at_peak = rows_at(peak)
    smaller = rows_between(
        peak - _CUT_IN_NEIGHBOURS_FAR_TENTHS, peak - _CUT_IN_NEIGHBOURS_NEAR_TENTHS
    )
    larger = rows_between(
        peak + _CUT_IN_NEIGHBOURS_NEAR_TENTHS, peak + _CUT_IN_NEIGHBOURS_FAR_TENTHS
    )
    has_notes = (
        at_peak >= _CUT_IN_PEAK_ROWS
        and at_peak >= _CUT_IN_PEAK_TIMES_NEIGHBOURS * smaller
        and at_peak >= _CUT_IN_PEAK_TIMES_NEIGHBOURS * larger
    )
    return peak / _CUT_IN_INSET_TENTHS if has_notes else None


# Laying out a page (layout spec section 3, "Per page").

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
# Guessed, so that each printed margin note is a region of its own.
_MARGIN_REGION_GAP_PITCHES: Final[float] = 1.5
# Measured: the 5th percentile of the gap below the running head is 1.42
# pitches or more in the four evaluation books.
_RUNNING_HEAD_GAP_PITCHES: Final[float] = 1.3


def _region(lines: tuple[Line, ...]) -> Region:
    """The region of `lines`, which are not empty, with the smallest box
    that holds them."""
    return Region(_enclosing_box(tuple(line.box for line in lines)), lines)


def _words_of(rows: tuple[Line, ...]) -> tuple[Word, ...]:
    return tuple(word for row in rows for word in row.words)


def _region_of_rows(rows: tuple[Line, ...]) -> Region:
    """The region of the words of `rows`, which are not empty, grouped
    into lines again (step 7)."""
    return _region(group_rows(_words_of(rows)))


def _column_edges(
    rows: tuple[Line, ...], page_index: int, measures: BookMeasures
) -> tuple[float, float]:
    """The left and right edges of the body column on the page of `rows`,
    in points (step 1): the page's own, or, when too few rows are wide,
    the usual left edge of the page index's parity and that plus the
    column width."""
    edges = _wide_rows_edges(rows, measures.column_width)
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


def _margin_regions(words: tuple[Word, ...], pitch: float) -> tuple[Region, ...]:
    """The margin regions of the margin words of one side of a page (step
    2): their lines, cut where a line's top is more than
    `_MARGIN_REGION_GAP_PITCHES` times `pitch` below the top of the line
    before."""
    groups: list[list[Line]] = []
    for line in group_rows(words):
        if (
            groups
            and line.box.top - groups[-1][-1].box.top
            <= _MARGIN_REGION_GAP_PITCHES * pitch
        ):
            groups[-1].append(line)
        else:
            groups.append([line])
    return tuple(_region(tuple(group)) for group in groups)


def _has_letter_or_digit(row: Line) -> bool:
    return any(char.isalnum() for word in row.words for char in word.text)


def _running_head_row_count(rows: tuple[Line, ...], pitch: float) -> int:
    """How many of the column's `rows`, from the top, form the running-head
    region (step 3): the first row with a letter or a digit and the rows
    above it, when the next row's top is at least
    `_RUNNING_HEAD_GAP_PITCHES` times `pitch` below that row's top. 0 when
    there is no such region."""
    first = next(
        (index for index, row in enumerate(rows) if _has_letter_or_digit(row)), None
    )
    if first is None or first + 1 >= len(rows):
        return 0
    gap = rows[first + 1].box.top - rows[first].box.top
    return first + 1 if gap >= _RUNNING_HEAD_GAP_PITCHES * pitch else 0


# Measured: the median height of a line's words over the book's is at
# most 0.85 for 57 of Haskins' 57 lines of notes and 8 of its 6,144 lines
# of body (layout spec section 2).
_SMALL_ROW_SHARE: Final[float] = 0.85
# Guessed: Mariéjol's note lines are small on 769 of 911.
_BAND_SMALL_ROWS_SHARE: Final[float] = 2 / 3
# Measured: the 10th percentile of the gap from the last body line to the
# first note line is 1.16 pitches in Haskins, 1.24 in Domesday, 1.39 in
# Mariéjol.
_BAND_GAP_PITCHES: Final[float] = 1.1
# Measured on the six books (layout spec section 3, "Where the thresholds
# come from"): a gutter is a strip 6 pt wide in the middle third of the
# column; a word across it whose middle is more than 6 pt from the strip's
# is an OCR word that ran over the gutter.
_GUTTER_WIDTH_PT: Final[float] = 6.0
# Guessed, not measured: a step of 1 pt, the precision of the commonest
# edge.
_GUTTER_STEP_PT: Final[float] = 1.0
_GUTTER_CROSSING_WORD_PT: Final[float] = 6.0
# Measured: with 8 open rows the cut fires on the index pages and tables of
# the six books and on no page of running text, with 5 on 14 pages of
# Mariéjol's text. Two columns of notes are often only 3 rows long.
_BODY_OPEN_ROWS: Final[int] = 8
_BAND_OPEN_ROWS: Final[int] = 3
# Measured on the six books: the gutter of two columns of notes is within
# 8 pt of the column's middle (Kadesh, 30 runs of 3 open rows or more); that
# of Domesday's short notes printed side by side 13 to 46 pt from it.
_BAND_GUTTER_OFF_CENTRE_PT: Final[float] = 10.0
# Measured: Haskins' drop capitals are 2.67 ("IN", page 163) to 4 times the
# body word height.
_DROP_CAPITAL_HEIGHTS: Final[float] = 2.2
# Guessed, not measured: the drop capital's left side lies within 3 pt of the
# left edge, a little more than the commonest edge's 2 pt.
_DROP_CAPITAL_EDGE_PT: Final[float] = 3.0


class _Part(StrEnum):
    """The part of the column that is cut into columns: the body or the
    footnote band, which need different numbers of open rows."""

    BODY = "body"
    BAND = "band"


def _open_rows_to_cut(part: _Part) -> int:
    """The open rows a run of `part` needs to be cut into columns."""
    match part:
        case _Part.BODY:
            return _BODY_OPEN_ROWS
        case _Part.BAND:
            return _BAND_OPEN_ROWS
        case _:
            assert_never(part)


class _AtGutter(StrEnum):
    """How a row lies at a gutter: open (words on both sides, none across),
    on one side only, with one word across it far from its middle, or
    blocked. All but the last are compatible with a column cut."""

    OPEN = "open"
    ONE_SIDE = "one side"
    CROSSED_ASIDE = "crossed aside"
    BLOCKED = "blocked"


def _band_start(rows: tuple[Line, ...], measures: BookMeasures) -> int:
    """The index in `rows` of the first row of the footnote band (step 4),
    or len(rows) when there is no band."""
    small = tuple(
        median_word_height(row.words) <= _SMALL_ROW_SHARE * measures.body_word_height
        for row in rows
    )
    if all(small):
        return len(rows)
    return next(
        (
            index
            for index in range(1, len(rows))
            if small[index]
            and rows[index].box.top - rows[index - 1].box.top
            >= _BAND_GAP_PITCHES * measures.body_line_pitch
            and sum(small[index:]) >= _BAND_SMALL_ROWS_SHARE * (len(rows) - index)
        ),
        len(rows),
    )


def _row_gaps(row: Line) -> tuple[tuple[float, float], ...]:
    """The empty stretches of `row` between its words, as (left, right) in
    points, with words on both sides."""
    gaps = []
    reach = None
    for word in sorted(row.words, key=lambda word: word.box.x0):
        if reach is not None and word.box.x0 > reach:
            gaps.append((reach, word.box.x0))
        reach = word.box.x1 if reach is None else max(reach, word.box.x1)
    return tuple(gaps)


def _gutter_middle(rows: tuple[Line, ...], left: float, width: float) -> float | None:
    """The middle of the gutter of `rows`, in points (step 5): of the strips
    whose middles step across the middle third of the column
    from `left`, `width` wide, the leftmost at which most rows are open.
    None when no row is open at any."""
    start = left + width / 3
    count = int(width / 3 / _GUTTER_STEP_PT) + 1
    half = _GUTTER_WIDTH_PT / 2
    open_rows = [0] * count
    for row in rows:
        opened = {
            step
            for gap_left, gap_right in _row_gaps(row)
            for step in range(
                max(0, math.floor((gap_left + half - start) / _GUTTER_STEP_PT)),
                min(count, math.ceil((gap_right - half - start) / _GUTTER_STEP_PT) + 1),
            )
            if gap_left <= start + step * _GUTTER_STEP_PT - half
            and start + step * _GUTTER_STEP_PT + half <= gap_right
        }
        for step in opened:
            open_rows[step] += 1
    most = max(open_rows)
    return None if most == 0 else start + open_rows.index(most) * _GUTTER_STEP_PT


def _at_gutter(row: Line, middle: float) -> _AtGutter:
    """How `row` lies at the gutter's strip around `middle` (step 5)."""
    half = _GUTTER_WIDTH_PT / 2
    across = tuple(
        word
        for word in row.words
        if word.box.x0 < middle + half and word.box.x1 > middle - half
    )
    if not across:
        both_sides = any(word.box.x1 <= middle - half for word in row.words) and any(
            word.box.x0 >= middle + half for word in row.words
        )
        return _AtGutter.OPEN if both_sides else _AtGutter.ONE_SIDE
    if (
        len(across) == 1
        and abs((across[0].box.x0 + across[0].box.x1) / 2 - middle)
        > _GUTTER_CROSSING_WORD_PT
    ):
        return _AtGutter.CROSSED_ASIDE
    return _AtGutter.BLOCKED


def _run_is_cut(column_run: tuple[tuple[Line, _AtGutter], ...], part: _Part) -> bool:
    """Whether a run of compatible rows has the open rows to be cut into two
    columns (step 5)."""
    open_rows = sum(at is _AtGutter.OPEN for _, at in column_run)
    return open_rows >= _open_rows_to_cut(part)


def _cut_run(rows: tuple[Line, ...], middle: float) -> tuple[Region, Region]:
    """The left and right columns of a cut run: each word goes by its own
    middle, left of `middle` or not."""
    words = _words_of(rows)
    return (
        _region(
            group_rows(
                tuple(
                    word for word in words if (word.box.x0 + word.box.x1) / 2 < middle
                )
            )
        ),
        _region(
            group_rows(
                tuple(
                    word for word in words if (word.box.x0 + word.box.x1) / 2 >= middle
                )
            )
        ),
    )


def _column_cut_regions(
    rows: tuple[Line, ...], left: float, width: float, part: _Part
) -> tuple[Region, ...]:
    """The regions of the body or the band, top to bottom: each run of
    rows cut at the gutter gives its left and its right column, and the
    rows between such runs a region each (step 5). A run is a stretch of
    compatible rows, in the body from an open row to an open row."""
    if not rows:
        return ()
    middle = _gutter_middle(rows, left, width)
    if middle is None or (
        part is _Part.BAND
        and abs(middle - (left + width / 2)) > _BAND_GUTTER_OFF_CENTRE_PT
    ):
        return (_region_of_rows(rows),)
    regions: list[Region] = []
    pending: list[Line] = []
    for compatible, group in groupby(
        ((row, _at_gutter(row, middle)) for row in rows),
        key=lambda row_at: row_at[1] is not _AtGutter.BLOCKED,
    ):
        stretch = tuple(group)
        opened = tuple(
            index for index, (_, at) in enumerate(stretch) if at is _AtGutter.OPEN
        )
        if not (compatible and opened):
            pending.extend(row for row, _ in stretch)
            continue
        if part is _Part.BAND:
            opened = (0, len(stretch) - 1)
        # In the body a run starts and ends at an open row; the rows before
        # and after it in the stretch stay rows.
        pending.extend(row for row, _ in stretch[: opened[0]])
        column_run = stretch[opened[0] : opened[-1] + 1]
        if _run_is_cut(column_run, part):
            if pending:
                regions.append(_region_of_rows(tuple(pending)))
                pending = []
            regions.extend(_cut_run(tuple(row for row, _ in column_run), middle))
        else:
            pending.extend(row for row, _ in column_run)
        pending.extend(row for row, _ in stretch[opened[-1] + 1 :])
    if pending:
        regions.append(_region_of_rows(tuple(pending)))
    return tuple(regions)


def _column_regions(
    words: tuple[Word, ...], left: float, measures: BookMeasures
) -> tuple[tuple[Region, ...], tuple[Region, ...]]:
    """The regions of the body column's `words`, a drop capital set aside:
    the running-head region and the body's regions, then the band's (steps
    3 to 5 and 7)."""
    rows = group_rows(words)
    head_count = _running_head_row_count(rows, measures.body_line_pitch)
    head, rest = rows[:head_count], rows[head_count:]
    band_start = _band_start(rest, measures)
    width = measures.column_width
    return (
        (
            *((_region_of_rows(head),) if head else ()),
            *_column_cut_regions(rest[:band_start], left, width, _Part.BODY),
        ),
        _column_cut_regions(rest[band_start:], left, width, _Part.BAND),
    )


def _is_drop_capital(word: Word, left: float, measures: BookMeasures) -> bool:
    return (
        word.box.bottom - word.box.top
        > _DROP_CAPITAL_HEIGHTS * measures.body_word_height
        and abs(word.box.x0 - left) <= _DROP_CAPITAL_EDGE_PT
    )


def _with_drop_capital(
    regions: tuple[Region, ...], capital: Word
) -> tuple[Region, ...] | None:
    """`regions` with `capital` placed first in a line beside it (step 6):
    a line whose box overlaps the capital's vertically and starts at or
    right of its middle. The line is the topmost beside it in the region
    whose line beside it starts nearest the capital. None when no line is
    beside it."""
    capital_middle = (capital.box.x0 + capital.box.x1) / 2
    beside = tuple(
        (line.box.x0, region_index, line.box.top, line_index)
        for region_index, region in enumerate(regions)
        for line_index, line in enumerate(region.lines)
        if line.box.top < capital.box.bottom
        and line.box.bottom > capital.box.top
        and line.box.x0 >= capital_middle
    )
    if not beside:
        return None
    _, region_index, _, _ = min(beside)
    _, line_index = min(
        (top, index) for _, region, top, index in beside if region == region_index
    )
    lines = regions[region_index].lines
    line = lines[line_index]
    placed = Line(_enclosing_box((capital.box, line.box)), (capital, *line.words))
    region = _region((*lines[:line_index], placed, *lines[line_index + 1 :]))
    return (*regions[:region_index], region, *regions[region_index + 1 :])


def _column_regions_with_drop_capitals(
    words: tuple[Word, ...],
    set_aside: frozenset[int],
    left: float,
    measures: BookMeasures,
) -> tuple[tuple[Region, ...], tuple[Region, ...]]:
    """`_column_regions` of `words` without the drop capitals at the
    indices `set_aside`, each then placed in the line beside it. A capital
    with no line beside it is laid out again as a word of the body."""
    upper, band = _column_regions(
        tuple(word for index, word in enumerate(words) if index not in set_aside),
        left,
        measures,
    )
    regions = (*upper, *band)
    unplaced = set()
    for index in sorted(set_aside):
        placed = _with_drop_capital(regions, words[index])
        if placed is None:
            unplaced.add(index)
        else:
            regions = placed
    if unplaced:
        return _column_regions_with_drop_capitals(
            words, set_aside - unplaced, left, measures
        )
    return regions[: len(upper)], regions[len(upper) :]


@dataclass(frozen=True, slots=True, kw_only=True)
class _ColumnSplit:
    """A page's words after steps 1 and 2: the body column's left and
    right edges, in points, the margin words of each side, and the words
    left in the column."""

    left: float
    right: float
    left_margin: tuple[Word, ...]
    right_margin: tuple[Word, ...]
    column: tuple[Word, ...]


def _split_at_column(
    words: tuple[Word, ...], page_index: int, measures: BookMeasures
) -> _ColumnSplit:
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
    return _ColumnSplit(
        left=left,
        right=right,
        left_margin=(
            *outside_left,
            *(word for word in in_column if id(word) in reaching),
        ),
        right_margin=right_margin,
        column=tuple(word for word in in_column if id(word) not in reaching),
    )


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


class _Side(StrEnum):
    """The side of the body column a cut-in note stands at."""

    LEFT = "left"
    RIGHT = "right"


def _side_words(
    row: Line, side: _Side, index_of: dict[int, int]
) -> tuple[_SideWord, ...]:
    """The words of `row` seen from `side`, in the order of their
    start; `index_of` gives a word's place by its identity."""
    match side:
        case _Side.LEFT:
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
        case _Side.RIGHT:
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


def _cut_in_note_indices(
    column: tuple[Word, ...], side: _Side, edge: float, measures: BookMeasures
) -> frozenset[int]:
    """The places among `column`'s words of the words of the notes cut into
    the column at `side` (step 2b, rule 3): their middle in a cut-in zone,
    give or take `_CUT_IN_ZONE_PT`, and ending `_CUT_IN_STRIP_PT` or more
    short of the inset. `edge` is the column's edge on that side, seen from
    it as `_SideWord` sees it: the right edge negated. Empty when the book has
    no inset on that side."""
    match side:
        case _Side.LEFT:
            inset = measures.cut_in_inset_left
        case _Side.RIGHT:
            inset = measures.cut_in_inset_right
        case _:
            assert_never(side)
    if inset is None:
        return frozenset()
    index_of = {id(word): index for index, word in enumerate(column)}
    rows = tuple(_side_words(row, side, index_of) for row in group_rows(column))
    at = edge + inset
    zones = _cut_in_zones(
        rows, at, _CUT_ROW_SPAN_SHARE * measures.column_width, measures.body_line_pitch
    )
    in_zones = frozenset(
        word.index
        for row in rows
        for word in row
        if word.end <= at - _CUT_IN_STRIP_PT
        and any(
            top - _CUT_IN_ZONE_PT
            <= (word.top + word.bottom) / 2
            <= bottom + _CUT_IN_ZONE_PT
            for top, bottom in zones
        )
    )
    return frozenset(index for row in rows for index in _apart_from_body(row, in_zones))


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


def _page_regions(
    words: tuple[Word, ...], page_index: int, measures: BookMeasures
) -> tuple[Region, ...]:
    """The regions of a page of `words`, which are not empty, in reading
    order (layout spec section 3): the running-head region, the body's
    regions, the margin regions by their top, the left side first, and the
    band's regions."""
    pitch = measures.body_line_pitch
    split = _split_at_column(words, page_index, measures)
    left_cut_in = _cut_in_note_indices(split.column, _Side.LEFT, split.left, measures)
    right_cut_in = _cut_in_note_indices(
        split.column, _Side.RIGHT, -split.right, measures
    )
    column = tuple(
        word
        for index, word in enumerate(split.column)
        if index not in left_cut_in and index not in right_cut_in
    )
    upper, band = _column_regions_with_drop_capitals(
        column,
        frozenset(
            index
            for index, word in enumerate(column)
            if _is_drop_capital(word, split.left, measures)
        ),
        split.left,
        measures,
    )
    # The cut-in notes' words are grouped apart from the outer margin notes
    # of their side, and their regions placed among them by their top.
    margin_words = (
        (_Side.LEFT, split.left_margin),
        (_Side.LEFT, tuple(split.column[index] for index in sorted(left_cut_in))),
        (_Side.RIGHT, split.right_margin),
        (_Side.RIGHT, tuple(split.column[index] for index in sorted(right_cut_in))),
    )
    margins = sorted(
        (
            (side, region)
            for side, side_words in margin_words
            for region in _margin_regions(side_words, pitch)
        ),
        # By top, and at the same top the left side first.
        key=lambda side_region: (
            side_region[1].box.top,
            side_region[0] is _Side.RIGHT,
        ),
    )
    return (*upper, *(region for _, region in margins), *band)


def layout_page(page: PageWords, measures: BookMeasures | None) -> PageLayout:
    """The layout of one page: its regions in reading order, each its words
    grouped into lines, and its figures, copied from `page` (layout spec
    section 3). A page with no words has no region. With no `measures`,
    the page is one region holding the lines of all its words, as the
    walking skeleton laid it out."""
    if not page.words:
        return PageLayout(page.index, (), page.figures)
    regions = (
        (_region(group_rows(page.words)),)
        if measures is None
        else _page_regions(page.words, page.index, measures)
    )
    return PageLayout(page.index, regions, page.figures)


def run(
    folder: BookFolder, config: BookConfig, *, workers: int = DEFAULT_WORKERS
) -> None:
    """Reads pages.json and words.json from `folder`, measures the book and
    lays out every page in `workers` threads, and writes lines.json.

    lines.json and every later stage's file (blocks.json, book.md,
    book.epub) are deleted first. pages.json must have been made from
    `config.pdf` and words.json from the same PDF, or InputFileError names
    the stage to run again. When the words of lines.json are not those of
    words.json, FidelityError is raised and nothing is written.
    """
    delete_stage_outputs(folder, Stage.LAYOUT)
    _, words = read_checked_input(
        folder.pages_json, config.pdf, folder.words_json, read_words
    )
    measures = measure_book(words, workers=workers)
    if measures is None:
        _logger.info(
            "layout: no page has enough rows to measure the book; "
            "every page is laid out as one region"
        )
    else:
        _logger.info("layout: the book's measures, in points: %s", measures)

    def lay_out(page: PageWords) -> PageLayout:
        return layout_page(page, measures)

    lines = LinesFile(
        source_pdf_sha256=words.source_pdf_sha256,
        pages=map_pages(lay_out, words.pages, workers),
        # Nothing is re-read yet: the reocr spec's re-reading comes with
        # work package 5 of the plan clean-text.
        rereads=(),
    )
    check_stage(FidelityBoundary.LAYOUT, words, lines)
    write_lines(folder.lines_json, lines)
    _logger.info(
        "layout: %d pages, %d regions, %d lines written to %s",
        len(lines.pages),
        sum(len(page.regions) for page in lines.pages),
        sum(len(region.lines) for page in lines.pages for region in page.regions),
        folder.lines_json,
    )
