"""Tests of galley.layout (spec section 7, "layout" and "Their tests").

Every value is written by hand: layout's tests need no output of extract.
The excerpt tests of layout are in work package 4.
"""

import hashlib
from dataclasses import replace
from pathlib import Path

import pytest

from galley import layout
from galley.book_folder import BookFolder
from galley.config import BookConfig, Language
from galley.errors import FidelityBoundary, FidelityError, InputFileError
from galley.fidelity import check_stage
from galley.layout import BookMeasures, group_lines, layout_page, measure_book
from galley.model import (
    Box,
    Figure,
    Line,
    LinesFile,
    PageInfo,
    PageKind,
    PageLayout,
    PagesFile,
    PageWords,
    TextSource,
    Word,
    WordsFile,
    read_lines,
    write_lines,
    write_pages,
    write_words,
)


def _word(text: str, x0: float, top: float, x1: float, bottom: float) -> Word:
    return Word(text, Box(x0, top, x1, bottom), None)


def _texts(lines: tuple[Line, ...]) -> tuple[tuple[str, ...], ...]:
    return tuple(tuple(word.text for word in line.words) for line in lines)


def _page(index: int, words: tuple[Word, ...]) -> PageWords:
    return PageWords(
        index=index, text_source=TextSource.TEXT_LAYER, words=words, figures=()
    )


# group_lines


def test_two_rows_given_shuffled_come_out_as_two_lines_left_to_right() -> None:
    words = (
        _word("six", 70, 30, 90, 40),
        _word("two", 40, 10, 60, 20),
        _word("four", 10, 30, 30, 40),
        _word("three", 70, 10, 90, 20),
        _word("five", 40, 30, 60, 40),
        _word("one", 10, 10, 30, 20),
    )
    lines = group_lines(words)
    assert _texts(lines) == (("one", "two", "three"), ("four", "five", "six"))
    assert tuple(line.box for line in lines) == (
        Box(10, 10, 90, 20),
        Box(10, 30, 90, 40),
    )


def test_word_two_points_below_with_its_centre_in_the_band_joins_the_line() -> None:
    words = (_word("anchor", 10, 10, 30, 20), _word("low", 40, 12, 60, 22))
    lines = group_lines(words)
    assert _texts(lines) == (("anchor", "low"),)
    assert lines[0].box == Box(10, 10, 60, 22)


def test_word_whose_centre_is_on_the_anchors_bottom_joins_the_line() -> None:
    # Centre (10 + 30) / 2 = 20.0, the anchor's bottom: edges are included.
    words = (_word("anchor", 10, 10, 30, 20), _word("edge", 40, 10, 60, 30))
    assert _texts(group_lines(words)) == (("anchor", "edge"),)


def test_word_whose_centre_is_just_below_the_anchors_bottom_starts_a_line() -> None:
    # Centre (10.02 + 30) / 2 = 20.01, 0.01 pt below the anchor's bottom.
    words = (_word("anchor", 10, 10, 30, 20), _word("below", 40, 10.02, 60, 30))
    assert _texts(group_lines(words)) == (("anchor",), ("below",))


def test_two_columns_of_two_rows_give_two_lines_across_both_columns() -> None:
    # The skeleton's known bad reading order (spec sections 2 and 7): a row
    # runs across both columns. The real layout spec changes this.
    words = (
        _word("left-1", 10, 10, 100, 20),
        _word("left-2", 10, 30, 100, 40),
        _word("right-1", 200, 10, 300, 20),
        _word("right-2", 200, 30, 300, 40),
    )
    assert _texts(group_lines(words)) == (
        ("left-1", "right-1"),
        ("left-2", "right-2"),
    )


def test_words_with_the_same_top_and_x0_keep_their_given_order() -> None:
    words = (_word("first", 10, 10, 30, 20), _word("second", 10, 10, 30, 20))
    assert _texts(group_lines(words)) == (("first", "second"),)


def test_words_of_a_line_are_sorted_by_x0() -> None:
    # "right" comes first by top and anchors the band 10-20; "left" has its
    # centre at 16, joins, and goes before "right" by x0.
    words = (_word("right", 50, 10, 70, 20), _word("left", 10, 11, 30, 21))
    lines = group_lines(words)
    assert _texts(lines) == (("left", "right"),)
    assert lines[0].box == Box(10, 10, 70, 21)


