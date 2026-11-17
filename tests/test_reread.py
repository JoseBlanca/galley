"""Tests of the pure parts of layout's re-reading (docs/specs/reocr.md,
sections 3, 4 and 9, "Unit tests").

Every page here is written by hand, with the book's measures given in the
test, and Tesseract's words are written as it would give them: no PDF is
read and no Tesseract runs. The word list is a small set of words written
here, standing for the book language's list.
"""

from dataclasses import replace

import pytest
from PIL import Image, ImageDraw

from galley.body_measures import group_rows
from galley.errors import FidelityBoundary, FidelityError
from galley.fidelity import check_stage
from galley.layout import BookMeasures, _Side
from galley.layout._reread import (
    CutInCrop,
    RegionReading,
    cut_in_crops,
    cut_in_reading,
    footnote_band_crop,
    footnote_band_reading,
    is_small_print_page,
    margin_note_reading,
    margin_strip,
    note_bands,
    page_rereads,
    pixel_box,
    point_box,
    reading_score,
    small_print_crop,
    small_print_reading,
    words_after_rereads,
)
from galley.model import (
    Box,
    LinesFile,
    PageLayout,
    PageWords,
    Region,
    Reread,
    RereadKind,
    TextSource,
    Word,
    WordsFile,
)

# The words the tests' word list holds, in lower case, as
# wordlist.lower_case_word_list gives them. It holds "bl" and "en", as the
# English list of Tesseract 5.5.4 does (reocr spec, section 3).
_WORD_LIST = frozenset(
    {
        "stephen",
        "of",
        "blois",
        "bl",
        "en",
        "henry's",
        "free",
        "holding",
        "moral",
        "lessons",
        "the",
        "barons",
        "next",
        "history",
        "index",
    }
)


def _word(text: str, x0: float, top: float, x1: float, bottom: float) -> Word:
    return Word(text, Box(x0, top, x1, bottom), None)


def _ocr(text: str, x0: float, top: float, x1: float, bottom: float) -> Word:
    return Word(text, Box(x0, top, x1, bottom), 90.0)


def _layer(*texts: str) -> tuple[Word, ...]:
    """Words of `texts` side by side on one row."""
    return tuple(
        _word(text, 10 + 40 * index, 100, 40 + 40 * index, 110)
        for index, text in enumerate(texts)
    )


def _texts(words: tuple[Word, ...]) -> tuple[str, ...]:
    return tuple(word.text for word in words)


# reading_score


def test_reading_score_counts_each_known_word() -> None:
    assert reading_score(_layer("Stephen", "of", "Blois."), _WORD_LIST) == 3


def test_reading_score_subtracts_unknown_words_from_a_spaced_out_note() -> None:
    # Known: "Bl", "en", "of" (3); unknown: "S", "t", "o", "e", "i", "p",
    # "s", "h" (8), single letters having fewer than 2 letters; "." neither.
    spaced = _layer("S", "Bl", "t", "o", "e", "i", "p", "s", "h", ".", "en", "of")
    assert reading_score(spaced, _WORD_LIST) == -5


def test_reading_score_takes_a_curly_apostrophe_inside_a_word_as_straight() -> None:
    assert reading_score(_layer("Henry’s"), _WORD_LIST) == 1


def test_reading_score_strips_quotation_marks_from_both_ends() -> None:
    assert reading_score(_layer("“Moral”", "'lessons'", '"Barons"'), _WORD_LIST) == 3


def test_reading_score_counts_a_word_broken_at_a_line_end_once_as_known() -> None:
    assert reading_score(_layer("‘free-", "holding.’"), _WORD_LIST) == 1


def test_reading_score_counts_a_broken_word_known_when_joined() -> None:
    assert reading_score(_layer("bar-", "ons"), _WORD_LIST) == 1


def test_reading_score_counts_a_broken_word_of_unknown_parts_once_as_unknown() -> None:
    assert reading_score(_layer("satel-", "lites."), _WORD_LIST) == -1


def test_reading_score_does_not_join_a_hyphen_before_a_number() -> None:
    # "free-" alone is unknown (its key keeps the hyphen); "1066" is known.
    assert reading_score(_layer("free-", "1066"), _WORD_LIST) == 0


