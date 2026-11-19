"""Tests of galley.extract (walking skeleton spec section 6, plates spec
section 3).

The unit tests of `page_words` build their pages and words by hand. The
excerpt tests read the folders of the session fixture `excerpt_books`; a
test that runs extract on a folder of its own is marked thread_unsafe, so
that the 8-thread run does it once.
"""

import logging
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
    ],
    ids=["blank_with_words", "plate_without_layer_with_words"],
)
def test_page_whose_words_would_be_lost_is_a_value_error(
    kind: PageKind, text_source: TextSource, layer_words: tuple[Word, ...]
) -> None:
    with pytest.raises(ValueError, match=r"^page 4 "):
        page_words(page(kind, text_source), layer_words)


# Pages read by Tesseract under ocr = "redo" (extract spec section 9)


def tesseract_word(text: str, box: Box, confidence: float) -> Word:
    return Word(text, box, confidence)


OCR_PAGE = page(PageKind.TEXT, TextSource.OCR, (REGION,))
MEGIDDO = tesseract_word("Megiddo,", Box(100.0, 50.0, 140.0, 60.0), 96.0)
LAYER_MEGIDDO = word("Me^iddo.", Box(100.0, 53.0, 140.0, 64.0))
PAGE_NUMBER = tesseract_word("81", Box(12.0, 12.0, 16.0, 16.0), 91.0)


def test_ocr_page_keeps_tesseracts_words_but_those_in_a_region() -> None:
    assert page_words(OCR_PAGE, (MEGIDDO, PAGE_NUMBER)) == (
        PageWords(index=4, text_source=TextSource.OCR, words=(MEGIDDO,), figures=()),
        (
            Removal(
                page_index=4,
                box=PAGE_NUMBER.box,
                text="81",
                reason=RemovalReason.EXCLUDED_REGION,
            ),
        ),
    )


def test_ocr_page_where_tesseract_reads_words_is_read_from_them() -> None:
    assert extract._words_read(OCR_PAGE, (MEGIDDO,), (LAYER_MEGIDDO,)) == (
        OCR_PAGE,
        (MEGIDDO,),
    )


def test_ocr_page_where_tesseract_reads_no_word_falls_back_to_the_layer() -> None:
    # Extract spec section 9: no printed word is lost; the page's source
    # becomes the layer, and its regions apply to the layer's words.
    page_read, words = extract._words_read(OCR_PAGE, (), (LAYER_MEGIDDO,))

    assert page_read == replace(OCR_PAGE, text_source=TextSource.TEXT_LAYER)
    assert words == (LAYER_MEGIDDO,)


def test_page_read_from_the_layer_keeps_the_layers_words() -> None:
    assert extract._words_read(TEXT_PAGE, (), (LAYER_MEGIDDO,)) == (
        TEXT_PAGE,
        (LAYER_MEGIDDO,),
    )


# Note references put back from the layer (extract spec section 9). The
# words and boxes are Kadesh's, read by Tesseract and by the layer on 19
# November 2026 (the page index of the whole book in each name).
KADESH_10_TESSERACT = tesseract_word(
    "Kadesh,\u201d", Box(250.56, 346.08, 292.32, 355.92), 81.66
)
KADESH_10_LAYER = word("Kadesh,12", Box(250.321, 349.911, 288.488, 360.911))
HIM_36_TESSERACT = tesseract_word("him,", Box(200.88, 187.2, 223.92, 195.84), 40.25)
HIM_36_LAYER = word("him,88", Box(200.838, 190.137, 221.722, 200.241))
GREECE_8_TESSERACT = tesseract_word(
    "Greece,\u2019", Box(275.76, 266.4, 312.0, 276.24), 21.86
)
GREECE_8_LAYER = word("Greece,1", Box(275.76, 270.122, 308.962, 281.122))
THOUSAND_8_TESSERACT = tesseract_word(
    "thousand", Box(279.6, 279.84, 320.64, 287.52), 96.25
)
# Page 13's "Mon., 17": Tesseract reads two words, the layer one, given
# twice with the same box.
MON_13_TESSERACT = tesseract_word("Mon..", Box(318.72, 526.08, 336.24, 531.12), 47.21)
SEVENTEEN_13_TESSERACT = tesseract_word(
    "17", Box(338.64, 526.08, 343.92, 530.88), 83.06
)
MON_13_LAYER = word("Jfem.,17", Box(318.438, 526.076, 341.191, 534.212))
RAMSES_31_TESSERACT = tesseract_word(
    "Ramses\u2019s", Box(141.6, 525.6, 182.16, 533.28), 62.66
)
RAMSES_31_LAYER = word("Ramses1", Box(141.6, 529.088, 170.595, 540.088))
CAMPE_62_TESSERACT = tesseract_word(
    "camp\u00e9", Box(52.56, 395.76, 78.96, 404.16), 92.36
)
CAMPE_62_LAYER = word("camp6", Box(52.56, 397.291, 74.415, 408.291))


