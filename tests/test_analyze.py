"""Tests of galley.analyze (walking skeleton spec section 6, plates spec
sections 2 and 6).

The unit tests build their configs, pages and renders by hand. The excerpt tests
read the folders of the session fixture `excerpt_books`; a test that runs
analyze on a folder of its own is marked thread_unsafe, so that the
8-thread run does it once.
"""

import logging
import tomllib
from dataclasses import replace
from pathlib import Path

import pytest

from galley import analyze
from galley.analyze import (
    PictureArea,
    PlateRule,
    check_config_pages,
    classify_page,
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
        blank_checked_by_ocr=False,
    )


# classify_page


def test_page_with_layer_words_is_text_with_its_regions_in_config_order() -> None:
    assert classify_page(
        3, 400.0, 600.0, 12, CONFIG, plate_rule=PlateRule.NOT_PLATE
    ) == PageInfo(
        index=3,
        width_pt=400.0,
        height_pt=600.0,
        kind=PageKind.TEXT,
        text_source=TextSource.TEXT_LAYER,
        text_layer_score=None,
        exclude_regions=(REGION_A, REGION_B),
        blank_checked_by_ocr=False,
    )


def test_page_in_exclude_pages_is_excluded_although_it_has_layer_words() -> None:
    config = replace(CONFIG, exclude_pages=(1, 3))

    assert classify_page(
        3, 400.0, 600.0, 12, config, plate_rule=PlateRule.NOT_PLATE
    ) == PageInfo(
        index=3,
        width_pt=400.0,
        height_pt=600.0,
        kind=PageKind.EXCLUDED,
        text_source=TextSource.NONE,
        text_layer_score=None,
        exclude_regions=(REGION_A, REGION_B),
        blank_checked_by_ocr=False,
    )


def test_page_in_exclude_pages_without_layer_words_is_excluded_not_blank() -> None:
    config = replace(CONFIG, exclude_pages=(4,))

    assert (
        classify_page(4, 400.0, 600.0, 0, config, plate_rule=PlateRule.NOT_PLATE).kind
        is PageKind.EXCLUDED
    )


def test_page_without_layer_words_is_blank_with_no_text_source() -> None:
    assert classify_page(
        4, 400.0, 600.0, 0, CONFIG, plate_rule=PlateRule.NOT_PLATE
    ) == PageInfo(
        index=4,
        width_pt=400.0,
        height_pt=600.0,
        kind=PageKind.BLANK,
        text_source=TextSource.NONE,
        text_layer_score=None,
        exclude_regions=(),
        blank_checked_by_ocr=False,
    )


# classify_page with the plate rule (plates spec section 2)


def test_page_the_plate_rule_takes_is_a_plate_read_from_its_layer() -> None:
    page = classify_page(3, 400.0, 600.0, 4, CONFIG, plate_rule=PlateRule.PLATE)

    assert (page.kind, page.text_source) == (PageKind.PLATE, TextSource.TEXT_LAYER)
    assert page.exclude_regions == (REGION_A, REGION_B)


def test_page_without_a_layer_the_plate_rule_takes_is_a_plate_with_no_source() -> None:
    page = classify_page(4, 400.0, 600.0, 0, CONFIG, plate_rule=PlateRule.PLATE)

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
        23, 612.0, 792.0, layer_word_count, config, plate_rule=PlateRule.NOT_PLATE
    )

    assert (page.kind, page.text_source) == (PageKind.PLATE, text_source)


def test_cover_page_the_plate_rule_takes_is_never_a_plate() -> None:
    config = replace(CONFIG, cover_page=0)

    page = classify_page(0, 400.0, 600.0, 12, config, plate_rule=PlateRule.PLATE)

    assert page.kind is PageKind.TEXT


def test_excluded_page_the_plate_rule_takes_is_excluded() -> None:
    config = replace(CONFIG, exclude_pages=(3,))

    page = classify_page(3, 400.0, 600.0, 12, config, plate_rule=PlateRule.PLATE)

    assert (page.kind, page.text_source) == (PageKind.EXCLUDED, TextSource.NONE)


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
    page = classify_page(23, 612.0, 792.0, 40, config, plate_rule=PlateRule.NOT_PLATE)

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
    ],
    ids=[
        "exclude_pages",
        "exclude_regions",
        "cover_page",
        "plate_pages",
        "contents_pages",
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


# The excerpts, from the session fixture.


def test_kadesh_pages_are_text_but_plates_8_and_9_with_the_region_on_page_0(
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
                blank_checked_by_ocr=False,
            )
            for index in range(8)
        ),
        # Book page 16, a relief whose layer holds 4 stray words.
        PageInfo(
            index=8,
            width_pt=508.32,
            height_pt=728.16,
            kind=PageKind.PLATE,
            text_source=TextSource.TEXT_LAYER,
            text_layer_score=None,
            exclude_regions=(),
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
            blank_checked_by_ocr=False,
        ),
    )