def test_reading_score_counts_punctuation_as_neither_known_nor_unknown() -> None:
    assert reading_score(_layer("."), _WORD_LIST) == 0
    assert reading_score(_layer("—", "‘"), _WORD_LIST) == 0


def test_reading_score_of_no_words_is_zero() -> None:
    assert reading_score((), _WORD_LIST) == 0


# is_small_print_page

_MEASURES = BookMeasures(
    column_width=300,
    body_word_height=10,
    body_line_pitch=14,
    usual_left_edge=frozendict({0: 50.0, 1: 50.0}),
    cut_in_inset_left=None,
    cut_in_inset_right=None,
)
# A small row's words are at most 0.85 of the body word height, 10 pt.
_SMALL_PT = 7
_FULL_PT = 10


def _row(top: float, height: float, count: int) -> tuple[Word, ...]:
    """`count` words spread across the column, 50 to 350 pt; one word sits
    in its middle."""
    if count == 1:
        return (_word("12", 190, top, 210, top + height),)
    step = 300 / count
    return tuple(
        _word(
            "index", 50 + step * index, top, 50 + step * (index + 1) - 5, top + height
        )
        for index in range(count)
    )


def _page(rows: tuple[tuple[float, int], ...], *, first_top: float = 80) -> PageWords:
    """A page of `rows`, each its words' height and count, 14 pt apart."""
    words = tuple(
        word
        for index, (height, count) in enumerate(rows)
        for word in _row(first_top + 14 * index, height, count)
    )
    return PageWords(
        index=4, text_source=TextSource.TEXT_LAYER, words=words, figures=()
    )


def _with_words(page: PageWords, words: tuple[Word, ...]) -> PageWords:
    return replace(page, words=(*words, *page.words))


def test_page_of_50_words_in_small_rows_is_small_print() -> None:
    page = _page(((_SMALL_PT, 5),) * 10)
    assert len(page.words) == 50
    assert is_small_print_page(page, _MEASURES)


def test_page_of_49_words_in_small_rows_is_not_small_print() -> None:
    page = _page((*((_SMALL_PT, 5),) * 9, (_SMALL_PT, 4)))
    assert len(page.words) == 49
    assert not is_small_print_page(page, _MEASURES)


def test_page_of_17_small_rows_of_20_is_small_print() -> None:
    page = _page((*((_SMALL_PT, 3),) * 17, *((_FULL_PT, 3),) * 3))
    assert is_small_print_page(page, _MEASURES)


def test_page_of_16_small_rows_of_20_is_not_small_print() -> None:
    page = _page((*((_SMALL_PT, 3),) * 16, *((_FULL_PT, 3),) * 4))
    assert not is_small_print_page(page, _MEASURES)


def test_running_head_of_full_size_words_does_not_count() -> None:
    # Counted, the head would make 17 small rows of 21, under 0.85.
    page = _page((*((_SMALL_PT, 3),) * 17, *((_FULL_PT, 3),) * 3))
    head = tuple(replace(word, text="HISTORY") for word in _row(40, _FULL_PT, 3))
    assert is_small_print_page(_with_words(page, head), _MEASURES)


def test_rows_of_one_word_do_not_count() -> None:
    # Counted, the five page numbers would make 17 small rows of 25.
    page = _page(
        (*((_SMALL_PT, 3),) * 17, *((_FULL_PT, 3),) * 3, *((_FULL_PT, 1),) * 5)
    )
    assert is_small_print_page(page, _MEASURES)


def test_page_of_full_size_rows_is_not_small_print() -> None:
    assert not is_small_print_page(_page(((_FULL_PT, 5),) * 12), _MEASURES)


def test_small_margin_words_do_not_count_as_column_rows() -> None:
    # 4 full-size rows of the column, then 30 rows of a small margin note
    # of two words on the left, outside the column: counted, they would
    # make 30 small rows of 34.
    page = _page(((_FULL_PT, 5),) * 4)
    margin = tuple(
        word
        for index in range(30)
        for word in (
            _word("Moral", 5, 140 + 8 * index, 20, 146 + 8 * index),
            _word("lessons", 22, 140 + 8 * index, 40, 146 + 8 * index),
        )
    )
    assert not is_small_print_page(_with_words(page, margin), _MEASURES)


# note_bands


