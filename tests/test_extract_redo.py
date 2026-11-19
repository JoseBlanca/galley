"""Unit tests of the words of a page read by Tesseract under `ocr = "redo"`
(docs/specs/extract.md, section 9): the note references and caption
numbers put back from the layer, the layer words Tesseract missed, and the
heights from the layer. The words and boxes are Kadesh's
(battleofkadeshst00breauoft), read by Tesseract and by the layer on 19
November 2026; the page index of the whole book is in each name. A few
words are moved or copied to reach a limit; the comment says so."""

from dataclasses import replace

import pytest

from galley.extract import (
    are_over_each_other,
    layer_offset,
    ocr_page_words,
    with_caption_numbers,
    with_layer_heights,
    with_layer_references,
    with_missed_layer_words,
)
from galley.model import Box, Word


def layer(text: str, x0: float, top: float, x1: float, bottom: float) -> Word:
    return Word(text, Box(x0, top, x1, bottom), None)


def tesseract(
    text: str, x0: float, top: float, x1: float, bottom: float, confidence: float
) -> Word:
    return Word(text, Box(x0, top, x1, bottom), confidence)


def moved_up(word: Word, offset: float) -> Word:
    box = word.box
    return replace(word, box=Box(box.x0, box.top - offset, box.x1, box.bottom - offset))


def middle(word: Word) -> float:
    return (word.box.top + word.box.bottom) / 2


# Note references put back from the layer.
KADESH_10 = tesseract("Kadesh,”", 250.56, 346.08, 292.32, 355.92, 81.66)
KADESH_10_LAYER = layer("Kadesh,12", 250.321, 349.911, 288.488, 360.911)
HIM_36 = tesseract("him,", 200.88, 187.2, 223.92, 195.84, 40.25)
HIM_36_LAYER = layer("him,88", 200.838, 190.137, 221.722, 200.241)
GREECE_8 = tesseract("Greece,’", 275.76, 266.4, 312.0, 276.24, 21.86)
GREECE_8_LAYER = layer("Greece,1", 275.76, 270.122, 308.962, 281.122)
THOUSAND_8 = tesseract("thousand", 279.6, 279.84, 320.64, 287.52, 96.25)
HIGELS_26 = tesseract("Higels.”", 300.0, 400.0, 336.0, 408.0, 90.0)
HIGELS_26_LAYER = layer("Hugels.80", 300.0, 401.0, 333.0, 411.0)
FIND_13 = tesseract("find", 200.0, 300.0, 216.0, 308.0, 95.0)
FIND_13_LAYER = layer("flui1", 200.0, 301.0, 215.0, 311.0)
MON_13 = tesseract("Mon..", 318.72, 526.08, 336.24, 531.12, 47.21)
SEVENTEEN_13 = tesseract("17", 338.64, 526.08, 343.92, 530.88, 83.06)
MON_13_LAYER = layer("Jfem.,17", 318.438, 526.076, 341.191, 534.212)
RAMSES_31 = tesseract("Ramses’s", 141.6, 525.6, 182.16, 533.28, 62.66)
RAMSES_31_LAYER = layer("Ramses1", 141.6, 529.088, 170.595, 540.088)
CAMPE_62 = tesseract("campé", 52.56, 395.76, 78.96, 404.16, 92.36)
CAMPE_62_LAYER = layer("camp6", 52.56, 397.291, 74.415, 408.291)


@pytest.mark.parametrize(
    ("ocr_word", "layer_word", "expected"),
    [
        (KADESH_10, KADESH_10_LAYER, "Kadesh,12"),
        (HIM_36, HIM_36_LAYER, "him,88"),
        (GREECE_8, GREECE_8_LAYER, "Greece,1"),
        (HIGELS_26, HIGELS_26_LAYER, "Higels.80"),
    ],
    ids=["mark_for_the_digits", "digits_dropped", "quote", "one_letter_differs"],
)
def test_tesseract_word_takes_the_layers_reference_where_it_read_none(
    ocr_word: Word, layer_word: Word, expected: str
) -> None:
    assert with_layer_references((THOUSAND_8, ocr_word), (layer_word,)) == (
        THOUSAND_8,
        replace(ocr_word, text=expected),
    )


