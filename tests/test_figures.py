"""Tests of the figures printed inside text pages (docs/specs/figures.md):
analyze's figure boxes (section 3), extract's cut (section 4) and layout's
figure regions (section 5), on values made in the test and on the excerpt
kadesh_29-38 (section 10).
"""

import json
from pathlib import Path

import pytest
from PIL import Image

from galley.analyze import figure_boxes
from galley.book_folder import BookFolder
from galley.extract import figure_crop_px, figure_image, page_words
from galley.model import (
    Box,
    Figure,
    FigureKind,
    PageInfo,
    PageKind,
    RenderedPage,
    TextSource,
    Word,
    read_pages,
    read_words,
)

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


# extract's cut (figures spec section 4).


def _text_page(figure_boxes: tuple[Box, ...]) -> PageInfo:
    return PageInfo(
        index=25,
        width_pt=432.0,
        height_pt=648.0,
        kind=PageKind.TEXT,
        text_source=TextSource.TEXT_LAYER,
        text_layer_score=None,
        exclude_regions=(),
        figure_boxes=figure_boxes,
        blank_checked_by_ocr=False,
    )


_WORD = Word("text", Box(60.0, 500.0, 80.0, 510.0), None)


def test_cut_a_text_page_with_two_boxes_has_two_in_page_figures_in_order() -> None:
    upper = Box(40.0, 66.0, 300.0, 200.0)
    lower = Box(150.0, 300.0, 400.0, 450.0)
    words, removals = page_words(_text_page((upper, lower)), (_WORD,))
    assert words.figures == (
        Figure(
            box=upper,
            image="images/figure-0025-1.png",
            dpi=300,
            kind=FigureKind.IN_PAGE,
        ),
        Figure(
            box=lower,
            image="images/figure-0025-2.png",
            dpi=300,
            kind=FigureKind.IN_PAGE,
        ),
    )
    # No word is removed for a figure in extract.
    assert words.words == (_WORD,)
    assert removals == ()


def test_cut_a_text_page_without_boxes_has_no_figure() -> None:
    words, _ = page_words(_text_page(()), (_WORD,))
    assert words.figures == ()


def test_cut_a_plates_figure_is_of_kind_plate() -> None:
    plate = PageInfo(
        index=16,
        width_pt=432.0,
        height_pt=648.0,
        kind=PageKind.PLATE,
        text_source=TextSource.NONE,
        text_layer_score=None,
        exclude_regions=(),
        figure_boxes=(),
        blank_checked_by_ocr=False,
    )
    words, _ = page_words(plate, ())
    assert words.figures == (
        Figure(
            box=Box(0.0, 0.0, 432.0, 648.0),
            image="images/plate-0016.png",
            dpi=300,
            kind=FigureKind.PLATE,
        ),
    )


def test_cut_the_image_names_hold_the_page_index_in_4_digits_and_the_number() -> None:
    assert figure_image(7, 1) == "images/figure-0007-1.png"
    assert figure_image(1174, 12) == "images/figure-1174-12.png"


def test_cut_the_box_is_rounded_outwards_to_whole_pixels() -> None:
    # At 300 dpi a point is 25/6 pixels: 112 pt is 466.67 pixels, 398 pt
    # 1658.33, 192 pt 800 exactly.
    assert figure_crop_px(Box(112.0, 192.0, 398.0, 504.0), 300) == (
        466,
        800,
        1659,
        2100,
    )
    assert figure_crop_px(Box(0.1, 0.1, 0.2, 0.2), 72) == (0, 0, 1, 1)


# The excerpt kadesh_29-38 (figures spec section 10): Kadesh's page indices
# 29 to 38 are the excerpt's pages 0 to 9.

_KADESH = "kadesh_29-38"
_EXPECTED = Path(__file__).parent / "fixtures" / "expected" / "lists_figures"

# The figures' boxes, in points. The maps' frames and the block's ink were
# measured by eye on the 300 dpi render (the expected files of
# tests/fixtures/expected/lists_figures/); each box below was checked
# against them, and where it differs the rule of figures spec section 3,
# as written, is why:
# - 29, 36 and 38: the box holds the frame within 6 pt on three sides, and
#   at the foot runs on to the scale bars printed under the frame, picture
#   squares that touch the frame's.
# - 33: the same at the sides and the foot, where it takes in both scale
#   bars (the question left by the expected file: yes, by the rule). Its
#   top is 144 pt, 9.1 pt inside the frame's top rule at 134.9: the line
#   of text above ends 2.1 pt over the frame, and its words, grown by 2
#   pt, touch every square of the frame's top row.
# - 37: the block of hieroglyphs; its left side is 100 pt, 10 pt right of
#   the ink at 90.0, because the two "Var." words printed at its left edge
#   stop the squares they touch. Top, right and bottom are within 4 pt of
#   the ink (a pixel of the 36 dpi render is 2 pt).
_KADESH_BOXES = {
    0: (Box(112.0, 192.0, 398.0, 504.0),),
    4: (Box(56.0, 144.0, 288.0, 568.0),),
    7: (Box(50.0, 348.0, 178.0, 624.0),),
    8: (Box(100.0, 148.0, 408.0, 396.0),),
    9: (Box(58.0, 288.0, 180.0, 580.0),),
}
# The words of the text layer whose middle lies inside a figure's box, by
# excerpt page: layout takes them out as the figure's (figures spec
# section 5). 29's are the spec's (section 10). On 33 the words read on the
# scale bars, "JO Km." and "icM", are inside the box; on 36 "SM.", read on
# the miles scale bar; on 37 only the second "Var.", whose middle is at
# 100.5 pt, against the first's 98.7 and the box's left side at 100: by
# the rule as written, not a choice made here.
_KADESH_WORDS_INSIDE = {
    0: ("/ifr,yrafex*^Tx", "<•"),
    4: ("JO", "Km.", "icM"),
    7: ("SM.",),
    8: ("Var.",),
    9: (),
}


