"""The figures printed inside a text page, found on the plate rule's
render (docs/specs/figures.md, section 3).

The render is cut into squares of 12 pt a side, from the top left; an
outer band of two squares, which holds the dark edges of the scan, and a
partial square at the right or the foot are left out. A picture square
is an inked square that no word box touches, as for the plate rule, but
a word inside one of the page's excluded regions does not stop one. Each
group of picture squares that touch side by side is measured: its box
holds every ink pixel of its squares, and of the two band squares beyond
each of its squares that touches the band. A group of at least 120
squares with at most 12 known words inside its box is a figure.
"""

from dataclasses import dataclass
from typing import Final

from galley import wordlist
from galley.analyze._plates import (
    INK_LEVELS_WITH_LAYER,
    INKED_SHARE,
    Square,
    ink_mask,
    ink_pixels,
    squares_touched,
)
from galley.model import Box, RenderedPage
from galley.pdfium import POINTS_PER_INCH

# Figures spec section 3, "square": measured; with the plate rule's 24 pt
# squares, Kadesh 36's map and the hieroglyphs beside it were one group.
_SQUARE_PT: Final[int] = 12
# Figures spec section 3, "outer band": measured; with one square of 12 pt,
# the scan's dark edges made groups on 7 pages of the eight books.
_BAND_SQUARES: Final[int] = 2
# Figures spec section 3, "group": measured; the smallest figure, Kadesh
# 38's map, is 132 squares, the largest group that is not a picture and
# has few known words, Domesday 553's stamp, 100.
_LEAST_SQUARES: Final[int] = 120
# Figures spec section 3, "known words in the box": measured; the figures
# hold 7 or fewer (Haynes 53), Kadesh 74's card pocket 17.
_MOST_KNOWN_WORDS: Final[int] = 12


@dataclass(frozen=True, slots=True, kw_only=True)
class PictureGroup:
    """A group of picture squares of a page, as section 3 measures it: its
    box in points, grown into the outer band; its number of squares; the
    known words with their middle inside its box before that growth; and
    whether it is a figure."""

    box: Box
    squares: int
    known_words: int
    is_figure: bool


def figure_boxes(
    page: RenderedPage,
    words: tuple[tuple[str, Box], ...],
    excluded: tuple[Box, ...],
    lower_case_words: frozenset[str],
) -> tuple[Box, ...]:
    """The boxes of the in-page figures of a text page rendered as `page`,
    by figures spec section 3, in points, from the top down and, at the
    same top, from the left.

    `words` are the page's text-layer words, each its text and box in
    points. A word whose middle lies inside one of `excluded`, the page's
    exclude_regions, edges included, does not stop a picture square and is
    not counted. A known word is one `wordlist.is_known_word` takes with
    `lower_case_words`.
    """
    return tuple(
        group.box
        for group in picture_groups(page, words, excluded, lower_case_words)
        if group.is_figure
    )