@pytest.mark.parametrize(
    ("ocr_words", "layer_words"),
    [
        ((MON_13, SEVENTEEN_13), (MON_13_LAYER,)),
        ((MON_13, SEVENTEEN_13), (MON_13_LAYER, MON_13_LAYER)),
        ((RAMSES_31,), (RAMSES_31_LAYER,)),
        ((CAMPE_62,), (CAMPE_62_LAYER,)),
        ((KADESH_10,), (GREECE_8_LAYER,)),
        ((replace(KADESH_10, text="Kadesh,7”"),), (KADESH_10_LAYER,)),
        # Page 13: "find" under the layer's "flui1"; the page prints no
        # reference there (the boxes moved to round values).
        ((FIND_13,), (FIND_13_LAYER,)),
        # Two Tesseract words over the one layer word: page 10's word given
        # twice.
        ((KADESH_10, KADESH_10), (KADESH_10_LAYER,)),
        # Page 8's "Greece," and the layer's box 1.6 pt lower than it is,
        # over it by less than half its height (4.3 of 9.8 pt).
        ((GREECE_8,), (moved_up(GREECE_8_LAYER, -1.6),)),
    ],
    ids=[
        "layer_word_over_two",
        "layer_word_given_twice",
        "more_letters_than_the_layer",
        "layer_digit_for_a_letter",
        "no_layer_word_over_it",
        "tesseract_read_a_digit",
        "letters_differ_in_three_places",
        "tesseract_word_given_twice",
        "over_by_less_than_half",
    ],
)
def test_tesseract_word_keeps_its_text_where_the_reference_rule_does_not_hold(
    ocr_words: tuple[Word, ...], layer_words: tuple[Word, ...]
) -> None:
    assert with_layer_references(ocr_words, layer_words) == ocr_words


def test_word_boxes_of_the_same_word_are_over_each_other() -> None:
    assert are_over_each_other(GREECE_8.box, GREECE_8_LAYER.box)


def test_word_box_of_the_layer_is_not_over_the_line_below() -> None:
    # The layer's box sits 4 pt lower than Tesseract's and touches the
    # line below, but by less than half the lower height.
    assert not are_over_each_other(THOUSAND_8.box, GREECE_8_LAYER.box)


# Caption numbers from the layer: page 36 prints "MAP V. Second Positions",
# page 38 "MAP VI.".
MAP_36 = tesseract("MAP", 71.28, 632.64, 87.12, 637.92, 92.2)
V_36 = tesseract("Y.", 90.0, 632.64, 96.72, 638.4, 70.8)
SECOND_36 = tesseract("Second", 103.0, 629.4, 127.0, 636.4, 96.2)
MAP_36_LAYER = layer("MAP", 71.52, 631.478, 83.23, 638.478)
V_36_LAYER = layer("V.", 90.24, 631.478, 94.757, 638.478)


@pytest.mark.parametrize(
    ("number", "layer_number", "expected"),
    [("Y.", "V.", "V."), ("ILL.", "111.", "111."), ("VIIL", "VIII.", "VIII.")],
    ids=["no_numeral", "ill_formed", "ill_formed_roman"],
)
def test_number_after_a_caption_word_takes_the_layers_numeral(
    number: str, layer_number: str, expected: str
) -> None:
    ocr_words = (MAP_36, replace(V_36, text=number), SECOND_36)
    assert with_caption_numbers(
        ocr_words, (MAP_36_LAYER, replace(V_36_LAYER, text=layer_number))
    ) == (MAP_36, replace(V_36, text=expected), SECOND_36)


@pytest.mark.parametrize(
    ("caption_word", "number", "layer_number"),
    [
        ("(Map", "Y.", "V."),
        ("MAP", "Y.", "Second"),
        ("Maple", "Y.", "V."),
        # Page 62's "Plate 30:", where the layer reads "30" and ":".
        ("Plate", "30:", "30"),
        # Page 38: Tesseract's "VI." is the printed numeral, the layer's
        # "vi." is not.
        ("MAP", "VI.", "vi."),
    ],
    ids=[
        "bracketed",
        "layer_word_no_numeral",
        "no_caption_word",
        "digits_read",
        "well_formed",
    ],
)
def test_number_after_a_caption_word_stays_where_the_rule_does_not_hold(
    caption_word: str, number: str, layer_number: str
) -> None:
    ocr_words = (replace(MAP_36, text=caption_word), replace(V_36, text=number))
    assert (
        with_caption_numbers(
            ocr_words, (MAP_36_LAYER, replace(V_36_LAYER, text=layer_number))
        )
        == ocr_words
    )