def test_a_line_keeps_the_band_of_its_first_word() -> None:
    # Each word 4 pt lower than the one before: "b" (centre 9) is in the
    # band of "a" (0-10), "c" (centre 13) is not, though it is in b's.
    words = (
        _word("a", 10, 0, 20, 10),
        _word("b", 30, 4, 40, 14),
        _word("c", 50, 8, 60, 18),
    )
    lines = group_lines(words)
    assert _texts(lines) == (("a", "b"), ("c",))
    assert tuple(line.box for line in lines) == (Box(10, 0, 40, 14), Box(50, 8, 60, 18))


def test_words_with_the_same_top_are_taken_by_x0() -> None:
    # "short" goes first by x0 and anchors the band 10-14; the centre of
    # "tall", 20, is outside it. Taken in the given order, "tall" would
    # anchor the band 10-30 and "short" (centre 12) would join it.
    words = (_word("tall", 50, 10, 60, 30), _word("short", 10, 10, 20, 14))
    lines = group_lines(words)
    assert _texts(lines) == (("short",), ("tall",))
    assert tuple(line.box for line in lines) == (
        Box(10, 10, 20, 14),
        Box(50, 10, 60, 30),
    )


def test_no_words_give_no_lines() -> None:
    assert group_lines(()) == ()


# layout_page

_PAGE_WORDS = (
    _word("Alpha", 50, 100, 90, 112),
    _word("beta", 95, 101, 120, 113),
    _word("gamma", 40, 120, 80, 132),
    _word("delta", 85, 120, 130, 131),
)


def test_layout_page_without_measures_puts_every_line_in_one_region() -> None:
    result = layout_page(_page(3, _PAGE_WORDS), None)
    assert result.index == 3
    assert len(result.regions) == 1
    region = result.regions[0]
    assert _texts(region.lines) == (("Alpha", "beta"), ("gamma", "delta"))
    assert region.box == Box(40, 100, 130, 132)
    for line in region.lines:
        assert region.box.x0 <= line.box.x0
        assert region.box.top <= line.box.top
        assert line.box.x1 <= region.box.x1
        assert line.box.bottom <= region.box.bottom


def test_page_with_no_words_has_no_region() -> None:
    assert layout_page(_page(5, ()), None) == PageLayout(5, (), ())
    assert layout_page(_page(5, ()), _MEASURES) == PageLayout(5, (), ())


def test_layout_page_copies_the_figures() -> None:
    figures = (Figure(Box(10, 20, 300, 400), "images/p0002-01.png", 300),)
    page = replace(_page(2, _PAGE_WORDS[:1]), figures=figures)
    assert layout_page(page, None).figures == figures
    assert layout_page(page, _MEASURES).figures == figures


# measure_book and the body column (layout spec section 3, "The book's
# measures" and step 1)

_ROW_HEIGHT = 8.0
_PITCH = 12.0


def _full_row(row: int, left: float, width: float, top: float) -> tuple[Word, ...]:
    """Three words of height 8 that fill `width` from `left`, 4 pt apart as
    word spaces are, too close for a gutter."""
    bottom = top + _ROW_HEIGHT
    return (
        _word(f"a{row}", left, top, left + 65, bottom),
        _word(f"b{row}", left + 69, top, left + 135, bottom),
        _word(f"c{row}", left + 139, top, left + width, bottom),
    )


def _column_page(
    index: int, left: float, width: float, rows: int, top: float = 100.0
) -> PageWords:
    """A page of `rows` full rows of the column at `left`, `width` wide,
    12 pt apart."""
    return _page(
        index,
        tuple(
            word
            for row in range(rows)
            for word in _full_row(row, left, width, top + row * _PITCH)
        ),
    )


def test_measure_book_on_20_pages_gives_the_medians() -> None:
    # Widths 200 to 219: the median is 209.5. Even pages start at 50, odd at
    # 60. A page of 5 rows, 400 pt wide at 10, is not measured: the others
    # have 15 rows or more.
    pages = (
        *(_column_page(i, 50 if i % 2 == 0 else 60, 200 + i, 16) for i in range(20)),
        _column_page(20, 10, 400, 5),
    )
    measures = measure_book(_words_file(pages))
    assert measures == BookMeasures(
        column_width=209.5,
        body_word_height=_ROW_HEIGHT,
        body_line_pitch=_PITCH,
        usual_left_edge=frozendict({0: 50.0, 1: 60.0}),
    )


