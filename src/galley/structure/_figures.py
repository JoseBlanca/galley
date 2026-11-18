"""In-page figures (docs/specs/figures.md, section 5): a figure's region
kept out of the survey and the body stream, its words removed as
`figure_text`.

layout gives each in-page figure that holds words a region whose box is
the figure's box. structure takes those regions out of the page before it
looks at it, and removes their words as `figure_text`.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from galley.model import (
    Box,
    Figure,
    FigureKind,
    Line,
    PageLayout,
    Region,
    box_holds_middle,
)

# The page's figure regions.


@dataclass(frozen=True, slots=True)
class SplitPage:
    """A page with its in-page figures' regions taken apart (figures spec
    section 5, "structure: removing the figure text"): `text` is the page
    without them, its other regions in their order; `figures` are its
    in-page figures in the order of pages.json, and `regions` the region of
    each, None for a figure that holds no word."""

    text: PageLayout
    figures: tuple[Figure, ...]
    regions: tuple[Region | None, ...]


def split_figure_regions(page: PageLayout) -> SplitPage:
    """`page` split into its text and its in-page figures' regions: a region
    whose box is one of the page's in-page figure boxes is that figure's
    region (the first such region, for each figure)."""
    figures = tuple(
        figure for figure in page.figures if figure.kind is FigureKind.IN_PAGE
    )
    boxes = frozenset(figure.box for figure in figures)
    return SplitPage(
        text=PageLayout(
            page.index,
            tuple(region for region in page.regions if region.box not in boxes),
            page.figures,
        ),
        figures=figures,
        regions=tuple(
            next((region for region in page.regions if region.box == figure.box), None)
            for figure in figures
        ),
    )


def text_page(page: PageLayout) -> PageLayout:
    """`page` without its in-page figures' regions, which take no part in
    structure's survey (figures spec section 5)."""
    return split_figure_regions(page).text


def in_any_figure(line: Line, boxes: Sequence[Box]) -> bool:
    """Whether the middle of each word of `line` lies inside one of the
    figure `boxes`, edges included (figures spec section 5: a head line
    printed inside a picture)."""
    return bool(line.words) and all(
        any(box_holds_middle(box, word.box) for box in boxes) for word in line.words
    )