def test_number_on_another_line_than_the_caption_word_stays() -> None:
    # "Y." moved 10 pt down, off the line of "MAP".
    lower = moved_up(V_36, -10.0)
    ocr_words = (MAP_36, lower)
    assert with_caption_numbers(ocr_words, (moved_up(V_36_LAYER, -10.0),)) == (
        ocr_words
    )


# The page's offset and the layer words Tesseract missed. Page 11:
# Tesseract skipped the line "with the accession of new material made the
# compilation" between "been great ... de Rougé's day" and "of a new
# composite text". The pairs "been" and "text" give the page's offset, 4.0
# and 1.4 pt, median 2.7.
BEEN_11 = tesseract("been", 268.3, 575.3, 283.9, 583.7, 95.9)
ROUGES_11 = tesseract("Rougé's", 342.5, 575.3, 366.7, 583.7, 31.0)
OF_11 = tesseract("of", 268.1, 591.1, 275.5, 599.5, 96.4)
COMPOSITE_11 = tesseract("composite", 297.6, 592.8, 384.5, 598.6, 53.0)
TEXT_11 = tesseract("text", 333.1, 591.1, 345.8, 599.5, 87.7)
# The "the" of the line below, which no layer "the" pairs with.
THE_BELOW_11 = tesseract("the", 407.0, 599.5, 416.6, 607.7, 93.3)
BEEN_11_LAYER = layer("been", 269.0, 580.0, 281.7, 587.0)
ROUGES_11_LAYER = layer("Rouce's", 341.5, 580.0, 363.9, 587.0)
OF_11_LAYER = layer("of", 268.8, 593.2, 273.8, 600.2)
COMPOSITE_11_LAYER = layer("oosaposite", 297.4, 593.2, 327.3, 600.2)
TEXT_11_LAYER = layer("text", 332.6, 593.2, 343.2, 600.2)
SKIPPED_LINE_11_LAYER = tuple(
    layer(text, x0, 585.6, x1, 592.6)
    for text, x0, x1 in (
        ("with", 269.3, 281.0),
        ("the", 286.1, 295.4),
        ("ieeeeslon", 300.7, 329.0),
        ("of", 334.8, 340.4),
        ("new", 344.6, 353.9),
        ("material", 359.5, 384.1),
        ("made", 389.8, 403.4),
        ("the", 409.4, 417.6),
        ("compilation", 421.7, 458.2),
    )
)
PAGE_11_TESSERACT = (BEEN_11, ROUGES_11, OF_11, COMPOSITE_11, TEXT_11, THE_BELOW_11)
PAGE_11_LAYER = (
    BEEN_11_LAYER,
    ROUGES_11_LAYER,
    *SKIPPED_LINE_11_LAYER,
    OF_11_LAYER,
    COMPOSITE_11_LAYER,
    TEXT_11_LAYER,
)
PAGE_11_OFFSET = 2.7


def test_page_offset_is_the_median_of_the_pairs_of_the_same_word() -> None:
    assert layer_offset(PAGE_11_TESSERACT, PAGE_11_LAYER) == pytest.approx(
        PAGE_11_OFFSET
    )


def test_page_offset_leaves_out_a_pair_12_pt_apart_and_the_kept_words() -> None:
    # "text" of the layer moved 10 pt down: its middle is 11.4 pt from
    # Tesseract's, still a pair; 13 pt down, 14.4 pt, no longer one. A word
    # without a confidence is never one of a pair.
    near = layer_offset((TEXT_11,), (moved_up(TEXT_11_LAYER, -10.0),))
    far = layer_offset(
        (TEXT_11, BEEN_11), (moved_up(TEXT_11_LAYER, -13.0), BEEN_11_LAYER)
    )
    kept = layer_offset((replace(BEEN_11, ocr_confidence=None),), (BEEN_11_LAYER,))
    assert (near, far, kept) == pytest.approx((11.4, 4.0, 0.0))


