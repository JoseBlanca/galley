"""Tests of the figures printed inside text pages (docs/specs/figures.md):
analyze's figure boxes (section 3), extract's cut (section 4) and layout's
figure regions (section 5), on values made in the test and on the excerpt
kadesh_29-38 (section 10).
"""

from galley.analyze import figure_boxes
from galley.model import Box, RenderedPage

# Figures spec section 10: a page of white, 300 by 450 pixels at 36 dpi,
# where a pixel is 2 pt and a square of 12 pt is 6 pixels.
_DPI = 36
_WIDTH_PX = 300
_HEIGHT_PX = 450
_SQUARE_PX = 6
_PT_PER_PX = 2.0
_KNOWN = frozenset({"the"})


def _page(*blocks: tuple[int, int, int, int]) -> RenderedPage:
    """A white page with each of `blocks`, (left, top, right, bottom) in
    pixels, ends excluded, in black."""
    pixels = bytearray(b"\xff" * (_WIDTH_PX * _HEIGHT_PX))
    for left, top, right, bottom in blocks:
        for row in range(top, bottom):
            pixels[row * _WIDTH_PX + left : row * _WIDTH_PX + right] = bytes(
                right - left
            )
    return RenderedPage(
        page_index=0,
        dpi=_DPI,
        width_px=_WIDTH_PX,
        height_px=_HEIGHT_PX,
        pixels=bytes(pixels),
    )


def _squares(left: int, top: int, columns: int, rows: int) -> tuple[int, int, int, int]:
    """A block of `columns` by `rows` squares from the square at column
    `left` and row `top`, in pixels."""
    return (
        left * _SQUARE_PX,
        top * _SQUARE_PX,
        (left + columns) * _SQUARE_PX,
        (top + rows) * _SQUARE_PX,
    )


def _in_points(block: tuple[int, int, int, int]) -> Box:
    left, top, right, bottom = block
    return Box(
        left * _PT_PER_PX, top * _PT_PER_PX, right * _PT_PER_PX, bottom * _PT_PER_PX
    )


def _word_in_square(text: str, column: int, row: int) -> tuple[str, Box]:
    """A word of 1 by 1 pt in the middle of the square at `column` and
    `row`: grown by 2 pt, it touches that square alone."""
    x = column * _SQUARE_PX * _PT_PER_PX + 5.5
    y = row * _SQUARE_PX * _PT_PER_PX + 5.5
    return text, Box(x, y, x + 1.0, y + 1.0)


def _word_across_row(row: int, left: int, right: int) -> tuple[str, Box]:
    """A word 1 pt high in the middle of square row `row`, from square
    column `left` to the end of column `right - 1`: grown by 2 pt, it
    touches the squares of that row alone."""
    y = row * _SQUARE_PX * _PT_PER_PX + 5.5
    return "x", Box(
        left * _SQUARE_PX * _PT_PER_PX + 1.0,
        y,
        right * _SQUARE_PX * _PT_PER_PX - 1.0,
        y + 1.0,
    )


def test_figure_boxes_a_block_of_144_squares_is_one_figure_with_its_box() -> None:
    block = _squares(10, 10, 12, 12)
    assert figure_boxes(_page(block), (), (), _KNOWN) == (_in_points(block),)


def test_figure_boxes_a_block_of_110_squares_is_no_figure() -> None:
    assert figure_boxes(_page(_squares(10, 10, 10, 11)), (), (), _KNOWN) == ()


def test_figure_boxes_a_block_with_13_known_words_is_no_figure() -> None:
    words = tuple(_word_in_square("the", 12 + index, 15) for index in range(13))
    assert figure_boxes(_page(_squares(10, 10, 20, 20)), words, (), _KNOWN) == ()


def test_figure_boxes_a_block_with_12_known_words_is_one_figure() -> None:
    block = _squares(10, 10, 20, 20)
    words = tuple(_word_in_square("the", 12 + index, 15) for index in range(12))
    assert figure_boxes(_page(block), words, (), _KNOWN) == (_in_points(block),)


