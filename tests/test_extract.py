"""Tests of galley.extract (walking skeleton spec section 6, plates spec
section 3).

The unit tests of `page_words` build their pages and words by hand. The
excerpt tests read the folders of the session fixture `excerpt_books`; a
test that runs extract on a folder of its own is marked thread_unsafe, so
that the 8-thread run does it once.
"""

import shutil
from dataclasses import replace
from pathlib import Path

import pytest
from PIL import Image

from galley import analyze, extract
from galley.book_folder import BookFolder
from galley.config import read_config
from galley.errors import InputFileError
from galley.extract import page_words, plate_image
from galley.model import (
    Box,
    Figure,
    PageInfo,
    PageKind,
    PagesFile,
    PageWords,
    Removal,
    RemovalReason,
    TextSource,
    Word,
    read_pages,
    read_words,
    write_pages,
)

KADESH = "kadesh_8-17"
GIERKE = "gierke_86-93_270-271"

# Spec section 2: the words of extract_words() per page, pdfplumber 0.11.10.
KADESH_WORD_COUNTS = (584, 641, 671, 904, 822, 764, 909, 822, 4, 0)
GIERKE_WORD_COUNTS = (192, 311, 297, 325, 319, 309, 292, 273, 547, 541)

REGION = Box(10.0, 10.0, 20.0, 20.0)

# The figures of the Kadesh excerpt's plates, pages 8 and 9 (book pages 16
# and 17): the whole page, at 300 dpi.
KADESH_PLATE_FIGURE = frozendict(
    {
        index: Figure(
            box=Box(0.0, 0.0, 508.32, 728.16),
            image=f"images/plate-{index:04d}.png",
            dpi=300,
        )
        for index in (8, 9)
    }
)


def page(
    kind: PageKind,
    text_source: TextSource,
    exclude_regions: tuple[Box, ...] = (),
) -> PageInfo:
    return PageInfo(
        index=4,
        width_pt=400.0,
        height_pt=600.0,
        kind=kind,
        text_source=text_source,
        text_layer_score=None,
        exclude_regions=exclude_regions,
        blank_checked_by_ocr=False,
    )


def word(text: str, box: Box) -> Word:
    return Word(text, box, None)


TEXT_PAGE = page(
    PageKind.TEXT, TextSource.TEXT_LAYER, (Box(300.0, 300.0, 310.0, 310.0), REGION)
)


# page_words


def test_word_with_its_centre_inside_a_region_is_a_removal() -> None:
    inside = word("81", Box(12.0, 12.0, 16.0, 16.0))

    assert page_words(TEXT_PAGE, (inside,)) == (
        PageWords(index=4, text_source=TextSource.TEXT_LAYER, words=(), figures=()),
        (
            Removal(
                page_index=4,
                box=inside.box,
                text="81",
                reason=RemovalReason.EXCLUDED_REGION,
            ),
        ),
    )


def test_word_touching_a_region_with_its_centre_outside_stays() -> None:
    # Centre (8, 15): the word reaches 6 pt into the region.
    touching = word("ROB.,", Box(0.0, 12.0, 16.0, 18.0))

    assert page_words(TEXT_PAGE, (touching,)) == (
        PageWords(
            index=4, text_source=TextSource.TEXT_LAYER, words=(touching,), figures=()
        ),
        (),
    )


@pytest.mark.parametrize(
    "box",
    [Box(18.0, 12.0, 22.0, 18.0), Box(12.0, 8.0, 18.0, 12.0)],
    ids=["centre_on_x1", "centre_on_top"],
)
def test_word_with_its_centre_on_the_edge_of_a_region_is_a_removal(box: Box) -> None:
    assert page_words(TEXT_PAGE, (word("on", box),)) == (
        PageWords(index=4, text_source=TextSource.TEXT_LAYER, words=(), figures=()),
        (
            Removal(
                page_index=4, box=box, text="on", reason=RemovalReason.EXCLUDED_REGION
            ),
        ),
    )