def test_measure_book_pools_the_heights_and_pitches_of_every_row() -> None:
    # Page 0: 16 rows of height 8, 12 pt apart. Page 1: 16 rows of height
    # 10, 14 pt apart. Pooled, 32 heights and 30 pitches: the medians fall
    # between the two pages' values.
    tall = tuple(
        Word(word.text, replace(word.box, bottom=word.box.top + 10), None)
        for row in range(16)
        for word in _full_row(row, 50, 200, 100 + row * 14)
    )
    pages = (_column_page(0, 50, 200, 16), _page(1, tall))
    measures = measure_book(_words_file(pages))
    assert measures is not None
    assert measures.body_word_height == 9.0
    assert measures.body_line_pitch == 13.0


def test_measure_book_on_pages_of_2_rows_gives_none() -> None:
    pages = tuple(_column_page(i, 50, 200, 2) for i in range(20))
    assert measure_book(_words_file(pages)) is None


def test_measure_book_with_no_page_of_15_rows_measures_pages_of_3() -> None:
    pages = (_column_page(0, 50, 200, 3), _column_page(1, 50, 200, 2))
    assert measure_book(_words_file(pages)) == BookMeasures(
        column_width=200.0,
        body_word_height=_ROW_HEIGHT,
        body_line_pitch=_PITCH,
        usual_left_edge=frozendict({0: 50.0, 1: 50.0}),
    )


def test_column_left_edge_is_the_commonest_left_side_of_the_wide_rows() -> None:
    # 8 full rows start at 50; 9 short rows (100 pt, under 0.8 of the
    # column) start at 80; 2 rows with a margin note start at 20 and are
    # wider than the column. The commonest left side of all rows is 80, of
    # the wide rows 50.
    full = tuple(w for row in range(8) for w in _full_row(row, 50, 200, row * 12))
    short = tuple(
        _word(f"s{row}", 80, 200 + row * 12, 180, 208 + row * 12) for row in range(9)
    )
    noted = tuple(
        word
        for row in range(2)
        for word in (
            _word(f"note{row}", 20, 320 + row * 12, 44, 328 + row * 12),
            *_full_row(row + 20, 50, 200, 320 + row * 12),
        )
    )
    measures = measure_book(
        _words_file((_page(0, full + short + noted), _column_page(1, 50, 200, 16)))
    )
    assert measures is not None
    assert measures.usual_left_edge[0] == 50.0


def test_column_left_edge_counts_edges_within_2_pt_and_takes_the_smallest_on_a_tie() -> (
    None
):
    # Two rows start at 50 and two at 54: each value has two edges within
    # 2 pt of it, and the tie goes to the smaller.
    rows = (
        *_full_row(0, 50, 200, 100),
        *_full_row(1, 50, 200, 112),
        *_full_row(2, 54, 200, 124),
        *_full_row(3, 54, 200, 136),
    )
    measures = measure_book(_words_file((_page(0, rows),)))
    assert measures is not None
    assert measures.usual_left_edge[0] == 50.0
    # A fifth row at 51.6 rounds to 52, which has all five edges within 2
    # pt. A fifth row at 55.6 rounds to 56: 54 and 56 have three edges
    # each, 50 two, and the tie goes to 54.
    for extra_left, expected in ((51.6, 52.0), (55.6, 54.0)):
        page = _page(0, rows + _full_row(4, extra_left, 200, 148))
        measures = measure_book(_words_file((page,)))
        assert measures is not None
        assert measures.usual_left_edge[0] == expected


def test_usual_left_edge_of_a_parity_without_a_wide_row_is_the_other_paritys() -> None:
    # Page 1 holds only short rows (100 pt of a 200-pt column).
    short = tuple(
        _word(f"s{row}", 90, 100 + row * 12, 190, 108 + row * 12) for row in range(16)
    )
    pages = (*(_column_page(i, 50, 200, 16) for i in (0, 2, 4)), _page(1, short))
    measures = measure_book(_words_file(pages))
    assert measures is not None
    assert measures.usual_left_edge == frozendict({0: 50.0, 1: 50.0})


# layout_page: outer margin notes and the running-head line (layout spec
# section 3, steps 1 to 3)

# The measures of the pages below: a column 200 pt wide at 50 on every
# page, rows 12 pt apart of words 8 pt high.
_MEASURES = BookMeasures(
    column_width=200.0,
    body_word_height=_ROW_HEIGHT,
    body_line_pitch=_PITCH,
    usual_left_edge=frozendict({0: 50.0, 1: 50.0}),
)


def _rows(count: int, top: float = 100.0, left: float = 50.0) -> tuple[Word, ...]:
    """`count` full rows of the column of `_MEASURES`, 12 pt apart from `top`."""
    return tuple(
        word
        for row in range(count)
        for word in _full_row(row, left, 200, top + row * _PITCH)
    )