# The plates of each excerpt, by page index in the excerpt (plates spec
# section 6): Kadesh 16 and 17; Kadesh 64, 65 (the back of plate 64, a
# known wrong case) and 68; Domesday's maps 39 and 40. The other
# excerpts have none.
EXCERPT_PLATES = frozendict(
    {
        "kadesh_8-17": (8, 9),
        "kadesh_59-68": (5, 6, 9),
        "domesday_headings_quotes": (3, 4),
    }
)


def test_the_excerpts_plates_are_those_of_the_spec_and_every_other_page_is_text(
    excerpt_books: frozendict[str, BookFolder],
) -> None:
    for name, folder in excerpt_books.items():
        pages = read_pages(folder.pages_json).pages
        plates = EXCERPT_PLATES.get(name, ())
        # Haskins' blank page before the index is excluded by its config.
        excluded = (8,) if name == "haskins_eval" else ()
        assert tuple(page.index for page in pages if page.kind is PageKind.PLATE) == (
            plates
        ), name
        assert all(
            page.kind is PageKind.TEXT
            for page in pages
            if page.index not in plates and page.index not in excluded
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
    # Page 8 by the rule is logged, page 9 made a plate by the config is not.
    folder = kadesh_folder(tmp_path, excerpt_pdf[KADESH], "plate_pages = [9]\n")

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
def test_a_plate_without_a_layer_is_logged_with_its_share_of_the_page(
    tmp_path: Path,
    excerpt_pdf: frozendict[str, Path],
    caplog: pytest.LogCaptureFixture,
) -> None:
    folder = kadesh_folder(tmp_path, excerpt_pdf[KADESH], "exclude_pages = [8]\n")

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
def test_ocr_redo_stops_analyze_before_writing_and_leaves_no_file(
    tmp_path: Path, excerpt_pdf: frozendict[str, Path]
) -> None:
    folder = kadesh_folder(tmp_path, excerpt_pdf[KADESH], 'ocr = "redo"\n')
    folder.pages_json.write_text("an old pages.json\n", encoding="utf-8")

    with pytest.raises(ConfigError, match=r"^ocr = redo needs OCR"):
        analyze.run(folder, read_config(folder.book_toml))

    assert not folder.pages_json.exists()


# The whole books (plates spec section 1)

# The 22 plates of the six books, by Internet Archive identifier, with the
# configs of tests/conftest.py: those without a text layer are Kadesh 17,
# 23 (named in plate_pages), 35, 43, 57 and 69, and Stubbs' four maps.
WHOLE_BOOK_PLATES = frozendict(
    {
        "battleofkadeshst00breauoft": (
            (16, TextSource.TEXT_LAYER),
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


def test_the_whole_book_plates_are_22() -> None:
    assert sum(len(plates) for plates in WHOLE_BOOK_PLATES.values()) == 22


@pytest.mark.whole_book
@pytest.mark.thread_unsafe
@pytest.mark.timeout(600)
@pytest.mark.parametrize("book", sorted(WHOLE_BOOK_PLATES))
def test_analyze_takes_the_plates_of_each_whole_book_and_no_other_page(
    book: str, whole_book_toml: frozendict[str, str], tmp_path: Path
) -> None:
    folder = BookFolder(tmp_path)
    folder.book_toml.write_text(whole_book_toml[book], encoding="utf-8")
    config = read_config(folder.book_toml)
    # The plates without a text layer are not excluded.
    assert not set(tomllib.loads(whole_book_toml[book]).get("exclude_pages", [])) & {
        index
        for index, text_source in WHOLE_BOOK_PLATES[book]
        if text_source is TextSource.NONE
    }

    analyze.run(folder, config)

    assert (
        tuple(
            (page.index, page.text_source)
            for page in read_pages(folder.pages_json).pages
            if page.kind is PageKind.PLATE
        )
        == WHOLE_BOOK_PLATES[book]
    )
