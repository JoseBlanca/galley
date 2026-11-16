"""A printed index (spec section 17): its pages, the regions of an index
page read as two columns, the guide words removed, and which lines start
an entry.

Positions are PDF points, origin at the top left of the page."""

import statistics
from collections.abc import Sequence
from dataclasses import dataclass

from galley.body_measures import commonest
from galley.model import Line, PageLayout, Region, Removal, RemovalReason, Word
from galley.structure._foot import LinePlace
from galley.structure._measures import (
    box_of,
    is_page_number_form,
    letters,
    middle,
    words_box,
    words_text,
)
from galley.structure._regions import RegionKind, head_line

# Spec section 17, rule 1: the words that start an index's title.
_INDEX_TITLES = (("index",), ("table", "alphabétique"))
# Spec section 17, rule 1: each index column is 0.3 to 0.65 of the width
# that the page's regions span (Haskins' columns are about 130 pt of 270).
_COLUMN_SHARE_MIN = 0.3
_COLUMN_SHARE_MAX = 0.65
# Spec section 17, rule 2: a guide word is three capital letters; the two
# guide words, split by layout into the first lines of the two columns,
# have tops within 3 pt (Stubbs' pages 313 to 319: 0.3 to 2.2 pt apart).
_GUIDE_WORD_LETTERS = 3
_GUIDE_WORDS_ON_A_LINE = 2
_GUIDE_WORDS_TOPS_PT = 3.0
# Spec section 17, rule 2: a region is cut at the gutter when at least two
# thirds of its lines have no word over it (Gierke's footnote on page 83,
# 1 of 2 lines over it, is not).
_UNCROSSED_SHARE = 2 / 3
# Spec section 17, rule 3: a line starts an entry within 5 pt of its
# column's left edge (no line of the four indexes lies at 5 pt; the
# smallest indent is 6 pt); the edge is fitted through the left sides
# within 3 pt of the entry side, then of the first fit; a column of
# fewer than 5 lines takes its smallest left side. The entry side is the
# commonest left side, or the commonest of the left sides more than 5 pt
# left of it when there are at least 2 (Stubbs' columns of long entries,
# whose continuation lines outnumber their first lines).
_ENTRY_START_PT = 5.0
_EDGE_FIT_PT = 3.0
_EDGE_FIT_MIN_LINES = 5
_LEFT_OF_COMMONEST_PT = 5.0
_LEFT_OF_COMMONEST_MIN_SIDES = 2
# A straight line is fitted through at least two different tops.
_FIT_MIN_TOPS = 2


def _title_line(page: PageLayout, kinds: Sequence[RegionKind]) -> Line | None:
    """The page's title line: the text line of its head line, or else the
    first line of its first body region; None without either."""
    head = head_line(page)
    if head is not None:
        return head.lines[-1]
    return next(
        (
            region.lines[0]
            for region, kind in zip(page.regions, kinds, strict=True)
            if kind is RegionKind.BODY and region.lines
        ),
        None,
    )


def _without_page_number(texts: Sequence[str]) -> tuple[str, ...]:
    """`texts` without a page-number form at their start or at their end."""
    start = 1 if texts and is_page_number_form(texts[0]) else 0
    end = (
        len(texts) - 1
        if len(texts) > start and is_page_number_form(texts[-1])
        else len(texts)
    )
    return tuple(texts[start:end])


def is_index_title(page: PageLayout, kinds: Sequence[RegionKind]) -> bool:
    """Whether the page's title, without a page number at its start or end,
    starts with the word "index" or "table alphabétique", in any case (spec
    section 17, rule 1)."""
    line = _title_line(page, kinds)
    if line is None:
        return False
    words = tuple(
        letters(text)
        for text in _without_page_number(tuple(word.text for word in line.words))
    )
    return any(words[: len(title)] == title for title in _INDEX_TITLES)


@dataclass(frozen=True, slots=True)
class IndexColumns:
    """The index columns of a page: the numbers of the regions of the left
    column and of the right, and the gutter, the middle between the left
    column's right edge and the right column's left edge."""

    left: frozenset[int]
    right: frozenset[int]
    gutter: float


def _width(region: Region) -> float:
    return region.box.x1 - region.box.x0


