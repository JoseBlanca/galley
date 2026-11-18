"""The figures printed inside a text page, found on the plate rule's
render (docs/specs/figures.md, section 3).

The render is cut into squares of 12 pt a side, from the top left; an
outer band of two squares, which holds the dark edges of the scan, and a
partial square at the right or the foot are left out. A picture square
is an inked square that no word box touches, as for the plate rule, but
a word inside one of the page's excluded regions does not stop one. Each
group of picture squares that touch side by side is cut where a band
without ink runs across it beside a rule or a frame's edge, and each part
is measured: its box holds every ink pixel of its squares on its side of
the cut, and of the two band squares beyond each of its squares that
touches the band. A group of at least 120 squares with at most 12 known
words inside its box is a figure, and its box grows to hold the groups
that are no figures and have their middle inside it.
"""

import itertools
from dataclasses import dataclass, replace
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
from galley.model import Box, RenderedPage, box_holds_middle
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
# Figures spec section 3, step 3, "cut": measured; the bands across the
# 56 figures are 6 to 12 pt, the runs of ink beside them 30 pt at most, the
# rules and the frame cut 96 to 154 pt (Kadesh 53, 44, 41, 40). A line is
# looked for in the two pixel rows on each side of the band, as the frame
# of Kadesh 41's map is two pixels high and fills the second.
_RULE_GAP_PT: Final[float] = 6.0
_LINE_PT: Final[float] = 72.0
_LINE_ROWS: Final[int] = 2


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
        group.box for group in figure_groups(page, words, excluded, lower_case_words)
    )


