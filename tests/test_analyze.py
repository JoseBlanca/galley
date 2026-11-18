"""Tests of galley.analyze (walking skeleton spec section 6, plates spec
sections 2 and 6).

The unit tests build their configs, pages and renders by hand. The excerpt tests
read the folders of the session fixture `excerpt_books`; a test that runs
analyze on a folder of its own is marked thread_unsafe, so that the
8-thread run does it once.
"""

import logging
import tomllib
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

import pytest

from galley import analyze
from galley.analyze import (
    InkRule,
    PageStart,
    PictureArea,
    PlateRule,
    check_config_pages,
    classify_page,
    front_matter_end,
    is_inkless,
    is_plate,
    picture_area,
    require_text_layer,
)
from galley.book_folder import BookFolder
from galley.config import BookConfig, ExcludedRegion, Language, OcrMode, read_config
from galley.errors import ConfigError, PdfError
from galley.model import (
    Box,
    PageInfo,
    PageKind,
    RenderedPage,
    TextSource,
    pdf_sha256,
    read_pages,
)

KADESH = "kadesh_8-17"
GIERKE = "gierke_86-93_270-271"
HASKINS = "haskins_eval"

REGION_A = Box(10.0, 20.0, 30.0, 40.0)
REGION_B = Box(1.0, 2.0, 3.0, 4.0)
REGION_ELSEWHERE = Box(5.0, 6.0, 7.0, 8.0)

CONFIG = BookConfig(
    pdf=Path("/books/book.pdf"),
    title="A Book",
    authors=("An Author",),
    language=Language.EN,
    # Two regions on page 3, not in the order of their boxes, and one on 5.
    exclude_regions=(
        ExcludedRegion(3, REGION_A),
        ExcludedRegion(5, REGION_ELSEWHERE),
        ExcludedRegion(3, REGION_B),
    ),
)


def page(index: int, kind: PageKind, text_source: TextSource) -> PageInfo:
    return PageInfo(
        index=index,
        width_pt=400.0,
        height_pt=600.0,
        kind=kind,
        text_source=text_source,
        text_layer_score=None,
        exclude_regions=(),
        figure_boxes=(),
        blank_checked_by_ocr=False,
    )


# classify_page


def test_page_with_layer_words_is_text_with_its_regions_in_config_order() -> None:
    assert classify_page(
        3,
        400.0,
        600.0,
        12,
        CONFIG,
        plate_rule=PlateRule.NOT_PLATE,
        ink_rule=InkRule.NOT_INKLESS,
        front_matter_end=0,
    ) == PageInfo(
        index=3,
        width_pt=400.0,
        height_pt=600.0,
        kind=PageKind.TEXT,
        text_source=TextSource.TEXT_LAYER,
        text_layer_score=None,
        exclude_regions=(REGION_A, REGION_B),
        figure_boxes=(),
        blank_checked_by_ocr=False,
    )


def test_page_in_exclude_pages_is_excluded_although_it_has_layer_words() -> None:
    config = replace(CONFIG, exclude_pages=(1, 3))

    assert classify_page(
        3,
        400.0,
        600.0,
        12,
        config,
        plate_rule=PlateRule.NOT_PLATE,
        ink_rule=InkRule.NOT_INKLESS,
        front_matter_end=0,
    ) == PageInfo(
        index=3,
        width_pt=400.0,
        height_pt=600.0,
        kind=PageKind.EXCLUDED,
        text_source=TextSource.NONE,
        text_layer_score=None,
        exclude_regions=(REGION_A, REGION_B),
        figure_boxes=(),
        blank_checked_by_ocr=False,
    )


def test_page_in_exclude_pages_without_layer_words_is_excluded_not_blank() -> None:
    config = replace(CONFIG, exclude_pages=(4,))

    assert (
        classify_page(
            4,
            400.0,
            600.0,
            0,
            config,
            plate_rule=PlateRule.NOT_PLATE,
            ink_rule=InkRule.NOT_INKLESS,
            front_matter_end=0,
        ).kind
        is PageKind.EXCLUDED
    )


def test_page_without_layer_words_is_blank_with_no_text_source() -> None:
    assert classify_page(
        4,
        400.0,
        600.0,
        0,
        CONFIG,
        plate_rule=PlateRule.NOT_PLATE,
        ink_rule=InkRule.NOT_INKLESS,
        front_matter_end=0,
    ) == PageInfo(
        index=4,
        width_pt=400.0,
        height_pt=600.0,
        kind=PageKind.BLANK,
        text_source=TextSource.NONE,
        text_layer_score=None,
        exclude_regions=(),
        figure_boxes=(),
        blank_checked_by_ocr=False,
    )


# classify_page with the plate rule (plates spec section 2)


def test_page_the_plate_rule_takes_is_a_plate_read_from_its_layer() -> None:
    page = classify_page(
        3,
        400.0,
        600.0,
        4,
        CONFIG,
        plate_rule=PlateRule.PLATE,
        ink_rule=InkRule.NOT_INKLESS,
        front_matter_end=0,
    )

    assert (page.kind, page.text_source) == (PageKind.PLATE, TextSource.TEXT_LAYER)
    assert page.exclude_regions == (REGION_A, REGION_B)


def test_page_without_a_layer_the_plate_rule_takes_is_a_plate_with_no_source() -> None:
    page = classify_page(
        4,
        400.0,
        600.0,
        0,
        CONFIG,
        plate_rule=PlateRule.PLATE,
        ink_rule=InkRule.NOT_INKLESS,
        front_matter_end=0,
    )

    assert (page.kind, page.text_source) == (PageKind.PLATE, TextSource.NONE)


@pytest.mark.parametrize(
    ("layer_word_count", "text_source"),
    [(40, TextSource.TEXT_LAYER), (0, TextSource.NONE)],
    ids=["with_layer", "without_layer"],
)
def test_page_in_plate_pages_is_a_plate_whatever_the_rule_finds(
    layer_word_count: int, text_source: TextSource
) -> None:
    config = replace(CONFIG, plate_pages=(23,))

    page = classify_page(
        23,
        612.0,
        792.0,
        layer_word_count,
        config,
        plate_rule=PlateRule.NOT_PLATE,
        ink_rule=InkRule.NOT_INKLESS,
        front_matter_end=0,
    )

    assert (page.kind, page.text_source) == (PageKind.PLATE, text_source)


def test_cover_page_the_plate_rule_takes_is_never_a_plate() -> None:
    config = replace(CONFIG, cover_page=0)

    page = classify_page(
        0,
        400.0,
        600.0,
        12,
        config,
        plate_rule=PlateRule.PLATE,
        ink_rule=InkRule.NOT_INKLESS,
        front_matter_end=0,
    )

    assert page.kind is PageKind.TEXT


def test_excluded_page_the_plate_rule_takes_is_excluded() -> None:
    config = replace(CONFIG, exclude_pages=(3,))

    page = classify_page(
        3,
        400.0,
        600.0,
        12,
        config,
        plate_rule=PlateRule.PLATE,
        ink_rule=InkRule.NOT_INKLESS,
        front_matter_end=0,
    )

    assert (page.kind, page.text_source) == (PageKind.EXCLUDED, TextSource.NONE)


# classify_page with the inkless rule (plates spec section 2b)


def test_page_the_inkless_rule_takes_is_inkless_with_no_text_source() -> None:
    page = classify_page(
        3,
        400.0,
        600.0,
        6,
        CONFIG,
        plate_rule=PlateRule.NOT_PLATE,
        ink_rule=InkRule.INKLESS,
        front_matter_end=0,
    )

    assert (page.kind, page.text_source) == (PageKind.INKLESS, TextSource.NONE)
    assert page.exclude_regions == (REGION_A, REGION_B)


def test_page_the_inkless_and_plate_rules_both_take_is_inkless() -> None:
    page = classify_page(
        3,
        400.0,
        600.0,
        6,
        CONFIG,
        plate_rule=PlateRule.PLATE,
        ink_rule=InkRule.INKLESS,
        front_matter_end=0,
    )

    assert (page.kind, page.text_source) == (PageKind.INKLESS, TextSource.NONE)