def test_layer_line_tesseract_skipped_is_kept_whole_moved_by_the_offset() -> None:
    words = with_missed_layer_words(
        PAGE_11_TESSERACT, PAGE_11_LAYER, offset=PAGE_11_OFFSET
    )
    assert [word.text for word in words] == [
        "been",
        "Rougé's",
        "with",
        "the",
        "ieeeeslon",
        "of",
        "new",
        "material",
        "made",
        "the",
        "compilation",
        "of",
        "composite",
        "text",
        "the",
    ]
    kept = words[2:11]
    assert all(word.ocr_confidence is None for word in kept)
    assert [word.box.top for word in kept] == pytest.approx([585.6 - 2.7] * 9)


def test_layer_word_covered_by_a_third_of_its_height_is_not_kept() -> None:
    # The cover test's height share is a quarter of the lower height, not
    # half: "with" 2.4 pt (a third of 7 pt) inside "been".
    with_word = moved_up(SKIPPED_LINE_11_LAYER[0], 585.6 - (583.7 - 2.4))
    assert "with" not in [
        word.text
        for word in with_missed_layer_words(
            (BEEN_11,), (with_word, *SKIPPED_LINE_11_LAYER[1:3]), offset=0.0
        )
    ]


def test_cover_test_takes_the_lower_height_not_the_taller() -> None:
    # A Tesseract word 20 pt tall over "with" by 4 pt: a quarter of the
    # lower height (7 pt) but not of the taller (20 pt).
    tall = tesseract("been", 268.3, 569.6, 283.9, 589.6, 95.9)
    words = with_missed_layer_words(
        (tall,), (SKIPPED_LINE_11_LAYER[0], *SKIPPED_LINE_11_LAYER[2:4]), offset=0.0
    )
    assert "with" not in [word.text for word in words]


# Page 12: the layer boxes its line up to 25 pt right of Tesseract's, so
# that its "of" lies beside Tesseract's "of", which covers no layer "of"
# (unclaimed).
SIONS_12 = tesseract("sions", 67.4, 339.4, 89.5, 347.0, 96.3)
OF_12 = tesseract("of", 91.9, 339.4, 100.6, 347.0, 96.6)
THE_12 = tesseract("the", 104.4, 339.4, 118.3, 347.0, 96.3)
SIONS_12_LAYER = layer("sions", 91.9, 340.1, 99.2, 351.1)
OF_12_LAYER = layer("of", 100.7, 340.1, 103.6, 351.1)
THE_12_LAYER = layer("the", 104.4, 340.1, 116.1, 351.1)


def test_layer_copy_of_a_word_tesseract_read_beside_it_is_not_kept() -> None:
    ocr_words = (SIONS_12, OF_12, THE_12)
    assert (
        with_missed_layer_words(
            ocr_words, (SIONS_12_LAYER, OF_12_LAYER, THE_12_LAYER), offset=2.4
        )
        == ocr_words
    )


def test_layer_word_of_a_skipped_line_is_no_copy_of_a_word_one_line_below() -> None:
    # Finding of the review of work package 3: page 11's second "the" was
    # taken for a copy of the "the" of the line below, 9.6 pt lower.
    words = with_missed_layer_words(
        PAGE_11_TESSERACT, PAGE_11_LAYER, offset=PAGE_11_OFFSET
    )
    assert [word.text for word in words].count("the") == 3


def test_layer_word_of_a_skipped_line_is_a_copy_up_to_16_pt_across() -> None:
    # A Tesseract "compilation" on the line, copied 15 pt and 17 pt right
    # of the layer's: a copy at 15, not at 17.
    def kept_with(gap: float) -> bool:
        copy = tesseract("compilation", 458.2 + gap, 582.9, 494.7 + gap, 589.9, 90.0)
        words = with_missed_layer_words(
            (*PAGE_11_TESSERACT, copy), PAGE_11_LAYER, offset=PAGE_11_OFFSET
        )
        return [word.text for word in words].count("compilation") == 2

    assert (kept_with(15.0), kept_with(17.0)) == (False, True)


# Page 41: the layer's "behind", alone on its row, 9 pt below Tesseract's
# 'behind"', which it copies; page 9's "FftAigou" ("FRANÇOIS"), alone on
# its row, a word Tesseract missed.
BEHIND_41 = tesseract('behind"', 219.36, 629.28, 246.24, 634.32, 79.0)
BEHIND_41_LAYER = layer("behind", 219.36, 643.436, 237.4, 651.436)
FRANCOIS_9_LAYER = layer("FftAigou", 237.8, 572.9, 273.2, 579.9)


