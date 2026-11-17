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
and puts a drop capital first in the line beside it.
`layout_page_with_rereads` does the same and re-reads the page's small
print with Tesseract where it reads better than the text layer
(docs/specs/reocr.md): a page printed wholly in small type, the note
bands of the outer margins, the crops of the cut-in notes and, when the
config asks, the footnote band; the steps they share with the laying out
are in `_column`, the crops and choices in `_reread`. `run` measures the
book, then lays out its pages in parallel, re-reading unless the config's
`ocr` is `trust` or `redo`.
"""

import bisect
import logging
import math
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace
from enum import StrEnum
from itertools import groupby
from pathlib import Path
from statistics import median
from typing import Final, Protocol, assert_never

from PIL import Image

from galley import pdfium, wordlist
from galley.body_measures import (
    body_measures,
    commonest,
    group_rows,
    measured_page_positions,
    measured_pages,
)
from galley.book_folder import BookFolder, Stage, delete_stage_outputs
from galley.config import BookConfig, OcrMode, tesseract_language
from galley.errors import FidelityBoundary
from galley.fidelity import check_stage
from galley.layout._column import (
    BookMeasures,
    ColumnSplit,
    Side,
    is_small_row,
    running_head_row_count,
    split_at_column,
    wide_rows_edges,
    without_cut_in_notes,
)
from galley.layout._reread import (
    NOTE_PSM,
    SMALL_PRINT_PSM,
    RegionReading,
    cut_in_crops,
    cut_in_reading,
    footnote_band_crop,
    footnote_band_reading,
    is_small_print_page,
    margin_note_reading,
    margin_note_sides,
    margin_strip,
    note_bands,
    page_rereads,
    pixel_box,
    reading_score,
    small_print_crop,
    small_print_reading,
)
from galley.model import (
    Box,
    Line,
    LinesFile,
    PageKind,
    PageLayout,
    PageWords,
    Region,
    Reread,
    RereadKind,
    TextSource,
    Word,
    WordsFile,
    read_checked_input,
    read_words,
    words_after_rereads,
    write_lines,
)
from galley.ocr import OCR_DPI, point_box, read_image_lines
from galley.parallel import DEFAULT_WORKERS, map_pages
from galley.pdfium import POINTS_PER_INCH

__all__ = [
    "BookMeasures",
    "ReadLines",
    "Rereading",
    "Side",
    "is_small_print_page",
    "layout_page",
    "layout_page_with_rereads",
    "measure_book",
    "note_bands",
    "reading_score",
    "run",
]

_logger = logging.getLogger(__name__)


def _enclosing_box(boxes: tuple[Box, ...]) -> Box:
    """The smallest box that holds every box of `boxes`, which is not empty."""
    return Box(
        min(box.x0 for box in boxes),
        min(box.top for box in boxes),
        max(box.x1 for box in boxes),
        max(box.bottom for box in boxes),
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
        if (edges := wide_rows_edges(rows, column_width)) is not None
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
        return _row_insets(split_at_column(page.words, page.index, without_insets))

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


def _row_insets(split: ColumnSplit) -> tuple[tuple[int, ...], tuple[int, ...]]:
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

# Guessed, so that each printed margin note is a region of its own.
_MARGIN_REGION_GAP_PITCHES: Final[float] = 1.5


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
    small = tuple(is_small_row(row, measures) for row in rows)
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
    words: tuple[Word, ...],
    left: float,
    measures: BookMeasures,
    band: tuple[Word, ...] | None,
) -> tuple[tuple[Region, ...], tuple[Region, ...]]:
    """The regions of the body column's `words`, a drop capital set aside:
    the running-head region and the body's regions, then the band's (steps
    3 to 5 and 7). With `band`, the words of a footnote band re-read with
    Tesseract, step 4 does not look for the band in `words`: `band` is
    the band, and the rows of `words` below the running head the body."""
    rows = group_rows(words)
    head_count = running_head_row_count(rows, measures.body_line_pitch)
    head, rest = rows[:head_count], rows[head_count:]
    if band is None:
        band_start = _band_start(rest, measures)
        body_rows, band_rows = rest[:band_start], rest[band_start:]
    else:
        body_rows, band_rows = rest, group_rows(band)
    width = measures.column_width
    return (
        (
            *((_region_of_rows(head),) if head else ()),
            *_column_cut_regions(body_rows, left, width, _Part.BODY),
        ),
        _column_cut_regions(band_rows, left, width, _Part.BAND),
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
    band: tuple[Word, ...] | None,
) -> tuple[tuple[Region, ...], tuple[Region, ...]]:
    """`_column_regions` of `words` and `band` without the drop capitals at
    the indices `set_aside` of `words`, each then placed in the line beside
    it. A capital with no line beside it is laid out again as a word of the
    body."""
    upper, band_regions = _column_regions(
        tuple(word for index, word in enumerate(words) if index not in set_aside),
        left,
        measures,
        band,
    )
    regions = (*upper, *band_regions)
    unplaced = set()
    for index in sorted(set_aside):
        placed = _with_drop_capital(regions, words[index])
        if placed is None:
            unplaced.add(index)
        else:
            regions = placed
    if unplaced:
        return _column_regions_with_drop_capitals(
            words, set_aside - unplaced, left, measures, band
        )
    return regions[: len(upper)], regions[len(upper) :]


@dataclass(frozen=True, slots=True, kw_only=True)
class _PageParts:
    """A page's words as steps 1, 2 and 2b place them, in points: the body
    column's `left` and `right` edges; each side's outer margin words and
    cut-in words; `column`, the words left in the column, which steps 3 to
    7 lay out; each side's cut-in zones, (top, bottom); and `band`, the
    words of a footnote band re-read with Tesseract, or None when step 4
    finds the band among `column`."""

    left: float
    right: float
    left_margin: tuple[Word, ...]
    right_margin: tuple[Word, ...]
    left_cut_in: tuple[Word, ...]
    right_cut_in: tuple[Word, ...]
    column: tuple[Word, ...]
    left_zones: tuple[tuple[float, float], ...]
    right_zones: tuple[tuple[float, float], ...]
    band: tuple[Word, ...] | None


def _page_parts(
    words: tuple[Word, ...], page_index: int, measures: BookMeasures
) -> _PageParts:
    """The parts of a page of `words` (steps 1, 2 and 2b)."""
    split = split_at_column(words, page_index, measures)
    column_words = without_cut_in_notes(split, measures)
    return _PageParts(
        left=split.left,
        right=split.right,
        left_margin=split.left_margin,
        right_margin=split.right_margin,
        left_cut_in=column_words.left_cut_in,
        right_cut_in=column_words.right_cut_in,
        column=column_words.column,
        left_zones=column_words.left_zones,
        right_zones=column_words.right_zones,
        band=None,
    )


def _regions_of_parts(parts: _PageParts, measures: BookMeasures) -> tuple[Region, ...]:
    """The regions of a page whose words are placed as `parts`, in reading
    order (layout spec section 3): the running-head region, the body's
    regions, the margin regions by their top, the left side first, and the
    band's regions."""
    pitch = measures.body_line_pitch
    upper, band = _column_regions_with_drop_capitals(
        parts.column,
        frozenset(
            index
            for index, word in enumerate(parts.column)
            if _is_drop_capital(word, parts.left, measures)
        ),
        parts.left,
        measures,
        parts.band,
    )
    # The cut-in notes' words are grouped apart from the outer margin notes
    # of their side, and their regions placed among them by their top.
    margin_words = (
        (Side.LEFT, parts.left_margin),
        (Side.LEFT, parts.left_cut_in),
        (Side.RIGHT, parts.right_margin),
        (Side.RIGHT, parts.right_cut_in),
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
            side_region[0] is Side.RIGHT,
        ),
    )
    return (*upper, *(region for _, region in margins), *band)


