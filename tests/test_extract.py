"""Tests of galley.extract (walking skeleton spec section 6, plates spec
section 3).

The unit tests of `page_words` build their pages and words by hand. The
excerpt tests read the folders of the session fixture `excerpt_books`; a
test that runs extract on a folder of its own is marked thread_unsafe, so
that the 8-thread run does it once.
"""

import shutil
from collections.abc import Callable
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
    FigureKind,
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

# The words of text_layer.layer_words per page (extract spec sections 3 and
# 4), pdfplumber 0.11.10. With extract_words() and its default options,
# Kadesh's were (584, 641, 671, 904, 822, 764, 909, 822, 4, 0) and Gierke's
# (192, 311, 297, 325, 319, 309, 292, 273, 547, 541). Both text layers have
# space characters, so no word is split; the differences are the pieces of
# cut words joined and overlaid words pulled apart (spec section 3).
KADESH_WORD_COUNTS = (582, 639, 668, 854, 818, 733, 832, 816, 4, 0)
GIERKE_WORD_COUNTS = (192, 311, 297, 323, 318, 306, 290, 272, 537, 534)

REGION = Box(10.0, 10.0, 20.0, 20.0)

# The figures of Kadesh excerpt pages 8 and 9 (book pages 16 and 17) when
# both are plates, as the tests with pages of their own make them: the
# whole page, at 300 dpi. The excerpt's config excludes page 8, the scan
# of a cover (the owner, 16 November 2026).
KADESH_PLATE_FIGURE = frozendict(
    {
        index: Figure(
            box=Box(0.0, 0.0, 508.32, 728.16),
            image=f"images/plate-{index:04d}.png",
            dpi=300,
            kind=FigureKind.PLATE,
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
        figure_boxes=(),
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


def test_front_matter_page_gives_a_front_matter_removal_per_word_and_no_words() -> None:
    # Front-matter spec, section 3: the words of a title page.
    front = page(PageKind.FRONT_MATTER, TextSource.NONE)
    words = (
        word("THE", Box(150.0, 200.0, 180.0, 216.0)),
        word("NORMANS", Box(185.0, 200.0, 260.0, 216.0)),
    )

    assert page_words(front, words) == (
        PageWords(index=4, text_source=TextSource.NONE, words=(), figures=()),
        tuple(
            Removal(
                page_index=4,
                box=layer_word.box,
                text=layer_word.text,
                reason=RemovalReason.FRONT_MATTER,
            )
            for layer_word in words
        ),
    )


def test_inkless_page_gives_an_inkless_removal_per_word_but_in_a_region() -> None:
    # Plates spec, section 2b: the words the OCR read in an endpaper's
    # pattern, in the layer's order; a word in an excluded region keeps
    # the reason excluded_region, as on any page.
    inkless = page(PageKind.INKLESS, TextSource.NONE, (REGION,))
    words = (
        word("SP", Box(150.0, 200.0, 170.0, 216.0)),
        word("fiyj.", Box(12.0, 12.0, 18.0, 18.0)),
        word("v", Box(185.0, 200.0, 195.0, 216.0)),
    )

    assert page_words(inkless, words) == (
        PageWords(index=4, text_source=TextSource.NONE, words=(), figures=()),
        tuple(
            Removal(
                page_index=4, box=layer_word.box, text=layer_word.text, reason=reason
            )
            for layer_word, reason in zip(
                words,
                (
                    RemovalReason.INKLESS_PAGE,
                    RemovalReason.EXCLUDED_REGION,
                    RemovalReason.INKLESS_PAGE,
                ),
                strict=True,
            )
        ),
    )


def test_blank_page_has_no_words_and_no_removals() -> None:
    assert page_words(page(PageKind.BLANK, TextSource.NONE), ()) == (
        PageWords(index=4, text_source=TextSource.NONE, words=(), figures=()),
        (),
    )


# A plate page (plates spec section 3)

PLATE_FIGURE = Figure(
    box=Box(0.0, 0.0, 400.0, 600.0),
    image="images/plate-0004.png",
    dpi=300,
    kind=FigureKind.PLATE,
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


def test_word_counts_per_page_are_those_of_the_text_layer_but_81_and_pages_8_9(
    excerpt_books: frozendict[str, BookFolder],
) -> None:
    kadesh = read_words(excerpt_books[KADESH].words_json)
    gierke = read_words(excerpt_books[GIERKE].words_json)

    # Page 8 is excluded; page 9 has no text layer.
    assert tuple(len(page_words.words) for page_words in kadesh.pages) == (
        581,
        *KADESH_WORD_COUNTS[1:8],
        0,
        0,
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
        (8, TextSource.NONE, ()),
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


def test_kadesh_removals_are_81_in_its_region_and_the_4_words_of_excluded_page_8(
    excerpt_books: frozendict[str, BookFolder],
) -> None:
    assert read_words(excerpt_books[KADESH].words_json).removals == KADESH_REMOVALS


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


# The pages of the excerpts that carry the two rules of extract spec
# sections 3 and 4, by page index in the excerpt: Domesday's pages 23, 24
# and 200 are domesday_front_flow's 7, 8 and 9; Gierke's 13 and 100 are
# gierke_front_flow's 8 and 9; Haskins' 12 is haskins_front's 5. With the
# default options of extract_words(), each piece below was a word of its
# page ("s ome", "i t", "W L i o n n c d h o e n s ter", "' T he", "to h im").
PIECES_OF_CUT_WORDS = (
    ("domesday_front_flow", 7, ("s", "ome")),
    ("domesday_front_flow", 8, ("i", "t")),
    ("domesday_front_flow", 9, ("W", "L", "ter")),
    ("gierke_front_flow", 8, ("T",)),
    ("gierke_front_flow", 9, ("h", "im")),
)


@pytest.mark.parametrize(
    ("excerpt", "page", "pieces"),
    PIECES_OF_CUT_WORDS,
    ids=[f"{excerpt}-{page}" for excerpt, page, _ in PIECES_OF_CUT_WORDS],
)
def test_words_of_a_page_in_the_pdfs_order_leave_no_piece_of_a_cut_word(
    excerpt_books: frozendict[str, BookFolder],
    excerpt: str,
    page: int,
    pieces: tuple[str, ...],
) -> None:
    words = read_words(excerpt_books[excerpt].words_json)
    texts = {word.text for word in words.pages[page].words}
    assert texts.isdisjoint(pieces)


# Haskins' page 12, the first page of the preface, as the page image reads:
# its text layer has no space character, and "of these", "as well", "the
# omission of many" and "This book rests partly upon the writings of the
# various" were glued words before the split of extract spec section 4. The
# words in order, one space between two.
HASKINS_12_WORDS = (
    "PREFACE THE eight lectures which are here published were delivered "
    "before the Lowell Institute in February, 1915, and at the University "
    "of Cali- fornia the following July, and it has seemed best to print "
    "them in the form in which they were prepared for a general audience. "
    "Their purpose is not so much to furnish an outline of the annals of "
    "Norman history as to place the Normans in relation to their time and "
    "to indicate the larger features of their work as founders and "
    "organizers of states and contributors to European culture. "
    "Biographical and narrative detail has accord- ingly been subordinated "
    "in the effort to give a general view of Norman achievement in France, "
    "in England, and in Italy. Various aspects of Norman history have been "
    "treated with considerable fullness by historians, but, so far as I am "
    "aware, no connected account of the whole subject has yet been "
    "attempted from this point of view. This fact, it is hoped, may justify "
    "the publication of these lectures, as well as explain the omission of "
    "many topics which would naturally be treated in an extended narrative. "
    "This book rests partly upon the writings of the various scholars "
    "enumerated in the bibliographical note at the"
)


def test_haskins_front_page_12_gives_its_words_exactly(
    excerpt_books: frozendict[str, BookFolder],
) -> None:
    words = read_words(excerpt_books["haskins_front"].words_json)
    # No word of the text layer holds a space, so the joined text compares
    # the words one by one.
    assert " ".join(word.text for word in words.pages[5].words) == HASKINS_12_WORDS


# The plates of the excerpts (plates spec section 6), by page index in the
# excerpt: Kadesh 17 (16, the scan of a cover, is excluded); Kadesh 64, 65
# (the back of plate 64) and 68;
# Domesday's maps 39 and 40; Kadesh 34 and 35, the back of plate 34.
# Each has its image, and nothing else is in
# images/ but the cover and the in-page figures' images.
EXCERPT_PLATES = frozendict(
    {
        "kadesh_8-17": (9,),
        "kadesh_59-68": (5, 6, 9),
        "domesday_headings_quotes": (3, 4),
        "kadesh_29-38": (5, 6),
    }
)
# The text pages with one in-page figure (figures spec section 10): Kadesh
# 29, 33, 36, 37 and 38. tests/test_figures.py checks them.
EXCERPT_IN_PAGE_FIGURES = frozendict({"kadesh_29-38": (0, 4, 7, 8, 9)})


def test_each_excerpt_plate_has_its_whole_page_figure_and_its_image_alone(
    excerpt_books: frozendict[str, BookFolder],
) -> None:
    for name, folder in excerpt_books.items():
        plates = EXCERPT_PLATES.get(name, ())
        in_page = EXCERPT_IN_PAGE_FIGURES.get(name, ())
        pages = read_pages(folder.pages_json).pages
        words = read_words(folder.words_json)
        assert tuple(
            page_words.index for page_words in words.pages if page_words.figures
        ) == tuple(sorted((*plates, *in_page))), name
        for index in plates:
            assert words.pages[index].figures == (
                Figure(
                    box=Box(0.0, 0.0, pages[index].width_pt, pages[index].height_pt),
                    image=f"images/plate-{index:04d}.png",
                    dpi=300,
                    kind=FigureKind.PLATE,
                ),
            ), name
            with Image.open(folder.root / words.pages[index].figures[0].image) as plate:
                assert (plate.format, plate.mode) == ("PNG", "L"), name
        cover = ("cover.png",) if name == KADESH else ()
        assert sorted(path.name for path in folder.images_dir.iterdir()) == sorted(
            (
                *cover,
                *(f"plate-{index:04d}.png" for index in plates),
                *(f"figure-{index:04d}-1.png" for index in in_page),
            )
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
# in the region of page 0, and the 4 words of page 8, the scan of a cover.
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


@pytest.fixture(scope="module")
def kadesh_with_two_pages_of_removals(
    tmp_path_factory: pytest.TempPathFactory, excerpt_pdf: frozendict[str, Path]
) -> frozendict[int, BookFolder]:
    """Kadesh folders with TWO_PAGES_OF_REMOVALS, by number of workers, 1 and
    6, through analyze and extract run with that many workers. Each held a
    file left by an earlier run in images/, which extract must delete.

    Module-scoped, so that the two tests below read one run of each.
    """
    folders = {}
    for workers in (1, 6):
        folder = kadesh_folder(
            tmp_path_factory.mktemp(f"removals_{workers}"),
            excerpt_pdf[KADESH],
            TWO_PAGES_OF_REMOVALS,
        )
        config = read_config(folder.book_toml)
        analyze.run(folder, config, workers=workers)
        folder.images_dir.mkdir()
        (folder.images_dir / "stale.png").write_bytes(b"not an image")
        extract.run(folder, config, workers=workers)
        folders[workers] = folder
    return frozendict(folders)


@pytest.mark.thread_unsafe
def test_kadesh_with_plate_page_excluded_has_81_and_its_4_words_as_the_removals(
    kadesh_with_two_pages_of_removals: frozendict[int, BookFolder],
) -> None:
    for workers, folder in kadesh_with_two_pages_of_removals.items():
        words = read_words(folder.words_json)
        assert words.pages[8] == PageWords(
            index=8, text_source=TextSource.NONE, words=(), figures=()
        ), workers
        assert words.removals == KADESH_REMOVALS, workers
        assert list(folder.images_dir.iterdir()) == [], workers


@pytest.mark.thread_unsafe
def test_kadesh_with_1_worker_and_with_6_gives_the_same_bytes(
    kadesh_with_two_pages_of_removals: frozendict[int, BookFolder],
) -> None:
    one, six = (kadesh_with_two_pages_of_removals[workers] for workers in (1, 6))

    assert one.pages_json.read_bytes() == six.pages_json.read_bytes()
    assert one.words_json.read_bytes() == six.words_json.read_bytes()


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
    page 9 a plate without one: page 8 as analyze's plate rule takes it when
    the config does not exclude it (it is the scan of a cover, the owner
    found on 16 November 2026), a page with a layer of stray words alone."""
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


@pytest.fixture(scope="module")
def kadesh_plates_8_and_9(
    tmp_path_factory: pytest.TempPathFactory,
    excerpt_pdf: frozendict[str, Path],
    excerpt_books: frozendict[str, BookFolder],
) -> frozendict[int, BookFolder]:
    """Kadesh folders with `cover_page = 0` and pages 8 and 9 plates, by
    number of workers, 1 and 6, through extract run with that many workers.

    Module-scoped, so that the two tests below read one run of each.
    """
    pages = _pages_with_plates_8_and_9(read_pages(excerpt_books[KADESH].pages_json))
    folders = {}
    for workers in (1, 6):
        folder = kadesh_folder(
            tmp_path_factory.mktemp(f"plates_{workers}"),
            excerpt_pdf[KADESH],
            "cover_page = 0\n",
        )
        write_pages(folder.pages_json, pages)
        extract.run(folder, read_config(folder.book_toml), workers=workers)
        folders[workers] = folder
    return frozendict(folders)


@pytest.mark.thread_unsafe
def test_kadesh_plates_8_and_9_get_their_images_and_figures_and_8_keeps_its_words(
    kadesh_plates_8_and_9: frozendict[int, BookFolder],
) -> None:
    folder = kadesh_plates_8_and_9[6]

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
                kind=FigureKind.PLATE,
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
                kind=FigureKind.PLATE,
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
    kadesh_plates_8_and_9: frozendict[int, BookFolder],
) -> None:
    one, six = (kadesh_plates_8_and_9[workers] for workers in (1, 6))

    assert one.words_json.read_bytes() == six.words_json.read_bytes()
    for name in ("cover.png", "plate-0008.png", "plate-0009.png"):
        assert (one.images_dir / name).read_bytes() == (
            six.images_dir / name
        ).read_bytes(), name


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


# The whole books (front-matter spec sections 4 and 6): the pages of each
# book that are front matter, by Internet Archive identifier, and the number
# of their words, each a front_matter removal.
WHOLE_BOOK_FRONT_MATTER_REMOVALS = frozendict(
    {
        "normansineuropea00hask": ((1, 2, 6, 8, 9, 10), 108),
        "earlyplantagenet01stub": ((1, 6, 7, 12, 13), 370),
        "domesdaybook00maituoft": ((4, 8, 9, 10, 11), 99),
        "politicaltheorie00gieruoft": ((1, 6, 7, 8, 9), 100),
        "battleofkadeshst00breauoft": ((4, 5, 6, 7), 91),
    }
)


# words.json comes from the session's run of the book (tests/conftest.py),
# which layout's whole_book tests share; the run re-reads with Tesseract.
@pytest.mark.whole_book
@pytest.mark.tesseract
@pytest.mark.thread_unsafe
@pytest.mark.timeout(900)
@pytest.mark.parametrize("book", sorted(WHOLE_BOOK_FRONT_MATTER_REMOVALS))
def test_front_matter_removals_of_each_whole_book_are_the_words_of_its_front_pages(
    book: str, whole_book_run: Callable[[str], BookFolder]
) -> None:
    words = read_words(whole_book_run(book).words_json)
    removals = tuple(
        removal
        for removal in words.removals
        if removal.reason is RemovalReason.FRONT_MATTER
    )
    front_matter, word_count = WHOLE_BOOK_FRONT_MATTER_REMOVALS[book]

    assert (
        tuple(sorted({removal.page_index for removal in removals})),
        len(removals),
    ) == (front_matter, word_count)
    assert all(not words.pages[index].words for index in front_matter)