def test_words_and_removals_keep_the_order_the_layer_gave() -> None:
    words = (
        word("b", Box(15.0, 15.0, 16.0, 16.0)),
        word("z", Box(100.0, 100.0, 110.0, 110.0)),
        word("a", Box(11.0, 11.0, 12.0, 12.0)),
        word("y", Box(50.0, 50.0, 60.0, 60.0)),
    )

    kept, removals = page_words(TEXT_PAGE, words)

    assert tuple(kept_word.text for kept_word in kept.words) == ("z", "y")
    assert tuple(removal.text for removal in removals) == ("b", "a")


def test_excluded_page_with_three_words_gives_three_removals_and_no_words() -> None:
    excluded = page(PageKind.EXCLUDED, TextSource.NONE, (REGION,))
    words = (
        word(",", Box(1.0, 2.0, 3.0, 4.0)),
        word("'", Box(12.0, 12.0, 14.0, 14.0)),
        word("^U;L", Box(5.0, 6.0, 7.0, 8.0)),
    )

    assert page_words(excluded, words) == (
        PageWords(index=4, text_source=TextSource.NONE, words=(), figures=()),
        tuple(
            Removal(
                page_index=4,
                box=layer_word.box,
                text=layer_word.text,
                reason=RemovalReason.EXCLUDED_PAGE,
            )
            for layer_word in words
        ),
    )


def test_blank_page_has_no_words_and_no_removals() -> None:
    assert page_words(page(PageKind.BLANK, TextSource.NONE), ()) == (
        PageWords(index=4, text_source=TextSource.NONE, words=(), figures=()),
        (),
    )


# A plate page (plates spec section 3)

PLATE_FIGURE = Figure(
    box=Box(0.0, 0.0, 400.0, 600.0), image="images/plate-0004.png", dpi=300
)


def test_plate_image_is_named_by_its_page_index_in_4_digits() -> None:
    assert plate_image(16) == "images/plate-0016.png"
    assert plate_image(4) == "images/plate-0004.png"
    assert plate_image(12345) == "images/plate-12345.png"


def test_plate_page_with_a_layer_keeps_its_words_and_has_the_whole_page_figure() -> (
    None
):
    plate = page(PageKind.PLATE, TextSource.TEXT_LAYER, (REGION,))
    stray = word("^U;L", Box(330.0, 627.0, 351.0, 637.0))
    in_region = word("81", Box(12.0, 12.0, 16.0, 16.0))

    assert page_words(plate, (stray, in_region)) == (
        PageWords(
            index=4,
            text_source=TextSource.TEXT_LAYER,
            words=(stray,),
            figures=(PLATE_FIGURE,),
        ),
        (
            Removal(
                page_index=4,
                box=in_region.box,
                text="81",
                reason=RemovalReason.EXCLUDED_REGION,
            ),
        ),
    )


def test_plate_page_without_a_layer_has_its_figure_and_no_words() -> None:
    assert page_words(page(PageKind.PLATE, TextSource.NONE), ()) == (
        PageWords(
            index=4, text_source=TextSource.NONE, words=(), figures=(PLATE_FIGURE,)
        ),
        (),
    )


@pytest.mark.parametrize(
    ("kind", "text_source", "layer_words"),
    [
        (PageKind.BLANK, TextSource.NONE, (word("lost", Box(1.0, 1.0, 2.0, 2.0)),)),
        (PageKind.PLATE, TextSource.NONE, (word("lost", Box(1.0, 1.0, 2.0, 2.0)),)),
        (PageKind.TEXT, TextSource.OCR, ()),
        (PageKind.PLATE, TextSource.OCR, ()),
    ],
    ids=["blank_with_words", "plate_without_layer_with_words", "ocr", "plate_ocr"],
)
def test_page_extract_cannot_read_or_whose_words_would_be_lost_is_a_value_error(
    kind: PageKind, text_source: TextSource, layer_words: tuple[Word, ...]
) -> None:
    with pytest.raises(ValueError, match=r"^page 4 "):
        page_words(page(kind, text_source), layer_words)


# The excerpts, from the session fixture.