@pytest.mark.parametrize("plate_rule", [PlateRule.PLATE, PlateRule.NOT_PLATE])
def test_inkless_page_before_front_matter_end_stays_front_matter(
    plate_rule: PlateRule,
) -> None:
    # Haskins' front endpapers, pages 1 and 2 (plates spec section 2b).
    page = classify_page(
        2,
        400.0,
        600.0,
        20,
        CONFIG,
        plate_rule=plate_rule,
        ink_rule=InkRule.INKLESS,
        front_matter_end=12,
    )

    assert (page.kind, page.text_source) == (PageKind.FRONT_MATTER, TextSource.NONE)


def test_inkless_page_in_exclude_pages_or_plate_pages_keeps_the_configs_kind() -> None:
    config = replace(CONFIG, exclude_pages=(3,), plate_pages=(4,))

    assert tuple(
        classify_page(
            index,
            400.0,
            600.0,
            6,
            config,
            plate_rule=PlateRule.NOT_PLATE,
            ink_rule=InkRule.INKLESS,
            front_matter_end=0,
        ).kind
        for index in (3, 4)
    ) == (PageKind.EXCLUDED, PageKind.PLATE)


# is_plate, on renders of 30 by 40 squares of 24 pt (12 px at 36 dpi), made
# in the test (plates spec section 6).

SQUARE_PX = 12
WIDTH_SQUARES = 30
HEIGHT_SQUARES = 40
WHITE = 255
BLACK = 0

# Squares looked at: without the outer ring, 28 by 38; without a layer, the
# binding's column on each side left out too, 26 by 38.
SQUARES_WITH_LAYER = 28 * 38
SQUARES_WITHOUT_LAYER = 26 * 38


def render(
    *blocks: tuple[int, int, int, int, int], background: int = WHITE
) -> RenderedPage:
    """A page of 30 by 40 squares at 36 dpi, of gray `background`, with each
    block (top row, left column, rows, columns, gray) painted on it."""
    width_px = WIDTH_SQUARES * SQUARE_PX
    height_px = HEIGHT_SQUARES * SQUARE_PX
    pixels = bytearray([background]) * (width_px * height_px)
    for top, left, rows, columns, gray in blocks:
        for y in range(top * SQUARE_PX, (top + rows) * SQUARE_PX):
            start = y * width_px + left * SQUARE_PX
            pixels[start : start + columns * SQUARE_PX] = bytes([gray]) * (
                columns * SQUARE_PX
            )
    return RenderedPage(
        page_index=0,
        dpi=36,
        width_px=width_px,
        height_px=height_px,
        pixels=bytes(pixels),
    )


BLACK_BLOCK = render((5, 5, 10, 10, BLACK))


def test_is_plate_for_a_black_block_of_100_squares_no_word_covers() -> None:
    assert picture_area(BLACK_BLOCK, ()) == PictureArea(
        largest_group=100, squares=SQUARES_WITH_LAYER
    )
    assert is_plate(BLACK_BLOCK, (), 0)


def test_is_plate_false_with_a_word_box_over_the_block() -> None:
    # The block spans 120 to 360 pt; grown by 2 pt the box touches every square.
    word_box = Box(130.0, 130.0, 350.0, 350.0)

    assert picture_area(BLACK_BLOCK, (word_box,)).largest_group == 0
    assert not is_plate(BLACK_BLOCK, (word_box,), 1)


@pytest.mark.parametrize(("inset_pt", "largest_group"), [(25.0, 0), (27.0, 36)])
def test_word_box_touches_the_squares_within_2_pt_of_it(
    inset_pt: float, largest_group: int
) -> None:
    # The block's squares span 120 to 360 pt. A box 25 pt inside its edges
    # lies 1 pt from the outer ring of squares and, grown by 2 pt, touches
    # it; 27 pt inside it lies 3 pt away and leaves the ring of 36 squares.
    word_box = Box(120 + inset_pt, 120 + inset_pt, 360 - inset_pt, 360 - inset_pt)

    assert picture_area(BLACK_BLOCK, (word_box,)).largest_group == largest_group


def test_is_plate_false_with_21_known_words_and_true_with_20() -> None:
    assert not is_plate(BLACK_BLOCK, (), 21)
    assert is_plate(BLACK_BLOCK, (), 20)


def test_is_plate_false_for_a_block_of_49_squares_and_true_for_50() -> None:
    assert not is_plate(render((5, 5, 7, 7, BLACK)), (), 0)
    assert is_plate(render((5, 5, 10, 5, BLACK)), (), 0)


def test_is_plate_false_for_two_blocks_of_40_touching_only_by_a_corner() -> None:
    corner = render((5, 5, 8, 5, BLACK), (13, 10, 8, 5, BLACK))
    # The same blocks one column apart touch side by side, a group of 80.
    side = render((5, 5, 8, 5, BLACK), (13, 9, 8, 5, BLACK))

    assert picture_area(corner, ()).largest_group == 40
    assert not is_plate(corner, (), 0)
    assert picture_area(side, ()).largest_group == 80
    assert is_plate(side, (), 0)


def test_is_plate_false_for_a_block_20_levels_below_the_median_with_a_layer() -> None:
    page = render((5, 5, 10, 10, WHITE - 20))

    assert picture_area(page, ()).largest_group == 0
    assert not is_plate(page, (), 0)


def test_is_plate_measures_ink_from_the_median_not_from_white() -> None:
    # A gray page, the block 30 levels darker than it.
    page = render((5, 5, 10, 10, 170), background=200)

    assert is_plate(page, (), 0)


def test_is_plate_leaves_out_the_outer_ring_of_squares() -> None:
    # Black bands one square wide round the page, 132 squares touching.
    page = render(
        (0, 0, 1, WIDTH_SQUARES, BLACK),
        (HEIGHT_SQUARES - 1, 0, 1, WIDTH_SQUARES, BLACK),
        (0, 0, HEIGHT_SQUARES, 1, BLACK),
        (0, WIDTH_SQUARES - 1, HEIGHT_SQUARES, 1, BLACK),
    )

    assert picture_area(page, ()).largest_group == 0
    assert not is_plate(page, (), 0)


# 396 of the 988 squares looked at: 0.40 of the page; 304: 0.31.
GRAY_BLOCK_04 = render((5, 5, 22, 18, WHITE - 20))
GRAY_BLOCK_03 = render((5, 5, 19, 16, WHITE - 20))


def test_is_plate_without_a_layer_for_a_gray_block_of_0_4_of_the_page() -> None:
    assert picture_area(GRAY_BLOCK_04, None) == PictureArea(
        largest_group=396, squares=SQUARES_WITHOUT_LAYER
    )
    # Without a layer the known words are ignored.
    assert is_plate(GRAY_BLOCK_04, None, 100)


def test_is_plate_false_without_a_layer_for_a_gray_block_of_0_3_of_the_page() -> None:
    assert picture_area(GRAY_BLOCK_03, None).largest_group == 304
    assert not is_plate(GRAY_BLOCK_03, None, 0)


def test_is_plate_without_a_layer_leaves_out_the_binding_columns() -> None:
    # A dark band in the second column from each side, the binding's shadow,
    # and a block of 0.3 of the page touching the left one: counted with
    # the band, the group would be 304 + 38 = 342, over 0.34 of the page.
    page = render(
        (0, 1, HEIGHT_SQUARES, 1, BLACK),
        (0, WIDTH_SQUARES - 2, HEIGHT_SQUARES, 1, BLACK),
        (5, 2, 19, 16, BLACK),
    )

    assert picture_area(page, None).largest_group == 304
    assert not is_plate(page, None, 0)


# is_inkless, on renders of 100 by 100 pixels (200 by 200 pt at 36 dpi), made
# in the test (plates spec section 6, "The inkless page").

INK_PAGE_PX = 100
# Four word boxes of 40 by 10 pt, 40 pt apart down the page.
INK_WORD_BOXES = tuple(
    Box(40.0, 30.0 + 40.0 * line, 80.0, 40.0 + 40.0 * line) for line in range(4)
)


def ink_render(
    gray_at: Callable[[int, int], int], width_px: int = INK_PAGE_PX
) -> RenderedPage:
    """A page of `width_px` by 100 pixels at 36 dpi whose pixel at (across,
    down) has the gray `gray_at(across, down)`."""
    return RenderedPage(
        page_index=0,
        dpi=36,
        width_px=width_px,
        height_px=INK_PAGE_PX,
        pixels=bytes(
            gray_at(across, down)
            for down in range(INK_PAGE_PX)
            for across in range(width_px)
        ),
    )