def index_columns(page: PageLayout, kinds: Sequence[RegionKind]) -> IndexColumns | None:
    """The page's two index columns (spec section 17, rule 1): the regions,
    not margin regions nor the head line, each 0.3 to 0.65 of the width
    that the page's regions span, of which one lies left of another; every
    such region left of another is of the left column, every one right of
    another of the right. None when the page has no two such regions, or
    when one region lies both left and right of others."""
    if not page.regions:
        return None
    span = max(region.box.x1 for region in page.regions) - min(
        region.box.x0 for region in page.regions
    )
    head = head_line(page)
    candidates = tuple(
        number
        for number, (region, kind) in enumerate(zip(page.regions, kinds, strict=True))
        if kind is not RegionKind.MARGIN
        and region is not head
        and _COLUMN_SHARE_MIN * span <= _width(region) <= _COLUMN_SHARE_MAX * span
    )
    boxes = {number: page.regions[number].box for number in candidates}
    left = frozenset(
        number
        for number in candidates
        if any(boxes[number].x1 <= boxes[other].x0 for other in candidates)
    )
    right = frozenset(
        number
        for number in candidates
        if any(boxes[other].x1 <= boxes[number].x0 for other in candidates)
    )
    if not left or not right or left & right:
        return None
    gutter = (
        max(boxes[number].x1 for number in left)
        + min(boxes[number].x0 for number in right)
    ) / 2
    return IndexColumns(left, right, gutter)


def index_pages(
    pages: Sequence[PageLayout], kinds: Sequence[Sequence[RegionKind]]
) -> frozenset[int]:
    """The page indices of the book's printed indexes (spec section 17, rule
    1): from a page whose title starts with "index" (`is_index_title`),
    and over the following pages while each page that has words has two
    index columns. `kinds` are the kinds of each page's regions."""
    found: list[int] = []
    in_index = False
    for page, page_kinds in zip(pages, kinds, strict=True):
        if is_index_title(page, page_kinds):
            in_index = True
        elif in_index and any(region.lines for region in page.regions):
            in_index = index_columns(page, page_kinds) is not None
        if in_index:
            found.append(page.index)
    return frozenset(found)


# The regions of an index page


def _is_guide_word(text: str) -> bool:
    return len(text) == _GUIDE_WORD_LETTERS and text.isalpha() and text.isupper()


def _is_guide_words_line(line: Line) -> bool:
    """A line of exactly two words of three capital letters each."""
    return len(line.words) == _GUIDE_WORDS_ON_A_LINE and all(
        _is_guide_word(word.text) for word in line.words
    )


def _crosses(word: Word, gutter: float) -> bool:
    return word.box.x0 < gutter < word.box.x1


def _is_cut(region: Region, lines: Sequence[Line], gutter: float) -> bool:
    """Whether a region is cut at the gutter: it crosses it, and at least two
    thirds of its lines `lines`, those not removed, have no word over it."""
    if not lines or not region.box.x0 < gutter < region.box.x1:
        return False
    uncrossed = sum(
        not any(_crosses(word, gutter) for word in line.words) for line in lines
    )
    return uncrossed >= _UNCROSSED_SHARE * len(lines)


def _part(lines: Sequence[Line], side: int, gutter: float) -> tuple[Line, ...]:
    """The left (`side` 0) or right (1) part of each of `lines`, each word
    going by its middle; lines with no word on that side are left out."""
    parts = []
    for line in lines:
        words = tuple(
            word for word in line.words if (middle(word.box) >= gutter) == bool(side)
        )
        if words:
            parts.append(Line(words_box(words), words))
    return tuple(parts)


@dataclass(frozen=True, slots=True)
class _Item:
    """Lines read together into a column, placed by the top of the first:
    one line of a column region, or the part of a cut region, as a whole
    (spec section 17, rule 2)."""

    top: float
    lines: tuple[Line, ...]


@dataclass(frozen=True, slots=True)
class _Side:
    """What goes into one index column: its items, and the lines of the
    margin regions on its side, each placed on its own."""

    items: tuple[_Item, ...]
    margin_lines: tuple[Line, ...]


@dataclass(frozen=True, slots=True)
class IndexPage:
    """What an index page gives (spec section 17, rule 2): the guide words
    removed; the lines of the left column, then of the right, in reading
    order, and the positions of those that start an entry (rule 3); the
    left and right edge of each line's column; the numbers of the regions
    read into the columns, which leave the page's other streams; and the
    lines of guide words removed from regions not read into the columns,
    as (region number, line number)."""

    removals: tuple[Removal, ...]
    lines: tuple[Line, ...]
    starts: frozenset[int]
    column_edges: tuple[tuple[float, float], ...]
    taken: frozenset[int]
    removed_lines: frozenset[LinePlace]