def test_word_counts_per_page_are_those_of_the_text_layer_but_81_and_page_9(
    excerpt_books: frozendict[str, BookFolder],
) -> None:
    kadesh = read_words(excerpt_books[KADESH].words_json)
    gierke = read_words(excerpt_books[GIERKE].words_json)

    assert tuple(len(page_words.words) for page_words in kadesh.pages) == (
        583,
        *KADESH_WORD_COUNTS[1:],
    )
    assert tuple(len(page_words.words) for page_words in gierke.pages) == (
        GIERKE_WORD_COUNTS
    )


def test_pages_have_their_index_their_text_source_and_figures_on_plates_alone(
    excerpt_books: frozendict[str, BookFolder],
) -> None:
    kadesh = read_words(excerpt_books[KADESH].words_json)
    gierke = read_words(excerpt_books[GIERKE].words_json)

    assert tuple(
        (page_words.index, page_words.text_source, page_words.figures)
        for page_words in kadesh.pages
    ) == (
        *((index, TextSource.TEXT_LAYER, ()) for index in range(8)),
        (8, TextSource.TEXT_LAYER, (KADESH_PLATE_FIGURE[8],)),
        (9, TextSource.NONE, (KADESH_PLATE_FIGURE[9],)),
    )
    assert tuple(
        (page_words.index, page_words.text_source, page_words.figures)
        for page_words in gierke.pages
    ) == tuple((index, TextSource.TEXT_LAYER, ()) for index in range(10))


def test_words_json_carries_the_pdf_hash_of_pages_json(
    excerpt_books: frozendict[str, BookFolder],
) -> None:
    for folder in excerpt_books.values():
        assert (
            read_words(folder.words_json).source_pdf_sha256
            == read_pages(folder.pages_json).source_pdf_sha256
        )


def test_kadesh_only_removal_is_the_page_number_81_in_its_region(
    excerpt_books: frozendict[str, BookFolder],
) -> None:
    assert read_words(excerpt_books[KADESH].words_json).removals == (
        Removal(
            page_index=0,
            box=Box(241.68, 622.509, 249.07648, 629.509),
            text="81",
            reason=RemovalReason.EXCLUDED_REGION,
        ),
    )


def test_kadesh_word_touching_the_region_with_its_centre_outside_stays(
    excerpt_books: frozendict[str, BookFolder],
) -> None:
    page_0 = read_words(excerpt_books[KADESH].words_json).pages[0]

    assert [
        (round(kept.box.x0, 2), round(kept.box.x1, 2))
        for kept in page_0.words
        if kept.text == "ROB.,"
    ] == [(223.92, 244.8)]


def test_kadesh_page_0_starts_with_the_title(
    excerpt_books: frozendict[str, BookFolder],
) -> None:
    page_0 = read_words(excerpt_books[KADESH].words_json).pages[0]

    assert tuple(kept.text for kept in page_0.words[:6]) == (
        "THE",
        "BATTLE",
        "OF",
        "KADESH",
        "A",
        "STUDY",
    )


def test_kadesh_page_8_holds_exactly_the_four_stray_words_of_the_plate(
    excerpt_books: frozendict[str, BookFolder],
) -> None:
    page_8 = read_words(excerpt_books[KADESH].words_json).pages[8]

    assert tuple(kept.text for kept in page_8.words) == (",", "'", "..", "^U;L")
    assert all(kept.ocr_confidence is None for kept in page_8.words)


def test_gierke_page_9_starts_with_its_running_head_and_has_no_removal(
    excerpt_books: frozendict[str, BookFolder],
) -> None:
    gierke = read_words(excerpt_books[GIERKE].words_json)

    assert tuple(kept.text for kept in gierke.pages[9].words[:6]) == (
        "1",
        "86",
        "Political",
        "Theories",
        "of",
        "the",
    )
    assert gierke.removals == ()


def test_kadesh_cover_is_page_0_at_300_dpi_in_8_bit_grayscale(
    excerpt_books: frozendict[str, BookFolder],
) -> None:
    with Image.open(excerpt_books[KADESH].cover_png) as cover:
        assert (cover.format, cover.mode, cover.size) == ("PNG", "L", (2118, 3034))