def _strip(*blocks: tuple[int, int, int, int]) -> Image.Image:
    """A white strip 100 by 300 px with black `blocks`, each (left, top,
    right, bottom), the right and bottom pixels not inked."""
    image = Image.new("L", (100, 300), 255)
    draw = ImageDraw.Draw(image)
    for left, top, right, bottom in blocks:
        draw.rectangle((left, top, right - 1, bottom - 1), fill=0)
    return image


def test_blocks_of_ink_30_px_apart_are_two_bands_cropped_to_ink_plus_6_px() -> None:
    bands = note_bands(_strip((10, 10, 60, 30), (20, 60, 90, 80)))
    assert bands == ((4, 4, 66, 36), (14, 54, 96, 86))


def test_blocks_of_ink_15_px_apart_are_one_band() -> None:
    assert note_bands(_strip((10, 10, 60, 30), (20, 45, 90, 65))) == ((4, 4, 96, 71),)


def test_block_10_px_high_is_no_band() -> None:
    assert note_bands(_strip((10, 10, 60, 20))) == ()


def test_block_20_px_wide_is_no_band() -> None:
    assert note_bands(_strip((10, 10, 30, 30))) == ()


def test_band_of_fewer_than_150_ink_pixels_is_no_band() -> None:
    # Two vertical lines 40 px apart, 2 px wide and 30 px high: 120 pixels,
    # 42 px wide and 30 high.
    assert note_bands(_strip((10, 10, 12, 40), (50, 10, 52, 40))) == ()


def test_rows_of_one_ink_pixel_are_not_inked() -> None:
    # A line 1 px wide joins nothing: the two blocks stay two bands.
    image = _strip((10, 10, 60, 30), (10, 60, 60, 80), (80, 30, 81, 60))
    assert note_bands(image) == ((4, 4, 66, 36), (4, 54, 66, 86))


def test_light_grey_is_not_ink() -> None:
    image = Image.new("L", (100, 300), 255)
    ImageDraw.Draw(image).rectangle((10, 10, 59, 29), fill=140)
    assert note_bands(image) == ()


def test_band_crop_stays_inside_the_strip() -> None:
    assert note_bands(_strip((0, 0, 100, 20))) == ((0, 0, 100, 26),)


# The crops


def test_pixel_box_holds_the_points_box_at_the_dpi() -> None:
    # At 300 dpi a point is 300/72 px: 10 pt is 41.67 px, 20 pt 83.33 px.
    assert pixel_box(Box(10, 100, 20, 110), 300) == (41, 416, 84, 459)


def test_point_box_moves_a_pixel_box_by_the_crop_origin() -> None:
    box = point_box((4, 4, 66, 36), origin=(10, 100), dpi=300)
    assert (box.x0, box.top, box.x1, box.bottom) == pytest.approx(
        (10.96, 100.96, 25.84, 108.64)
    )


def test_small_print_crop_starts_1_pt_below_the_running_head() -> None:
    assert small_print_crop(page_width=400, page_height=600, head_bottom=50) == Box(
        0, 51, 400, 600
    )


def test_small_print_crop_without_running_head_is_the_whole_page() -> None:
    assert small_print_crop(page_width=400, page_height=600, head_bottom=None) == Box(
        0, 0, 400, 600
    )


def test_margin_strip_runs_from_4_pt_inside_the_page_to_4_pt_off_the_column() -> None:
    common = {"left": 50, "right": 350, "column_top": 60, "lowest": 560}
    assert margin_strip(_Side.LEFT, page_width=400, **common) == Box(4, 56, 46, 564)
    assert margin_strip(_Side.RIGHT, page_width=400, **common) == Box(354, 56, 396, 564)


def test_cut_in_crop_is_the_zone_widened_by_2_5_pitches_up_to_the_inset() -> None:
    # A pitch of 14 pt widens the zone by 35 pt above and below; the crop
    # runs from 3 pt outside the column's edge to 3 pt short of the inset.
    left = cut_in_crops(
        ((200, 220),), _Side.LEFT, edge=50, inset=60, pitch=14, head_bottom=None
    )
    right = cut_in_crops(
        ((200, 220),), _Side.RIGHT, edge=350, inset=60, pitch=14, head_bottom=None
    )
    assert left == (CutInCrop(Box(47, 165, 107, 255), ((200, 220),)),)
    assert right == (CutInCrop(Box(293, 165, 353, 255), ((200, 220),)),)


