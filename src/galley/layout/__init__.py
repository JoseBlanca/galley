"""layout: each page's words grouped into regions and lines, in reading order.

The rules are those of docs/specs/layout.md. `measure_book` takes the
book's measures over all its pages: the width of the body column, the
height of a body word, the distance between rows, and the usual left edge
of the column. `group_lines` groups words into lines by the walking
skeleton's rule: a word joins the line of the word that started it, its
anchor, when the word's vertical centre lies within the anchor's top and
bottom. `layout_page` places the body column on the page, takes the
words outside it as margin regions, the first row set apart at the top as
the running-head region and the small rows at the foot as the footnote
band, cuts the body and the band into two columns where a gutter runs
down them, and puts a drop capital first in the line beside it. `run`
measures the book, then lays out its pages in parallel.
"""

import logging
import math
from bisect import bisect_left, bisect_right
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from itertools import groupby, pairwise
from statistics import median
from typing import Final, assert_never

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

__all__ = ["BookMeasures", "group_lines", "layout_page", "measure_book", "run"]

_logger = logging.getLogger(__name__)


def _enclosing_box(boxes: tuple[Box, ...]) -> Box:
    """The smallest box that holds every box of `boxes`, which is not empty."""
    return Box(
        min(box.x0 for box in boxes),
        min(box.top for box in boxes),
        max(box.x1 for box in boxes),
        max(box.bottom for box in boxes),
    )


def _line(words: tuple[Word, ...]) -> Line:
    """The line of `words`, sorted left to right by x0; equal x0 keep their order."""
    left_to_right = tuple(sorted(words, key=lambda word: word.box.x0))
    return Line(_enclosing_box(tuple(word.box for word in words)), left_to_right)


def group_lines(words: tuple[Word, ...]) -> tuple[Line, ...]:
    """The lines of `words`, top to bottom, each one's words left to right.

    The words are taken by (top, x0), equal keys in their given order. The
    first word starts a line and is its anchor; a later word joins the
    current line when its vertical centre, (top + bottom) / 2 in points,
    lies within the anchor's top and bottom, edges included, and otherwise
    starts the next line as its anchor. A line's box is the smallest box
    that holds its words. No words give no lines.
    """
    rows: list[list[Word]] = []
    anchor: Word | None = None
    for word in sorted(words, key=lambda word: (word.box.top, word.box.x0)):
        centre = (word.box.top + word.box.bottom) / 2
        if anchor is not None and anchor.box.top <= centre <= anchor.box.bottom:
            rows[-1].append(word)
        else:
            rows.append([word])
            anchor = word
    return tuple(_line(tuple(row)) for row in rows)


# The book's measures (layout spec section 3, "The book's measures").