# The plates of the excerpts (plates spec section 6), by page index in the
# excerpt: Kadesh 16 and 17; Kadesh 64, 65 (the back of plate 64) and 68;
# Domesday's maps 39 and 40. Each has its image, and nothing else is in
# images/ but the cover.
EXCERPT_PLATES = frozendict(
    {
        "kadesh_8-17": (8, 9),
        "kadesh_59-68": (5, 6, 9),
        "domesday_headings_quotes": (3, 4),
    }
)


def test_each_excerpt_plate_has_its_whole_page_figure_and_its_image_alone(
    excerpt_books: frozendict[str, BookFolder],
) -> None:
    for name, folder in excerpt_books.items():
        plates = EXCERPT_PLATES.get(name, ())
        pages = read_pages(folder.pages_json).pages
        words = read_words(folder.words_json)
        assert tuple(
            page_words.index for page_words in words.pages if page_words.figures
        ) == (plates), name
        for index in plates:
            assert words.pages[index].figures == (
                Figure(
                    box=Box(0.0, 0.0, pages[index].width_pt, pages[index].height_pt),
                    image=f"images/plate-{index:04d}.png",
                    dpi=300,
                ),
            ), name
            with Image.open(folder.root / words.pages[index].figures[0].image) as plate:
                assert (plate.format, plate.mode) == ("PNG", "L"), name
        cover = ("cover.png",) if name == KADESH else ()
        assert sorted(path.name for path in folder.images_dir.iterdir()) == sorted(
            (*cover, *(f"plate-{index:04d}.png" for index in plates))
        ), name


def test_gierke_without_cover_page_has_an_empty_images_folder(
    excerpt_books: frozendict[str, BookFolder],
) -> None:
    images_dir = excerpt_books[GIERKE].images_dir

    assert images_dir.is_dir()
    assert list(images_dir.iterdir()) == []


# Runs of their own.


def kadesh_folder(root: Path, pdf: Path, settings: str) -> BookFolder:
    """A book folder for the Kadesh excerpt whose book.toml has `settings`
    besides the required keys."""
    root.mkdir(parents=True, exist_ok=True)
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


# Removals on two pages, so that their order is tested: the page number 81
# in the region of page 0, and the 4 words of the plate on page 8.
TWO_PAGES_OF_REMOVALS = (
    "exclude_pages = [8, 9]\n"
    "exclude_regions = [{page = 0, box = [240, 620, 252, 632]}]\n"
)

# The boxes of pdfplumber 0.11.10's extract_words() on Kadesh pages 0 and 8,
# read with pdfplumber directly, not through galley (spec section 11).
KADESH_REMOVALS = (
    Removal(
        page_index=0,
        box=Box(241.68, 622.509, 249.07648, 629.509),
        text="81",
        reason=RemovalReason.EXCLUDED_REGION,
    ),
    Removal(
        page_index=8,
        box=Box(488.4, 222.33399999999995, 490.15455, 227.33399999999995),
        text=",",
        reason=RemovalReason.EXCLUDED_PAGE,
    ),
    Removal(
        page_index=8,
        box=Box(492.23999999999995, 222.33399999999995, 494.05375, 227.33399999999995),
        text="'",
        reason=RemovalReason.EXCLUDED_PAGE,
    ),
    Removal(
        page_index=8,
        box=Box(
            496.31999999999994,
            222.33399999999995,
            497.8957999999999,
            227.33399999999995,
        ),
        text="..",
        reason=RemovalReason.EXCLUDED_PAGE,
    ),
    Removal(
        page_index=8,
        box=Box(330.48, 627.21, 351.6124, 637.21),
        text="^U;L",
        reason=RemovalReason.EXCLUDED_PAGE,
    ),
)