def _page_regions(
    words: tuple[Word, ...], page_index: int, measures: BookMeasures
) -> tuple[Region, ...]:
    """The regions of a page of `words`, which are not empty, in reading
    order (layout spec section 3)."""
    return _regions_of_parts(_page_parts(words, page_index, measures), measures)


def layout_page(page: PageWords, measures: BookMeasures | None) -> PageLayout:
    """The layout of one page: its regions in reading order, each its words
    grouped into lines, and its figures, copied from `page` (layout spec
    section 3). A page with no words has no region. With no `measures`,
    the page is one region holding the lines of all its words, as the
    walking skeleton laid it out. Nothing is re-read
    (`layout_page_with_rereads` re-reads)."""
    if not page.words:
        return PageLayout(page.index, (), page.figures)
    regions = (
        (_region(group_rows(page.words)),)
        if measures is None
        else _page_regions(page.words, page.index, measures)
    )
    return PageLayout(page.index, regions, page.figures)


# Re-reading small print (docs/specs/reocr.md, sections 3 and 4).


class ReadLines(Protocol):
    """Tesseract run on an image: its words grouped by its lines, with
    boxes in points on the page, as `ocr.read_image_lines` gives them."""

    def __call__(
        self, image: Image.Image, *, origin: tuple[float, float], psm: int
    ) -> tuple[tuple[Word, ...], ...]:
        """The words of `image`, a crop of a page rendered at `OCR_DPI`
        whose top left lies at `origin`, (left, top) in points on the page,
        read with page segmentation mode `psm`."""
        ...


