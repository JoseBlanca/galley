"""Tests of galley.layout (docs/specs/layout.md, section 8).

The unit tests lay out pages written by hand, with the book's measures
given in the test, and need no output of extract. The excerpt tests read
the session's run of each committed excerpt (tests/conftest.py), and the
whole_book tests run analyze, extract and layout on the six whole books;
both check that no word is lost, duplicated or moved to another page. The
exact regions of the reference pages are tested in tests/test_excerpts.py.
"""

import hashlib
import json
import math
from collections import Counter
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from galley import layout, wordlist
from galley.book_folder import BookFolder
from galley.config import BookConfig, Language, OcrMode, read_config
from galley.errors import (
    ExternalProgramError,
    FidelityBoundary,
    FidelityError,
    InputFileError,
)
from galley.fidelity import check_stage
from galley.layout import (
    BookMeasures,
    ReadLines,
    Rereading,
    Side,
    layout_page,
    layout_page_with_figures,
    layout_page_with_rereads,
    measure_book,
)
from galley.layout._reread import RegionReading, page_rereads
from galley.model import (
    BlockKind,
    Box,
    Figure,
    FigureKind,
    Line,
    LinesFile,
    PageInfo,
    PageKind,
    PageLayout,
    PagesFile,
    PageWords,
    Reread,
    RereadKind,
    TextSource,
    Word,
    WordsFile,
    folded_letters_and_digits,
    read_blocks,
    read_lines,
    read_words,
    words_after_rereads,
    write_lines,
    write_pages,
    write_words,
)
from galley.ocr import OCR_DPI


def _word(text: str, x0: float, top: float, x1: float, bottom: float) -> Word:
    return Word(text, Box(x0, top, x1, bottom), None)


def _texts(lines: tuple[Line, ...]) -> tuple[tuple[str, ...], ...]:
    return tuple(tuple(word.text for word in line.words) for line in lines)