def picture_groups(
    page: RenderedPage,
    words: tuple[tuple[str, Box], ...],
    excluded: tuple[Box, ...],
    lower_case_words: frozenset[str],
) -> tuple[PictureGroup, ...]:
    """Every group of picture squares of `page`, figure or not, in the
    order of `figure_boxes`; the arguments are `figure_boxes`'."""
    square_px = max(1, round(_SQUARE_PT * page.dpi / POINTS_PER_INCH))
    rows = page.height_px // square_px
    columns = page.width_px // square_px
    first_row, last_row = _BAND_SQUARES, rows - 1 - _BAND_SQUARES
    first_column, last_column = _BAND_SQUARES, columns - 1 - _BAND_SQUARES
    ink = ink_mask(page, INK_LEVELS_WITH_LAYER)
    least_ink_pixels = INKED_SHARE * square_px * square_px
    kept_words = tuple(
        (text, box) for text, box in words if not _middle_inside(box, excluded)
    )
    touched = frozenset(
        square
        for _, box in kept_words
        for square in squares_touched(box, page.dpi, square_px)
    )
    pictures = frozenset(
        (row, column)
        for row in range(first_row, last_row + 1)
        for column in range(first_column, last_column + 1)
        if (row, column) not in touched
        and ink_pixels(ink, page.width_px, (row, column), square_px) >= least_ink_pixels
    )
    scale = POINTS_PER_INCH / page.dpi

    def measured(group: frozenset[Square]) -> PictureGroup:
        own = _ink_box_px(ink, page.width_px, group, square_px)
        band = tuple(
            beyond
            for row, column in group
            for beyond in (
                *(
                    ((row - step, column) for step in range(1, _BAND_SQUARES + 1))
                    if row == first_row
                    else ()
                ),
                *(
                    ((row + step, column) for step in range(1, _BAND_SQUARES + 1))
                    if row == last_row
                    else ()
                ),
                *(
                    ((row, column - step) for step in range(1, _BAND_SQUARES + 1))
                    if column == first_column
                    else ()
                ),
                *(
                    ((row, column + step) for step in range(1, _BAND_SQUARES + 1))
                    if column == last_column
                    else ()
                ),
            )
        )
        grown = _ink_box_px(ink, page.width_px, (*group, *band), square_px)
        # A group's squares are inked, so `own`, and with it `grown`, is a box.
        assert own is not None
        assert grown is not None
        own_pt = _in_points(own, scale)
        known = sum(
            1
            for text, box in kept_words
            if _middle_inside(box, (own_pt,))
            and wordlist.is_known_word(text, lower_case_words)
        )
        return PictureGroup(
            box=_in_points(grown, scale),
            squares=len(group),
            known_words=known,
            is_figure=len(group) >= _LEAST_SQUARES and known <= _MOST_KNOWN_WORDS,
        )

    return tuple(
        sorted(
            (measured(group) for group in _groups(pictures)),
            key=lambda group: (group.box.top, group.box.x0),
        )
    )


def _middle_inside(box: Box, regions: tuple[Box, ...]) -> bool:
    """Whether the middle of `box` is inside one of `regions`, edges
    included: extract's test for an excluded region (extract spec)."""
    middle_x = (box.x0 + box.x1) / 2
    middle_y = (box.top + box.bottom) / 2
    return any(
        region.x0 <= middle_x <= region.x1 and region.top <= middle_y <= region.bottom
        for region in regions
    )


def _groups(squares: frozenset[Square]) -> tuple[frozenset[Square], ...]:
    """The sets of `squares` that touch side by side, not only by a corner."""
    unvisited = set(squares)
    found = []
    while unvisited:
        start = min(unvisited)
        unvisited.remove(start)
        stack = [start]
        group = []
        while stack:
            row, column = stack.pop()
            group.append((row, column))
            for neighbour in (
                (row - 1, column),
                (row + 1, column),
                (row, column - 1),
                (row, column + 1),
            ):
                if neighbour in unvisited:
                    unvisited.remove(neighbour)
                    stack.append(neighbour)
        found.append(frozenset(group))
    return tuple(found)


type _PixelBox = tuple[int, int, int, int]  # left, top, right, bottom; ends excluded


def _ink_box_px(
    ink: bytes,
    width_px: int,
    squares: tuple[Square, ...] | frozenset[Square],
    square_px: int,
) -> _PixelBox | None:
    """The smallest box, in pixels, that holds every ink pixel of
    `squares`; None when they hold none."""
    boxes = tuple(
        box
        for square in squares
        if (box := _square_ink_box(ink, width_px, square, square_px)) is not None
    )
    if not boxes:
        return None
    return (
        min(box[0] for box in boxes),
        min(box[1] for box in boxes),
        max(box[2] for box in boxes),
        max(box[3] for box in boxes),
    )


def _square_ink_box(
    ink: bytes, width_px: int, square: Square, square_px: int
) -> _PixelBox | None:
    """The smallest box, in pixels, that holds the ink pixels of `square`;
    None when it has none."""
    row, column = square
    top = row * square_px
    left = column * square_px
    lines = tuple(
        (top + line, ink[start : start + square_px])
        for line in range(square_px)
        if 1 in ink[(start := (top + line) * width_px + left) : start + square_px]
    )
    if not lines:
        return None
    return (
        left + min(pixels.index(1) for _, pixels in lines),
        lines[0][0],
        left + max(pixels.rindex(1) for _, pixels in lines) + 1,
        lines[-1][0] + 1,
    )


def _in_points(box: _PixelBox, scale: float) -> Box:
    left, top, right, bottom = box
    return Box(left * scale, top * scale, right * scale, bottom * scale)