@dataclass(frozen=True, slots=True, kw_only=True)
class Rereading:
    """What layout needs to re-read a page's small print with Tesseract
    (reocr spec, sections 3, 4 and 6).

    `render` gives the page of a page index rendered whole at `OCR_DPI`, a
    grayscale Pillow image; `read_lines` runs Tesseract on a crop of it.
    `lower_case_words` is the word list of the book's language in lower
    case, for the reading scores. `margin_note_sides` are the sides of the
    book whose outer margins hold notes (`margin_note_sides` of the book's
    pages), and `footnote_bands` whether each page's footnote band is read
    too (the config's `reread_footnotes`).
    """

    render: Callable[[int], Image.Image]
    read_lines: ReadLines
    lower_case_words: frozenset[str]
    margin_note_sides: frozenset[Side]
    footnote_bands: bool


def _words_of_lines(lines: tuple[tuple[Word, ...], ...]) -> tuple[Word, ...]:
    return tuple(word for line in lines for word in line)


def _read_crop(
    image: Image.Image, pixels: tuple[int, int, int, int], psm: int, read: ReadLines
) -> tuple[tuple[Word, ...], ...]:
    """Tesseract's lines of the crop `pixels` of `image`, a page rendered at
    `OCR_DPI`, cut to the image's edges; no line when nothing is left of
    the crop."""
    width, height = image.size
    left, top = max(0, pixels[0]), max(0, pixels[1])
    right, bottom = min(width, pixels[2]), min(height, pixels[3])
    if right <= left or bottom <= top:
        return ()
    scale = POINTS_PER_INCH / OCR_DPI
    return read(
        image.crop((left, top, right, bottom)),
        origin=(left * scale, top * scale),
        psm=psm,
    )


def _head_words(column: tuple[Word, ...], measures: BookMeasures) -> tuple[Word, ...]:
    """The words of the running-head region of a column of `column`'s words
    (step 3)."""
    rows = group_rows(column)
    head_count = running_head_row_count(rows, measures.body_line_pitch)
    return _words_of(rows[:head_count])


def _layer_band_words(parts: _PageParts, measures: BookMeasures) -> tuple[Word, ...]:
    """The words of the footnote band that step 4 finds among the column's
    words of `parts`, in the order of its rows."""
    _, band = _column_regions_with_drop_capitals(
        parts.column,
        frozenset(
            index
            for index, word in enumerate(parts.column)
            if _is_drop_capital(word, parts.left, measures)
        ),
        parts.left,
        measures,
        None,
    )
    return tuple(word for region in band for word in _words_of(region.lines))