@pytest.mark.parametrize(
    ("tesseract", "layer", "expected"),
    [
        (KADESH_10_TESSERACT, KADESH_10_LAYER, "Kadesh,12"),
        (HIM_36_TESSERACT, HIM_36_LAYER, "him,88"),
        (GREECE_8_TESSERACT, GREECE_8_LAYER, "Greece,1"),
    ],
    ids=["mark_for_the_digits", "digits_dropped", "quote_for_the_digit"],
)
def test_tesseract_word_takes_the_layers_reference_where_it_read_none(
    tesseract: Word, layer: Word, expected: str
) -> None:
    assert extract.with_layer_references(
        (THOUSAND_8_TESSERACT, tesseract), (layer,)
    ) == (THOUSAND_8_TESSERACT, replace(tesseract, text=expected))


@pytest.mark.parametrize(
    ("tesseract_words", "layer_words"),
    [
        ((MON_13_TESSERACT, SEVENTEEN_13_TESSERACT), (MON_13_LAYER,)),
        ((MON_13_TESSERACT, SEVENTEEN_13_TESSERACT), (MON_13_LAYER, MON_13_LAYER)),
        ((RAMSES_31_TESSERACT,), (RAMSES_31_LAYER,)),
        ((CAMPE_62_TESSERACT,), (CAMPE_62_LAYER,)),
        ((KADESH_10_TESSERACT,), (GREECE_8_LAYER,)),
        ((replace(KADESH_10_TESSERACT, text="Kadesh,12"),), (KADESH_10_LAYER,)),
    ],
    ids=[
        "layer_word_over_two",
        "layer_word_given_twice",
        "more_letters_than_the_layer",
        "layer_digit_for_a_letter",
        "no_layer_word_over_it",
        "tesseract_read_the_digits",
    ],
)
def test_tesseract_word_keeps_its_text_where_the_rule_does_not_hold(
    tesseract_words: tuple[Word, ...], layer_words: tuple[Word, ...]
) -> None:
    assert extract.with_layer_references(tesseract_words, layer_words) == (
        tesseract_words
    )


def test_word_boxes_of_the_same_word_are_over_each_other() -> None:
    assert extract.are_over_each_other(GREECE_8_TESSERACT.box, GREECE_8_LAYER.box)


def test_word_box_of_the_layer_is_not_over_the_line_below() -> None:
    # The layer's box sits 4 pt lower than Tesseract's and touches the
    # line below, but by less than half the lower height.
    assert not extract.are_over_each_other(THOUSAND_8_TESSERACT.box, GREECE_8_LAYER.box)


def test_ocr_page_takes_the_layers_references_into_tesseracts_words() -> None:
    assert extract._words_read(OCR_PAGE, (HIM_36_TESSERACT,), (HIM_36_LAYER,)) == (
        OCR_PAGE,
        (replace(HIM_36_TESSERACT, text="him,88"),),
    )


# Layer words Tesseract missed (extract spec section 9). Kadesh's page 11:
# Tesseract skipped the line "with the accession of new material made the
# compilation" between "been great ... de Rougé's day" and "of a new
# composite text". The pairs "been" and "text" give the page's offset,
# 4.0 and 1.4 pt, median 2.7.
BEEN_11_TESSERACT = tesseract_word("been", Box(268.3, 575.3, 283.9, 583.7), 95.9)
ROUGES_11_TESSERACT = tesseract_word(
    "Roug\u00e9's", Box(342.5, 575.3, 366.7, 583.7), 31.0
)
OF_11_TESSERACT = tesseract_word("of", Box(268.1, 591.1, 275.5, 599.5), 96.4)
COMPOSITE_11_TESSERACT = tesseract_word(
    "composite", Box(297.6, 592.8, 384.5, 598.6), 53.0
)
TEXT_11_TESSERACT = tesseract_word("text", Box(333.1, 591.1, 345.8, 599.5), 87.7)
BEEN_11_LAYER = word("been", Box(269.0, 580.0, 281.7, 587.0))
ROUGES_11_LAYER = word("Rouce's", Box(341.5, 580.0, 363.9, 587.0))
WITH_11_LAYER = word("with", Box(269.3, 585.6, 281.0, 592.6))
MATERIAL_11_LAYER = word("material", Box(359.5, 585.6, 384.1, 592.6))
OF_11_LAYER = word("of", Box(268.8, 593.2, 273.8, 600.2))
COMPOSITE_11_LAYER = word("oosaposite", Box(297.4, 593.2, 327.3, 600.2))
TEXT_11_LAYER = word("text", Box(332.6, 593.2, 343.2, 600.2))
PAGE_11_OFFSET = 2.7