@pytest.mark.thread_unsafe
def test_kadesh_with_plate_page_excluded_has_81_and_its_4_words_as_the_removals(
    tmp_path: Path, excerpt_pdf: frozendict[str, Path]
) -> None:
    folder = kadesh_folder(tmp_path, excerpt_pdf[KADESH], TWO_PAGES_OF_REMOVALS)
    config = read_config(folder.book_toml)
    analyze.run(folder, config)
    # A file left by an earlier run, which extract must delete.
    folder.images_dir.mkdir()
    (folder.images_dir / "stale.png").write_bytes(b"not an image")

    extract.run(folder, config)

    words = read_words(folder.words_json)
    assert words.pages[8] == PageWords(
        index=8, text_source=TextSource.NONE, words=(), figures=()
    )
    assert words.removals == KADESH_REMOVALS
    assert list(folder.images_dir.iterdir()) == []


@pytest.mark.thread_unsafe
def test_kadesh_with_1_worker_and_with_6_gives_the_same_bytes(
    tmp_path: Path, excerpt_pdf: frozendict[str, Path]
) -> None:
    folders = {}
    for workers in (1, 6):
        folder = kadesh_folder(
            tmp_path / str(workers), excerpt_pdf[KADESH], TWO_PAGES_OF_REMOVALS
        )
        config = read_config(folder.book_toml)
        analyze.run(folder, config, workers=workers)
        extract.run(folder, config, workers=workers)
        folders[workers] = folder

    assert read_words(folders[1].words_json).removals == KADESH_REMOVALS
    assert folders[1].pages_json.read_bytes() == folders[6].pages_json.read_bytes()
    assert folders[1].words_json.read_bytes() == folders[6].words_json.read_bytes()


@pytest.mark.thread_unsafe
def test_extract_on_a_kadesh_folder_holding_the_gierke_pages_json_names_analyze(
    tmp_path: Path,
    excerpt_pdf: frozendict[str, Path],
    excerpt_books: frozendict[str, BookFolder],
) -> None:
    folder = kadesh_folder(tmp_path, excerpt_pdf[KADESH], "exclude_pages = [9]\n")
    shutil.copyfile(excerpt_books[GIERKE].pages_json, folder.pages_json)
    folder.words_json.write_text("an old words.json\n", encoding="utf-8")

    with pytest.raises(
        InputFileError,
        match=r"made from another PDF .* run `galley2epub analyze` again$",
    ):
        extract.run(folder, read_config(folder.book_toml))

    assert not folder.words_json.exists()
    assert not folder.images_dir.exists()


@pytest.mark.thread_unsafe
def test_extract_on_a_kadesh_folder_whose_config_names_the_gierke_pdf_names_analyze(
    tmp_path: Path,
    excerpt_pdf: frozendict[str, Path],
    excerpt_books: frozendict[str, BookFolder],
) -> None:
    folder = kadesh_folder(tmp_path, excerpt_pdf[KADESH], "exclude_pages = [9]\n")
    shutil.copyfile(excerpt_books[KADESH].pages_json, folder.pages_json)
    config = replace(read_config(folder.book_toml), pdf=excerpt_pdf[GIERKE])

    with pytest.raises(
        InputFileError,
        match=r"pages\.json was made from another PDF .* run `galley2epub analyze`",
    ):
        extract.run(folder, config)

    assert not folder.words_json.exists()


@pytest.mark.thread_unsafe
def test_extract_without_pages_json_names_analyze(
    tmp_path: Path, excerpt_pdf: frozendict[str, Path]
) -> None:
    folder = kadesh_folder(tmp_path, excerpt_pdf[KADESH], "exclude_pages = [9]\n")

    with pytest.raises(InputFileError, match=r"run `galley2epub analyze` to write it$"):
        extract.run(folder, read_config(folder.book_toml))


def _pages_with_plates_8_and_9(kadesh_pages: PagesFile) -> PagesFile:
    """The Kadesh excerpt's pages with page 8 a plate with a text layer and
    page 9 a plate without one, as plates spec section 6 has them."""
    return replace(
        kadesh_pages,
        pages=(
            *kadesh_pages.pages[:8],
            replace(
                kadesh_pages.pages[8],
                kind=PageKind.PLATE,
                text_source=TextSource.TEXT_LAYER,
            ),
            replace(
                kadesh_pages.pages[9], kind=PageKind.PLATE, text_source=TextSource.NONE
            ),
        ),
    )