def _region_texts(page: PageLayout) -> tuple[tuple[tuple[str, ...], ...], ...]:
    return tuple(_texts(region.lines) for region in page.regions)


def test_margin_word_6_pt_right_of_the_column_is_a_margin_region_of_its_own() -> None:
    note = _word("Note", 256, 136, 290, 144)  # beside row 3, top 136
    result = layout_page(_page(0, (*_rows(20), note)), _MEASURES)
    body, margin = result.regions
    assert len(body.lines) == 20
    assert "Note" not in {word.text for line in body.lines for word in line.words}
    assert _texts(margin.lines) == (("Note",),)
    assert margin.box == note.box


def test_word_1_pt_outside_the_column_stays_in_its_body_line() -> None:
    hung = _word("”", 251, 136, 255, 144)  # 1 pt right of the right edge, 250
    result = layout_page(_page(0, (*_rows(20), hung)), _MEASURES)
    (body,) = result.regions
    assert _texts(body.lines)[3] == ("a3", "b3", "c3", "”")


def test_margin_word_2_pt_left_of_the_column_is_a_margin_word() -> None:
    note = _word("Note", 20, 136, 48, 144)  # right side 2 pt left of 50
    result = layout_page(_page(0, (*_rows(20), note)), _MEASURES)
    assert _region_texts(result)[1:] == ((("Note",),),)


def test_margin_lines_more_than_1_5_pitches_apart_are_two_margin_regions() -> None:
    # Lines at 136 and 148 are one note; the next at 167 is 19 pt, more
    # than 1.5 pitches (18 pt), below 148: a second note.
    notes = (
        _word("First", 256, 136, 290, 144),
        _word("note", 256, 148, 290, 156),
        _word("Second", 256, 167, 290, 175),
    )
    result = layout_page(_page(0, (*_rows(20), *notes)), _MEASURES)
    assert _region_texts(result)[1:] == ((("First",), ("note",)), (("Second",),))


def test_page_without_a_wide_row_places_the_column_at_its_paritys_usual_left_edge() -> (
    None
):
    # Rows of 100 pt at 120: none is 0.8 of the column wide. Page 1 takes
    # the usual left edge 50, so the word at 20 to 40 is a margin word; at
    # parity 0's edge, 300, every word would be.
    short = tuple(
        _word(f"s{row}", 120, 100 + row * 12, 220, 108 + row * 12) for row in range(5)
    )
    note = _word("Note", 20, 200, 40, 208)  # below the rows, on a row of its own
    measures = replace(_MEASURES, usual_left_edge=frozendict({0: 300.0, 1: 50.0}))
    result = layout_page(_page(1, (*short, note)), measures)
    assert _region_texts(result) == (
        tuple((f"s{row}",) for row in range(5)),
        (("Note",),),
    )


def test_head_row_1_4_pitches_above_the_body_is_a_running_head_region_first() -> None:
    head = _word("HEAD", 120, 100 - 1.4 * _PITCH, 180, 100 - 1.4 * _PITCH + 8)
    result = layout_page(_page(0, (head, *_rows(20))), _MEASURES)
    head_region, body = result.regions
    assert _texts(head_region.lines) == (("HEAD",),)
    assert len(body.lines) == 20


def test_head_row_1_2_pitches_above_the_body_gives_no_running_head_region() -> None:
    head = _word("HEAD", 120, 100 - 1.2 * _PITCH, 180, 100 - 1.2 * _PITCH + 8)
    result = layout_page(_page(0, (head, *_rows(20))), _MEASURES)
    (body,) = result.regions
    assert _texts(body.lines)[0] == ("HEAD",)
    assert len(body.lines) == 21


def test_row_of_specks_above_the_head_goes_into_the_running_head_region() -> None:
    specks = _word(";", 140, 60, 144, 66)
    head = _word("HEAD", 120, 80, 180, 88)
    result = layout_page(_page(0, (specks, head, *_rows(20))), _MEASURES)
    assert _region_texts(result)[0] == ((";",), ("HEAD",))
    assert len(result.regions) == 2


def test_specks_above_a_head_not_set_apart_stay_in_the_body() -> None:
    specks = _word(";", 140, 60, 144, 66)
    head = _word("HEAD", 120, 88, 180, 96)  # 12 pt above the body: 1 pitch
    result = layout_page(_page(0, (specks, head, *_rows(20))), _MEASURES)
    (body,) = result.regions
    assert _texts(body.lines)[:2] == ((";",), ("HEAD",))