@pytest.mark.parametrize(
    ("layer_word", "kept"),
    [
        (FRANCOIS_9_LAYER, True),
        (BEHIND_41_LAYER, False),
        # Page 55's "US", page 44's "inn", page 33's "•J4", page 38's
        # "AA/^AA^" and page 10's page number "83", each alone on its row.
        (layer("US", 273.0, 677.0, 285.0, 685.0), False),
        (layer("inn", 323.0, 331.0, 335.0, 339.0), False),
        (layer("•J4", 74.0, 61.0, 86.0, 69.0), False),
        (layer("AA/^AA^", 488.0, 432.0, 520.0, 440.0), False),
        (layer("83", 267.8, 645.2, 275.5, 655.2), False),
        # A word without a letter or a digit, page 8's "=".
        (layer("=", 216.7, 619.5, 219.5, 626.5), False),
    ],
    ids=[
        "printed_word",
        "copy_below",
        "us",
        "inn",
        "j4",
        "hieroglyph_junk",
        "page_number",
        "sign",
    ],
)
def test_layer_word_alone_on_its_row_is_kept_only_when_a_long_word(
    layer_word: Word, kept: bool
) -> None:
    words = with_missed_layer_words((BEHIND_41,), (layer_word,), offset=0.0)
    assert (layer_word in words) is kept


def test_ocr_page_keeps_no_layer_word_that_touches_an_in_page_figure() -> None:
    # Page 52: "UJ", the layer's junk under the hieroglyphs, whose box (70,
    # 442, 408, 544) its own reaches into; the line of page 11 elsewhere.
    junk = layer("UJ", 164.88, 542.4, 179.41, 555.4)
    read = ocr_page_words(
        PAGE_11_TESSERACT, (*PAGE_11_LAYER, junk), (Box(70.0, 442.0, 408.0, 544.0),)
    )
    assert "UJ" not in [word.text for word in read.words]


def test_ocr_page_words_say_what_the_layer_gave() -> None:
    read = ocr_page_words(
        (HIM_36, *PAGE_11_TESSERACT), (HIM_36_LAYER, *PAGE_11_LAYER), ()
    )
    assert read.taken == ((HIM_36, "him,88"),)
    assert [word.text for word in read.kept] == [
        word.text for word in SKIPPED_LINE_11_LAYER
    ]


# Word heights from the layer: each word keeps its middle and takes the
# layer word's height, 7.0 pt on page 11.
def test_tesseract_word_takes_the_height_of_the_layer_word_over_it() -> None:
    words = (BEEN_11, OF_11, COMPOSITE_11, TEXT_11)
    heights = with_layer_heights(words, PAGE_11_LAYER, offset=PAGE_11_OFFSET)
    assert [word.text for word in heights] == [word.text for word in words]
    assert [(word.box.x0, word.box.x1) for word in heights] == [
        (word.box.x0, word.box.x1) for word in words
    ]
    assert [
        edge for word in heights for edge in (word.box.top, word.box.bottom)
    ] == pytest.approx(
        [edge for word in words for edge in (middle(word) - 3.5, middle(word) + 3.5)]
    )


def test_word_no_layer_word_covers_and_a_kept_layer_word_keep_their_boxes() -> None:
    kept = moved_up(SKIPPED_LINE_11_LAYER[5], PAGE_11_OFFSET)
    words = (ROUGES_11, kept)
    assert (
        with_layer_heights(
            words, (OF_11_LAYER, SKIPPED_LINE_11_LAYER[5]), offset=PAGE_11_OFFSET
        )
        == words
    )


def test_height_comes_from_a_layer_word_only_where_it_covers_after_the_offset() -> None:
    # "of" of page 11 under the layer's "of" moved 6 pt lower: covered (by
    # 3.0 pt of 7) once the offset of 2.7 pt moves it up, not without it
    # (0.3 pt).
    lower = moved_up(OF_11_LAYER, -6.0)
    with_offset = with_layer_heights((OF_11,), (lower,), offset=2.7)
    without = with_layer_heights((OF_11,), (lower,), offset=0.0)
    assert with_offset[0].box.bottom - with_offset[0].box.top == pytest.approx(7.0)
    assert without == (OF_11,)


