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
from galley.layout import group_lines, layout_page
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


def test_no_words_give_no_lines() -> None:
    assert group_lines(()) == ()


# layout_page

_PAGE_WORDS = (
    _word("Alpha", 50, 100, 90, 112),
    _word("beta", 95, 101, 120, 113),
    _word("gamma", 40, 120, 80, 132),
    _word("delta", 85, 120, 130, 131),
)


def test_layout_page_puts_every_line_in_one_region_whose_box_holds_them() -> None:
    result = layout_page(_page(3, _PAGE_WORDS))
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
    assert layout_page(_page(5, ())) == PageLayout(5, (), ())


def test_layout_page_copies_the_figures() -> None:
    figures = (Figure(Box(10, 20, 300, 400), "images/p0002-01.png", 300),)
    page = replace(_page(2, _PAGE_WORDS[:1]), figures=figures)
    assert layout_page(page).figures == figures


# The fidelity check at the layout boundary


def _words_file(pages: tuple[PageWords, ...]) -> WordsFile:
    return WordsFile(source_pdf_sha256="0" * 64, pages=pages, removals=())


def test_fidelity_check_passes_on_layout_pages() -> None:
    pages = (_page(0, _PAGE_WORDS), _page(1, ()))
    lines = LinesFile(
        source_pdf_sha256="0" * 64, pages=tuple(layout_page(p) for p in pages)
    )
    check_stage(FidelityBoundary.LAYOUT, _words_file(pages), lines)


def test_fidelity_check_fails_when_a_word_is_dropped_from_a_line() -> None:
    page = layout_page(_page(0, _PAGE_WORDS))
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
