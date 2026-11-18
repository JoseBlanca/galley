"""The words read inside an in-page figure kept apart (docs/specs/figures.md,
section 5, "layout: the figure's words kept apart").

A word of the text layer printed inside a picture lies on the rows of the
text beside it, and would join their lines. So, once the page is laid out
with all its words, the words whose middle lies inside an in-page figure's
box are taken out of the regions they fell in, but for those of the
page's first row, which may be the head line. They make one region per
figure whose box is the figure's box. The page is laid out with them
because its bands and columns are found on all its rows: taken out
first, they changed the footnotes of Kadesh page 52. A figure's region is
never re-read with Tesseract.
"""

from collections import Counter

from galley.body_measures import group_rows
from galley.layout._column import BookMeasures
from galley.layout._rereading import Rereading, layout_page_with_rereads
from galley.model import (
    Box,
    FigureKind,
    Line,
    PageLayout,
    PageWords,
    Region,
    Reread,
    Word,
)


def _figure_words(page: PageWords) -> frozendict[Word, int]:
    """The words of `page` that belong to an in-page figure, each with the
    position of its figure among the in-page figures: the first whose box
    holds its middle, edges included, unless the word is in the page's
    first row (the row with the smallest top, as `group_rows` makes rows).
    """
    boxes = _in_page_boxes(page)
    owners: dict[Word, int] = {}
    if not boxes or not page.words:
        return frozendict(owners)
    first_row = frozenset(group_rows(page.words)[0].words)
    for word in page.words:
        if word in first_row:
            continue
        owner = next(
            (
                position
                for position, box in enumerate(boxes)
                if _holds_middle(box, word.box)
            ),
            None,
        )
        if owner is not None:
            owners[word] = owner
    return frozendict(owners)


def _in_page_boxes(page: PageWords) -> tuple[Box, ...]:
    """The boxes of the in-page figures of `page`, in their order."""
    return tuple(
        figure.box for figure in page.figures if figure.kind is FigureKind.IN_PAGE
    )


def _enclosing_box(boxes: tuple[Box, ...]) -> Box:
    return Box(
        min(box.x0 for box in boxes),
        min(box.top for box in boxes),
        max(box.x1 for box in boxes),
        max(box.bottom for box in boxes),
    )


def figure_regions(page: PageWords, layout: PageLayout) -> PageLayout:
    """`layout`, the layout of `page` made with all its words, with the
    words of its in-page figures taken out of its regions and put into one
    region per figure, after the other regions, in the order of the
    figures.

    A word belongs to the first in-page figure whose box holds its middle,
    edges included, unless it is in the page's first row (the row with the
    smallest top, as `group_rows` makes rows), which stays where it is.
    Each such word of `page` is taken out once, from the first line of
    `layout` that holds it; a word a kept re-reading replaced is in no
    line and is not taken. A line left with no word is dropped, and so is
    a region left with no line; a line or a region that lost a word has
    again the smallest box that holds what is left. A figure region's box
    is its figure's box, its lines the rows of its words; a figure with no
    word taken has no region. A page without in-page figures gives
    `layout` back.
    """
    owners = _figure_words(page)
    if not owners:
        return layout
    left = Counter(word for word in page.words if word in owners)
    taken: list[Word] = []

    def line_without(line: Line) -> Line | None:
        kept = []
        for word in line.words:
            if left[word] > 0:
                left[word] -= 1
                taken.append(word)
            else:
                kept.append(word)
        if len(kept) == len(line.words):
            return line
        if not kept:
            return None
        return Line(_enclosing_box(tuple(word.box for word in kept)), tuple(kept))

    def region_without(region: Region) -> Region | None:
        lines = tuple(
            line
            for line in (line_without(line) for line in region.lines)
            if line is not None
        )
        if lines == region.lines:
            return region
        if not lines:
            return None
        return Region(_enclosing_box(tuple(line.box for line in lines)), lines)

    regions = tuple(
        region
        for region in (region_without(region) for region in layout.regions)
        if region is not None
    )
    boxes = _in_page_boxes(page)
    regions_of_figures = tuple(
        Region(box, group_rows(words))
        for position, box in enumerate(boxes)
        if (words := tuple(word for word in taken if owners[word] == position))
    )
    return PageLayout(layout.index, (*regions, *regions_of_figures), layout.figures)


def layout_page_with_figures(
    page: PageWords, measures: BookMeasures | None, rereading: Rereading | None
) -> tuple[PageLayout, tuple[Reread, ...]]:
    """The layout of one page as `layout_page_with_rereads` gives it, made
    with all the page's words, with the words of its in-page figures then
    taken out into their regions (`figure_regions`); and the records of
    the regions re-read, of which a figure's region is never one."""
    layout, records = layout_page_with_rereads(page, measures, rereading)
    return figure_regions(page, layout), records


def _holds_middle(box: Box, word_box: Box) -> bool:
    middle_x = (word_box.x0 + word_box.x1) / 2
    middle_y = (word_box.top + word_box.bottom) / 2
    return box.x0 <= middle_x <= box.x1 and box.top <= middle_y <= box.bottom