def figure_groups(
    page: RenderedPage,
    words: tuple[tuple[str, Box], ...],
    excluded: tuple[Box, ...],
    lower_case_words: frozenset[str],
) -> tuple[PictureGroup, ...]:
    """The groups of `picture_groups` that are figures, in its order: those
    whose boxes `figure_boxes` gives, with their squares and known words
    for the log; the arguments are `figure_boxes`'."""
    return tuple(
        group
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
        (text, box)
        for text, box in words
        if not any(box_holds_middle(region, box) for region in excluded)
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

    def measured(group: frozenset[Square], rows: _PixelRows) -> PictureGroup:
        own = _ink_box_px(ink, page.width_px, group, square_px, rows)
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
        grown = _ink_box_px(ink, page.width_px, (*group, *band), square_px, rows)
        # A group's squares are inked, so `own`, and with it `grown`, is a box.
        assert own is not None
        assert grown is not None
        own_pt = _in_points(own, scale)
        known = sum(
            1
            for text, box in kept_words
            if box_holds_middle(own_pt, box)
            and wordlist.is_known_word(text, lower_case_words)
        )
        return PictureGroup(
            box=_in_points(grown, scale),
            squares=len(group),
            known_words=known,
            is_figure=len(group) >= _LEAST_SQUARES and known <= _MOST_KNOWN_WORDS,
        )

    gap_px = max(1, round(_RULE_GAP_PT * page.dpi / POINTS_PER_INCH))
    line_px = round(_LINE_PT * page.dpi / POINTS_PER_INCH)
    groups = tuple(
        measured(part, rows)
        for group in _groups(pictures)
        for part, rows in _cut_at_rules(
            group, ink, page.width_px, square_px, gap_px, line_px
        )
    )
    return tuple(
        sorted(
            _with_parts_inside(groups), key=lambda group: (group.box.top, group.box.x0)
        )
    )


def _with_parts_inside(groups: tuple[PictureGroup, ...]) -> tuple[PictureGroup, ...]:
    """`groups` with each figure's box grown to hold the groups that are no
    figures and whose box has its middle inside the figure's box, edges
    included: parts of the same picture that the words read on it cut off
    (Kadesh 51). The squares and known words of a figure are its own."""
    figures = tuple(group for group in groups if group.is_figure)
    others = tuple(group for group in groups if not group.is_figure)

    def grown(figure: PictureGroup) -> PictureGroup:
        inside = tuple(
            other.box for other in others if box_holds_middle(figure.box, other.box)
        )
        if not inside:
            return figure
        return replace(figure, box=_enclosing((figure.box, *inside)))

    return (*(grown(figure) for figure in figures), *others)


def _enclosing(boxes: tuple[Box, ...]) -> Box:
    return Box(
        min(box.x0 for box in boxes),
        min(box.top for box in boxes),
        max(box.x1 for box in boxes),
        max(box.bottom for box in boxes),
    )


type _PixelRows = tuple[int, int]  # top, bottom, in pixels; the bottom excluded


def _cut_at_rules(
    group: frozenset[Square],
    ink: bytes,
    width_px: int,
    square_px: int,
    gap_px: int,
    least_line_px: int,
) -> tuple[tuple[frozenset[Square], _PixelRows], ...]:
    """The parts of `group`, each with the pixel rows its ink is taken from:
    the group is cut in the middle of each band of at least `gap_px` pixel
    rows without ink across all its squares when one of the `_LINE_ROWS`
    pixel rows next to the band, on either side, holds a run of at least
    `least_line_px` ink pixels side by side in the group's squares (a rule
    under a running head, or a map's frame). Each square goes to the part
    between two cuts that holds most of its ink, the upper on a tie, and a
    part's squares that do not touch side by side are parts of their own.
    The first part's rows start at the top of the page and the last's end
    at its foot."""
    top = min(row for row, _ in group) * square_px
    bottom = (max(row for row, _ in group) + 1) * square_px
    columns: dict[int, list[int]] = {}
    for row, column in group:
        columns.setdefault(row, []).append(column)

    def inked_in_row(y: int) -> int:
        start = y * width_px
        return sum(
            ink.count(1, start + column * square_px, start + (column + 1) * square_px)
            for column in columns.get(y // square_px, ())
        )

    def longest_run(y: int) -> int:
        """The longest run of ink pixels side by side in pixel row `y`,
        counting only the pixels of the group's squares."""
        in_group = frozenset(columns.get(y // square_px, ()))
        longest = run = 0
        for x in range(width_px):
            if x // square_px in in_group and ink[y * width_px + x]:
                run += 1
                longest = max(longest, run)
            else:
                run = 0
        return longest

    counts = tuple(inked_in_row(y) for y in range(top, bottom))
    inked = tuple(index for index, count in enumerate(counts) if count > 0)

    def has_line(indices: range) -> bool:
        return any(
            0 <= index < len(counts) and longest_run(top + index) >= least_line_px
            for index in indices
        )

    cuts = []
    start = None
    for index in range(inked[0], inked[-1] + 1):
        if counts[index] == 0:
            start = index if start is None else start
            continue
        if (
            start is not None
            and index - start >= gap_px
            and (
                has_line(range(start - _LINE_ROWS, start))
                or has_line(range(index, index + _LINE_ROWS))
            )
        ):
            cuts.append(top + (start + index) // 2)
        start = None
    # The first part reaches the top of the page and the last its foot, so
    # that the band squares beyond them count for their boxes.
    page_bottom = len(ink) // width_px
    if not cuts:
        return ((group, (0, page_bottom)),)
    bounds = (0, *cuts, page_bottom)
    slabs = tuple(itertools.pairwise(bounds))

    def slab_of(square: Square) -> int:
        row, column = square
        left = column * square_px
        inks = tuple(
            sum(
                ink.count(1, y * width_px + left, y * width_px + left + square_px)
                for y in range(
                    max(upper, row * square_px), min(lower, (row + 1) * square_px)
                )
            )
            for upper, lower in slabs
        )
        return inks.index(max(inks))

    owners = {square: slab_of(square) for square in group}
    return tuple(
        (part, slab)
        for position, slab in enumerate(slabs)
        for part in _groups(
            frozenset(square for square, owner in owners.items() if owner == position)
        )
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
    rows: _PixelRows,
) -> _PixelBox | None:
    """The smallest box, in pixels, that holds every ink pixel of
    `squares` in the pixel rows `rows`; None when they hold none."""
    boxes = tuple(
        box
        for square in squares
        if (box := _square_ink_box(ink, width_px, square, square_px, rows)) is not None
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
    ink: bytes, width_px: int, square: Square, square_px: int, rows: _PixelRows
) -> _PixelBox | None:
    """The smallest box, in pixels, that holds the ink pixels of `square`
    in the pixel rows `rows`; None when it has none."""
    row, column = square
    top = row * square_px
    left = column * square_px
    lines = tuple(
        (y, ink[start : start + square_px])
        for y in range(max(top, rows[0]), min(top + square_px, rows[1]))
        if 1 in ink[(start := y * width_px + left) : start + square_px]
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