def with_bars(
    boxes: tuple[Box, ...], bar: int, ground: int
) -> Callable[[int, int], int]:
    """A page of gray `ground` with a bar of gray `bar`, 1 pixel high, across
    the middle of each of `boxes`."""
    rows = frozenset(round((box.top + box.bottom) / 2 / 2) for box in boxes)
    columns = range(20, 40)  # 40 to 80 pt, the boxes' width

    def gray_at(across: int, down: int) -> int:
        return bar if down in rows and across in columns else ground

    return gray_at


def test_is_inkless_for_a_white_page_with_4_word_boxes() -> None:
    assert is_inkless(ink_render(lambda _across, _down: WHITE), INK_WORD_BOXES)


@pytest.mark.parametrize(
    ("words_with_ink", "inkless"), [(2, True), (3, False)], ids=["half", "a_quarter"]
)
def test_is_inkless_when_at_least_half_the_words_have_no_ink(
    words_with_ink: int, inkless: bool
) -> None:
    page = ink_render(with_bars(INK_WORD_BOXES[:words_with_ink], BLACK, WHITE))

    assert is_inkless(page, INK_WORD_BOXES) is inkless


def test_is_inkless_false_for_white_print_on_a_black_page() -> None:
    page = ink_render(with_bars(INK_WORD_BOXES, WHITE, BLACK))

    assert not is_inkless(page, INK_WORD_BOXES)


def test_is_inkless_for_a_page_darkening_from_200_to_120_across() -> None:
    # 400 pt wide: the gray falls 0.4 levels a pixel, about 9 across a
    # word's box grown by 3 pt.
    width_px = 200
    page = ink_render(
        lambda across, _down: 200 - round(80 * across / (width_px - 1)), width_px
    )

    assert is_inkless(page, INK_WORD_BOXES)


def test_is_inkless_false_without_word_boxes() -> None:
    assert not is_inkless(ink_render(lambda _across, _down: WHITE), ())


def test_word_box_2_pt_left_of_a_black_line_has_ink() -> None:
    # A line 1 pixel wide at pixel 60, 120 to 122 pt; the box ends at 118 pt.
    page = ink_render(lambda across, _down: BLACK if across == 60 else WHITE)

    assert not is_inkless(page, (Box(78.0, 30.0, 118.0, 40.0),))
    assert is_inkless(page, (Box(70.0, 30.0, 110.0, 40.0),))


def test_word_box_wholly_off_the_page_has_no_ink() -> None:
    # Domesday 481's "Cotton" starts at 422 pt on a page 393 pt wide.
    page = ink_render(lambda across, _down: BLACK if across % 2 else WHITE)

    assert is_inkless(page, (Box(210.0, 30.0, 250.0, 40.0),))


# require_text_layer


def test_require_text_layer_names_both_blank_pages_of_four() -> None:
    pages = (
        page(0, PageKind.TEXT, TextSource.TEXT_LAYER),
        page(1, PageKind.BLANK, TextSource.NONE),
        page(2, PageKind.EXCLUDED, TextSource.NONE),
        page(3, PageKind.BLANK, TextSource.NONE),
    )

    with pytest.raises(
        PdfError,
        match=r"^page indices 1, 3: these pages have no text layer, and the "
        r"walking skeleton has no OCR; add them to `exclude_pages` once you "
        r"have checked that they hold no text$",
    ):
        require_text_layer(pages)


def test_require_text_layer_accepts_text_excluded_and_plate_pages() -> None:
    pages = (
        page(0, PageKind.TEXT, TextSource.TEXT_LAYER),
        page(1, PageKind.EXCLUDED, TextSource.NONE),
        page(2, PageKind.PLATE, TextSource.NONE),
        page(3, PageKind.PLATE, TextSource.TEXT_LAYER),
    )

    require_text_layer(pages)


# check_config_pages


def test_ocr_redo_is_a_config_error() -> None:
    with pytest.raises(
        ConfigError,
        match=r"^ocr = redo needs OCR, which the walking skeleton does not have; "
        r"use verify or trust$",
    ):
        check_config_pages(replace(CONFIG, ocr=OcrMode.REDO), 10)


@pytest.mark.parametrize("ocr", [OcrMode.VERIFY, OcrMode.TRUST])
def test_ocr_verify_and_trust_with_pages_below_the_count_pass(ocr: OcrMode) -> None:
    config = replace(
        CONFIG,
        ocr=ocr,
        exclude_pages=(0, 9),
        exclude_regions=(ExcludedRegion(9, REGION_A),),
        cover_page=9,
        plate_pages=(0, 9),
        contents_pages=(0, 9),
    )

    check_config_pages(config, 10)


def test_page_in_plate_pages_and_exclude_pages_is_accepted_and_excluded() -> None:
    # Architecture section 6: exclude_pages wins.
    config = replace(CONFIG, exclude_pages=(23,), plate_pages=(23,))

    check_config_pages(config, 24)
    page = classify_page(
        23,
        612.0,
        792.0,
        40,
        config,
        plate_rule=PlateRule.NOT_PLATE,
        ink_rule=InkRule.NOT_INKLESS,
        front_matter_end=0,
    )

    assert page.kind is PageKind.EXCLUDED
    assert page.text_source is TextSource.NONE


def test_contents_pages_and_plate_pages_below_the_page_count_pass() -> None:
    config = replace(CONFIG, contents_pages=(14, 15, 16), plate_pages=(23,))

    check_config_pages(config, 24)


@pytest.mark.parametrize(
    ("config", "key"),
    [
        (replace(CONFIG, exclude_pages=(2, 10)), "exclude_pages[1]"),
        (
            replace(
                CONFIG,
                exclude_regions=(
                    ExcludedRegion(3, REGION_A),
                    ExcludedRegion(10, REGION_B),
                ),
            ),
            "exclude_regions[1].page",
        ),
        (replace(CONFIG, cover_page=10), "cover_page"),
        (replace(CONFIG, plate_pages=(10,)), "plate_pages[0]"),
        (replace(CONFIG, contents_pages=(4, 5, 10)), "contents_pages[2]"),
        (replace(CONFIG, front_matter_end=10), "front_matter_end"),
    ],
    ids=[
        "exclude_pages",
        "exclude_regions",
        "cover_page",
        "plate_pages",
        "contents_pages",
        "front_matter_end",
    ],
)
def test_page_index_equal_to_the_page_count_is_a_config_error(
    config: BookConfig, key: str
) -> None:
    with pytest.raises(ConfigError) as raised:
        check_config_pages(config, 10)

    assert str(raised.value) == (
        f"key `{key}`: page index 10 is not below the page count of /books/book.pdf, 10"
    )


def test_front_matter_end_below_the_page_count_after_the_contents_passes() -> None:
    # Front-matter spec section 2: a contents page at the front-matter end
    # is kept, so it is no contradiction.
    config = replace(CONFIG, contents_pages=(14, 15), front_matter_end=14)

    check_config_pages(config, 16)


def test_contents_page_before_front_matter_end_is_a_config_error_naming_both_keys() -> (
    None
):
    config = replace(CONFIG, contents_pages=(10, 14), front_matter_end=12)

    with pytest.raises(ConfigError) as raised:
        check_config_pages(config, 20)

    assert str(raised.value) == (
        "key `contents_pages`: page index 10 lies before `front_matter_end`, 12, "
        "and would be dropped with the front matter; correct one of the two keys"
    )


def test_contents_page_just_before_front_matter_end_is_a_config_error() -> None:
    config = replace(CONFIG, contents_pages=(11, 14), front_matter_end=12)

    with pytest.raises(ConfigError) as raised:
        check_config_pages(config, 20)

    assert str(raised.value) == (
        "key `contents_pages`: page index 11 lies before `front_matter_end`, 12, "
        "and would be dropped with the front matter; correct one of the two keys"
    )


# The front matter (front-matter spec sections 1, 2 and 7)


def start(index: int, kind: PageKind, word_count: int, *first_row: str) -> PageStart:
    return PageStart(index=index, kind=kind, first_row=first_row, word_count=word_count)