def _near(box: Box, expected: Box) -> bool:
    """Whether every side of `box` is within 1 pt of `expected`'s."""
    return all(
        abs(side - expected_side) <= 1.0
        for side, expected_side in zip(
            (box.x0, box.top, box.x1, box.bottom),
            (expected.x0, expected.top, expected.x1, expected.bottom),
            strict=True,
        )
    )


@pytest.mark.pandoc
@pytest.mark.tesseract
def test_kadesh_29_38_boxes_are_those_of_the_reference_pages(
    excerpt_books: frozendict[str, BookFolder],
) -> None:
    pages = read_pages(excerpt_books[_KADESH].pages_json).pages
    found = {page.index: page.figure_boxes for page in pages if page.figure_boxes}
    assert found.keys() == _KADESH_BOXES.keys()
    for index, boxes in _KADESH_BOXES.items():
        assert len(found[index]) == len(boxes)
        assert all(
            _near(box, expected) for box, expected in zip(found[index], boxes)
        ), (index, found[index])


def _frame(index: int) -> tuple[Box, float]:
    """The frame, or the ink extent, of the figure the expected file of
    excerpt page `index` measured by eye, and the bottom of what is printed
    under it (its scale bars), or the frame's bottom."""
    printed = json.loads(
        (_EXPECTED / f"{_KADESH}_page{index}.json").read_text(encoding="utf-8")
    )["printed"]["figures"][0]
    x0, top, x1, bottom = printed.get("frame_pt") or printed["ink_extent_pt"]
    under = printed.get("scale_bar_bottom_pt") or printed.get(
        "scale_bars_bottom_pt", bottom
    )
    return Box(x0, top, x1, bottom), float(under)


@pytest.mark.parametrize("index", [0, 4, 7, 9])
def test_kadesh_29_38_boxes_hold_each_maps_frame_and_its_scale_bars(
    index: int,
) -> None:
    (box,) = _KADESH_BOXES[index]
    frame, under = _frame(index)
    assert abs(box.x0 - frame.x0) <= 6.0
    assert abs(box.x1 - frame.x1) <= 6.0
    # 33's top: 9.1 pt inside the frame (see _KADESH_BOXES).
    assert abs(box.top - frame.top) <= (9.5 if index == 4 else 6.0)
    # Within 4 pt of the scale bars, as of the ink on 37.
    assert frame.bottom < box.bottom <= under + 4.0


def test_kadesh_29_38_box_of_the_hieroglyphs_lies_within_their_ink() -> None:
    (box,) = _KADESH_BOXES[8]
    ink, _ = _frame(8)
    assert ink.x0 + 9.0 <= box.x0 <= ink.x0 + 11.0
    assert abs(box.top - ink.top) <= 4.0
    assert abs(box.x1 - ink.x1) <= 4.0
    assert abs(box.bottom - ink.bottom) <= 4.0


@pytest.mark.pandoc
@pytest.mark.tesseract
def test_kadesh_29_38_boxes_take_in_the_words_read_on_the_pictures(
    excerpt_books: frozendict[str, BookFolder],
) -> None:
    words = read_words(excerpt_books[_KADESH].words_json).pages

    def inside(word: Word, box: Box) -> bool:
        middle_x = (word.box.x0 + word.box.x1) / 2
        middle_y = (word.box.top + word.box.bottom) / 2
        return box.x0 <= middle_x <= box.x1 and box.top <= middle_y <= box.bottom

    assert {
        index: tuple(
            word.text
            for word in words[index].words
            if any(inside(word, box) for box in boxes)
        )
        for index, boxes in _KADESH_BOXES.items()
    } == {
        index: tuple(sorted(texts, key=lambda text: _order(words[index].words, text)))
        for index, texts in _KADESH_WORDS_INSIDE.items()
    }


def _order(page_words: tuple[Word, ...], text: str) -> int:
    return next(
        position for position, word in enumerate(page_words) if word.text == text
    )


@pytest.mark.pandoc
@pytest.mark.tesseract
def test_kadesh_29_38_boxes_each_have_an_in_page_figure_and_its_image(
    excerpt_books: frozendict[str, BookFolder],
) -> None:
    folder = excerpt_books[_KADESH]
    pages = read_pages(folder.pages_json).pages
    words = read_words(folder.words_json).pages
    for page, page_of_words in zip(pages, words, strict=True):
        assert tuple(figure.box for figure in page_of_words.figures) == (
            page.figure_boxes
            if page.kind is PageKind.TEXT
            else tuple(figure.box for figure in page_of_words.figures)
        )
        for number, figure in enumerate(
            (
                figure
                for figure in page_of_words.figures
                if figure.kind is FigureKind.IN_PAGE
            ),
            start=1,
        ):
            assert figure.image == figure_image(page.index, number)
            assert figure.dpi == 300
            left, top, right, bottom = figure_crop_px(figure.box, 300)
            with Image.open(folder.root / figure.image) as image:
                assert image.mode == "L"
                assert image.size == (right - left, bottom - top)
    assert {
        page.index: tuple(figure.kind for figure in page.figures)
        for page in words
        if page.figures
    } == {
        **{index: (FigureKind.IN_PAGE,) for index in _KADESH_BOXES},
        5: (FigureKind.PLATE,),
        6: (FigureKind.PLATE,),
    }