def test_cut_in_zones_whose_crops_overlap_are_one_crop() -> None:
    crops = cut_in_crops(
        ((200, 220), (260, 280), (400, 420)),
        _Side.LEFT,
        edge=50,
        inset=60,
        pitch=14,
        head_bottom=None,
    )
    assert crops == (
        CutInCrop(Box(47, 165, 107, 315), ((200, 220), (260, 280))),
        CutInCrop(Box(47, 365, 107, 455), ((400, 420),)),
    )


def test_cut_in_crop_stops_1_pt_below_the_running_head() -> None:
    crops = cut_in_crops(
        ((200, 220),), _Side.LEFT, edge=50, inset=60, pitch=14, head_bottom=180
    )
    assert crops == (CutInCrop(Box(47, 181, 107, 255), ((200, 220),)),)


def test_footnote_band_crop_is_3_pt_outside_the_column_and_the_band() -> None:
    band = (_word("1", 60, 500, 200, 507), _word("note", 55, 510, 340, 517))
    assert footnote_band_crop(band, left=50, right=350) == Box(47, 497, 353, 520)


# The replacement


def _page_of(words: tuple[Word, ...], index: int = 7) -> PageWords:
    return PageWords(
        index=index, text_source=TextSource.TEXT_LAYER, words=words, figures=()
    )


def _check_fidelity(page: PageWords, rereads: tuple[Reread, ...]) -> None:
    """layout's fidelity check on `page` laid out as one region of the
    words `words_after_rereads` gives."""
    after = words_after_rereads(page.words, rereads)
    lines = group_rows(after)
    region = Region(
        Box(
            min(line.box.x0 for line in lines),
            min(line.box.top for line in lines),
            max(line.box.x1 for line in lines),
            max(line.box.bottom for line in lines),
        ),
        lines,
    )
    check_stage(
        FidelityBoundary.LAYOUT,
        WordsFile(source_pdf_sha256="0" * 64, pages=(page,), removals=()),
        LinesFile(
            source_pdf_sha256="0" * 64,
            pages=(PageLayout(page.index, (region,), ()),),
            rereads=rereads,
        ),
    )


# A margin note of three layer words on the left of a column whose left
# edge is 50 pt; two single letters of the layer just inside the column,
# under Tesseract's "Moral"; a body word beside the note; a margin word
# below the band.
_MORAL = _word("Moral", 10, 100, 40, 108)
_LES = _word("les-", 10, 110, 30, 118)
_SONS = _word("sons", 10, 120, 30, 128)
_LETTER_O = _word("o", 48.5, 101, 49.5, 107)
_LETTER_A = _word("a", 48.2, 102, 49, 106)
_BODY_THE = _word("The", 60, 110, 80, 118)
_BELOW = _word("Fall", 10, 300, 30, 308)
_MARGIN_PAGE = _page_of((_MORAL, _LES, _SONS, _LETTER_O, _LETTER_A, _BODY_THE, _BELOW))
_BAND = Box(8, 98, 46, 130)
_OCR_MORAL = _ocr("Moral", 10, 100, 49, 108)
_OCR_LESSONS = _ocr("lessons.", 10, 115, 40, 123)


def _margin_rereads() -> tuple[Reread, ...]:
    reading = margin_note_reading(
        _Side.LEFT,
        _BAND,
        (_OCR_MORAL, _OCR_LESSONS),
        margin_words=(_MORAL, _LES, _SONS, _BELOW),
        page_words=_MARGIN_PAGE.words,
    )
    return page_rereads(_MARGIN_PAGE.index, (reading,), _WORD_LIST)


def test_margin_note_replaces_its_words_and_the_letters_under_tesseract_words() -> None:
    (record,) = _margin_rereads()
    assert record.page_index == 7
    assert record.kind is RereadKind.MARGIN_NOTE
    assert record.box == _BAND
    assert record.layer_words == (_MORAL, _LES, _SONS, _LETTER_O, _LETTER_A)
    assert record.ocr_words == (_OCR_MORAL, _OCR_LESSONS)
    # "Moral" and "les-" "sons" known, "o" and "a" unknown.
    assert (record.layer_score, record.ocr_score) == (0, 2)
    assert record.kept