def text_starts(page_count: int, word_count: int) -> tuple[PageStart, ...]:
    """`page_count` text pages of `word_count` words each, whose topmost row
    is a running head that names no preface."""
    return tuple(
        start(index, PageKind.TEXT, word_count, str(index), "A", "BOOK")
        for index in range(page_count)
    )


TEXT = PageKind.TEXT
EXCLUDED = PageKind.EXCLUDED

# Haskins' pages 0 to 27 as analyze measured them on 17 November 2026, with
# the kinds of the whole_book config of tests/conftest.py, which excludes
# 0, 3, 4, 5, 7, 11 and 15.
HASKINS_STARTS = (
    start(0, EXCLUDED, 0),
    start(1, TEXT, 22, "•^A", "V"),
    start(2, TEXT, 29, "<^", "-fL"),
    start(3, EXCLUDED, 0),
    start(4, EXCLUDED, 0),
    start(5, EXCLUDED, 0),
    start(6, TEXT, 5, "THE", "NORMANS", "IN", "EUROPEAN", "HISTORY"),
    start(7, EXCLUDED, 0),
    start(8, TEXT, 31, "THE", "NORMANS", "IN"),
    start(9, TEXT, 18, '^/v"^'),
    start(10, TEXT, 3, "TO", "MY", "WIFE"),
    start(11, EXCLUDED, 0),
    start(12, TEXT, 204, "PREFACE"),
    start(13, TEXT, 145, "vlil", "PREFACE"),
    start(14, TEXT, 55, "CONTENTS"),
    start(15, EXCLUDED, 0),
    start(16, TEXT, 185, "THE", "NORMANS", "IN"),
    start(17, TEXT, 252, "2", "NORMANS", "IN", "EUROPEAN", "HISTORY"),
    start(18, TEXT, 260, "NORMANDY", "IN", "HISTORY", "3"),
    start(19, TEXT, 269, "4", "NORMANS", "IN", "EUROPEAN", "HISTORY"),
    start(20, TEXT, 278, "NORMANDY", "IN", "HISTORY", "5"),
    start(21, TEXT, 273, "6", "NORMANS", "IN", "EUROPEAN", "HISTORY"),
    start(22, TEXT, 266, "NORMANDY", "IN", "HISTORY", "7"),
    start(23, TEXT, 249, "!"),
    start(24, TEXT, 264, "NORMANDY", "IN", "HISTORY", "9"),
    start(25, TEXT, 257, "10", "NORMANS", "IN", "EUROPEAN", "HISTORY"),
    start(26, TEXT, 264, "NORMANDY", "IN", "HISTORY", "ii"),
    start(27, TEXT, 258, "12", "NORMANS", "IN", "EUROPEAN", "HISTORY"),
)


# Haskins' PDF has 280 pages, which make the search window its first 28. Its
# pages 28 to 279 stand in as text pages: only their number matters here.
HASKINS_BOOK_STARTS = (*HASKINS_STARTS, *text_starts(280, 260)[28:])


def test_front_matter_end_of_haskins_first_28_pages_is_its_preface_page_12() -> None:
    config = replace(CONFIG, contents_pages=(14,))

    assert front_matter_end(HASKINS_BOOK_STARTS, config) == 12


def test_front_matter_end_of_haskins_without_contents_pages_is_still_12() -> None:
    assert front_matter_end(HASKINS_BOOK_STARTS, CONFIG) == 12


@pytest.mark.parametrize(
    "first_row",
    [
        ("PREFACE.",),
        ("vi", "Preface."),
        ("AUTHOR'S", "PREFACE"),
        ("PRÉFACE",),
        ("AVANT-PROPOS",),
        ("Vorwort",),
        ("FOREWORD",),
        ("PREFATORY", "NOTE"),
        ("PREFAZIONE",),
        ("PRÓLOGO",),
        ("PREFACIO",),
        ("1", "2", "3", "4", "5", "PREFACE"),
    ],
)
def test_front_matter_end_is_the_first_preface_page_in_the_window(
    first_row: tuple[str, ...],
) -> None:
    starts = (
        *text_starts(4, 300),
        start(4, TEXT, 200, *first_row),
        *text_starts(20, 300)[5:],
    )

    assert front_matter_end(starts, CONFIG) == 4


@pytest.mark.parametrize(
    "first_row",
    [
        ("1", "2", "3", "4", "5", "6", "PREFACE"),
        ("PREFACES",),
        ("INTRODUCTION",),
    ],
    ids=["seven_words", "plural", "introduction"],
)
def test_front_matter_end_takes_no_preface_page_from_a_row_that_names_none(
    first_row: tuple[str, ...],
) -> None:
    # Without a preface page or contents, the end is the first page of
    # running text, page 5.
    starts = (
        *(start(index, TEXT, 10, "TITLE") for index in range(4)),
        start(4, TEXT, 100, *first_row),
        *text_starts(20, 300)[5:],
    )

    assert front_matter_end(starts, CONFIG) == 5


def test_front_matter_end_is_a_contents_page_before_a_preface_page() -> None:
    starts = (
        *(start(index, TEXT, 10, "TITLE") for index in range(3)),
        start(3, TEXT, 50, "CONTENTS"),
        start(4, TEXT, 50, "vi", "CONTENTS"),
        start(5, TEXT, 200, "PREFACE"),
        *text_starts(20, 300)[6:],
    )
    config = replace(CONFIG, contents_pages=(3, 4))

    assert front_matter_end(starts, config) == 3


def test_front_matter_end_is_a_preface_page_before_a_contents_page() -> None:
    starts = (
        *(start(index, TEXT, 10, "TITLE") for index in range(3)),
        start(3, TEXT, 200, "PREFACE"),
        start(4, TEXT, 50, "CONTENTS"),
        *text_starts(20, 300)[5:],
    )
    config = replace(CONFIG, contents_pages=(4,))

    assert front_matter_end(starts, config) == 3


def test_front_matter_end_ignores_a_preface_and_contents_past_the_window() -> None:
    # 120 pages: the window is the first 12. The first page of running text
    # is page 5.
    starts = (
        *(start(index, TEXT, 10, "TITLE") for index in range(5)),
        *text_starts(120, 300)[5:12],
        start(12, TEXT, 200, "PREFACE"),
        *text_starts(120, 300)[13:],
    )
    config = replace(CONFIG, contents_pages=(13, 119))

    assert front_matter_end(starts, config) == 5


def test_front_matter_end_takes_a_preface_page_on_the_last_page_of_the_window() -> None:
    # 120 pages: the window is the first 12, pages 0 to 11.
    starts = (
        *(start(index, TEXT, 10, "TITLE") for index in range(11)),
        start(11, TEXT, 200, "PREFACE"),
        *text_starts(120, 300)[12:],
    )

    assert front_matter_end(starts, CONFIG) == 11


# Kadesh's 76 pages as analyze measured them on 17 November 2026, with the
# whole_book config of tests/conftest.py: each page's kind and word count.
# Their topmost rows name no preface and are left out.
KADESH_KINDS_AND_WORD_COUNTS = (
    *((EXCLUDED, 6), (EXCLUDED, 0), (EXCLUDED, 0), (EXCLUDED, 0)),
    *((TEXT, 26), (TEXT, 6), (TEXT, 47), (TEXT, 12)),
    *((TEXT, 582), (TEXT, 639), (TEXT, 668), (TEXT, 854)),
    *((TEXT, 818), (TEXT, 733), (TEXT, 832), (TEXT, 816)),
    *((EXCLUDED, 4), (PageKind.PLATE, 0), (TEXT, 652), (PageKind.PLATE, 5)),
    *((TEXT, 545), (TEXT, 639), (PageKind.PLATE, 2), (PageKind.PLATE, 0)),
    *((PageKind.PLATE, 4), (TEXT, 562), (TEXT, 646), (TEXT, 229)),
    *((TEXT, 804), (TEXT, 211), (TEXT, 468), (TEXT, 679)),
    *((TEXT, 433), (TEXT, 386), (PageKind.PLATE, 3), (PageKind.PLATE, 0)),
    *((TEXT, 387), (TEXT, 358), (TEXT, 317), (TEXT, 302)),
    *((TEXT, 543), (TEXT, 411), (PageKind.PLATE, 3), (PageKind.PLATE, 0)),
    *((TEXT, 212), (TEXT, 556), (TEXT, 436), (TEXT, 692)),
    *((PageKind.PLATE, 8), (EXCLUDED, 4), (TEXT, 271), (TEXT, 435)),
    *((TEXT, 539), (TEXT, 513), (TEXT, 679), (TEXT, 620)),
    *((PageKind.PLATE, 13), (PageKind.PLATE, 0), (TEXT, 608), (TEXT, 693)),
    *((TEXT, 649), (TEXT, 616), (TEXT, 607), (TEXT, 673)),
    *((PageKind.PLATE, 24), (EXCLUDED, 3), (TEXT, 538), (TEXT, 135)),
    *((PageKind.PLATE, 12), (PageKind.PLATE, 0), (EXCLUDED, 0), (EXCLUDED, 0)),
    *((EXCLUDED, 0), (EXCLUDED, 0), (TEXT, 20), (EXCLUDED, 0)),
)