def moved_up(layer_word: Word, offset: float) -> Word:
    box = layer_word.box
    return replace(
        layer_word, box=Box(box.x0, box.top - offset, box.x1, box.bottom - offset)
    )


def test_layer_line_tesseract_skipped_is_kept_moved_by_the_offset() -> None:
    kept = extract.with_missed_layer_words(
        (
            BEEN_11_TESSERACT,
            ROUGES_11_TESSERACT,
            OF_11_TESSERACT,
            COMPOSITE_11_TESSERACT,
            TEXT_11_TESSERACT,
        ),
        (
            BEEN_11_LAYER,
            ROUGES_11_LAYER,
            WITH_11_LAYER,
            MATERIAL_11_LAYER,
            OF_11_LAYER,
            COMPOSITE_11_LAYER,
            TEXT_11_LAYER,
        ),
    )
    assert [word.text for word in kept] == [
        "been",
        "Roug\u00e9's",
        "with",
        "material",
        "of",
        "composite",
        "text",
    ]
    assert kept[2].ocr_confidence is None
    assert kept[2].box == pytest.approx(moved_up(WITH_11_LAYER, PAGE_11_OFFSET).box)
    assert kept[3].box == pytest.approx(moved_up(MATERIAL_11_LAYER, PAGE_11_OFFSET).box)


# Kadesh's page 12: the layer boxes its line up to 25 pt right of
# Tesseract's, so that its "of" lies beside Tesseract's "of", which covers
# no layer "of" (unclaimed); the pair "the" gives the offset.
SIONS_12_TESSERACT = tesseract_word("sions", Box(67.4, 339.4, 89.5, 347.0), 96.3)
OF_12_TESSERACT = tesseract_word("of", Box(91.9, 339.4, 100.6, 347.0), 96.6)
THE_12_TESSERACT = tesseract_word("the", Box(104.4, 339.4, 118.3, 347.0), 96.3)
SIONS_12_LAYER = word("sions", Box(91.9, 340.1, 99.2, 351.1))
OF_12_LAYER = word("of", Box(100.7, 340.1, 103.6, 351.1))
THE_12_LAYER = word("the", Box(104.4, 340.1, 116.1, 351.1))


def test_layer_copy_of_a_word_tesseract_read_beside_it_is_not_kept() -> None:
    tesseract_words = (SIONS_12_TESSERACT, OF_12_TESSERACT, THE_12_TESSERACT)
    assert (
        extract.with_missed_layer_words(
            tesseract_words, (SIONS_12_LAYER, OF_12_LAYER, THE_12_LAYER)
        )
        == tesseract_words
    )


def test_layer_word_without_a_letter_or_digit_is_not_kept() -> None:
    # Kadesh page 8's "=", which Tesseract does not read.
    assert extract.with_missed_layer_words(
        (BEEN_11_TESSERACT,), (word("=", Box(216.7, 619.5, 219.5, 626.5)),)
    ) == (BEEN_11_TESSERACT,)


def test_layer_word_of_a_page_without_pairs_is_kept_where_the_layer_boxes_it() -> None:
    # Kadesh page 10's page number "83", which Tesseract does not read; no
    # word of the two readings pairs, so the offset is 0.
    page_number = word("83", Box(267.8, 645.2, 275.5, 655.2))
    assert extract.with_missed_layer_words((BEEN_11_TESSERACT,), (page_number,)) == (
        BEEN_11_TESSERACT,
        page_number,
    )


def test_ocr_page_keeps_the_layer_words_tesseract_missed() -> None:
    # The reference put back first makes "him,88" a pair of the two
    # readings, which gives the offset.
    _, words = extract._words_read(
        OCR_PAGE, (HIM_36_TESSERACT,), (HIM_36_LAYER, WITH_11_LAYER)
    )
    offset = (HIM_36_LAYER.box.top + HIM_36_LAYER.box.bottom) / 2 - (
        HIM_36_TESSERACT.box.top + HIM_36_TESSERACT.box.bottom
    ) / 2
    assert [word.text for word in words] == ["him,88", "with"]
    assert words[1].box == pytest.approx(moved_up(WITH_11_LAYER, offset).box)


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