def test_kept_margin_note_keeps_the_body_word_beside_it() -> None:
    after = words_after_rereads(_MARGIN_PAGE.words, _margin_rereads())
    assert sorted(_texts(after)) == sorted(("The", "Fall", "Moral", "lessons."))


def test_margin_note_rereads_pass_the_fidelity_check() -> None:
    _check_fidelity(_MARGIN_PAGE, _margin_rereads())


def test_margin_note_reading_scoring_lower_keeps_the_layer() -> None:
    reading = margin_note_reading(
        _Side.LEFT,
        _BAND,
        (_ocr("id", 10, 100, 20, 108), _ocr("i", 22, 100, 24, 108)),
        margin_words=(_MORAL, _LES, _SONS),
        page_words=_MARGIN_PAGE.words,
    )
    (record,) = page_rereads(7, (reading,), _WORD_LIST)
    assert not record.kept
    assert words_after_rereads(_MARGIN_PAGE.words, (record,)) == _MARGIN_PAGE.words


def test_band_with_no_layer_word_and_no_reading_is_not_recorded() -> None:
    reading = margin_note_reading(
        _Side.LEFT,
        Box(8, 400, 46, 420),
        (),
        margin_words=(_MORAL, _LES, _SONS),
        page_words=_MARGIN_PAGE.words,
    )
    assert page_rereads(7, (reading,), _WORD_LIST) == ()


def test_note_the_layer_did_not_read_is_kept() -> None:
    reading = margin_note_reading(
        _Side.LEFT,
        Box(8, 400, 46, 420),
        (_ocr("Moral", 10, 402, 40, 410), _ocr("lessons.", 10, 410, 40, 418)),
        margin_words=(_MORAL, _LES, _SONS),
        page_words=_MARGIN_PAGE.words,
    )
    (record,) = page_rereads(7, (reading,), _WORD_LIST)
    assert record.layer_words == ()
    assert record.kept


# A cut-in crop at the left of a column whose left edge is 50 pt, with an
# inset of 60 pt: the crop runs from 47 to 107 pt, and a note word ends by
# 106 pt.
_CROP = CutInCrop(Box(47, 165, 107, 255), ((200, 220),))
_TANCE = _word("tance", 52, 200, 80, 208)
_CHANGE = _word("change", 60, 170, 100, 180)
_BODY_AN = _word("an", 70, 240, 82, 250)
_HE_BARONS = _word("heBarons", 52, 211, 100, 219)
_BESIDE = _word("word", 104, 212, 130, 220)
_CUT_IN_PAGE = _page_of((_CHANGE, _TANCE, _HE_BARONS, _BESIDE, _BODY_AN))
_OCR_TANCE = _ocr("tance.", 52, 199, 82, 209)
_OCR_THE = _ocr("the", 52, 210, 64, 220)
_OCR_BARONS = _ocr("Barons.", 66, 210, 99, 220)
_OCR_LINES = (
    # Junk read off a full body line: "NE" over "change".
    (_ocr("NE", 62, 171, 90, 179),),
    (_OCR_TANCE,),
    (_OCR_THE, _OCR_BARONS),
    # A body line that runs on to within 3 pt of the crop's inset side.
    (
        _ocr("he", 48, 230, 58, 238),
        _ocr("was", 62, 230, 80, 238),
        _ocr("dd", 85, 230, 105, 238),
    ),
    # "an" read over the body's "an".
    (_ocr("an", 70, 241, 82, 249),),
)


def _cut_in_rereads() -> tuple[Reread, ...]:
    reading = cut_in_reading(
        _Side.LEFT,
        _CROP,
        _OCR_LINES,
        edge=50,
        inset=60,
        cut_in_words=(_TANCE,),
        column_words=(_CHANGE, _HE_BARONS, _BESIDE, _BODY_AN),
    )
    return page_rereads(_CUT_IN_PAGE.index, (reading,), _WORD_LIST)


def test_cut_in_crop_drops_tesseract_words_over_body_words_and_lines_at_the_inset() -> (
    None
):
    (record,) = _cut_in_rereads()
    assert record.kind is RereadKind.CUT_IN_NOTE
    assert record.box == _CROP.box
    assert record.ocr_words == (_OCR_TANCE, _OCR_THE, _OCR_BARONS)