def test_front_matter_end_of_kadesh_is_its_first_page_of_running_text_8() -> None:
    starts = tuple(
        start(index, kind, word_count)
        for index, (kind, word_count) in enumerate(KADESH_KINDS_AND_WORD_COUNTS)
    )

    assert len(starts) == 76
    assert sum(1 for page_start in starts if page_start.kind is TEXT) == 49
    assert front_matter_end(starts, CONFIG) == 8


def test_front_matter_end_is_0_without_preface_contents_or_running_text() -> None:
    # The median is 300 words; no page of the window has 150.
    starts = (
        *(start(index, TEXT, 149, "TITLE") for index in range(10)),
        *text_starts(30, 300)[10:],
    )

    assert front_matter_end(starts, CONFIG) == 0


def test_front_matter_end_is_a_window_page_of_exactly_half_the_median() -> None:
    # The median is 300 words, half of it 150: pages 0 to 3, of 140 words,
    # fall short; page 4, of 150, is the first page of running text.
    starts = (
        *(start(index, TEXT, 140, "TITLE") for index in range(4)),
        start(4, TEXT, 150, "TITLE"),
        *text_starts(30, 300)[5:],
    )

    assert front_matter_end(starts, CONFIG) == 4


def test_front_matter_end_takes_the_median_of_the_text_pages_only() -> None:
    # The 7 text pages of 300 words make the median of the 10 text pages 300,
    # so the first page of running text is page 3. The 20 excluded pages of
    # no words do not count: with them the median would be 0, and the end 0.
    starts = (
        *(start(index, TEXT, 100, "TITLE") for index in range(3)),
        *text_starts(10, 300)[3:],
        *(start(index, EXCLUDED, 0) for index in range(10, 30)),
    )

    assert front_matter_end(starts, CONFIG) == 3


def test_front_matter_end_takes_a_preface_on_page_9_of_a_30_page_book() -> None:
    # A tenth of 30 pages is 3, so the window is its least, the first 10
    # pages, 0 to 9.
    starts = (
        *(start(index, TEXT, 10, "TITLE") for index in range(9)),
        start(9, TEXT, 200, "PREFACE"),
        *text_starts(30, 300)[10:],
    )

    assert front_matter_end(starts, CONFIG) == 9


def test_front_matter_end_is_0_for_a_book_of_no_text_page() -> None:
    starts = tuple(start(index, EXCLUDED, 0) for index in range(12))

    assert front_matter_end(starts, CONFIG) == 0


@pytest.mark.parametrize("config_end", [0, 3, 13])
def test_front_matter_end_of_the_config_wins_over_the_rule(config_end: int) -> None:
    config = replace(CONFIG, contents_pages=(14,), front_matter_end=config_end)

    assert front_matter_end(HASKINS_BOOK_STARTS, config) == config_end


def test_text_page_before_front_matter_end_is_front_matter_with_no_text_source() -> (
    None
):
    page = classify_page(
        3,
        400.0,
        600.0,
        12,
        CONFIG,
        plate_rule=PlateRule.NOT_PLATE,
        ink_rule=InkRule.NOT_INKLESS,
        front_matter_end=4,
    )

    assert (page.kind, page.text_source) == (PageKind.FRONT_MATTER, TextSource.NONE)
    assert page.exclude_regions == (REGION_A, REGION_B)


def test_text_page_at_front_matter_end_stays_text() -> None:
    page = classify_page(
        3,
        400.0,
        600.0,
        12,
        CONFIG,
        plate_rule=PlateRule.NOT_PLATE,
        ink_rule=InkRule.NOT_INKLESS,
        front_matter_end=3,
    )

    assert (page.kind, page.text_source) == (PageKind.TEXT, TextSource.TEXT_LAYER)


def test_excluded_plate_and_blank_pages_before_front_matter_end_keep_their_kind() -> (
    None
):
    config = replace(CONFIG, exclude_pages=(1,), plate_pages=(2,))

    kinds = tuple(
        classify_page(
            index,
            400.0,
            600.0,
            word_count,
            config,
            plate_rule=PlateRule.NOT_PLATE,
            ink_rule=InkRule.NOT_INKLESS,
            front_matter_end=10,
        ).kind
        for index, word_count in ((1, 12), (2, 12), (3, 0))
    )

    assert kinds == (PageKind.EXCLUDED, PageKind.PLATE, PageKind.BLANK)


# The excerpts, from the session fixture.


def test_kadesh_pages_are_text_but_8_excluded_and_plate_9_with_the_region_on_0(
    excerpt_books: frozendict[str, BookFolder], excerpt_pdf: frozendict[str, Path]
) -> None:
    pages = read_pages(excerpt_books[KADESH].pages_json)

    assert pages.source_pdf_sha256 == pdf_sha256(excerpt_pdf[KADESH])
    assert pages.ocr_audit is None
    assert pages.pages == (
        *(
            PageInfo(
                index=index,
                width_pt=508.32,
                height_pt=728.16,
                kind=PageKind.TEXT,
                text_source=TextSource.TEXT_LAYER,
                text_layer_score=None,
                exclude_regions=(Box(240.0, 620.0, 252.0, 632.0),)
                if index == 0
                else (),
                figure_boxes=(),
                blank_checked_by_ocr=False,
            )
            for index in range(8)
        ),
        # Book page 16, the scan of a cover (the owner, 16 November 2026),
        # excluded by the config.
        PageInfo(
            index=8,
            width_pt=508.32,
            height_pt=728.16,
            kind=PageKind.EXCLUDED,
            text_source=TextSource.NONE,
            text_layer_score=None,
            exclude_regions=(),
            figure_boxes=(),
            blank_checked_by_ocr=False,
        ),
        # Book page 17, a relief without a text layer.
        PageInfo(
            index=9,
            width_pt=508.32,
            height_pt=728.16,
            kind=PageKind.PLATE,
            text_source=TextSource.NONE,
            text_layer_score=None,
            exclude_regions=(),
            figure_boxes=(),
            blank_checked_by_ocr=False,
        ),
    )


# The plates of each excerpt, by page index in the excerpt (plates spec
# section 6): Kadesh 17 (16, the scan of a cover, is excluded); Kadesh 64,
# 65 (the back of plate 64, a known wrong case) and 68; Domesday's maps 39 and 40;
# Kadesh 34 and 35, the back of plate 34, without a text layer. The other
# excerpts have none.
EXCERPT_PLATES = frozendict(
    {
        "kadesh_8-17": (9,),
        "kadesh_59-68": (5, 6, 9),
        "domesday_headings_quotes": (3, 4),
        "kadesh_29-38": (5, 6),
    }
)
# The front-matter pages of each excerpt (front-matter spec section 6,
# "Excerpt tests"): pages 0 to 4 of the three that open with the book's
# front pages. The other eleven have none.
EXCERPT_FRONT_MATTER = frozendict(
    {
        "haskins_front": (0, 1, 2, 3, 4),
        "domesday_front_flow": (0, 1, 2, 3, 4),
        "gierke_front_flow": (0, 1, 2, 3, 4),
    }
)
# The inkless pages of each excerpt (plates spec section 6, "The inkless
# page"): Haskins' back endpapers 277 and 278. Its front endpapers, pages 1
# and 2 of `haskins_front`, are inkless too but stay front matter.
EXCERPT_INKLESS = frozendict({"haskins_endpapers": (2, 3)})