# Guessed: enough rows on a page for a commonest edge.
_MEASURED_PAGE_ROWS: Final[int] = 15
# Guessed, not measured: a book with no page of 15 rows is measured on its
# pages of 3 rows, the fewest that give a pitch between two rows and a
# commonest edge of more than one.
_MEASURED_PAGE_ROWS_FALLBACK: Final[int] = 3
# Measured: body lines start within 2.2 pt of the edge on 99% of Haskins'
# lines.
_COMMONEST_EDGE_PT: Final[float] = 2.0
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
    0 for even pages, 1 for odd.
    """

    column_width: float
    body_word_height: float
    body_line_pitch: float
    usual_left_edge: frozendict[int, float]


def _commonest(edges: Iterable[float]) -> float | None:
    """The commonest value of `edges`, in points: each edge rounded to the
    point, the value with the most edges within `_COMMONEST_EDGE_PT` of it,
    the smallest on a tie. None for no edges."""
    rounded = sorted(float(round(edge)) for edge in edges)
    if not rounded:
        return None
    return min(
        dict.fromkeys(rounded),
        key=lambda value: (
            -(
                bisect_right(rounded, value + _COMMONEST_EDGE_PT)
                - bisect_left(rounded, value - _COMMONEST_EDGE_PT)
            ),
            value,
        ),
    )


def _row_word_height(row: Line) -> float:
    """The median height of the words of `row`, in points."""
    return median(word.box.bottom - word.box.top for word in row.words)


def _edge_counts(edges: Iterable[float]) -> dict[float, int]:
    """Each value of `edges`, rounded to the point, with the number of
    edges within `_COMMONEST_EDGE_PT` of it."""
    rounded = sorted(float(round(edge)) for edge in edges)
    return {
        value: bisect_right(rounded, value + _COMMONEST_EDGE_PT)
        - bisect_left(rounded, value - _COMMONEST_EDGE_PT)
        for value in dict.fromkeys(rounded)
    }


def _common_edges(edges: Iterable[float]) -> tuple[float, ...]:
    """The common edges of `edges` (layout spec section 3, step 1): the
    commonest value, then the commonest of the values apart from every
    edge found, and so on, while a value has `_COMMON_EDGE_SHARE` of the
    first one's count."""
    by_count = sorted(
        _edge_counts(edges).items(),
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
    edge = _commonest(row.box.x0 for row in rows)
    assert edge is not None, "rows is not empty"
    return edge


def _column_width_of_page(rows: tuple[Line, ...]) -> float:
    """The commonest right side of `rows` minus their commonest left side;
    `rows` is not empty."""
    right = _commonest(row.box.x1 for row in rows)
    assert right is not None, "rows is not empty"
    return right - _commonest_left_edge(rows)


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
    out as one region each. The rows of each page are grouped in `workers`
    threads; the result does not depend on their number."""

    def page_rows(page: PageWords) -> tuple[Line, ...]:
        return group_lines(page.words)

    rows_by_page = map_pages(page_rows, words.pages, workers)
    measured = tuple(
        rows for rows in rows_by_page if len(rows) >= _MEASURED_PAGE_ROWS
    ) or tuple(
        rows for rows in rows_by_page if len(rows) >= _MEASURED_PAGE_ROWS_FALLBACK
    )
    if not measured:
        return None
    column_width = median(_column_width_of_page(rows) for rows in measured)
    return BookMeasures(
        column_width=column_width,
        body_word_height=median(
            _row_word_height(row) for rows in measured for row in rows
        ),
        body_line_pitch=median(
            below.box.top - above.box.top
            for rows in measured
            for above, below in pairwise(rows)
        ),
        usual_left_edge=_usual_left_edges(
            words.pages, rows_by_page, measured, column_width
        ),
    )


# Laying out a page (layout spec section 3, "Per page").

# Measured: a word that crosses the column's edge is a body word; a word 2
# pt outside it took 64 of Domesday's 181,400 body words and 11 of Haskins'
# 60,900 into a margin.
_MARGIN_WORD_PT: Final[float] = 2.0
# Measured on the six whole books on 15 November 2026: a word whose middle
# lies 2 pt left of the left edge, whose row's next word starts a pitch
# inside the edge, beside a margin word of 2 letters, is a margin note's
# word in 23 of 23 checked (176 such words in Domesday, 96 in Gierke, none
# in the other four). With 1 letter, a list number hung outside the column
# counted as a note (Gierke page 62).
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
    return _region(group_lines(_words_of(rows)))


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


def _reaches_from_left_margin(
    row: Line, left: float, left_margin: tuple[Word, ...], pitch: float
) -> bool:
    """Whether the first word of `row`, a row of the column's words, is a
    margin note's word whose box runs on into the column (step 2): it
    holds a letter or a digit, its middle lies `_MARGIN_WORD_PT` or more
    left of `left`, the row's second word starts `pitch` or more right of
    `left` (or there is none), and a word of `left_margin` with
    `_MARGIN_NOTE_LETTERS` letters lies within `pitch` above or below it."""
    first, *rest = sorted(row.words, key=lambda word: word.box.x0)
    return (
        any(char.isalnum() for char in first.text)
        and (first.box.x0 + first.box.x1) / 2 <= left - _MARGIN_WORD_PT
        and (not rest or rest[0].box.x0 - left >= pitch)
        and any(
            sum(char.isalpha() for char in word.text) >= _MARGIN_NOTE_LETTERS
            and word.box.top < first.box.bottom + pitch
            and word.box.bottom > first.box.top - pitch
            for word in left_margin
        )
    )


def _margin_regions(words: tuple[Word, ...], pitch: float) -> tuple[Region, ...]:
    """The margin regions of the margin words of one side of a page (step
    2): their lines, cut where a line's top is more than
    `_MARGIN_REGION_GAP_PITCHES` times `pitch` below the top of the line
    before."""
    groups: list[list[Line]] = []
    for line in group_lines(words):
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
        _row_word_height(row) <= _SMALL_ROW_SHARE * measures.body_word_height
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
            group_lines(
                tuple(
                    word for word in words if (word.box.x0 + word.box.x1) / 2 < middle
                )
            )
        ),
        _region(
            group_lines(
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
    rows = group_lines(words)
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


def _page_regions(
    words: tuple[Word, ...], page_index: int, measures: BookMeasures
) -> tuple[Region, ...]:
    """The regions of a page of `words`, which are not empty, in reading
    order (layout spec section 3): the running-head region, the body's
    regions, the margin regions by their top, the left side first, and the
    band's regions."""
    pitch = measures.body_line_pitch
    left, right = _column_edges(group_lines(words), page_index, measures)
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
        id(min(row.words, key=lambda word: word.box.x0))
        for row in group_lines(in_column)
        if _reaches_from_left_margin(row, left, outside_left, pitch)
    }
    left_margin = (
        *outside_left,
        *(word for word in in_column if id(word) in reaching),
    )
    column = tuple(word for word in in_column if id(word) not in reaching)
    upper, band = _column_regions_with_drop_capitals(
        column,
        frozenset(
            index
            for index, word in enumerate(column)
            if _is_drop_capital(word, left, measures)
        ),
        left,
        measures,
    )
    margins = sorted(
        (
            *((0, region) for region in _margin_regions(left_margin, pitch)),
            *((1, region) for region in _margin_regions(right_margin, pitch)),
        ),
        key=lambda side_region: (side_region[1].box.top, side_region[0]),
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
        (_region(group_lines(page.words)),)
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
            "layout: no page has %d rows; every page is laid out as one region",
            _MEASURED_PAGE_ROWS_FALLBACK,
        )
    else:
        _logger.info("layout: the book's measures, in points: %s", measures)

    def lay_out(page: PageWords) -> PageLayout:
        return layout_page(page, measures)

    lines = LinesFile(
        source_pdf_sha256=words.source_pdf_sha256,
        pages=map_pages(lay_out, words.pages, workers),
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