def test_cut_in_crop_replaces_a_column_word_of_a_zone_row_left_of_the_inset() -> None:
    (record,) = _cut_in_rereads()
    assert record.layer_words == (_TANCE, _HE_BARONS)
    assert (record.layer_score, record.ocr_score) == (-2, 1)
    assert record.kept
    after = words_after_rereads(_CUT_IN_PAGE.words, (record,))
    assert sorted(_texts(after)) == sorted(
        ("change", "word", "an", "tance.", "the", "Barons.")
    )
    _check_fidelity(_CUT_IN_PAGE, (record,))


def test_cut_in_reading_with_no_word_left_is_not_kept() -> None:
    # The layer's note word is unknown, so an empty reading would score
    # higher; every word of Tesseract's lies over a body word.
    note = _word("Dspnsrs,", 52, 200, 90, 208)
    reading = cut_in_reading(
        _Side.LEFT,
        _CROP,
        ((_ocr("NE", 62, 171, 90, 179),), (_ocr("an", 70, 241, 82, 249),)),
        edge=50,
        inset=60,
        cut_in_words=(note,),
        column_words=(_CHANGE, _BODY_AN),
    )
    (record,) = page_rereads(7, (reading,), _WORD_LIST)
    assert record.ocr_words == ()
    assert (record.layer_score, record.ocr_score) == (-1, 0)
    assert not record.kept


def test_cut_in_crop_at_the_right_side_mirrors_the_left() -> None:
    # Right edge 350 pt, inset 60 pt: the crop runs from 293 to 353 pt, a
    # note word starts at 294 pt or right of it.
    crop = CutInCrop(Box(293, 165, 353, 255), ((200, 220),))
    note = _word("Barns", 300, 211, 345, 219)
    body = _word("body", 280, 170, 320, 180)
    reading = cut_in_reading(
        _Side.RIGHT,
        crop,
        (
            (_ocr("xx", 290, 171, 300, 179),),
            (_ocr("the", 300, 210, 315, 220), _ocr("Barons.", 318, 210, 345, 220)),
        ),
        edge=350,
        inset=60,
        cut_in_words=(),
        column_words=(note, body),
    )
    (record,) = page_rereads(7, (reading,), _WORD_LIST)
    assert _texts(record.ocr_words) == ("the", "Barons.")
    assert record.layer_words == (note,)
    assert record.kept


# Two regions of one page


def test_second_of_two_overlapping_regions_takes_no_word_the_first_replaced() -> None:
    moral = _word("Moral", 10, 100, 40, 108)
    lesons = _word("lesons", 10, 121, 40, 129)
    following = _word("Next", 10, 140, 40, 148)
    page = _page_of((moral, lesons, following))
    margin_words = (moral, lesons, following)
    upper = margin_note_reading(
        _Side.LEFT,
        Box(8, 98, 46, 130),
        (_ocr("Moral", 10, 100, 40, 108), _ocr("lessons", 10, 121, 40, 129)),
        margin_words=margin_words,
        page_words=page.words,
    )
    lower = margin_note_reading(
        _Side.LEFT,
        Box(8, 125, 46, 160),
        (_ocr("lessons", 10, 121, 40, 129), _ocr("Next", 10, 140, 40, 148)),
        margin_words=margin_words,
        page_words=page.words,
    )
    # Given in either order, the upper band is taken first.
    first, second = page_rereads(7, (lower, upper), _WORD_LIST)
    assert first.layer_words == (moral, lesons)
    assert first.kept
    assert second.layer_words == (following,)
    assert _texts(second.ocr_words) == ("Next",)
    _check_fidelity(page, (first, second))


