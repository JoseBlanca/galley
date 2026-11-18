"""The laying out of one page from its words (docs/specs/layout.md,
section 3, "Per page"): the body column, the margin regions, the running
head, the footnote band, the cut at a gutter and the drop capital, which
layout_page gives and the re-reading of small print (`_rereading`) shares.
Positions are PDF points from the page's top left.
"""

import math
import re
from dataclasses import dataclass
from enum import StrEnum
from itertools import groupby
from typing import Final, assert_never

from galley.body_measures import (
    group_rows,
)
from galley.layout._column import (
    BookMeasures,
    Side,
    has_letter_or_digit,
    is_small_row,
    running_head_row_count,
    split_at_column,
    without_cut_in_notes,
)
from galley.model import (
    Box,
    Line,
    PageLayout,
    PageWords,
    Region,
    Word,
)

# Laying out a page (layout spec section 3, "Per page").


def _enclosing_box(boxes: tuple[Box, ...]) -> Box:
    """The smallest box that holds every box of `boxes`, which is not empty."""
    return Box(
        min(box.x0 for box in boxes),
        min(box.top for box in boxes),
        max(box.x1 for box in boxes),
        max(box.bottom for box in boxes),
    )


# Guessed, so that each printed margin note is a region of its own.
_MARGIN_REGION_GAP_PITCHES: Final[float] = 1.5


def _region(lines: tuple[Line, ...]) -> Region:
    """The region of `lines`, which are not empty, with the smallest box
    that holds them."""
    return Region(_enclosing_box(tuple(line.box for line in lines)), lines)


def words_of(rows: tuple[Line, ...]) -> tuple[Word, ...]:
    return tuple(word for row in rows for word in row.words)


def _region_of_rows(rows: tuple[Line, ...]) -> Region:
    """The region of the words of `rows`, which are not empty, grouped
    into lines again (step 7)."""
    return _region(group_rows(words_of(rows)))


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
# Measured on 17 November 2026 on the whole books' words.json (layout spec
# section 3, step 4): a small row that opens with a note marker, 1 to 3
# digits or 1 or 2 signs and a word with a capital, starts the band without
# the gap, as Haskins' note on page 28, 1.06 pitches below the text; it
# starts the band on 23 pages of the eight books (Haskins 5, Domesday 14,
# Kadesh 3, Haynes 1), none in Stubbs, Mariéjol, Gierke or Turney.
_NOTE_MARKER = re.compile(r"[0-9]{1,3}\.?|[*^•†‡§]{1,2}")
_MARKER_ROW_WORDS = 2
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


def _opens_with_note_marker(row: Line) -> bool:
    """Whether `row` opens with a note marker (step 4): its first word is 1
    to 3 digits with an optional "." or 1 or 2 of the signs `* ^ • † ‡ §`,
    and its second word starts with a capital letter."""
    words = sorted(row.words, key=lambda word: word.box.x0)
    return (
        len(words) >= _MARKER_ROW_WORDS
        and _NOTE_MARKER.fullmatch(words[0].text) is not None
        and words[1].text[:1].isupper()
    )


def _after_small_row(
    rows: tuple[Line, ...], small: tuple[bool, ...], index: int
) -> bool:
    """Whether the nearest row above `rows[index]` that holds a letter or a
    digit is small, `small` saying which rows are (step 4); a row of marks
    above it, a speck, is passed over."""
    return next(
        (
            small[before]
            for before in range(index - 1, -1, -1)
            if has_letter_or_digit(rows[before])
        ),
        False,
    )


def _band_start(rows: tuple[Line, ...], measures: BookMeasures) -> int:
    """The index in `rows` of the first row of the footnote band (step 4),
    or len(rows) when there is no band: the first small row, not the
    first of `rows`, from which on two thirds of the rows are small, and
    which lies `_BAND_GAP_PITCHES` below the row before or opens with a
    note marker below a row that is not small (`_after_small_row`)."""
    small = tuple(is_small_row(row, measures) for row in rows)
    if all(small):
        return len(rows)
    return next(
        (
            index
            for index in range(1, len(rows))
            if small[index]
            and sum(small[index:]) >= _BAND_SMALL_ROWS_SHARE * (len(rows) - index)
            and (
                rows[index].box.top - rows[index - 1].box.top
                >= _BAND_GAP_PITCHES * measures.body_line_pitch
                or (
                    not _after_small_row(rows, small, index)
                    and _opens_with_note_marker(rows[index])
                )
            )
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
    words = words_of(rows)
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


def _head_region(rows: tuple[Line, ...]) -> Region:
    """The running-head region of its `rows` (step 3): each row above the
    head row a line of its own, and the head row with the rows of its
    skew below it one line, its words left to right."""
    head_row = next(index for index, row in enumerate(rows) if has_letter_or_digit(row))
    words = sorted(words_of(rows[head_row:]), key=lambda word: word.box.x0)
    head_line = Line(_enclosing_box(tuple(word.box for word in words)), tuple(words))
    return _region((*rows[:head_row], head_line))


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
            *((_head_region(head),) if head else ()),
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


def column_regions_with_drop_capitals(
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
        return column_regions_with_drop_capitals(
            words, set_aside - unplaced, left, measures, band
        )
    return regions[: len(upper)], regions[len(upper) :]


@dataclass(frozen=True, slots=True, kw_only=True)
class PageParts:
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


def page_parts(
    words: tuple[Word, ...], page_index: int, measures: BookMeasures
) -> PageParts:
    """The parts of a page of `words` (steps 1, 2 and 2b)."""
    split = split_at_column(words, page_index, measures)
    column_words = without_cut_in_notes(split, measures)
    return PageParts(
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


def drop_capital_indices(parts: PageParts, measures: BookMeasures) -> frozenset[int]:
    """The places among the column's words of `parts` of its drop
    capitals."""
    return frozenset(
        index
        for index, word in enumerate(parts.column)
        if _is_drop_capital(word, parts.left, measures)
    )


def regions_of_parts(parts: PageParts, measures: BookMeasures) -> tuple[Region, ...]:
    """The regions of a page whose words are placed as `parts`, in reading
    order (layout spec section 3): the running-head region, the body's
    regions, the margin regions by their top, the left side first, and the
    band's regions."""
    pitch = measures.body_line_pitch
    upper, band = column_regions_with_drop_capitals(
        parts.column,
        drop_capital_indices(parts, measures),
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


def page_regions(
    words: tuple[Word, ...], page_index: int, measures: BookMeasures
) -> tuple[Region, ...]:
    """The regions of a page of `words`, which are not empty, in reading
    order (layout spec section 3)."""
    return regions_of_parts(page_parts(words, page_index, measures), measures)


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
        else page_regions(page.words, page.index, measures)
    )
    return PageLayout(page.index, regions, page.figures)