def _guide_words_removal(page_index: int, words: Sequence[Word]) -> Removal:
    return Removal(
        page_index=page_index,
        box=words_box(words),
        text=words_text(words),
        reason=RemovalReason.GUIDE_WORDS,
    )


def entry_side(left_sides: Sequence[float]) -> float:
    """The side, in points, that a column's first lines start at (spec
    section 17, rule 3): the commonest of `left_sides`, which are not none,
    unless at least 2 of them lie more than 5 pt left of it; then the
    commonest of those."""
    usual = commonest(left_sides)
    further_left = tuple(
        side for side in left_sides if side < usual - _LEFT_OF_COMMONEST_PT
    )
    if len(further_left) >= _LEFT_OF_COMMONEST_MIN_SIDES:
        return commonest(further_left)
    return usual


def column_left_edge(lines: Sequence[Line]) -> tuple[float, float]:
    """The column's left edge as (x at top 0, points per point of top), a
    straight line through its lines' left sides (spec section 17, rule 3):
    fitted by least squares on the line's top through the left sides within
    3 pt of the entry side (`entry_side`), then again through those within
    3 pt of the first fit. A column of fewer than 5 lines takes its
    smallest left side; a fit through fewer than 2 tops, the mean of its
    left sides."""
    if len(lines) < _EDGE_FIT_MIN_LINES:
        return (min(line.box.x0 for line in lines), 0.0) if lines else (0.0, 0.0)
    usual = entry_side(tuple(line.box.x0 for line in lines))
    first = _fit(
        tuple(line for line in lines if abs(line.box.x0 - usual) <= _EDGE_FIT_PT)
    )
    near_first = tuple(
        line for line in lines if abs(line.box.x0 - _at(first, line)) <= _EDGE_FIT_PT
    )
    return _fit(near_first) if near_first else first


def _at(edge: tuple[float, float], line: Line) -> float:
    return edge[0] + edge[1] * line.box.top


def _fit(lines: Sequence[Line]) -> tuple[float, float]:
    """The least-squares line x = a + b * top through the left sides of
    `lines`, which are not none; (mean, 0) when their tops are all one."""
    tops = tuple(line.box.top for line in lines)
    sides = tuple(line.box.x0 for line in lines)
    if len(set(tops)) < _FIT_MIN_TOPS:
        return statistics.fmean(sides), 0.0
    slope, intercept = statistics.linear_regression(tops, sides)
    return intercept, slope


def _shares_row(line: Line, other: Line) -> bool:
    """Whether `line` is in the row of `other`: its vertical centre lies
    within `other`'s top and bottom (layout spec section 1, "Row")."""
    centre = (line.box.top + line.box.bottom) / 2
    return other.box.top <= centre <= other.box.bottom


def _column(side: _Side) -> tuple[Line, ...]:
    """The lines of one index column in reading order (spec section 17,
    rule 2): the items by their tops, and each margin line just before the
    line of its row when it lies left of it, just after when right of it,
    or, in no line's row, before the first line whose top is below its
    own."""
    lines = [
        line
        for item in sorted(side.items, key=lambda item: item.top)
        for line in item.lines
    ]
    for margin in sorted(side.margin_lines, key=lambda line: line.box.top):
        row = next(
            (
                number
                for number, line in enumerate(lines)
                if line not in side.margin_lines and _shares_row(margin, line)
            ),
            None,
        )
        if row is not None:
            position = row if margin.box.x1 <= lines[row].box.x0 else row + 1
        else:
            position = next(
                (
                    number
                    for number, line in enumerate(lines)
                    if line.box.top > margin.box.top
                ),
                len(lines),
            )
        lines.insert(position, margin)
    return tuple(lines)