def _margin_readings(
    page: PageWords,
    parts: _PageParts,
    image: Image.Image,
    rereading: Rereading,
) -> tuple[RegionReading, ...]:
    """The note bands of the outer margins of `page` on the book's sides
    with margin notes, each read (reocr spec, section 3, kind 2)."""
    column = (*parts.column, *parts.left_cut_in, *parts.right_cut_in)
    if not column:
        return ()
    page_width = image.size[0] * POINTS_PER_INCH / OCR_DPI
    readings = []
    for side in sorted(rereading.margin_note_sides):
        strip = margin_strip(
            side,
            left=parts.left,
            right=parts.right,
            column_top=min(word.box.top for word in column),
            lowest=max(word.box.bottom for word in page.words),
            page_width=page_width,
        )
        strip_pixels = pixel_box(strip, OCR_DPI)
        width, height = image.size
        strip_left, strip_top = max(0, strip_pixels[0]), max(0, strip_pixels[1])
        strip_right = min(width, strip_pixels[2])
        strip_bottom = min(height, strip_pixels[3])
        if strip_right <= strip_left or strip_bottom <= strip_top:
            continue
        strip_image = image.crop((strip_left, strip_top, strip_right, strip_bottom))
        for band in note_bands(strip_image, dpi=OCR_DPI):
            band_pixels = (
                strip_left + band[0],
                strip_top + band[1],
                strip_left + band[2],
                strip_top + band[3],
            )
            readings.append(
                margin_note_reading(
                    side,
                    point_box(band_pixels, origin=(0.0, 0.0), dpi=OCR_DPI),
                    _words_of_lines(
                        _read_crop(image, band_pixels, NOTE_PSM, rereading.read_lines)
                    ),
                    page_words=page.words,
                )
            )
    return tuple(readings)


def _cut_in_readings(
    parts: _PageParts,
    measures: BookMeasures,
    image: Image.Image,
    rereading: Rereading,
    head_bottom: float | None,
) -> tuple[RegionReading, ...]:
    """The crops of the notes cut into the column of a page placed as
    `parts`, each read (reocr spec, section 3, kind 3)."""
    readings = []
    for side, zones, edge, inset, cut_in_words in (
        (
            Side.LEFT,
            parts.left_zones,
            parts.left,
            measures.cut_in_inset_left,
            parts.left_cut_in,
        ),
        (
            Side.RIGHT,
            parts.right_zones,
            parts.right,
            measures.cut_in_inset_right,
            parts.right_cut_in,
        ),
    ):
        if inset is None or not zones:
            continue
        for crop in cut_in_crops(
            zones,
            side,
            edge=edge,
            inset=inset,
            pitch=measures.body_line_pitch,
            head_bottom=head_bottom,
        ):
            readings.append(
                cut_in_reading(
                    side,
                    crop,
                    _read_crop(
                        image,
                        pixel_box(crop.box, OCR_DPI),
                        NOTE_PSM,
                        rereading.read_lines,
                    ),
                    edge=edge,
                    inset=inset,
                    cut_in_words=cut_in_words,
                    column_words=parts.column,
                )
            )
    return tuple(readings)


def _page_readings(
    page: PageWords,
    parts: _PageParts,
    measures: BookMeasures,
    rereading: Rereading,
) -> tuple[RegionReading, ...]:
    """The regions of `page` read with Tesseract (reocr spec, sections 3
    and 4): the whole page below its running head when it is a small-print
    page, and then no other region; else the note bands of its outer
    margins, the crops of its cut-in notes and, when `rereading` asks, its
    footnote band. The page is rendered once, and only when it has a
    region to read."""
    head = _head_words(parts.column, measures)
    head_bottom = max((word.box.bottom for word in head), default=None)
    small_print = is_small_print_page(page, measures)
    band = (
        _layer_band_words(parts, measures)
        if rereading.footnote_bands and not small_print
        else ()
    )
    if not (
        small_print
        or rereading.margin_note_sides
        or parts.left_zones
        or parts.right_zones
        or band
    ):
        return ()
    image = rereading.render(page.index)
    width_pt, height_pt = (size * POINTS_PER_INCH / OCR_DPI for size in image.size)
    if small_print:
        crop = small_print_crop(
            page_width=width_pt, page_height=height_pt, head_bottom=head_bottom
        )
        return (
            small_print_reading(
                crop,
                _words_of_lines(
                    _read_crop(
                        image,
                        pixel_box(crop, OCR_DPI),
                        SMALL_PRINT_PSM,
                        rereading.read_lines,
                    )
                ),
                page_words=page.words,
                head_words=head,
            ),
        )
    footnote = ()
    if band:
        crop = footnote_band_crop(band, left=parts.left, right=parts.right)
        footnote = (
            footnote_band_reading(
                crop,
                _words_of_lines(
                    _read_crop(
                        image, pixel_box(crop, OCR_DPI), NOTE_PSM, rereading.read_lines
                    )
                ),
                band_words=band,
            ),
        )
    return (
        *_margin_readings(page, parts, image, rereading),
        *_cut_in_readings(parts, measures, image, rereading, head_bottom),
        *footnote,
    )


