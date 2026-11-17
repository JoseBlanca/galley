"""The measures of a book's body text that layout and structure both take.

`rows_of` groups words, or lines, into rows (layout spec section 1,
"Row"), and `group_rows` makes a page's words rows; `edge_counts` counts the edges near each edge and `commonest`
finds the commonest of a set of edges; and
`body_measures` gives the book's body word height and body line pitch
from the rows of its pages (layout spec section 3, "The book's
measures"). The rules are written here once, so that the two stages
measure the same book alike (architecture section 12). Positions are PDF
points, origin at the top left of the page.
"""

import bisect
import itertools
import statistics
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Final

from galley.model import Box, Line, Word

__all__ = [
    "COMMONEST_EDGE_PT",
    "BodyMeasures",
    "body_measures",
    "commonest",
    "edge_counts",
    "group_rows",
    "measured_page_positions",
    "measured_pages",
    "median_word_height",
    "rows_of",
]

# Measured: body lines start within 2.2 pt of the edge on 99% of Haskins'
# lines (layout spec section 3), so the commonest edge counts the edges
# within 2 pt of it.
COMMONEST_EDGE_PT: Final[float] = 2.0
# Guessed: enough rows on a page for a commonest edge.
_MEASURED_PAGE_ROWS: Final[int] = 15
# Guessed, not measured: a book with no page of 15 rows is measured on its
# pages of 3 rows, the fewest that give a pitch between two rows and a
# commonest edge of more than one.
_MEASURED_PAGE_ROWS_FALLBACK: Final[int] = 3


@dataclass(frozen=True, slots=True)
class BodyMeasures:
    """The body word height and the body line pitch of a book, in points
    (layout spec section 3): the median height of a row's words, and the
    median distance from the top of one row to the top of the next."""

    body_word_height: float
    body_line_pitch: float


def rows_of[T](
    items: Iterable[T], box: Callable[[T], Box]
) -> tuple[tuple[T, ...], ...]:
    """`items` grouped into rows, top to bottom, each row's items left to
    right, by the box `box` gives each (layout spec section 1, "Row").

    The items are taken by top, then left side, equal keys in their given
    order. The first item starts a row and is its anchor; a later item
    joins the current row when its vertical centre lies within the
    anchor's top and bottom, edges included, and otherwise starts the next
    row as its anchor. Within a row, equal left sides keep their order. No
    items give no rows.
    """
    rows: list[list[T]] = []
    anchor: Box | None = None
    for item in sorted(items, key=lambda item: (box(item).top, box(item).x0)):
        item_box = box(item)
        centre = (item_box.top + item_box.bottom) / 2
        if anchor is not None and anchor.top <= centre <= anchor.bottom:
            rows[-1].append(item)
        else:
            rows.append([item])
            anchor = item_box
    return tuple(tuple(sorted(row, key=lambda item: box(item).x0)) for row in rows)


def group_rows(words: tuple[Word, ...]) -> tuple[Line, ...]:
    """The rows of a page's `words`, top to bottom, each one's words left to
    right (`rows_of`). A row's box is the smallest box that holds its
    words, so its top is its anchor's. No words give no rows.
    """
    return tuple(_row(row) for row in rows_of(words, lambda word: word.box))


def _row(words: tuple[Word, ...]) -> Line:
    """The row of `words`, which are left to right."""
    return Line(
        Box(
            min(word.box.x0 for word in words),
            min(word.box.top for word in words),
            max(word.box.x1 for word in words),
            max(word.box.bottom for word in words),
        ),
        words,
    )


def edge_counts(edges: Iterable[float]) -> frozendict[float, int]:
    """Each value of `edges` rounded to the point, in increasing order, with
    the number of edges within 2 pt of it, in points (layout spec section
    1). No edges give no values."""
    rounded = sorted(float(round(edge)) for edge in edges)
    return frozendict(
        {
            value: bisect.bisect_right(rounded, value + COMMONEST_EDGE_PT)
            - bisect.bisect_left(rounded, value - COMMONEST_EDGE_PT)
            for value in dict.fromkeys(rounded)
        }
    )


def commonest(edges: Iterable[float]) -> float:
    """The commonest of `edges`, in points (layout spec section 1): each edge
    rounded to the point, the value with the most edges within 2 pt of it,
    the smallest such value on a tie. Raises ValueError for no edges."""
    counts = edge_counts(edges)
    if not counts:
        msg = "the commonest of no edges is asked for"
        raise ValueError(msg)
    # The values are in increasing order, and max keeps the first of a tie.
    return max(counts, key=lambda value: counts[value])


def median_word_height(words: Iterable[Word]) -> float:
    """The median height of `words`' boxes, in points; 0 for no word."""
    heights = tuple(word.box.bottom - word.box.top for word in words)
    return statistics.median(heights) if heights else 0.0


def measured_page_positions(
    rows_by_page: tuple[tuple[Line, ...], ...],
) -> tuple[int, ...]:
    """The positions in `rows_by_page`, in increasing order, of the pages on
    which a book is measured: those of at least 15 rows, or, when none has
    15, those of at least 3; none when no page has 3 rows."""
    return tuple(
        position
        for position, rows in enumerate(rows_by_page)
        if len(rows) >= _MEASURED_PAGE_ROWS
    ) or tuple(
        position
        for position, rows in enumerate(rows_by_page)
        if len(rows) >= _MEASURED_PAGE_ROWS_FALLBACK
    )


def measured_pages(
    rows_by_page: tuple[tuple[Line, ...], ...],
) -> tuple[tuple[Line, ...], ...]:
    """The pages, given by their rows, on which a book is measured (see
    `measured_page_positions`), in their given order."""
    return tuple(
        rows_by_page[position] for position in measured_page_positions(rows_by_page)
    )


def body_measures(rows_by_page: tuple[tuple[Line, ...], ...]) -> BodyMeasures | None:
    """The body word height and body line pitch of a book whose pages have
    the rows `rows_by_page` (layout spec section 3), taken over the rows of
    the measured pages pooled, and the distances between consecutive rows
    of one page. None when no page has 3 rows."""
    measured = measured_pages(rows_by_page)
    if not measured:
        return None
    return BodyMeasures(
        body_word_height=statistics.median(
            median_word_height(row.words) for rows in measured for row in rows
        ),
        body_line_pitch=statistics.median(
            below.box.top - above.box.top
            for rows in measured
            for above, below in itertools.pairwise(rows)
        ),
    )
