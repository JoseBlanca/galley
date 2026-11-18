"""Lists (spec section 29): the list markers, and the items of the lists
that the body stream prints, found in page order across page breaks.

Positions are PDF points, origin at the top left of the page; the gap is
in body line pitches."""

from collections.abc import Sequence
from dataclasses import dataclass

from galley.list_markers import ListMarker, follows, marker_readings, starts_a_list
from galley.model import Box
from galley.structure._lines import PlacedLine, hyphen_between

# Spec section 29, rule 3: the next item's marker line lies within 3 pt of
# the marker column (the five marker lines of Haynes' page 16 lie from 37.7
# to 39.4 pt).
_COLUMN_PT = 3.0
# Spec section 29, rule 4: before a list has a hang, a continuation line
# lies 5 to 20 pt right of the marker column (Haynes 12.5 and 14 pt,
# Domesday 14 to 14.4; 30 pt would reach Haynes' paragraph indent, 29 pt);
# once it has one, within 3 pt of the marker column plus the hang.
_HANG_MIN_PT = 5.0
_HANG_MAX_PT = 20.0
_HANG_SLACK_PT = 3.0
# Spec section 29, rule 5: a list ends at a line whose top lies more than
# 1.5 body line pitches below the top of the line before it on its page
# (guessed: with no limit the eight books give the same lists).
_GAP_MAX_PITCHES = 1.5

# Spec section 29, rule 1: the fewest items of a list.
_LIST_MIN_ITEMS = 2


def _rest(line: PlacedLine, marker: ListMarker) -> bool:
    """Whether `line` holds a word after its marker: a second word, or the
    part of its first word after a glued dash."""
    words = line.line.words
    return len(words) > 1 or len(words[0].text) > len(marker.text)


def _starting_marker(line: PlacedLine) -> ListMarker | None:
    """The marker with which `line` can start a list (spec section 29, rule
    1): its first word is a dash, a bullet or the first value of its kind,
    and a word follows it; a word that reads as a roman numeral and as a
    letter is the numeral. None otherwise."""
    if not line.line.words:
        return None
    return next(
        (
            reading
            for reading in marker_readings(line.line.words[0].text)
            if starts_a_list(reading) and _rest(line, reading)
        ),
        None,
    )


def _following_marker(line: PlacedLine, before: ListMarker) -> ListMarker | None:
    """The marker of `line` when it follows `before`, the marker of the item
    before (spec section 29, rule 3), with a word after it; None
    otherwise."""
    if not line.line.words:
        return None
    return next(
        (
            reading
            for reading in marker_readings(line.line.words[0].text)
            if follows(reading, before) and _rest(line, reading)
        ),
        None,
    )


@dataclass(frozen=True, slots=True)
class StreamPage:
    """A page's body stream as the list rules see it (spec section 29, "The
    rules"): its lines; the positions of those the rules take none of,
    the lines of a run of section 2, step 2.3, or every line of a page of
    the printed contents, an index or the endnote section; and the boxes
    of its in-page figures, across which the gap is not tested (rule 5)."""

    lines: tuple[PlacedLine, ...]
    closed: frozenset[int] = frozenset()
    figures: tuple[Box, ...] = ()


@dataclass(frozen=True, slots=True)
class ItemLine:
    """A line of a list item: `marker` is the item's marker on its first
    line, None on its other lines."""

    marker: ListMarker | None


@dataclass(frozen=True, slots=True)
class _StreamLine:
    page_index: int
    number: int
    line: PlacedLine
    closed: bool
    figures: tuple[Box, ...]


def _across_a_figure(before: _StreamLine, here: _StreamLine) -> bool:
    """Whether an in-page figure of the page lies between the tops of
    `before` and `here`, two lines of one page (spec section 29, rule 5)."""
    return any(
        before.line.line.box.top
        < (figure.top + figure.bottom) / 2
        < here.line.line.box.top
        for figure in here.figures
    )


def _left(line: _StreamLine) -> float:
    return line.line.line.box.x0