def _column_items(
    page: PageLayout,
    kinds: Sequence[RegionKind],
    columns: IndexColumns,
    removed: frozenset[LinePlace],
) -> tuple[tuple[_Side, _Side], frozenset[int]]:
    """What goes into the left and the right column of an index page (spec
    section 17, rule 2), and the numbers of the regions taken: each line
    of a column region, the lines of each margin region on its side but
    one wholly above every column region, and the part of each region cut
    at the gutter on each side. The head line and the lines of `removed`
    are left out."""
    head = head_line(page)
    columns_top = min(
        page.regions[number].box.top for number in columns.left | columns.right
    )
    items: tuple[list[_Item], list[_Item]] = ([], [])
    margins: tuple[list[Line], list[Line]] = ([], [])
    taken: set[int] = set()
    for number, (region, kind) in enumerate(zip(page.regions, kinds, strict=True)):
        lines = tuple(
            line
            for line_number, line in enumerate(region.lines)
            if (number, line_number) not in removed
        )
        if region is head:
            continue
        if number in columns.left or number in columns.right:
            side = 0 if number in columns.left else 1
            items[side].extend(_Item(line.box.top, (line,)) for line in lines)
        elif kind is RegionKind.MARGIN and region.box.bottom > columns_top:
            side = 0 if middle(region.box) < columns.gutter else 1
            margins[side].extend(lines)
        elif _is_cut(region, lines, columns.gutter):
            for side in (0, 1):
                part = _part(lines, side, columns.gutter)
                if part:
                    items[side].append(_Item(part[0].box.top, part))
        else:
            continue
        taken.add(number)
    return (
        _Side(tuple(items[0]), tuple(margins[0])),
        _Side(tuple(items[1]), tuple(margins[1])),
    ), frozenset(taken)


def _are_guide_words(left: Sequence[Line], right: Sequence[Line]) -> bool:
    """Whether the first lines of the two columns are the guide words, which
    layout split between them: one guide word each, their tops within 3 pt."""
    return (
        bool(left)
        and bool(right)
        and len(left[0].words) == 1
        and len(right[0].words) == 1
        and _is_guide_word(left[0].words[0].text)
        and _is_guide_word(right[0].words[0].text)
        and abs(left[0].box.top - right[0].box.top) <= _GUIDE_WORDS_TOPS_PT
    )


def index_page(
    page: PageLayout,
    kinds: Sequence[RegionKind],
    removed: frozenset[LinePlace],
) -> IndexPage:
    """The regions of an index page read as its two columns (spec section 17,
    rule 2), `removed` being the lines already removed from it, as (region
    number, line number). A line of two guide words is removed first; then
    the column regions' lines, the margin regions on each side and the
    parts of each region cut at the gutter go into the left or the right
    column by their tops, and the first lines of the two columns, when
    they are one guide word each at one height, are removed. A page
    without two index columns gives its guide words alone. The head line is
    left as on any page."""
    head = head_line(page)
    guide_lines = frozenset(
        (number, line_number)
        for number, region in enumerate(page.regions)
        if region is not head
        for line_number, line in enumerate(region.lines)
        if (number, line_number) not in removed and _is_guide_words_line(line)
    )
    removals = tuple(
        _guide_words_removal(page.index, page.regions[number].lines[line_number].words)
        for number, line_number in sorted(
            guide_lines,
            key=lambda place: page.regions[place[0]].lines[place[1]].box.top,
        )
    )
    columns = index_columns(page, kinds)
    if columns is None:
        return IndexPage(removals, (), frozenset(), (), frozenset(), guide_lines)
    sides, taken = _column_items(page, kinds, columns, removed | guide_lines)
    left, right = _column(sides[0]), _column(sides[1])
    if _are_guide_words(left, right):
        removals = tuple(
            sorted(
                (
                    *removals,
                    _guide_words_removal(page.index, (*left[0].words, *right[0].words)),
                ),
                key=lambda removal: removal.box.top,
            )
        )
        left, right = left[1:], right[1:]
    starts: list[int] = []
    edges: list[tuple[float, float]] = []
    for offset, column in ((0, left), (len(left), right)):
        edge = column_left_edge(column)
        starts.extend(
            offset + position
            for position, line in enumerate(column)
            if abs(line.box.x0 - _at(edge, line)) <= _ENTRY_START_PT
        )
        if column:
            box = box_of(tuple(line.box for line in column))
            edges.extend((box.x0, box.x1) for _ in column)
    return IndexPage(
        removals,
        left + right,
        frozenset(starts),
        tuple(edges),
        frozenset(taken),
        frozenset(place for place in guide_lines if place[0] not in taken),
    )