def test_the_excerpts_plates_and_front_matter_are_the_specs_and_other_pages_text(
    excerpt_books: frozendict[str, BookFolder],
) -> None:
    for name, folder in excerpt_books.items():
        pages = read_pages(folder.pages_json).pages
        plates = EXCERPT_PLATES.get(name, ())
        front_matter = EXCERPT_FRONT_MATTER.get(name, ())
        inkless = EXCERPT_INKLESS.get(name, ())
        # Haskins' blank page before the index and Kadesh's scan of a cover
        # are excluded by their configs, and so is Haskins' page index 276
        # in `haskins_endpapers`.
        excluded = {"haskins_eval": (8,), KADESH: (8,), "haskins_endpapers": (1,)}.get(
            name, ()
        )
        assert tuple(page.index for page in pages if page.kind is PageKind.PLATE) == (
            plates
        ), name
        assert tuple(
            page.index for page in pages if page.kind is PageKind.FRONT_MATTER
        ) == (front_matter), name
        assert tuple(page.index for page in pages if page.kind is PageKind.INKLESS) == (
            inkless
        ), name
        assert all(
            page.kind is PageKind.TEXT
            for page in pages
            if page.index not in (*plates, *excluded, *front_matter, *inkless)
        ), name


def test_gierke_pages_are_ten_text_pages(
    excerpt_books: frozendict[str, BookFolder], excerpt_pdf: frozendict[str, Path]
) -> None:
    pages = read_pages(excerpt_books[GIERKE].pages_json)

    assert pages.source_pdf_sha256 == pdf_sha256(excerpt_pdf[GIERKE])
    assert pages.ocr_audit is None
    assert pages.pages == tuple(
        PageInfo(
            index=index,
            width_pt=376.128,
            height_pt=621.504,
            kind=PageKind.TEXT,
            text_source=TextSource.TEXT_LAYER,
            text_layer_score=None,
            exclude_regions=(),
            figure_boxes=(),
            blank_checked_by_ocr=False,
        )
        for index in range(10)
    )


# Runs of their own.


def kadesh_folder(root: Path, pdf: Path, settings: str) -> BookFolder:
    """A book folder for the Kadesh excerpt whose book.toml has `settings`
    besides the required keys."""
    folder = BookFolder(root)
    folder.book_toml.write_text(
        f"pdf = '{pdf}'\n"
        'title = "The Battle of Kadesh"\n'
        'authors = ["J. H. Breasted"]\n'
        'language = "en"\n'
        f"{settings}",
        encoding="utf-8",
    )
    return folder


@pytest.mark.thread_unsafe
def test_haskins_without_exclude_pages_stops_naming_its_blank_page_8_and_leaves_no_file(
    tmp_path: Path, excerpt_pdf: frozendict[str, Path]
) -> None:
    # Haskins' page 8 has no text layer and is not a plate.
    folder = BookFolder(tmp_path)
    folder.book_toml.write_text(
        f"pdf = '{excerpt_pdf[HASKINS]}'\n"
        'title = "The Normans in European History"\n'
        'authors = ["Charles Homer Haskins"]\n'
        'language = "en"\n',
        encoding="utf-8",
    )
    folder.pages_json.write_text("an old pages.json\n", encoding="utf-8")

    with pytest.raises(PdfError, match=r"^page indices 8: these pages have no"):
        analyze.run(folder, read_config(folder.book_toml))

    assert not folder.pages_json.exists()