def test_page_whose_only_row_holds_a_letter_has_no_running_head_region() -> None:
    result = layout_page(_page(0, (_word("Alone", 120, 100, 180, 108),)), _MEASURES)
    assert _region_texts(result) == ((("Alone",),),)


def test_margin_note_level_with_the_head_never_joins_the_head() -> None:
    head = _word("HEAD", 120, 80, 180, 88)
    note = _word("Note", 256, 80, 290, 88)
    result = layout_page(_page(0, (head, note, *_rows(20))), _MEASURES)
    assert _region_texts(result)[0] == (("HEAD",),)
    assert _region_texts(result)[2] == (("Note",),)


# layout_page: the footnote band, columns and the drop capital (layout spec
# section 3, steps 4 to 6)

_SMALL_HEIGHT = 0.7 * _ROW_HEIGHT


def _small_rows(count: int, top: float, pitch: float = 9.0) -> tuple[Word, ...]:
    """`count` rows of words 0.7 of the body word height high, `pitch` apart."""
    return tuple(
        _word(f"n{row}", 50, top + row * pitch, 250, top + row * pitch + _SMALL_HEIGHT)
        for row in range(count)
    )


# 20 body rows at tops 100 to 328.
_LAST_BODY_TOP = 100 + 19 * _PITCH


def test_small_rows_1_5_pitches_below_the_body_are_a_band_region() -> None:
    band = _small_rows(5, _LAST_BODY_TOP + 1.5 * _PITCH)
    result = layout_page(_page(0, (*_rows(20), *band)), _MEASURES)
    body, band_region = result.regions
    assert len(body.lines) == 20
    assert _texts(band_region.lines) == tuple((f"n{row}",) for row in range(5))


def test_small_rows_without_the_gap_are_no_band() -> None:
    band = _small_rows(5, _LAST_BODY_TOP + _PITCH)
    result = layout_page(_page(0, (*_rows(20), *band)), _MEASURES)
    (body,) = result.regions
    assert len(body.lines) == 25


def test_page_of_small_rows_only_has_no_band() -> None:
    rows = (*_small_rows(10, 100), *_small_rows(10, 100 + 9 * 9 + 1.5 * _PITCH))
    result = layout_page(_page(0, rows), _MEASURES)
    (body,) = result.regions
    assert len(body.lines) == 20


def test_small_row_set_apart_but_followed_by_body_rows_is_no_band() -> None:
    # One small row in four from there down: under two thirds.
    small = _small_rows(1, _LAST_BODY_TOP + 1.5 * _PITCH)
    after = _rows(3, top=_LAST_BODY_TOP + 1.5 * _PITCH + _PITCH)
    result = layout_page(_page(0, (*_rows(20), *small, *after)), _MEASURES)
    (body,) = result.regions
    assert len(body.lines) == 24


def _two_column_rows(
    count: int, top: float = 100.0, height: float = _ROW_HEIGHT, pitch: float = _PITCH
) -> tuple[Word, ...]:
    """`count` rows of a left word from 50 to 146 and a right word from 154
    to 250: an empty strip 8 pt wide at the middle of the column."""
    return tuple(
        word
        for row in range(count)
        for word in (
            _word(f"L{row}", 50, top + row * pitch, 146, top + row * pitch + height),
            _word(f"R{row}", 154, top + row * pitch, 250, top + row * pitch + height),
        )
    )


def test_10_rows_with_an_empty_strip_at_the_middle_are_two_columns_left_first() -> None:
    result = layout_page(_page(0, _two_column_rows(10)), _MEASURES)
    assert _region_texts(result) == (
        tuple((f"L{row}",) for row in range(10)),
        tuple((f"R{row}",) for row in range(10)),
    )


def test_7_rows_with_an_empty_strip_at_the_middle_are_one_region() -> None:
    result = layout_page(_page(0, _two_column_rows(7)), _MEASURES)
    assert _region_texts(result) == (tuple((f"L{row}", f"R{row}") for row in range(7)),)


def test_column_cut_keeps_the_rows_above_and_below_as_regions_of_their_own() -> None:
    title = _word("INDEX", 120, 76, 180, 84)  # spans the strip
    columns = _two_column_rows(10)
    footer = _word("END", 120, 100 + 10 * _PITCH, 180, 108 + 10 * _PITCH)
    result = layout_page(_page(0, (title, *columns, footer)), _MEASURES)
    assert _region_texts(result) == (
        (("INDEX",),),
        tuple((f"L{row}",) for row in range(10)),
        tuple((f"R{row}",) for row in range(10)),
        (("END",),),
    )