def _take_out(
    groups: tuple[tuple[Word, ...], ...], taken: Iterable[Word]
) -> tuple[tuple[Word, ...], ...]:
    """`groups` of a page's words less the words of `taken`, each taken out
    once, from the first group that holds it."""
    left = Counter(taken)
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


def _side_of(record: Reread, parts: _PageParts) -> Side:
    """The side of the column a margin note band or a cut-in crop lies at:
    that of its crop's middle."""
    middle = (record.box.x0 + record.box.x1) / 2
    return Side.LEFT if middle < (parts.left + parts.right) / 2 else Side.RIGHT


def _ocr_words_of(
    kept: tuple[Reread, ...], kind: RereadKind, side: Side | None, parts: _PageParts
) -> tuple[Word, ...]:
    return tuple(
        word
        for record in kept
        if record.kind is kind and (side is None or _side_of(record, parts) is side)
        for word in record.ocr_words
    )


def _parts_after_rereads(
    parts: _PageParts, kept: tuple[Reread, ...], measures: BookMeasures
) -> _PageParts:
    """The parts of a page with the kept records `kept` of its regions read
    again (reocr spec, section 4): each record's layer words taken out of
    the part that holds them, and its Tesseract words put into the part of
    its kind, the side's margin words, the side's cut-in words or the
    band, which the later steps lay out as they lay out the layer's."""
    band_read = _ocr_words_of(kept, RereadKind.FOOTNOTE_BAND, None, parts)
    layer_band = (
        _layer_band_words(parts, measures)
        if any(record.kind is RereadKind.FOOTNOTE_BAND for record in kept)
        else ()
    )
    (column,) = _take_out((parts.column,), layer_band)
    left_margin, right_margin, left_cut_in, right_cut_in, column, band = _take_out(
        (
            parts.left_margin,
            parts.right_margin,
            parts.left_cut_in,
            parts.right_cut_in,
            column,
            layer_band,
        ),
        (word for record in kept for word in record.layer_words),
    )
    return replace(
        parts,
        left_margin=(
            *left_margin,
            *_ocr_words_of(kept, RereadKind.MARGIN_NOTE, Side.LEFT, parts),
        ),
        right_margin=(
            *right_margin,
            *_ocr_words_of(kept, RereadKind.MARGIN_NOTE, Side.RIGHT, parts),
        ),
        left_cut_in=(
            *left_cut_in,
            *_ocr_words_of(kept, RereadKind.CUT_IN_NOTE, Side.LEFT, parts),
        ),
        right_cut_in=(
            *right_cut_in,
            *_ocr_words_of(kept, RereadKind.CUT_IN_NOTE, Side.RIGHT, parts),
        ),
        column=column,
        band=(*band, *band_read) if layer_band else None,
    )


def layout_page_with_rereads(
    page: PageWords, measures: BookMeasures | None, rereading: Rereading | None
) -> tuple[PageLayout, tuple[Reread, ...]]:
    """The layout of one page, as `layout_page` gives it, with its small
    print re-read with Tesseract (reocr spec, sections 3 and 4), and the
    records of the regions read, in their order.

    Nothing is read, and the layout is `layout_page`'s, when `rereading`
    or `measures` is None, or the page's words are not the text layer's.
    Each region is found on the layer's words, read, and kept or not by
    `page_rereads`. A small-print page whose reading is kept is laid out
    from its words after the record (`model.words_after_rereads`), by
    steps 1 to 7; on another page, each kept region's Tesseract words go
    into the part the replaced words were in, and the later steps lay
    them out.
    """
    if (
        rereading is None
        or measures is None
        or not page.words
        or page.text_source is not TextSource.TEXT_LAYER
    ):
        return layout_page(page, measures), ()
    parts = _page_parts(page.words, page.index, measures)
    records = page_rereads(
        page.index,
        _page_readings(page, parts, measures, rereading),
        rereading.lower_case_words,
    )
    kept = tuple(record for record in records if record.kept)
    if not kept:
        return layout_page(page, measures), records
    if kept[0].kind is RereadKind.SMALL_PRINT_PAGE:
        regions = _page_regions(
            words_after_rereads(page.words, kept), page.index, measures
        )
    else:
        regions = _regions_of_parts(
            _parts_after_rereads(parts, kept, measures), measures
        )
    return PageLayout(page.index, regions, page.figures), records


