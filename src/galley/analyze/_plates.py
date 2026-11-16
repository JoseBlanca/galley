"""Whether a page is a plate, from a small render of it (plates spec
section 2).

The render is cut into squares of 24 pt a side, from the top left; the
outer ring of squares, which holds the dark edges of the scan, and a
partial square at the right or the foot are left out. A square is inked
when enough of its pixels are darker than the page's median gray; a
picture square is an inked square that no word box touches. A page with
a text layer is a plate when its largest group of picture squares that
touch side by side is large and its layer holds few known words; a page
without one, when its largest group covers a large share of the page,
the columns where the binding's shadow falls left out as well.
"""

import math
import statistics
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Final

from galley.model import Box, RenderedPage

# Plates spec section 2, "render": guessed, enough to see a picture and cheap
# to render (12.6 s for Domesday's 558 pages on an M5 Pro).
PLATE_RENDER_DPI: Final[int] = 36

_POINTS_PER_INCH: Final[int] = 72
# Guessed: 12 pixels at 36 dpi.
_SQUARE_PT: Final[int] = 24
# Measured on the six books: at 50, Kadesh 16 and Domesday 39 and 40 are lost.
_INK_LEVELS_WITH_LAYER: Final[int] = 25
# Measured on the 79 pages without a layer of the six books: at 15, Kadesh
# 23's group falls to 0.12 of the page.
_INK_LEVELS_WITHOUT_LAYER: Final[int] = 10
# Guessed: the share of a square's pixels that must be ink.
_INKED_SHARE: Final[float] = 0.06
# Guessed: how far a word box is grown on every side before it is said to
# touch a square.
_WORD_BOX_GROWTH_PT: Final[float] = 2.0
# Measured: the plates' largest groups are 70 to 403 squares, title pages'
# 25 or fewer, and Mariéjol 265, a text page whose OCR failed, 107.
_MIN_GROUP_WITH_LAYER: Final[int] = 50
# Measured: the plates hold 17 known words or fewer, Mariéjol 265 holds 26.
_MAX_KNOWN_WORDS: Final[int] = 20
# Measured: the plates without a layer 0.48 to 0.94 (Kadesh 69, 0.36), the
# highest of the other pages 0.32 (Kadesh 72, a blank page).
_MIN_GROUP_SHARE_WITHOUT_LAYER: Final[float] = 0.34

type _Square = tuple[int, int]  # (row, column), from the top left


@dataclass(frozen=True, slots=True)
class PictureArea:
    """What the plate rule measures on a rendered page: the number of
    squares in its largest group of picture squares, and the number of
    squares the rule looks at, the outer ring (and, without a text layer,
    the binding's columns) left out."""

    largest_group: int
    squares: int


def is_plate(
    page: RenderedPage, word_boxes: tuple[Box, ...] | None, known_words: int
) -> bool:
    """Whether the page is a plate by plates spec section 2.

    `word_boxes` are the boxes of its text layer's words, in points, or
    None for a page without a text layer, and `known_words` the number of
    the layer's words that `wordlist.is_known_word` takes, ignored without
    a layer. With a layer, a plate has a largest group of at least 50
    picture squares and at most 20 known words; without one, a largest
    group of at least 0.34 of the squares looked at.
    """
    return is_plate_by_area(picture_area(page, word_boxes), word_boxes, known_words)


def is_plate_by_area(
    area: PictureArea, word_boxes: tuple[Box, ...] | None, known_words: int
) -> bool:
    """`is_plate` on the page's `picture_area`, already measured."""
    if word_boxes is None:
        return area.largest_group >= _MIN_GROUP_SHARE_WITHOUT_LAYER * area.squares
    return area.largest_group >= _MIN_GROUP_WITH_LAYER and known_words <= (
        _MAX_KNOWN_WORDS
    )


def picture_area(page: RenderedPage, word_boxes: tuple[Box, ...] | None) -> PictureArea:
    """The largest group of picture squares of `page` and the number of
    squares looked at; `word_boxes` as `is_plate` takes them."""
    square_px = max(1, round(_SQUARE_PT * page.dpi / _POINTS_PER_INCH))
    rows = page.height_px // square_px
    columns = page.width_px // square_px
    # The outer ring, and without a layer the binding's column on each side.
    side = 1 if word_boxes is not None else 2
    looked_at = tuple(
        (row, column)
        for row in range(1, rows - 1)
        for column in range(side, columns - side)
    )
    levels = (
        _INK_LEVELS_WITH_LAYER if word_boxes is not None else _INK_LEVELS_WITHOUT_LAYER
    )
    ink = _ink(page, levels)
    min_ink_pixels = _INKED_SHARE * square_px * square_px
    touched = (
        frozenset()
        if word_boxes is None
        else frozenset(
            square
            for box in word_boxes
            for square in _squares_touched(box, page.dpi, square_px)
        )
    )
    pictures = frozenset(
        square
        for square in looked_at
        if square not in touched
        and _ink_pixels(ink, page.width_px, square, square_px) >= min_ink_pixels
    )
    return PictureArea(largest_group=_largest_group(pictures), squares=len(looked_at))


def _ink(page: RenderedPage, levels: int) -> bytes:
    """One byte per pixel of `page`: 1 for a pixel darker than the page's
    median gray by more than `levels`, else 0."""
    cutoff = statistics.median_low(page.pixels) - levels
    table = bytes(1 if value < cutoff else 0 for value in range(256))
    return page.pixels.translate(table)


def _ink_pixels(ink: bytes, width_px: int, square: _Square, square_px: int) -> int:
    row, column = square
    top = row * square_px
    left = column * square_px
    return sum(
        ink.count(1, start, start + square_px)
        for start in ((top + line) * width_px + left for line in range(square_px))
    )


def _squares_touched(box: Box, dpi: int, square_px: int) -> Iterator[_Square]:
    """The squares that `box`, grown by 2 pt on every side, overlaps or
    touches by an edge."""
    scale = dpi / _POINTS_PER_INCH
    x0 = (box.x0 - _WORD_BOX_GROWTH_PT) * scale
    x1 = (box.x1 + _WORD_BOX_GROWTH_PT) * scale
    top = (box.top - _WORD_BOX_GROWTH_PT) * scale
    bottom = (box.bottom + _WORD_BOX_GROWTH_PT) * scale
    # Square n spans [n * square_px, (n + 1) * square_px].
    for row in range(
        max(0, math.ceil(top / square_px) - 1), math.floor(bottom / square_px) + 1
    ):
        for column in range(
            max(0, math.ceil(x0 / square_px) - 1), math.floor(x1 / square_px) + 1
        ):
            yield row, column


def _largest_group(squares: frozenset[_Square]) -> int:
    """The number of squares in the largest set of `squares` that touch side
    by side, not only by a corner."""
    unvisited = set(squares)
    largest = 0
    while unvisited:
        stack = [unvisited.pop()]
        size = 0
        while stack:
            row, column = stack.pop()
            size += 1
            for neighbour in (
                (row - 1, column),
                (row + 1, column),
                (row, column - 1),
                (row, column + 1),
            ):
                if neighbour in unvisited:
                    unvisited.remove(neighbour)
                    stack.append(neighbour)
        largest = max(largest, size)
    return largest