def test_blank_left_cell_and_a_word_over_the_gutter_keep_the_columns_one_run() -> None:
    # Rows 0 to 4 and 7 to 11 are open. Row 5 has a word on the right only;
    # row 6 a word from 100 to 152, across the strip but with its middle,
    # 126, more than 6 pt from the strip's. Both are compatible.
    rows = tuple(
        word for word in _two_column_rows(12) if word.text not in {"L5", "L6", "R5"}
    )
    rows += (
        _word("R5", 200, 100 + 5 * _PITCH, 250, 108 + 5 * _PITCH),
        _word("X6", 100, 100 + 6 * _PITCH, 152, 108 + 6 * _PITCH),
    )
    result = layout_page(_page(0, rows), _MEASURES)
    left, right = result.regions
    assert _texts(left.lines) == (
        *((f"L{row}",) for row in range(5)),
        ("X6",),
        *((f"L{row}",) for row in range(7, 12)),
    )
    assert _texts(right.lines) == tuple((f"R{row}",) for row in range(12))


def test_word_across_the_middle_of_the_gutter_ends_the_run() -> None:
    # Row 5 holds one word from 140 to 160: its middle is the strip's. Two
    # runs of 5 open rows are too short to cut.
    rows = tuple(
        word for word in _two_column_rows(11) if word.text not in {"L5", "R5"}
    ) + (_word("X5", 140, 100 + 5 * _PITCH, 160, 108 + 5 * _PITCH),)
    result = layout_page(_page(0, rows), _MEASURES)
    (body,) = result.regions
    assert len(body.lines) == 11


def test_3_band_rows_justified_to_the_gutter_are_two_band_columns() -> None:
    band = _two_column_rows(
        3, top=_LAST_BODY_TOP + 1.5 * _PITCH, height=_SMALL_HEIGHT, pitch=9.0
    )
    result = layout_page(_page(0, (*_rows(20), *band)), _MEASURES)
    assert _region_texts(result)[1:] == (
        tuple((f"L{row}",) for row in range(3)),
        tuple((f"R{row}",) for row in range(3)),
    )


def test_3_band_rows_of_short_notes_side_by_side_stay_three_rows() -> None:
    # The left notes end at 90: the leftmost strip open on every row is at
    # the start of the middle third, its middle at 116.7, 33 pt from the
    # column's middle, 150.
    top = _LAST_BODY_TOP + 1.5 * _PITCH
    band = tuple(
        word
        for row in range(3)
        for word in (
            _word(f"{2 * row + 1}", 50, top + row * 9, 90, top + row * 9 + 5.6),
            _word(f"{2 * row + 2}", 154, top + row * 9, 200, top + row * 9 + 5.6),
        )
    )
    result = layout_page(_page(0, (*_rows(20), *band)), _MEASURES)
    assert _region_texts(result)[1:] == ((("1", "2"), ("3", "4"), ("5", "6")),)


def test_band_rows_with_a_gutter_11_pt_off_the_middle_stay_rows() -> None:
    # Left notes end at 157.5 and right notes start at 166: the strips'
    # middles step by 1 pt from 116.7, so the gutter's middle is at 160.7
    # (strip 157.7 to 163.7), 10.7 pt right of the column's middle, though
    # every left part ends within 3 pt of the strip. With the left notes
    # ending at 156.5, the gutter is at 159.7, 9.7 pt off the middle, and
    # the band is cut.
    top = _LAST_BODY_TOP + 1.5 * _PITCH

    def band(left_end: float) -> tuple[Word, ...]:
        return tuple(
            word
            for row in range(3)
            for word in (
                _word(f"L{row}", 50, top + row * 9, left_end, top + row * 9 + 5.6),
                _word(f"R{row}", 166, top + row * 9, 250, top + row * 9 + 5.6),
            )
        )

    off = layout_page(_page(0, (*_rows(20), *band(157.5))), _MEASURES)
    assert _region_texts(off)[1:] == (
        tuple((f"L{row}", f"R{row}") for row in range(3)),
    )
    centred = layout_page(_page(0, (*_rows(20), *band(156.5))), _MEASURES)
    assert _region_texts(centred)[1:] == (
        tuple((f"L{row}",) for row in range(3)),
        tuple((f"R{row}",) for row in range(3)),
    )


