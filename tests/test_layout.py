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
    """Three words of height 8 that fill `width` from `left`."""
    bottom = top + _ROW_HEIGHT
    return (
        _word(f"a{row}", left, top, left + 60, bottom),
        _word(f"b{row}", left + 70, top, left + 130, bottom),
        _word(f"c{row}", left + 140, top, left + width, bottom),
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
