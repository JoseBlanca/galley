"""The words read inside an in-page figure kept apart (docs/specs/figures.md,
section 5, "layout: the figure's words kept apart").

A word of the text layer printed inside a picture lies on the rows of the
text beside it, and would join their lines. So, before step 1 of layout
spec section 3, the words whose middle lies inside an in-page figure's box
are taken out of the page's words, but for those of the page's first row,
which may be the head line. They make one region per figure whose box is
the figure's box, and the page's other steps run on the words left. A
figure's region is never re-read with Tesseract.
"""

from galley.body_measures import group_rows
from galley.layout._column import BookMeasures
from galley.layout._rereading import Rereading, layout_page_with_rereads
from galley.model import (
    Box,
    FigureKind,
    PageLayout,
    PageWords,
    Region,
    Reread,
    Word,
)


def figure_regions(page: PageWords) -> tuple[PageWords, tuple[Region, ...]]:
    """`page` without the words of its in-page figures, and those words as
    one region per figure, in the order of `page.figures`.

    A word belongs to the first in-page figure whose box holds its middle,
    edges included, unless it is in the page's first row (the row with the
    smallest top, as `group_rows` makes rows), which stays with the page's
    words. A region's box is its figure's box, its lines the rows of its
    words; a figure with no word has no region. A page without in-page
    figures is given back whole, with no region.
    """
    boxes = tuple(
        figure.box for figure in page.figures if figure.kind is FigureKind.IN_PAGE
    )
    if not boxes or not page.words:
        return page, ()
    rows = group_rows(page.words)
    first_row = frozenset(id(word) for word in rows[0].words)

    def figure_of(word: Word) -> int | None:
        if id(word) in first_row:
            return None
        return next(
            (
                position
                for position, box in enumerate(boxes)
                if _holds_middle(box, word.box)
            ),
            None,
        )

    owners = tuple(figure_of(word) for word in page.words)
    regions = tuple(
        Region(box, group_rows(words))
        for position, box in enumerate(boxes)
        if (
            words := tuple(
                word
                for word, owner in zip(page.words, owners, strict=True)
                if owner == position
            )
        )
    )
    rest = tuple(
        word for word, owner in zip(page.words, owners, strict=True) if owner is None
    )
    return (
        PageWords(
            index=page.index,
            text_source=page.text_source,
            words=rest,
            figures=page.figures,
        ),
        regions,
    )


def layout_page_with_figures(
    page: PageWords, measures: BookMeasures | None, rereading: Rereading | None
) -> tuple[PageLayout, tuple[Reread, ...]]:
    """The layout of one page as `layout_page_with_rereads` gives it, made
    from the page's words without those of its in-page figures
    (`figure_regions`), whose regions follow the page's other regions, in
    the order of its figures; and the records of the regions re-read, of
    which a figure's region is never one."""
    rest, regions = figure_regions(page)
    layout, records = layout_page_with_rereads(rest, measures, rereading)
    return (
        PageLayout(page.index, (*layout.regions, *regions), page.figures),
        records,
    )


def _holds_middle(box: Box, word_box: Box) -> bool:
    middle_x = (word_box.x0 + word_box.x1) / 2
    middle_y = (word_box.top + word_box.bottom) / 2
    return box.x0 <= middle_x <= box.x1 and box.top <= middle_y <= box.bottom