def test_figure_boxes_unknown_words_are_not_counted() -> None:
    block = _squares(10, 10, 20, 20)
    words = tuple(_word_in_square("qzx", 12 + index, 15) for index in range(13))
    assert figure_boxes(_page(block), words, (), _KNOWN) == (_in_points(block),)


def test_figure_boxes_a_word_that_splits_a_block_into_two_small_groups_leaves_none() -> (
    None
):
    # 11 rows of 20: the word takes the middle row, leaving two groups of
    # 100 squares; without it the block is a figure of 220.
    block = _squares(10, 10, 20, 11)
    assert figure_boxes(_page(block), (), (), _KNOWN) == (_in_points(block),)
    word = _word_across_row(15, 10, 30)
    assert figure_boxes(_page(block), (word,), (), _KNOWN) == ()


def test_figure_boxes_an_excluded_regions_word_does_not_stop_the_squares() -> None:
    block = _squares(10, 10, 20, 11)
    word = _word_across_row(15, 10, 30)
    region = Box(100.0, 170.0, 380.0, 200.0)
    assert figure_boxes(_page(block), (word,), (region,), _KNOWN) == (
        _in_points(block),
    )


def test_figure_boxes_known_words_in_an_excluded_region_are_not_counted() -> None:
    block = _squares(10, 10, 20, 20)
    words = tuple(_word_in_square("the", 12 + index, 15) for index in range(13))
    region = Box(140.0, 175.0, 320.0, 195.0)
    assert figure_boxes(_page(block), words, (region,), _KNOWN) == (_in_points(block),)


def test_figure_boxes_a_band_inside_the_outer_band_does_not_change_the_box() -> None:
    block = _squares(10, 10, 12, 12)
    # 2 pt, one pixel, along the top of the page, apart from the block.
    band = (0, 0, _WIDTH_PX, 1)
    assert figure_boxes(_page(block, band), (), (), _KNOWN) == (_in_points(block),)


def test_figure_boxes_a_block_into_the_outer_band_reaches_its_left_side() -> None:
    # From pixel 3, inside the band's first square, to the end of square
    # column 13; the group's squares start at column 2.
    block = (3, 60, 14 * _SQUARE_PX, 132)
    assert figure_boxes(_page(block), (), (), _KNOWN) == (_in_points(block),)


def test_figure_boxes_a_block_into_the_outer_band_at_the_foot_reaches_its_bottom() -> (
    None
):
    # To the last pixel row; the band is the last two whole squares, rows
    # 73 and 74 of 75.
    block = (60, 300, 132, _HEIGHT_PX)
    assert figure_boxes(_page(block), (), (), _KNOWN) == (_in_points(block),)


def test_figure_boxes_two_blocks_one_square_apart_are_two_figures_by_their_tops() -> (
    None
):
    lower_left = _squares(3, 20, 12, 12)
    upper_right = _squares(16, 10, 12, 12)
    assert figure_boxes(_page(lower_left, upper_right), (), (), _KNOWN) == (
        _in_points(upper_right),
        _in_points(lower_left),
    )


def test_figure_boxes_squares_are_12_pt_at_72_dpi() -> None:
    # 12 by 10 squares of 12 pt, 120: a figure; at 72 dpi a pixel is 1 pt.
    width_px, height_px = 2 * _WIDTH_PX, 2 * _HEIGHT_PX
    page = RenderedPage(
        page_index=0,
        dpi=72,
        width_px=width_px,
        height_px=height_px,
        pixels=bytes(
            0 if 120 <= column < 264 and 120 <= row < 240 else 255
            for row in range(height_px)
            for column in range(width_px)
        ),
    )
    assert figure_boxes(page, (), (), _KNOWN) == (Box(120.0, 120.0, 264.0, 240.0),)
