"""Tests of the figures printed inside text pages (docs/specs/figures.md):
analyze's figure boxes (section 3), extract's cut (section 4), layout's
figure regions and structure's figure text, captions and figure blocks
(section 5), on values made in the test and on the excerpt kadesh_29-38
(section 10).
"""

import functools
import json
import logging
import zipfile
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

import pytest
from PIL import Image

from galley import analyze
from galley.analyze import figure_boxes
from galley.book_folder import BookFolder
from galley.config import read_config
from galley.errors import FidelityBoundary
from galley.extract import _save_figures, figure_crop_px, figure_image, page_words
from galley.fidelity import check_stage
from galley.layout import figure_regions, layout_page_with_figures
from galley.model import (
    Block,
    BlockKind,
    BlocksFile,
    Box,
    Figure,
    FigureKind,
    Line,
    LinesFile,
    Origin,
    PageInfo,
    PageKind,
    PageLayout,
    PageWords,
    Region,
    RemovalReason,
    RenderedPage,
    TextSource,
    Word,
    block_text,
    read_blocks,
    read_lines,
    read_pages,
    read_words,
)
from galley.structure import is_caption_label, make_blocks

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


def test_figure_boxes_a_block_into_the_outer_band_at_the_top_reaches_its_top() -> None:
    # From pixel row 3, inside the band's first square; the group's squares
    # start at row 2.
    block = (60, 3, 132, 72)
    assert figure_boxes(_page(block), (), (), _KNOWN) == (_in_points(block),)


def test_figure_boxes_a_block_into_the_outer_band_at_the_right_reaches_its_side() -> (
    None
):
    # To pixel 297 of 300; the band is square columns 48 and 49.
    block = (160, 60, 297, 132)
    assert figure_boxes(_page(block), (), (), _KNOWN) == (_in_points(block),)


def test_figure_boxes_known_words_in_the_band_strip_are_not_counted() -> None:
    # 14 known words in square column 1, inside the band: in the box grown
    # into the band, not in the group's own box, which starts at column 2.
    block = (3, 60, 84, 132)
    words = tuple(
        ("the", Box(x, row * 12.0 + 5.5, x + 1.0, row * 12.0 + 6.5))
        for row in range(10, 17)
        for x in (15.0, 18.0)
    )
    assert figure_boxes(_page(block), words, (), _KNOWN) == (_in_points(block),)


def _striped(block: tuple[int, int, int, int]) -> tuple[tuple[int, int, int, int], ...]:
    """`block`, in pixels, as black columns one pixel wide on its even
    pixels: inked squares with no run of ink across, as rows of
    hieroglyphs have none."""
    left, top, right, bottom = block
    return tuple((x, top, x + 1, bottom) for x in range(left, right, 2))


# A striped block of 12 by 12 squares from square column 10 and row 12,
# and its ink's box: its last stripe ends at pixel 131.
_STRIPED = _striped(_squares(10, 12, 12, 12))
_STRIPED_BOX = _in_points((60, 72, 131, 144))


def test_figure_boxes_a_rule_6_pt_above_a_block_is_cut_off() -> None:
    # A rule of 80 pt, one pixel high in the square row above the block,
    # 3 pixels (6 pt) above its top: its squares join the block's.
    rule = (60, 68, 100, 69)
    assert figure_boxes(_page(*_STRIPED, rule), (), (), _KNOWN) == (_STRIPED_BOX,)


def test_figure_boxes_a_line_of_68_pt_above_a_block_is_not_cut_off() -> None:
    line = (60, 68, 94, 69)
    assert figure_boxes(_page(*_STRIPED, line), (), (), _KNOWN) == (
        replace(_STRIPED_BOX, top=136.0),
    )


def test_figure_boxes_a_rule_4_pt_above_a_block_is_not_cut_off() -> None:
    rule = (60, 69, 100, 70)
    assert figure_boxes(_page(*_STRIPED, rule), (), (), _KNOWN) == (
        replace(_STRIPED_BOX, top=138.0),
    )


# A figure shaped as an L lying on its back: 12 by 12 squares from square
# column 10 and row 10, and an arm of 6 by 2 squares on its right at the
# top; its box ends at pixel 168.
_FIGURE_L = (_squares(10, 10, 12, 12), _squares(22, 10, 6, 2))


def test_figure_boxes_a_small_group_with_its_middle_in_a_figures_box_grows_it() -> None:
    # 5 by 3 squares under the arm, apart from the figure: its middle, at
    # pixel 165, is inside the figure's box, its right side outside.
    part = _squares(25, 15, 5, 3)
    assert figure_boxes(_page(*_FIGURE_L, part), (), (), _KNOWN) == (
        _in_points((60, 60, 180, 132)),
    )