def _rendered_image(pdf: Path, page_index: int) -> Image.Image:
    """Page `page_index` of `pdf` rendered at `OCR_DPI` by the PDFium
    thread, as a grayscale Pillow image."""
    rendered = pdfium.render(pdf, page_index, OCR_DPI)
    return Image.frombytes(
        "L", (rendered.width_px, rendered.height_px), rendered.pixels
    )


def _rereading(
    config: BookConfig,
    words: WordsFile,
    measures: BookMeasures | None,
    workers: int,
) -> Rereading | None:
    """What layout needs to re-read the small print of the book of `words`;
    None when the config's `ocr` is not `verify` (reocr spec, section 3) or
    the book has no measures."""
    if config.ocr is not OcrMode.VERIFY or measures is None:
        return None
    lower_case_words = wordlist.lower_case_word_list(
        config.language, wordlist.DEFAULT_CACHE_DIR
    )
    language = tesseract_language(config.language)

    def split(page: PageWords) -> tuple[int, ColumnSplit]:
        return len(page.words), split_at_column(page.words, page.index, measures)

    def render(page_index: int) -> Image.Image:
        return _rendered_image(config.pdf, page_index)

    def read_lines(
        image: Image.Image, *, origin: tuple[float, float], psm: int
    ) -> tuple[tuple[Word, ...], ...]:
        return read_image_lines(
            image, origin=origin, dpi=OCR_DPI, psm=psm, language=language
        )

    return Rereading(
        render=render,
        read_lines=read_lines,
        lower_case_words=lower_case_words,
        margin_note_sides=margin_note_sides(
            map_pages(
                split, tuple(page for page in words.pages if page.words), workers
            ),
            lower_case_words,
        ),
        footnote_bands=config.reread_footnotes,
    )


def run(
    folder: BookFolder, config: BookConfig, *, workers: int = DEFAULT_WORKERS
) -> None:
    """Reads pages.json and words.json from `folder`, measures the book,
    lays out every page in `workers` threads, re-reading its small print
    with Tesseract unless the config's `ocr` is `trust` or `redo`, and
    writes lines.json with the records of the regions read.

    Only text pages whose words are the text layer's are re-read (reocr
    spec, section 3); a render is made in the one PDFium thread, and
    Tesseract runs in the worker threads. lines.json and every later
    stage's file (blocks.json, book.md, book.epub) are deleted first.
    pages.json must have been made from `config.pdf` and words.json from
    the same PDF, or InputFileError names the stage to run again. When the
    words of lines.json are not those of words.json after the kept
    records, FidelityError is raised and nothing is written.
    """
    delete_stage_outputs(folder, Stage.LAYOUT)
    pages, words = read_checked_input(
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
    rereading = _rereading(config, words, measures, workers)
    if rereading is not None:
        _logger.info(
            "layout: re-reading small print; outer margin notes on the sides %s",
            ", ".join(sorted(rereading.margin_note_sides)) or "none",
        )
    readable = frozenset(
        page.index
        for page in pages.pages
        if page.kind is PageKind.TEXT and page.text_source is TextSource.TEXT_LAYER
    )

    def lay_out(page: PageWords) -> tuple[PageLayout, tuple[Reread, ...]]:
        return layout_page_with_rereads(
            page, measures, rereading if page.index in readable else None
        )

    laid_out = map_pages(lay_out, words.pages, workers)
    lines = LinesFile(
        source_pdf_sha256=words.source_pdf_sha256,
        pages=tuple(page for page, _ in laid_out),
        rereads=tuple(record for _, records in laid_out for record in records),
    )
    check_stage(FidelityBoundary.LAYOUT, words, lines)
    write_lines(folder.lines_json, lines)
    _logger.info(
        "layout: %d pages, %d regions, %d lines written to %s; "
        "%d regions re-read, %d of them kept",
        len(lines.pages),
        sum(len(page.regions) for page in lines.pages),
        sum(len(region.lines) for page in lines.pages for region in page.regions),
        folder.lines_json,
        len(lines.rereads),
        sum(record.kept for record in lines.rereads),
    )