def _page_column(
    stream: Sequence[_StreamLine], start: int, last: ListMarker
) -> float | None:
    """The marker column of the page whose first line is at `start`, for a
    list whose last item's marker is `last` (spec section 29, rule 6): the
    left side of the page's first marker line that follows `last`, when the
    lines before it on the page lie within 3 pt of one left side 5 to 20
    pt right of it, or there are none; otherwise the text edge of the
    page's first body region, None when it has none."""
    page_index = stream[start].page_index
    page = []
    for line in stream[start:]:
        if line.page_index != page_index or line.closed:
            break
        page.append(line)
    marker_line = next(
        (
            position
            for position, line in enumerate(page)
            if _following_marker(line.line, last) is not None
        ),
        None,
    )
    if marker_line is not None:
        column = _left(page[marker_line])
        lefts = tuple(_left(line) for line in page[:marker_line])
        if not lefts or (
            max(lefts) - min(lefts) <= _COLUMN_PT
            and _HANG_MIN_PT <= lefts[0] - column <= _HANG_MAX_PT
        ):
            return column
    return stream[start].line.text_edge


def _grow(
    stream: Sequence[_StreamLine],
    start: int,
    marker: ListMarker,
    body_line_pitch: float,
) -> tuple[tuple[tuple[int, ListMarker], ...], int]:
    """The items of the list that starts at `start` with `marker`, each as
    the position of its marker line and its marker, and the position of
    the line that ends the list (spec section 29, rules 3 to 6)."""
    column = _left(stream[start])
    hang: float | None = None
    items = [(start, marker)]
    position = start + 1
    while position < len(stream):
        here, before = stream[position], stream[position - 1]
        if here.closed:
            break
        if here.page_index != before.page_index:
            page_column = _page_column(stream, position, items[-1][1])
            if page_column is None:
                break
            column = page_column
        elif (
            here.line.line.box.top - before.line.line.box.top
            > _GAP_MAX_PITCHES * body_line_pitch
            and not _across_a_figure(before, here)
        ):
            break
        # Spec section 29, rule 2: the hyphen rule holds, so a line after a
        # hyphen goes on with the item, wherever it lies.
        if not hyphen_between(before.line, here.line):
            following = _following_marker(here.line, items[-1][1])
            offset = _left(here) - column
            if following is not None and abs(offset) <= _COLUMN_PT:
                items.append((position, following))
            elif hang is not None and abs(offset - hang) <= _HANG_SLACK_PT:
                pass
            elif hang is None and _HANG_MIN_PT <= offset <= _HANG_MAX_PT:
                hang = offset
            else:
                break
        position += 1
    return tuple(items), position


def list_items(
    pages: Sequence[StreamPage], body_line_pitch: float
) -> frozendict[tuple[int, int], ItemLine]:
    """The lines of the lists of the body stream `pages`, in page order, by
    their page index and position in their page's stream (spec section 29,
    rules 1 to 6): a list starts at a marker line that can start one, not
    after a line that ends with a hyphen, and has at least two items; a
    list of one item is none, and the search goes on at the line after its
    marker line. `body_line_pitch` is in points. A page without lines is
    passed over; a closed line ends a list."""
    stream = tuple(
        _StreamLine(line.page_index, number, line, number in page.closed, page.figures)
        for page in pages
        for number, line in enumerate(page.lines)
    )
    found: dict[tuple[int, int], ItemLine] = {}
    position = 0
    while position < len(stream):
        here = stream[position]
        marker = None if here.closed else _starting_marker(here.line)
        if marker is None or (
            position > 0 and hyphen_between(stream[position - 1].line, here.line)
        ):
            position += 1
            continue
        items, end = _grow(stream, position, marker, body_line_pitch)
        if len(items) < _LIST_MIN_ITEMS:
            position += 1
            continue
        starts = dict(items)
        for number in range(position, end):
            line = stream[number]
            found[line.page_index, line.number] = ItemLine(starts.get(number))
        position = end
    return frozendict(found)