@pytest.mark.thread_unsafe
def test_each_page_the_plate_rule_takes_is_logged_at_warning_with_its_measures(
    tmp_path: Path,
    excerpt_pdf: frozendict[str, Path],
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Page 8, the scan of a cover that the rule takes when the config does
    # not exclude it, is logged; page 9 made a plate by the config is not.
    # front_matter_end = 0, so that the front-matter rule logs no WARNING.
    folder = kadesh_folder(
        tmp_path, excerpt_pdf[KADESH], "plate_pages = [9]\nfront_matter_end = 0\n"
    )

    with caplog.at_level(logging.WARNING, logger="galley.analyze"):
        analyze.run(folder, read_config(folder.book_toml))

    pages = read_pages(folder.pages_json).pages
    assert (pages[8].kind, pages[9].kind) == (PageKind.PLATE, PageKind.PLATE)
    assert [(record.levelno, record.getMessage()) for record in caplog.records] == [
        (
            logging.WARNING,
            (
                "analyze: page index 8 taken for a plate: a picture of 70 "
                "squares, 0 known words; add it to `exclude_pages` if it is not one"
            ),
        )
    ]


@pytest.mark.thread_unsafe
def test_each_inkless_page_is_logged_at_warning_with_its_share_without_ink(
    tmp_path: Path,
    excerpt_book_toml: frozendict[str, str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Haskins' back endpapers 277 and 278, pages 2 and 3 of the excerpt,
    # 1.00 and 0.88 of their words without ink (plates spec section 2b);
    # the excerpt's config has front_matter_end = 0.
    folder = BookFolder(tmp_path)
    folder.book_toml.write_text(
        excerpt_book_toml["haskins_endpapers"], encoding="utf-8"
    )

    with caplog.at_level(logging.WARNING, logger="galley.analyze"):
        analyze.run(folder, read_config(folder.book_toml))

    assert [(record.levelno, record.getMessage()) for record in caplog.records] == [
        (
            logging.WARNING,
            (
                f"analyze: page index {index} is inkless, its words removed: "
                f"{share} of its words have no ink under them"
            ),
        )
        for index, share in ((2, "1.00"), (3, "0.88"))
    ]


@pytest.mark.thread_unsafe
def test_a_plate_without_a_layer_is_logged_with_its_share_of_the_page(
    tmp_path: Path,
    excerpt_pdf: frozendict[str, Path],
    caplog: pytest.LogCaptureFixture,
) -> None:
    folder = kadesh_folder(
        tmp_path, excerpt_pdf[KADESH], "exclude_pages = [8]\nfront_matter_end = 0\n"
    )

    with caplog.at_level(logging.WARNING, logger="galley.analyze"):
        analyze.run(folder, read_config(folder.book_toml))

    assert [record.getMessage() for record in caplog.records] == [
        (
            "analyze: page index 9, without a text layer, taken for a plate: a "
            "picture of 279 of its 476 squares; add it to `exclude_pages` if it "
            "is not one"
        )
    ]


@pytest.mark.thread_unsafe
@pytest.mark.parametrize(
    ("kind", "logged"),
    [(PageKind.PLATE, 1), (PageKind.INKLESS, 0), (PageKind.FRONT_MATTER, 0)],
)
def test_a_page_the_plate_rule_takes_is_logged_as_a_plate_only_when_it_is_one(
    kind: PageKind, logged: int, caplog: pytest.LogCaptureFixture
) -> None:
    # An inkless page the plate rule also takes is inkless (plates spec
    # section 2b), front matter before the front-matter end: not a plate.
    plate_test = analyze._PlateTest(
        area=PictureArea(largest_group=70, squares=400),
        known_words=0,
        has_layer=True,
        rule=PlateRule.PLATE,
    )

    with caplog.at_level(logging.WARNING, logger="galley.analyze"):
        analyze._log_plate_taken(page(4, kind, TextSource.NONE), plate_test)

    assert len(caplog.records) == logged


@pytest.mark.thread_unsafe
def test_ocr_redo_stops_analyze_before_writing_and_leaves_no_file(
    tmp_path: Path, excerpt_pdf: frozendict[str, Path]
) -> None:
    folder = kadesh_folder(tmp_path, excerpt_pdf[KADESH], 'ocr = "redo"\n')
    folder.pages_json.write_text("an old pages.json\n", encoding="utf-8")

    with pytest.raises(ConfigError, match=r"^ocr = redo needs OCR"):
        analyze.run(folder, read_config(folder.book_toml))

    assert not folder.pages_json.exists()


@pytest.mark.thread_unsafe
def test_front_matter_end_its_step_and_pages_are_logged_at_info(
    tmp_path: Path,
    excerpt_book_toml: frozendict[str, str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    folder = BookFolder(tmp_path)
    folder.book_toml.write_text(excerpt_book_toml["haskins_front"], encoding="utf-8")

    with caplog.at_level(logging.INFO, logger="galley.analyze"):
        analyze.run(folder, read_config(folder.book_toml))

    assert [
        (record.levelno, record.getMessage())
        for record in caplog.records
        if "front matter" in record.getMessage()
    ] == [
        (
            logging.INFO,
            (
                "analyze: the front matter ends at page index 5, by the first "
                "preface page; page indices 0, 1, 2, 3, 4 are front matter, their "
                "words dropped"
            ),
        )
    ]


@pytest.mark.thread_unsafe
def test_front_matter_ended_at_running_text_dropping_pages_without_contents_pages_is_a_warning(
    tmp_path: Path,
    excerpt_book_toml: frozendict[str, str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Gierke's excerpt without its contents_pages: the running text starts
    # at excerpt page 2, after two front pages (front-matter spec section 2).
    folder = BookFolder(tmp_path)
    folder.book_toml.write_text(
        excerpt_book_toml["gierke_front_flow"].replace("contents_pages = [5]\n", ""),
        encoding="utf-8",
    )

    with caplog.at_level(logging.INFO, logger="galley.analyze"):
        analyze.run(folder, read_config(folder.book_toml))

    assert [
        (record.levelno, record.getMessage())
        for record in caplog.records
        if "front matter" in record.getMessage()
    ] == [
        (
            logging.INFO,
            (
                "analyze: the front matter ends at page index 2, by the first "
                "page of running text; page indices 0, 1 are front matter, their "
                "words dropped"
            ),
        ),
        (
            logging.WARNING,
            (
                "analyze: the front matter ends at the first page of running "
                "text, page index 2, and the config has no `contents_pages`; "
                "add the pages of the printed table of contents, or set "
                "`front_matter_end`"
            ),
        ),
    ]


@pytest.mark.thread_unsafe
def test_front_matter_ended_at_running_text_dropping_nothing_logs_no_warning(
    tmp_path: Path,
    excerpt_pdf: frozendict[str, Path],
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Kadesh's excerpt opens with running text and has no contents_pages:
    # the end is 0 and nothing is dropped (front-matter spec section 2).
    folder = kadesh_folder(tmp_path, excerpt_pdf[KADESH], "exclude_pages = [8]\n")

    with caplog.at_level(logging.INFO, logger="galley.analyze"):
        analyze.run(folder, read_config(folder.book_toml))

    assert [
        (record.levelno, record.getMessage())
        for record in caplog.records
        if "front matter" in record.getMessage()
    ] == [
        (
            logging.INFO,
            (
                "analyze: the front matter ends at page index 0, by the first "
                "page of running text; no page is front matter"
            ),
        ),
    ]


@pytest.mark.thread_unsafe
def test_front_matter_ended_by_contents_pages_logs_no_warning(
    tmp_path: Path,
    excerpt_book_toml: frozendict[str, str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    folder = BookFolder(tmp_path)
    folder.book_toml.write_text(
        excerpt_book_toml["gierke_front_flow"], encoding="utf-8"
    )

    with caplog.at_level(logging.INFO, logger="galley.analyze"):
        analyze.run(folder, read_config(folder.book_toml))

    assert [
        (record.levelno, record.getMessage())
        for record in caplog.records
        if "front matter" in record.getMessage()
    ] == [
        (
            logging.INFO,
            (
                "analyze: the front matter ends at page index 5, by the first "
                "page of `contents_pages`; page indices 0, 1, 2, 3, 4 are front "
                "matter, their words dropped"
            ),
        )
    ]


# The whole books (plates spec section 1)

# The 21 plates of the six books, by Internet Archive identifier, with the
# configs of tests/conftest.py: those without a text layer are Kadesh 17,
# 23 (named in plate_pages), 35, 43, 57 and 69, and Stubbs' four maps.
WHOLE_BOOK_PLATES = frozendict(
    {
        "battleofkadeshst00breauoft": (
            (17, TextSource.NONE),
            (19, TextSource.TEXT_LAYER),
            (22, TextSource.TEXT_LAYER),
            (23, TextSource.NONE),
            (24, TextSource.TEXT_LAYER),
            (34, TextSource.TEXT_LAYER),
            (35, TextSource.NONE),
            (42, TextSource.TEXT_LAYER),
            (43, TextSource.NONE),
            (48, TextSource.TEXT_LAYER),
            (56, TextSource.TEXT_LAYER),
            (57, TextSource.NONE),
            (64, TextSource.TEXT_LAYER),
            (68, TextSource.TEXT_LAYER),
            (69, TextSource.NONE),
        ),
        "domesdaybook00maituoft": (
            (39, TextSource.TEXT_LAYER),
            (40, TextSource.TEXT_LAYER),
        ),
        "earlyplantagenet01stub": (
            (9, TextSource.NONE),
            (11, TextSource.NONE),
            (52, TextSource.NONE),
            (54, TextSource.NONE),
        ),
        "catherinedemedic00mariuoft": (),
        "normansineuropea00hask": (),
        "politicaltheorie00gieruoft": (),
    }
)


def test_the_whole_book_plates_are_21_of_them_15_of_kadesh() -> None:
    assert sum(len(plates) for plates in WHOLE_BOOK_PLATES.values()) == 21
    assert len(WHOLE_BOOK_PLATES["battleofkadeshst00breauoft"]) == 15


@pytest.fixture(scope="module")
def whole_book_pages(
    tmp_path_factory: pytest.TempPathFactory, whole_book_toml: frozendict[str, str]
) -> frozendict[str, tuple[PageInfo, ...]]:
    """The pages of each whole book as analyze finds them with the configs of
    tests/conftest.py, by Internet Archive identifier: one run of analyze
    per book for every test of the module."""
    pages = {}
    for book in sorted(whole_book_toml):
        folder = BookFolder(tmp_path_factory.mktemp(book))
        folder.book_toml.write_text(whole_book_toml[book], encoding="utf-8")
        analyze.run(folder, read_config(folder.book_toml))
        pages[book] = read_pages(folder.pages_json).pages
    return frozendict(pages)


@pytest.mark.whole_book
@pytest.mark.thread_unsafe
@pytest.mark.timeout(600)
@pytest.mark.parametrize("book", sorted(WHOLE_BOOK_PLATES))
def test_analyze_takes_the_plates_of_each_whole_book_and_no_other_page(
    book: str,
    whole_book_toml: frozendict[str, str],
    whole_book_pages: frozendict[str, tuple[PageInfo, ...]],
) -> None:
    # The plates without a text layer are not excluded.
    assert not set(tomllib.loads(whole_book_toml[book]).get("exclude_pages", [])) & {
        index
        for index, text_source in WHOLE_BOOK_PLATES[book]
        if text_source is TextSource.NONE
    }
    assert (
        tuple(
            (page.index, page.text_source)
            for page in whole_book_pages[book]
            if page.kind is PageKind.PLATE
        )
        == WHOLE_BOOK_PLATES[book]
    )


# Extract spec section 7, "Whole books": the page count of each whole book
# and its pages that are not text, with their kinds, as analyze gave them
# at commit 9f012ac, before it read the text layer through
# text_layer.layer_words (run on 17 November 2026 with the configs of
# tests/conftest.py). The words analyze reads now change no page's kind.
WHOLE_BOOK_PAGE_KINDS_AT_9F012AC = frozendict(
    {
        "battleofkadeshst00breauoft": (
            76,
            (
                (0, PageKind.EXCLUDED),
                (1, PageKind.EXCLUDED),
                (2, PageKind.EXCLUDED),
                (3, PageKind.EXCLUDED),
                (16, PageKind.EXCLUDED),
                (17, PageKind.PLATE),
                (19, PageKind.PLATE),
                (22, PageKind.PLATE),
                (23, PageKind.PLATE),
                (24, PageKind.PLATE),
                (34, PageKind.PLATE),
                (35, PageKind.PLATE),
                (42, PageKind.PLATE),
                (43, PageKind.PLATE),
                (48, PageKind.PLATE),
                (49, PageKind.EXCLUDED),
                (56, PageKind.PLATE),
                (57, PageKind.PLATE),
                (64, PageKind.PLATE),
                (65, PageKind.EXCLUDED),
                (68, PageKind.PLATE),
                (69, PageKind.PLATE),
                (70, PageKind.EXCLUDED),
                (71, PageKind.EXCLUDED),
                (72, PageKind.EXCLUDED),
                (73, PageKind.EXCLUDED),
                (75, PageKind.EXCLUDED),
            ),
        ),
        "catherinedemedic00mariuoft": (
            460,
            (
                (0, PageKind.EXCLUDED),
                (1, PageKind.EXCLUDED),
                (2, PageKind.EXCLUDED),
                (3, PageKind.EXCLUDED),
                (4, PageKind.EXCLUDED),
                (5, PageKind.EXCLUDED),
                (17, PageKind.EXCLUDED),
                (449, PageKind.EXCLUDED),
                (451, PageKind.EXCLUDED),
                (453, PageKind.EXCLUDED),
                (454, PageKind.EXCLUDED),
                (455, PageKind.EXCLUDED),
                (456, PageKind.EXCLUDED),
                (457, PageKind.EXCLUDED),
                (458, PageKind.EXCLUDED),
            ),
        ),
        "domesdaybook00maituoft": (
            558,
            (
                (0, PageKind.EXCLUDED),
                (1, PageKind.EXCLUDED),
                (2, PageKind.EXCLUDED),
                (3, PageKind.EXCLUDED),
                (5, PageKind.EXCLUDED),
                (6, PageKind.EXCLUDED),
                (7, PageKind.EXCLUDED),
                (38, PageKind.EXCLUDED),
                (39, PageKind.PLATE),
                (40, PageKind.PLATE),
                (41, PageKind.EXCLUDED),
                (554, PageKind.EXCLUDED),
                (555, PageKind.EXCLUDED),
                (557, PageKind.EXCLUDED),
            ),
        ),
        "earlyplantagenet01stub": (
            344,
            (
                (0, PageKind.EXCLUDED),
                (2, PageKind.EXCLUDED),
                (3, PageKind.EXCLUDED),
                (4, PageKind.EXCLUDED),
                (5, PageKind.EXCLUDED),
                (8, PageKind.EXCLUDED),
                (9, PageKind.PLATE),
                (10, PageKind.EXCLUDED),
                (11, PageKind.PLATE),
                (52, PageKind.PLATE),
                (53, PageKind.EXCLUDED),
                (54, PageKind.PLATE),
                (55, PageKind.EXCLUDED),
                # The publisher's lists, excluded since the plan owner-books
                # (structure spec section 27, point 4).
                (322, PageKind.EXCLUDED),
                (323, PageKind.EXCLUDED),
                (324, PageKind.EXCLUDED),
                (325, PageKind.EXCLUDED),
                (326, PageKind.EXCLUDED),
                (327, PageKind.EXCLUDED),
                (328, PageKind.EXCLUDED),
                (329, PageKind.EXCLUDED),
                (330, PageKind.EXCLUDED),
                (331, PageKind.EXCLUDED),
                (332, PageKind.EXCLUDED),
                (333, PageKind.EXCLUDED),
                (334, PageKind.EXCLUDED),
                (335, PageKind.EXCLUDED),
                (336, PageKind.EXCLUDED),
                (337, PageKind.EXCLUDED),
                (338, PageKind.EXCLUDED),
                (339, PageKind.EXCLUDED),
                (340, PageKind.EXCLUDED),
                (341, PageKind.EXCLUDED),
                (342, PageKind.EXCLUDED),
                (343, PageKind.EXCLUDED),
            ),
        ),
        "normansineuropea00hask": (
            280,
            (
                (0, PageKind.EXCLUDED),
                (3, PageKind.EXCLUDED),
                (4, PageKind.EXCLUDED),
                (5, PageKind.EXCLUDED),
                (7, PageKind.EXCLUDED),
                (11, PageKind.EXCLUDED),
                (15, PageKind.EXCLUDED),
                (265, PageKind.EXCLUDED),
                (274, PageKind.EXCLUDED),
                (276, PageKind.EXCLUDED),
                (279, PageKind.EXCLUDED),
            ),
        ),
        "politicaltheorie00gieruoft": (
            290,
            (
                (0, PageKind.EXCLUDED),
                (2, PageKind.EXCLUDED),
                (3, PageKind.EXCLUDED),
                (4, PageKind.EXCLUDED),
                (5, PageKind.EXCLUDED),
                (51, PageKind.EXCLUDED),
                (283, PageKind.EXCLUDED),
                (284, PageKind.EXCLUDED),
                (285, PageKind.EXCLUDED),
                (286, PageKind.EXCLUDED),
                (287, PageKind.EXCLUDED),
                (288, PageKind.EXCLUDED),
                (289, PageKind.EXCLUDED),
            ),
        ),
    }
)


# Front-matter spec section 4: the pages of each whole book that analyze
# makes front_matter, text pages at 9f012ac.
WHOLE_BOOK_FRONT_MATTER = frozendict(
    {
        "normansineuropea00hask": (1, 2, 6, 8, 9, 10),
        "earlyplantagenet01stub": (1, 6, 7, 12, 13),
        "domesdaybook00maituoft": (4, 8, 9, 10, 11),
        "catherinedemedic00mariuoft": (6, 7, 8, 9),
        "politicaltheorie00gieruoft": (1, 6, 7, 8, 9),
        "battleofkadeshst00breauoft": (4, 5, 6, 7),
    }
)


@pytest.mark.whole_book
@pytest.mark.thread_unsafe
@pytest.mark.timeout(600)
@pytest.mark.parametrize("book", sorted(WHOLE_BOOK_PAGE_KINDS_AT_9F012AC))
def test_page_kinds_of_each_whole_book_are_those_before_the_text_flow_and_front_matter(
    book: str, whole_book_pages: frozendict[str, tuple[PageInfo, ...]]
) -> None:
    pages = whole_book_pages[book]
    page_count, kinds_at_9f012ac = WHOLE_BOOK_PAGE_KINDS_AT_9F012AC[book]
    assert (
        len(pages),
        tuple(
            (page.index, page.kind) for page in pages if page.kind is not PageKind.TEXT
        ),
    ) == (
        page_count,
        tuple(
            sorted(
                (
                    *kinds_at_9f012ac,
                    *(
                        (index, PageKind.FRONT_MATTER)
                        for index in WHOLE_BOOK_FRONT_MATTER[book]
                    ),
                    *(
                        (index, PageKind.INKLESS)
                        for index in WHOLE_BOOK_INKLESS.get(book, ())
                    ),
                )
            )
        ),
    )


# Plates spec section 2b: the inkless pages of the eight books, with the
# configs of tests/conftest.py, are Haskins' back endpapers 277 and 278 and
# Haynes' blank pages 9 and 421; Mariejol's back board, 459, is not caught.
WHOLE_BOOK_INKLESS = frozendict({"normansineuropea00hask": (277, 278)})
OWNER_BOOK_INKLESS = frozendict({"haynes": (9, 421), "turney": ()})


@pytest.mark.whole_book
@pytest.mark.thread_unsafe
@pytest.mark.timeout(600)
@pytest.mark.parametrize("book", sorted(WHOLE_BOOK_PAGE_KINDS_AT_9F012AC))
def test_inkless_pages_of_each_public_domain_whole_book_are_haskins_back_endpapers(
    book: str, whole_book_pages: frozendict[str, tuple[PageInfo, ...]]
) -> None:
    assert tuple(
        page.index for page in whole_book_pages[book] if page.kind is PageKind.INKLESS
    ) == WHOLE_BOOK_INKLESS.get(book, ())


@pytest.mark.whole_book
@pytest.mark.thread_unsafe
@pytest.mark.timeout(600)
@pytest.mark.parametrize("book", sorted(OWNER_BOOK_INKLESS))
def test_inkless_pages_of_the_owners_books_are_haynes_blank_pages_9_and_421(
    book: str, owner_book_toml: Callable[[str], str], tmp_path: Path
) -> None:
    folder = BookFolder(tmp_path)
    folder.book_toml.write_text(owner_book_toml(book), encoding="utf-8")

    analyze.run(folder, read_config(folder.book_toml))

    assert (
        tuple(
            page.index
            for page in read_pages(folder.pages_json).pages
            if page.kind is PageKind.INKLESS
        )
        == OWNER_BOOK_INKLESS[book]
    )