def test_records_of_a_page_are_in_the_order_of_their_kinds_and_tops() -> None:
    def reading(kind: str, side: _Side, top: float) -> RegionReading:
        x0 = 8 if side is _Side.LEFT else 360
        box = Box(x0, top, x0 + 38, top + 10)
        word = _ocr("Next", x0 + 8, top + 1, x0 + 30, top + 9)
        match kind:
            case "margin":
                return margin_note_reading(
                    side, box, (word,), margin_words=(), page_words=()
                )
            case "cut-in":
                return cut_in_reading(
                    side,
                    CutInCrop(box, ((top, top + 10),)),
                    ((word,),),
                    edge=50 if side is _Side.LEFT else 350,
                    inset=60,
                    cut_in_words=(),
                    column_words=(),
                )
            case _:
                return footnote_band_reading(box, (word,), band_words=())

    readings = (
        reading("footnote", _Side.LEFT, 500),
        reading("cut-in", _Side.RIGHT, 150),
        reading("margin", _Side.RIGHT, 200),
        reading("margin", _Side.RIGHT, 100),
        reading("cut-in", _Side.LEFT, 300),
        reading("margin", _Side.LEFT, 100),
    )
    # No crop overlaps another, so every region is recorded.
    records = page_rereads(7, readings, _WORD_LIST)
    assert tuple(
        (record.kind, record.box.top, record.box.x0) for record in records
    ) == (
        (RereadKind.MARGIN_NOTE, 100, 8),
        (RereadKind.MARGIN_NOTE, 100, 360),
        (RereadKind.MARGIN_NOTE, 200, 360),
        (RereadKind.CUT_IN_NOTE, 150, 360),
        (RereadKind.CUT_IN_NOTE, 300, 8),
        (RereadKind.FOOTNOTE_BAND, 500, 8),
    )


# A small-print page


def test_small_print_page_replaces_every_word_but_its_running_head() -> None:
    head = _word("INDEX", 150, 40, 250, 50)
    margin = _word("Moral", 5, 100, 40, 107)
    entries = (_word("Acre,", 60, 100, 90, 107), _word("siege", 95, 100, 130, 107))
    page = _page_of((head, margin, *entries))
    reading = small_print_reading(
        Box(0, 51, 400, 600),
        (
            _ocr("Moral", 5, 100, 40, 107),
            _ocr("Acre,", 60, 100, 90, 107),
            _ocr("siege", 95, 100, 130, 107),
            _ocr("of,", 135, 100, 150, 107),
        ),
        page_words=page.words,
        head_words=(head,),
    )
    (record,) = page_rereads(7, (reading,), _WORD_LIST)
    assert record.kind is RereadKind.SMALL_PRINT_PAGE
    assert record.layer_words == (margin, *entries)
    assert record.kept
    _check_fidelity(page, (record,))


def test_small_print_page_with_another_region_raises() -> None:
    page = _page_of((_MORAL,))
    whole = small_print_reading(
        Box(0, 0, 400, 600), (), page_words=page.words, head_words=()
    )
    margin = margin_note_reading(
        _Side.LEFT, _BAND, (), margin_words=(_MORAL,), page_words=page.words
    )
    with pytest.raises(ValueError, match="small-print page"):
        page_rereads(7, (whole, margin), _WORD_LIST)


def test_footnote_band_replaces_the_band_words() -> None:
    band = (_word("^", 50, 500, 55, 507), _word("Ibid.", 58, 500, 80, 507))
    page = _page_of((_BODY_THE, *band))
    reading = footnote_band_reading(
        Box(47, 497, 353, 510),
        (_ocr("1", 50, 500, 55, 507), _ocr("Ibid.", 58, 500, 80, 507)),
        band_words=band,
    )
    (record,) = page_rereads(7, (reading,), _WORD_LIST)
    assert record.kind is RereadKind.FOOTNOTE_BAND
    assert record.layer_words == band
    # "1" is a number, so known; "^" is neither; "Ibid." is not in the list.
    assert (record.layer_score, record.ocr_score) == (-1, 0)
    assert record.kept
    _check_fidelity(page, (record,))


# The fidelity check of the records


def test_fidelity_check_fails_on_a_kept_record_naming_a_word_the_page_lacks() -> None:
    (record,) = _margin_rereads()
    ghost = _word("Ghost", 10, 140, 40, 148)
    wrong = replace(record, layer_words=(*record.layer_words, ghost))
    with pytest.raises(FidelityError, match="does not have"):
        _check_fidelity(_MARGIN_PAGE, (wrong,))


def test_fidelity_check_fails_on_two_kept_records_naming_one_word() -> None:
    (record,) = _margin_rereads()
    twice = replace(record, ocr_words=())
    with pytest.raises(FidelityError, match="two kept rereads"):
        _check_fidelity(_MARGIN_PAGE, (record, twice))