@pytest.mark.tesseract
@pytest.mark.thread_unsafe
@pytest.mark.usefixtures("tesseract_of_the_literals")
def test_ocr_pages_are_read_by_tesseract_alike_with_1_worker_and_with_6(
    tmp_path: Path,
    excerpt_pdf: frozendict[str, Path],
    excerpt_books: frozendict[str, BookFolder],
) -> None:
    # Extract spec section 9: Kadesh's excerpt pages 0 and 1 (book pages 8
    # and 9) marked `ocr`, as analyze marks them under ocr = "redo"; page
    # 1's layer reads "Me^iddo. already in tli.- sixti-fiith century".
    # Page 0's region is moved to the page number 81 where it is printed
    # and Tesseract reads it, 634.8 to 641.8 pt from the top; the layer
    # puts it at 622.5 to 629.5.
    pages = read_pages(excerpt_books[KADESH].pages_json)
    pages = replace(
        pages,
        pages=(
            replace(
                pages.pages[0],
                text_source=TextSource.OCR,
                exclude_regions=(Box(240.0, 632.0, 252.0, 644.0),),
            ),
            replace(pages.pages[1], text_source=TextSource.OCR),
            *pages.pages[2:],
        ),
    )
    folders = []
    for workers in (1, 6):
        folder = kadesh_folder(
            tmp_path / str(workers), excerpt_pdf[KADESH], TWO_PAGES_OF_REMOVALS
        )
        write_pages(folder.pages_json, pages)
        extract.run(folder, read_config(folder.book_toml), workers=workers)
        folders.append(folder)

    one, six = folders
    assert one.words_json.read_bytes() == six.words_json.read_bytes()
    words = read_words(one.words_json)
    texts = tuple(word.text for word in words.pages[1].words)
    assert [page.text_source for page in words.pages[:3]] == [
        TextSource.OCR,
        TextSource.OCR,
        TextSource.TEXT_LAYER,
    ]
    assert "Me^iddo." not in texts
    assert any(
        texts[start : start + 8]
        == ("At", "Megiddo,", "already", "in", "the", "sixteenth", "century", "before")
        for start in range(len(texts))
    )
    # The words of page 1 without a confidence are the layer's words of the
    # line Tesseract skipped, the first of note 8, "CHABAS was conscious of
    # the thoroughness of his", and "FRANÇOIS" two lines below.
    assert [
        word.text for word in words.pages[1].words if word.ocr_confidence is None
    ] == [
        ">C||ABA*",
        "wu",
        "eocueiou*",
        "of",
        "the",
        "thoroughness",
        "of",
        "his",
        "FftAigou",
    ]
    assert all(word.ocr_confidence is None for word in words.pages[2].words)
    # The page number 81 in page 0's region, as Tesseract reads it.
    assert [
        (removal.text, removal.reason)
        for removal in words.removals
        if removal.page_index == 0
    ] == [("81", RemovalReason.EXCLUDED_REGION)]


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


@pytest.mark.thread_unsafe
def test_ocr_page_where_tesseract_finds_no_word_keeps_the_layers_words_and_warns(
    tmp_path: Path,
    excerpt_pdf: frozendict[str, Path],
    excerpt_books: frozendict[str, BookFolder],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Extract spec section 9: Kadesh's page 9 (the excerpt's page 1) marked
    # `ocr`, with a Tesseract that reads no word on it.
    pages = read_pages(excerpt_books[KADESH].pages_json)
    pages = replace(
        pages,
        pages=(
            pages.pages[0],
            replace(pages.pages[1], text_source=TextSource.OCR),
            *pages.pages[2:],
        ),
    )
    folder = kadesh_folder(tmp_path, excerpt_pdf[KADESH], TWO_PAGES_OF_REMOVALS)
    write_pages(folder.pages_json, pages)
    monkeypatch.setattr(extract.ocr, "read_image", lambda *_, **__: ())

    with caplog.at_level(logging.WARNING, logger="galley.extract"):
        extract.run(folder, read_config(folder.book_toml), workers=1)

    page = read_words(folder.words_json).pages[1]
    layer_page = read_words(excerpt_books[KADESH].words_json).pages[1]
    assert page.text_source is TextSource.TEXT_LAYER
    assert page.words == layer_page.words
    assert "Me^iddo." in [word.text for word in page.words]
    assert [record.getMessage() for record in caplog.records] == [
        (
            "extract: page index 1: Tesseract found no word on it; it keeps "
            f"the {len(layer_page.words)} words of its text layer"
        )
    ]