@pytest.mark.thread_unsafe
def test_kadesh_plates_8_and_9_get_their_images_and_figures_and_8_keeps_its_words(
    tmp_path: Path,
    excerpt_pdf: frozendict[str, Path],
    excerpt_books: frozendict[str, BookFolder],
) -> None:
    folder = kadesh_folder(tmp_path, excerpt_pdf[KADESH], "cover_page = 0\n")
    write_pages(
        folder.pages_json,
        _pages_with_plates_8_and_9(read_pages(excerpt_books[KADESH].pages_json)),
    )

    extract.run(folder, read_config(folder.book_toml))

    words = read_words(folder.words_json)
    assert words.pages[8] == PageWords(
        index=8,
        text_source=TextSource.TEXT_LAYER,
        words=words.pages[8].words,
        figures=(
            Figure(
                box=Box(0.0, 0.0, 508.32, 728.16),
                image="images/plate-0008.png",
                dpi=300,
            ),
        ),
    )
    assert tuple(kept.text for kept in words.pages[8].words) == (
        ",",
        "'",
        "..",
        "^U;L",
    )
    assert words.pages[9] == PageWords(
        index=9,
        text_source=TextSource.NONE,
        words=(),
        figures=(
            Figure(
                box=Box(0.0, 0.0, 508.32, 728.16),
                image="images/plate-0009.png",
                dpi=300,
            ),
        ),
    )
    assert all(page_words.figures == () for page_words in words.pages[:8])
    # The page number 81 in the region of page 0 alone: the plate's words stay.
    assert words.removals == KADESH_REMOVALS[:1]
    assert sorted(path.name for path in folder.images_dir.iterdir()) == [
        "cover.png",
        "plate-0008.png",
        "plate-0009.png",
    ]
    for name in ("plate-0008.png", "plate-0009.png"):
        with Image.open(folder.images_dir / name) as plate:
            assert (plate.format, plate.mode, plate.size) == ("PNG", "L", (2118, 3034))


@pytest.mark.thread_unsafe
def test_kadesh_plates_with_1_worker_and_with_6_give_the_same_bytes(
    tmp_path: Path,
    excerpt_pdf: frozendict[str, Path],
    excerpt_books: frozendict[str, BookFolder],
) -> None:
    pages = _pages_with_plates_8_and_9(read_pages(excerpt_books[KADESH].pages_json))
    folders = {}
    for workers in (1, 6):
        folder = kadesh_folder(tmp_path / str(workers), excerpt_pdf[KADESH], "")
        write_pages(folder.pages_json, pages)
        extract.run(folder, read_config(folder.book_toml), workers=workers)
        folders[workers] = folder

    assert folders[1].words_json.read_bytes() == folders[6].words_json.read_bytes()
    for name in ("plate-0008.png", "plate-0009.png"):
        assert (folders[1].images_dir / name).read_bytes() == (
            folders[6].images_dir / name
        ).read_bytes()


@pytest.mark.thread_unsafe
def test_extract_on_pages_json_with_an_ocr_page_names_it_and_analyze(
    tmp_path: Path,
    excerpt_pdf: frozendict[str, Path],
    excerpt_books: frozendict[str, BookFolder],
) -> None:
    folder = kadesh_folder(tmp_path, excerpt_pdf[KADESH], "")
    pages = _pages_with_plates_8_and_9(read_pages(excerpt_books[KADESH].pages_json))
    write_pages(
        folder.pages_json,
        replace(
            pages,
            pages=(
                replace(pages.pages[0], text_source=TextSource.OCR),
                *pages.pages[1:],
            ),
        ),
    )

    with pytest.raises(InputFileError) as raised:
        extract.run(folder, read_config(folder.book_toml))

    assert str(raised.value) == (
        f"{folder.pages_json}: page indices 0 are read by OCR, which extract "
        "cannot read yet; run `galley2epub analyze` again"
    )
    assert not folder.words_json.exists()