# Page 44: the line "The then proceeds with the" runs over the layer's
# junk of a row of hieroglyphs, "v-ik-Mru^i—", 34.5 pt tall, which covers
# its words too; ten words of the page's text set its 90th percentile of
# heights at 11 pt.
THEN_44 = tesseract("then", 201.12, 299.04, 220.8, 306.96, 96.3)
PROCEEDS_44 = tesseract("proceeds", 224.64, 299.04, 263.52, 309.6, 96.3)
THEN_44_LAYER = layer("then", 201.12, 302.698, 217.615, 313.698)
PROCEEDS_44_LAYER = layer("proceeds", 224.64, 302.698, 260.031, 313.698)
JUNK_44_LAYER = layer("v-ik-Mru^i—", 191.477, 302.092, 319.221, 336.634)
TEXT_44_LAYER = tuple(
    layer("word", 60.0 + 30.0 * number, 100.0, 80.0 + 30.0 * number, 111.0)
    for number in range(10)
)


def test_tall_junk_box_of_the_layer_gives_no_height_and_lines_stay_apart() -> None:
    # "procceds", Tesseract's word with its letters changed so that no
    # layer word has them, takes the height of "proceeds", not the junk's.
    misread = replace(PROCEEDS_44, text="procceds")
    heights = with_layer_heights(
        (THEN_44, misread),
        (THEN_44_LAYER, PROCEEDS_44_LAYER, JUNK_44_LAYER, *TEXT_44_LAYER),
        offset=1.158,
    )
    assert [word.box.bottom - word.box.top for word in heights] == pytest.approx(
        [11.0, 11.0]
    )
    assert [middle(word) for word in heights] == pytest.approx(
        [middle(THEN_44), middle(PROCEEDS_44)]
    )


def test_height_comes_from_the_covering_word_with_the_same_letters() -> None:
    # Page 44's "then" under the layer's "then" and, made a normal height
    # here, the junk word: the same letters win over a larger overlap.
    junk = replace(JUNK_44_LAYER, box=Box(191.477, 300.0, 319.221, 310.0))
    (then,) = with_layer_heights(
        (THEN_44,), (junk, THEN_44_LAYER, *TEXT_44_LAYER), offset=1.158
    )
    assert then.box.bottom - then.box.top == pytest.approx(11.0)


def test_height_comes_from_the_covering_word_it_overlaps_most_by_its_area() -> None:
    # A misread word under two layer words of other letters: one 9 pt tall
    # that it covers whole, one 12 pt tall and wide that it covers in part.
    word = tesseract("xyz", 100.0, 100.0, 120.0, 108.0, 90.0)
    small = layer("abc", 101.0, 99.0, 119.0, 108.0)
    wide = layer("def", 60.0, 98.0, 160.0, 110.0)
    (taken,) = with_layer_heights((word,), (small, wide, *TEXT_44_LAYER), offset=0.0)
    assert taken.box.bottom - taken.box.top == pytest.approx(9.0)


def test_tall_junk_box_alone_over_a_word_gives_it_no_height() -> None:
    misread = replace(PROCEEDS_44, text="procceds")
    (word,) = with_layer_heights(
        (misread,), (JUNK_44_LAYER, *TEXT_44_LAYER), offset=1.158
    )
    assert word == misread


def test_same_letters_win_over_a_word_the_tesseract_word_holds_whole() -> None:
    # A speck of the layer, 6 pt tall, inside page 44's "then": it is all
    # inside the word, "then" of the layer only half, but "then" gives the
    # height.
    speck = layer("t", 203.0, 300.5, 206.0, 306.5)
    (then,) = with_layer_heights(
        (THEN_44,), (speck, THEN_44_LAYER, *TEXT_44_LAYER), offset=1.158
    )
    assert then.box.bottom - then.box.top == pytest.approx(11.0)


def test_layer_word_of_one_letter_is_not_kept_even_on_a_long_row() -> None:
    # Page 11's skipped line with an "a" of the layer after "compilation".
    letter = layer("a", 462.0, 585.6, 466.0, 592.6)
    words = with_missed_layer_words(
        PAGE_11_TESSERACT, (*PAGE_11_LAYER, letter), offset=PAGE_11_OFFSET
    )
    assert "a" not in [word.text for word in words]


def test_page_offset_takes_no_pair_of_fewer_than_3_letters() -> None:
    # Page 11's "of" with the layer's, 1.4 pt lower: no pair.
    assert layer_offset((OF_11,), (OF_11_LAYER,)) == 0.0