def _page(index: int, words: tuple[Word, ...]) -> PageWords:
    return PageWords(
        index=index, text_source=TextSource.TEXT_LAYER, words=words, figures=()
    )


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
    figures = (
        Figure(
            box=Box(10, 20, 300, 400),
            image="images/p0002-01.png",
            dpi=300,
            kind=FigureKind.PLATE,
        ),
    )
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
    # 60. Each page has one more row whose last word hangs 15 pt past the
    # others, so its right side is not the commonest. A page of 5 rows,
    # 400 pt wide at 10, is not measured: the others have 15 rows or more.
    def ragged_page(index: int) -> PageWords:
        left = 50 if index % 2 == 0 else 60
        page = _column_page(index, left, 200 + index, 16)
        hanging = _full_row(16, left, 200 + index + 15, 100 + 16 * _PITCH)
        return replace(page, words=page.words + hanging)

    pages = (*(ragged_page(i) for i in range(20)), _column_page(20, 10, 400, 5))
    measures = measure_book(_words_file(pages))
    assert measures == BookMeasures(
        column_width=209.5,
        body_word_height=_ROW_HEIGHT,
        body_line_pitch=_PITCH,
        usual_left_edge=frozendict({0: 50.0, 1: 60.0}),
        cut_in_inset_left=None,
        cut_in_inset_right=None,
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
        cut_in_inset_left=None,
        cut_in_inset_right=None,
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
    # Pages 1, 3 and 5 hold only short rows, 100 pt from 90, under 0.8 of
    # the 150-pt column (the median of 200, 200, 200, 100, 100, 100). They
    # take the even pages' 50, not the median of every measured page's
    # commonest left edge, 70.
    short = tuple(
        _word(f"s{row}", 90, 100 + row * 12, 190, 108 + row * 12) for row in range(16)
    )
    pages = (
        *(_column_page(i, 50, 200, 16) for i in (0, 2, 4)),
        *(_page(i, short) for i in (1, 3, 5)),
    )
    measures = measure_book(_words_file(pages))
    assert measures is not None
    assert measures.usual_left_edge == frozendict({0: 50.0, 1: 50.0})


def test_book_without_a_wide_row_takes_the_median_commonest_left_edge() -> None:
    # On every page 8 rows start at its left edge and end 30 to 100 pt past
    # it, 10 pt apart, and 8 rows end 200 pt past it and start 100 to 170
    # pt past it: the column is 200 wide and no row is 160. Even pages
    # start at 50, odd at 60: both parities take the median of the pages'
    # commonest left edges, 55.
    def page(index: int) -> PageWords:
        left = 50 if index % 2 == 0 else 60
        starting = tuple(
            _word(
                f"s{row}",
                left,
                100 + row * _PITCH,
                left + 30 + 10 * row,
                108 + row * _PITCH,
            )
            for row in range(8)
        )
        ending = tuple(
            _word(
                f"e{row}",
                left + 100 + 10 * row,
                196 + row * _PITCH,
                left + 200,
                204 + row * _PITCH,
            )
            for row in range(8)
        )
        return _page(index, starting + ending)

    measures = measure_book(_words_file((page(0), page(1))))
    assert measures is not None
    assert measures.column_width == 200.0
    assert measures.usual_left_edge == frozendict({0: 55.0, 1: 55.0})


# The cut-in insets (layout spec section 3, "The book's measures")


def _inset_pages(insets: tuple[float, ...]) -> WordsFile:
    """Pages of 17 full rows of the column at 50, 200 wide, starting 0 to 2
    pt inside its left edge, each with 3 rows of `insets` more, rows that
    start that far inside the left edge and end at the right one."""
    pages = []
    for index in range(math.ceil(len(insets) / 3)):
        page_insets = insets[3 * index : 3 * index + 3]
        full = tuple(
            word
            for row in range(17)
            for word in _full_row(row, 50 + row % 3, 200 - row % 3, row * _PITCH)
        )
        inset_rows = tuple(
            word
            for row, inset in enumerate(page_insets, start=17)
            for word in (
                _word(
                    f"i{row}", 50 + inset, row * _PITCH, 50 + inset + 40, 8 + row * 12
                ),
                _word(f"j{row}", 50 + inset + 44, row * _PITCH, 250, 8 + row * _PITCH),
            )
        )
        pages.append(_page(index, full + inset_rows))
    return _words_file(tuple(pages))


def test_cut_in_inset_of_60_rows_60_pt_in_is_measured() -> None:
    measures = measure_book(_inset_pages((60.0,) * 60))
    assert measures is not None
    assert (measures.cut_in_inset_left, measures.cut_in_inset_right) == (60.0, None)


def test_cut_in_inset_with_as_many_rows_8_pt_further_in_is_none() -> None:
    measures = measure_book(_inset_pages((30.0,) * 30 + (38.0,) * 30))
    assert measures is not None
    assert measures.cut_in_inset_left is None


@pytest.mark.parametrize(("rows", "inset"), [(9, None), (10, 60.0)])
def test_cut_in_inset_needs_10_rows_at_its_peak(rows: int, inset: float | None) -> None:
    measures = measure_book(_inset_pages((60.0,) * rows))
    assert measures is not None
    assert measures.cut_in_inset_left == inset


@pytest.mark.parametrize(
    ("inset", "found"), [(29.9, None), (30.0, 30.0), (100.0, 100.0), (100.1, None)]
)
def test_cut_in_inset_is_looked_for_from_30_to_100_pt(
    inset: float, found: float | None
) -> None:
    measures = measure_book(_inset_pages((inset,) * 30))
    assert measures is not None
    assert measures.cut_in_inset_left == found


def test_cut_in_inset_takes_the_smaller_peak_within_2_pt_and_rounds_to_0_1_pt() -> None:
    # 59.97 rounds to 60.0, 4 tenths from 59.6: both peaks have every row
    # within 2 pt, and the tie goes to the smaller.
    measures = measure_book(_inset_pages((59.6,) * 10 + (59.97,) * 10))
    assert measures is not None
    assert measures.cut_in_inset_left == 59.6


# layout_page: outer margin notes and the running-head line (layout spec
# section 3, steps 1 to 3)

# The measures of the pages below: a column 200 pt wide at 50 on every
# page, rows 12 pt apart of words 8 pt high.
_MEASURES = BookMeasures(
    column_width=200.0,
    body_word_height=_ROW_HEIGHT,
    body_line_pitch=_PITCH,
    usual_left_edge=frozendict({0: 50.0, 1: 50.0}),
    cut_in_inset_left=None,
    cut_in_inset_right=None,
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


def _page_with_row_3_reaching_left(
    first: Word, second_x0: float, note: Word
) -> PageLayout:
    """A page of 20 full rows of the column at 50 whose row 3 (top 136) is
    `first`, then words from `second_x0` to the right edge, with `note`
    in the left margin."""
    rows = tuple(word for word in _rows(20) if not word.text.endswith("3"))
    row_3 = (
        first,
        _word("The", second_x0, 136, second_x0 + 40, 144),
        _word("idea", second_x0 + 44, 136, 250, 144),
    )
    return layout_page(_page(0, (*rows, *row_3, note)), _MEASURES)


def test_note_word_reaching_into_the_empty_indent_joins_its_margin_note() -> None:
    # "land." runs from 20 pt left of the edge, 50, to 7 pt right of it;
    # "The" starts 17 pt inside, more than the 12 pt pitch.
    result = _page_with_row_3_reaching_left(
        _word("land.", 30, 136, 57, 144), 67, _word("Free", 5, 136, 25, 144)
    )
    body, margin = _region_texts(result)
    assert body[3] == ("The", "idea")
    assert margin == (("Free", "land."),)


def test_note_word_reaching_into_the_column_joins_a_note_a_pitch_above() -> None:
    result = _page_with_row_3_reaching_left(
        _word("land.", 30, 136, 57, 144), 67, _word("Free", 5, 124, 25, 132)
    )
    body, margin = _region_texts(result)
    assert body[3] == ("The", "idea")
    assert margin == (("Free",), ("land.",))


def test_word_reaching_left_stays_when_the_next_word_is_less_than_a_pitch_inside() -> (
    None
):
    # "The" starts 6 pt inside the edge: the column is not empty there.
    result = _page_with_row_3_reaching_left(
        _word("land.", 30, 136, 57, 144), 56, _word("Free", 5, 136, 25, 144)
    )
    body, margin = _region_texts(result)
    assert body[3] == ("land.", "The", "idea")
    assert margin == (("Free",),)


def test_word_reaching_left_stays_beside_a_margin_word_of_fewer_than_2_letters() -> (
    None
):
    # A list number hung outside the column, as Gierke's "44" on page 62.
    result = _page_with_row_3_reaching_left(
        _word("land.", 30, 136, 57, 144), 67, _word("44", 5, 136, 25, 144)
    )
    body, margin = _region_texts(result)
    assert body[3] == ("land.", "The", "idea")
    assert margin == (("44",),)


def test_word_reaching_left_stays_when_its_middle_is_1_pt_outside() -> None:
    result = _page_with_row_3_reaching_left(
        _word("land.", 40, 136, 58, 144), 67, _word("Free", 5, 136, 25, 144)
    )
    body, _ = _region_texts(result)
    assert body[3] == ("land.", "The", "idea")


def test_word_reaching_left_with_its_middle_exactly_2_pt_outside_moves() -> None:
    # Middle (30 + 66) / 2 = 48, 2 pt left of the edge at 50.
    result = _page_with_row_3_reaching_left(
        _word("land.", 30, 136, 66, 144), 67, _word("Free", 5, 136, 25, 144)
    )
    body, margin = _region_texts(result)
    assert body[3] == ("The", "idea")
    assert margin == (("Free", "land."),)


def test_word_reaching_left_with_its_middle_1_9_pt_outside_stays() -> None:
    # Middle (30 + 66.2) / 2 = 48.1, 1.9 pt left of the edge at 50.
    result = _page_with_row_3_reaching_left(
        _word("land.", 30, 136, 66.2, 144), 67, _word("Free", 5, 136, 25, 144)
    )
    body, _ = _region_texts(result)
    assert body[3] == ("land.", "The", "idea")


def test_word_reaching_left_alone_on_its_row_stays() -> None:
    # Gierke's page 123: "Stfoarm.", a note word and a body word read as one.
    rows = tuple(word for word in _rows(20) if not word.text.endswith("3"))
    alone = _word("land.", 30, 136, 57, 144)
    note = _word("Free", 5, 136, 25, 144)
    body, margin = _region_texts(layout_page(_page(0, (*rows, alone, note)), _MEASURES))
    assert body[3] == ("land.",)
    assert margin == (("Free",),)


@pytest.mark.parametrize(
    ("top", "bottom"),
    [(114.8, 122.8), (157.2, 165.2)],
    ids=["1.1 pitches above", "1.1 pitches below"],
)
def test_word_reaching_left_stays_with_the_note_more_than_a_pitch_away(
    top: float, bottom: float
) -> None:
    # "land." runs from 136 to 144; the note ends 13.2 pt above its top or
    # starts 13.2 pt below its bottom, 1.1 pitches of 12 pt.
    result = _page_with_row_3_reaching_left(
        _word("land.", 30, 136, 57, 144), 67, _word("Free", 5, top, 25, bottom)
    )
    body, _ = _region_texts(result)
    assert body[3] == ("land.", "The", "idea")


def test_word_reaching_left_stays_beside_a_margin_word_of_one_letter() -> None:
    # A margin word of one letter, as "U" on Kadesh's cover (page 0).
    result = _page_with_row_3_reaching_left(
        _word("land.", 30, 136, 57, 144), 67, _word("U", 5, 136, 25, 144)
    )
    body, margin = _region_texts(result)
    assert body[3] == ("land.", "The", "idea")
    assert margin == (("U",),)


def test_hung_semicolon_3_pt_outside_stays_in_its_body_line() -> None:
    result = _page_with_row_3_reaching_left(
        _word(";", 45.5, 136, 48.5, 144), 67, _word("Free", 5, 136, 25, 144)
    )
    body, _ = _region_texts(result)
    assert body[3] == (";", "The", "idea")


def test_note_word_reaching_into_the_right_margin_stays_in_its_body_line() -> None:
    # The rule is applied at the left edge only.
    rows = tuple(word for word in _rows(20) if not word.text.endswith("3"))
    row_3 = (
        _word("The", 50, 136, 150, 144),
        _word("own", 243, 136, 270, 144),  # middle 6.5 pt right of 250
    )
    note = _word("Free", 275, 136, 295, 144)
    result = layout_page(_page(0, (*rows, *row_3, note)), _MEASURES)
    body, margin = _region_texts(result)
    assert body[3] == ("The", "own")
    assert margin == (("Free",),)


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


def test_rows_with_margin_notes_joined_outnumbering_the_body_rows_keep_the_column() -> (
    None
):
    # 14 body rows from 50 to 250, then 16 rows whose note word at 12 to
    # 44 the text layer joined to the row (Gierke's endnotes). The common
    # left edges are 12 and 50; with the right edge 250, the pair 50-250
    # is the column's width, so the notes are margin words.
    joined = tuple(
        word
        for row in range(16)
        for word in (
            _word(f"note{row}", 12, 268 + row * _PITCH, 44, 276 + row * _PITCH),
            *_full_row(row + 14, 50, 200, 268 + row * _PITCH),
        )
    )
    result = layout_page(_page(0, (*_rows(14), *joined)), _MEASURES)
    texts = _region_texts(result)
    assert len(texts[0]) == 30
    assert all(not line[0].startswith("note") for line in texts[0])
    assert sum(len(region) for region in texts[1:]) == 16


def test_page_set_wider_than_the_book_keeps_its_line_ends_in_the_body() -> None:
    # Rows from 50 to 270 on a book whose column is 200 wide: the last
    # word, from 254, would be 4 pt outside the column 50-250.
    rows = tuple(
        word
        for row in range(16)
        for word in (
            *_full_row(row, 50, 200, 100 + row * _PITCH),
            _word(f"d{row}", 254, 100 + row * _PITCH, 270, 108 + row * _PITCH),
        )
    )
    result = layout_page(_page(0, rows), _MEASURES)
    (body,) = result.regions
    assert len(body.lines) == 16


def test_table_rows_outvoting_the_body_rows_do_not_move_the_column() -> None:
    # 20 table rows from 63 to 240 and 15 body rows from 50 to 250 (Domesday
    # page 28). The pair 50-250 is the column's width; "is" at 50 to 58
    # stays in the body.
    table = tuple(
        _word(f"t{row}", 63, 100 + row * _PITCH, 240, 108 + row * _PITCH)
        for row in range(20)
    )
    body = _rows(15, top=100 + 20 * _PITCH)
    alone = _word("is", 50, 100 + 35 * _PITCH, 58, 108 + 35 * _PITCH)
    result = layout_page(_page(0, (*table, *body, alone)), _MEASURES)
    (region,) = result.regions
    assert _texts(region.lines)[-1] == ("is",)


def test_page_with_2_wide_rows_takes_the_usual_left_edge() -> None:
    # Two wide rows start at 20; page 1's usual left edge is 50, so the
    # word at 20 to 44 on the first row is a margin word.
    rows = (
        _word("Note", 20, 100, 44, 108),
        *_full_row(0, 50, 200, 100),
        *_full_row(1, 20, 230, 112),
        _word("short", 50, 124, 120, 132),
    )
    result = layout_page(_page(1, rows), _MEASURES)
    assert _region_texts(result)[-1] == (("Note",),)


def test_word_with_an_inverted_box_is_in_one_region_only() -> None:
    # The model accepts a box whose x0 is right of its x1: (400, 130, 10,
    # 140) lies both 2 pt left of the column and 2 pt right of it.
    inverted = _word("odd", 400, 130, 10, 140)
    page = _page(0, (*_rows(20), inverted))
    result = layout_page(page, _MEASURES)
    texts = [
        word.text
        for region in result.regions
        for line in region.lines
        for word in line.words
    ]
    assert sorted(texts) == sorted(word.text for word in page.words)


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


def test_head_set_apart_by_median_top_above_a_tall_em_dash_is_a_running_head_region() -> (
    None
):
    # The head 1.6 pitches above the body by its words' median tops; the
    # body's first row holds an em dash boxed 10 pt taller than its words,
    # so the row's box top lies 0.77 pitch below the head's.
    head = _word("HEAD", 120, 100 - 1.6 * _PITCH, 180, 100 - 1.6 * _PITCH + 8)
    dash = _word("—", 116, 90, 118, 108)
    result = layout_page(_page(0, (head, dash, *_rows(20))), _MEASURES)
    head_region, body = result.regions
    assert _texts(head_region.lines) == (("HEAD",),)
    assert _texts(body.lines)[0] == ("a0", "—", "b0", "c0")
    assert len(body.lines) == 20


def test_head_row_top_leaves_out_a_page_number_boxed_low() -> None:
    # Domesday's page 159: "134" boxed 3 pt lower than the head's words,
    # which lie 1.31 pitches above the body; with "134" in the median the
    # gap is 1.18 pitches.
    head = (_word("134", 50, 83, 65, 91), _word("HEAD", 120, 80, 180, 88))
    result = layout_page(
        _page(0, (*head, *_rows(20, top=80 + 1.31 * _PITCH))), _MEASURES
    )
    head_region, body = result.regions
    assert _texts(head_region.lines) == (("134", "HEAD"),)
    assert len(body.lines) == 20


def test_skewed_head_whose_last_word_is_a_row_4_pt_lower_is_one_region_of_one_line() -> (
    None
):
    # Words 7 pt high: the date's centre lies below the head's bottom, so
    # it is a row of its own, 4 pt (a third of a pitch) lower. A speck
    # above the head stays a line of its own.
    speck = _word(";", 140, 60, 144, 66)
    date = _word("1170", 40, 84, 70, 91)
    head = _word("HEAD", 120, 80, 180, 87)
    result = layout_page(_page(0, (speck, date, head, *_rows(20))), _MEASURES)
    head_region, body = result.regions
    assert _texts(head_region.lines) == ((";",), ("1170", "HEAD"))
    assert head_region.lines[1].box == Box(40, 80, 180, 91)
    assert len(body.lines) == 20


def test_marks_row_between_head_and_body_is_passed_over_and_stays_in_the_body() -> None:
    head = _word("HEAD", 120, 80, 180, 88)
    marks = (_word("^", 130, 90, 134, 96), _word("_", 160, 90, 166, 96))
    result = layout_page(_page(0, (head, *marks, *_rows(20))), _MEASURES)
    head_region, body = result.regions
    assert _texts(head_region.lines) == (("HEAD",),)
    assert _texts(body.lines)[0] == ("^", "_")
    assert len(body.lines) == 21


def _hanging(text: str, row: int, gap: float = 9.0) -> Word:
    """A number 10 pt wide ending `gap` pt left of the column's edge, 50,
    beside row `row` of `_rows`."""
    top = 100 + row * _PITCH
    return _word(text, 50 - gap - 10, top, 50 - gap, top + 8)


def test_hanging_number_9_pt_left_of_a_line_stays_at_the_start_of_that_line() -> None:
    numbers = (_hanging("12", 3), _hanging("13", 4))
    result = layout_page(_page(0, (*_rows(20), *numbers)), _MEASURES)
    (body,) = result.regions
    assert _texts(body.lines)[3:5] == (
        ("12", "a3", "b3", "c3"),
        ("13", "a4", "b4", "c4"),
    )


def test_hanging_number_16_pt_left_of_a_line_is_a_margin_word() -> None:
    numbers = (_hanging("12", 3), _hanging("13", 4), _hanging("14", 5, 16.0))
    result = layout_page(_page(0, (*_rows(20), *numbers)), _MEASURES)
    assert _region_texts(result)[1:] == ((("14",),),)


def test_hanging_number_alone_on_its_page_is_a_margin_word() -> None:
    # A speck read as a digit beside a margin note (Gierke's page 160).
    result = layout_page(_page(0, (*_rows(20), _hanging("9", 3))), _MEASURES)
    assert _region_texts(result)[1:] == ((("9",),),)


def test_hanging_number_with_a_margin_word_before_its_line_is_a_margin_word() -> None:
    # A margin "—" between the number and the line (Domesday's page 39).
    dash = _word("—", 44, 124 + 3 * _PITCH - 24, 48, 124 + 3 * _PITCH - 16)
    numbers = (
        _word("16", 30, 136, 40, 144),
        _hanging("17", 4),
        _hanging("18", 5),
    )
    result = layout_page(_page(0, (*_rows(20), dash, *numbers)), _MEASURES)
    (body, *margins) = _region_texts(result)
    assert body[3] == ("a3", "b3", "c3")
    assert body[4][0] == "17"
    assert ("16", "—") in tuple(line for region in margins for line in region)


def test_hanging_number_split_by_the_ocr_hangs_whole() -> None:
    numbers = (
        _word("5", 33, 136, 36, 144),
        _word("1", 37, 136, 41, 144),
        _hanging("52", 4),
    )
    result = layout_page(_page(0, (*_rows(20), *numbers)), _MEASURES)
    (body,) = result.regions
    assert _texts(body.lines)[3] == ("5", "1", "a3", "b3", "c3")


def test_hanging_number_on_the_head_row_is_a_margin_word() -> None:
    head = _word("HEAD", 50, 80, 110, 88)
    number = _word("12", 31, 80, 41, 88)
    numbers = (_hanging("13", 3), _hanging("14", 4))
    result = layout_page(_page(0, (head, number, *numbers, *_rows(20))), _MEASURES)
    assert _region_texts(result)[0] == (("HEAD",),)
    assert _region_texts(result)[2:] == ((("12",),),)


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


def _note_row(texts: tuple[str, ...], top: float) -> tuple[Word, ...]:
    """A row of small words `texts`, 30 pt wide and 4 pt apart from 50."""
    return tuple(
        _word(text, 50 + 34 * place, top, 80 + 34 * place, top + _SMALL_HEIGHT)
        for place, text in enumerate(texts)
    )


def test_gapless_band_starts_at_a_small_row_opening_with_a_note_marker() -> None:
    note = _note_row(("1", "Ibid.", "29."), _LAST_BODY_TOP + _PITCH)
    after = _small_rows(3, _LAST_BODY_TOP + _PITCH + 9)
    result = layout_page(_page(0, (*_rows(20), *note, *after)), _MEASURES)
    body, band = result.regions
    assert len(body.lines) == 20
    assert _texts(band.lines) == (("1", "Ibid.", "29."), ("n0",), ("n1",), ("n2",))


def test_gapless_band_does_not_start_at_a_marker_below_a_small_row() -> None:
    # A small row with no gap above it, then a note "2 Ibid." among small
    # rows, as a marker inside notes in two columns (Kadesh's page 14).
    above = _small_rows(1, _LAST_BODY_TOP + _PITCH)
    note = _note_row(("2", "Ibid.", "29."), _LAST_BODY_TOP + _PITCH + 9)
    after = _small_rows(3, _LAST_BODY_TOP + _PITCH + 18)
    result = layout_page(_page(0, (*_rows(20), *above, *note, *after)), _MEASURES)
    (body,) = result.regions
    assert len(body.lines) == 25


def test_gapless_band_starts_at_a_marker_below_a_speck() -> None:
    # Domesday's page 406: a speck between the text and its note.
    speck = _word("•", 140, _LAST_BODY_TOP + _PITCH, 142, _LAST_BODY_TOP + _PITCH + 3)
    note = _note_row(("1", "Ibid.", "29."), _LAST_BODY_TOP + _PITCH + 6)
    after = _small_rows(3, _LAST_BODY_TOP + _PITCH + 15)
    result = layout_page(_page(0, (*_rows(20), speck, *note, *after)), _MEASURES)
    body, band = result.regions
    assert len(body.lines) == 21
    assert _texts(band.lines)[0] == ("1", "Ibid.", "29.")


def test_gapless_band_does_not_start_at_a_row_of_numbers() -> None:
    numbers = _note_row(("35", "52", "26"), _LAST_BODY_TOP + _PITCH)
    after = _small_rows(3, _LAST_BODY_TOP + _PITCH + 9)
    result = layout_page(_page(0, (*_rows(20), *numbers, *after)), _MEASURES)
    (body,) = result.regions
    assert len(body.lines) == 24


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


def test_prose_row_with_a_word_across_the_strip_above_the_columns_stays_one_line() -> (
    None
):
    # The prose row's word "across" runs from 104 to 170 over the strip
    # (146.7 to 152.7); its middle, 137, is more than 6 pt from the strip's,
    # so the row is compatible, but it is not between two open rows. A row
    # with a word on the left only, below the columns, stays a row too.
    prose = (
        _word("prose", 50, 88, 100, 96),
        _word("across", 104, 88, 170, 96),
        _word("end", 174, 88, 250, 96),
    )
    after = _word("alone", 50, 100 + 10 * _PITCH, 120, 108 + 10 * _PITCH)
    result = layout_page(_page(0, (*prose, *_two_column_rows(10), after)), _MEASURES)
    assert _region_texts(result) == (
        (("prose", "across", "end"),),
        tuple((f"L{row}",) for row in range(10)),
        tuple((f"R{row}",) for row in range(10)),
        (("alone",),),
    )


def test_band_row_with_a_word_over_the_gutter_at_the_runs_edge_joins_the_run() -> None:
    # The band's first row has "Ori-" from 120 to 152 over the strip, its
    # middle 136 more than 6 pt from the strip's (Kadesh page 8); it
    # starts the run in the band, so its words go to the two columns.
    top = _LAST_BODY_TOP + 1.5 * _PITCH
    first = (
        _word("L0", 50, top, 110, top + 5.6),
        _word("Ori-", 120, top, 152, top + 5.6),
        _word("R0", 160, top, 250, top + 5.6),
    )
    band = _two_column_rows(3, top=top + 9, height=_SMALL_HEIGHT, pitch=9.0)
    result = layout_page(_page(0, (*_rows(20), *first, *band)), _MEASURES)
    assert _region_texts(result)[1:] == (
        (("L0", "Ori-"), *((f"L{row}",) for row in range(3))),
        (("R0",), *((f"R{row}",) for row in range(3))),
    )


def test_word_across_the_middle_of_the_gutter_ends_the_run() -> None:
    # Row 5 holds one word from 140 to 160: its middle is the strip's. Two
    # runs of 5 open rows are too short to cut.
    rows = tuple(
        word for word in _two_column_rows(11) if word.text not in {"L5", "R5"}
    ) + (_word("X5", 140, 100 + 5 * _PITCH, 160, 108 + 5 * _PITCH),)
    result = layout_page(_page(0, rows), _MEASURES)
    (body,) = result.regions
    assert len(body.lines) == 11


def test_3_band_rows_with_the_gutter_at_the_middle_are_two_band_columns() -> None:
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


def test_drop_capital_beside_two_columns_goes_to_the_left_column() -> None:
    # Rows 0 and 1 of the left column start at 75, beside a capital from
    # 50 to 70 and 100.5 to 124.5; the right column's first line, from 98,
    # is higher than the left's, from 100, and overlaps the capital too.
    words = tuple(
        replace(word, box=replace(word.box, x0=75))
        if word.text in {"L0", "L1"}
        else replace(word, box=replace(word.box, top=98, bottom=106))
        if word.text == "R0"
        else word
        for word in _two_column_rows(10)
    )
    capital = _word("T", 50, 100.5, 70, 124.5)
    result = layout_page(_page(0, (capital, *words)), _MEASURES)
    left, right = result.regions
    assert _texts(left.lines)[:2] == (("T", "L0"), ("L1",))
    assert _texts(right.lines)[0] == ("R0",)


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


def test_regions_are_head_body_columns_body_margins_by_top_then_band() -> None:
    # A head; 10 two-column rows, then 10 full rows; a right margin note at
    # the top, a left and a right one level with each other lower down; 3
    # band rows.
    words = (
        _word("Head", 120, 82, 180, 90),
        *_two_column_rows(10),
        *_rows(10, top=220),
        _word("Early", 256, 100, 290, 108),
        _word("Left", 20, 232, 44, 240),
        _word("Right", 256, 232, 290, 240),
        *_small_rows(3, 220 + 9 * _PITCH + 1.5 * _PITCH),
    )
    result = layout_page(_page(0, words), _MEASURES)
    assert _region_texts(result) == (
        (("Head",),),
        tuple((f"L{row}",) for row in range(10)),
        tuple((f"R{row}",) for row in range(10)),
        tuple((f"a{row}", f"b{row}", f"c{row}") for row in range(10)),
        (("Early",),),
        (("Left",),),
        (("Right",),),
        (("n0",), ("n1",), ("n2",)),
    )


# Boundary cases of the band, the columns and the drop capital


def _rows_of_height(count: int, top: float, height: float) -> tuple[Word, ...]:
    return tuple(
        _word(f"n{row}", 50, top + row * 9, 250, top + row * 9 + height)
        for row in range(count)
    )


@pytest.mark.parametrize(("share", "regions"), [(0.8, 2), (0.9, 1)])
def test_band_rows_are_small_at_0_8_of_the_body_height_and_not_at_0_9(
    share: float, regions: int
) -> None:
    band = _rows_of_height(5, _LAST_BODY_TOP + 1.5 * _PITCH, share * _ROW_HEIGHT)
    result = layout_page(_page(0, (*_rows(20), *band)), _MEASURES)
    assert len(result.regions) == regions


@pytest.mark.parametrize(("gap", "regions"), [(1.05, 1), (1.15, 2)])
def test_band_needs_a_gap_of_1_1_pitches_above_it(gap: float, regions: int) -> None:
    band = _small_rows(5, _LAST_BODY_TOP + gap * _PITCH)
    result = layout_page(_page(0, (*_rows(20), *band)), _MEASURES)
    assert len(result.regions) == regions


def test_2_band_rows_with_a_gutter_at_the_middle_stay_rows() -> None:
    band = _two_column_rows(
        2, top=_LAST_BODY_TOP + 1.5 * _PITCH, height=_SMALL_HEIGHT, pitch=9.0
    )
    result = layout_page(_page(0, (*_rows(20), *band)), _MEASURES)
    assert _region_texts(result)[1:] == ((("L0", "R0"), ("L1", "R1")),)


def test_8_rows_with_an_empty_strip_at_the_middle_are_two_columns() -> None:
    result = layout_page(_page(0, _two_column_rows(8)), _MEASURES)
    assert len(result.regions) == 2


def test_body_gutter_20_pt_off_the_middle_is_still_cut() -> None:
    # Left words end at 126 and right words start at 134: the gutter's
    # middle is at 129.7, 20.3 pt left of the column's middle. The test of
    # the gutter's place is the band's only.
    rows = tuple(
        word
        for row in range(10)
        for word in (
            _word(f"L{row}", 50, 100 + row * _PITCH, 126, 108 + row * _PITCH),
            _word(f"R{row}", 134, 100 + row * _PITCH, 250, 108 + row * _PITCH),
        )
    )
    result = layout_page(_page(0, rows), _MEASURES)
    assert len(result.regions) == 2


def test_strip_open_only_in_the_outer_third_is_no_gutter() -> None:
    # Words end at 58 and start at 72: the only empty strip lies in the
    # left third of the column, 50 to 116.7.
    rows = tuple(
        word
        for row in range(10)
        for word in (
            _word(f"L{row}", 50, 100 + row * _PITCH, 58, 108 + row * _PITCH),
            _word(f"R{row}", 72, 100 + row * _PITCH, 250, 108 + row * _PITCH),
        )
    )
    result = layout_page(_page(0, rows), _MEASURES)
    assert len(result.regions) == 1


def test_rows_on_one_side_of_the_gutter_only_are_not_cut() -> None:
    # 10 open rows, a full row that blocks the strip, then 10 rows with a
    # word on the left only: the first run is cut, the second has no open
    # row and stays rows.
    one_side = tuple(
        _word(f"S{row}", 50, 232 + row * _PITCH, 140, 240 + row * _PITCH)
        for row in range(10)
    )
    words = (*_two_column_rows(10), *_full_row(10, 50, 200, 220), *one_side)
    result = layout_page(_page(0, words), _MEASURES)
    assert _region_texts(result)[2] == (
        ("a10", "b10", "c10"),
        *((f"S{row}",) for row in range(10)),
    )
    assert len(result.regions) == 3


def test_two_words_across_the_strip_block_the_row() -> None:
    # Row 5 has words from 130 to 148 and 151 to 175, both across the strip
    # 146.7 to 152.7, each with its middle more than 6 pt from 149.7. The
    # row blocks; two runs of 5 open rows are too short to cut.
    rows = tuple(
        word for word in _two_column_rows(11) if word.text not in {"L5", "R5"}
    ) + (
        _word("x", 130, 100 + 5 * _PITCH, 148, 108 + 5 * _PITCH),
        _word("y", 151, 100 + 5 * _PITCH, 175, 108 + 5 * _PITCH),
    )
    result = layout_page(_page(0, rows), _MEASURES)
    assert len(result.regions) == 1


def test_word_over_the_gutter_goes_to_the_column_of_its_middle() -> None:
    # "over", from 140 to 175, has its middle at 157.5, right of the
    # gutter's 149.7 and more than 6 pt from it: the row stays in the run
    # and the word goes to the right column.
    rows = tuple(
        word for word in _two_column_rows(11) if word.text not in {"L5", "R5"}
    ) + (_word("over", 140, 100 + 5 * _PITCH, 175, 108 + 5 * _PITCH),)
    result = layout_page(_page(0, rows), _MEASURES)
    left, right = result.regions
    assert ("over",) in _texts(right.lines)
    assert ("over",) not in _texts(left.lines)


def test_word_twice_the_body_height_at_the_left_edge_is_no_drop_capital() -> None:
    # 16 pt tall, beside rows 2 and 3 at 100 and 112: it is grouped with
    # them as the skeleton groups words, into one line.
    above = _rows(2, top=76)
    beside = tuple(
        word
        for row in (2, 3)
        for word in (
            _word(f"a{row}", 75, 76 + row * _PITCH, 130, 84 + row * _PITCH),
            _word(f"b{row}", 140, 76 + row * _PITCH, 250, 84 + row * _PITCH),
        )
    )
    tall = _word("T", 50, 100, 70, 116)
    result = layout_page(
        _page(0, (*above, tall, *beside, *_rows(16, top=124))), _MEASURES
    )
    (body,) = result.regions
    assert _texts(body.lines)[2] == ("T", "a2", "a3", "b2", "b3")


def test_line_starting_left_of_the_capitals_middle_does_not_receive_it() -> None:
    # The capital runs from 50 to 70 (middle 60), 100 to 124. Row 0 starts
    # at 55 and row 1 at 75: only row 1 is beside it.
    rows = (
        _word("x0", 55, 100, 130, 108),
        _word("y0", 140, 100, 250, 108),
        _word("x1", 75, 112, 130, 120),
        _word("y1", 140, 112, 250, 120),
    )
    capital = _word("T", 50, 100, 70, 124)
    result = layout_page(_page(0, (capital, *rows, *_rows(16, top=124))), _MEASURES)
    (body,) = result.regions
    assert _texts(body.lines)[:2] == (("x0", "y0"), ("T", "x1", "y1"))


# The fidelity check at the layout boundary


# layout_page: Stubbs' cut-in notes (layout spec section 3, step 2b)

_CUT_IN_MEASURES = replace(_MEASURES, cut_in_inset_left=60.0, cut_in_inset_right=60.0)


def _row_top(row: int) -> float:
    return 100 + row * _PITCH


def _cut_row(row: int, start: float = 110) -> tuple[Word, ...]:
    """Row `row` of the column of `_MEASURES`, its words from `start`, by
    default 110, 60 pt inside the left edge at 50, to the right edge."""
    top = _row_top(row)
    return (
        _word(f"d{row}", start, top, start + 65, top + 8),
        _word(f"e{row}", start + 69, top, 250, top + 8),
    )


def _note_words(
    row: int, words: tuple[tuple[str, float, float], ...]
) -> tuple[Word, ...]:
    """The words (text, left side, right side) on row `row`."""
    top = _row_top(row)
    return tuple(_word(text, x0, top, x1, top + 8) for text, x0, x1 in words)


_CHARACTER_OF_HENRY = (("Character", 55, 80), ("of", 82, 88), ("Henry", 90, 102))


def _cut_in_page(
    rows: dict[int, tuple[Word, ...]], measures: BookMeasures = _CUT_IN_MEASURES
) -> PageLayout:
    """A page of 20 full rows of the column of `_MEASURES`, but for the
    rows of `rows`."""
    full = tuple(word for word in _rows(20) if int(word.text[1:]) not in rows)
    return layout_page(
        _page(0, (*full, *(word for words in rows.values() for word in words))),
        measures,
    )


def test_cut_in_note_beside_shortened_rows_is_a_margin_region() -> None:
    result = _cut_in_page(
        {
            10: _cut_row(10),
            11: (*_note_words(11, _CHARACTER_OF_HENRY), *_cut_row(11)),
            12: _cut_row(12),
        }
    )
    body, margin = _region_texts(result)
    assert body[10:13] == (("d10", "e10"), ("d11", "e11"), ("d12", "e12"))
    assert len(body) == 20
    assert margin == (("Character", "of", "Henry"),)


@pytest.mark.parametrize(("start", "margin"), [(113, 1), (114, 0)])
def test_cut_in_row_starts_within_3_pt_of_the_inset(start: float, margin: int) -> None:
    rows = {
        10: _cut_row(10, start),
        11: (*_note_words(11, _CHARACTER_OF_HENRY), *_cut_row(11)),
        12: _cut_row(12, start),
    }
    assert len(_cut_in_page(rows).regions) == 1 + margin


def test_cut_in_note_stays_in_the_body_without_a_cut_in_inset() -> None:
    rows = {
        10: _cut_row(10),
        11: (*_note_words(11, _CHARACTER_OF_HENRY), *_cut_row(11)),
        12: _cut_row(12),
    }
    (body,) = _region_texts(_cut_in_page(rows, _MEASURES))
    assert body[11] == ("Character", "of", "Henry", "d11", "e11")


def test_cut_in_word_at_the_inset_after_a_4_pt_gap_makes_no_cut_row() -> None:
    # "Henry" ends at 106, 4 pt short of the word at the inset: row 11 is
    # not cut, and rows 10 and 12, 2 pitches apart, are no chain.
    rows = {
        10: _cut_row(10),
        11: (
            *_note_words(
                11, (("Character", 55, 80), ("of", 82, 88), ("Henry", 90, 106))
            ),
            *_cut_row(11),
        ),
        12: _cut_row(12),
    }
    (body,) = _region_texts(_cut_in_page(rows))
    assert body[11] == ("Character", "of", "Henry", "d11", "e11")


def test_cut_in_rows_2_pitches_apart_are_no_chain() -> None:
    rows = {
        10: _cut_row(10),
        11: _note_words(11, _CHARACTER_OF_HENRY),
        12: _cut_row(12),
    }
    (body,) = _region_texts(_cut_in_page(rows))
    assert body[11] == ("Character", "of", "Henry")


def test_cut_in_full_line_at_the_end_of_a_chain_keeps_its_words() -> None:
    # Row 13 is a full line with a 9-pt space before the word at the inset:
    # a cut row, but not shortened, so the zone ends at row 12.
    top = _row_top(13)
    rows = {
        10: _cut_row(10),
        11: (*_note_words(11, _CHARACTER_OF_HENRY), *_cut_row(11)),
        12: _cut_row(12),
        13: (_word("a13", 50, top, 101, top + 8), *_cut_row(13)),
    }
    body, margin = _region_texts(_cut_in_page(rows))
    assert body[13] == ("a13", "d13", "e13")
    assert margin == (("Character", "of", "Henry"),)


def test_cut_in_speck_at_the_inset_spanning_a_quarter_of_the_column_is_no_cut_row() -> (
    None
):
    # Row 12's words from ";" span 50 pt, a quarter of the column: had it
    # been cut, the zone would run from row 10 to row 12 and take row 11's
    # note.
    top = _row_top(12)
    rows = {
        10: _cut_row(10),
        11: (*_note_words(11, _CHARACTER_OF_HENRY), *_cut_row(11)),
        12: (_word(";", 110, top, 113, top + 8), _word("end", 120, top, 160, top + 8)),
    }
    (body,) = _region_texts(_cut_in_page(rows))
    assert body[11] == ("Character", "of", "Henry", "d11", "e11")


def test_cut_in_zone_of_one_shortened_row_takes_a_note_word_1_pt_below_it() -> None:
    # Rows 10 and 11 are cut; only row 11 is shortened, so the zone is row
    # 11, from 232 to 240. "accession.", a row of its own, has its middle
    # at 240.75, inside the zone and its 1 pt; row 10's "of" is outside it.
    top = _row_top(11)
    rows = {
        10: (*_note_words(10, (("of", 55, 70),)), *_cut_row(10)),
        11: (*_cut_row(11), _word("accession.", 55, top + 4.5, 100, top + 13)),
    }
    body, margin = _region_texts(_cut_in_page(rows))
    assert body[10] == ("of", "d10", "e10")
    assert margin == (("accession.",),)


@pytest.mark.parametrize(
    ("his_right", "margin"),
    [
        (86, (("Character", "of", "Henry"),)),
        (85, (("as", "his"), ("Character", "of", "Henry"))),
    ],
)
def test_cut_in_zone_keeps_its_words_within_5_pt_of_a_body_word(
    his_right: float, margin: tuple[tuple[str, ...], ...]
) -> None:
    # A row of its own at 226, inside the zone from row 10 to row 12, reads
    # "as his issued": "issued" ends past the strip, a body word. "his"
    # 4 pt short of it stays, and so then does "as", 4 pt short of "his";
    # 5 pt short, both move (Stubbs' page 33, mirrored).
    rows = {
        10: _cut_row(10),
        11: (*_note_words(11, _CHARACTER_OF_HENRY), *_cut_row(11)),
        12: _cut_row(12),
    }
    sentence = (
        _word("as", 55, 226, his_right - 20, 234),
        _word("his", his_right - 16, 226, his_right, 234),
        _word("issued", 90, 226, 130, 234),
    )
    page = _page(
        0,
        (
            *(word for word in _rows(20) if int(word.text[1:]) not in rows),
            *(word for words in rows.values() for word in words),
            *sentence,
        ),
    )
    _, *margins = _region_texts(layout_page(page, _CUT_IN_MEASURES))
    assert tuple(margins) == (margin,)


def test_cut_in_lone_shortened_row_is_no_zone() -> None:
    # Row 11 is cut and shortened, but rows 10 and 12 are full lines: a
    # chain of one cut row, so "accession.", a row of its own beside row
    # 11, stays in the body.
    top = _row_top(11)
    rows: dict[int, tuple[Word, ...]] = {
        11: (*_cut_row(11), _word("accession.", 55, top + 4.5, 100, top + 13))
    }
    (body,) = _region_texts(_cut_in_page(rows))
    assert ("accession.",) in body


def test_cut_in_zone_keeps_a_word_ending_3_pt_short_of_the_inset() -> None:
    # "Henry", a row of its own inside the zone, ends at 107, 3 pt short of
    # the inset at 110: not 4, so it stays in the body.
    top = _row_top(11)
    rows = {
        10: _cut_row(10),
        11: (
            *_note_words(11, (("Character", 55, 80), ("of", 82, 88))),
            *_cut_row(11),
            _word("Henry", 90, top + 4.5, 107, top + 13),
        ),
        12: _cut_row(12),
    }
    body, margin = _region_texts(_cut_in_page(rows))
    assert ("Henry",) in body
    assert margin == (("Character", "of"),)


def test_cut_in_note_at_the_right_is_a_margin_region() -> None:
    # The mirror of the first case: body words from the left edge to 190,
    # 60 pt inside the right edge at 250, and the note right of them.
    def shortened(row: int) -> tuple[Word, ...]:
        top = _row_top(row)
        return (
            _word(f"d{row}", 50, top, 120, top + 8),
            _word(f"e{row}", 124, top, 190, top + 8),
        )

    rows = {
        10: shortened(10),
        11: (
            *shortened(11),
            *_note_words(11, (("His", 200, 215), ("family", 217, 245))),
        ),
        12: shortened(12),
    }
    body, margin = _region_texts(_cut_in_page(rows))
    assert body[11] == ("d11", "e11")
    assert margin == (("His", "family"),)


def _words_file(pages: tuple[PageWords, ...]) -> WordsFile:
    return WordsFile(source_pdf_sha256="0" * 64, pages=pages, removals=())


def test_fidelity_check_passes_on_layout_pages() -> None:
    pages = (_page(0, _PAGE_WORDS), _page(1, ()))
    lines = LinesFile(
        source_pdf_sha256="0" * 64,
        pages=tuple(layout_page(p, _MEASURES) for p in pages),
        rereads=(),
    )
    check_stage(FidelityBoundary.LAYOUT, _words_file(pages), lines)


def test_fidelity_check_fails_when_a_word_is_dropped_from_a_line() -> None:
    page = layout_page(_page(0, _PAGE_WORDS), None)
    region = page.regions[0]
    first_line = region.lines[0]
    dropped = replace(first_line, words=first_line.words[:1])
    page = replace(page, regions=(replace(region, lines=(dropped, *region.lines[1:])),))
    lines = LinesFile(source_pdf_sha256="0" * 64, pages=(page,), rereads=())
    with pytest.raises(FidelityError) as raised:
        check_stage(
            FidelityBoundary.LAYOUT, _words_file((_page(0, _PAGE_WORDS),)), lines
        )
    assert raised.value.missing == frozendict({"beta": 1})
    assert raised.value.invented == frozendict()


# layout_page_with_rereads: re-reading small print (docs/specs/reocr.md,
# sections 3 and 4). The page is rendered as a white image with ink drawn
# where a test needs it, and Tesseract's words are written in the test, as
# a reader that gives them whatever crop it is given: no PDF, no Tesseract.

# A page of 500 by 700 pt at 300 dpi.
_PAGE_PIXELS = (round(500 * OCR_DPI / 72), round(700 * OCR_DPI / 72))


def _render_with_ink(*ink: Box) -> Callable[[int], Image.Image]:
    """A render of every page: white, black in each box of `ink`."""

    def render(_: int) -> Image.Image:
        image = Image.new("L", _PAGE_PIXELS, 255)
        draw = ImageDraw.Draw(image)
        for box in ink:
            draw.rectangle(
                tuple(
                    round(value * OCR_DPI / 72)
                    for value in (box.x0, box.top, box.x1, box.bottom)
                ),
                fill=0,
            )
        return image

    return render


def _no_render(page_index: int) -> Image.Image:
    msg = f"page {page_index} was rendered, and no region of it is to be read"
    raise AssertionError(msg)


def _reader(*lines: tuple[Word, ...]) -> ReadLines:
    """Tesseract standing in: `lines` for every crop read."""

    def read(
        image: Image.Image, *, origin: tuple[float, float], psm: int
    ) -> tuple[tuple[Word, ...], ...]:
        del image, origin, psm
        return lines

    return read


def _no_reader(
    image: Image.Image, *, origin: tuple[float, float], psm: int
) -> tuple[tuple[Word, ...], ...]:
    del image, origin
    msg = f"Tesseract was run with psm {psm}, and no region is to be read"
    raise AssertionError(msg)


def _rereading(
    read_lines: ReadLines,
    *,
    render: Callable[[int], Image.Image] = _no_render,
    words: frozenset[str] = frozenset(),
    margin_note_sides: frozenset[Side] = frozenset(),
    footnote_bands: bool = False,
) -> Rereading:
    return Rereading(
        pdf=Path("book.pdf"),
        render=render,
        read_lines=read_lines,
        lower_case_words=words,
        margin_note_sides=margin_note_sides,
        footnote_bands=footnote_bands,
    )


def _ocr_word(text: str, x0: float, top: float, x1: float, bottom: float) -> Word:
    return Word(text, Box(x0, top, x1, bottom), 90.0)


def _assert_fidelity(
    page: PageWords, result: tuple[PageLayout, tuple[Reread, ...]]
) -> None:
    layout_of_page, records = result
    lines = LinesFile(
        source_pdf_sha256="0" * 64, pages=(layout_of_page,), rereads=records
    )
    check_stage(FidelityBoundary.LAYOUT, _words_file((page,)), lines)


# A left margin note the layer garbles, beside row 3, and Tesseract's
# reading of it, over the layer's words.
_GARBLED_NOTE = (_word("Mor", 10, 136, 25, 144), _word("al", 27, 136, 45, 144))
_NOTE_INK = Box(10, 136, 45, 144)
_MORAL_LESSONS = (
    _ocr_word("Moral", 9, 135, 30, 145),
    _ocr_word("lessons.", 31, 135, 46, 145),
)


def test_reread_margin_note_kept_puts_tesseract_words_in_its_margin_region() -> None:
    page = _page(0, (*_rows(20), *_GARBLED_NOTE))
    result = layout_page_with_rereads(
        page,
        _MEASURES,
        _rereading(
            _reader(_MORAL_LESSONS),
            render=_render_with_ink(_NOTE_INK),
            words=frozenset({"moral", "lessons"}),
            margin_note_sides=frozenset({Side.LEFT}),
        ),
    )
    layout_of_page, (record,) = result
    assert _region_texts(layout_of_page)[1:] == ((("Moral", "lessons."),),)
    assert len(_region_texts(layout_of_page)[0]) == 20
    assert (record.kind, record.kept) == (RereadKind.MARGIN_NOTE, True)
    assert (record.layer_words, record.ocr_words) == (_GARBLED_NOTE, _MORAL_LESSONS)
    assert (record.layer_score, record.ocr_score) == (-2, 2)
    _assert_fidelity(page, result)


def test_reread_margin_note_scoring_lower_keeps_the_layer_layout() -> None:
    page = _page(0, (*_rows(20), *_GARBLED_NOTE))
    layout_of_page, (record,) = layout_page_with_rereads(
        page,
        _MEASURES,
        _rereading(
            _reader((_ocr_word("Mxq", 9, 135, 46, 145),)),
            render=_render_with_ink(_NOTE_INK),
            words=frozenset({"mor", "al"}),
            margin_note_sides=frozenset({Side.LEFT}),
        ),
    )
    assert layout_of_page == layout_page(page, _MEASURES)
    assert record.kept is False


def test_reread_margin_of_a_side_without_notes_is_not_read() -> None:
    page = _page(0, (*_rows(20), *_GARBLED_NOTE))
    assert layout_page_with_rereads(
        page,
        _MEASURES,
        _rereading(
            _no_reader,
            margin_note_sides=frozenset({Side.RIGHT}),
            render=_render_with_ink(_NOTE_INK),
        ),
    ) == (layout_page(page, _MEASURES), ())


def test_reread_page_with_no_region_to_read_is_not_rendered() -> None:
    page = _page(0, (*_rows(20), *_GARBLED_NOTE))
    assert layout_page_with_rereads(page, _MEASURES, _rereading(_no_reader)) == (
        layout_page(page, _MEASURES),
        (),
    )


def test_reread_page_of_tesseract_words_is_not_read() -> None:
    page = replace(_page(0, (*_rows(20), *_GARBLED_NOTE)), text_source=TextSource.OCR)
    assert layout_page_with_rereads(
        page,
        _MEASURES,
        _rereading(_no_reader, margin_note_sides=frozenset({Side.LEFT})),
    ) == (layout_page(page, _MEASURES), ())


def _small_print_rows(layer: str) -> tuple[Word, ...]:
    """12 rows of 5 words of small type, 0.7 of the body word height, 10
    pt apart from top 110: the text layer's when `layer` is "x", each word
    "x" and its row and place, else Tesseract's, each a page number, 100
    plus ten times its row plus its place."""
    return tuple(
        Word(
            f"x{row}{place}" if layer == "x" else str(100 + 10 * row + place),
            Box(
                50 + place * 40,
                110 + row * 10,
                85 + place * 40,
                110 + row * 10 + _SMALL_HEIGHT,
            ),
            None if layer == "x" else 90.0,
        )
        for row in range(12)
        for place in range(5)
    )


def test_reread_small_print_page_kept_is_laid_out_from_tesseract_words() -> None:
    head = _word("Head", 120, 82, 180, 90)
    page = _page(0, (head, *_small_print_rows("x"), *_GARBLED_NOTE))
    result = layout_page_with_rereads(
        page,
        _MEASURES,
        _rereading(
            _reader(_small_print_rows("ocr")),
            render=_render_with_ink(_NOTE_INK),
            # Read whole, the page's margin and band are no regions of their
            # own: a second region would raise.
            margin_note_sides=frozenset({Side.LEFT}),
            footnote_bands=True,
        ),
    )
    layout_of_page, (record,) = result
    assert (record.kind, record.kept) == (RereadKind.SMALL_PRINT_PAGE, True)
    assert record.box.top == 91.0
    regions = _region_texts(layout_of_page)
    assert regions[0] == (("Head",),)
    assert regions[1] == tuple(
        tuple(str(100 + 10 * row + place) for place in range(5)) for row in range(12)
    )
    # The margin note lies under no word of Tesseract's: the layer's stays.
    assert regions[2:] == ((("Mor", "al"),),)
    _assert_fidelity(page, result)


_CUT_IN_NOTE = (("Charcter", 55, 80), ("of", 82, 88), ("Hnry", 90, 102))


def test_reread_cut_in_note_kept_puts_tesseract_words_in_its_margin_region() -> None:
    rows = {
        10: _cut_row(10),
        11: (*_note_words(11, _CUT_IN_NOTE), *_cut_row(11)),
        12: _cut_row(12),
    }
    full = tuple(word for word in _rows(20) if int(word.text[1:]) not in rows)
    page = _page(0, (*full, *(word for words in rows.values() for word in words)))
    top = _row_top(11)
    read = tuple(
        _ocr_word(text, x0, top, x1, top + 8) for text, x0, x1 in _CHARACTER_OF_HENRY
    )
    result = layout_page_with_rereads(
        page,
        _CUT_IN_MEASURES,
        _rereading(
            _reader(read),
            render=_render_with_ink(),
            words=frozenset({"character", "of", "henry"}),
        ),
    )
    layout_of_page, (record,) = result
    assert (record.kind, record.kept) == (RereadKind.CUT_IN_NOTE, True)
    assert record.box == Box(47, _row_top(10) - 30, 107, _row_top(12) + 8 + 30)
    body, margin = _region_texts(layout_of_page)
    assert body[10:13] == (("d10", "e10"), ("d11", "e11"), ("d12", "e12"))
    assert margin == (("Character", "of", "Henry"),)
    _assert_fidelity(page, result)


def _page_with_band() -> PageWords:
    return _page(0, (*_rows(20), *_small_rows(3, _LAST_BODY_TOP + 1.5 * _PITCH)))


def test_reread_footnote_band_kept_takes_the_band_place() -> None:
    page = _page_with_band()
    read = tuple(
        replace(word, text=text, ocr_confidence=90.0)
        for word, text in zip(
            _small_rows(3, _LAST_BODY_TOP + 1.5 * _PITCH),
            ("First", "second", "third."),
            strict=True,
        )
    )
    result = layout_page_with_rereads(
        page,
        _MEASURES,
        _rereading(
            _reader(read),
            render=_render_with_ink(),
            words=frozenset({"first", "second", "third"}),
            footnote_bands=True,
        ),
    )
    layout_of_page, (record,) = result
    assert (record.kind, record.kept) == (RereadKind.FOOTNOTE_BAND, True)
    body, band = _region_texts(layout_of_page)
    assert len(body) == 20
    assert band == (("First",), ("second",), ("third.",))
    _assert_fidelity(page, result)


def test_reread_footnote_band_across_a_figure_neither_reads_nor_replaces_its_words() -> (
    None
):
    # An in-page figure over the band's third row: the band's crop runs
    # across it, and Tesseract reads a word there (figures spec section 5).
    figure = Figure(
        box=Box(40.0, 362.0, 260.0, 380.0),
        image="images/figure-0000-1.png",
        dpi=300,
        kind=FigureKind.IN_PAGE,
    )
    page = replace(_page_with_band(), figures=(figure,))
    read = tuple(
        replace(word, text=text, ocr_confidence=90.0)
        for word, text in zip(
            _small_rows(3, _LAST_BODY_TOP + 1.5 * _PITCH),
            ("First", "second", "third."),
            strict=True,
        )
    )
    result = layout_page_with_figures(
        page,
        _MEASURES,
        _rereading(
            _reader(read),
            render=_render_with_ink(),
            words=frozenset({"first", "second", "third"}),
            footnote_bands=True,
        ),
    )
    layout_of_page, (record,) = result
    assert (record.kind, record.kept) == (RereadKind.FOOTNOTE_BAND, True)
    assert tuple(word.text for word in record.ocr_words) == ("First", "second")
    assert tuple(word.text for word in record.layer_words) == ("n0", "n1")
    body, band, figure_region = _region_texts(layout_of_page)
    assert len(body) == 20
    assert band == (("First",), ("second",))
    # The layer's word in the figure is the figure's region, not re-read.
    assert figure_region == (("n2",),)
    assert layout_of_page.regions[2].box == figure.box
    _assert_fidelity(page, result)


def test_reread_tesseract_failure_names_the_page_and_the_pdf() -> None:
    def failing(
        image: Image.Image, *, origin: tuple[float, float], psm: int
    ) -> tuple[tuple[Word, ...], ...]:
        del image, origin, psm
        msg = "tesseract (eng) printed no tsv"
        raise ExternalProgramError(msg)

    rereading = _rereading(failing, render=_render_with_ink(), footnote_bands=True)
    with pytest.raises(ExternalProgramError) as raised:
        layout_page_with_rereads(_page_with_band(), _MEASURES, rereading)
    assert "page 0 of book.pdf" in str(raised.value)
    assert "tesseract (eng) printed no tsv" in str(raised.value)
    assert isinstance(raised.value.__cause__, ExternalProgramError)


def test_reread_footnote_band_is_not_read_unless_asked() -> None:
    page = _page_with_band()
    assert layout_page_with_rereads(page, _MEASURES, _rereading(_no_reader)) == (
        layout_page(page, _MEASURES),
        (),
    )


@pytest.mark.thread_unsafe
def test_run_with_ocr_verify_rereads_and_with_trust_or_redo_needs_no_word_list(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The pages of `_book` have no region to read: layout reads the word
    # list for the margins' notes, renders nothing and records nothing.
    # With `redo` every page is Tesseract's already, and nothing is re-read.
    folder, config = _book(tmp_path)
    monkeypatch.setattr(wordlist, "DEFAULT_CACHE_DIR", tmp_path / "no-cache")
    monkeypatch.setenv("PATH", "")
    with pytest.raises(ExternalProgramError, match="tesseract"):
        layout.run(folder, config, workers=1)
    for ocr in (OcrMode.TRUST, OcrMode.REDO):
        layout.run(folder, replace(config, ocr=ocr), workers=1)
        assert read_lines(folder.lines_json).rereads == ()


# run, on a book folder of its own


_PDF_BYTES = b"%PDF-1.4 a stand-in: layout reads only its hash"
_PAGE_COUNT = 8


def _regions_page(index: int) -> PageWords:
    """A page with a running head, 16 body rows, a margin note beside row 3
    (on the right on even pages, on the left on odd ones) and a band of 3
    small rows, its words in an order that differs from page to page."""
    note = (
        _word("Note", 256, 136, 290, 144)
        if index % 2 == 0
        else _word("Note", 20, 136, 44, 144)
    )
    words = (
        _word("Head", 120, 82, 180, 90),
        *_rows(16),
        note,
        *_small_rows(3, 100 + 15 * _PITCH + 1.5 * _PITCH),
    )
    shift = index * 7 % len(words)
    return _page(index, words[shift:] + words[:shift])


def _book(root: Path) -> tuple[BookFolder, BookConfig]:
    """A book folder with pages.json and words.json of 8 pages written by
    hand, each page as `_regions_page` makes it, page 4 without words."""
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
                figure_boxes=(),
                blank_checked_by_ocr=False,
            )
            for index in range(_PAGE_COUNT)
        ),
        ocr_audit=None,
    )
    word_pages = tuple(
        _page(4, ()) if index == 4 else _regions_page(index)
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
    body = tuple((f"a{row}", f"b{row}", f"c{row}") for row in range(16))
    band = (("n0",), ("n1",), ("n2",))
    for page in written.pages[:4] + written.pages[5:]:
        assert _region_texts(page) == ((("Head",),), body, (("Note",),), band)


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
    write_lines(
        folder.lines_json, LinesFile(source_pdf_sha256="0" * 64, pages=(), rereads=())
    )
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

    # layout_page_with_rereads, which run calls, lays out with it.
    monkeypatch.setattr(
        "galley.layout._rereading.layout_page", layout_page_losing_a_word
    )
    with pytest.raises(FidelityError):
        layout.run(folder, config, workers=1)
    assert not folder.lines_json.exists()


# The fidelity check on the excerpts and the whole books (layout spec
# section 7)

_EXCERPTS_DIR = Path(__file__).parent / "fixtures" / "pdf"


def _assert_laid_out_in_regions(words: WordsFile, lines: LinesFile) -> None:
    """The fidelity check passes; each page's words, with their boxes, are
    those of the same page in words.json after the page's kept re-readings
    (reocr spec, section 4), since layout never moves a word to another
    page; and some page has more than one region: the book was measured
    and its pages cut."""
    check_stage(FidelityBoundary.LAYOUT, words, lines)
    assert tuple(page.index for page in lines.pages) == tuple(
        page.index for page in words.pages
    )
    for page_lines, page_words in zip(lines.pages, words.pages, strict=True):
        page_rereads = tuple(
            reread for reread in lines.rereads if reread.page_index == page_words.index
        )
        assert Counter(
            (word.text, word.box)
            for region in page_lines.regions
            for line in region.lines
            for word in line.words
        ) == Counter(
            (word.text, word.box)
            for word in words_after_rereads(page_words.words, page_rereads)
        )
    assert any(len(page.regions) > 1 for page in lines.pages)


@pytest.mark.parametrize(
    "excerpt", sorted(path.stem for path in _EXCERPTS_DIR.glob("*.pdf"))
)
def test_layout_of_an_excerpt_with_rereading_keeps_every_word(
    excerpt: str, excerpt_books: frozendict[str, BookFolder]
) -> None:
    # The session's one run of each excerpt (tests/conftest.py).
    folder = excerpt_books[excerpt]
    words, lines = read_words(folder.words_json), read_lines(folder.lines_json)
    _assert_laid_out_in_regions(words, lines)


def test_cut_in_insets_of_the_excerpts_are_stubbs_and_domesday_tables_only(
    excerpt_books: frozendict[str, BookFolder],
) -> None:
    # Layout spec section 3, "The book's measures": the Stubbs excerpt's
    # insets are 60.3 pt (17 rows) and 58.2 pt (13 rows); no other excerpt
    # has 10 rows at its peak and 4 times those beside it but `stubbs_heads`,
    # whose pages are all even, with their notes on the right, and whose
    # right inset is 58.0 pt (scripts/fetch_samples.py; 17 November 2026),
    # and `domesday_lists`, whose tables of page indices 156 to 158 end
    # their rows 58.8 pt inside the column, a peak the whole book's other
    # rows drown (18 November 2026).
    insets = {}
    for name, folder in excerpt_books.items():
        measures = measure_book(read_words(folder.words_json))
        assert measures is not None
        insets[name] = (measures.cut_in_inset_left, measures.cut_in_inset_right)
    found = {
        "stubbs_51_56-64": (60.3, 58.2),
        "stubbs_heads": (None, 58.0),
        "domesday_lists": (None, 58.8),
    }
    assert insets == {name: found.get(name, (None, None)) for name in excerpt_books}
    assert len(insets) == 20


def test_cut_in_notes_of_stubbs_page_57_are_margin_regions(
    excerpt_books: frozendict[str, BookFolder],
) -> None:
    # Layout spec section 8: excerpt page 2, book page index 57, has two
    # notes cut into the column at the left.
    lines = read_lines(excerpt_books["stubbs_51_56-64"].lines_json)
    page = next(page for page in lines.pages if page.index == 2)
    regions = [
        [" ".join(word.text for word in line.words) for line in region.lines]
        for region in page.regions
    ]
    assert regions[2:] == [["Character of", "Henry II."], ["His family", "policy."]]


# Re-reading on the excerpts (reocr spec, section 9, "Excerpt tests"). The
# session's run of each excerpt re-reads with the default config; a test
# that needs another config, or another number of workers, runs layout
# again on a copy of the excerpt's pages.json and words.json. An excerpt's
# book measures come from its own pages. The readings written here are
# those galley keeps with Tesseract 5.5.4, compared by the session with the
# page images on 17 November 2026 (where the print differs, a comment says
# so); the owner's check of every region read waits for task 6.2 of
# docs/plans/clean-text.md.


def _layout_again(
    folder: BookFolder,
    root: Path,
    change: Callable[[BookConfig], BookConfig],
    workers: int,
) -> BookFolder:
    """A book folder at `root` with the book.toml, pages.json and words.json
    of `folder`, and the lines.json that layout writes there with the
    config changed by `change`, in `workers` threads."""
    again = BookFolder(root)
    for source, copy in (
        (folder.book_toml, again.book_toml),
        (folder.pages_json, again.pages_json),
        (folder.words_json, again.words_json),
    ):
        copy.write_bytes(source.read_bytes())
    layout.run(again, change(read_config(again.book_toml)), workers=workers)
    return again


def _unchanged(config: BookConfig) -> BookConfig:
    return config


def _trusting(config: BookConfig) -> BookConfig:
    return replace(config, ocr=OcrMode.TRUST)


def _reading_footnotes(config: BookConfig) -> BookConfig:
    return replace(config, reread_footnotes=True)


def _kept_readings(lines: LinesFile) -> tuple[tuple[int, RereadKind, str], ...]:
    return tuple(
        (
            reread.page_index,
            reread.kind,
            " ".join(word.text for word in reread.ocr_words),
        )
        for reread in lines.rereads
        if reread.kept
    )


def _line_texts(page: PageLayout) -> tuple[tuple[str, ...], ...]:
    """Each region of `page` as the texts of its lines."""
    return tuple(
        tuple(" ".join(word.text for word in line.words) for line in region.lines)
        for region in page.regions
    )


def _lines_with_boxes(page: PageLayout) -> Counter[tuple[tuple[str, Box], ...]]:
    return Counter(
        tuple((word.text, word.box) for word in line.words)
        for region in page.regions
        for line in region.lines
    )


@pytest.mark.tesseract
@pytest.mark.usefixtures("tesseract_of_the_literals")
def test_reread_gierke_88_reads_its_four_margin_notes_the_last_one_the_layer_missed(
    excerpt_books: frozendict[str, BookFolder],
) -> None:
    # Excerpt page 2 is book page index 88. Its fourth note, "Medieval
    # Thought.", has no word in the layer: Tesseract's reading holds 2
    # known words and is kept (reocr spec, sections 3 and 8).
    lines = read_lines(excerpt_books["gierke_86-93_270-271"].lines_json)
    records = tuple(reread for reread in lines.rereads if reread.page_index == 2)
    assert (
        tuple((reread.kind, reread.kept) for reread in records)
        == ((RereadKind.MARGIN_NOTE, True),) * 4
    )
    assert records[-1].layer_words == ()
    assert _line_texts(lines.pages[2])[2:] == (
        ("Diverse", "methods."),
        # Printed "Unity of the move- ment."
        ("Unity of", "the move.", "ment,"),
        # Printed "Medieval and Antique- Modern Thought."
        ("Medieval", "and", "Antique-", "Modern", "Thought."),
        ("Medieval", "Thought."),
    )


@pytest.mark.tesseract
@pytest.mark.usefixtures("tesseract_of_the_literals")
def test_reread_stubbs_excerpt_keeps_tesseract_for_nine_of_its_cut_in_crops(
    excerpt_books: frozendict[str, BookFolder],
) -> None:
    # The excerpt's pages 1 to 9 are book page indices 56 to 64. The other
    # crops keep the layer: it read the note as well ("His family policy.",
    # page 2), or Tesseract's reading scores no higher. "Henry’s" (page 7)
    # and "Coronation." (page 8) are sure single words over no layer word
    # (reocr spec, section 3).
    lines = read_lines(excerpt_books["stubbs_51_56-64"].lines_json)
    assert _kept_readings(lines) == tuple(
        (page, RereadKind.CUT_IN_NOTE, text)
        for page, text in (
            (4, "Henry’s mismanage- ment of his children."),
            (5, "Plan of reform."),
            (5, "Terms of pacification,"),  # printed "pacification."
            (6, "Meaning of these terms,"),  # printed "terms."
            (7, "Arrival of Henry as successor to Stephen, 1154."),
            (7, "Henry’s"),  # printed "Henry's advisers."
            (8, "Bishop of Winchester. The Empress."),
            (8, "Coronation."),
            (9, "Destruction of castles."),
        )
    )
    # The notes as regions, with those whose layer reading stays on the same
    # pages ("Theobald and Becket.", page 8; "Banishment", page 9).
    assert tuple(_line_texts(lines.pages[page])[2:] for page in (5, 6, 7, 8, 9)) == (
        (("Plan of", "reform."), ("Terms of", "pacification,")),
        (("Meaning of", "these terms,"),),
        (
            ("Arrival of", "Henry as", "successor", "to Stephen,", "1154."),
            ("Henry’s",),
        ),
        (
            ("Bishop", "of Winchester."),
            ("The", "Empress."),
            ("Theobald", "and Becket."),
            ("Coronation.",),
        ),
        (("Banishment",), ("Destruction of", "castles.")),
    )


@pytest.mark.tesseract
@pytest.mark.usefixtures("tesseract_of_the_literals")
def test_reread_stubbs_59_note_keeps_no_layer_copy_beside_tesseract_reading(
    excerpt_books: frozendict[str, BookFolder],
) -> None:
    # Excerpt page 4, book page index 59: the note printed "Henry's
    # mismanage- ment of his children." The layer's garbled copy
    # "mentofhis", off Tesseract's "ment of his", is replaced by its likeness
    # to "ment" (reocr spec, section 4, rule (c)).
    lines = read_lines(excerpt_books["stubbs_51_56-64"].lines_json)
    assert _line_texts(lines.pages[4])[2] == (
        "Henry’s",
        "mismanage-",
        "ment of his",
        "children.",
    )


@pytest.mark.tesseract
@pytest.mark.thread_unsafe
def test_reread_stubbs_excerpt_leaves_every_line_without_a_replaced_word_as_trusted(
    excerpt_books: frozendict[str, BookFolder], tmp_path: Path
) -> None:
    # Each line of the run that trusts the layer, less the words that kept
    # records replaced, is a line of the run that re-reads less Tesseract's
    # words, in the same order and with the same boxes: the body lines
    # beside the notes, in rows outside the cut-in zones and right of the
    # inset alike, are as without re-reading, and a note line keeps the
    # layer words no record replaced. "advUers.", the layer's reading of
    # the note "advisers." that layout leaves at the end of a body line
    # (book page index 62, layout spec section 3, step 2b), stays there.
    folder = excerpt_books["stubbs_51_56-64"]
    reread = read_lines(folder.lines_json)
    trusted = read_lines(_layout_again(folder, tmp_path, _trusting, 1).lines_json)
    assert len(reread.pages) == len(trusted.pages) == 10
    for page_reread, page_trusted in zip(reread.pages, trusted.pages, strict=True):
        kept = tuple(
            record
            for record in reread.rereads
            if record.kept and record.page_index == page_reread.index
        )
        replaced = {
            (word.text, word.box) for record in kept for word in record.layer_words
        }
        read = {(word.text, word.box) for record in kept for word in record.ocr_words}
        layer_lines_reread = Counter(
            kept_line
            for line in _lines_with_boxes(page_reread).elements()
            if (kept_line := tuple(word for word in line if word not in read))
        )
        layer_lines_trusted = Counter(
            kept_line
            for line in _lines_with_boxes(page_trusted).elements()
            if (kept_line := tuple(word for word in line if word not in replaced))
        )
        assert layer_lines_reread == layer_lines_trusted, page_reread.index
    assert (
        "one, to be maintained only by caution ; advUers."
        in _line_texts(reread.pages[7])[1]
    )
    # Two more regions: the notes "Henry’s" and "Coronation.", which the
    # layer did not read (pages 7 and 8).
    assert sum(len(page.regions) for page in reread.pages) == 2 + sum(
        len(page.regions) for page in trusted.pages
    )


@pytest.mark.tesseract
@pytest.mark.thread_unsafe
def test_reread_stubbs_excerpt_with_1_worker_and_with_6_writes_the_same_bytes(
    excerpt_books: frozendict[str, BookFolder], tmp_path: Path
) -> None:
    folder = excerpt_books["stubbs_51_56-64"]
    (tmp_path / "one").mkdir()
    (tmp_path / "six").mkdir()
    one = _layout_again(folder, tmp_path / "one", _unchanged, 1)
    six = _layout_again(folder, tmp_path / "six", _unchanged, 6)
    assert read_lines(one.lines_json).rereads != ()
    assert one.lines_json.read_bytes() == six.lines_json.read_bytes()


@pytest.mark.tesseract
@pytest.mark.thread_unsafe
def test_reread_with_ocr_trust_records_nothing_and_lays_out_the_layer(
    excerpt_books: frozendict[str, BookFolder], tmp_path: Path
) -> None:
    folder = excerpt_books["domesday_74-83"]
    lines = read_lines(_layout_again(folder, tmp_path, _trusting, 6).lines_json)
    words = read_words(folder.words_json)
    measures = measure_book(words)
    assert lines.rereads == ()
    assert lines.pages == tuple(layout_page(page, measures) for page in words.pages)
    # The excerpt's own run, with the default `verify`, did re-read.
    assert read_lines(folder.lines_json).rereads != ()


@pytest.mark.tesseract
def test_reread_stubbs_summaries_index_has_no_small_print_page(
    excerpt_books: frozendict[str, BookFolder],
) -> None:
    # Six of the excerpt's ten pages are index pages, so their small type is
    # the excerpt's common size (reocr spec, section 9); the index read
    # whole is tested on the whole book.
    lines = read_lines(excerpt_books["stubbs_summaries_index"].lines_json)
    assert lines.rereads == ()


@pytest.mark.tesseract
@pytest.mark.usefixtures("tesseract_of_the_literals")
def test_reread_domesday_75_and_77_margin_notes_layer_garbled_and_layer_kept(
    excerpt_books: frozendict[str, BookFolder],
) -> None:
    # Excerpt pages 1 and 3, book page indices 75 and 77. The layer read
    # "Free land." as well as Tesseract did and is kept; it garbled the
    # others ("dOTQ^tht villein.", "Sn°inhbe pursued?", "The villein
    # nodal"8 justice.").
    lines = read_lines(excerpt_books["domesday_74-83"].lines_json)
    assert tuple(
        (
            reread.page_index,
            reread.kept,
            " ".join(word.text for word in reread.ocr_words),
        )
        for reread in lines.rereads
        if reread.page_index in {1, 3}
    ) == (
        (1, False, "Free land."),
        (1, True, "The unfree dom of the villein."),  # printed "unfree- dom"
        (1, True, "Can the villein be pursued ?"),
        (3, True, "The villein and seig- norial justice."),
        (3, True, "The villein and nation al justice."),  # printed "nation- al"
    )
    assert _line_texts(lines.pages[1])[2:5] == (
        ("Free land.",),
        ("The unfree", "dom of the", "villein."),
        ("Can the", "villein be", "pursued ?"),
    )
    assert _line_texts(lines.pages[3])[2:4] == (
        ("The villein", "and seig-", "norial", "justice."),
        ("The villein", "and nation", "al justice."),
    )


@pytest.mark.tesseract
@pytest.mark.thread_unsafe
@pytest.mark.usefixtures("tesseract_of_the_literals")
def test_reread_haskins_footnote_band_reads_the_marker_1_where_the_layer_has_a_caret(
    excerpt_books: frozendict[str, BookFolder], tmp_path: Path
) -> None:
    # Excerpt page 5, book page index 136, with `reread_footnotes = true`.
    folder = excerpt_books["haskins_eval"]
    lines = read_lines(
        _layout_again(folder, tmp_path, _reading_footnotes, 6).lines_json
    )
    (record,) = (
        reread
        for reread in lines.rereads
        if reread.page_index == 5 and reread.kind is RereadKind.FOOTNOTE_BAND
    )
    assert record.kept
    assert [word.text for word in record.layer_words][:2] == ["^", "Constitutional"]
    # Printed "1 Constitutional History, i, p. 551."
    assert _line_texts(lines.pages[5])[-1] == (
        "1 Constitutional",
        "History, 1, p. 551.",
    )


@pytest.mark.tesseract
@pytest.mark.usefixtures("tesseract_of_the_literals")
def test_reread_haskins_excerpt_by_default_reads_only_its_index_page(
    excerpt_books: frozendict[str, BookFolder],
) -> None:
    # Excerpt page 9 is book page index 266, the first page of the index,
    # a small-print page (reocr spec, section 3, kind 1); no footnote band
    # is read without `reread_footnotes`.
    lines = read_lines(excerpt_books["haskins_eval"].lines_json)
    assert tuple((reread.page_index, reread.kind) for reread in lines.rereads) == (
        (9, RereadKind.SMALL_PRINT_PAGE),
    )


# The margin notes the owner checked on the page images on 17 November
# 2026 (the check sheet of task 6.2 of docs/plans/clean-text.md, checks
# S-LOST, S-CUT, G-88, D-75 and D-77), each as printed and as the EPUB
# shows it: the text of a margin-note block of blocks.json, the output of
# structure, with the hyphens at line ends joined. The owner typed "'"
# where the books print, and Tesseract reads, "’", and left out two final
# full stops the page prints ("children.", "movement."); the literals hold
# the printed forms. A note galley still gets wrong is a strict xfail with
# the reason.

_CUT_IN_LINES_LEFT_IN_THE_COLUMN = (
    "layout leaves the note's first lines in the body column (layout spec, "
    "section 9: its cut-in zones find about half the notes' lines)"
)
_FINAL_STOP_READ_AS_COMMA = "Tesseract reads the note's final full stop as a comma"


def _owner_note(
    excerpt: str, page: int, note: str, reason: str | None = None
) -> object:
    marks = () if reason is None else (pytest.mark.xfail(strict=True, reason=reason),)
    return pytest.param(excerpt, page, note, marks=marks, id=f"{excerpt}-{page}-{note}")


_STUBBS = "stubbs_51_56-64"  # excerpt page 0 is book page index 51, 1 to 9 are 56 to 64
_GIERKE = "gierke_86-93_270-271"  # excerpt page 2 is book page index 88
_DOMESDAY = "domesday_74-83"  # excerpt pages 1 and 3 are book page indices 75 and 77


@pytest.mark.tesseract
@pytest.mark.usefixtures("tesseract_of_the_literals")
@pytest.mark.parametrize(
    ("excerpt", "page", "note"),
    [
        _owner_note(
            _STUBBS,
            0,
            "Importance attached by contemporaries to Henry’s accession.",
            _CUT_IN_LINES_LEFT_IN_THE_COLUMN,
        ),
        _owner_note(_STUBBS, 2, "Character of Henry II."),
        _owner_note(_STUBBS, 2, "His family policy."),
        # The layer reads the hyphen of "posi-" as a full stop, which
        # structure drops (structure spec, section 5, "hyphen_lost").
        _owner_note(_STUBBS, 3, "His great position in Christendom."),
        _owner_note(_STUBBS, 4, "Henry’s mismanagement of his children."),
        _owner_note(_STUBBS, 5, "Plan of reform."),
        _owner_note(_STUBBS, 5, "Terms of pacification.", _FINAL_STOP_READ_AS_COMMA),
        _owner_note(_STUBBS, 6, "Meaning of these terms.", _FINAL_STOP_READ_AS_COMMA),
        _owner_note(_STUBBS, 7, "Arrival of Henry as successor to Stephen, 1154."),
        _owner_note(
            _STUBBS,
            7,
            "Henry’s advisers.",
            "the crop drops Tesseract's 'advisers.' over the layer's 'advUers.', "
            "which layout leaves at the end of a body line by its 5 pt guard",
        ),
        _owner_note(_STUBBS, 8, "Bishop of Winchester."),
        _owner_note(_STUBBS, 8, "The Empress."),
        _owner_note(_STUBBS, 8, "Theobald and Becket."),
        _owner_note(_STUBBS, 8, "Coronation."),
        _owner_note(
            _STUBBS, 9, "Banishment of mercenaries.", _CUT_IN_LINES_LEFT_IN_THE_COLUMN
        ),
        _owner_note(_STUBBS, 9, "Destruction of castles."),
        _owner_note(_GIERKE, 2, "Diverse methods."),
        _owner_note(
            _GIERKE,
            2,
            "Unity of the movement.",
            _FINAL_STOP_READ_AS_COMMA,
        ),
        # Tesseract reads "and" as "_and" (reocr spec, section 4).
        _owner_note(_GIERKE, 2, "Medieval and Antique-Modern Thought."),
        _owner_note(_GIERKE, 2, "Medieval Thought."),
        _owner_note(_DOMESDAY, 1, "Free land."),
        _owner_note(
            _DOMESDAY,
            1,
            "The unfreedom of the villein.",
            "the excerpt's ten pages never print 'unfreedom' whole, the evidence "
            "for joining 'unfree' 'dom'; the whole book does (whole-book test below)",
        ),
        # The page prints a space before "?", which structure attaches
        # (structure spec, section 23).
        _owner_note(_DOMESDAY, 1, "Can the villein be pursued?"),
        _owner_note(_DOMESDAY, 3, "The villein and seignorial justice."),
        _owner_note(_DOMESDAY, 3, "The villein and national justice."),
    ],
)
def test_reread_owner_checked_margin_note_is_a_block_of_the_printed_text(
    excerpt: str, page: int, note: str, excerpt_books: frozendict[str, BookFolder]
) -> None:
    notes = _margin_notes_of_page(excerpt_books[excerpt].blocks_json, page)
    assert note in notes, notes


def _margin_notes_of_page(blocks_json: Path, page: int) -> tuple[str, ...]:
    """The texts of the margin-note blocks of blocks.json that start on
    page index `page`."""
    return tuple(
        "".join(span.text for span in block.spans)
        for block in read_blocks(blocks_json).blocks
        if block.kind is BlockKind.MARGIN_NOTE and block.origin[0].page_index == page
    )


def test_reread_scores_the_junk_under_a_word_not_its_copy_beside_it() -> None:
    # reocr spec, section 3: Domesday page 469, "Produce and value.", where
    # the layer holds junk under Tesseract's "value." and its copy "value."
    # 7 pt below. Counted with the copy, the layer's reading tied and was
    # kept; with the junk, Tesseract's is kept, and both are replaced.
    produce = Word("Produce", Box(10, 100, 34, 108), None)
    conjunction = Word("and", Box(40, 100, 52, 108), None)
    junk = Word("^x", Box(10, 111, 30, 119), None)
    copy = Word("value.", Box(10, 117, 30, 125), None)
    ocr = (
        Word("Produce", Box(10, 100, 34, 108), 90.0),
        Word("and", Box(40, 100, 52, 108), 90.0),
        Word("value.", Box(10, 110, 30, 118), 90.0),
    )
    reading = RegionReading(
        kind=RereadKind.MARGIN_NOTE,
        side=Side.LEFT,
        box=Box(8, 98, 56, 128),
        ocr_words=ocr,
        layer_words=(produce, conjunction, junk, copy),
    )
    (record,) = page_rereads(
        0, (reading,), frozenset({"produce", "and", "value"}), page_words=()
    )
    assert record.kept
    assert record.layer_words == (produce, conjunction, junk, copy)
    assert record.junk_words == (junk,)
    assert (record.layer_score, record.ocr_score) == (1, 3)


# domesday_rereads: excerpt pages 0, 2, 6, 8 and 10 are book page indices
# 26, 36, 139, 150 and 160. The text layer holds, beside a margin note's
# last word, its own reading a few points off and junk under Tesseract's
# word (reocr spec, section 4, "A pairing by letters wins over a word under
# it whose letters are unlike"). The printed notes are those the assistant
# read on the 300-dpi renders (tests/fixtures/expected/owner_books_wp1/).
_DOMESDAY_REREADS = "domesday_rereads"


@pytest.mark.tesseract
@pytest.mark.usefixtures("tesseract_of_the_literals")
@pytest.mark.parametrize(
    ("page", "layer_word"),
    [(0, "tem<"), (2, "scat'"), (6, "midlands."), (8, "taxes>"), (10, "Justice-")],
)
def test_reread_domesday_margin_note_word_of_the_layer_beside_is_read_once(
    page: int, layer_word: str, excerpt_books: frozendict[str, BookFolder]
) -> None:
    # The layer's second reading of the note's last word is replaced by
    # Tesseract's reading, not left beside it.
    lines = read_lines(excerpt_books[_DOMESDAY_REREADS].lines_json)
    assert any(
        word.text == layer_word
        for reread in lines.rereads
        if reread.kept and reread.page_index == page
        for word in reread.layer_words
    )
    # Tesseract's words have a confidence; the text layer's have none.
    assert layer_word not in (
        word.text
        for page_layout in lines.pages
        if page_layout.index == page
        for region in page_layout.regions
        for line in region.lines
        for word in line.words
        if word.ocr_confidence is None
    )


@pytest.mark.tesseract
@pytest.mark.usefixtures("tesseract_of_the_literals")
def test_reread_domesday_junk_under_a_note_word_read_once_is_replaced_too(
    excerpt_books: frozendict[str, BookFolder],
) -> None:
    # Excerpt page 2, book page index 36: the layer's "&g" lies under
    # Tesseract's "seat-", whose copy "scat'" the record replaces; left in
    # the text, it fell between "seat-" and "tered".
    lines = read_lines(excerpt_books[_DOMESDAY_REREADS].lines_json)
    assert any(
        word.text == "&g"
        for reread in lines.rereads
        if reread.kept and reread.page_index == 2
        for word in reread.layer_words
    )


@pytest.mark.tesseract
@pytest.mark.usefixtures("tesseract_of_the_literals")
@pytest.mark.parametrize(
    ("page", "printed"),
    [
        # Tesseract reads the final full stop as a comma.
        (0, "The survey and the geld system."),
        (6, "Large manors in the midlands."),
        (8, "The lord and his man's taxes."),
        (10, "The sokeman and seignorial justice."),
    ],
)
def test_reread_domesday_margin_note_read_once_has_the_printed_words(
    page: int, printed: str, excerpt_books: frozendict[str, BookFolder]
) -> None:
    def letters(text: str) -> tuple[str, ...]:
        return tuple(
            folded
            for word in text.split()
            if (folded := folded_letters_and_digits(word))
        )

    notes = _margin_notes_of_page(excerpt_books[_DOMESDAY_REREADS].blocks_json, page)
    assert letters(printed) in tuple(letters(note) for note in notes), notes


@pytest.mark.whole_book
@pytest.mark.tesseract
@pytest.mark.thread_unsafe
@pytest.mark.timeout(600)
@pytest.mark.usefixtures("tesseract_of_the_literals")
def test_reread_owner_checked_whole_domesday_75_joins_unfree_dom(
    whole_book_run: Callable[[str], BookFolder],
) -> None:
    # The book prints "unfreedom" whole 6 times, so "unfree" "dom", whose
    # hyphen Tesseract missed, is joined (structure spec, section 5).
    folder = whole_book_run("domesdaybook00maituoft")
    assert _margin_notes_of_page(folder.blocks_json, 75) == (
        "Free land.",
        "The unfreedom of the villein.",
        "Can the villein be pursued?",
    )


# Three index pages transcribed by eye from 400 and 600 dpi renders on 17
# November 2026, one printed line per line (tests/fixtures/expected/
# index_*.txt): Haskins' page indices 266 and 267, excerpt page 9 of
# haskins_eval and of haskins_quotes_index, and Stubbs' 312, which is a
# small-print page in the whole book only (reocr spec, section 9). The
# words layout gives on the page, all its regions, are compared with the
# transcription's as multisets: the words galley misses and the words it
# has that the page does not print. What galley gets wrong today is the
# frozen list beside each transcription (index_*.differences.json), which
# the test compares strictly, so that a change shows, for the better or the
# worse. The order of the words is not compared.

_EXPECTED_DIR = Path(__file__).parent / "fixtures" / "expected"


def _transcribed_words(name: str) -> Counter[str]:
    """The words of the transcription `name`, without its comment lines and
    the "[ornament]" it writes for a printed ornament."""
    text = (_EXPECTED_DIR / f"{name}.txt").read_text(encoding="utf-8")
    return Counter(
        word
        for line in text.splitlines()
        if not line.startswith("#")
        for word in line.split()
        if word != "[ornament]"
    )


def _differences_from_transcription(
    lines: LinesFile, page_index: int, name: str
) -> dict[str, dict[str, int]]:
    printed = _transcribed_words(name)
    page = next(page for page in lines.pages if page.index == page_index)
    laid_out = Counter(
        word.text
        for region in page.regions
        for line in region.lines
        for word in line.words
    )
    return {
        "missing": dict(sorted((printed - laid_out).items())),
        "extra": dict(sorted((laid_out - printed).items())),
    }


def _frozen_differences(name: str) -> object:
    return json.loads(
        (_EXPECTED_DIR / f"{name}.differences.json").read_text(encoding="utf-8")
    )


@pytest.mark.tesseract
@pytest.mark.usefixtures("tesseract_of_the_literals")
@pytest.mark.parametrize(
    ("excerpt", "name"),
    [
        ("haskins_eval", "index_haskins_266"),
        ("haskins_quotes_index", "index_haskins_267"),
    ],
)
def test_reread_haskins_index_page_differs_from_its_transcription_as_frozen(
    excerpt: str, name: str, excerpt_books: frozendict[str, BookFolder]
) -> None:
    lines = read_lines(excerpt_books[excerpt].lines_json)
    assert _differences_from_transcription(lines, 9, name) == _frozen_differences(name)


@pytest.mark.whole_book
@pytest.mark.tesseract
@pytest.mark.thread_unsafe
@pytest.mark.timeout(600)
@pytest.mark.usefixtures("tesseract_of_the_literals")
def test_reread_whole_stubbs_index_page_312_differs_from_its_transcription_as_frozen(
    whole_book_run: Callable[[str], BookFolder],
) -> None:
    lines = read_lines(whole_book_run("earlyplantagenet01stub").lines_json)
    assert _differences_from_transcription(
        lines, 312, "index_stubbs_312"
    ) == _frozen_differences("index_stubbs_312")


# The whole books (reocr spec, section 9, "Whole-book tests"), from the
# session's run of each (tests/conftest.py), whose layout re-reads with 6
# workers.


@pytest.mark.whole_book
@pytest.mark.tesseract
@pytest.mark.thread_unsafe
@pytest.mark.timeout(600)
@pytest.mark.parametrize(
    "book",
    [
        "battleofkadeshst00breauoft",
        "catherinedemedic00mariuoft",
        "domesdaybook00maituoft",
        "earlyplantagenet01stub",
        "normansineuropea00hask",
        "politicaltheorie00gieruoft",
    ],
)
def test_layout_of_a_whole_book_with_rereading_keeps_every_word(
    book: str, whole_book_run: Callable[[str], BookFolder]
) -> None:
    # The configs of the six books are those of tests/conftest.py.
    folder = whole_book_run(book)
    _assert_laid_out_in_regions(
        read_words(folder.words_json), read_lines(folder.lines_json)
    )


@pytest.mark.whole_book
@pytest.mark.tesseract
@pytest.mark.thread_unsafe
@pytest.mark.timeout(900)
def test_reread_whole_stubbs_with_1_worker_and_with_6_writes_the_same_bytes(
    whole_book_run: Callable[[str], BookFolder], tmp_path: Path
) -> None:
    # The session's run laid Stubbs out with 6 workers; this one takes 1.
    folder = whole_book_run("earlyplantagenet01stub")
    one = _layout_again(folder, tmp_path, _unchanged, 1)
    assert len(read_lines(one.lines_json).rereads) > 300
    assert one.lines_json.read_bytes() == folder.lines_json.read_bytes()