def test_figure_boxes_a_small_group_with_its_middle_outside_does_not_grow_it() -> None:
    # Its middle at pixel 177, right of the figure's box.
    part = _squares(27, 15, 5, 3)
    assert figure_boxes(_page(*_FIGURE_L, part), (), (), _KNOWN) == (
        _in_points((60, 60, 168, 132)),
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


@pytest.mark.thread_unsafe
def test_cut_a_box_past_the_render_is_clipped_with_a_warning_naming_the_page(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    # A render of 72 by 72 pixels at 72 dpi, and a box whose right side is
    # 8 pt past it.
    rendered = RenderedPage(
        page_index=25, dpi=72, width_px=72, height_px=72, pixels=bytes(72 * 72)
    )
    (tmp_path / "images").mkdir()
    with caplog.at_level(logging.WARNING, logger="galley.extract"):
        _save_figures(rendered, _text_page((Box(10.0, 10.0, 80.0, 30.0),)), tmp_path)
    with Image.open(tmp_path / figure_image(25, 1)) as image:
        assert image.size == (62, 20)
    assert [record.getMessage() for record in caplog.records] == [
        (
            "extract: page index 25, figure 1: its box (10.0, 10.0, 80.0, 30.0) "
            "pt runs past the page's render, 72 by 72 pixels at 72 dpi; the "
            "image is cut to the render"
        )
    ]


@pytest.mark.thread_unsafe
def test_cut_a_box_inside_the_render_logs_no_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    rendered = RenderedPage(
        page_index=25, dpi=72, width_px=72, height_px=72, pixels=bytes(72 * 72)
    )
    (tmp_path / "images").mkdir()
    with caplog.at_level(logging.WARNING, logger="galley.extract"):
        _save_figures(rendered, _text_page((Box(10.0, 10.0, 72.0, 30.0),)), tmp_path)
    assert caplog.records == []


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


@pytest.mark.thread_unsafe
def test_analyze_gives_a_front_matter_page_no_box_and_logs_each_page_with_figures(
    excerpt_book_toml: frozendict[str, str],
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    # The excerpt's page 0, Kadesh 29's map, made front matter by the
    # config: only a text page has figures (figures spec section 3).
    folder = BookFolder(tmp_path)
    folder.book_toml.write_text(
        f"{excerpt_book_toml[_KADESH]}front_matter_end = 1\n", encoding="utf-8"
    )
    with caplog.at_level(logging.INFO, logger="galley.analyze"):
        analyze.run(folder, read_config(folder.book_toml))
    pages = read_pages(folder.pages_json).pages
    assert pages[0].kind is PageKind.FRONT_MATTER
    assert {page.index: page.figure_boxes for page in pages if page.figure_boxes} == {
        index: boxes for index, boxes in _KADESH_BOXES.items() if index != 0
    }
    assert [
        record.getMessage()
        for record in caplog.records
        if record.levelno == logging.INFO and "in-page figures" in record.getMessage()
    ] == [
        (
            "analyze: page index 4 has 1 in-page figures: box (56.0, 144.0, 288.0, "
            "568.0) pt, 445 squares, 3 known words"
        ),
        (
            "analyze: page index 7 has 1 in-page figures: box (50.0, 348.0, 178.0, "
            "624.0) pt, 144 squares, 1 known words"
        ),
        (
            "analyze: page index 8 has 1 in-page figures: box (100.0, 148.0, 408.0, "
            "396.0) pt, 371 squares, 1 known words"
        ),
        (
            "analyze: page index 9 has 1 in-page figures: box (58.0, 288.0, 180.0, "
            "580.0) pt, 132 squares, 0 known words"
        ),
    ]


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


def _excerpt_boxes(folder: BookFolder) -> dict[int, tuple[Box, ...]]:
    """The figure boxes analyze gave the excerpt's pages, by page index."""
    return {
        page.index: page.figure_boxes
        for page in read_pages(folder.pages_json).pages
        if page.figure_boxes
    }


@pytest.mark.pandoc
@pytest.mark.tesseract
@pytest.mark.parametrize("index", [0, 4, 7, 9])
def test_kadesh_29_38_boxes_hold_each_maps_frame_and_its_scale_bars(
    index: int, excerpt_books: frozendict[str, BookFolder]
) -> None:
    (box,) = _excerpt_boxes(excerpt_books[_KADESH])[index]
    frame, under = _frame(index)
    assert abs(box.x0 - frame.x0) <= 6.0
    assert abs(box.x1 - frame.x1) <= 6.0
    # 33's top: 9.1 pt inside the frame (see _KADESH_BOXES).
    assert abs(box.top - frame.top) <= (9.5 if index == 4 else 6.0)
    # Within 4 pt of the scale bars, as of the ink on 37.
    assert frame.bottom < box.bottom <= under + 4.0


@pytest.mark.pandoc
@pytest.mark.tesseract
def test_kadesh_29_38_box_of_the_hieroglyphs_lies_within_their_ink(
    excerpt_books: frozendict[str, BookFolder],
) -> None:
    (box,) = _excerpt_boxes(excerpt_books[_KADESH])[8]
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
        # A text page's in-page figures are its boxes; no other page has one.
        assert tuple(
            figure.box
            for figure in page_of_words.figures
            if figure.kind is FigureKind.IN_PAGE
        ) == (page.figure_boxes if page.kind is PageKind.TEXT else ())
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


# Whole books (figures spec section 10, "Whole-book tests", analyze's part):
# the in-page figures analyze finds, by page index and count.
_KADESH_BOOK = "battleofkadeshst00breauoft"
# Figures spec section 2: Kadesh's 6 maps (29, 33, 36, 38, 41, 45) and its
# 11 groups of hieroglyphs or Arabic, 17 in all.
_WHOLE_BOOK_FIGURES = frozendict(
    {
        _KADESH_BOOK: frozendict(
            {
                20: 1,
                27: 2,
                29: 1,
                33: 1,
                36: 1,
                37: 1,
                38: 1,
                40: 1,
                41: 1,
                44: 2,
                45: 1,
                50: 1,
                51: 1,
                52: 1,
                53: 1,
            }
        ),
        "normansineuropea00hask": frozendict(),
        "earlyplantagenet01stub": frozendict(),
        "domesdaybook00maituoft": frozendict(),
        "catherinedemedic00mariuoft": frozendict(),
        "politicaltheorie00gieruoft": frozendict(),
    }
)


@pytest.fixture(scope="module")
def whole_book_analyzed(
    tmp_path_factory: pytest.TempPathFactory, whole_book_toml: frozendict[str, str]
) -> Callable[[str], tuple[PageInfo, ...]]:
    """A function that gives the pages of a whole book as analyze finds them
    with the configs of tests/conftest.py, by Internet Archive identifier,
    analyze run the first time a test asks for the book."""
    roots = frozendict(
        {book: tmp_path_factory.mktemp(book) for book in whole_book_toml}
    )

    @functools.cache
    def analyzed(book: str) -> tuple[PageInfo, ...]:
        folder = BookFolder(roots[book])
        folder.book_toml.write_text(whole_book_toml[book], encoding="utf-8")
        analyze.run(folder, read_config(folder.book_toml))
        return read_pages(folder.pages_json).pages

    return analyzed


@pytest.mark.whole_book
@pytest.mark.thread_unsafe
@pytest.mark.timeout(600)
@pytest.mark.parametrize("book", sorted(_WHOLE_BOOK_FIGURES))
def test_whole_book_analyze_finds_the_in_page_figures_of_section_2_and_no_other(
    book: str, whole_book_analyzed: Callable[[str], tuple[PageInfo, ...]]
) -> None:
    pages = whole_book_analyzed(book)
    assert {
        page.index: len(page.figure_boxes) for page in pages if page.figure_boxes
    } == _WHOLE_BOOK_FIGURES[book]
    assert all(page.kind is PageKind.TEXT for page in pages if page.figure_boxes)


# Whole Kadesh's boxes that steps 3 and 5 of figures spec section 3 make,
# checked by eye on the 144 dpi render on 18 November 2026: 40, 44 and 53
# without the rule under the running head; 41 the map alone, from its
# frame's top rule, without "19." and the hieroglyphs above it; 50 and 51
# with the right ends of their rows of hieroglyphs, which the words read
# on them cut off. 44's bottom is 4 pt above the ink of its last row, whose
# squares the words of the line below touch.
_WHOLE_KADESH_BOXES = frozendict(
    {
        40: (Box(104.0, 108.0, 430.0, 240.0),),
        41: (Box(54.0, 286.0, 180.0, 576.0),),
        44: (Box(72.0, 112.0, 420.0, 204.0), Box(122.0, 450.0, 392.0, 660.0)),
        50: (Box(106.0, 306.0, 400.0, 548.0),),
        51: (Box(102.0, 396.0, 430.0, 536.0),),
        53: (Box(78.0, 90.0, 458.0, 260.0),),
    }
)


@pytest.mark.whole_book
@pytest.mark.thread_unsafe
@pytest.mark.timeout(600)
def test_whole_kadesh_boxes_leave_out_rules_and_take_in_cut_off_parts(
    whole_book_analyzed: Callable[[str], tuple[PageInfo, ...]],
) -> None:
    pages = whole_book_analyzed(_KADESH_BOOK)
    for index, boxes in _WHOLE_KADESH_BOXES.items():
        found = pages[index].figure_boxes
        assert len(found) == len(boxes), index
        assert all(_near(box, expected) for box, expected in zip(found, boxes)), (
            index,
            found,
        )


# layout's figure regions (figures spec section 5, "layout: the figure's
# words kept apart").

_FIGURE = Figure(
    box=Box(100.0, 100.0, 300.0, 300.0),
    image="images/figure-0025-1.png",
    dpi=300,
    kind=FigureKind.IN_PAGE,
)


def _word(text: str, x0: float, top: float) -> Word:
    return Word(text, Box(x0, top, x0 + 20.0, top + 10.0), None)


def _words_page(words: tuple[Word, ...], figures: tuple[Figure, ...]) -> PageWords:
    return PageWords(
        index=25, text_source=TextSource.TEXT_LAYER, words=words, figures=figures
    )


_HEAD = _word("Head", 200.0, 40.0)
_ABOVE = _word("above", 60.0, 80.0)
_LABEL = _word("Kadesh", 150.0, 200.0)
_BESIDE = _word("beside", 320.0, 200.0)
_LABEL_2 = _word("Orontes", 200.0, 250.0)
_BELOW = _word("below", 60.0, 320.0)


def _line(*words: Word) -> Line:
    return Line(
        Box(
            min(word.box.x0 for word in words),
            min(word.box.top for word in words),
            max(word.box.x1 for word in words),
            max(word.box.bottom for word in words),
        ),
        words,
    )


def _region(*lines: Line) -> Region:
    return Region(
        Box(
            min(line.box.x0 for line in lines),
            min(line.box.top for line in lines),
            max(line.box.x1 for line in lines),
            max(line.box.bottom for line in lines),
        ),
        lines,
    )


def _layout(*regions: Region, figures: tuple[Figure, ...]) -> PageLayout:
    return PageLayout(25, regions, figures)


def test_figure_region_takes_the_words_inside_the_box_out_of_the_laid_out_lines() -> (
    None
):
    page = _words_page((_HEAD, _ABOVE, _LABEL, _BESIDE, _LABEL_2, _BELOW), (_FIGURE,))
    # The page as laid out with all its words: the label joined the line of
    # "beside", and the second label has a line of its own.
    laid_out = _layout(
        _region(_line(_HEAD)),
        _region(
            _line(_ABOVE),
            _line(_LABEL, _BESIDE),
            _line(_LABEL_2),
            _line(_BELOW),
        ),
        figures=(_FIGURE,),
    )
    assert figure_regions(page, laid_out) == _layout(
        _region(_line(_HEAD)),
        # The line of "beside" keeps its place, with the box of its word.
        _region(_line(_ABOVE), _line(_BESIDE), _line(_BELOW)),
        Region(_FIGURE.box, (_line(_LABEL), _line(_LABEL_2))),
        figures=(_FIGURE,),
    )


def test_figure_region_drops_a_region_left_with_no_line() -> None:
    page = _words_page((_HEAD, _ABOVE, _LABEL, _BELOW), (_FIGURE,))
    laid_out = _layout(
        _region(_line(_HEAD), _line(_ABOVE)),
        _region(_line(_LABEL)),
        _region(_line(_BELOW)),
        figures=(_FIGURE,),
    )
    assert figure_regions(page, laid_out) == _layout(
        _region(_line(_HEAD), _line(_ABOVE)),
        _region(_line(_BELOW)),
        Region(_FIGURE.box, (_line(_LABEL),)),
        figures=(_FIGURE,),
    )


def test_figure_region_leaves_a_word_of_the_first_row_with_the_page() -> None:
    # The figure's box reaches the top of the page: its first row, inside
    # the box, may be the head line.
    figure = Figure(
        box=Box(100.0, 20.0, 300.0, 300.0),
        image=_FIGURE.image,
        dpi=300,
        kind=FigureKind.IN_PAGE,
    )
    page = _words_page((_HEAD, _LABEL, _BELOW), (figure,))
    laid_out = _layout(
        _region(_line(_HEAD)), _region(_line(_LABEL), _line(_BELOW)), figures=(figure,)
    )
    assert figure_regions(page, laid_out) == _layout(
        _region(_line(_HEAD)),
        _region(_line(_BELOW)),
        Region(figure.box, (_line(_LABEL),)),
        figures=(figure,),
    )


def test_figure_region_none_for_a_figure_with_no_word_inside() -> None:
    page = _words_page((_HEAD, _ABOVE, _BELOW), (_FIGURE,))
    laid_out = _layout(
        _region(_line(_HEAD), _line(_ABOVE), _line(_BELOW)), figures=(_FIGURE,)
    )
    assert figure_regions(page, laid_out) == laid_out


def test_figure_region_none_for_a_word_a_rereading_replaced() -> None:
    # A kept re-reading replaced the label: it is in no line, and nothing
    # is taken for it.
    page = _words_page((_HEAD, _ABOVE, _LABEL, _BELOW), (_FIGURE,))
    laid_out = _layout(
        _region(_line(_HEAD), _line(_ABOVE), _line(_BELOW)), figures=(_FIGURE,)
    )
    assert figure_regions(page, laid_out) == laid_out


def test_figure_region_none_on_a_plate() -> None:
    plate = Figure(
        box=Box(0.0, 0.0, 432.0, 648.0),
        image="images/plate-0025.png",
        dpi=300,
        kind=FigureKind.PLATE,
    )
    page = _words_page((_HEAD, _LABEL, _BELOW), (plate,))
    laid_out = _layout(
        _region(_line(_HEAD), _line(_LABEL), _line(_BELOW)), figures=(plate,)
    )
    assert figure_regions(page, laid_out) == laid_out


def test_figure_region_a_word_inside_two_boxes_goes_to_the_first_figure() -> None:
    second = Figure(
        box=Box(140.0, 190.0, 400.0, 400.0),
        image="images/figure-0025-2.png",
        dpi=300,
        kind=FigureKind.IN_PAGE,
    )
    page = _words_page((_HEAD, _LABEL, _BESIDE), (_FIGURE, second))
    laid_out = _layout(
        _region(_line(_HEAD), _line(_LABEL, _BESIDE)), figures=(_FIGURE, second)
    )
    assert figure_regions(page, laid_out) == _layout(
        _region(_line(_HEAD)),
        Region(_FIGURE.box, (_line(_LABEL),)),
        Region(second.box, (_line(_BESIDE),)),
        figures=(_FIGURE, second),
    )


def test_figure_region_follows_the_pages_regions_and_keeps_the_figures() -> None:
    page = _words_page((_HEAD, _ABOVE, _LABEL, _BESIDE, _BELOW), (_FIGURE,))
    layout, records = layout_page_with_figures(page, None, None)
    # Without measures the page is one region, laid out with the label,
    # which joined the line of "beside" and is then taken out of it.
    assert layout == _layout(
        _region(_line(_HEAD), _line(_ABOVE), _line(_BESIDE), _line(_BELOW)),
        Region(_FIGURE.box, (_line(_LABEL),)),
        figures=(_FIGURE,),
    )
    assert records == ()


# Whole Kadesh page 52: hieroglyphs printed among its footnotes, in the
# figure box (70, 442, 408, 544). Its regions outside the figure, each as
# its line count, first line and last line, are those layout made on main
# (83f2754, before in-page figures) less the words read in the hieroglyphs
# (figures spec section 5); with the figure's words taken out before the
# layout, its 7 footnotes became 4, their text reordered.
_KADESH_52_REGIONS = (
    (1, "JAMES HENRY BREASTED 37", "JAMES HENRY BREASTED 37"),
    (
        26,
        (
            "another with him, and he found that 2,500 spans of chariotry had "
            "surrounded him m in four"
        ),
        "30. &",
    ),
    (
        10,
        "UJ",
        "nobles, his infantry, and his chariotry. He overthrew them",
    ),
    (
        8,
        "'>' Ramses himself repeats this statement, Poem, 1, 88.",
        "IV and VI.",
    ),
    (
        1,
        'prostrate upon thoir faces; he hurled them, etc ." as above. 115',
        'prostrate upon thoir faces; he hurled them, etc ." as above. 115',
    ),
)


@pytest.mark.whole_book
@pytest.mark.thread_unsafe
@pytest.mark.timeout(600)
def test_whole_kadesh_52_regions_outside_the_figure_are_those_laid_out_with_all_words(
    whole_book_run: Callable[[str], BookFolder],
) -> None:
    folder = whole_book_run(_KADESH_BOOK)
    page = read_lines(folder.lines_json).pages[52]
    boxes = tuple(figure.box for figure in page.figures)
    assert boxes == (Box(70.0, 442.0, 408.0, 544.0),)

    def text(line: Line) -> str:
        return " ".join(word.text for word in line.words)

    assert (
        tuple(
            (len(region.lines), text(region.lines[0]), text(region.lines[-1]))
            for region in page.regions
            if region.box not in boxes
        )
        == _KADESH_52_REGIONS
    )
    # Its notes: the five printed, without the two that main made of the
    # hieroglyphs' words.
    notes = tuple(
        note
        for note in read_blocks(folder.blocks_json).notes
        if note.id.startswith("n-p0052-")
    )
    assert tuple(note.blocks[0].spans[0].text[:20] for note in notes) == (
        "; himself makes a si",
        "l*>The omitted porti",
        "'>' Ramses himself r",
        'i" They will be take',
        "l» Abn Simbel: CHAMP",
    )


@pytest.mark.pandoc
@pytest.mark.tesseract
def test_kadesh_29_38_figure_regions_hold_the_words_read_on_the_pictures(
    excerpt_books: frozendict[str, BookFolder],
) -> None:
    folder = excerpt_books[_KADESH]
    lines = read_lines(folder.lines_json)
    regions = {
        page.index: tuple(
            word.text
            for region in page.regions
            if region.box in tuple(figure.box for figure in page.figures)
            for line in region.lines
            for word in line.words
        )
        for page in lines.pages
        if page.index in _KADESH_BOXES
    }
    # Each figure with words has one region, whose box is the figure's.
    assert {
        page.index: sum(
            region.box in tuple(figure.box for figure in page.figures)
            for region in page.regions
        )
        for page in lines.pages
        if page.index in _KADESH_BOXES
    } == {index: 1 if words else 0 for index, words in _KADESH_WORDS_INSIDE.items()}
    assert {index: sorted(words) for index, words in regions.items()} == {
        index: sorted(words) for index, words in _KADESH_WORDS_INSIDE.items()
    }
    # The figures go through with their kind; no figure's region is re-read.
    assert {
        page.index: tuple(figure.kind for figure in page.figures)
        for page in lines.pages
        if page.figures
    } == {
        **{index: (FigureKind.IN_PAGE,) for index in _KADESH_BOXES},
        5: (FigureKind.PLATE,),
        6: (FigureKind.PLATE,),
    }
    # No record reads or replaces a word whose middle lies in a figure.
    boxes = {page.index: tuple(f.box for f in page.figures) for page in lines.pages}
    assert not any(
        box.x0 <= (word.box.x0 + word.box.x1) / 2 <= box.x1
        and box.top <= (word.box.top + word.box.bottom) / 2 <= box.bottom
        for record in lines.rereads
        for word in (*record.layer_words, *record.ocr_words)
        for box in boxes[record.page_index]
    )


# structure: the figure text, the caption and the figure block's place
# (figures spec section 5; the unit tests of section 10), on lines.json
# made here. A word is 5 pt a character and 10 pt tall, one character
# apart, and a line 14 pt below the one before.

_CHARACTER_PT = 5.0
_WORD_TALL_PT = 10.0
_NO_WORD_LIST: frozenset[str] = frozenset()


def _text_words(text: str, x0: float, top: float) -> tuple[Word, ...]:
    words = []
    left = x0
    for part in text.split(" "):
        right = left + _CHARACTER_PT * len(part)
        words.append(Word(part, Box(left, top, right, top + _WORD_TALL_PT), None))
        left = right + _CHARACTER_PT
    return tuple(words)


def _text_line(text: str, x0: float, top: float, x1: float | None = None) -> Line:
    """A line of `text` from `x0`, its words spread to end at `x1` when
    given."""
    words = _text_words(text, x0, top)
    if x1 is not None and len(words) > 1:
        spare = (x1 - words[-1].box.x1) / (len(words) - 1)
        words = tuple(
            Word(
                word.text,
                Box(
                    word.box.x0 + number * spare,
                    top,
                    word.box.x1 + number * spare,
                    top + _WORD_TALL_PT,
                ),
                None,
            )
            for number, word in enumerate(words)
        )
    return _line(*words)


def _in_page(index: int, box: Box, number: int = 1) -> Figure:
    return Figure(
        box=box,
        image=f"images/figure-{index:04d}-{number}.png",
        dpi=300,
        kind=FigureKind.IN_PAGE,
    )


def _lines_file(*pages: PageLayout) -> LinesFile:
    return LinesFile(source_pdf_sha256="0" * 64, pages=pages, rereads=())


def _structure(
    lines: LinesFile, word_list: frozenset[str] = _NO_WORD_LIST
) -> BlocksFile:
    blocks = make_blocks(lines, word_list, workers=1)
    check_stage(FidelityBoundary.STRUCTURE, lines, blocks)
    return blocks


def _texts(blocks: BlocksFile) -> tuple[tuple[BlockKind, str], ...]:
    return tuple((block.kind, block_text(block)) for block in blocks.blocks)


_MAP_BOX = Box(100.0, 145.0, 320.0, 290.0)
_ABOVE_THE_MAP = (
    _text_line("The text of the paragraph begins here and", 75.0, 100.0, 360.0),
    _text_line("goes on along the line to the very end of", 60.0, 114.0, 360.0),
    _text_line("the line before the figure printed in it, the", 60.0, 128.0, 360.0),
)
_BELOW_THE_MAP = (
    _text_line("picture, and then it goes on after it as it", 60.0, 330.0, 360.0),
    _text_line("did, to its end.", 60.0, 344.0),
)
_CAPTION_UNDER_THE_MAP = (
    _text_line("figure 2. A picture of the", 100.0, 296.0),
    _text_line("place.", 100.0, 309.0),
)
_MAP_REGION = _region(_line(_word("Orontes", 150.0, 200.0)))


def _map_page(
    above: tuple[Line, ...] = _ABOVE_THE_MAP, below: tuple[Line, ...] = _BELOW_THE_MAP
) -> PageLayout:
    """A page whose paragraph the map cuts, the caption under the map and a
    word read on it, laid out as layout gives it: the body region with the
    caption among its lines, then the map's region, whose box is the
    map's."""
    return PageLayout(
        0,
        (
            _region(*above, *_CAPTION_UNDER_THE_MAP, *below),
            Region(_MAP_BOX, _MAP_REGION.lines),
        ),
        (_in_page(0, _MAP_BOX),),
    )


def test_caption_rows_below_a_figure_join_the_paragraph_it_cuts() -> None:
    blocks = _structure(_lines_file(_map_page()))
    assert _texts(blocks) == (
        (
            BlockKind.PARAGRAPH,
            (
                "The text of the paragraph begins here and goes on along the "
                "line to the very end of the line before the figure printed in "
                "it, the picture, and then it goes on after it as it did, to "
                "its end."
            ),
        ),
        (BlockKind.FIGURE, "figure 2. A picture of the place."),
    )
    figure = blocks.blocks[1]
    assert figure.figure == "images/figure-0000-1.png"
    # Its origin holds the map and its caption.
    assert figure.origin == (Origin(0, Box(100.0, 145.0, 320.0, 319.0)),)


def test_figure_text_the_words_of_a_figures_region_are_removed_one_per_line() -> None:
    blocks = _structure(_lines_file(_map_page()))
    assert tuple(
        (removal.reason, removal.text)
        for removal in blocks.removals
        if removal.reason is RemovalReason.FIGURE_TEXT
    ) == ((RemovalReason.FIGURE_TEXT, "Orontes"),)


def test_caption_rows_a_hyphen_before_the_figure_joins_the_word_after_it() -> None:
    above = (
        *_ABOVE_THE_MAP[:2],
        _text_line("the line before the figure printed in it, the pic-", 60.0, 128.0),
    )
    below = (
        _text_line("ture, and then it goes on after it as it", 60.0, 330.0, 360.0),
        _BELOW_THE_MAP[1],
    )
    blocks = _structure(_lines_file(_map_page(above, below)), frozenset({"picture"}))
    assert tuple(block.kind for block in blocks.blocks) == (
        BlockKind.PARAGRAPH,
        BlockKind.FIGURE,
    )
    assert "the picture, and then" in block_text(blocks.blocks[0])


def test_caption_rows_below_a_figure_leave_the_body_words_of_their_row() -> None:
    # Kadesh 38: the map's caption and the line of text set beside the map
    # are one line of layout's.
    box = Box(60.0, 145.0, 200.0, 290.0)
    beside = tuple(
        _text_line(f"words set beside the map {n} go", 215.0, 146.0 + 14 * n, 360.0)
        for n in range(11)
    )
    shared = _line(
        *_text_words("MAP vi. Third Positions", 60.0, 300.0),
        *_text_words("Shabtuna and the camp", 215.0, 300.0),
    )
    page = PageLayout(
        0,
        (_region(*_ABOVE_THE_MAP, *beside, shared, *_BELOW_THE_MAP),),
        (_in_page(0, box),),
    )
    blocks = _structure(_lines_file(page))
    assert tuple(block.kind for block in blocks.blocks) == (
        BlockKind.PARAGRAPH,
        BlockKind.FIGURE,
    )
    assert block_text(blocks.blocks[1]) == "MAP vi. Third Positions"
    assert "go Shabtuna and the camp picture," in block_text(blocks.blocks[0])


def test_caption_rows_beside_a_figure_end_at_a_row_more_than_20_pt_below() -> None:
    # Haynes: a caption in a narrow column right of the picture, the next
    # row of text 26 pt below its last.
    box = Box(60.0, 145.0, 200.0, 290.0)
    caption = (
        _text_line("figure 4. The", 215.0, 150.0),
        _text_line("view from the", 215.0, 163.0),
        _text_line("hill.", 215.0, 176.0),
    )
    beside = _text_line("and beside it", 215.0, 202.0)
    page = PageLayout(
        0,
        (_region(*_ABOVE_THE_MAP, *caption, beside, *_BELOW_THE_MAP),),
        (_in_page(0, box),),
    )
    blocks = _structure(_lines_file(page))
    assert block_text(blocks.blocks[1]) == "figure 4. The view from the hill."
    assert "the and beside it picture," in block_text(blocks.blocks[0])


def test_caption_rows_beside_a_figure_take_their_words_on_its_side() -> None:
    # Turney 175: the caption's last row is one line with lettering printed
    # under the picture, and a row of the lettering alone lies 2.6 pt above
    # it.
    box = Box(12.0, 200.0, 268.0, 372.0)
    caption = (
        _text_line("15. The perfect", 288.0, 316.0),
        _text_line("baby, and the", 288.0, 330.0),
        _text_line("product of", 288.0, 344.0),
    )
    lettering = _text_line("BROWN, bright-eyed", 40.0, 355.8)
    shared = _line(
        *_text_words("rictcn ay", 60.0, 358.4),
        *_text_words("this new person.", 292.0, 358.4),
    )
    page = PageLayout(
        0,
        (_region(*_ABOVE_THE_MAP, *caption, lettering, shared),),
        (_in_page(0, box),),
    )
    blocks = _structure(_lines_file(page))
    assert _texts(blocks) == (
        (
            BlockKind.PARAGRAPH,
            (
                "The text of the paragraph begins here and goes on along the "
                "line to the very end of the line before the figure printed in "
                "it, the BROWN, bright-eyed rictcn ay"
            ),
        ),
        (BlockKind.FIGURE, "15. The perfect baby, and the product of this new person."),
    )


def test_figure_text_a_head_line_inside_a_figure_is_removed() -> None:
    # Turney 174: the lettering at the top of a cover is the page's first
    # row, which layout keeps out of the figure's region.
    box = Box(40.0, 34.0, 272.0, 356.0)
    head = _text_line("Inside: Crisis", 85.0, 43.0)
    caption = (
        _text_line("14 (a) A cover", 280.0, 185.0),
        _text_line("and (b) another.", 280.0, 199.0),
    )
    page = PageLayout(
        0,
        (_region(head), _region(*caption), Region(box, _MAP_REGION.lines)),
        (_in_page(0, box),),
    )
    blocks = _structure(_lines_file(page))
    assert _texts(blocks) == ((BlockKind.FIGURE, "14 (a) A cover and (b) another."),)
    assert tuple(
        removal.text
        for removal in blocks.removals
        if removal.reason is RemovalReason.FIGURE_TEXT
    ) == ("Inside: Crisis", "Orontes")


def test_figure_text_a_figures_region_is_not_the_pages_widest_region() -> None:
    # Text set right of a wide picture, 90 pt wide: narrower than a quarter
    # of the picture's 440 pt, it would be a margin note; it is a quarter
    # of the body region's 300 pt or more, and is body text.
    box = Box(40.0, 420.0, 480.0, 600.0)
    beside = _text_line("set right of the", 490.0, 500.0, 580.0)
    page = PageLayout(
        0,
        (
            _region(*_ABOVE_THE_MAP),
            _region(beside),
            Region(box, (_line(_word("Orontes", 150.0, 500.0)),)),
        ),
        (_in_page(0, box),),
    )
    blocks = _structure(_lines_file(page))
    assert BlockKind.MARGIN_NOTE not in tuple(block.kind for block in blocks.blocks)


def test_figure_text_a_page_with_two_in_page_figures_is_a_text_page() -> None:
    # The plate rules refuse a page with two figures; in-page figures are
    # not a plate's.
    first, second = Box(60.0, 145.0, 200.0, 290.0), Box(220.0, 145.0, 360.0, 290.0)
    page = PageLayout(
        0,
        (_region(*_ABOVE_THE_MAP, *_BELOW_THE_MAP),),
        (_in_page(0, first, 1), _in_page(0, second, 2)),
    )
    blocks = _structure(_lines_file(page))
    assert tuple((block.kind, block.figure) for block in blocks.blocks) == (
        (BlockKind.PARAGRAPH, None),
        (BlockKind.FIGURE, "images/figure-0000-1.png"),
        (BlockKind.FIGURE, "images/figure-0000-2.png"),
    )


def test_figure_place_inside_a_list_is_after_its_last_item() -> None:
    # Structure spec section 29's Haynes geometry: dash items at 37.9 pt,
    # hung 12.5 pt; the figure printed between the two items does not end
    # the list (rule 5), and its block comes after the list.
    box = Box(60.0, 150.0, 300.0, 260.0)
    lines = (
        _text_line(
            "The figures of the scientist in the stories are", 37.9, 60.0, 300.0
        ),
        _text_line("grouped around two recurrent stereotypes:", 37.9, 74.0, 260.0),
        _text_line("—The first item starts here and", 37.9, 102.0, 300.0),
        _text_line("it goes on here to the end", 50.4, 116.0, 250.0),
        _text_line("—The second item starts here and", 37.9, 270.0, 300.0),
        _text_line("it goes on here to the end", 50.4, 284.0, 250.0),
        _text_line("The paragraph after it 0 goes on", 37.9, 312.0, 322.0),
    )
    page = PageLayout(0, (_region(*lines),), (_in_page(0, box),))
    blocks = _structure(_lines_file(page))
    assert tuple(block.kind for block in blocks.blocks) == (
        BlockKind.PARAGRAPH,
        BlockKind.LIST_ITEM,
        BlockKind.LIST_ITEM,
        BlockKind.FIGURE,
        BlockKind.PARAGRAPH,
    )
    assert blocks.blocks[3].spans == ()


def test_figure_place_before_any_body_line_is_first() -> None:
    box = Box(60.0, 40.0, 300.0, 90.0)
    page = PageLayout(0, (_region(*_ABOVE_THE_MAP),), (_in_page(0, box),))
    blocks = _structure(_lines_file(page))
    assert tuple(block.kind for block in blocks.blocks) == (
        BlockKind.FIGURE,
        BlockKind.PARAGRAPH,
    )


def test_figure_place_at_a_pages_top_is_after_the_paragraph_from_the_page_before() -> (
    None
):
    # Haynes' figure 2, printed at the top of page 25 inside the paragraph
    # that runs from page 24.
    box = Box(60.0, 40.0, 300.0, 90.0)
    first = PageLayout(0, (_region(*_ABOVE_THE_MAP),), ())
    second = PageLayout(
        1,
        (
            _region(
                *_BELOW_THE_MAP,
                _text_line("A new paragraph starts here and", 75.0, 358.0, 360.0),
                _text_line("ends.", 60.0, 372.0),
            ),
        ),
        (_in_page(1, box),),
    )
    blocks = _structure(_lines_file(first, second))
    assert tuple(
        (block.kind, tuple(origin.page_index for origin in block.origin))
        for block in blocks.blocks
    ) == (
        (BlockKind.PARAGRAPH, (0, 1)),
        (BlockKind.FIGURE, (1,)),
        (BlockKind.PARAGRAPH, (1,)),
    )


@pytest.mark.parametrize(
    "words",
    [
        ("figure", "2."),
        ("FIGURE", "l6."),
        ("figure", "li."),
        ("MAP", "111."),
        ("MAP", "vi."),
        ("13.", "The"),
        ("14", "(a)"),
        ("2.", "(top)"),
        ("2i.", "The"),
        ("M", "FIGURE", "25."),
    ],
)
def test_caption_label_is_found(words: tuple[str, ...]) -> None:
    assert is_caption_label(words)


@pytest.mark.parametrize(
    "words",
    [
        # A line inside Turney 179's caption.
        ("figure", "drawn"),
        ("Figure",),
        ("8.",),
        # Kadesh's numbers of inscriptions beside its maps.
        ("12.", "n", "lie"),
        ("L.", "P.", "H.,"),
        ("1066.", "The"),
        ("In", "1066"),
    ],
)
def test_caption_label_is_not_found(words: tuple[str, ...]) -> None:
    assert not is_caption_label(words)


# structure on the excerpt kadesh_29-38 (figures spec section 10, the table
# of the reference pages): the expected output of each page is that of its
# file in tests/fixtures/expected/lists_figures/, checked against the page
# rendered at 300 dpi.


def _expected_page(index: int) -> dict[str, Any]:
    return json.loads(
        (_EXPECTED / f"{_KADESH}_page{index}.json").read_text(encoding="utf-8")
    )["expected"]


def _in_page_blocks(blocks: BlocksFile) -> dict[int, list[Block]]:
    """The figure blocks of in-page figures, by excerpt page."""
    found: dict[int, list[Block]] = {}
    for block in blocks.blocks:
        if block.kind is BlockKind.FIGURE and "/figure-" in (block.figure or ""):
            found.setdefault(block.origin[0].page_index, []).append(block)
    return found


def _excerpt_blocks(folder: BookFolder) -> BlocksFile:
    return read_blocks(folder.blocks_json)


@pytest.mark.pandoc
@pytest.mark.tesseract
def test_kadesh_29_38_each_reference_page_has_its_figures_with_their_captions(
    excerpt_books: frozendict[str, BookFolder],
) -> None:
    blocks = _excerpt_blocks(excerpt_books[_KADESH])
    found = _in_page_blocks(blocks)
    expected = {
        index: tuple(
            figure["caption"]
            for figure in _expected_page(index)["figures"]
            if figure["kind"] == "in_page"
        )
        for index in range(10)
    }
    assert {
        index: tuple(block_text(block) or None for block in found.get(index, ()))
        for index in range(10)
    } == expected
    # The plates of pages 34 and 35 stay plates' figure blocks.
    assert tuple(
        block.figure
        for block in blocks.blocks
        if block.kind is BlockKind.FIGURE and "/plate-" in (block.figure or "")
    ) == ("images/plate-0005.png", "images/plate-0006.png")


@pytest.mark.pandoc
@pytest.mark.tesseract
def test_kadesh_29_38_figure_text_is_the_words_read_inside_each_figure(
    excerpt_books: frozendict[str, BookFolder],
) -> None:
    removals = _excerpt_blocks(excerpt_books[_KADESH]).removals
    assert {
        index: tuple(
            word
            for removal in removals
            if removal.page_index == index
            and removal.reason is RemovalReason.FIGURE_TEXT
            for word in removal.text.split(" ")
        )
        for index in range(10)
    } == {
        index: tuple(
            word
            for figure in _expected_page(index)["figures"]
            for word in figure.get("figure_text") or ()
        )
        for index in range(10)
    }


@pytest.mark.pandoc
@pytest.mark.tesseract
@pytest.mark.parametrize("index", [0, 4, 7, 8, 9])
def test_kadesh_29_38_figure_follows_the_block_of_the_line_printed_above_it(
    index: int, excerpt_books: frozendict[str, BookFolder]
) -> None:
    blocks = _excerpt_blocks(excerpt_books[_KADESH]).blocks
    expected = _expected_page(index)
    above = expected.get("figure_after_the_paragraph_holding") or expected.get(
        "figure_after_the_block_holding"
    )
    assert isinstance(above, str)
    (figure,) = _in_page_blocks(_excerpt_blocks(excerpt_books[_KADESH]))[index]
    position = blocks.index(figure)
    # The block before it, past the figure blocks placed after the same one.
    before = next(
        block
        for block in reversed(blocks[:position])
        if block.kind is not BlockKind.FIGURE
    )
    assert above in " ".join(span.text for span in before.spans)


@pytest.mark.pandoc
@pytest.mark.tesseract
def test_kadesh_29_38_the_paragraph_cut_by_a_map_is_one_block(
    excerpt_books: frozendict[str, BookFolder],
) -> None:
    blocks = _excerpt_blocks(excerpt_books[_KADESH]).blocks
    expected = _expected_page(0)
    before, after = expected["one_paragraph_across_the_figure"]
    (paragraph,) = (block for block in blocks if before in block_text(block))
    assert paragraph.kind is BlockKind.PARAGRAPH
    text = block_text(paragraph)
    # The junk read on the scale bar, outside the box, stays text between.
    assert after in text
    assert f"{before} {' '.join(expected['stay_text'])} {after}" in text


@pytest.mark.pandoc
@pytest.mark.tesseract
def test_kadesh_29_38_text_on_a_captions_row_stays_where_it_is(
    excerpt_books: frozendict[str, BookFolder],
) -> None:
    blocks = _excerpt_blocks(excerpt_books[_KADESH])
    texts = tuple(
        (block.kind, block_text(block), block.origin[0].page_index)
        for block in blocks.blocks
    )
    # 36: the caption on the row of a footnote; the footnote keeps its words.
    footnotes = tuple(
        " ".join(block_text(block) for block in note.blocks)
        for note in blocks.notes
        if note.origin[0].page_index == 7
    )
    assert any(_expected_page(7)["kept_in_footnote"] in note for note in footnotes)
    # 38: the caption on one line with the text set beside the map.
    assert any(
        kind is BlockKind.PARAGRAPH
        and page == 9
        and _expected_page(9)["stays_in_its_paragraph"] in text
        for kind, text, page in texts
    )
    # 37: the "Var." outside the hieroglyphs' box.
    assert (BlockKind.PARAGRAPH, "Var.", 8) in texts


@pytest.mark.pandoc
@pytest.mark.tesseract
@pytest.mark.epubcheck
@pytest.mark.thread_unsafe
def test_kadesh_29_38_epub_shows_each_figure_with_its_caption_and_passes_epubcheck(
    excerpt_books: frozendict[str, BookFolder], check_epubs: Callable[..., None]
) -> None:
    folder = excerpt_books[_KADESH]
    figures = tuple(
        block
        for blocks in _in_page_blocks(_excerpt_blocks(folder)).values()
        for block in blocks
    )
    assert len(figures) == 5
    xhtml = "{http://www.w3.org/1999/xhtml}"
    with zipfile.ZipFile(folder.book_epub) as epub:
        divs = {
            div.get("id"): div
            for name in sorted(epub.namelist())
            if name.startswith("EPUB/text/") and name.endswith(".xhtml")
            for div in ElementTree.fromstring(epub.read(name)).iter(f"{xhtml}div")
        }
    for block in figures:
        div = divs[block.id]
        assert len(tuple(div.iter(f"{xhtml}img"))) == 1, block.id
        captions = tuple(div.iter(f"{xhtml}figcaption"))
        assert tuple("".join(caption.itertext()) for caption in captions) == (
            (block_text(block),) if block.spans else ()
        ), block.id
    check_epubs(folder.book_epub)


# Whole books (figures spec section 10, "Whole-book tests", structure's
# part): a figure block for each in-page figure analyze finds, by page; the
# fidelity check passes on each book.


@pytest.mark.whole_book
@pytest.mark.thread_unsafe
@pytest.mark.timeout(600)
@pytest.mark.parametrize("book", sorted(_WHOLE_BOOK_FIGURES))
def test_whole_book_figure_blocks_are_one_for_each_in_page_figure(
    book: str, whole_book_run: Callable[[str], BookFolder]
) -> None:
    folder = whole_book_run(book)
    blocks = read_blocks(folder.blocks_json)
    check_stage(FidelityBoundary.STRUCTURE, read_lines(folder.lines_json), blocks)
    found = _in_page_blocks(blocks)
    assert {index: len(figures) for index, figures in found.items()} == (
        _WHOLE_BOOK_FIGURES[book]
    )


# Figures spec section 2: Kadesh's maps "MAP III." to "MAP VIII.", the
# first two words of each caption as the OCR read them.
_KADESH_MAP_CAPTIONS = frozendict(
    {
        29: ("MAP", "111."),
        33: ("MAP", "IV."),
        36: ("MAP", "V."),
        38: ("MAP", "vi."),
        41: ("MAP", "VII."),
        45: ("MAP", "VIII."),
    }
)


@pytest.mark.whole_book
@pytest.mark.thread_unsafe
@pytest.mark.timeout(600)
def test_whole_kadesh_caption_of_each_map_and_none_of_the_hieroglyphs(
    whole_book_run: Callable[[str], BookFolder],
) -> None:
    found = _in_page_blocks(read_blocks(whole_book_run(_KADESH_BOOK).blocks_json))
    captions = {
        index: tuple(block_text(block).split(" ")[:2])
        for index, figures in found.items()
        for block in figures
        if block.spans
    }
    assert captions == _KADESH_MAP_CAPTIONS