def _drop_capital_page(capital_top: float) -> tuple[Word, ...]:
    """A drop capital 3 body word heights tall at the left edge, beside rows
    0 and 1, which start at 75; 18 full rows below them."""
    beside = tuple(
        word
        for row in range(2)
        for word in (
            _word(f"a{row}", 75, 100 + row * _PITCH, 130, 108 + row * _PITCH),
            _word(f"b{row}", 140, 100 + row * _PITCH, 250, 108 + row * _PITCH),
        )
    )
    capital = _word("IN", 50, capital_top, 70, capital_top + 3 * _ROW_HEIGHT)
    return (capital, *beside, *_rows(18, top=100 + 2 * _PITCH))


def test_drop_capital_is_the_first_word_of_the_upper_line_it_spans() -> None:
    result = layout_page(_page(0, _drop_capital_page(100)), _MEASURES)
    (body,) = result.regions
    assert _texts(body.lines)[:3] == (
        ("IN", "a0", "b0"),
        ("a1", "b1"),
        ("a0", "b0", "c0"),
    )
    assert len(body.lines) == 20
    assert body.lines[0].box == Box(50, 100, 250, 124)


def test_drop_capital_whose_top_is_below_the_upper_lines_centre_joins_that_line() -> (
    None
):
    # The upper line is 100 to 108; the capital's top, 104.5, is 0.5 pt
    # below its centre.
    result = layout_page(_page(0, _drop_capital_page(104.5)), _MEASURES)
    (body,) = result.regions
    assert _texts(body.lines)[:2] == (("IN", "a0", "b0"), ("a1", "b1"))


def test_tall_word_away_from_the_left_edge_is_no_drop_capital() -> None:
    # 4 pt right of the left edge: its rows are grouped as the skeleton did.
    words = tuple(
        replace(word, box=replace(word.box, x0=54, x1=74))
        if word.text == "IN"
        else word
        for word in _drop_capital_page(100)
    )
    result = layout_page(_page(0, words), _MEASURES)
    # The tall word's row holds both rows beside it; the next row, 24 pt
    # below its top, sets it apart as a running-head region.
    assert _region_texts(result)[0] == (("IN", "a0", "a1", "b0", "b1"),)


def test_drop_capital_with_no_line_beside_it_is_laid_out_as_a_body_word() -> None:
    # A word 3 body word heights tall at the left edge, alone between rows
    # 9 and 10 of the body: no line overlaps it to its right.
    tall = _word("A", 50, 220, 70, 244)
    words = (*_rows(10), tall, *_rows(10, top=256))
    result = layout_page(_page(0, words), _MEASURES)
    (body,) = result.regions
    assert _texts(body.lines)[10] == ("A",)
    assert len(body.lines) == 21


# The fidelity check at the layout boundary


def _words_file(pages: tuple[PageWords, ...]) -> WordsFile:
    return WordsFile(source_pdf_sha256="0" * 64, pages=pages, removals=())


def test_fidelity_check_passes_on_layout_pages() -> None:
    pages = (_page(0, _PAGE_WORDS), _page(1, ()))
    lines = LinesFile(
        source_pdf_sha256="0" * 64,
        pages=tuple(layout_page(p, _MEASURES) for p in pages),
    )
    check_stage(FidelityBoundary.LAYOUT, _words_file(pages), lines)


def test_fidelity_check_fails_when_a_word_is_dropped_from_a_line() -> None:
    page = layout_page(_page(0, _PAGE_WORDS), None)
    region = page.regions[0]
    first_line = region.lines[0]
    dropped = replace(first_line, words=first_line.words[:1])
    page = replace(page, regions=(replace(region, lines=(dropped, *region.lines[1:])),))
    lines = LinesFile(source_pdf_sha256="0" * 64, pages=(page,))
    with pytest.raises(FidelityError) as raised:
        check_stage(
            FidelityBoundary.LAYOUT, _words_file((_page(0, _PAGE_WORDS),)), lines
        )
    assert raised.value.missing == frozendict({"beta": 1})
    assert raised.value.invented == frozendict()


# run, on a book folder of its own


_PDF_BYTES = b"%PDF-1.4 a stand-in: layout reads only its hash"
_PAGE_COUNT = 8


