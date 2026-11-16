"""Tests of galley.analyze (spec section 6).

The unit tests build their configs and pages by hand. The excerpt tests
read the folders of the session fixture `excerpt_books`; a test that runs
analyze on a folder of its own is marked thread_unsafe, so that the
8-thread run does it once.
"""

from dataclasses import replace
from pathlib import Path

import pytest

from galley import analyze
from galley.analyze import check_config_pages, classify_page, require_text_layer
from galley.book_folder import BookFolder
from galley.config import BookConfig, ExcludedRegion, Language, OcrMode, read_config
from galley.errors import ConfigError, PdfError
from galley.model import (
    Box,
    PageInfo,
    PageKind,
    TextSource,
    pdf_sha256,
    read_pages,
)

KADESH = "kadesh_8-17"
GIERKE = "gierke_86-93_270-271"

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
    assert classify_page(3, 400.0, 600.0, 12, CONFIG) == PageInfo(
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

    assert classify_page(3, 400.0, 600.0, 12, config) == PageInfo(
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

    assert classify_page(4, 400.0, 600.0, 0, config).kind is PageKind.EXCLUDED


def test_page_without_layer_words_is_blank_with_no_text_source() -> None:
    assert classify_page(4, 400.0, 600.0, 0, CONFIG) == PageInfo(
        index=4,
        width_pt=400.0,
        height_pt=600.0,
        kind=PageKind.BLANK,
        text_source=TextSource.NONE,
        text_layer_score=None,
        exclude_regions=(),
        blank_checked_by_ocr=False,
    )


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


def test_require_text_layer_accepts_text_and_excluded_pages() -> None:
    pages = (
        page(0, PageKind.TEXT, TextSource.TEXT_LAYER),
        page(1, PageKind.EXCLUDED, TextSource.NONE),
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
    page = classify_page(23, 612.0, 792.0, 40, config)

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


def test_kadesh_pages_are_text_but_page_9_excluded_with_the_region_on_page_0(
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
            for index in range(9)
        ),
        PageInfo(
            index=9,
            width_pt=508.32,
            height_pt=728.16,
            kind=PageKind.EXCLUDED,
            text_source=TextSource.NONE,
            text_layer_score=None,
            exclude_regions=(),
            blank_checked_by_ocr=False,
        ),
    )


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
def test_kadesh_without_exclude_pages_stops_naming_page_9_alone_and_leaves_no_file(
    tmp_path: Path, excerpt_pdf: frozendict[str, Path]
) -> None:
    folder = kadesh_folder(tmp_path, excerpt_pdf[KADESH], "")
    folder.pages_json.write_text("an old pages.json\n", encoding="utf-8")

    with pytest.raises(PdfError, match=r"^page indices 9: these pages have no"):
        analyze.run(folder, read_config(folder.book_toml))

    assert not folder.pages_json.exists()


@pytest.mark.thread_unsafe
def test_ocr_redo_stops_analyze_before_writing_and_leaves_no_file(
    tmp_path: Path, excerpt_pdf: frozendict[str, Path]
) -> None:
    folder = kadesh_folder(tmp_path, excerpt_pdf[KADESH], 'ocr = "redo"\n')
    folder.pages_json.write_text("an old pages.json\n", encoding="utf-8")

    with pytest.raises(ConfigError, match=r"^ocr = redo needs OCR"):
        analyze.run(folder, read_config(folder.book_toml))

    assert not folder.pages_json.exists()