def _book(root: Path) -> tuple[BookFolder, BookConfig]:
    """A book folder with pages.json and words.json of 8 pages written by
    hand, every page's words a different shuffle of two rows, page 4
    without words."""
    pdf = root / "book.pdf"
    pdf.write_bytes(_PDF_BYTES)
    pdf_hash = hashlib.sha256(_PDF_BYTES).hexdigest()
    folder = BookFolder(root)
    pages = PagesFile(
        source_pdf_sha256=pdf_hash,
        pages=tuple(
            PageInfo(
                index=index,
                width_pt=500.0,
                height_pt=700.0,
                kind=PageKind.TEXT,
                text_source=TextSource.TEXT_LAYER,
                text_layer_score=None,
                exclude_regions=(),
                blank_checked_by_ocr=False,
            )
            for index in range(_PAGE_COUNT)
        ),
        ocr_audit=None,
    )
    word_pages = tuple(
        _page(
            index,
            () if index == 4 else _PAGE_WORDS[index % 4 :] + _PAGE_WORDS[: index % 4],
        )
        for index in range(_PAGE_COUNT)
    )
    write_pages(folder.pages_json, pages)
    write_words(
        folder.words_json, replace(_words_file(word_pages), source_pdf_sha256=pdf_hash)
    )
    config = BookConfig(
        pdf=pdf, title="A Book", authors=("An Author",), language=Language.EN
    )
    return folder, config


@pytest.mark.thread_unsafe
def test_run_writes_the_layout_of_every_page(tmp_path: Path) -> None:
    folder, config = _book(tmp_path)
    layout.run(folder, config, workers=1)
    written = read_lines(folder.lines_json)
    assert written.source_pdf_sha256 == hashlib.sha256(_PDF_BYTES).hexdigest()
    assert tuple(page.index for page in written.pages) == tuple(range(_PAGE_COUNT))
    assert written.pages[4] == PageLayout(4, (), ())
    expected_lines = (("Alpha", "beta"), ("gamma", "delta"))
    for page in written.pages[:4] + written.pages[5:]:
        (region,) = page.regions
        assert _texts(region.lines) == expected_lines


@pytest.mark.thread_unsafe
def test_run_with_1_worker_and_with_3_writes_the_same_bytes(tmp_path: Path) -> None:
    one = tmp_path / "one"
    three = tmp_path / "three"
    one.mkdir()
    three.mkdir()
    folder_one, config_one = _book(one)
    folder_three, config_three = _book(three)
    layout.run(folder_one, config_one, workers=1)
    layout.run(folder_three, config_three, workers=3)
    assert folder_one.lines_json.read_bytes() == folder_three.lines_json.read_bytes()


@pytest.mark.thread_unsafe
def test_run_with_a_config_of_another_pdf_names_analyze(tmp_path: Path) -> None:
    folder, config = _book(tmp_path)
    other_pdf = tmp_path / "other.pdf"
    other_pdf.write_bytes(b"%PDF-1.4 another book")
    with pytest.raises(InputFileError, match=r"pages\.json.*galley2epub analyze"):
        layout.run(folder, replace(config, pdf=other_pdf), workers=1)
    assert not folder.lines_json.exists()


@pytest.mark.thread_unsafe
def test_run_with_a_pages_json_of_another_pdf_names_analyze(tmp_path: Path) -> None:
    folder, config = _book(tmp_path)
    write_lines(folder.lines_json, LinesFile(source_pdf_sha256="0" * 64, pages=()))
    stale = folder.pages_json.read_text(encoding="utf-8").replace(
        hashlib.sha256(_PDF_BYTES).hexdigest(), "f" * 64
    )
    folder.pages_json.write_text(stale, encoding="utf-8")
    with pytest.raises(InputFileError, match=r"pages\.json.*galley2epub analyze"):
        layout.run(folder, config, workers=1)
    assert not folder.lines_json.exists()


@pytest.mark.thread_unsafe
def test_run_with_a_words_json_of_another_pdf_names_extract(tmp_path: Path) -> None:
    folder, config = _book(tmp_path)
    stale = folder.words_json.read_text(encoding="utf-8").replace(
        hashlib.sha256(_PDF_BYTES).hexdigest(), "f" * 64
    )
    folder.words_json.write_text(stale, encoding="utf-8")
    with pytest.raises(InputFileError, match=r"words\.json.*galley2epub extract"):
        layout.run(folder, config, workers=1)
    assert not folder.lines_json.exists()


@pytest.mark.thread_unsafe
def test_run_that_loses_a_word_raises_and_writes_no_lines_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder, config = _book(tmp_path)

    def layout_page_losing_a_word(
        page: PageWords, measures: BookMeasures | None
    ) -> PageLayout:
        return layout_page(replace(page, words=page.words[1:]), measures)

    monkeypatch.setattr(layout, "layout_page", layout_page_losing_a_word)
    with pytest.raises(FidelityError):
        layout.run(folder, config, workers=1)
    assert not folder.lines_json.exists()
