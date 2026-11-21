"""Tests of galley.structure (docs/specs/structure.md, section 9).

Every value is written by hand: structure's tests need no output of layout.
The excerpt tests of structure on the reference pages are in
tests/test_excerpts.py; the whole_book tests here check the two reference
pages an excerpt cannot get right.
"""

import functools
import hashlib
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from enum import StrEnum
from pathlib import Path
from typing import assert_never

import pytest

from galley import structure, wordlist
from galley.book_folder import BookFolder
from galley.config import BookConfig, Language
from galley.errors import FidelityBoundary, FidelityError, InputFileError
from galley.fidelity import check_stage
from galley.model import (
    Block,
    BlockKind,
    BlocksFile,
    Box,
    ChangeReason,
    Emphasis,
    Figure,
    FigureKind,
    Line,
    LinesFile,
    NoteKind,
    Origin,
    PageInfo,
    PageKind,
    PageLayout,
    PageNumber,
    PageNumberPosition,
    PagesFile,
    Region,
    Removal,
    RemovalReason,
    RereadKind,
    Span,
    TextSource,
    Word,
    WordChange,
    block_text,
    read_blocks,
    read_lines,
    read_words,
    write_blocks,
    write_lines,
    write_pages,
)
from galley.structure import (
    HyphenJoin,
    NoteMarker,
    Reference,
    ReferenceForm,
    _survey,
    join_hyphen,
    join_lost_hyphen,
    make_blocks,
    note_marker,
    reference_candidate,
    survey_book,
)
from galley.structure._assemble import _taken_body_notes
from galley.structure._figure_blocks import with_figures
from galley.structure._figures import PageFigure
from galley.structure._heads import is_number_like
from galley.structure._index import entry_side, index_page
from galley.structure._index_entries import _index_runs, _IndexRun
from galley.structure._lines import Piece, PlacedLine
from galley.structure._linking import body_candidates
from galley.structure._margins import BesideLine, InParagraph, line_beside
from galley.structure._markers import MarkerForm, book_marker_form
from galley.structure._measures import Edges
from galley.structure._notes import Numbering
from galley.structure._paragraphs import PageParts
from galley.structure._plates import plate_survey
from galley.structure._references import (
    Candidate,
    NoteToMatch,
    align,
    match_endnotes,
    pair_score,
    reference_form,
)
from galley.structure._regions import region_kinds
from galley.structure._unnumbered import Unnumbered, without_marker
from galley.wordlist import word_key


def _word(text: str, x0: float, top: float, x1: float, bottom: float) -> Word:
    return Word(text, Box(x0, top, x1, bottom), None)


_FIRST_LINE = Line(
    Box(50, 100, 120, 113),
    (_word("Alpha", 50, 100, 90, 112), _word("beta,", 95, 101, 120, 113)),
)
_SECOND_LINE = Line(
    Box(40, 120, 130, 132),
    (_word("gamma", 40, 120, 80, 132), _word("delta.", 85, 120, 130, 131)),
)
_REGION = Region(Box(40, 100, 130, 132), (_FIRST_LINE, _SECOND_LINE))


def _paragraph(block_id: str, text: str, page_index: int, box: Box) -> Block:
    return Block(
        id=block_id,
        kind=BlockKind.PARAGRAPH,
        level=None,
        label=None,
        spans=(Span(text, Emphasis.NONE, None),),
        figure=None,
        origin=(Origin(page_index, box),),
    )


# Pages written by hand. A word is 5 pt wide per character and 10 pt high,
# with one character's width between words, unless given otherwise.

_NO_WORDS: frozenset[str] = frozenset()
_CHAR_PT = 5.0
_WORD_HEIGHT_PT = 10.0
_PITCH_PT = 15.0
_BODY_LEFT_PT = 50.0


def _words_at(
    text: str, x0: float, top: float, height: float = _WORD_HEIGHT_PT
) -> tuple[Word, ...]:
    words = []
    left = x0
    for part in text.split(" "):
        right = left + _CHAR_PT * len(part)
        words.append(Word(part, Box(left, top, right, top + height), None))
        left = right + _CHAR_PT
    return tuple(words)


def _box(boxes: tuple[Box, ...]) -> Box:
    return Box(
        min(box.x0 for box in boxes),
        min(box.top for box in boxes),
        max(box.x1 for box in boxes),
        max(box.bottom for box in boxes),
    )


def _line(text: str, x0: float, top: float, height: float = _WORD_HEIGHT_PT) -> Line:
    words = _words_at(text, x0, top, height)
    return Line(_box(tuple(word.box for word in words)), words)


def _region(*lines: Line) -> Region:
    return Region(_box(tuple(line.box for line in lines)), lines)


def _body(top: float, *texts: str, x0: float = _BODY_LEFT_PT) -> Region:
    """A region of one line per text, 15 pt apart, from `top`."""
    return _region(
        *(
            _line(text, x0, top + _PITCH_PT * number)
            for number, text in enumerate(texts)
        )
    )


_BODY_TEXTS = (
    "the first line of the body",
    "the second line of the body",
    "the third line of the body",
    "the fourth line of the body",
    "the fifth line of the body",
    "the sixth line of the body",
)


def _page_with_head(index: int, head: str, head_top: float = 36.0) -> PageLayout:
    """A page with a head line at `head_top` and six body lines from 34 pt
    below it."""
    return PageLayout(
        index,
        (
            _region(_line(head, _BODY_LEFT_PT, head_top)),
            _body(head_top + 34, *_BODY_TEXTS),
        ),
        (),
    )


# Heads that differ from one another, each at least 0.75 alike to another.
_HEADS_WITHOUT_NUMBERS = (
    "THE BOOK",
    "THE BOKO",
    "TIIE BOOK",
    "THE BOOKS",
    "THF BOOK",
    "THE BQOK",
)


def _lines_of(*pages: PageLayout) -> LinesFile:
    return LinesFile(source_pdf_sha256=_HASH, pages=pages, rereads=())


def _numbered_heads() -> tuple[PageLayout, ...]:
    """Pages 10 to 15 printed 25 to 30, the number first on even pages."""
    return tuple(
        _page_with_head(
            index,
            f"{index + 15} THE BOOK" if index % 2 == 0 else f"THE BOOK {index + 15}",
        )
        for index in range(10, 16)
    )


# survey_book


def test_survey_finds_numbered_heads_running_heads_and_the_offset() -> None:
    survey = survey_book(_lines_of(*_numbered_heads()), workers=1)
    assert survey.running_heads == frozenset(range(10, 16))
    assert survey.head_page_offset == -15
    assert survey.first_arabic_page == 10
    assert survey.body_word_height == _WORD_HEIGHT_PT
    assert survey.body_line_pitch == _PITCH_PT


def test_survey_finds_heads_without_numbers_running_heads_by_their_letters() -> None:
    pages = tuple(
        _page_with_head(index, head)
        for index, head in enumerate(_HEADS_WITHOUT_NUMBERS, start=10)
    )
    survey = survey_book(_lines_of(*pages), workers=1)
    assert survey.running_heads == frozenset(range(10, 16))
    assert survey.head_page_offset is None
    assert survey.first_arabic_page is None


def test_survey_does_not_take_a_head_line_alike_to_no_other_for_a_running_head() -> (
    None
):
    pages = (
        _page_with_head(10, "THE BOOK"),
        _page_with_head(11, "THE BOOK"),
        _page_with_head(12, "CHAPTER ON NORMANDY"),
    )
    assert survey_book(_lines_of(*pages), workers=1).running_heads == frozenset(
        {10, 11}
    )


def test_survey_does_not_take_the_same_title_70_pt_lower_for_a_running_head() -> None:
    pages = (
        *(
            _page_with_head(index, head)
            for index, head in enumerate(_HEADS_WITHOUT_NUMBERS, start=10)
        ),
        _page_with_head(16, "THE BOOK", head_top=106.0),
    )
    survey = survey_book(_lines_of(*pages), workers=1)
    assert survey.running_heads == frozenset(range(10, 16))


def test_survey_book_words_leave_out_the_parts_of_a_hyphenated_word() -> None:
    page = PageLayout(
        0, (_body(70, "Of the neces-", "sary Anglo-Saxon things,", "and so"),), ()
    )
    assert survey_book(_lines_of(page), workers=1).book_words == frozenset(
        {"of", "the", "anglo-saxon", "things", "and", "so"}
    )


def test_survey_book_words_keep_a_number_before_a_word_and_leave_out_a_range() -> None:
    page = PageLayout(
        0, (_body(70, "Britain, 136-39-", "Bryce, 1066-", "1087 here"),), ()
    )
    assert survey_book(_lines_of(page), workers=1).book_words == frozenset(
        {"britain", "136-39-", "bryce", "here"}
    )


def test_survey_body_word_height_is_the_median_of_the_rows_medians() -> None:
    small = _region(
        *(_line("a small note", 50, 300 + 10 * n, height=7.0) for n in range(3))
    )
    page = PageLayout(0, (_body(70, *_BODY_TEXTS[:4]), small), ())
    assert survey_book(_lines_of(page), workers=1).body_word_height == _WORD_HEIGHT_PT


# Running heads and page numbers in the head


def _removals_of(page_index: int, blocks: BlocksFile) -> tuple[Removal, ...]:
    return tuple(
        removal for removal in blocks.removals if removal.page_index == page_index
    )


def test_head_with_a_page_number_and_a_mark_above_is_removed_in_three_parts() -> None:
    mark = _line(";", 120, 20)
    head = _line("214 NORMANS IN EUROPEAN HISTORY", _BODY_LEFT_PT, 36)
    page = PageLayout(229, (_region(mark, head), _body(70, *_BODY_TEXTS)), ())
    others = (
        _page_with_head(230, "THE COMING OF THE NORMANS 215"),
        _page_with_head(231, "216 NORMANS IN EUROPEAN HISTORY"),
    )
    blocks = make_blocks(_lines_of(page, *others), _NO_WORDS, workers=1)
    assert _removals_of(229, blocks) == (
        Removal(
            page_index=229, box=mark.box, text=";", reason=RemovalReason.STRAY_MARK
        ),
        Removal(
            page_index=229,
            box=head.words[0].box,
            text="214",
            reason=RemovalReason.PAGE_NUMBER,
        ),
        Removal(
            page_index=229,
            box=_box(tuple(word.box for word in head.words[1:])),
            text="NORMANS IN EUROPEAN HISTORY",
            reason=RemovalReason.RUNNING_HEAD,
        ),
    )
    assert blocks.page_numbers == (
        PageNumber(229, "214", PageNumberPosition.HEAD),
        PageNumber(230, "215", PageNumberPosition.HEAD),
        PageNumber(231, "216", PageNumberPosition.HEAD),
    )
    assert all("NORMANS" not in block_text(block) for block in blocks.blocks)


def test_marks_above_a_head_line_that_is_no_running_head_stay() -> None:
    page = PageLayout(
        3,
        (
            _region(_line(";", 120, 20), _line("A TITLE", 80, 36)),
            _body(70, *_BODY_TEXTS),
        ),
        (),
    )
    blocks = make_blocks(_lines_of(page), _NO_WORDS, workers=1)
    assert blocks.removals == ()
    assert block_text(blocks.blocks[0]).startswith("; A TITLE the first line")


def test_misread_head_number_goes_with_the_running_head_and_gives_no_page_number() -> (
    None
):
    pages = (
        _page_with_head(130, "THE BOOK ii8"),
        _page_with_head(131, "THE BOOK 119"),
    )
    blocks = make_blocks(_lines_of(*pages), _NO_WORDS, workers=1)
    assert _removals_of(130, blocks) == (
        Removal(
            page_index=130,
            box=pages[0].regions[0].box,
            text="THE BOOK ii8",
            reason=RemovalReason.RUNNING_HEAD,
        ),
    )
    assert blocks.page_numbers == (PageNumber(131, "119", PageNumberPosition.HEAD),)


def test_roman_head_number_counts_only_before_the_first_arabic_one() -> None:
    pages = (
        _page_with_head(5, "PREFACE xi"),
        _page_with_head(6, "PREFACE xii"),
        _page_with_head(20, "THE EARLY KINGS 3"),
        _page_with_head(21, "THE EARLY KINGS. ch. i."),
    )
    blocks = make_blocks(_lines_of(*pages), _NO_WORDS, workers=1)
    assert blocks.page_numbers == (
        PageNumber(5, "xi", PageNumberPosition.HEAD),
        PageNumber(6, "xii", PageNumberPosition.HEAD),
        PageNumber(20, "3", PageNumberPosition.HEAD),
    )
    assert _removals_of(21, blocks)[0].text == "THE EARLY KINGS. ch. i."


def test_of_two_head_numbers_the_one_the_offset_gives_is_the_page_number() -> None:
    pages = (
        _page_with_head(20, "5 THE BOOK"),
        _page_with_head(21, "THE BOOK 6"),
        _page_with_head(22, "12 THE BOOK 7"),
    )
    blocks = make_blocks(_lines_of(*pages), _NO_WORDS, workers=1)
    assert blocks.page_numbers[-1] == PageNumber(22, "7", PageNumberPosition.HEAD)
    assert tuple(removal.text for removal in _removals_of(22, blocks)) == (
        "12 THE BOOK",
        "7",
    )


def test_top_line_ending_with_a_roman_form_that_is_a_word_stays() -> None:
    pages = (
        _page_with_head(5, "The war ended in the year of 1066 at last, in vi"),
        *_numbered_heads(),
    )
    survey = survey_book(_lines_of(*pages), workers=1)
    assert 5 not in survey.running_heads
    blocks = make_blocks(_lines_of(*pages), _NO_WORDS, workers=1)
    assert _removals_of(5, blocks) == ()


def test_number_alone_is_a_running_head_only_where_the_offset_puts_it() -> None:
    # Pages 10 to 15 print 25 to 30: the offset is -15.
    pages = (
        *_numbered_heads(),
        _page_with_head(16, "31"),
        _page_with_head(17, "47"),
        _page_with_head(18, "35"),
    )
    survey = survey_book(_lines_of(*pages), workers=1)
    assert {16, 18} <= survey.running_heads
    assert 17 not in survey.running_heads


def test_roman_number_whose_line_is_alike_to_another_without_it_is_a_head() -> None:
    # "PREF vii" and "PREF xxxviii" are not alike with their numbers' letters
    # (0.56), but are without them; the roman numbers come before the first
    # arabic head, on page 10.
    pages = (
        _page_with_head(3, "PREF vii"),
        _page_with_head(4, "PREF xxxviii"),
        _page_with_head(5, "INTRODUCTION 99"),
        *_numbered_heads(),
    )
    survey = survey_book(_lines_of(*pages), workers=1)
    assert {3, 4} <= survey.running_heads
    assert 5 not in survey.running_heads
    assert survey.head_page_offset == -15


def test_roman_number_alone_after_the_first_arabic_head_is_no_running_head() -> None:
    pages = (*_numbered_heads(), _page_with_head(16, "d"))
    assert 16 not in survey_book(_lines_of(*pages), workers=1).running_heads


def test_head_number_split_by_the_ocr_is_joined() -> None:
    pages = (*_numbered_heads(), _page_with_head(16, "THE BOOK 3 1"))
    blocks = make_blocks(_lines_of(*pages), _NO_WORDS, workers=1)
    assert blocks.page_numbers[-1] == PageNumber(16, "31", PageNumberPosition.HEAD)
    assert tuple(
        (removal.text, removal.reason) for removal in _removals_of(16, blocks)
    ) == (("THE BOOK", RemovalReason.RUNNING_HEAD), ("3 1", RemovalReason.PAGE_NUMBER))


def test_running_head_below_a_speck_is_removed_and_the_speck_stays() -> None:
    speck_page = PageLayout(
        16,
        (
            _region(_line("d", 120, 20)),
            _body(36, "THE BOOK 31", *_BODY_TEXTS),
        ),
        (),
    )
    pages = (*_numbered_heads(), speck_page)
    blocks = make_blocks(_lines_of(*pages), _NO_WORDS, workers=1)
    assert tuple(
        (removal.text, removal.reason) for removal in _removals_of(16, blocks)
    ) == (("THE BOOK", RemovalReason.RUNNING_HEAD), ("31", RemovalReason.PAGE_NUMBER))
    assert blocks.page_numbers[-1] == PageNumber(16, "31", PageNumberPosition.HEAD)
    assert "d the first line of the body" in block_text(blocks.blocks[-1])


# The head of a short section (spec section 3): a section of two pages, its
# heading on page 4 at 106 pt, 4.7 pitches below the median head top of 36
# pt, and its one running head on page 5; pages 10 to 15 print 25 to 30, so
# the first arabic head number is on page 10 and a roman one before it is a
# page-number form.


def _short_section(
    head: str, head_top: float = 36.0, heading: str = "PREFACE"
) -> tuple[PageLayout, ...]:
    return (
        _page_with_head(4, heading, head_top=106.0),
        _page_with_head(5, head, head_top=head_top),
        *_numbered_heads(),
    )


def _removed_texts(blocks: BlocksFile, page_index: int) -> tuple[tuple[str, str], ...]:
    return tuple(
        (removal.text, removal.reason) for removal in _removals_of(page_index, blocks)
    )


@pytest.mark.parametrize(
    "text", ["vi", "vlil", "xiv.", "47", "XIV,", "i", "MDCL", "c."]
)
def test_number_like_word_is_recognised(text: str) -> None:
    assert is_number_like(text)


@pytest.mark.parametrize(
    "text", ["", "vlili", "xiv..", "vi.,", "Pre", "ab", "v.i", "(vi)", "12345"]
)
def test_word_that_is_not_number_like_is_refused(text: str) -> None:
    assert not is_number_like(text)


def test_short_section_head_with_a_misread_number_is_removed_with_its_line() -> None:
    blocks = make_blocks(
        _lines_of(*_short_section("vlil PREFACE")), _NO_WORDS, workers=1
    )
    assert _removed_texts(blocks, 5) == (("vlil PREFACE", RemovalReason.RUNNING_HEAD),)
    assert all(number.page_index != 5 for number in blocks.page_numbers)


def test_short_section_head_with_a_roman_page_number_records_it() -> None:
    blocks = make_blocks(
        _lines_of(*_short_section("vi Preface.")), _NO_WORDS, workers=1
    )
    assert _removed_texts(blocks, 5) == (
        ("vi", RemovalReason.PAGE_NUMBER),
        ("Preface.", RemovalReason.RUNNING_HEAD),
    )
    assert blocks.page_numbers[0] == PageNumber(5, "vi", PageNumberPosition.HEAD)


def test_short_section_head_with_its_number_last_is_a_running_head() -> None:
    survey = survey_book(_lines_of(*_short_section("PREFACE vlil")), workers=1)
    assert 5 in survey.running_heads


def test_short_section_rule_keeps_a_title_line_without_a_number_like_word() -> None:
    # Gierke's page 8 repeats the half-title of page 6 at the top of the page.
    pages = (
        _page_with_head(6, "POLITICAL THEORIES", head_top=106.0),
        PageLayout(7, (), ()),
        _page_with_head(8, "POLITICAL THEORIES"),
        *_numbered_heads(),
    )
    blocks = make_blocks(_lines_of(*pages), _NO_WORDS, workers=1)
    assert _removals_of(8, blocks) == ()


def test_short_section_rule_keeps_a_head_whose_end_word_is_not_number_like() -> None:
    # Without its first word, "THE PREFACE" is the heading of page 4; "THE"
    # is not number-like, so the line stays.
    survey = survey_book(_lines_of(*_short_section("THE PREFACE")), workers=1)
    assert 5 not in survey.running_heads


def test_short_section_heading_is_the_topmost_line_not_the_first_region() -> None:
    # Page 4's heading is in its second region, above the body of the first.
    heading_page = PageLayout(
        4,
        (
            _body(140.0, *_BODY_TEXTS),
            _region(_line("PREFACE", _BODY_LEFT_PT, 106.0)),
        ),
        (),
    )
    pages = (heading_page, _page_with_head(5, "vi Preface."), *_numbered_heads())
    survey = survey_book(_lines_of(*pages), workers=1)
    assert 5 in survey.running_heads


def test_short_section_heading_two_pages_before_with_a_blank_page_between() -> None:
    pages = (
        _page_with_head(3, "PREFACE", head_top=106.0),
        PageLayout(4, (), ()),
        _page_with_head(5, "vi Preface."),
        *_numbered_heads(),
    )
    survey = survey_book(_lines_of(*pages), workers=1)
    assert 5 in survey.running_heads


def test_short_section_heading_three_pages_before_is_not_compared() -> None:
    pages = (
        _page_with_head(2, "PREFACE", head_top=106.0),
        PageLayout(3, (), ()),
        PageLayout(4, (), ()),
        _page_with_head(5, "vi Preface."),
        *_numbered_heads(),
    )
    survey = survey_book(_lines_of(*pages), workers=1)
    assert 5 not in survey.running_heads


def test_short_section_head_with_fewer_than_4_letters_stays() -> None:
    survey = survey_book(
        _lines_of(*_short_section("vi Pre.", heading="PRE")), workers=1
    )
    assert 5 not in survey.running_heads


def test_short_section_head_less_than_0_75_alike_to_the_heading_stays() -> None:
    # "preface" against "prefatory": 0.625 alike.
    survey = survey_book(
        _lines_of(*_short_section("vi Preface.", heading="PREFATORY")), workers=1
    )
    assert 5 not in survey.running_heads


def test_short_section_head_more_than_2_pitches_below_the_median_stays() -> None:
    # 31 pt below the median head top of 36 pt, against 2 pitches of 15 pt.
    survey = survey_book(
        _lines_of(*_short_section("vi Preface.", head_top=67.0)), workers=1
    )
    assert 5 not in survey.running_heads


def test_short_section_head_exactly_2_pitches_below_the_median_is_removed() -> None:
    survey = survey_book(
        _lines_of(*_short_section("vi Preface.", head_top=66.0)), workers=1
    )
    assert 5 in survey.running_heads


# Page numbers at the foot and signature marks, on a column from x 25 to
# 299 pt (its middle at 162 pt)

_COLUMN_LEFT_PT = 25.0
_COLUMN_RIGHT_PT = 299.0
_FOOT_TOP_PT = 400.0


def _column_line(top: float) -> Line:
    words = (
        Word("Body", Box(_COLUMN_LEFT_PT, top, 60, top + _WORD_HEIGHT_PT), None),
        Word("text.", Box(264, top, _COLUMN_RIGHT_PT, top + _WORD_HEIGHT_PT), None),
    )
    return Line(_box(tuple(word.box for word in words)), words)


def _foot_line(top: float, *words: tuple[str, float]) -> Line:
    """A line of the words (text, left side), each 5 pt wide a character."""
    placed = tuple(
        Word(
            text,
            Box(x0, top, x0 + _CHAR_PT * len(text), top + _WORD_HEIGHT_PT),
            None,
        )
        for text, x0 in words
    )
    return Line(_box(tuple(word.box for word in placed)), placed)


def _page_with_foot(index: int, *foot_lines: Line) -> PageLayout:
    """A page of six body lines across the column, then the foot lines in a
    region of their own, as layout gives a foot set apart."""
    body = _region(*(_column_line(70 + _PITCH_PT * number) for number in range(6)))
    return PageLayout(index, (body, _region(*foot_lines)), ())


def _centred(text: str) -> tuple[str, float]:
    return text, 162 - _CHAR_PT * len(text) / 2


@pytest.mark.parametrize("number", ["(49)", "U9)", "83"])
def test_centred_page_number_at_the_foot_is_removed(number: str) -> None:
    foot = _foot_line(_FOOT_TOP_PT, _centred(number))
    blocks = make_blocks(_lines_of(_page_with_foot(4, foot)), _NO_WORDS, workers=1)
    assert blocks.removals == (
        Removal(
            page_index=4, box=foot.box, text=number, reason=RemovalReason.PAGE_NUMBER
        ),
    )
    assert blocks.page_numbers == (PageNumber(4, number, PageNumberPosition.FOOT),)


@pytest.mark.parametrize(
    "words",
    [(("M.", 37), ("4", 266)), (("4—2", 252),)],
    ids=["M. 4", "4—2"],
)
def test_signature_mark_at_the_foot_is_removed(
    words: tuple[tuple[str, float], ...],
) -> None:
    foot = _foot_line(_FOOT_TOP_PT, *words)
    blocks = make_blocks(_lines_of(_page_with_foot(4, foot)), _NO_WORDS, workers=1)
    assert blocks.removals == (
        Removal(
            page_index=4,
            box=foot.box,
            text=" ".join(text for text, _ in words),
            reason=RemovalReason.SIGNATURE_MARK,
        ),
    )
    assert blocks.page_numbers == ()


@pytest.mark.parametrize(
    "words",
    [
        (("4", 28), ("Ibid.", 38), ("29.", 68)),
        (("(5)", 28), ("Ibid.,", 48), ("p.", 83), ("3.", 98)),
        (("p.", 28), ("83.", 43)),
        (_centred("1907"),),
    ],
    ids=["note line", "note line with a marker", "short note line", "year"],
)
def test_foot_line_that_is_no_page_number_or_mark_stays(
    words: tuple[tuple[str, float], ...],
) -> None:
    foot = _foot_line(_FOOT_TOP_PT, *words)
    blocks = make_blocks(_lines_of(_page_with_foot(4, foot)), _NO_WORDS, workers=1)
    assert blocks.removals == ()
    assert blocks.page_numbers == ()


def test_signature_mark_above_a_page_number_is_removed_with_it() -> None:
    mark = _foot_line(_FOOT_TOP_PT - _PITCH_PT, ("4—2", 252))
    number = _foot_line(_FOOT_TOP_PT, _centred("83"))
    blocks = make_blocks(
        _lines_of(_page_with_foot(4, mark, number)), _NO_WORDS, workers=1
    )
    assert tuple((removal.text, removal.reason) for removal in blocks.removals) == (
        ("4—2", RemovalReason.SIGNATURE_MARK),
        ("83", RemovalReason.PAGE_NUMBER),
    )


def _signature_line(*words: str) -> Line:
    """Mariéjol's signature line: the words, its page number in brackets
    centred, and the signature's number."""
    *signature, number, sheet = words
    left = 30.0
    placed = []
    for text in signature:
        placed.append((text, left))
        left += _CHAR_PT * (len(text) + 1)
    return _foot_line(_FOOT_TOP_PT, *placed, _centred(number), (sheet, 280))


def test_signature_line_on_two_pages_gives_a_page_number_and_a_mark_each() -> None:
    lines = (
        _signature_line("MARIÉJOL.", "Cath.", "de", "Médicis.", "(49)", "4"),
        _signature_line("UAMiàjoL.", "CmOl", "da", "Médidib", "(l93)", "13"),
    )
    pages = tuple(_page_with_foot(index, line) for index, line in enumerate(lines))
    blocks = make_blocks(_lines_of(*pages), _NO_WORDS, workers=1)
    assert tuple(
        (removal.page_index, removal.text, removal.reason)
        for removal in blocks.removals
    ) == (
        (0, "MARIÉJOL. Cath. de Médicis. 4", RemovalReason.SIGNATURE_MARK),
        (0, "(49)", RemovalReason.PAGE_NUMBER),
        (1, "UAMiàjoL. CmOl da Médidib 13", RemovalReason.SIGNATURE_MARK),
        (1, "(l93)", RemovalReason.PAGE_NUMBER),
    )
    assert blocks.page_numbers == (
        PageNumber(0, "(49)", PageNumberPosition.FOOT),
        PageNumber(1, "(l93)", PageNumberPosition.FOOT),
    )


def test_note_line_starting_with_its_marker_on_two_pages_is_no_signature_line() -> None:
    lines = (
        _foot_line(
            _FOOT_TOP_PT, _centred("(5)"), ("Ibid.,", 200), ("p.", 240), ("3.", 255)
        ),
        _foot_line(
            _FOOT_TOP_PT, _centred("(5)"), ("Ibid.,", 200), ("p.", 240), ("3.", 255)
        ),
    )
    pages = tuple(_page_with_foot(index, line) for index, line in enumerate(lines))
    blocks = make_blocks(_lines_of(*pages), _NO_WORDS, workers=1)
    assert blocks.removals == ()


# join_hyphen


@pytest.mark.parametrize(
    ("first", "second", "book_words", "word_list", "expected"),
    [
        (
            "neces-",
            "sary",
            frozenset(),
            frozenset({"necessary"}),
            HyphenJoin("necessary", ChangeReason.HYPHEN_JOIN),
        ),
        (
            "Anglo-",
            "Saxon",
            frozenset({"anglo-saxon"}),
            frozenset(),
            HyphenJoin("Anglo-Saxon", ChangeReason.HYPHEN_KEPT),
        ),
        (
            "Bal-",
            "hazar",
            frozenset(),
            frozenset(),
            HyphenJoin("Balhazar", ChangeReason.HYPHEN_JOIN_GUESSED),
        ),
        (
            "neces-",
            "sary,",
            frozenset({"necessary"}),
            frozenset(),
            HyphenJoin("necessary,", ChangeReason.HYPHEN_JOIN),
        ),
        (
            "Nor-",
            "mandy.",
            frozenset(),
            frozenset({"normandy"}),
            HyphenJoin("Normandy.", ChangeReason.HYPHEN_JOIN),
        ),
        (
            "12th-",
            "century",
            frozenset(),
            frozenset({"12thcentury"}),
            HyphenJoin("12thcentury", ChangeReason.HYPHEN_JOIN),
        ),
        (
            "1830-",
            "40,",
            frozenset(),
            frozenset(),
            HyphenJoin("1830-40,", ChangeReason.HYPHEN_KEPT),
        ),
        (
            "1066-",
            "1087",
            frozenset({"10661087"}),
            frozenset({"10661087"}),
            HyphenJoin("1066-1087", ChangeReason.HYPHEN_KEPT),
        ),
        (
            "d'in-",
            "signes",
            frozenset(),
            frozenset({"insignes"}),
            HyphenJoin("d'insignes", ChangeReason.HYPHEN_JOIN),
        ),
        (
            "Wil-",
            "liam's",
            frozenset(),
            frozenset({"s"}),
            HyphenJoin("William's", ChangeReason.HYPHEN_JOIN_GUESSED),
        ),
        (
            "sea-",
            "faring",
            frozenset({"sea-faring", "seafaring"}),
            frozenset(),
            HyphenJoin("seafaring", ChangeReason.HYPHEN_JOIN),
        ),
    ],
    ids=[
        "word list",
        "book's compound",
        "guessed",
        "punctuation after",
        "word list in lower case",
        "letter after a digit",
        "two numbers",
        "a range of years",
        "after the apostrophe",
        "apostrophe in the second part",
        "printed both ways",
    ],
)
def test_join_hyphen_gives_the_word_and_its_reason(
    first: str,
    second: str,
    book_words: frozenset[str],
    word_list: frozenset[str],
    expected: HyphenJoin,
) -> None:
    assert join_hyphen(first, second, book_words, word_list) == expected


@pytest.mark.parametrize(
    ("first", "second"),
    [
        ("—", "and"),
        ("rep-", "(1)"),
        ("-", "and"),
        ("word", "and"),
        ("136-39-", "Bryce,"),
        ("37-", "Abacus"),
        ("37-", "abacus"),
    ],
    ids=[
        "dash",
        "bracket after",
        "hyphen alone",
        "no hyphen",
        "digit before, index",
        "digit before, capital",
        "digit before, lower case",
    ],
)
def test_join_hyphen_does_not_join(first: str, second: str) -> None:
    known = frozenset({"and", "136-39bryce", "37abacus"})
    assert join_hyphen(first, second, known, known) is None


@pytest.mark.parametrize(
    ("first", "second", "known", "expected"),
    [
        ("235-", "37-", frozenset(), "235-37-"),
        ("235-", "37-", frozenset({"23537-", "23537"}), "235-37-"),
        ("149-", "57;insouthernItaly,", frozenset(), "149-57;insouthernItaly,"),
    ],
    ids=["range in an index", "joined form known", "digits then letters"],
)
def test_join_after_a_digit_with_a_digit_always_keeps_the_hyphen(
    first: str, second: str, known: frozenset[str], expected: str
) -> None:
    # Haskins' index, pages 270 and 268.
    assert join_hyphen(first, second, known, known) == HyphenJoin(
        expected, ChangeReason.HYPHEN_KEPT
    )


def test_join_after_a_digit_with_a_non_ascii_digit_does_not_join() -> None:
    assert join_hyphen("37-", "²", frozenset(), frozenset()) is None


@pytest.mark.parametrize(
    ("first", "second", "book_words", "word_list", "expected"),
    [
        ("half-", "Danish", frozenset(), frozenset({"halfdanish"}), None),
        ("be-", "The", frozenset({"bethe"}), frozenset({"bethe"}), None),
        (
            "half-",
            "Danish",
            frozenset({"half-danish"}),
            frozenset(),
            HyphenJoin("half-Danish", ChangeReason.HYPHEN_KEPT),
        ),
        (
            "ANGLO-",
            "SAXON",
            frozenset(),
            frozenset({"anglosaxon"}),
            HyphenJoin("ANGLOSAXON", ChangeReason.HYPHEN_JOIN),
        ),
        (
            "tro-",
            "d",
            frozenset(),
            frozenset({"trod"}),
            HyphenJoin("trod", ChangeReason.HYPHEN_JOIN_GUESSED),
        ),
        (
            "tro-",
            "d.",
            frozenset({"trod"}),
            frozenset(),
            HyphenJoin("trod.", ChangeReason.HYPHEN_JOIN),
        ),
    ],
    ids=[
        "capital without evidence",
        "capital with a word-list key",
        "capital with the book's compound",
        "capitals on both sides",
        "one letter, word list",
        "one letter, book's words",
    ],
)
def test_join_hyphen_before_a_capital_or_a_single_letter(
    first: str,
    second: str,
    book_words: frozenset[str],
    word_list: frozenset[str],
    expected: HyphenJoin | None,
) -> None:
    assert join_hyphen(first, second, book_words, word_list) == expected


def test_hyphen_before_a_capital_without_evidence_leaves_both_words() -> None:
    page = PageLayout(0, (_body(70, "who was half-", "Danish in blood"),), ())
    blocks = make_blocks(_lines_of(page), frozenset({"halfdanish"}), workers=1)
    assert block_text(blocks.blocks[0]) == "who was half- Danish in blood"
    assert blocks.word_changes == ()


# Hyphens in the blocks


def test_hyphen_at_a_line_end_is_joined_inside_a_block_and_recorded() -> None:
    page = PageLayout(
        3,
        (
            _body(
                70,
                "it is neces-",
                "sary that the Anglo-",
                "Saxon king of Bal-",
                "hazar",
            ),
        ),
        (),
    )
    blocks = make_blocks(
        _lines_of(page, PageLayout(4, (_body(70, "an Anglo-Saxon thing"),), ())),
        frozenset({"necessary"}),
        workers=1,
    )
    assert block_text(blocks.blocks[0]) == (
        "it is necessary that the Anglo-Saxon king of Balhazar an Anglo-Saxon thing"
    )
    assert blocks.word_changes == (
        WordChange(
            page_index=3,
            before=("neces-", "sary"),
            after=("necessary",),
            reason=ChangeReason.HYPHEN_JOIN,
        ),
        WordChange(
            page_index=3,
            before=("Anglo-", "Saxon"),
            after=("Anglo-Saxon",),
            reason=ChangeReason.HYPHEN_KEPT,
        ),
        WordChange(
            page_index=3,
            before=("Bal-", "hazar"),
            after=("Balhazar",),
            reason=ChangeReason.HYPHEN_JOIN_GUESSED,
        ),
    )


def test_hyphen_is_joined_across_a_line_holding_only_a_reference_sign() -> None:
    # Haskins page 71: "fol-", a line "^", "lows:". The hyphen is joined
    # and the sign goes after the joined word (structure spec, section 5),
    # where it is linked to its note.
    body = _region(
        *_five_full_lines(70, "body")[:4],
        _full("and the text runs as fol-", 130),
        _spread("^", 80, 85, 140),
        _short("lows: an end.", 145),
    )
    band = _region(
        _note_line("* A note on it.", 300, 62, 160),
        _note_line("and its end.", 300 + _NOTE_PITCH_PT, 50, 120),
    )
    lines = _lines_of(PageLayout(0, (body, band), ()))
    blocks = make_blocks(lines, frozenset({"follows"}), workers=1)
    paragraph = blocks.blocks[0]
    assert tuple(span.text for span in paragraph.spans)[1:] == ("^", " an end.")
    assert paragraph.spans[0].text.endswith(" runs as follows: ")
    assert (
        WordChange(
            page_index=0,
            before=("fol-", "lows:"),
            after=("follows:",),
            reason=ChangeReason.HYPHEN_JOIN,
        )
        in blocks.word_changes
    )
    check_stage(FidelityBoundary.STRUCTURE, lines, blocks)


def test_line_of_one_word_between_two_hyphens_is_joined_twice() -> None:
    page = PageLayout(0, (_body(70, "the pre-", "anglo-", "saxon age"),), ())
    lines = _lines_of(page)
    blocks = make_blocks(lines, _NO_WORDS, workers=1)
    assert block_text(blocks.blocks[0]) == "the preanglosaxon age"
    assert tuple(change.before for change in blocks.word_changes) == (
        ("pre-", "anglo-"),
        ("preanglo-", "saxon"),
    )
    check_stage(FidelityBoundary.STRUCTURE, lines, blocks)


# "¬" at a line's end, the hyphen of the owner's OCR (spec section 5)


@pytest.mark.parametrize(
    ("first", "second", "book_words", "word_list", "expected"),
    [
        (
            "liter¬",
            "ature",
            frozenset(),
            frozenset({"literature"}),
            HyphenJoin("literature", ChangeReason.HYPHEN_JOIN),
        ),
        (
            "proto¬",
            "journalist",
            frozenset({"proto-journalist"}),
            frozenset(),
            HyphenJoin("proto-journalist", ChangeReason.HYPHEN_KEPT),
        ),
        (
            "Bal¬",
            "hazar",
            frozenset(),
            frozenset(),
            HyphenJoin("Balhazar", ChangeReason.HYPHEN_JOIN_GUESSED),
        ),
        (
            "1830¬",
            "40",
            frozenset(),
            frozenset(),
            HyphenJoin("1830-40", ChangeReason.HYPHEN_KEPT),
        ),
        (
            "half¬",
            "Danish",
            frozenset({"half-danish"}),
            frozenset(),
            HyphenJoin("half-Danish", ChangeReason.HYPHEN_KEPT),
        ),
        (
            "d'in¬",
            "signes",
            frozenset(),
            frozenset({"insignes"}),
            HyphenJoin("d'insignes", ChangeReason.HYPHEN_JOIN),
        ),
        (
            "tro¬",
            "d",
            frozenset(),
            frozenset({"trod"}),
            HyphenJoin("trod", ChangeReason.HYPHEN_JOIN_GUESSED),
        ),
    ],
    ids=[
        "word list",
        "book's compound",
        "guessed",
        "a range of years",
        "capital with the book's compound",
        "after the apostrophe",
        "one letter, word list",
    ],
)
def test_join_hyphen_takes_a_not_sign_as_a_hyphen_and_keeps_it_as_hyphen_minus(
    first: str,
    second: str,
    book_words: frozenset[str],
    word_list: frozenset[str],
    expected: HyphenJoin,
) -> None:
    assert join_hyphen(first, second, book_words, word_list) == expected


@pytest.mark.parametrize(
    ("first", "second"),
    [
        ("¬", "and"),
        ("liter¬", "(1)"),
        ("136-39¬", "Bryce,"),
        ("half¬", "Danish"),
        ("liter¬a", "ture"),
        ("liter~", "ature"),
    ],
    ids=[
        "not sign alone",
        "bracket after",
        "number before a word",
        "capital without evidence",
        "not sign inside the word",
        "tilde",
    ],
)
def test_join_hyphen_with_a_not_sign_does_not_join(first: str, second: str) -> None:
    known = frozenset({"and", "136-39bryce", "halfdanish", "literature"})
    assert join_hyphen(first, second, known, known) is None


def test_not_sign_at_a_line_end_is_joined_and_recorded_with_the_layer_words() -> None:
    page = PageLayout(
        3,
        (_body(70, "the liter¬", "ature of the Anglo¬", "Saxon age, 1830¬", "40"),),
        (),
    )
    lines = _lines_of(page)
    blocks = make_blocks(lines, frozenset({"literature"}), workers=1)
    assert block_text(blocks.blocks[0]) == (
        "the literature of the Anglo¬ Saxon age, 1830-40"
    )
    assert blocks.word_changes == (
        WordChange(
            page_index=3,
            before=("liter¬", "ature"),
            after=("literature",),
            reason=ChangeReason.HYPHEN_JOIN,
        ),
        WordChange(
            page_index=3,
            before=("1830¬", "40"),
            after=("1830-40",),
            reason=ChangeReason.HYPHEN_KEPT,
        ),
    )
    check_stage(FidelityBoundary.STRUCTURE, lines, blocks)


def test_not_sign_inside_a_line_is_left_as_text() -> None:
    page = PageLayout(0, (_body(70, "a ¬ sign and a¬b", "here"),), ())
    blocks = make_blocks(_lines_of(page), frozenset({"a¬bhere"}), workers=1)
    assert block_text(blocks.blocks[0]) == "a ¬ sign and a¬b here"
    assert blocks.word_changes == ()


def test_survey_book_words_leave_out_the_parts_of_a_word_broken_with_a_not_sign() -> (
    None
):
    page = PageLayout(
        0, (_body(70, "Of the liter¬", "ature, 136¬", "Bryce, 1066¬", "1087 here"),), ()
    )
    assert survey_book(_lines_of(page), workers=1).book_words == frozenset(
        {"of", "the", "136", "bryce", "here"}
    )


def test_indented_line_after_a_not_sign_does_not_start_a_paragraph() -> None:
    page = PageLayout(
        0,
        (
            _region(
                _full("Alpha beta gamma delta", 70),
                _short("the work of liter¬", 85),
                _indented("ature here and there", 100),
                _short("Britain, 136-39¬", 115),
                _indented("Bryce, James, 12", 130),
            ),
        ),
        (),
    )
    blocks = make_blocks(_lines_of(page), frozenset({"literature"}), workers=1)
    assert _texts(blocks.blocks) == (
        "Alpha beta gamma delta the work of literature here and there Britain, 136-39¬",
        "Bryce, James, 12",
    )


# Cases the review of work package 3 found untested


def test_indented_first_line_after_a_short_last_line_starts_at_a_page_break() -> None:
    pages = (
        _body_page(0, *_five_full_lines(70, "first"), _short("its end.", 145)),
        _body_page(1, _indented("A new one", 70), *_five_full_lines(85, "next")),
    )
    blocks = make_blocks(_lines_of(*pages), _NO_WORDS, workers=1)
    assert tuple(block.id for block in blocks.blocks) == ("b-p0000-001", "b-p0001-001")


def test_lone_number_at_the_left_of_the_foot_stays() -> None:
    foot = _foot_line(_FOOT_TOP_PT, ("4", 28))
    blocks = make_blocks(_lines_of(_page_with_foot(4, foot)), _NO_WORDS, workers=1)
    assert blocks.removals == ()


def test_number_in_brackets_off_the_middle_of_the_column_stays() -> None:
    # The column is 274 pt wide: 0.15 of it is 41.1 pt; "(49)" is 50 pt off.
    foot = _foot_line(_FOOT_TOP_PT, ("(49)", 162 + 50 - 10))
    blocks = make_blocks(_lines_of(_page_with_foot(4, foot)), _NO_WORDS, workers=1)
    assert blocks.removals == ()


def test_bracket_lines_not_alike_are_no_signature_lines() -> None:
    lines = (
        _signature_line("MARIÉJOL.", "Cath.", "de", "Médicis.", "(49)", "4"),
        _signature_line("Voyez", "aussi", "les", "lettres", "(12)", "x"),
    )
    pages = tuple(_page_with_foot(index, line) for index, line in enumerate(lines))
    blocks = make_blocks(_lines_of(*pages), _NO_WORDS, workers=1)
    assert blocks.removals == ()


def test_band_region_of_two_notes_gives_two_notes() -> None:
    band = _region(
        _spread("1 A note in small type", 50, 300, 300, height=7.0),
        _spread("that ends.", 50, 120, 309, height=7.0),
        _spread("2 Another note in small", 60, 300, 318, height=7.0),
        _spread("type.", 50, 80, 327, height=7.0),
    )
    page = PageLayout(0, (_region(*_five_full_lines(70, "first")), band), ())
    blocks = make_blocks(_lines_of(page), _NO_WORDS, workers=1)
    assert len(blocks.notes) == 2


@pytest.mark.parametrize(
    ("pitches", "running"), [(1.5, True), (2.0, True), (2.85, False)]
)
def test_head_below_the_median_by_pitches(pitches: float, running: bool) -> None:
    pages = (
        *(_page_with_head(index, "THE BOOK") for index in range(10, 14)),
        _page_with_head(14, "THE BOOK", head_top=36 + pitches * _PITCH_PT),
    )
    survey = survey_book(_lines_of(*pages), workers=1)
    assert survey.body_line_pitch == _PITCH_PT
    assert (14 in survey.running_heads) is running


@pytest.mark.parametrize(
    ("heads", "running"),
    [
        (("ABCDEFGH", "ABCDEFXY"), True),
        (("ABCDEFGHIJ", "ABCDEFGXYZ"), True),
        (("ABCDEFGHIJKLMNOPQRST", "ABCDEFGHIJKLMVWXYZVW"), False),
        (("ABCD", "ABCD"), True),
        (("ABC", "ABC"), False),
        (
            (
                "ABCDEFGHIJKLMNOPQRSTUVWXYZABCDE",
                "ABCDEFGHIJKLMNOPQRSTUVWXYZABCDEFGHIJKLMNOPQRS",
            ),
            True,
        ),
        (
            (
                "ABCDEFGHIJKLMNOPQRSTUVWXYZABCDE",
                "ABCDEFGHIJKLMNOPQRSTUVWXYZABCDEFGHIJKLMNOPQRST",
            ),
            False,
        ),
    ],
    ids=[
        "0.75 alike",
        "0.70 alike",
        "0.65 alike",
        "4 letters",
        "3 letters",
        "31 and 45 letters",
        "31 and 46 letters",
    ],
)
def test_heads_alike_at_the_bounds(heads: tuple[str, str], running: bool) -> None:
    pages = tuple(
        _page_with_head(index, head) for index, head in enumerate(heads, start=10)
    )
    survey = survey_book(_lines_of(*pages), workers=1)
    assert survey.running_heads == (frozenset({10, 11}) if running else frozenset())


def test_head_offset_of_a_tie_is_the_smaller() -> None:
    pages = (_page_with_head(10, "25 THE BOOK"), _page_with_head(11, "THE BOOK 24"))
    assert survey_book(_lines_of(*pages), workers=1).head_page_offset == -15


def test_of_two_head_numbers_and_no_offset_the_first_is_the_page_number() -> None:
    pages = (_page_with_head(3, "xii THE BOOK vii"), _page_with_head(4, "THE BOOK ix"))
    blocks = make_blocks(_lines_of(*pages), _NO_WORDS, workers=1)
    assert blocks.page_numbers[0] == PageNumber(3, "xii", PageNumberPosition.HEAD)


def _page_of_rows(index: int, rows: int, height: float) -> PageLayout:
    return _body_page(
        index,
        *(
            _line("a row of words", 50, 70 + 15 * row, height=height)
            for row in range(rows)
        ),
    )


def test_body_word_height_is_measured_on_pages_of_15_rows() -> None:
    pages = (
        _page_of_rows(0, 15, 10.0),
        _page_of_rows(1, 14, 7.0),
        _page_of_rows(2, 14, 7.0),
    )
    assert survey_book(_lines_of(*pages), workers=1).body_word_height == 10.0


@pytest.mark.parametrize(("indent", "starts"), [(40.0, True), (41.0, False)])
def test_indent_of_at_most_40_pt_starts_a_paragraph(
    indent: float, starts: bool
) -> None:
    page = _body_page(
        0,
        *_five_full_lines(70, "first"),
        _short("the end.", 145),
        _spread("A new one", _BODY_LEFT_PT + indent, _RIGHT_PT, 160),
    )
    blocks = make_blocks(_lines_of(page), _NO_WORDS, workers=1)
    assert len(blocks.blocks) == (2 if starts else 1)


@pytest.mark.parametrize(("right_inset", "centred"), [(30.0, True), (31.0, False)])
def test_insets_differing_by_at_most_10_pt_are_centred(
    right_inset: float, centred: bool
) -> None:
    lines = _five_full_lines(70, "first")
    page = _body_page(
        0,
        *lines[:3],
        _spread("A TITLE", _BODY_LEFT_PT + 20, _RIGHT_PT - right_inset, 115),
        *_five_full_lines(130, "after")[:3],
    )
    blocks = make_blocks(_lines_of(page), _NO_WORDS, workers=1)
    assert len(blocks.blocks) == (3 if centred else 1)


@pytest.mark.parametrize(
    ("words", "removed"),
    [
        ((("MA.", 200), ("4567", 230)), True),
        ((("MAB.", 200), ("4567", 230)), False),
        ((("b", 200), ("c", 215), ("4", 230)), True),
        ((("a", 185), ("b", 200), ("c", 215), ("4", 230)), False),
    ],
    ids=["6 letters and digits", "7", "3 words", "4 words"],
)
def test_signature_mark_limits(
    words: tuple[tuple[str, float], ...], removed: bool
) -> None:
    foot = _foot_line(_FOOT_TOP_PT, *words)
    blocks = make_blocks(_lines_of(_page_with_foot(4, foot)), _NO_WORDS, workers=1)
    assert bool(blocks.removals) is removed


@pytest.mark.parametrize(
    ("words", "removed"),
    [
        ((("M.", 37), ("c", 266)), True),
        ((("M.", 37), ("IT", 266)), True),
        ((("M.", 25), ("c", 25 + 0.9 * 274)), True),
        ((("M.", 37), ("c", 37 + 0.5 * 274)), True),
        ((("M.", 37), ("c", 173)), False),
        ((("m.", 37), ("c", 266)), False),
        ((("Mr.", 37), ("c", 266)), False),
    ],
    ids=[
        "M. c",
        "M. IT",
        "0.9 of the column",
        "half the column",
        "less than half the column",
        "lower case",
        "two letters",
    ],
)
def test_signature_mark_without_a_digit_is_a_capital_and_a_word_set_far_apart(
    words: tuple[tuple[str, float], ...], removed: bool
) -> None:
    # Gierke signs its introduction with letters, "M." at the left and "c"
    # at the right (page 38). The column is 274 pt wide: the second word
    # must start 137 pt or more right of the first's left side.
    foot = _foot_line(_FOOT_TOP_PT, *words)
    blocks = make_blocks(_lines_of(_page_with_foot(4, foot)), _NO_WORDS, workers=1)
    assert [removal.reason for removal in blocks.removals] == (
        [RemovalReason.SIGNATURE_MARK] if removed else []
    )


class _MarkRegion(StrEnum):
    """Where the mark lies on `_page_with_mark_beside`'s page: below the
    line before it in the same region, or first in a region of its own."""

    WITH_THE_LINE_BEFORE = "with the line before"
    OF_ITS_OWN = "of its own"


def _page_with_mark_beside(
    pitches_below_the_line_before: float,
    lowest_below_the_mark_pt: float,
    mark_region: _MarkRegion,
) -> PageLayout:
    """Domesday's page index 428 (spec section 4): a table's column whose
    last line, "Norfolk", has the mark "26—2" at the foot, the given
    pitches below it, and another column whose lowest word, "[0", the text
    layer boxes `lowest_below_the_mark_pt` lower than the mark (5 pt on
    that page)."""
    body = _region(*(_column_line(70 + _PITCH_PT * number) for number in range(6)))
    before = _foot_line(
        _FOOT_TOP_PT - pitches_below_the_line_before * _PITCH_PT, ("Norfolk", 252)
    )
    mark = _foot_line(_FOOT_TOP_PT, ("26—2", 252))
    lower = _region(_foot_line(_FOOT_TOP_PT + lowest_below_the_mark_pt, ("[0", 40)))
    match mark_region:
        case _MarkRegion.WITH_THE_LINE_BEFORE:
            table: tuple[Region, ...] = (_region(before, mark),)
        case _MarkRegion.OF_ITS_OWN:
            table = (_region(before), _region(mark))
        case _:
            assert_never(mark_region)
    return PageLayout(4, (body, *table, lower), ())


@pytest.mark.parametrize(
    ("pitches_below", "lowest_below_pt", "mark_region", "removed"),
    [
        (3.0, 5.0, _MarkRegion.WITH_THE_LINE_BEFORE, True),
        (1.9, 5.0, _MarkRegion.WITH_THE_LINE_BEFORE, False),
        (3.0, _PITCH_PT, _MarkRegion.WITH_THE_LINE_BEFORE, False),
        (3.0, 5.0, _MarkRegion.OF_ITS_OWN, False),
    ],
    ids=[
        "3 pitches below the line before",
        "1.9 pitches below the line before",
        "a pitch above the lowest line",
        "first in its region",
    ],
)
def test_signature_mark_beside_a_lower_line_is_removed_when_set_apart(
    pitches_below: float,
    lowest_below_pt: float,
    mark_region: _MarkRegion,
    removed: bool,
) -> None:
    # The mark is removed only when its bottom lies less than a pitch above
    # the lowest line's and its top 2 pitches or more below the top of the
    # line before it in its region; each case but the first breaks one.
    page = _page_with_mark_beside(pitches_below, lowest_below_pt, mark_region)
    blocks = make_blocks(_lines_of(page), _NO_WORDS, workers=1)
    assert [(removal.text, removal.reason) for removal in blocks.removals] == (
        [("26—2", RemovalReason.SIGNATURE_MARK)] if removed else []
    )


@pytest.mark.parametrize(("shift", "removed"), [(0.05, True), (-0.05, False)])
def test_signature_mark_at_0_3_of_the_column_from_its_left_edge(
    shift: float, removed: bool
) -> None:
    # The column runs from 25 to 299 pt: 0.3 of it from its left edge is at
    # 107.2 pt; "4—2" is 15 pt wide.
    middle = _COLUMN_LEFT_PT + 0.3 * (_COLUMN_RIGHT_PT - _COLUMN_LEFT_PT) + shift
    foot = _foot_line(_FOOT_TOP_PT, ("4—2", middle - 7.5))
    blocks = make_blocks(_lines_of(_page_with_foot(4, foot)), _NO_WORDS, workers=1)
    assert bool(blocks.removals) is removed


@pytest.mark.parametrize(("width", "margin"), [(62.4, True), (62.5, False)])
def test_margin_region_is_narrower_than_a_quarter_of_the_widest(
    width: float, margin: bool
) -> None:
    page = PageLayout(
        0,
        (
            _region(*_five_full_lines(70, "first")),
            _region(_spread("Margin note", 310, 310 + width, 85)),
        ),
        (),
    )
    blocks = make_blocks(_lines_of(page), _NO_WORDS, workers=1)
    assert (BlockKind.MARGIN_NOTE in {block.kind for block in blocks.blocks}) is margin


def test_word_changes_are_in_page_order_a_band_join_before_the_next_page() -> None:
    band = _region(
        _spread("1 It was neces-", 50, 200, 300, height=7.0),
        _spread("sary.", 50, 80, 309, height=7.0),
    )
    pages = (
        PageLayout(0, (_region(*_five_full_lines(70, "first")), band), ()),
        _body_page(1, *_five_full_lines(70, "second"), _full("a hyphen-", 145)),
        _body_page(2, _full("ated word", 70), *_five_full_lines(85, "third")),
    )
    blocks = make_blocks(
        _lines_of(*pages), frozenset({"necessary", "hyphenated"}), workers=1
    )
    assert tuple(change.page_index for change in blocks.word_changes) == (0, 1)


def test_paragraph_runs_on_over_a_plate_and_a_blank_page() -> None:
    # Spec section 6: a page with no body stream does not end the paragraph,
    # and a plate's lines are not in the body stream (section 18).
    plate = PageLayout(
        1,
        (_region(_spread(", ' ..", 60, 90, 300)),),
        (
            Figure(
                box=Box(0, 0, 400, 600),
                image="images/plate-0001.png",
                dpi=300,
                kind=FigureKind.PLATE,
            ),
        ),
    )
    pages = (
        _body_page(0, *_five_full_lines(70, "first")),
        plate,
        PageLayout(2, (), ()),
        _body_page(3, *_five_full_lines(70, "third")),
    )
    blocks = make_blocks(_lines_of(*pages), _NO_WORDS, workers=1)
    assert tuple((block.id, block.kind) for block in blocks.blocks) == (
        ("b-p0000-001", BlockKind.PARAGRAPH),
        ("b-p0001-001", BlockKind.FIGURE),
    )
    assert tuple(origin.page_index for origin in blocks.blocks[0].origin) == (0, 3)


def test_u_and_a_digit_centred_at_the_foot_is_a_page_number() -> None:
    foot = _foot_line(_FOOT_TOP_PT, _centred("U9"))
    blocks = make_blocks(_lines_of(_page_with_foot(4, foot)), _NO_WORDS, workers=1)
    assert blocks.page_numbers == (PageNumber(4, "U9", PageNumberPosition.FOOT),)


def test_side_text_keeps_the_order_of_its_regions_and_lines() -> None:
    band = _region(
        _spread("1 The first note.", 50, 150, 300, height=7.0),
        _spread("2 The second note.", 60, 160, 309, height=7.0),
    )
    page = PageLayout(
        0,
        (
            _region(*_five_full_lines(70, "first")),
            _region(_spread("Upper", 310, 340, 75)),
            _region(_spread("Lower", 310, 340, 130)),
            band,
        ),
        (),
    )
    blocks = make_blocks(_lines_of(page), _NO_WORDS, workers=1)
    # Both stand beside the paragraph, Lower 3 pitches below Upper's bottom.
    assert _texts(blocks.blocks)[:2] == ("Upper", "Lower")
    assert tuple(
        (note.marker, block_text(note.blocks[0])) for note in blocks.notes
    ) == (("1", "The first note."), ("2", "The second note."))


# make_blocks

_HASH = "a" * 64
_LINES = LinesFile(
    source_pdf_sha256=_HASH,
    pages=(
        PageLayout(0, (_REGION,), ()),
        PageLayout(1, (), ()),
        PageLayout(2, (replace(_REGION, lines=(_SECOND_LINE,)),), ()),
    ),
    rereads=(),
)


# Paragraphs, side text and the order of the blocks. The body's lines run
# from 50 to 300 pt; a full line reaches 300.

_RIGHT_PT = 300.0


def _spread(text: str, x0: float, x1: float, top: float, height: float = 10.0) -> Line:
    """A line of the words of `text`, the first starting at `x0` and the last
    ending at `x1`."""
    parts = text.split(" ")
    step = (x1 - x0) / len(parts)
    words = tuple(
        Word(part, Box(x0 + step * n, top, x0 + step * (n + 1) - 2, top + height), None)
        for n, part in enumerate(parts)
    )
    words = (*words[:-1], replace(words[-1], box=replace(words[-1].box, x1=x1)))
    return Line(_box(tuple(word.box for word in words)), words)


def _full(text: str, top: float) -> Line:
    return _spread(text, _BODY_LEFT_PT, _RIGHT_PT, top)


def _short(text: str, top: float) -> Line:
    return _spread(text, _BODY_LEFT_PT, 150, top)


def _indented(text: str, top: float) -> Line:
    return _spread(text, _BODY_LEFT_PT + 20, _RIGHT_PT, top)


def _texts(blocks: tuple[Block, ...]) -> tuple[str, ...]:
    return tuple(block_text(block) for block in blocks)


def test_indented_line_after_a_short_one_starts_a_paragraph_after_a_full_one_not() -> (
    None
):
    page = PageLayout(
        0,
        (
            _region(
                _full("Alpha beta gamma delta", 70),
                _full("epsilon zeta eta theta", 85),
                _short("iota kappa.", 100),
                _indented("Lambda mu nu xi", 115),
                _full("omicron pi rho sigma", 130),
                _indented("Tau upsilon phi", 145),
            ),
        ),
        (),
    )
    blocks = make_blocks(_lines_of(page), _NO_WORDS, workers=1)
    assert _texts(blocks.blocks) == (
        "Alpha beta gamma delta epsilon zeta eta theta iota kappa.",
        "Lambda mu nu xi omicron pi rho sigma Tau upsilon phi",
    )
    assert tuple(block.id for block in blocks.blocks) == ("b-p0000-001", "b-p0000-002")


def test_centred_line_is_a_paragraph_of_its_own() -> None:
    page = PageLayout(
        0,
        (
            _region(
                _full("Alpha beta gamma delta", 70),
                _full("epsilon zeta eta theta", 85),
                _spread("CHAPTER II", 150, 200, 100),
                _full("iota kappa lambda mu", 115),
                _full("nu xi omicron pi", 130),
            ),
        ),
        (),
    )
    blocks = make_blocks(_lines_of(page), _NO_WORDS, workers=1)
    assert _texts(blocks.blocks) == (
        "Alpha beta gamma delta epsilon zeta eta theta",
        "CHAPTER II",
        "iota kappa lambda mu nu xi omicron pi",
    )


def test_centred_title_in_a_region_of_its_own_starts_a_paragraph_on_a_new_page() -> (
    None
):
    # The title's region is its one line, so its own edges would make no
    # line centred; it is measured against the body column, 50 to 300 pt.
    pages = (
        _body_page(0, *_five_full_lines(70, "first"), _full("runs on to", 145)),
        PageLayout(
            1,
            (
                _region(_spread("CHAPTER II", 150, 200, 40)),
                _region(*_five_full_lines(70, "second")),
            ),
            (),
        ),
    )
    blocks = make_blocks(_lines_of(*pages), _NO_WORDS, workers=1)
    assert tuple(block.id for block in blocks.blocks) == (
        "b-p0000-001",
        "b-p0001-001",
        "b-p0001-002",
    )
    assert block_text(blocks.blocks[1]) == "CHAPTER II"


def test_indented_line_after_a_hyphen_does_not_start_a_paragraph() -> None:
    page = PageLayout(
        0,
        (
            _region(
                _full("Alpha beta gamma delta", 70),
                _full("epsilon zeta eta theta", 85),
                _short("the work of neces-", 100),
                _indented("sary things here", 115),
                _full("omicron pi rho sigma", 130),
            ),
        ),
        (),
    )
    blocks = make_blocks(_lines_of(page), frozenset({"necessary"}), workers=1)
    assert _texts(blocks.blocks) == (
        (
            "Alpha beta gamma delta epsilon zeta eta theta the work of necessary "
            "things here omicron pi rho sigma"
        ),
    )


def test_indented_line_after_a_number_and_hyphen_starts_a_paragraph() -> None:
    page = PageLayout(
        0,
        (
            _region(
                _full("Alpha beta gamma delta", 70),
                _short("Britain, 136-39-", 85),
                _indented("Bryce, James, 12", 100),
                _short("Bari, 1066-", 115),
                _indented("1087 and later", 130),
            ),
        ),
        (),
    )
    blocks = make_blocks(_lines_of(page), _NO_WORDS, workers=1)
    assert _texts(blocks.blocks) == (
        "Alpha beta gamma delta Britain, 136-39-",
        "Bryce, James, 12 Bari, 1066-1087 and later",
    )


def _body_page(index: int, *lines: Line) -> PageLayout:
    return PageLayout(index, (_region(*lines),), ())


def _five_full_lines(top: float, word: str) -> tuple[Line, ...]:
    return tuple(
        _full(f"{word} {n} of the page", top + _PITCH_PT * n) for n in range(5)
    )


def test_page_not_indented_continues_the_paragraph_across_a_blank_page() -> None:
    pages = (
        _body_page(0, *_five_full_lines(70, "first"), _full("and a hyphen-", 145)),
        PageLayout(1, (), ()),
        _body_page(
            2,
            _full("ated word goes on", 70),
            *_five_full_lines(85, "third")[:3],
            _short("the end.", 130),
            _indented("A new one", 145),
        ),
    )
    lines = _lines_of(*pages)
    blocks = make_blocks(lines, frozenset({"hyphenated"}), workers=1)
    first, second = blocks.blocks
    assert first.id == "b-p0000-001"
    assert tuple(origin.page_index for origin in first.origin) == (0, 2)
    assert first.origin[1].box == _box(
        tuple(line.box for line in pages[2].regions[0].lines[:5])
    )
    assert "and a hyphenated word goes on" in block_text(first)
    assert block_text(first).endswith("the end.")
    assert (second.id, block_text(second)) == ("b-p0002-001", "A new one")
    assert blocks.word_changes == (
        WordChange(
            page_index=0,
            before=("hyphen-", "ated"),
            after=("hyphenated",),
            reason=ChangeReason.HYPHEN_JOIN,
        ),
    )
    check_stage(FidelityBoundary.STRUCTURE, lines, blocks)


# Plates (spec section 18)

_PLATE_BOX = Box(0, 0, 400, 600)


def _plate(index: int, *lines: Line) -> PageLayout:
    """A plate page: its figure, the whole page, and `lines` in one region."""
    return PageLayout(
        index,
        (_region(*lines),) if lines else (),
        (
            Figure(
                box=_PLATE_BOX,
                image=f"images/plate-{index:04d}.png",
                dpi=300,
                kind=FigureKind.PLATE,
            ),
        ),
    )


def _removed(blocks: BlocksFile, page_index: int) -> tuple[tuple[str, str], ...]:
    return tuple(
        (removal.reason.value, removal.text)
        for removal in blocks.removals
        if removal.page_index == page_index
    )


def test_plate_text_lines_removed_and_figure_block_without_text_follows_paragraph() -> (
    None
):
    # Two lines of stray words and no caption, as on Kadesh's page 16 (the
    # scan of a cover, which the configs exclude, the owner found).
    pages = (
        _body_page(0, *_five_full_lines(70, "first"), _full("runs on to", 145)),
        _plate(1, _spread("^U;L", 60, 90, 627), _spread(", ' ..", 60, 90, 222)),
        _body_page(2, *_five_full_lines(70, "second")),
    )
    lines = _lines_of(*pages)
    blocks = make_blocks(lines, _NO_WORDS, workers=1)
    # Removals go from the top down (spec section 7).
    assert _removed(blocks, 1) == (("plate_text", ", ' .."), ("plate_text", "^U;L"))
    assert blocks.blocks[1] == Block(
        id="b-p0001-001",
        kind=BlockKind.FIGURE,
        level=None,
        label=None,
        spans=(),
        figure="images/plate-0001.png",
        origin=(Origin(1, _PLATE_BOX),),
    )
    assert len(blocks.blocks) == 2
    assert tuple(origin.page_index for origin in blocks.blocks[0].origin) == (0, 2)
    assert "runs on to second 0 of the page" in block_text(blocks.blocks[0])
    check_stage(FidelityBoundary.STRUCTURE, lines, blocks)


def test_caption_lines_have_two_known_words_or_half_their_words_known() -> None:
    plate = _plate(
        1,
        _spread("THE MODERN MOUND OF KADESH", 60, 300, 100),
        _spread("^X.^ MoulslVl^rf", 60, 300, 300),
        _spread("Fir ^X", 60, 300, 400),
        _spread("Fir </ I", 60, 300, 450),
        # 2 known words of 5: a caption row by the first test alone.
        _spread("THE MOUND X;; Q< ^l", 60, 300, 475),
        _spread("17]", 60, 90, 500),
    )
    pages = (_body_page(0, *_five_full_lines(70, "first")), plate)
    lines = _lines_of(*pages)
    known = frozenset({"the", "modern", "mound", "of", "fir"})
    blocks = make_blocks(lines, known, workers=1)
    assert _removed(blocks, 1) == (
        ("plate_text", "^X.^ MoulslVl^rf"),
        ("plate_text", "Fir </ I"),
    )
    figure = blocks.blocks[-1]
    assert figure.kind is BlockKind.FIGURE
    assert block_text(figure) == (
        "THE MODERN MOUND OF KADESH Fir ^X THE MOUND X;; Q< ^l 17]"
    )
    check_stage(FidelityBoundary.STRUCTURE, lines, blocks)


def test_caption_is_decided_per_row_so_a_garbled_word_beside_it_stays() -> None:
    # Spec section 18, rule 2: Kadesh 48's "LUXOR", read "l.i v IK" in a
    # line of its own, beside "RELIEFS; THE" on its row, is kept; a row of
    # unknown words alone is removed.
    plate = _plate(
        1,
        _spread("l.i v IK", 60, 110, 500),
        _spread("RELIEFS; THE", 120, 300, 500),
        _spread("^X.^ MoulslVl^rf", 60, 300, 540),
    )
    pages = (_body_page(0, *_five_full_lines(70, "first")), plate)
    lines = _lines_of(*pages)
    blocks = make_blocks(lines, frozenset({"reliefs", "the"}), workers=1)
    assert _removed(blocks, 1) == (("plate_text", "^X.^ MoulslVl^rf"),)
    assert block_text(blocks.blocks[-1]) == "l.i v IK RELIEFS; THE"
    check_stage(FidelityBoundary.STRUCTURE, lines, blocks)


def test_caption_hyphen_is_joined_and_a_number_at_the_plate_foot_stays_caption() -> (
    None
):
    # Spec section 18: section 4 does not run on a plate page.
    plate = _plate(
        1,
        _spread("A LAND OF VIL-", 60, 300, 500),
        _spread("LAGES OF OLD", 60, 300, 515),
        _spread("17", 190, 210, 560),
    )
    pages = (_body_page(0, *_five_full_lines(70, "first")), plate)
    lines = _lines_of(*pages)
    blocks = make_blocks(
        lines, frozenset({"land", "of", "villages", "a", "old"}), workers=1
    )
    assert block_text(blocks.blocks[-1]) == "A LAND OF VILLAGES OF OLD 17"
    assert blocks.page_numbers == ()
    check_stage(FidelityBoundary.STRUCTURE, lines, blocks)


def test_caption_gets_its_spaced_sign_attached_and_its_glued_word_split() -> None:
    # Spec section 2, the paragraph after the steps: a figure's caption,
    # made after the references, gets the case split (section 24) and the
    # spaced signs (section 23). "of" is printed after a line's first word
    # 10 times, and the book prints "Kadesh" whole.
    plate = _plate(1, _spread("THE BATTLE ; ofKadesh AT Kadesh", 60, 300, 500))
    pages = (
        _body_page(0, *_five_full_lines(70, "first")),
        plate,
        _body_page(2, *_five_full_lines(70, "second")),
    )
    lines = _lines_of(*pages)
    known = frozenset({"the", "battle", "of", "at", "kadesh"})
    blocks = make_blocks(lines, known, workers=1)
    (figure,) = (block for block in blocks.blocks if block.kind is BlockKind.FIGURE)
    assert block_text(figure) == "THE BATTLE; of Kadesh AT Kadesh"
    assert tuple(
        change
        for change in blocks.word_changes
        if change.reason in {ChangeReason.PUNCTUATION_ATTACHED, ChangeReason.CASE_SPLIT}
    ) == (
        WordChange(
            page_index=1,
            before=("BATTLE", ";"),
            after=("BATTLE;",),
            reason=ChangeReason.PUNCTUATION_ATTACHED,
        ),
        WordChange(
            page_index=1,
            before=("ofKadesh",),
            after=("of", "Kadesh"),
            reason=ChangeReason.CASE_SPLIT,
        ),
    )
    check_stage(FidelityBoundary.STRUCTURE, lines, blocks)


def test_caption_lines_are_read_from_the_top_down_whatever_their_regions() -> None:
    # Domesday 39: layout put "17]" and the caption in a region after the
    # one of "Between pp. 16 —", which stands left of "17]" on its line.
    plate = PageLayout(
        1,
        (
            _region(_spread("Between pp. 16 —", 28, 80, 626)),
            _region(
                _spread("A LAND OF VILLAGES", 150, 240, 597),
                _spread("17]", 84, 90, 626),
            ),
        ),
        (
            Figure(
                box=_PLATE_BOX,
                image="images/plate-0001.png",
                dpi=300,
                kind=FigureKind.PLATE,
            ),
        ),
    )
    pages = (_body_page(0, *_five_full_lines(70, "first")), plate)
    known = frozenset({"between", "land", "of", "villages", "a", "pp"})
    blocks = make_blocks(_lines_of(*pages), known, workers=1)
    assert block_text(blocks.blocks[-1]) == "A LAND OF VILLAGES Between pp. 16 — 17]"


def test_plate_topmost_line_alike_to_another_plates_is_a_running_head() -> None:
    # Kadesh's "DECENNIAL PUBLICATIONS, V" on its plates, no head line by
    # section 3 since it shares its region with the caption; the third
    # plate's garbled head is not alike and stays a caption line.
    known = frozenset({"plate", "publications"})
    pages = (
        _body_page(0, *_five_full_lines(70, "first")),
        _plate(
            1,
            _spread("DECENNIAL PUBLICATIONS, V", 60, 300, 191),
            _spread("PLATE II", 60, 300, 520),
        ),
        _plate(
            2,
            _spread("DECENNIAL PUBLICATIONS, V", 60, 300, 185),
            _spread("PLATE III", 60, 300, 520),
        ),
        _plate(
            3,
            _spread("l>i .• I:N\\IAL PUBLICATIONS, PLATE VIII", 60, 300, 166),
            _spread("PLATE IX", 60, 300, 520),
        ),
    )
    lines = _lines_of(*pages)
    blocks = make_blocks(lines, known, workers=1)
    assert _removed(blocks, 1) == (("running_head", "DECENNIAL PUBLICATIONS, V"),)
    assert _removed(blocks, 2) == (("running_head", "DECENNIAL PUBLICATIONS, V"),)
    assert _removed(blocks, 3) == ()
    assert _texts(blocks.blocks)[1:] == (
        "PLATE II",
        "PLATE III",
        "l>i .• I:N\\IAL PUBLICATIONS, PLATE VIII PLATE IX",
    )
    check_stage(FidelityBoundary.STRUCTURE, lines, blocks)


def test_plate_topmost_lines_that_differ_only_in_a_numeral_are_kept() -> None:
    # Spec section 18, rule 1: plate labels at the top of each plate.
    known = frozenset({"plate", "battle", "of", "the", "camp", "kadesh"})
    pages = (
        _body_page(0, *_five_full_lines(70, "first")),
        _plate(1, _spread("PLATE II", 60, 300, 50), _spread("THE CAMP", 60, 300, 520)),
        _plate(
            2, _spread("PLATE III", 60, 300, 50), _spread("THE BATTLE", 60, 300, 520)
        ),
        _plate(3, _spread("PLATE 4", 60, 300, 50), _spread("OF KADESH", 60, 300, 520)),
        _plate(4, _spread("PLATE 5", 60, 300, 50), _spread("THE CAMP", 60, 300, 520)),
    )
    blocks = make_blocks(_lines_of(*pages), known, workers=1)
    assert all(_removed(blocks, page) == () for page in range(1, 5))
    assert _texts(blocks.blocks)[1:] == (
        "PLATE II THE CAMP",
        "PLATE III THE BATTLE",
        "PLATE 4 OF KADESH",
        "PLATE 5 THE CAMP",
    )


def test_plate_topmost_line_alike_to_a_running_head_of_the_book_is_removed() -> None:
    heads = tuple(
        _page_with_head(index, head)
        for index, head in enumerate(_HEADS_WITHOUT_NUMBERS, start=10)
    )
    plate = _plate(
        16, _spread("THE BOOK", 60, 300, 200), _spread("PLATE II", 60, 300, 500)
    )
    blocks = make_blocks(_lines_of(*heads, plate), frozenset({"plate"}), workers=1)
    assert _removed(blocks, 16) == (("running_head", "THE BOOK"),)
    assert block_text(blocks.blocks[-1]) == "PLATE II"


def test_hyphen_before_a_plate_page_is_joined_with_the_word_after_it() -> None:
    pages = (
        _body_page(0, *_five_full_lines(70, "first"), _full("we repli-", 145)),
        _plate(1, _spread("^U;L", 60, 90, 627)),
        _body_page(2, _full("cate the text", 70), *_five_full_lines(85, "third")),
    )
    blocks = make_blocks(_lines_of(*pages), frozenset({"replicate"}), workers=1)
    assert tuple(block.kind for block in blocks.blocks) == (
        BlockKind.PARAGRAPH,
        BlockKind.FIGURE,
    )
    assert "we replicate the text" in block_text(blocks.blocks[0])


def test_figure_block_after_a_number_and_hyphen_and_before_the_next_paragraph() -> None:
    # "136-39-" is a number before a word, not a hyphen to join, and the
    # indented "Bryce," after the short line starts a paragraph.
    pages = (
        _body_page(0, *_five_full_lines(70, "first"), _short("Britain, 136-39-", 145)),
        _plate(1, _spread("Plate one", 60, 300, 160)),
        _body_page(2, _indented("Bryce, James, 12", 70), _full("and so on", 85)),
    )
    blocks = make_blocks(_lines_of(*pages), frozenset({"plate", "one"}), workers=1)
    assert _texts(blocks.blocks)[1:] == ("Plate one", "Bryce, James, 12 and so on")
    assert block_text(blocks.blocks[0]).endswith("Britain, 136-39-")
    assert blocks.word_changes == ()


def test_figure_block_of_a_plate_without_a_text_layer_has_no_spans() -> None:
    pages = (
        _body_page(0, *_five_full_lines(70, "first")),
        _plate(1),
        _plate(2),
    )
    blocks = make_blocks(_lines_of(*pages), _NO_WORDS, workers=1)
    assert tuple(
        (block.kind, block.spans, block.figure) for block in blocks.blocks
    ) == (
        (BlockKind.PARAGRAPH, blocks.blocks[0].spans, None),
        (BlockKind.FIGURE, (), "images/plate-0001.png"),
        (BlockKind.FIGURE, (), "images/plate-0002.png"),
    )


def test_figure_block_of_a_plate_before_any_body_comes_first() -> None:
    pages = (_plate(0), _body_page(1, *_five_full_lines(70, "first")))
    blocks = make_blocks(_lines_of(*pages), _NO_WORDS, workers=1)
    assert tuple(block.id for block in blocks.blocks) == ("b-p0000-001", "b-p0001-001")
    assert blocks.blocks[0].kind is BlockKind.FIGURE


# A hyphen lost in a margin note (spec section 5)

_LOST_WORD_LIST = frozenset({"national", "movement", "inspite", "ofthe", "apiece"})


@pytest.mark.parametrize(
    ("first", "second", "book_words", "joined"),
    [
        # Domesday page 77, Gierke page 88, Domesday page 75.
        ("nation", "al", frozenset(), "national"),
        ("move.", "ment,", frozenset(), "movement,"),
        ("unfree", "dom", frozenset({"unfreedom"}), "unfreedom"),
    ],
)
def test_join_lost_hyphen_joins_a_fragment_into_a_known_word(
    first: str, second: str, book_words: frozenset[str], joined: str
) -> None:
    assert join_lost_hyphen(
        first, second, book_words, _LOST_WORD_LIST, frozenset({"the"})
    ) == HyphenJoin(joined, ChangeReason.HYPHEN_LOST)


@pytest.mark.parametrize(
    ("first", "second"),
    [
        ("of", "the"),  # "the" is printed inside lines more than 8 times
        ("a", "piece"),  # a first part of 1 letter
        ("nation", "Al"),  # a capital
        ("nation-", "al"),  # a hyphen: join_hyphen's
        ("nation,", "al"),  # a comma is no misread hyphen
        ("nation..", "al"),  # one full stop only
        ("unfree", "dom"),  # "unfreedom" is not known here
        ("nation", "al,x"),  # "nationalx" is not known
    ],
)
def test_join_lost_hyphen_does_not_join(first: str, second: str) -> None:
    assert (
        join_lost_hyphen(first, second, _NO_WORDS, _LOST_WORD_LIST, frozenset({"the"}))
        is None
    )


@pytest.mark.parametrize("first", ["AD1066", "(nation)", "nation)."])
def test_join_lost_hyphen_needs_a_letter_before_the_break(first: str) -> None:
    # A first word ending in a digit or a closing mark is no part of a word
    # broken at a line end, though the book prints the joined form.
    book_words = frozenset({word_key(first.removesuffix(".") + "al")})
    assert join_lost_hyphen(first, "al", book_words, _NO_WORDS, frozenset()) is None


def test_join_lost_hyphen_takes_the_word_list_only_for_2_letters_or_more() -> None:
    # As for hyphen_join: "posi." "t" is not looked up in the word list.
    assert (
        join_lost_hyphen("posi.", "t", _NO_WORDS, frozenset({"posit"}), frozenset())
        is None
    )
    assert join_lost_hyphen(
        "posi.", "t", frozenset({"posit"}), _NO_WORDS, frozenset()
    ) == HyphenJoin("posit", ChangeReason.HYPHEN_LOST)


def test_survey_common_inner_words_are_printed_after_a_lines_first_word_9_times() -> (
    None
):
    # "the" after the first word of 8 lines, and first in 9 more: not
    # common; after the first word of a 9th line, common.
    eight = PageLayout(0, (_body(70, *(("of the",) * 8), *(("the end",) * 9)),), ())
    assert survey_book(_lines_of(eight), workers=1).common_inner_words == frozenset(
        {"end"}
    )
    nine = PageLayout(1, (_body(70, "of the"),), ())
    assert survey_book(
        _lines_of(eight, nine), workers=1
    ).common_inner_words == frozenset({"the", "end"})


def _lost_hyphen_pages() -> tuple[PageLayout, ...]:
    """Page 0: a body of five full lines, two ending with a word the next
    line goes on with ("in" "spite", "of" "the"), and two margin notes,
    "The villein and nation al justice." and "Unity of the move. ment,".
    "the" is printed after the first word of a line 9 times, so "of"
    "the" is not joined into "ofthe", which the word list holds."""
    margin = _region(
        _spread("The villein", 310, 340, 85),
        _spread("and nation", 310, 340, 97),
        _spread("al justice.", 310, 340, 109),
    )
    second = _region(
        _spread("Unity of", 310, 340, 160),
        _spread("the move.", 310, 340, 172),
        _spread("ment,", 310, 340, 184),
    )
    body = _region(
        _full("first of the page and the in", 70),
        _full("spite of the page went on of", 85),
        _full("the page and so of the end of the", 100),
        _full("page of the page and of the page", 115),
        _full("the end of the page for the all.", 130),
    )
    return (PageLayout(0, (body, margin, second), ()),)


def test_margin_note_joins_a_word_whose_hyphen_was_lost_and_the_body_does_not() -> None:
    lines = _lines_of(*_lost_hyphen_pages())
    blocks = make_blocks(lines, _LOST_WORD_LIST, workers=1)
    assert tuple((block.kind, block_text(block)) for block in blocks.blocks) == (
        (BlockKind.MARGIN_NOTE, "The villein and national justice."),
        (BlockKind.MARGIN_NOTE, "Unity of the movement,"),
        (
            BlockKind.PARAGRAPH,
            (
                "first of the page and the in spite of the page went on of the page "
                "and so of the end of the page of the page and of the page the end of "
                "the page for the all."
            ),
        ),
    )
    assert blocks.word_changes == (
        WordChange(
            page_index=0,
            before=("nation", "al"),
            after=("national",),
            reason=ChangeReason.HYPHEN_LOST,
        ),
        WordChange(
            page_index=0,
            before=("move.", "ment,"),
            after=("movement,",),
            reason=ChangeReason.HYPHEN_LOST,
        ),
    )
    check_stage(FidelityBoundary.STRUCTURE, lines, blocks)


def _side_text_pages() -> tuple[PageLayout, ...]:
    """Page 0: a body whose last paragraph runs on to page 1, a margin note
    right of the body, and a band of small type below it; page 1: the
    paragraph's end and a new paragraph."""
    margin = _region(_spread("Margin", 310, 340, 85), _spread("note", 310, 330, 97))
    band = _region(
        _spread("1 A note in small", 50, 300, 300, height=7.0),
        _spread("type.", 50, 80, 309, height=7.0),
    )
    page_0 = PageLayout(
        0,
        (
            _region(*_five_full_lines(70, "first"), _full("runs on to", 145)),
            margin,
            band,
        ),
        (),
    )
    page_1 = _body_page(
        1,
        _full("the next page", 70),
        *_five_full_lines(85, "second")[:3],
        _short("its end.", 130),
        _indented("Another paragraph", 145),
    )
    return page_0, page_1


def test_margin_note_before_and_band_after_the_paragraph_the_page_ends_in() -> None:
    lines = _lines_of(*_side_text_pages())
    blocks = make_blocks(lines, _NO_WORDS, workers=1)
    assert tuple((block.id, block.kind) for block in blocks.blocks) == (
        ("b-p0000-001", BlockKind.MARGIN_NOTE),
        ("b-p0000-002", BlockKind.PARAGRAPH),
        ("b-p0001-001", BlockKind.PARAGRAPH),
    )
    assert tuple(origin.page_index for origin in blocks.blocks[1].origin) == (0, 1)
    assert block_text(blocks.blocks[0]) == "Margin note"
    assert block_text(blocks.blocks[2]) == "Another paragraph"
    (note,) = blocks.notes
    assert (note.id, note.marker, note.referenced) == ("n-p0000-001", "1", False)
    # Markdown writes the note after the paragraph, the last block whose
    # first origin is page 0, so its block is the third to start there.
    assert tuple((block.id, block.kind) for block in note.blocks) == (
        ("b-p0000-003", BlockKind.PARAGRAPH),
    )
    assert block_text(note.blocks[0]) == "A note in small type."
    assert note.origin == note.blocks[0].origin
    check_stage(FidelityBoundary.STRUCTURE, lines, blocks)


def test_margin_note_of_a_page_whose_body_is_empty_follows_the_last_block() -> None:
    # Page 1's one body line is its page number, removed; a mark 2 pt wide
    # right of it is a margin region.
    page_number = _region(_spread("83", 142, 182, 600))
    mark = _region(_spread("x", 300, 302, 300))
    pages = (
        _body_page(0, *_five_full_lines(70, "first")),
        PageLayout(1, (page_number, mark), ()),
    )
    blocks = make_blocks(_lines_of(*pages), _NO_WORDS, workers=1)
    assert tuple((block.id, block.kind) for block in blocks.blocks) == (
        ("b-p0000-001", BlockKind.PARAGRAPH),
        ("b-p0001-001", BlockKind.MARGIN_NOTE),
    )
    assert blocks.page_numbers == (PageNumber(1, "83", PageNumberPosition.FOOT),)


def test_note_follows_the_blocks_that_start_on_its_page_or_earlier() -> None:
    # A paragraph runs from page 0 to page 1; page 1 has a margin note and a
    # band, and no paragraph of its own. The margin note goes before the
    # paragraph (section 13, rule 4). Markdown writes page 1's note after
    # the last block whose first origin is on page 1 or earlier, the
    # paragraph, after the margin note of page 1 (section 6, "Order").
    page_0 = _body_page(0, *_five_full_lines(70, "first"), _full("runs on to", 145))
    page_1 = PageLayout(
        1,
        (
            _region(*_five_full_lines(70, "second"), _short("its end.", 145)),
            _region(_spread("Margin", 310, 340, 85)),
            _region(_spread("1 A note in small type.", 50, 300, 300, height=7.0)),
        ),
        (),
    )
    blocks = make_blocks(_lines_of(page_0, page_1), _NO_WORDS, workers=1)
    assert tuple((block.id, block.kind) for block in blocks.blocks) == (
        ("b-p0001-001", BlockKind.MARGIN_NOTE),
        ("b-p0000-001", BlockKind.PARAGRAPH),
    )
    assert blocks.notes[0].blocks[0].id == "b-p0001-002"


def test_band_of_two_columns_is_found_when_its_lines_outnumber_the_body() -> None:
    # 9 body lines and 16 note lines in two columns: the note lines are most
    # of the lines, but the body's are most of the rows, so the body word
    # height is the body's (structure spec, section 2, from layout §3).
    body = _region(*_five_full_lines(70, "first"), *_five_full_lines(145, "more")[:4])
    left = _region(
        *(
            _spread(f"{n} A note on the left", 50, 170, 220 + 9 * n, height=7.0)
            for n in range(8)
        )
    )
    right = _region(
        *(
            _spread(f"{n} A note on the right", 180, 300, 220 + 9 * n, height=7.0)
            for n in range(8)
        )
    )
    lines = _lines_of(PageLayout(0, (body, left, right), ()))
    assert survey_book(lines, workers=1).body_word_height == _WORD_HEIGHT_PT
    blocks = make_blocks(lines, _NO_WORDS, workers=1)
    # Markers 0 to 7 rising by one start a note each (structure spec,
    # section 11, rule 3); the right column, whose first marker reads 0,
    # is part of note 7.
    assert tuple(note.marker for note in blocks.notes) == tuple(
        str(n) for n in range(8)
    )
    assert all(block.kind is BlockKind.PARAGRAPH for block in blocks.blocks)
    check_stage(FidelityBoundary.STRUCTURE, lines, blocks)


def test_band_of_five_lines_with_short_last_lines_gives_a_note_each() -> None:
    # The band's commonest edges would be 60 and 140 pt, those of its
    # indented first lines and short last lines; its box, 50 to 300 pt,
    # gives each note its start (structure spec, section 6, "Side text").
    band = _region(
        _spread("1 A note in small", 60, 300, 300, height=7.0),
        _spread("type that ends.", 50, 140, 309, height=7.0),
        _spread("2 Another note here", 60, 300, 318, height=7.0),
        _spread("ends.", 50, 80, 327, height=7.0),
        _spread("3 A third one.", 60, 140, 336, height=7.0),
    )
    page = PageLayout(0, (_region(*_five_full_lines(70, "first")), band), ())
    blocks = make_blocks(_lines_of(page), _NO_WORDS, workers=1)
    assert tuple(
        (note.marker, block_text(note.blocks[0])) for note in blocks.notes
    ) == (
        ("1", "A note in small type that ends."),
        ("2", "Another note here ends."),
        ("3", "A third one."),
    )


def test_two_index_columns_of_equal_width_give_no_margin_note() -> None:
    left = _region(*(_spread(f"Entry {n}, 12", 50, 170, 70 + 15 * n) for n in range(6)))
    right = _region(
        *(_spread(f"Other {n}, 40", 180, 300, 70 + 15 * n) for n in range(6))
    )
    blocks = make_blocks(
        _lines_of(PageLayout(0, (left, right), ())), _NO_WORDS, workers=1
    )
    assert all(block.kind is BlockKind.PARAGRAPH for block in blocks.blocks)
    assert blocks.notes == ()


def test_make_blocks_with_1_worker_and_with_3_gives_the_same_value() -> None:
    pages = (
        *_side_text_pages(),
        *(
            replace(page, index=page.index + 2 * n)
            for n in range(1, 4)
            for page in _side_text_pages()
        ),
        *_numbered_heads(),
    )
    lines = _lines_of(*pages)
    assert make_blocks(lines, _NO_WORDS, workers=1) == make_blocks(
        lines, _NO_WORDS, workers=3
    )


# Notes (structure spec, section 11)


@pytest.mark.parametrize(
    ("word", "endnote", "expected"),
    [
        ("8", False, NoteMarker("8", "", 8)),
        ("291.", True, NoteMarker("291.", "", 291)),
        ("(t)", False, NoteMarker("(t)", "", 1)),
        ("(a)", False, NoteMarker("(a)", "", 2)),
        ("U)", False, NoteMarker("U)", "", None)),
        ("(3J", False, NoteMarker("(3J", "", 3)),
        ("(4", False, NoteMarker("(4", "", 4)),
        ("*", False, NoteMarker("*", "", None)),
        ("13The", False, NoteMarker("13", "The", 13)),
        ("I39-", True, NoteMarker("I39-", "", 139)),
        ("!6o.", True, NoteMarker("!6o.", "", 160)),
        ("I39-", False, None),
        ("I.", True, None),
        ("The", False, None),
        ("1907", False, None),
        ("(1907)", False, None),
    ],
)
def test_note_marker_gives_the_marker_its_rest_and_value(
    word: str, endnote: bool, expected: NoteMarker | None
) -> None:
    assert note_marker(word, endnote=endnote) == expected


_NOTE_HEIGHT_PT = 7.0
_NOTE_PITCH_PT = 9.0


def _note_line(text: str, top: float, x0: float = 50.0, x1: float = 300.0) -> Line:
    return _spread(text, x0, x1, top, height=_NOTE_HEIGHT_PT)


def _placed_line(top: float, *words: tuple[str, float, float]) -> Line:
    """A note line of the words given with their left and right sides."""
    placed = tuple(
        Word(text, Box(x0, top, x1, top + _NOTE_HEIGHT_PT), None)
        for text, x0, x1 in words
    )
    return Line(_box(tuple(word.box for word in placed)), placed)


def _page_with_band(index: int, *band: Line) -> PageLayout:
    """A page of five full body lines from 70 pt and a band of small type
    with the lines `band`."""
    return PageLayout(
        index, (_region(*_five_full_lines(70, "body")), _region(*band)), ()
    )


def _markers_and_texts(blocks: BlocksFile) -> tuple[tuple[str, str], ...]:
    return tuple(
        (note.marker, " / ".join(block_text(block) for block in note.blocks))
        for note in blocks.notes
    )


def test_footnote_markers_are_taken_off_the_notes_of_a_band() -> None:
    page = _page_with_band(
        0,
        _note_line("1 The first note runs", 300, 62),
        _note_line("on to a second line.", 300 + _NOTE_PITCH_PT, 50, 150),
        _note_line("2 The second note.", 300 + 2 * _NOTE_PITCH_PT, 62, 160),
    )
    lines = _lines_of(page)
    blocks = make_blocks(lines, _NO_WORDS, workers=1)
    assert _markers_and_texts(blocks) == (
        ("1", "The first note runs on to a second line."),
        ("2", "The second note."),
    )
    assert all(note.kind is NoteKind.FOOTNOTE for note in blocks.notes)
    check_stage(FidelityBoundary.STRUCTURE, lines, blocks)


def test_footnote_with_a_marker_indented_after_a_full_line_starts_a_note() -> None:
    # Rule 2: the line after a full one is no start by section 6's indent
    # rule, but its first word is a marker and it is indented 12 pt.
    # "7" does not read one more than "1", so rule 3 does not start it.
    page = _page_with_band(
        0,
        _note_line("1 The first note fills its line", 300, 62),
        _note_line("and the next one.", 300 + _NOTE_PITCH_PT),
        _note_line("7 The second note.", 300 + 2 * _NOTE_PITCH_PT, 62, 160),
    )
    blocks = make_blocks(_lines_of(page), _NO_WORDS, workers=1)
    assert _markers_and_texts(blocks) == (
        ("1", "The first note fills its line and the next one."),
        ("7", "The second note."),
    )


def test_footnote_marker_reading_one_more_starts_a_note_without_an_indent() -> None:
    # Rule 3: neither line is indented, and "2" reads one more than "1".
    page = _page_with_band(
        0,
        _note_line("1 The first note fills its line.", 300),
        _note_line("2 The second note.", 300 + _NOTE_PITCH_PT, 50, 150),
        _note_line("4 is a number in the second note.", 300 + 2 * _NOTE_PITCH_PT),
    )
    blocks = make_blocks(_lines_of(page), _NO_WORDS, workers=1)
    assert _markers_and_texts(blocks) == (
        ("1", "The first note fills its line."),
        ("2", "The second note. 4 is a number in the second note."),
    )


def test_footnote_of_two_notes_on_one_line_gives_two_notes() -> None:
    # The second marker is 14 pt after "12 b.", before a capital.
    line = _placed_line(
        300,
        ("1", 50, 55),
        ("D.", 59, 67),
        ("B.", 71, 79),
        ("12", 83, 93),
        ("b.", 97, 105),
        ("2", 119, 124),
        ("Dialogus", 128, 168),
        ("i.", 172, 178),
    )
    lines = _lines_of(_page_with_band(0, line))
    blocks = make_blocks(lines, _NO_WORDS, workers=1)
    assert _markers_and_texts(blocks) == (("1", "D. B. 12 b."), ("2", "Dialogus i."))
    check_stage(FidelityBoundary.STRUCTURE, lines, blocks)


@pytest.mark.parametrize(
    ("gap", "before", "after", "notes"),
    [
        (10.0, "b.", "Dialogus", 2),
        (9.0, "b.", "Dialogus", 1),
        (14.0, "b", "Dialogus", 1),
        (14.0, "b.", "dialogus", 1),
    ],
)
def test_footnote_second_marker_on_a_line_needs_gap_stop_and_capital(
    gap: float, before: str, after: str, notes: int
) -> None:
    line = _placed_line(
        300,
        ("1", 50, 55),
        ("Ibid.", 59, 84),
        (before, 88, 96),
        ("e", 96 + gap, 101 + gap),
        (after, 105 + gap, 145 + gap),
        ("i.", 149 + gap, 155 + gap),
    )
    blocks = make_blocks(_lines_of(_page_with_band(0, line)), _NO_WORDS, workers=1)
    assert len(blocks.notes) == notes


def test_footnote_one_character_marker_is_taken_when_the_note_is_indented() -> None:
    # "«" is no marker's form, but the note starts by its indent and the
    # next word starts with a capital (Domesday page 74).
    page = _page_with_band(
        0,
        _note_line("1 The first note.", 300, 62, 160),
        _note_line("« Domesday Book, ii. 59, and on", 300 + _NOTE_PITCH_PT, 62),
        _note_line("its second line.", 300 + 2 * _NOTE_PITCH_PT, 50, 160),
    )
    blocks = make_blocks(_lines_of(page), _NO_WORDS, workers=1)
    assert _markers_and_texts(blocks) == (
        ("1", "The first note."),
        ("«", "Domesday Book, ii. 59, and on its second line."),
    )


@pytest.mark.parametrize(
    ("word_list", "expected"),
    [
        (frozenset({"treatise"}), ("", "A Treatise on law, and on")),
        (_NO_WORDS, ("A", "Treatise on law, and on")),
    ],
)
def test_footnote_a_word_a_or_i_before_a_known_word_is_no_marker(
    word_list: frozenset[str], expected: tuple[str, str]
) -> None:
    # "A" is a word: before a known word it is no one-character marker
    # (structure spec, section 11, "The marker of a note").
    page = _page_with_band(
        0,
        _note_line("1 The first note.", 300, 62, 160),
        _note_line("A Treatise on law, and on", 300 + _NOTE_PITCH_PT, 62),
        _note_line("its second line.", 300 + 2 * _NOTE_PITCH_PT, 50, 160),
    )
    blocks = make_blocks(_lines_of(page), word_list, workers=1)
    marker, text = _markers_and_texts(blocks)[1]
    assert (marker, text.removesuffix(" its second line.")) == expected


def test_footnote_lower_case_a_before_a_known_word_is_the_marker() -> None:
    # Kadesh page 8: a superscript 2 read as "a", before "In", a known word
    # (structure spec, section 11, "The marker of a note").
    page = _page_with_band(
        0,
        _note_line("1 The first note.", 300, 62, 160),
        _note_line("a In Ramses III.'s day the", 300 + _NOTE_PITCH_PT, 62),
        _note_line("its second line.", 300 + 2 * _NOTE_PITCH_PT, 50, 160),
    )
    blocks = make_blocks(_lines_of(page), frozenset({"in"}), workers=1)
    assert _markers_and_texts(blocks)[1] == (
        "a",
        "In Ramses III.'s day the its second line.",
    )


def test_footnote_glued_marker_is_split_off_its_word() -> None:
    page = _page_with_band(0, _note_line("13The note glued to its marker.", 300, 62))
    lines = _lines_of(page)
    blocks = make_blocks(lines, _NO_WORDS, workers=1)
    assert _markers_and_texts(blocks) == (("13", "The note glued to its marker."),)
    assert blocks.word_changes == (
        WordChange(
            page_index=0,
            before=("13The",),
            after=("13", "The"),
            reason=ChangeReason.NOTE_MARKER,
        ),
    )
    check_stage(FidelityBoundary.STRUCTURE, lines, blocks)


def test_footnote_column_without_a_marker_is_part_of_the_note_before() -> None:
    left = _region(
        _note_line("1 A note that runs on", 300, 62, 170),
        _note_line("in its column", 300 + _NOTE_PITCH_PT, 50, 170),
    )
    right = _region(_note_line("into the next one.", 300, 180, 260))
    page = PageLayout(0, (_region(*_five_full_lines(70, "body")), left, right), ())
    blocks = make_blocks(_lines_of(page), _NO_WORDS, workers=1)
    assert _markers_and_texts(blocks) == (
        ("1", "A note that runs on in its column into the next one."),
    )


def test_footnote_column_indented_starts_a_note_its_glued_sign_split_off() -> None:
    # Rule 4 (Kadesh page 8): the right column's first line is indented 12
    # pt against its column, and its marker is a sign glued to its first
    # word.
    left = _region(
        _note_line("1 A note in the left column", 300, 62, 170),
        _note_line("that ends here.", 300 + _NOTE_PITCH_PT, 50, 170),
    )
    right = _region(
        _note_line("'There is a note on", 300, 192, 300),
        _note_line("the right, which ends.", 300 + _NOTE_PITCH_PT, 180, 300),
    )
    page = PageLayout(0, (_region(*_five_full_lines(70, "body")), left, right), ())
    lines = _lines_of(page)
    blocks = make_blocks(lines, _NO_WORDS, workers=1)
    assert _markers_and_texts(blocks) == (
        ("1", "A note in the left column that ends here."),
        ("'", "There is a note on the right, which ends."),
    )
    assert blocks.word_changes == (
        WordChange(
            page_index=0,
            before=("'There",),
            after=("'", "There"),
            reason=ChangeReason.NOTE_MARKER,
        ),
    )
    check_stage(FidelityBoundary.STRUCTURE, lines, blocks)


def test_footnote_alone_on_its_page_is_never_indented() -> None:
    # One note line: the band's left edge is its own left side.
    page = _page_with_band(0, _note_line("'Quoted words in small type.", 300, 70, 200))
    blocks = make_blocks(_lines_of(page), _NO_WORDS, workers=1)
    assert _markers_and_texts(blocks) == (("", "'Quoted words in small type."),)


def _note_running_over(gap_pages: tuple[PageLayout, ...]) -> LinesFile:
    """Page 0's band ends with note 2, which page N's band continues on a
    line neither indented nor marked, `gap_pages` coming between."""
    first = _page_with_band(
        0,
        _note_line("1 A note.", 300, 62, 120),
        _note_line("2 A note that runs", 300 + _NOTE_PITCH_PT, 62, 300),
    )
    last_index = 1 + len(gap_pages)
    last = _page_with_band(
        last_index,
        _note_line("over the page break.", 300, 50, 160),
        _note_line("1 The next page's note.", 300 + _NOTE_PITCH_PT, 62, 200),
    )
    return _lines_of(first, *gap_pages, last)


def test_footnote_running_over_a_blank_page_is_one_note_with_two_origins() -> None:
    lines = _note_running_over((PageLayout(1, (), ()),))
    blocks = make_blocks(lines, _NO_WORDS, workers=1)
    assert _markers_and_texts(blocks) == (
        ("1", "A note."),
        ("2", "A note that runs over the page break."),
        ("1", "The next page's note."),
    )
    running = blocks.notes[1]
    assert running.id == "n-p0000-002"
    assert tuple(origin.page_index for origin in running.origin) == (0, 2)
    check_stage(FidelityBoundary.STRUCTURE, lines, blocks)


def test_footnote_running_over_a_plate_page_is_one_note_with_two_origins() -> None:
    # Spec section 18: a plate's lines are not in the body stream, so the
    # plate is passed over as a blank page is (section 11).
    plate = _plate(1, _spread("^U;L", 60, 90, 627))
    lines = _note_running_over((plate,))
    blocks = make_blocks(lines, _NO_WORDS, workers=1)
    assert _markers_and_texts(blocks) == (
        ("1", "A note."),
        ("2", "A note that runs over the page break."),
        ("1", "The next page's note."),
    )
    assert tuple(origin.page_index for origin in blocks.notes[1].origin) == (0, 2)
    check_stage(FidelityBoundary.STRUCTURE, lines, blocks)


def test_footnote_after_a_page_of_body_without_notes_does_not_run_on() -> None:
    lines = _note_running_over((_body_page(1, *_five_full_lines(70, "other")),))
    blocks = make_blocks(lines, _NO_WORDS, workers=1)
    assert _markers_and_texts(blocks) == (
        ("1", "A note."),
        ("2", "A note that runs"),
        ("", "over the page break."),
        ("1", "The next page's note."),
    )


def test_footnote_first_on_its_page_and_indented_does_not_run_on() -> None:
    first = _page_with_band(0, _note_line("1 A note that runs", 300, 62, 300))
    second = _page_with_band(
        1,
        _note_line("A quotation in small type, which", 300, 62),
        _note_line("ends here.", 300 + _NOTE_PITCH_PT, 50, 120),
    )
    blocks = make_blocks(_lines_of(first, second), _NO_WORDS, workers=1)
    assert _markers_and_texts(blocks) == (
        ("1", "A note that runs"),
        ("", "A quotation in small type, which ends here."),
    )


_SMALL_PT = 8.5  # 0.85 of the body word height, 10 pt


def _body_notes_pages(
    markers: tuple[str, str, str],
    *,
    band_on_the_page: bool = False,
    text_height: float = _WORD_HEIGHT_PT,
) -> LinesFile:
    """Page 0: a body and a band note "(1)", which give the book the
    bracketed marker form, numbered per page. Page 1: five body lines of
    `text_height` ending short, then three short lines indented 20 pt at
    0.85 of the body height starting with `markers`. Page 2: a body whose
    first line is not indented."""
    band = _region(_note_line("(1) A note in the band.", 300, 62, 200))
    page_0 = PageLayout(0, (_region(*_five_full_lines(70, "zero")), band), ())
    text = (
        *(
            _spread(f"text {n} of the page", 50, 300, 70 + 15 * n, text_height)
            for n in range(4)
        ),
        _spread("its end.", 50, 150, 130, text_height),
    )
    notes = tuple(
        _spread(
            f"{marker} Note {marker} in small type.", 70, 200, 145 + 12 * n, _SMALL_PT
        )
        for n, marker in enumerate(markers)
    )
    regions = (_region(*text, *notes),) + (
        (_region(_note_line("(1) Another band note.", 300, 62, 200)),)
        if band_on_the_page
        else ()
    )
    page_1 = PageLayout(1, regions, ())
    page_2 = _body_page(2, *_five_full_lines(70, "two"))
    return _lines_of(page_0, page_1, page_2)


def _page_1_blocks(blocks: BlocksFile) -> tuple[str, ...]:
    return tuple(
        block_text(block) for block in blocks.blocks if block.origin[0].page_index == 1
    )


# Spec section 29: the three notes left in the body, one line each at one
# left side and the first reading "(1)", are a list of three items.
_NOTES_AS_LIST_ITEMS = (
    ("list_item", "(1)", "Note (1) in small type."),
    ("list_item", "(2)", "Note (2) in small type."),
    ("list_item", "(3)", "Note (3) in small type."),
)


def _page_1_kinds(blocks: BlocksFile) -> tuple[tuple[str, str | None, str], ...]:
    """Each block of page 1, its kind, label and text."""
    return tuple(
        (block.kind.value, block.label, block_text(block))
        for block in blocks.blocks
        if block.origin[0].page_index == 1
    )


def test_footnote_left_in_the_body_in_rising_order_is_taken_as_notes() -> None:
    lines = _body_notes_pages(("(1)", "(2)", "(3)"))
    blocks = make_blocks(lines, _NO_WORDS, workers=1)
    assert _markers_and_texts(blocks)[1:] == (
        ("(1)", "Note (1) in small type."),
        ("(2)", "Note (2) in small type."),
        ("(3)", "Note (3) in small type."),
    )
    assert tuple(note.origin[0].page_index for note in blocks.notes) == (0, 1, 1, 1)
    assert _page_1_blocks(blocks) == ()
    check_stage(FidelityBoundary.STRUCTURE, lines, blocks)


def test_footnote_left_in_the_body_out_of_order_stays_and_does_not_run_on() -> None:
    blocks = make_blocks(_body_notes_pages(("(1)", "(3)", "(2)")), _NO_WORDS, workers=1)
    assert len(blocks.notes) == 1
    page_1 = _page_1_blocks(blocks)
    assert page_1[-3:] == (
        "(1) Note (1) in small type.",
        "(3) Note (3) in small type.",
        "(2) Note (2) in small type.",
    )
    # The marker-led paragraph does not run on; page 2 starts its own.
    assert block_text(blocks.blocks[-1]).startswith("two 0 of the page")


def test_footnote_lines_in_the_body_of_a_page_whose_band_starts_at_1_stay() -> None:
    blocks = make_blocks(
        _body_notes_pages(("(1)", "(2)", "(3)"), band_on_the_page=True),
        _NO_WORDS,
        workers=1,
    )
    assert tuple(note.marker for note in blocks.notes) == ("(1)", "(1)")
    assert _page_1_kinds(blocks)[-3:] == _NOTES_AS_LIST_ITEMS


def test_footnote_lines_in_the_body_below_text_as_small_stay() -> None:
    blocks = make_blocks(
        _body_notes_pages(("(1)", "(2)", "(3)"), text_height=_SMALL_PT),
        _NO_WORDS,
        workers=1,
    )
    assert len(blocks.notes) == 1
    assert _page_1_kinds(blocks) == _NOTES_AS_LIST_ITEMS


def test_footnote_lines_in_the_body_of_a_book_with_digit_markers_stay() -> None:
    # The book's band starts its notes with digits, not brackets.
    pages = _body_notes_pages(("(1)", "(2)", "(3)")).pages
    band = _region(_note_line("1 A note in the band.", 300, 62, 200))
    page_0 = replace(pages[0], regions=(pages[0].regions[0], band))
    blocks = make_blocks(_lines_of(page_0, *pages[1:]), _NO_WORDS, workers=1)
    assert len(blocks.notes) == 1


@pytest.mark.parametrize(
    ("word", "expected"),
    [
        ("land3.", Reference("land", "3", ".", ReferenceForm.GLUED, 3)),
        ("Kadesh,12", Reference("Kadesh,", "12", "", ReferenceForm.GLUED, 12)),
        ("causa)27.", Reference("causa)", "27", ".", ReferenceForm.GLUED, 27)),
        ("12s.2", Reference("12s.", "2", "", ReferenceForm.GLUED, 2)),
        ("30d8", Reference("30d", "8", "", ReferenceForm.GLUED, 8)),
        (";13", Reference(";", "13", "", ReferenceForm.GLUED, 13)),
        ("14);", None),
        ("13,", None),
        ("(i).", Reference("", "(i)", ".", ReferenceForm.BRACKETED, 1)),
        ("{2).", Reference("", "{2)", ".", ReferenceForm.BRACKETED, 2)),
        ("rulers.^", Reference("rulers.", "^", "", ReferenceForm.SIGN, None)),
        ("^", Reference("", "^", "", ReferenceForm.SIGN, None)),
        ("servus*.", Reference("servus", "*", ".", ReferenceForm.SIGN, None)),
        ("rulers.^),", Reference("rulers.", "^", "),", ReferenceForm.SIGN, None)),
        ("*.", None),
        ("^,", None),
        ("land*£", None),
        ("S*.", None),
        ("S.*", Reference("S.", "*", "", ReferenceForm.SIGN, None)),
        ("p.12", None),
        ("pp.3", None),
        ("vol.3", None),
        ("1066", None),
        ("'", None),
        ("t", None),
        ("£2", None),
        ("(1907)", None),
    ],
)
def test_reference_candidate_gives_the_reference_in_a_word(
    word: str, expected: Reference | None
) -> None:
    assert reference_candidate(word) == expected


def _referenced_page(
    index: int, body_words: str, *notes: str, right: float = 300.0
) -> PageLayout:
    """A page of five full body lines, the last ending with `body_words`,
    and a band of `notes`, each on one line indented 12 pt, with a line at
    the band's left edge after them."""
    body = (
        *_five_full_lines(70, "body")[:4],
        _spread(f"words of the page {body_words}", 50, right, 130),
    )
    band = (
        *(
            _note_line(text, 300 + _NOTE_PITCH_PT * n, 62, 200)
            for n, text in enumerate(notes)
        ),
        _note_line("and its end.", 300 + _NOTE_PITCH_PT * len(notes), 50, 120),
    )
    return PageLayout(index, (_region(*body), _region(*band)), ())


def _references(blocks: BlocksFile) -> tuple[tuple[str, str], ...]:
    """Each reference span's text and the marker of its note."""
    markers = {note.id: note.marker for note in blocks.notes}
    return tuple(
        (span.text, markers[span.note_ref])
        for block in blocks.blocks
        for span in block.spans
        if span.note_ref is not None
    )


def test_referenced_glued_numbers_are_linked_and_a_bracketed_one_stays() -> None:
    lines = _lines_of(
        _referenced_page(0, "land1. day2 (3)", "1 One.", "2 Two.", "3 Three.")
    )
    blocks = make_blocks(lines, _NO_WORDS, workers=1)
    assert _references(blocks) == (("1", "1"), ("2", "2"))
    assert tuple(note.referenced for note in blocks.notes) == (True, True, False)
    paragraph = blocks.blocks[0]
    assert block_text(paragraph).endswith("land1. day2 (3)")
    assert tuple(span.text for span in paragraph.spans)[1:] == (
        "1",
        ". day",
        "2",
        " (3)",
    )
    assert paragraph.spans[0].text.endswith(" land")
    assert blocks.word_changes == (
        WordChange(
            page_index=0,
            before=("land1.",),
            after=("land", "1", "."),
            reason=ChangeReason.NOTE_MARKER,
        ),
        WordChange(
            page_index=0,
            before=("day2",),
            after=("day", "2"),
            reason=ChangeReason.NOTE_MARKER,
        ),
    )
    check_stage(FidelityBoundary.STRUCTURE, lines, blocks)


def test_referenced_number_misread_against_its_marker_is_linked_as_read() -> None:
    # Numbered per page, the note is note 3 of its page whatever its marker
    # reads: "land3." links to it and keeps "3".
    pages = (
        _referenced_page(0, "now1.", "1 One."),
        _referenced_page(1, "here1. there2 land3.", "1 One.", "2 Two.", "8 Three."),
    )
    blocks = make_blocks(_lines_of(*pages), _NO_WORDS, workers=1)
    assert _references(blocks) == (("1", "1"), ("1", "1"), ("2", "2"), ("3", "8"))


def test_referenced_sign_alone_is_linked_to_a_note_marked_by_a_sign() -> None:
    lines = _lines_of(_referenced_page(0, "the king. ^", "* A note."))
    blocks = make_blocks(lines, _NO_WORDS, workers=1)
    assert _references(blocks) == (("^", "*"),)
    assert blocks.word_changes == ()
    check_stage(FidelityBoundary.STRUCTURE, lines, blocks)


def test_referenced_sign_followed_by_punctuation_is_split_from_its_word() -> None:
    # Spec section 11, "References": Domesday 55's "servus*.".
    lines = _lines_of(_referenced_page(0, "the servus*. was", "* A note."))
    blocks = make_blocks(lines, _NO_WORDS, workers=1)
    assert _references(blocks) == (("*", "*"),)
    paragraph = blocks.blocks[0]
    assert tuple(span.text for span in paragraph.spans)[1:] == ("*", ". was")
    assert paragraph.spans[0].text.endswith(" servus")
    assert blocks.word_changes == (
        WordChange(
            page_index=0,
            before=("servus*.",),
            after=("servus", "*", "."),
            reason=ChangeReason.NOTE_MARKER,
        ),
    )
    check_stage(FidelityBoundary.STRUCTURE, lines, blocks)


def test_referenced_bracketed_reference_with_a_letter_stays_in_its_word() -> None:
    # "(i)." would be a span with a letter that was a whole word, which the
    # fidelity check refuses (architecture section 13); "{2)." is linked.
    lines = _lines_of(
        _referenced_page(0, "first (i). second {2).", "(1) One.", "(2) Two.")
    )
    blocks = make_blocks(lines, _NO_WORDS, workers=1)
    assert _references(blocks) == (("{2)", "(2)"),)
    assert tuple(note.referenced for note in blocks.notes) == (False, True)
    check_stage(FidelityBoundary.STRUCTURE, lines, blocks)


def test_referenced_page_s_leftover_note_end_is_not_counted() -> None:
    # Page 1's band starts with the end of a note whose start is on no page
    # with notes: it has no value, and "(1)" is the page's first note.
    first = _referenced_page(0, "now1.", "1 One.")
    body_only = _body_page(1, *_five_full_lines(70, "other"))
    page = _referenced_page(2, "here1. there2", "1 One.", "2 Two.")
    band = page.regions[1]
    leftover = _note_line("the end of a note.", 290, 50, 150)
    page = replace(
        page, regions=(page.regions[0], replace(band, lines=(leftover, *band.lines)))
    )
    blocks = make_blocks(_lines_of(first, body_only, page), _NO_WORDS, workers=1)
    assert _references(blocks) == (("1", "1"), ("1", "1"), ("2", "2"))
    assert tuple(note.referenced for note in blocks.notes) == (True, False, True, True)


def test_referenced_note_is_never_linked_to_an_earlier_candidate() -> None:
    # Notes 1 and 2, candidates "2" then "1": one pair only, note 1 with the
    # later "1", since a later note is never paired with an earlier
    # candidate and of equal totals the first note's earlier pair wins.
    lines = _lines_of(_referenced_page(0, "this2 that1", "1 One.", "2 Two."))
    blocks = make_blocks(lines, _NO_WORDS, workers=1)
    assert _references(blocks) == (("1", "1"),)


@pytest.mark.parametrize(
    ("values", "references", "pairs"),
    [
        ((1, 2), ("x1", "y2"), ((0, 0), (1, 1))),
        ((1, 2), ("x2", "y1"), ((0, 1),)),
        ((1,), ("x1", "y1"), ((0, 0),)),
        ((3,), ("x8",), ((0, 0),)),
        ((3,), ("x4",), ()),
        ((None,), ("x.^",), ((0, 0),)),
        ((1, 2), ("x.^", "y2"), ((0, 0), (1, 1))),
        ((1, 2), ("x2",), ((1, 0),)),
    ],
)
def test_referenced_alignment_pairs_the_highest_total_in_order(
    values: tuple[int | None, ...],
    references: tuple[str, ...],
    pairs: tuple[tuple[int, int], ...],
) -> None:
    candidates = tuple(reference_candidate(word) for word in references)
    assert all(candidate is not None for candidate in candidates)
    assert align(values, tuple(c for c in candidates if c is not None)) == pairs


def _endnote_pages(
    first: int, count: int, *, body_words: str = "the text", between: bool = False
) -> LinesFile:
    """Page 0: a paragraph holding `body_words` whose last line is full, so
    that it would run on. Page 1: the end of a note at its top, then
    `count` endnotes, "N." from `first`, each an indented line and a short
    one, with a paragraph without a marker after the first when
    `between`."""
    page_0 = _body_page(
        0,
        _indented(f"A paragraph with {body_words} in it", 70),
        *_five_full_lines(85, "body"),
    )
    texts = [("the end of a note whose start is", "not here.", False)]
    for n in range(count):
        texts.append((f"{first + n}. The note {first + n} which", "ends.", True))
        if between and n == 0:
            texts.append(("A second paragraph of", "the note.", True))
    lines = tuple(
        line
        for number, (start, end, indented) in enumerate(texts)
        for line in (
            (_indented if indented else _full)(start, 70 + 45 * number),
            _full("goes on over a full line", 85 + 45 * number),
            _short(end, 100 + 45 * number),
        )
    )
    return _lines_of(page_0, _body_page(1, *lines))


def _endnotes_of(blocks: BlocksFile) -> tuple[tuple[str, tuple[str, ...]], ...]:
    return tuple(
        (note.marker, tuple(block_text(block) for block in note.blocks))
        for note in blocks.notes
        if note.kind is NoteKind.ENDNOTE
    )


def _references_to_endnotes(blocks: BlocksFile) -> tuple[tuple[str, str], ...]:
    """Each reference to a note: its note's marker and the word it was
    split off."""
    markers = {note.id: note.marker for note in blocks.notes}
    return tuple(
        (markers[span.note_ref], block.spans[position - 1].text.split(" ")[-1])
        for block in blocks.blocks
        for position, span in enumerate(block.spans)
        if span.note_ref is not None
    )


def test_endnote_references_are_taken_after_the_last_contents_page() -> None:
    # An introduction (page 0) refers to its own notes, before the book's
    # contents page (1); "Law1" on page 2 is the endnote's reference
    # (structure spec, section 12, "References").
    section = _endnote_pages(1, 12, body_words="Law1")
    introduction = _body_page(0, _indented("An introduction says Maitland1 so", 70))
    contents = _body_page(1, _indented("Contents of the book", 70))
    lines = _lines_of(
        introduction,
        contents,
        *(replace(page, index=page.index + 2) for page in section.pages),
    )
    blocks = make_blocks(lines, _NO_WORDS, contents_pages=frozenset({1}), workers=1)
    assert _references_to_endnotes(blocks) == (("1.", "Law"),)
    without = make_blocks(lines, _NO_WORDS, workers=1)
    # Without it, the introduction's "Maitland1" takes endnote 1, and "Law1"
    # goes to endnote 4, a digit the OCR confuses with 1.
    assert _references_to_endnotes(without) == (("1.", "Maitland"), ("4.", "Law"))


def test_endnote_marker_that_does_not_rise_starts_a_new_run() -> None:
    # A list numbered 1 to 5 on page 0, then the section's 1 to 12: "1."
    # does not rise above "5.", so the list is a run of its own, too short
    # for a section, and stays paragraphs (structure spec, section 12).
    section = _endnote_pages(1, 12)
    listed = _body_page(
        0,
        *(
            line
            for n in range(1, 6)
            for line in (
                _indented(f"{n}. An item of a list", 25 + 45 * n),
                _full("goes on over a full line", 40 + 45 * n),
                _short("ends.", 55 + 45 * n),
            )
        ),
    )
    lines = _lines_of(
        listed, *(replace(page, index=page.index + 1) for page in section.pages)
    )
    blocks = make_blocks(lines, _NO_WORDS, workers=1)
    assert tuple(marker for marker, _ in _endnotes_of(blocks))[1:] == tuple(
        f"{n}." for n in range(1, 13)
    )
    assert tuple(block_text(block) for block in blocks.blocks[:5]) == tuple(
        f"{n}. An item of a list goes on over a full line ends." for n in range(1, 6)
    )


def test_endnote_section_stops_back_at_a_centred_line() -> None:
    # "NOTES." centred above the first endnote stays a body block; the end
    # of a note between it and "1." is an endnote without a marker.
    section = _endnote_pages(1, 12)
    page = section.pages[1]
    region = page.regions[0]
    title = _spread("NOTES.", 150, 200, 50)
    page = replace(page, regions=(replace(region, lines=(title, *region.lines)),))
    blocks = make_blocks(_lines_of(section.pages[0], page), _NO_WORDS, workers=1)
    assert block_text(blocks.blocks[-1]) == "NOTES."
    assert _endnotes_of(blocks)[0][0] == ""


def test_endnote_section_does_not_run_on_over_blank_pages() -> None:
    # The last endnote ends with a full line; after two blank pages, a
    # page's first line, not indented, does not run on into it.
    section = _endnote_pages(1, 12)
    last = section.pages[1]
    region = last.regions[0]
    full_end = replace(region, lines=(*region.lines[:-1], _full("and runs on", 640)))
    card = _body_page(4, _full("PLEASE DO NOT REMOVE CARDS", 70))
    lines = _lines_of(
        section.pages[0],
        replace(last, regions=(full_end,)),
        PageLayout(2, (), ()),
        PageLayout(3, (), ()),
        card,
    )
    blocks = make_blocks(lines, _NO_WORDS, workers=1)
    assert _endnotes_of(blocks)[-1][1][-1].endswith("and runs on")
    assert block_text(blocks.blocks[-1]) == "PLEASE DO NOT REMOVE CARDS"


def test_endnote_runs_on_over_a_page_break_in_a_book_of_digit_markers() -> None:
    # A footnote "1 …" in small type on page 0 makes the book's marker form
    # digits (Gierke once its introduction's notes are band regions); the
    # section's endnote "12. …" ends page 1 with a full line and runs on
    # into page 2 as one paragraph (structure spec, section 16).
    section = _endnote_pages(1, 12)
    first = section.pages[0]
    band = _region(_spread("1 A note in small type.", 50, 300, 300, height=7.0))
    last = section.pages[1]
    region = last.regions[0]
    full_end = replace(region, lines=(*region.lines[:-1], _full("and runs on", 640)))
    lines = _lines_of(
        replace(first, regions=(*first.regions, band)),
        replace(last, regions=(full_end,)),
        _body_page(
            2,
            _short("over the page.", 70),
            _indented("13. The note 13 which", 85),
            _full("goes on over a full line", 100),
            _short("ends.", 115),
        ),
    )
    blocks = make_blocks(lines, _NO_WORDS, workers=1)
    assert _endnotes_of(blocks)[-2] == (
        "12.",
        ("The note 12 which goes on over a full line and runs on over the page.",),
    )


def test_endnote_section_of_12_paragraphs_gives_12_endnotes() -> None:
    lines = _endnote_pages(291, 12, between=True)
    blocks = make_blocks(lines, _NO_WORDS, workers=1)
    endnotes = _endnotes_of(blocks)
    assert tuple(marker for marker, _ in endnotes) == (
        "",
        *(f"{n}." for n in range(291, 303)),
    )
    assert endnotes[0] == (
        "",
        ("the end of a note whose start is goes on over a full line not here.",),
    )
    assert endnotes[1] == (
        "291.",
        (
            "The note 291 which goes on over a full line ends.",
            "A second paragraph of goes on over a full line the note.",
        ),
    )
    assert not any(note.referenced for note in blocks.notes)
    # The paragraph of page 0 does not run on into the section.
    assert tuple(origin.page_index for origin in blocks.blocks[-1].origin) == (0,)
    check_stage(FidelityBoundary.STRUCTURE, lines, blocks)


def test_endnote_run_of_6_paragraphs_gives_no_endnote() -> None:
    blocks = make_blocks(_endnote_pages(291, 6), _NO_WORDS, workers=1)
    assert _endnotes_of(blocks) == ()
    assert block_text(blocks.blocks[-1]) == (
        "296. The note 296 which goes on over a full line ends."
    )


def test_endnote_damaged_marker_counts_in_the_section() -> None:
    # The tenth marker, "139.", is read "I39-".
    lines = _endnote_pages(130, 12)
    page = lines.pages[1]
    region = page.regions[0]
    tenth = region.lines[3 + 3 * 9]
    damaged = replace(
        tenth, words=(replace(tenth.words[0], text="I39-"), *tenth.words[1:])
    )
    region_lines = tuple(damaged if line is tenth else line for line in region.lines)
    page = replace(page, regions=(replace(region, lines=region_lines),))
    blocks = make_blocks(_lines_of(lines.pages[0], page), _NO_WORDS, workers=1)
    markers = tuple(marker for marker, _ in _endnotes_of(blocks))
    assert markers[10] == "I39-"
    assert len(markers) == 13


def test_endnote_is_linked_to_a_glued_number_of_the_body_before_it() -> None:
    lines = _endnote_pages(1, 12, body_words="Law1")
    blocks = make_blocks(lines, _NO_WORDS, workers=1)
    (law,) = tuple(
        (span.text, span.note_ref)
        for block in blocks.blocks
        for span in block.spans
        if span.note_ref is not None
    )
    note = next(note for note in blocks.notes if note.id == law[1])
    assert (law[0], note.kind, note.marker, note.referenced) == (
        "1",
        NoteKind.ENDNOTE,
        "1.",
        True,
    )
    check_stage(FidelityBoundary.STRUCTURE, lines, blocks)


def _with_margin(lines: LinesFile, page: int, *margins: Line) -> LinesFile:
    """`lines` with a margin region of each of `margins` on page `page`."""
    pages = tuple(
        replace(
            layout,
            regions=(*layout.regions, *(_region(margin) for margin in margins)),
        )
        if layout.index == page
        else layout
        for layout in lines.pages
    )
    return _lines_of(*pages)


def test_margin_note_inside_an_endnote_beside_its_line_before_its_text() -> None:
    # Endnote 292's first line is at 160 pt; the margin note's top is 4 pt
    # lower (structure spec, section 13, rules 2 and 5).
    lines = _with_margin(
        _endnote_pages(291, 12), 1, _spread("Natural Law.", 310, 340, 164)
    )
    blocks = make_blocks(lines, _NO_WORDS, workers=1)
    note = next(note for note in blocks.notes if note.marker == "292.")
    assert tuple((block.kind, block_text(block)) for block in note.blocks) == (
        (BlockKind.MARGIN_NOTE, "Natural Law."),
        (BlockKind.PARAGRAPH, "The note 292 which goes on over a full line ends."),
    )
    assert all(block.kind is not BlockKind.MARGIN_NOTE for block in blocks.blocks)
    check_stage(FidelityBoundary.STRUCTURE, lines, blocks)


def test_margin_note_inside_a_footnote_beside_its_line() -> None:
    page = _page_with_band(
        0,
        _note_line("1 The first note.", 300, 62, 160),
        _note_line("2 The second note runs", 300 + _NOTE_PITCH_PT, 62),
        _note_line("on here.", 300 + 2 * _NOTE_PITCH_PT, 50, 120),
    )
    lines = _with_margin(_lines_of(page), 0, _spread("Aside", 310, 340, 309))
    blocks = make_blocks(lines, _NO_WORDS, workers=1)
    assert tuple(
        tuple(block.kind for block in note.blocks) for note in blocks.notes
    ) == ((BlockKind.PARAGRAPH,), (BlockKind.MARGIN_NOTE, BlockKind.PARAGRAPH))


def test_margin_note_beside_a_body_line_stays_in_the_body() -> None:
    page = _page_with_band(0, _note_line("1 A note.", 300, 62, 160))
    lines = _with_margin(_lines_of(page), 0, _spread("Aside", 310, 340, 85))
    blocks = make_blocks(lines, _NO_WORDS, workers=1)
    assert tuple(block.kind for block in blocks.blocks) == (
        BlockKind.MARGIN_NOTE,
        BlockKind.PARAGRAPH,
    )
    assert tuple(block.kind for block in blocks.notes[0].blocks) == (
        BlockKind.PARAGRAPH,
    )


def _beside(top: float, *, first: bool) -> BesideLine:
    line = _spread("a line", 50, 300, top)
    edges = Edges(50, 300)
    return BesideLine(PlacedLine(0, line, edges, edges), first, InParagraph(0, 0))


def test_beside_a_paragraph_s_first_line_within_half_a_pitch_before_a_nearer_one() -> (
    None
):
    # The margin note's top is 100: the middle line at 101 is nearer, but a
    # first line at 107 is within 0.5 of a 15 pt pitch.
    lines = (_beside(101, first=False), _beside(107, first=True))
    assert line_beside(100, lines, 15.0) == lines[1]
    assert line_beside(100, (lines[0], _beside(108, first=True)), 15.0) == lines[0]


# Margin notes placed before their paragraphs (structure spec, section 13).
# The body's lines run from 50 to 300 pt, 15 pt apart; a margin note stands
# right of them, from 310 pt.


def _placed(*pages: PageLayout) -> tuple[tuple[BlockKind, str], ...]:
    blocks = make_blocks(_lines_of(*pages), _NO_WORDS, workers=1)
    check_stage(FidelityBoundary.STRUCTURE, _lines_of(*pages), blocks)
    return tuple((block.kind, block_text(block)) for block in blocks.blocks)


def _two_paragraphs(*margins: Line, beside: Line | None = None) -> PageLayout:
    """Page 0: a paragraph of three lines from 70 pt, and one of three from
    115 pt whose second line, at 130 pt, is `beside` or a full line; a
    margin region of each of `margins`."""
    body = _region(
        _indented("Alpha begins here", 70),
        _full("and goes on over", 85),
        _short("its end.", 100),
        _indented("Beta begins here", 115),
        beside or _full("and goes on over", 130),
        _short("its own end.", 145),
    )
    return PageLayout(0, (body, *(_region(margin) for margin in margins)), ())


_ALPHA = "Alpha begins here and goes on over its end."
_BETA = "Beta begins here and goes on over its own end."


def test_margin_note_before_the_paragraph_whose_first_line_it_is_beside() -> None:
    # Its top is 0.3 pitch below Beta's first line (rules 2 and 4).
    page = _two_paragraphs(_spread("Aside", 310, 340, 115 + 0.3 * _PITCH_PT))
    assert _placed(page) == (
        (BlockKind.PARAGRAPH, _ALPHA),
        (BlockKind.MARGIN_NOTE, "Aside"),
        (BlockKind.PARAGRAPH, _BETA),
    )


def test_margin_note_before_the_paragraph_of_the_flush_line_it_is_beside() -> None:
    # Beside Beta's second line, a full one: before Beta, which stays whole.
    page = _two_paragraphs(_spread("Aside", 310, 340, 130))
    assert _placed(page)[1:] == (
        (BlockKind.MARGIN_NOTE, "Aside"),
        (BlockKind.PARAGRAPH, _BETA),
    )


def test_margin_note_beside_an_indented_line_starts_a_paragraph_there() -> None:
    # Beta's second line is indented 20 pt after a full line: no paragraph
    # start by section 6, but one beside a margin note (rule 3).
    page = _two_paragraphs(
        _spread("Aside", 310, 340, 130), beside=_indented("Gamma starts here", 130)
    )
    assert _placed(page)[1:] == (
        (BlockKind.PARAGRAPH, "Beta begins here"),
        (BlockKind.MARGIN_NOTE, "Aside"),
        (BlockKind.PARAGRAPH, "Gamma starts here its own end."),
    )


def test_margin_note_beside_an_indented_line_after_a_hyphen_does_not_split() -> None:
    body = _region(
        _indented("Alpha begins here", 70),
        _full("and goes on a hyph-", 85),
        _indented("enated word on", 100),
        _short("its end.", 115),
    )
    page = PageLayout(0, (body, _region(_spread("Aside", 310, 340, 100))), ())
    assert _placed(page) == (
        (BlockKind.MARGIN_NOTE, "Aside"),
        (
            BlockKind.PARAGRAPH,
            "Alpha begins here and goes on a hyphenated word on its end.",
        ),
    )


def test_margin_note_cut_into_the_column_beside_an_indented_line_does_not_split() -> (
    None
):
    # A note cut into the column at 50 to 105 pt pushes the line beside it
    # to 110 pt (Stubbs): its indent is the note's, not a paragraph's.
    body = _region(
        _indented("Alpha begins here", 70),
        _full("and goes on over", 85),
        _spread("the cut in note", 110, 300, 100),
        _short("its end.", 115),
    )
    page = PageLayout(0, (body, _region(_spread("Cut in", 50, 105, 100))), ())
    assert _placed(page) == (
        (BlockKind.MARGIN_NOTE, "Cut in"),
        (
            BlockKind.PARAGRAPH,
            "Alpha begins here and goes on over the cut in note its end.",
        ),
    )


def test_margin_note_before_a_paragraph_run_on_from_the_page_before() -> None:
    # Page 1's margin note stands beside its first line, which continues the
    # paragraph of page 0: it goes before that paragraph, after page 0's
    # margin note, which stands beside the paragraph's first line.
    page_0 = PageLayout(
        0,
        (
            _region(_indented("Alpha begins here", 70), *_five_full_lines(85, "body")),
            _region(_spread("Zero", 310, 340, 70)),
        ),
        (),
    )
    page_1 = PageLayout(
        1,
        (
            _region(
                *_five_full_lines(70, "more"),
                _short("its end.", 145),
                _indented("Beta begins here", 160),
            ),
            _region(_spread("One", 310, 340, 72)),
        ),
        (),
    )
    blocks = make_blocks(_lines_of(page_0, page_1), _NO_WORDS, workers=1)
    assert tuple(
        (block.id, block.kind, block_text(block).split(" ")[0])
        for block in blocks.blocks
    ) == (
        ("b-p0000-001", BlockKind.MARGIN_NOTE, "Zero"),
        ("b-p0001-001", BlockKind.MARGIN_NOTE, "One"),
        ("b-p0000-002", BlockKind.PARAGRAPH, "Alpha"),
        ("b-p0001-002", BlockKind.PARAGRAPH, "Beta"),
    )


def test_margin_note_before_one_paragraph_goes_from_the_top_down() -> None:
    # Layout gives the lower region first, 2.7 pitches below the upper's
    # bottom; both stand beside Beta, the lower nearest its last line.
    page = _two_paragraphs(
        _spread("Lower", 310, 340, 165), _spread("Upper", 310, 340, 115)
    )
    assert _placed(page)[1:3] == (
        (BlockKind.MARGIN_NOTE, "Upper"),
        (BlockKind.MARGIN_NOTE, "Lower"),
    )


@pytest.mark.parametrize(("gap", "joined"), [(37.5, True), (38.0, False)])
def test_margin_note_before_its_paragraph_one_block_within_2_5_pitches(
    gap: float, joined: bool
) -> None:
    # Two regions on the right, the lower beside a flush line of Alpha
    # (rule 1): one printed note within 2.5 pitches, 37.5 pt.
    upper = _region(_spread("One", 310, 340, 40))
    lower = _region(_spread("note.", 310, 340, 50 + gap))
    body = _region(
        _indented("Alpha begins here", 40),
        *(_full(f"and goes on {n}", 55 + 15 * n) for n in range(4)),
        _short("its end.", 115),
    )
    page = PageLayout(0, (body, upper, lower), ())
    kinds = tuple(kind for kind, _ in _placed(page))
    texts = tuple(text for kind, text in _placed(page) if kind is BlockKind.MARGIN_NOTE)
    assert texts == (("One note.",) if joined else ("One", "note."))
    assert kinds[-1] is BlockKind.PARAGRAPH


def test_margin_note_before_each_paragraph_when_the_lower_is_beside_a_first_line() -> (
    None
):
    # The lower region is 1.2 pitches below the upper, but beside Beta's
    # first line: two printed notes (rule 1).
    page = _two_paragraphs(
        _spread("Upper", 310, 340, 87), _spread("Lower", 310, 340, 115)
    )
    assert _placed(page) == (
        (BlockKind.MARGIN_NOTE, "Upper"),
        (BlockKind.PARAGRAPH, _ALPHA),
        (BlockKind.MARGIN_NOTE, "Lower"),
        (BlockKind.PARAGRAPH, _BETA),
    )


def test_margin_note_regions_of_one_note_are_not_joined_at_a_hyphen() -> None:
    # Two regions of one printed note 1.5 pitches apart: a line between them
    # went unread, so "pea-" is not joined to "the" (Domesday page 90 gave
    # "peathe").
    upper = _region(_spread("The pea-", 310, 345, 40))
    lower = _region(_spread("the royal", 310, 345, 50 + 22.5))
    body = _region(
        _indented("Alpha begins here", 40),
        *(_full(f"and goes on {n}", 55 + 15 * n) for n in range(4)),
        _short("its end.", 115),
    )
    lines = _lines_of(PageLayout(0, (body, upper, lower), ()))
    blocks = make_blocks(lines, frozenset({"peathe"}), workers=1)
    assert tuple(
        block_text(block)
        for block in blocks.blocks
        if block.kind is BlockKind.MARGIN_NOTE
    ) == ("The pea- the royal",)
    assert blocks.word_changes == ()


def test_margin_notes_on_the_two_sides_are_not_joined() -> None:
    # A region left of the column and one right of it, at the same height
    # within 2.5 pitches: each is a note of its own.
    page = _two_paragraphs(_spread("Right", 310, 340, 85), _spread("Left", 10, 40, 95))
    assert tuple(
        text for kind, text in _placed(page) if kind is BlockKind.MARGIN_NOTE
    ) == ("Right", "Left")


# Rules of sections 11 and 12 each pinned by a literal case (review S11)


def _glued(word: str) -> Reference:
    reference = reference_candidate(word)
    assert reference is not None
    return reference


@pytest.mark.parametrize(
    ("word", "value", "score"),
    [
        ("x7", 1, 2),
        ("x5", 3, 2),
        ("x8", 6, 2),
        ("x4", 1, 2),
        ("x9", 8, 2),
        ("x8", 2, 2),
        ("x2", 7, 0),
        ("x81", 3, 0),
        ("x.^", None, 2),
        ("x.^", 1, 1),
    ],
)
def test_referenced_pair_score_by_the_digits_the_ocr_confuses(
    word: str, value: int | None, score: int
) -> None:
    # "x81" against 3: one digit differs only if the lengths are equal.
    assert pair_score(_glued(word), value) == score


def _candidate(word: str, position: int) -> Candidate:
    return Candidate(0, position, 0, _glued(word))


def test_referenced_book_form_on_a_tie_is_the_glued_number() -> None:
    notes = (NoteToMatch(0, 0, 1), NoteToMatch(1, 0, 2))
    candidates = (_candidate("x1", 0), _candidate("(2)", 1))
    assert reference_form(notes, candidates) is ReferenceForm.GLUED


def test_note_marker_form_of_the_book_on_a_tie_is_digits() -> None:
    assert book_marker_form(("(1)", "1", "*")) is MarkerForm.DIGITS
    assert book_marker_form(("(1)", "*")) is MarkerForm.BRACKETED


@pytest.mark.parametrize(("word", "marker"), [("(ab", True), ("(abc", False)])
def test_note_marker_loose_bracket_holds_at_most_two_letters_or_digits(
    word: str, marker: bool
) -> None:
    assert (note_marker(word) is not None) is marker


def test_referenced_endnotes_are_matched_in_the_order_of_their_values() -> None:
    # Note 2 printed before note 1: in printed order note 2 would take "y2"
    # and note 1 could not take the earlier "x1".
    notes = (NoteToMatch(0, 5, 2), NoteToMatch(1, 5, 1))
    candidates = (_candidate("x1", 0), _candidate("y2", 1))
    assert tuple(
        (link.note, link.candidate.word) for link in match_endnotes(notes, candidates)
    ) == ((1, 0), (0, 1))


def test_referenced_a_bracketed_reference_with_a_letter_is_left_out_first() -> None:
    # "(i)" comes before "(1)": left out before the matching, it does not
    # take note 1's place, and "(1)" is linked (structure spec, section 11).
    lines = _lines_of(
        _referenced_page(0, "first (i) second (1)", "(1) One.", "(2) Two.")
    )
    blocks = make_blocks(lines, _NO_WORDS, workers=1)
    assert _references(blocks) == (("(1)", "(1)"),)


def test_referenced_margin_note_gives_no_candidate() -> None:
    page = _referenced_page(0, "plain words", "1 One.")
    margin = _region(_spread("Aside1", 310, 340, 85))
    blocks = make_blocks(
        _lines_of(replace(page, regions=(*page.regions, margin))), _NO_WORDS, workers=1
    )
    assert _references(blocks) == ()
    assert not blocks.notes[0].referenced


@pytest.mark.parametrize(
    ("second", "after", "notes"),
    [("2", "12", 2), ("(3)", "Dialogus", 1)],
)
def test_footnote_second_marker_before_a_digit_and_of_at_most_2_characters(
    second: str, after: str, notes: int
) -> None:
    line = _placed_line(
        300,
        ("1", 50, 55),
        ("Ibid.", 59, 84),
        ("b.", 88, 96),
        (second, 110, 110 + 5 * len(second)),
        (after, 130, 170),
        ("i.", 174, 180),
    )
    blocks = make_blocks(_lines_of(_page_with_band(0, line)), _NO_WORDS, workers=1)
    assert len(blocks.notes) == notes


def test_footnote_whose_only_word_is_its_marker_keeps_it_as_text() -> None:
    page = _page_with_band(
        0,
        _note_line("1 A note that runs", 300, 62),
        _note_line("on and ends.", 300 + _NOTE_PITCH_PT, 50, 120),
        _note_line("8", 300 + 2 * _NOTE_PITCH_PT, 62, 67),
    )
    blocks = make_blocks(_lines_of(page), _NO_WORDS, workers=1)
    assert _markers_and_texts(blocks) == (
        ("1", "A note that runs on and ends."),
        ("", "8"),
    )


def test_footnote_left_in_the_body_with_equal_markers_is_taken() -> None:
    lines = _body_notes_pages(("(1)", "(1)", "(2)"))
    blocks = make_blocks(lines, _NO_WORDS, workers=1)
    assert _page_1_blocks(blocks) == ()


def test_footnote_left_in_the_body_needs_text_above_it() -> None:
    pages = _body_notes_pages(("(1)", "(2)", "(3)")).pages
    region = pages[1].regions[0]
    only_notes = replace(region, lines=region.lines[5:])
    page_1 = replace(pages[1], regions=(only_notes,))
    blocks = make_blocks(_lines_of(pages[0], page_1, pages[2]), _NO_WORDS, workers=1)
    assert tuple(note.marker for note in blocks.notes) == ("(1)",)


def _section_pages(
    markers: tuple[str, ...],
    *,
    after: str | None = None,
    next_page_markers: tuple[str, ...] = (),
) -> LinesFile:
    """Page 0: a body paragraph with "Law1". Page 1: a paragraph per marker
    of `markers`, each an indented line, a full one and a short one, then
    a paragraph `after` without a marker. Page 2: a paragraph per marker of
    `next_page_markers` and then `after`, when there are such markers, and
    a paragraph without a marker on the page after the markers."""
    page_0 = _body_page(
        0, _indented("A paragraph with Law1 in it", 70), *_five_full_lines(85, "body")
    )
    texts = [(f"{marker} The note which", "ends.") for marker in markers]
    next_texts = [(f"{marker} The note which", "ends.") for marker in next_page_markers]
    if after is not None:
        (next_texts if next_page_markers else texts).append((after, "ends."))
    lines = tuple(
        line
        for number, (start, end) in enumerate(texts)
        for line in (
            _indented(start, 70 + 45 * number),
            _full("goes on over a full line", 85 + 45 * number),
            _short(end, 100 + 45 * number),
        )
    )
    last = (
        _indented("A paragraph after the section", 70),
        _full("goes on over a full line", 85),
        _short("and ends.", 100),
    )
    if not next_page_markers:
        return _lines_of(page_0, _body_page(1, *lines), _body_page(2, *last))
    next_lines = tuple(
        line
        for number, (start, end) in enumerate(next_texts)
        for line in (
            _indented(start, 70 + 45 * number),
            _full("goes on over a full line", 85 + 45 * number),
            _short(end, 100 + 45 * number),
        )
    )
    return _lines_of(
        page_0,
        _body_page(1, *lines),
        _body_page(2, *next_lines),
        _body_page(3, *last),
    )


def test_endnote_section_spans_every_long_run_and_its_last_page() -> None:
    # Two runs of at least 8, on pages 1 and 2, the second starting at "3.";
    # a paragraph without a marker after the last marker, on page 2, is in
    # the section, and page 3's paragraph is out of it.
    first_run = tuple(f"{n}." for n in range(1, 10))
    second_run = tuple(f"{n}." for n in range(3, 12))
    markers = (*first_run, *second_run)
    blocks = make_blocks(
        _section_pages(
            first_run, after="A paragraph of note 11", next_page_markers=second_run
        ),
        _NO_WORDS,
        workers=1,
    )
    endnotes = _endnotes_of(blocks)
    assert tuple(marker for marker, _ in endnotes) == markers
    assert (
        endnotes[-1][1][-1] == "A paragraph of note 11 goes on over a full line ends."
    )
    assert block_text(blocks.blocks[-1]).startswith("A paragraph after the section")


def test_endnote_takes_no_candidate_a_footnote_took() -> None:
    # "Law1" refers to the footnote of its page; endnote 1 stays unlinked.
    lines = _section_pages(tuple(f"{n}." for n in range(1, 10)))
    page_0 = replace(
        lines.pages[0],
        regions=(
            *lines.pages[0].regions,
            _region(
                _note_line("1 A footnote.", 300, 62, 160),
                _note_line("and its end.", 300 + _NOTE_PITCH_PT, 50, 120),
            ),
        ),
    )
    blocks = make_blocks(_lines_of(page_0, *lines.pages[1:]), _NO_WORDS, workers=1)
    assert len(_endnotes_of(blocks)) == 9
    kinds = {note.id: note.kind for note in blocks.notes}
    assert tuple(
        kinds[span.note_ref]
        for block in blocks.blocks
        for span in block.spans
        if span.note_ref is not None
    ) == (NoteKind.FOOTNOTE,)


def test_endnote_page_keeps_its_small_lines_and_lists_endnotes_first() -> None:
    # Page 0 gives the book a bracketed form numbered per page. On the
    # section's page, small marker lines at the foot of the body are not
    # taken as notes, and the page's endnotes come before its footnote.
    lines = _section_pages(tuple(f"{n}." for n in range(1, 10)))
    band = _region(
        _note_line("(1) A note.", 300, 62, 160),
        _note_line("and its end.", 300 + _NOTE_PITCH_PT, 50, 120),
    )
    page_0 = replace(lines.pages[0], regions=(*lines.pages[0].regions, band))
    section = lines.pages[1].regions[0]
    small = tuple(
        _spread(f"({n}) Small {n}.", 70, 200, 470 + 12 * n, _SMALL_PT)
        for n in range(1, 4)
    )
    band_1 = _region(
        _note_line("* A note.", 530, 62, 160),
        _note_line("and its end.", 530 + _NOTE_PITCH_PT, 50, 120),
    )
    page_1 = replace(
        lines.pages[1],
        regions=(replace(section, lines=(*section.lines, *small)), band_1),
    )
    blocks = make_blocks(
        _lines_of(page_0, page_1, lines.pages[2]), _NO_WORDS, workers=1
    )
    on_page_1 = tuple(
        (note.kind, note.marker)
        for note in blocks.notes
        if note.origin[0].page_index == 1
    )
    assert on_page_1 == (
        *((NoteKind.ENDNOTE, f"{n}.") for n in range(1, 10)),
        (NoteKind.FOOTNOTE, "*"),
    )
    assert "(3) Small 3." in _endnotes_of(blocks)[-1][1][-1]


def test_make_blocks_with_notes_with_1_worker_and_with_3_gives_the_same_value() -> None:
    lines = _lines_of(
        *_note_running_over((PageLayout(1, (), ()),)).pages,
        *(
            _page_with_band(
                index,
                _note_line("13The note.", 300, 62, 200),
                _note_line("14 Another note.", 300 + _NOTE_PITCH_PT, 62, 200),
            )
            for index in range(3, 9)
        ),
    )
    assert make_blocks(lines, _NO_WORDS, workers=1) == make_blocks(
        lines, _NO_WORDS, workers=3
    )


# Headings (structure spec, section 14). The body line pitch is 15 pt: the
# pages hold more lines 15 pt apart than any other distance.


def _centred_line(text: str, top: float, width: float = 90.0) -> Line:
    """A line `width` pt wide centred in the column from 50 to 300 pt."""
    return _spread(text, 175 - width / 2, 175 + width / 2, top)


def _around(*heading: Line, gap_after: float = 22.5) -> PageLayout:
    """Page 0: three full lines from 70 pt, then the lines `heading`, then
    five full lines from `gap_after` pt below the last of them."""
    after = heading[-1].box.top + gap_after
    return _body_page(
        0,
        *(_full(f"before {n} of the page", 70 + _PITCH_PT * n) for n in range(3)),
        *heading,
        *(_full(f"after {n} of the page", after + _PITCH_PT * n) for n in range(5)),
    )


def _kinds_and_texts(
    blocks: BlocksFile,
) -> tuple[tuple[str, int | None, str | None, str], ...]:
    return tuple(
        (block.kind.value, block.level, block.label, block_text(block))
        for block in blocks.blocks
    )


_BEFORE = (
    "paragraph",
    None,
    None,
    "before 0 of the page before 1 of the page before 2 of the page",
)
_AFTER = (
    "paragraph",
    None,
    None,
    " ".join(f"after {n} of the page" for n in range(5)),
)


def test_heading_chapter_label_and_its_title_are_one_level_1_heading() -> None:
    # "CHAPTER III." 2 pitches below the text, its title 1.5 pitches below it.
    lines = _lines_of(
        _around(
            _centred_line("CHAPTER III.", 130), _centred_line("THE EARLY YEARS.", 152.5)
        )
    )
    blocks = make_blocks(lines, _NO_WORDS, workers=1)
    assert _kinds_and_texts(blocks) == (
        _BEFORE,
        ("heading", 1, "CHAPTER III.", "THE EARLY YEARS."),
        _AFTER,
    )
    assert blocks.blocks[1].origin == (Origin(0, Box(130, 130, 220, 162.5)),)
    check_stage(FidelityBoundary.STRUCTURE, lines, blocks)


# Structure spec section 34: a line read by Tesseract whose median
# confidence is below 60 is no heading; the words of Kadesh's junk line of
# page 32, "KELP IPM DS", had 8 to 25.


def _with_confidences(line: Line, *confidences: float | None) -> Line:
    return replace(
        line,
        words=tuple(
            replace(word, ocr_confidence=confidence)
            for word, confidence in zip(line.words, confidences, strict=True)
        ),
    )


@pytest.mark.parametrize(
    ("confidences", "kind"),
    [
        ((8.0, 25.0, 49.0, 30.0), "paragraph"),
        ((90.0, 90.0, 90.0, 90.0), "heading"),
        ((None, None, None, None), "heading"),
        ((90.0, 8.0, 59.0, 70.0), "heading"),
        ((8.0, 25.0, 49.0, 59.0), "paragraph"),
        ((54.0, 55.0, 55.0, 56.0), "paragraph"),
        ((8.0, None, 25.0, None), "paragraph"),
        ((8.0, None, None, None), "heading"),
    ],
    ids=[
        "low",
        "high",
        "layer",
        "median_64_5",
        "median_37",
        "median_55",
        "half_layer_low",
        "mostly_layer",
    ],
)
def test_centred_line_in_capitals_is_a_heading_unless_tesseract_read_it_poorly(
    confidences: tuple[float | None, ...], kind: str
) -> None:
    line = _with_confidences(_centred_line("KELP IPM DSRT WORD", 130), *confidences)
    blocks = make_blocks(_lines_of(_around(line)), _NO_WORDS, workers=1)
    # The line is in the text either way, in a heading or in a paragraph.
    assert [
        block.kind.value for block in blocks.blocks if "KELP" in block_text(block)
    ] == [kind]


# Structure spec section 14: a line right below a line Tesseract read
# poorly takes no heading by the gaps; Kadesh's page 39 prints the
# translation of a row of hieroglyphs, centred, 3.2 pitches below the row.


@pytest.mark.parametrize(
    ("row_confidences", "kind"),
    [((8.0, 25.0, 49.0, 30.0), "paragraph"), ((90.0, 90.0, 90.0, 90.0), "heading")],
    ids=["row_read_poorly", "row_read_well"],
)
def test_centred_line_below_a_line_read_poorly_is_no_heading_by_its_gaps(
    row_confidences: tuple[float, ...], kind: str
) -> None:
    # The row has no letter, so it is no heading itself whatever its
    # confidence; the translation is 2 pitches below it and 1.5 above the
    # text after it.
    row = _with_confidences(_centred_line("16. 12 345 6789", 130), *row_confidences)
    translation = _centred_line("The stand which his majesty made.", 160, width=170)
    lines = _lines_of(_around(row, translation))
    blocks = make_blocks(lines, _NO_WORDS, workers=1)
    assert [
        block.kind.value
        for block in blocks.blocks
        if "stand which" in block_text(block)
    ] == [kind]
    check_stage(FidelityBoundary.STRUCTURE, lines, blocks)


def test_centred_line_in_capitals_below_a_line_read_poorly_is_a_heading() -> None:
    row = _with_confidences(
        _centred_line("16. 12 345 6789", 130), 8.0, 25.0, 49.0, 30.0
    )
    title = _centred_line("THE STAND OF HIS MAJESTY", 160, width=120)
    blocks = make_blocks(_lines_of(_around(row, title)), _NO_WORDS, workers=1)
    assert [
        block.kind.value for block in blocks.blocks if "STAND" in block_text(block)
    ] == ["heading"]


def test_heading_of_one_line_has_no_label() -> None:
    blocks = make_blocks(
        _lines_of(_around(_centred_line("INDEX", 130))), _NO_WORDS, workers=1
    )
    assert _kinds_and_texts(blocks)[1] == ("heading", 2, None, "INDEX")


def test_heading_label_alone_has_no_label_and_is_level_1() -> None:
    blocks = make_blocks(
        _lines_of(_around(_centred_line("CHAPTER III.", 130))), _NO_WORDS, workers=1
    )
    assert _kinds_and_texts(blocks)[1] == ("heading", 1, None, "CHAPTER III.")


@pytest.mark.parametrize(
    ("gap_above", "heading"), [(37.5, True), (30.0, True), (29.5, False), (22.5, False)]
)
def test_heading_in_lower_case_needs_a_gap_above_of_2_pitches(
    gap_above: float, heading: bool
) -> None:
    # The line before the title is at 100 pt; the title is 1.5 pitches above
    # the text after it.
    blocks = make_blocks(
        _lines_of(_around(_centred_line("The Plan of the Survey.", 100 + gap_above))),
        _NO_WORDS,
        workers=1,
    )
    title = _kinds_and_texts(blocks)[1]
    assert title == (
        ("heading", 2, None, "The Plan of the Survey.")
        if heading
        else ("paragraph", None, None, "The Plan of the Survey.")
    )


@pytest.mark.parametrize(("gap_below", "heading"), [(19.5, True), (19.0, False)])
def test_heading_in_lower_case_needs_a_gap_below_of_1_3_pitches(
    gap_below: float, heading: bool
) -> None:
    blocks = make_blocks(
        _lines_of(
            _around(
                _centred_line("The Plan of the Survey.", 137.5), gap_after=gap_below
            )
        ),
        _NO_WORDS,
        workers=1,
    )
    assert (_kinds_and_texts(blocks)[1][0] == "heading") is heading


@pytest.mark.parametrize(
    ("text", "heading"),
    [
        ("§ 1. Plan of the Survey.", True),
        ("§ 1. Plan of the Survey, pp. 9 — 26.", False),
        ("(VIII)", False),
        ("2»K O ) ? 4. )5", False),
    ],
)
def test_heading_line_ending_with_a_number_or_without_a_long_word_is_none(
    text: str, heading: bool
) -> None:
    blocks = make_blocks(
        _lines_of(_around(_centred_line(text, 137.5, width=150))), _NO_WORDS, workers=1
    )
    assert (_kinds_and_texts(blocks)[1][0] == "heading") is heading


def test_heading_on_a_page_of_contents_pages_is_only_the_runs_title() -> None:
    # Spec section 30, rule 1: the run's first line is its title, a heading
    # of level 1; "CHAPTER III." is a lone label over its entry's title.
    lines = _lines_of(
        _around(
            _centred_line("CHAPTER III.", 130), _centred_line("THE EARLY YEARS.", 152.5)
        )
    )
    blocks = make_blocks(lines, _NO_WORDS, contents_pages=frozenset({0}), workers=1)
    assert tuple(
        (block.level, block_text(block))
        for block in blocks.blocks
        if block.kind is BlockKind.HEADING
    ) == ((1, "before 0 of the page"),)
    assert _kinds_and_texts(blocks)[2] == (
        "contents_entry",
        1,
        "CHAPTER III.",
        "THE EARLY YEARS.",
    )


def test_heading_label_of_a_roman_numeral_joins_its_title() -> None:
    # Haskins' "V", fewer than 4 letters, 0.9 pitch above its title.
    blocks = make_blocks(
        _lines_of(
            _around(
                _centred_line("V", 130, width=10),
                _centred_line("NORMANDY AND FRANCE", 143.5),
            )
        ),
        _NO_WORDS,
        workers=1,
    )
    assert _kinds_and_texts(blocks)[1] == ("heading", 1, "V", "NORMANDY AND FRANCE")


def test_heading_roman_numeral_alone_is_no_heading() -> None:
    blocks = make_blocks(
        _lines_of(_around(_centred_line("V", 130, width=10))), _NO_WORDS, workers=1
    )
    assert _kinds_and_texts(blocks)[1] == ("paragraph", None, None, "V")


@pytest.mark.parametrize(
    ("title", "heading"),
    [
        ("L'EXPERIENCE ET L'ECHEC DE LA POLITIQUE MODEREE", True),
        ("L'Experience et l'echec de la politique moderee", False),
    ],
)
def test_heading_continuation_in_capitals_as_wide_as_the_column(
    title: str, heading: bool
) -> None:
    # Mariéjol's title that fills the column, 2.2 pitches below "CHAPITRE V"
    # and 2.2 above the text.
    blocks = make_blocks(
        _lines_of(
            _around(_centred_line("CHAPITRE V", 130), _full(title, 163), gap_after=33)
        ),
        _NO_WORDS,
        workers=1,
    )
    after = " ".join(f"after {n} of the page" for n in range(5))
    assert _kinds_and_texts(blocks)[1:] == (
        (("heading", 1, "CHAPITRE V", title), _AFTER)
        if heading
        else (
            ("heading", 1, None, "CHAPITRE V"),
            ("paragraph", None, None, f"{title} {after}"),
        )
    )


def test_heading_continuation_in_lower_case_centred() -> None:
    # Stubbs' "John.", read in lower case, under "CHAPTER VII.".
    blocks = make_blocks(
        _lines_of(
            _around(
                _centred_line("CHAPTER VII.", 130), _centred_line("John.", 152.5, 30)
            )
        ),
        _NO_WORDS,
        workers=1,
    )
    assert _kinds_and_texts(blocks)[1] == ("heading", 1, "CHAPTER VII.", "John.")


@pytest.mark.parametrize(("distance", "one_block"), [(39.0, True), (39.5, False)])
def test_heading_lines_are_one_block_within_2_6_pitches(
    distance: float, one_block: bool
) -> None:
    blocks = make_blocks(
        _lines_of(
            _around(
                _centred_line("THE NORMANS IN HISTORY", 130),
                _centred_line("NORMANDY AND FRANCE", 130 + distance),
            )
        ),
        _NO_WORDS,
        workers=1,
    )
    headings = tuple(
        block_text(block) for block in blocks.blocks if block.kind is BlockKind.HEADING
    )
    assert headings == (
        ("THE NORMANS IN HISTORY NORMANDY AND FRANCE",)
        if one_block
        else ("THE NORMANS IN HISTORY", "NORMANDY AND FRANCE")
    )


@pytest.mark.parametrize(("distance", "one_block"), [(60.0, True), (60.5, False)])
def test_heading_title_joins_a_label_alone_within_4_pitches(
    distance: float, one_block: bool
) -> None:
    # Domesday's "ESSAY I." 3.4 pitches above "DOMESDAY BOOK.".
    blocks = make_blocks(
        _lines_of(
            _around(
                _centred_line("ESSAY I.", 130),
                _centred_line("DOMESDAY BOOK.", 130 + distance),
            )
        ),
        _NO_WORDS,
        workers=1,
    )
    headings = tuple(
        (block.label, block_text(block))
        for block in blocks.blocks
        if block.kind is BlockKind.HEADING
    )
    assert headings == (
        (("ESSAY I.", "DOMESDAY BOOK."),)
        if one_block
        else ((None, "ESSAY I."), (None, "DOMESDAY BOOK."))
    )


def test_heading_first_on_a_page_without_running_head_is_level_1() -> None:
    # "PREFACE" first on its page; "I. The Evolution of Political Theory."
    # lower in it, a numbered section, level 2.
    page = _body_page(
        0,
        _centred_line("PREFACE", 70),
        *(_full(f"first {n} of the page", 100 + _PITCH_PT * n) for n in range(5)),
        _centred_line("I. The Evolution of Political Theory.", 205, width=200),
        *(_full(f"second {n} of the page", 235 + _PITCH_PT * n) for n in range(5)),
    )
    blocks = make_blocks(_lines_of(page), _NO_WORDS, workers=1)
    assert tuple(
        (block.level, block_text(block))
        for block in blocks.blocks
        if block.kind is BlockKind.HEADING
    ) == ((1, "PREFACE"), (2, "I. The Evolution of Political Theory."))


def _headed_page(index: int, *body: Region) -> PageLayout:
    """A page whose head line is "THE BOOK" and its printed page number,
    index + 15, above the regions `body`."""
    head = _region(_line(f"THE BOOK {index + 15}", _BODY_LEFT_PT, 36))
    return PageLayout(index, (head, *body), ())


def _headed_pages(page_11: tuple[Region, ...]) -> LinesFile:
    """Pages 10 to 15, each with a running head; page 11 holds the regions
    `page_11`, every other five full lines."""
    return _lines_of(
        *(
            _headed_page(index, *page_11)
            if index == 11
            else _headed_page(index, _region(*_five_full_lines(70, f"page{index}")))
            for index in range(10, 16)
        )
    )


def test_heading_first_on_a_page_with_a_running_head_is_level_2() -> None:
    # Page 11's body starts with "PREFACE", centred in a region of its own.
    blocks = make_blocks(
        _headed_pages(
            (
                _region(_centred_line("PREFACE", 70)),
                _region(*_five_full_lines(100, "page11")),
            )
        ),
        _NO_WORDS,
        workers=1,
    )
    assert len(_removals_of(11, blocks)) == 2
    assert tuple(
        (block.level, block_text(block))
        for block in blocks.blocks
        if block.kind is BlockKind.HEADING
    ) == ((2, "PREFACE"),)


@pytest.mark.parametrize(("body_lines", "heading"), [(0, True), (3, True), (4, False)])
def test_heading_centred_over_a_band_on_a_page_of_fewer_than_5_body_lines(
    body_lines: int, heading: bool
) -> None:
    # As on Haskins' page 129: a heading in a region of its own above a band
    # of small type, so that the body column is the heading itself (another
    # title than "BIBLIOGRAPHICAL NOTE", whose band would be paragraphs).
    # With 4 more short body lines at the left, the heading's region is
    # measured against them, and the band is not looked at.
    short_lines = tuple(
        _spread(f"short {n} line", 50, 140, 85 + _PITCH_PT * n)
        for n in range(body_lines)
    )
    band_top = 100 + _PITCH_PT * body_lines
    band = _region(
        *(
            _spread(
                f"small {n} of the band type", 50, 300, band_top + 9 * n, height=7.0
            )
            for n in range(6)
        )
    )
    regions = (
        _region(_centred_line("NOTE ON THE SOURCES", 65, 120)),
        *((_region(*short_lines),) if short_lines else ()),
        band,
    )
    blocks = make_blocks(_headed_pages(regions), _NO_WORDS, workers=1)
    assert any(r.reason is RemovalReason.RUNNING_HEAD for r in _removals_of(11, blocks))
    assert len(blocks.notes) == 1
    assert tuple(
        block_text(block) for block in blocks.blocks if block.kind is BlockKind.HEADING
    ) == (("NOTE ON THE SOURCES",) if heading else ())


@pytest.mark.parametrize(
    ("text", "heading"),
    [
        ("ONE TWO", False),
        ("ONE FOUR", True),
        ("12345 ABCD", False),
        ("1234 ABCD", True),
    ],
)
def test_heading_needs_a_word_of_4_letters_and_half_its_characters_letters(
    text: str, heading: bool
) -> None:
    blocks = make_blocks(
        _lines_of(_around(_centred_line(text, 130))), _NO_WORDS, workers=1
    )
    assert (_kinds_and_texts(blocks)[1][0] == "heading") is heading


@pytest.mark.parametrize(("centred", "heading"), [(True, True), (False, False)])
def test_heading_label_joins_its_title_only_when_centred(
    centred: bool, heading: bool
) -> None:
    label = _centred_line("V", 130, width=10) if centred else _spread("V", 50, 60, 130)
    blocks = make_blocks(
        _lines_of(_around(label, _centred_line("NORMANDY AND FRANCE", 143.5))),
        _NO_WORDS,
        workers=1,
    )
    assert (_kinds_and_texts(blocks)[1][2] == "V") is heading


def test_heading_starting_with_a_label_word_is_level_1_with_its_words() -> None:
    # "PART THE FIRST" starts with a label word, mid-page: level 1, no label
    # since it is one line.
    blocks = make_blocks(
        _lines_of(_around(_centred_line("PART THE FIRST", 130))), _NO_WORDS, workers=1
    )
    assert _kinds_and_texts(blocks)[1] == ("heading", 1, None, "PART THE FIRST")


@pytest.mark.parametrize(
    ("above", "distance", "gap_after", "continued"),
    [
        ("THE OPENING TITLE", 39.0, 33.0, True),
        ("THE OPENING TITLE", 39.5, 33.0, False),
        ("THE OPENING TITLE", 33.0, 22.5, True),
        ("THE OPENING TITLE", 33.0, 22.0, False),
        # Below a chapter label alone, 4.0 pitches (the plan owner-books,
        # structure spec section 14).
        ("CHAPITRE V", 60.0, 33.0, True),
        ("CHAPITRE V", 60.5, 33.0, False),
    ],
)
def test_heading_continuation_in_capitals_within_2_6_pitches_and_1_5_above_the_text(
    above: str, distance: float, gap_after: float, continued: bool
) -> None:
    title = "L'EXPERIENCE ET L'ECHEC DE LA POLITIQUE MODEREE"
    blocks = make_blocks(
        _lines_of(
            _around(
                _centred_line(above, 130),
                _full(title, 130 + distance),
                gap_after=gap_after,
            )
        ),
        _NO_WORDS,
        workers=1,
    )
    # The title is the heading's text, after the label or the line above.
    assert _kinds_and_texts(blocks)[1][3].endswith(title) is continued


@pytest.mark.parametrize(
    ("title", "continued"),
    [
        ("L'EXPERIENCE ET L'ECHEC DE LA POLITIQUE MODEREe", True),
        ("L'EXPERIENCE ET L'ECHEC DE LA POLITIQUE Moderee", False),
    ],
)
def test_heading_continuation_has_0_9_of_its_letters_in_capitals(
    title: str, continued: bool
) -> None:
    # 37 of 38 letters upper case, 0.97, against 33 of 38, 0.87.
    blocks = make_blocks(
        _lines_of(
            _around(_centred_line("CHAPITRE V", 130), _full(title, 163), gap_after=33)
        ),
        _NO_WORDS,
        workers=1,
    )
    assert (_kinds_and_texts(blocks)[1][3] == title) is continued


def test_reference_in_a_heading_is_linked() -> None:
    # Kadesh's title, "STRATEGY*", linked to the note the band starts with "*".
    page = PageLayout(
        0,
        (
            _region(
                *(
                    _full(f"before {n} of the page", 70 + _PITCH_PT * n)
                    for n in range(3)
                ),
                _centred_line("A MILITARY STRATEGY*", 130, width=140),
                *(
                    _full(f"after {n} of the page", 152.5 + _PITCH_PT * n)
                    for n in range(5)
                ),
            ),
            _region(_note_line("* Paper read at Hamburg.", 300, 62, 200)),
        ),
        (),
    )
    blocks = make_blocks(_lines_of(page), _NO_WORDS, workers=1)
    heading = blocks.blocks[1]
    assert heading.kind is BlockKind.HEADING
    assert [span.note_ref for span in heading.spans] == [None, blocks.notes[0].id]


# Chapter summaries (structure spec, section 15)


def _summary_page(*summary: Line) -> PageLayout:
    """A page whose heading "CHAPTER III." / "THE EARLY YEARS." is followed
    by the lines `summary`, 15 pt apart from 167.5 pt, and a paragraph whose
    first line is not indented."""
    after = 167.5 + _PITCH_PT * len(summary)
    return _around(
        _centred_line("CHAPTER III.", 130),
        _centred_line("THE EARLY YEARS.", 152.5),
        *(replace_top(line, 167.5 + _PITCH_PT * n) for n, line in enumerate(summary)),
        gap_after=after - 152.5,
    )


def replace_top(line: Line, top: float) -> Line:
    """`line` moved so that its top is at `top`."""
    shift = top - line.box.top
    return Line(
        replace(line.box, top=line.box.top + shift, bottom=line.box.bottom + shift),
        tuple(
            replace(
                word,
                box=replace(
                    word.box, top=word.box.top + shift, bottom=word.box.bottom + shift
                ),
            )
            for word in line.words
        ),
    )


def _hanging(text: str, indent: float, right: float = _RIGHT_PT) -> Line:
    return _spread(text, _BODY_LEFT_PT + indent, right, 0)


_SUMMARY_TEXTS = (
    "Terms of accession — His character — His early",
    "reforms — His relations with France — Summary",
    "of nine years' work.",
)


def test_chapter_summary_of_three_lines_with_a_hanging_indent_is_one_block() -> None:
    lines = _lines_of(
        _summary_page(
            _hanging(_SUMMARY_TEXTS[0], 0),
            _hanging(_SUMMARY_TEXTS[1], 9),
            _hanging(_SUMMARY_TEXTS[2], 9, 150),
        )
    )
    blocks = make_blocks(lines, _NO_WORDS, workers=1)
    assert _kinds_and_texts(blocks)[1:] == (
        ("heading", 1, "CHAPTER III.", "THE EARLY YEARS."),
        ("chapter_summary", None, None, " ".join(_SUMMARY_TEXTS)),
        _AFTER,
    )
    check_stage(FidelityBoundary.STRUCTURE, lines, blocks)


@pytest.mark.parametrize(
    ("texts", "summary"),
    [
        (
            (
                "Terms of accession - His character, his early",
                "reforms - his relations with France, summary",
                "of nine years' work.",
            ),
            True,
        ),
        (
            (
                "Terms of accession-His character, his early",
                "reforms - his relations with France, summary",
                "of nine years' work.",
            ),
            False,
        ),
    ],
    ids=["two spaced hyphens", "one spaced hyphen and one glued"],
)
def test_chapter_summary_counts_a_spaced_hyphen_as_a_dash(
    texts: tuple[str, str, str], summary: bool
) -> None:
    blocks = make_blocks(
        _lines_of(
            _summary_page(
                _hanging(texts[0], 0), _hanging(texts[1], 9), _hanging(texts[2], 9, 150)
            )
        ),
        _NO_WORDS,
        workers=1,
    )
    assert (
        any(block.kind is BlockKind.CHAPTER_SUMMARY for block in blocks.blocks)
        is summary
    )


def test_chapter_summary_with_one_dash_is_paragraphs() -> None:
    texts = ("Terms of accession — his character, his early", *_SUMMARY_TEXTS[1:])
    texts = (texts[0], texts[1].replace(" — ", ", "), texts[2])
    blocks = make_blocks(
        _lines_of(
            _summary_page(
                _hanging(texts[0], 0), _hanging(texts[1], 9), _hanging(texts[2], 9, 150)
            )
        ),
        _NO_WORDS,
        workers=1,
    )
    assert not any(block.kind is BlockKind.CHAPTER_SUMMARY for block in blocks.blocks)


@pytest.mark.parametrize(
    ("first_indent", "second_indent", "summary"),
    [(0, 9, True), (4.9, 9, True), (5, 9, False), (0, 4.9, False)],
)
def test_chapter_summary_starts_at_the_left_edge_and_hangs_5_pt(
    first_indent: float, second_indent: float, summary: bool
) -> None:
    blocks = make_blocks(
        _lines_of(
            _summary_page(
                _hanging(_SUMMARY_TEXTS[0], first_indent),
                _hanging(_SUMMARY_TEXTS[1], second_indent),
                _hanging(_SUMMARY_TEXTS[2], second_indent, 150),
            )
        ),
        _NO_WORDS,
        workers=1,
    )
    assert (
        any(block.kind is BlockKind.CHAPTER_SUMMARY for block in blocks.blocks)
        is summary
    )


def test_chapter_summary_ends_before_the_first_line_not_indented() -> None:
    # The second line ends the summary's indent; the third, at the left
    # edge, is the paragraph's first line.
    blocks = make_blocks(
        _lines_of(
            _summary_page(
                _hanging("Terms of accession — His character — His", 0),
                _hanging("early reforms.", 9, 150),
                _hanging("The paragraph starts here at the edge", 0),
            )
        ),
        _NO_WORDS,
        workers=1,
    )
    assert _kinds_and_texts(blocks)[2:4] == (
        (
            "chapter_summary",
            None,
            None,
            "Terms of accession — His character — His early reforms.",
        ),
        (
            "paragraph",
            None,
            None,
            "The paragraph starts here at the edge "
            + " ".join(f"after {n} of the page" for n in range(5)),
        ),
    )


def test_chapter_summary_only_right_after_a_heading() -> None:
    # The same lines after a paragraph's last line are paragraphs.
    page = _body_page(
        0,
        *(_full(f"before {n} of the page", 70 + _PITCH_PT * n) for n in range(3)),
        _short("its end.", 115),
        replace_top(_hanging(_SUMMARY_TEXTS[0], 0), 130),
        replace_top(_hanging(_SUMMARY_TEXTS[1], 9), 145),
        replace_top(_hanging(_SUMMARY_TEXTS[2], 9, 150), 160),
        *(_full(f"after {n} of the page", 175 + _PITCH_PT * n) for n in range(5)),
    )
    blocks = make_blocks(_lines_of(page), _NO_WORDS, workers=1)
    assert not any(block.kind is BlockKind.CHAPTER_SUMMARY for block in blocks.blocks)


# Verse (structure spec, section 16, rule 4)


def _verse_line(text: str, top: float, inset: float = 40.0, left: float = 0.0) -> Line:
    """A line inset `inset` pt from both edges of the column, 50 to 300 pt,
    moved `left` pt to the right."""
    return _spread(text, _BODY_LEFT_PT + inset + left, _RIGHT_PT - inset, top)


_VERSE = (
    "Quelle dame a la pratique",
    "De tant de mathematique",
    "Quelle princesse entend mieux",
)


def _verse_page(*verse: Line) -> PageLayout:
    return _around(*verse, gap_after=22.5)


def test_verse_of_three_lines_inset_on_both_sides_is_one_block_with_line_feeds() -> (
    None
):
    lines = _lines_of(
        _verse_page(
            *(_verse_line(text, 122.5 + 15 * n) for n, text in enumerate(_VERSE))
        )
    )
    blocks = make_blocks(lines, _NO_WORDS, workers=1)
    assert _kinds_and_texts(blocks) == (
        _BEFORE,
        ("verse", None, None, "\n".join(_VERSE)),
        _AFTER,
    )
    check_stage(FidelityBoundary.STRUCTURE, lines, blocks)


@pytest.mark.parametrize(
    ("inset", "words", "verse"),
    [(30.0, 4, True), (29.5, 4, False), (40.0, 3, True), (40.0, 2, False)],
)
def test_verse_lines_have_3_words_and_are_inset_30_pt(
    inset: float, words: int, verse: bool
) -> None:
    texts = tuple(" ".join(text.split()[:words]) for text in _VERSE)
    blocks = make_blocks(
        _lines_of(
            _verse_page(
                *(
                    _verse_line(text, 122.5 + 15 * n, inset)
                    for n, text in enumerate(texts)
                )
            )
        ),
        _NO_WORDS,
        workers=1,
    )
    assert any(block.kind is BlockKind.VERSE for block in blocks.blocks) is verse


def test_verse_needs_two_lines() -> None:
    blocks = make_blocks(
        _lines_of(_verse_page(_verse_line(_VERSE[0], 122.5))), _NO_WORDS, workers=1
    )
    assert not any(block.kind is BlockKind.VERSE for block in blocks.blocks)


@pytest.mark.parametrize(("shift", "verse"), [(12.0, True), (12.5, False)])
def test_verse_needs_more_than_half_its_lines_near_their_median_left(
    shift: float, verse: bool
) -> None:
    # Four lines: two at the median left and two moved right; with the
    # shift over 12 pt only two of four lie within 12 pt of the median.
    lines = (
        _verse_line(_VERSE[0], 122.5, 40, 0),
        _verse_line(_VERSE[1], 137.5, 40, 0),
        _verse_line(_VERSE[2], 152.5, 40, 2 * shift),
        _verse_line(_VERSE[0], 167.5, 40, 2 * shift),
    )
    blocks = make_blocks(_lines_of(_verse_page(*lines)), _NO_WORDS, workers=1)
    assert any(block.kind is BlockKind.VERSE for block in blocks.blocks) is verse


@pytest.mark.parametrize(
    ("lefts", "verse"), [((0, 10, 30, 40), False), ((0, 10, 20, 25), True)]
)
def test_verse_needs_more_than_half_not_half(
    lefts: tuple[float, ...], verse: bool
) -> None:
    # (0, 10, 30, 40): median 20, only 10 and 30 within 12 pt, half. (0, 10, 20, 25): median 15, three within 12 pt.
    lines = tuple(
        _verse_line(_VERSE[n % 3], 122.5 + 15 * n, 40, left)
        for n, left in enumerate(lefts)
    )
    blocks = make_blocks(_lines_of(_verse_page(*lines)), _NO_WORDS, workers=1)
    assert any(block.kind is BlockKind.VERSE for block in blocks.blocks) is verse


def test_verse_line_must_be_inset_on_the_right_too() -> None:
    lines = tuple(
        _spread(text, 90, _RIGHT_PT - 10, 122.5 + 15 * n)
        for n, text in enumerate(_VERSE)
    )
    blocks = make_blocks(_lines_of(_verse_page(*lines)), _NO_WORDS, workers=1)
    assert not any(block.kind is BlockKind.VERSE for block in blocks.blocks)


def test_verse_line_ending_with_a_hyphen_is_joined_to_the_next() -> None:
    texts = (
        "Quelle dame a la pra-",
        "tique de tant de",
        "Quelle princesse entend mieux",
    )
    lines = _lines_of(
        _verse_page(
            *(_verse_line(text, 122.5 + 15 * n) for n, text in enumerate(texts))
        )
    )
    blocks = make_blocks(lines, frozenset({"pratique"}), workers=1)
    assert block_text(blocks.blocks[1]) == (
        "Quelle dame a la pratique de tant de\nQuelle princesse entend mieux"
    )


@pytest.mark.parametrize(("ending", "verse"), [("se sou-", False), ("se sou", True)])
def test_verse_run_does_not_start_after_a_line_ending_with_a_hyphen(
    ending: str, verse: bool
) -> None:
    # Mariéjol page 212: two inset lines after "se sou-" are prose.
    page = _body_page(
        0,
        *(_full(f"before {n} of the page", 70 + _PITCH_PT * n) for n in range(3)),
        _full(f"and the bourgeois {ending}", 115),
        *(_verse_line(text, 130 + 15 * n) for n, text in enumerate(_VERSE[:2])),
        *(_full(f"after {n} of the page", 160 + _PITCH_PT * n) for n in range(5)),
    )
    blocks = make_blocks(_lines_of(page), _NO_WORDS, workers=1)
    assert any(block.kind is BlockKind.VERSE for block in blocks.blocks) is verse


def test_verse_heading_line_is_not_part_of_a_run() -> None:
    # A centred title in capitals of 3 words, inset on both sides, stays a
    # heading above the verse.
    lines = _lines_of(
        _around(
            _centred_line("THE LAST POEM", 130),
            *(_verse_line(text, 152.5 + 15 * n) for n, text in enumerate(_VERSE)),
        )
    )
    blocks = make_blocks(lines, _NO_WORDS, workers=1)
    assert tuple(block.kind.value for block in blocks.blocks) == (
        "paragraph",
        "heading",
        "verse",
        "paragraph",
    )


def _verse_over_a_break(next_top: tuple[Line, ...]) -> LinesFile:
    """Page 0 ends with two lines of verse; page 1 starts with the lines
    `next_top`, then a paragraph."""
    page_0 = _body_page(
        0,
        *(_full(f"zero {n} of the page", 70 + _PITCH_PT * n) for n in range(5)),
        _verse_line(_VERSE[0], 152.5),
        _verse_line(_VERSE[1], 167.5),
    )
    page_1 = _body_page(
        1,
        *next_top,
        *(_full(f"one {n} of the page", 107.5 + _PITCH_PT * n) for n in range(5)),
    )
    return _lines_of(page_0, page_1)


def test_verse_block_ending_a_page_goes_on_into_verse_at_the_next_top() -> None:
    blocks = make_blocks(
        _verse_over_a_break((_verse_line(_VERSE[2], 70), _verse_line(_VERSE[0], 85))),
        _NO_WORDS,
        workers=1,
    )
    verse = tuple(block for block in blocks.blocks if block.kind is BlockKind.VERSE)
    assert len(verse) == 1
    assert block_text(verse[0]) == "\n".join((*_VERSE, _VERSE[0]))
    assert tuple(origin.page_index for origin in verse[0].origin) == (0, 1)


def test_verse_block_ending_a_page_ends_before_prose_on_the_next() -> None:
    blocks = make_blocks(_verse_over_a_break(()), _NO_WORDS, workers=1)
    assert _kinds_and_texts(blocks)[1:] == (
        ("verse", None, None, "\n".join(_VERSE[:2])),
        (
            "paragraph",
            None,
            None,
            " ".join(f"one {n} of the page" for n in range(5)),
        ),
    )


def test_make_blocks_with_headings_summaries_verse_and_quotes_with_1_and_3_workers() -> (
    None
):
    pages = (
        *_verse_over_a_break(
            (_verse_line(_VERSE[2], 70), _verse_line(_VERSE[0], 85))
        ).pages,
        replace(
            _summary_page(
                _hanging(_SUMMARY_TEXTS[0], 0),
                _hanging(_SUMMARY_TEXTS[1], 9),
                _hanging(_SUMMARY_TEXTS[2], 9, 150),
            ),
            index=2,
        ),
        replace(
            _verse_page(
                *(_verse_line(t, 122.5 + 15 * n) for n, t in enumerate(_VERSE))
            ),
            index=3,
        ),
        *(
            replace(_around(_centred_line("CHAPTER IV.", 130)), index=index)
            for index in range(4, 8)
        ),
        replace(_quote_page(8, *_quote_lines(115, 8.5)), index=8),
        *(
            replace(page, index=page.index + 10)
            for page in _bibliography_pages("BIBLIOGRAPHICAL NOTE").pages
        ),
    )
    lines = _lines_of(*pages)
    assert make_blocks(lines, _NO_WORDS, workers=1) == make_blocks(
        lines, _NO_WORDS, workers=3
    )


# Quotes (structure spec, section 16, rules 1 to 3). The body's full lines
# hold 16 characters over 250 pt; a quote's 24 over the same width, 1.5
# times as dense.

_QUOTE_TEXTS = (
    "quoted words of smaller type",
    "and more of them quoted here",
    "the quotation ends here now",
)


def _quote_lines(
    top: float,
    height: float,
    texts: tuple[str, ...] = _QUOTE_TEXTS,
    x0: float = _BODY_LEFT_PT,
    x1: float = _RIGHT_PT,
) -> tuple[Line, ...]:
    """Lines of `texts` 15 pt apart from `top`, the first indented 10 pt,
    the last ending at 210 pt, of words `height` pt high."""
    last = len(texts) - 1
    return tuple(
        _spread(
            text,
            x0 + (10 if n == 0 else 0),
            210 if n == last and x1 == _RIGHT_PT else x1,
            top + _PITCH_PT * n,
            height,
        )
        for n, text in enumerate(texts)
    )


def _quote_page(index: int, *middle: Line) -> PageLayout:
    """A paragraph whose last line is short, the lines `middle` from 115 pt,
    and a paragraph whose first line is indented."""
    after = 115 + _PITCH_PT * len(middle)
    return _body_page(
        index,
        _full("before 0 of the page", 70),
        _full("before 1 of the page", 85),
        _short("its end.", 100),
        *middle,
        _indented("after 0 of the page", after),
        *(_full(f"after {n} of the page", after + _PITCH_PT * n) for n in range(1, 5)),
    )


def _kinds(blocks: BlocksFile) -> tuple[str, ...]:
    return tuple(block.kind.value for block in blocks.blocks)


@pytest.mark.parametrize(
    ("height", "kind"),
    [(8.5, "quote"), (9.5, "quote"), (9.6, "paragraph"), (10.0, "paragraph")],
)
def test_quote_of_smaller_and_denser_type_across_the_column(
    height: float, kind: str
) -> None:
    # A height ratio of at most 0.95 over the body word height, 10 pt.
    lines = _lines_of(_quote_page(0, *_quote_lines(115, height)))
    blocks = make_blocks(lines, _NO_WORDS, workers=1)
    assert _kinds(blocks) == ("paragraph", kind, "paragraph")
    assert block_text(blocks.blocks[1]) == " ".join(_QUOTE_TEXTS)
    check_stage(FidelityBoundary.STRUCTURE, lines, blocks)


@pytest.mark.parametrize(("x1", "kind"), [(290.0, "quote"), (295.0, "paragraph")])
def test_quote_by_rule_1_needs_a_density_of_1_04(x1: float, kind: str) -> None:
    # The body's full lines hold 15 characters over 250 pt (the median). The
    # quote's lines hold 15 over (x1 - 50) pt, the first a little denser, so their
    # median density against the book's is 250 / (x1 - 50): 1.042 at 290 pt,
    # 1.020 at 295.
    lines = tuple(
        _spread(f"aside {n} of the page", 60 if n == 1 else 50, x1, 100 + 15 * n, 8.5)
        for n in range(1, 4)
    )
    blocks = make_blocks(_lines_of(_quote_page(0, *lines)), _NO_WORDS, workers=1)
    assert _kinds(blocks)[1] == kind


def test_quote_by_rule_1_needs_two_wide_lines() -> None:
    # The second and third lines of 4 words are not wide.
    texts = (_QUOTE_TEXTS[0], "and more quoted here", "the quote ends now")
    blocks = make_blocks(
        _lines_of(_quote_page(0, *_quote_lines(115, 8.5, texts))), _NO_WORDS, workers=1
    )
    assert _kinds(blocks)[1] == "paragraph"


@pytest.mark.parametrize(("inset", "kind"), [(16.0, "quote"), (15.5, "paragraph")])
def test_quote_inset_by_16_pt_in_smaller_type_by_rule_2(
    inset: float, kind: str
) -> None:
    # Domesday's numbered items: two lines, one wide, inset on the left.
    lines = (
        _spread(
            "(vi) A Devonshire manor of the", _BODY_LEFT_PT + inset, _RIGHT_PT, 115, 8.5
        ),
        _spread("king's own land.", _BODY_LEFT_PT + inset, 160, 130, 8.5),
    )
    blocks = make_blocks(_lines_of(_quote_page(0, *lines)), _NO_WORDS, workers=1)
    assert _kinds(blocks)[1] == kind


def test_quote_short_block_next_to_a_quote_by_rule_3() -> None:
    # A quote, then a short line of small type indented after its short last
    # line: a quote too; the same short line after a paragraph stays one.
    short = _spread("Thus spoke the poet.", 70, 170, 160, 8.5)
    blocks = make_blocks(
        _lines_of(_quote_page(0, *_quote_lines(115, 8.5), short)), _NO_WORDS, workers=1
    )
    assert _kinds(blocks) == ("paragraph", "quote", "quote", "paragraph")
    alone = make_blocks(
        _lines_of(_quote_page(0, replace_top(short, 115))), _NO_WORDS, workers=1
    )
    assert _kinds(alone) == ("paragraph", "paragraph", "paragraph")


def test_quote_band_of_small_type_is_still_a_note() -> None:
    page = PageLayout(
        0,
        (
            _region(*_quote_page(0).regions[0].lines),
            _region(
                _note_line("1 A note of small type that runs on", 300),
                _note_line("and ends.", 309, 50, 100),
            ),
        ),
        (),
    )
    blocks = make_blocks(_lines_of(page), _NO_WORDS, workers=1)
    assert len(blocks.notes) == 1
    assert "quote" not in _kinds(blocks)


def test_quote_none_on_a_page_of_contents_pages() -> None:
    lines = _lines_of(_quote_page(0, *_quote_lines(115, 8.5)))
    blocks = make_blocks(lines, _NO_WORDS, contents_pages=frozenset({0}), workers=1)
    assert "quote" not in _kinds(blocks)


@pytest.mark.parametrize(
    ("markers", "taken"),
    [(("(1)", "(2)", "(3)"), True), (("(1)", "(3)", "(2)"), False)],
)
def test_quote_never_made_of_notes_left_in_the_body(
    markers: tuple[str, str, str], taken: bool
) -> None:
    # Section 16: in order, the small lines are notes; out of order, each
    # stays a paragraph led by a marker, not a quote, and the last does not
    # run on into page 2.
    blocks = make_blocks(_body_notes_pages(markers), _NO_WORDS, workers=1)
    assert "quote" not in _kinds(blocks)
    assert (len(blocks.notes) == 4) is taken
    if not taken:
        assert block_text(blocks.blocks[-1]).startswith("two 0 of the page")


def test_quote_never_made_of_notes_in_the_body_on_a_page_whose_band_starts_at_1() -> (
    None
):
    blocks = make_blocks(
        _body_notes_pages(("(1)", "(2)", "(3)"), band_on_the_page=True),
        _NO_WORDS,
        workers=1,
    )
    assert "quote" not in _kinds(blocks)


def test_quote_never_made_of_notes_in_the_body_below_text_as_small() -> None:
    blocks = make_blocks(
        _body_notes_pages(("(1)", "(2)", "(3)"), text_height=_SMALL_PT),
        _NO_WORDS,
        workers=1,
    )
    assert tuple(
        block.kind.value for block in blocks.blocks if block.origin[0].page_index == 1
    )[-3:] == ("list_item", "list_item", "list_item")


# Haskins' bibliographical notes (structure spec, section 16)


def _bibliography_pages(title: str) -> LinesFile:
    """Page 0: a paragraph, the level-2 heading `title`, and a block of small
    type that rule 1 would make a quote. Page 1: a paragraph and a band
    block of small type without a marker. Page 2: a paragraph, the heading
    "CHAPTER II." and the same two blocks. Page 3: a band note "1 …" so
    that the book's marker form is digits."""

    def band() -> Region:
        return _region(
            _note_line("Sources are listed in the general works on", 300),
            _note_line("the period.", 309, 50, 100),
        )

    page_0 = _quote_page(0, _centred_line(title, 122.5, 120), *_quote_lines(145, 8.5))
    page_1 = PageLayout(1, (_region(*_five_full_lines(70, "one")), band()), ())
    body_2 = _quote_page(
        2, _centred_line("CHAPTER II.", 122.5, 60), *_quote_lines(145, 8.5)
    ).regions[0]
    # Its first line indented, so that it starts a paragraph.
    body_2 = _region(_indented("before 0 of the page", 70), *body_2.lines[1:])
    page_2 = PageLayout(2, (body_2, band()), ())
    page_3 = PageLayout(
        3,
        (
            _region(*_five_full_lines(70, "three")),
            _region(_note_line("1 A real note.", 300, 50, 120)),
        ),
        (),
    )
    return _lines_of(page_0, page_1, page_2, page_3)


def test_bibliographical_note_blocks_are_paragraphs_up_to_the_next_heading() -> None:
    lines = _bibliography_pages("BIBLIOGRAPHICAL NOTE")
    blocks = make_blocks(lines, _NO_WORDS, workers=1)
    by_page = tuple(
        (block.origin[0].page_index, block.kind.value, block_text(block).split(" ")[0])
        for block in blocks.blocks
    )
    # Page 0's small block and page 1's band block are paragraphs, the band
    # block after page 1's body; after "CHAPTER II." the small block is a
    # quote and the band block a note.
    assert by_page == (
        (0, "paragraph", "before"),
        (0, "heading", "BIBLIOGRAPHICAL"),
        (0, "paragraph", "quoted"),
        (0, "paragraph", "after"),
        (1, "paragraph", "Sources"),
        (2, "paragraph", "before"),
        (2, "heading", "CHAPTER"),
        (2, "quote", "quoted"),
        (2, "paragraph", "after"),
    )
    # Page 2's band block, not indented and without a marker, is a note.
    assert tuple(
        (note.origin[0].page_index, block_text(note.blocks[0]).split(" ")[0])
        for note in blocks.notes
    ) == ((2, "Sources"), (3, "A"))
    check_stage(FidelityBoundary.STRUCTURE, lines, blocks)


def test_bibliographical_note_footnote_under_the_heading_s_page_stays_a_note() -> None:
    # Haskins page 204: on the heading's page, the band's block led by a
    # marker of the book's form (digits, from page 3) and what follows stay
    # notes; the unmarked block before them is a paragraph. On page 1, a
    # marked band block is a paragraph of the section.
    lines = _bibliography_pages("BIBLIOGRAPHICAL NOTE")
    band_0 = _region(
        _note_line("Sources are listed in the general works on", 300),
        _note_line("the period.", 309, 50, 100),
        _note_line("1 Mont-Saint-Michel and Chartres, p. 4.", 320, 62, 250),
        _note_line("2 Ibid.", 329, 62, 100),
    )
    band_1 = _region(_note_line("3 Cited above, p. 9.", 300, 62, 200))
    page_0 = replace(lines.pages[0], regions=(*lines.pages[0].regions, band_0))
    page_1 = replace(lines.pages[1], regions=(lines.pages[1].regions[0], band_1))
    blocks = make_blocks(
        _lines_of(page_0, page_1, *lines.pages[2:]), _NO_WORDS, workers=1
    )
    assert tuple((note.origin[0].page_index, note.marker) for note in blocks.notes)[
        :2
    ] == ((0, "1"), (0, "2"))
    # "Sources…" runs on into page 1's body, as any paragraph does.
    assert tuple(
        " ".join(block_text(block).split(" ")[:2])
        for block in blocks.blocks
        if block_text(block).startswith(("Sources", "3 Cited"))
    ) == ("Sources are", "3 Cited")


def test_bibliographical_note_rule_names_its_title() -> None:
    blocks = make_blocks(_bibliography_pages("FURTHER READING"), _NO_WORDS, workers=1)
    assert tuple(
        (block.origin[0].page_index, block.kind.value)
        for block in blocks.blocks
        if block_text(block).startswith("quoted")
    ) == ((0, "quote"), (2, "quote"))
    assert not any(block_text(block).startswith("Sources") for block in blocks.blocks)


def test_bibliographical_note_heading_of_level_1_heads_none() -> None:
    # "BIBLIOGRAPHICAL NOTE" first on a page without a running head is
    # level 1, so its section is not a bibliographical note.
    page = _body_page(
        0,
        _centred_line("BIBLIOGRAPHICAL NOTE", 40, 120),
        *_quote_page(0, *_quote_lines(115, 8.5)).regions[0].lines,
    )
    blocks = make_blocks(_lines_of(page), _NO_WORDS, workers=1)
    assert _kinds_and_texts(blocks)[0][:2] == ("heading", 1)
    assert "quote" in _kinds(blocks)


def test_bibliographical_note_pages_keep_the_notes_left_in_their_body() -> None:
    # The heading at the foot of page 0 starts a bibliographical note that
    # runs to "CHAPTER II." on page 3: page 1's small lines with rising
    # markers stay paragraphs. Page 0's band note, led by a marker on the
    # heading's page, stays a note.
    pages = _body_notes_pages(("(1)", "(2)", "(3)")).pages
    page_0 = replace(
        pages[0],
        regions=(
            _region(
                *pages[0].regions[0].lines,
                _centred_line("BIBLIOGRAPHICAL NOTE", 160, 120),
            ),
            pages[0].regions[1],
        ),
    )
    page_3 = PageLayout(
        3,
        (
            _region(
                _centred_line("CHAPTER II.", 40, 60), *_five_full_lines(70, "three")
            ),
            _region(_note_line("(1) A note after the chapter.", 300, 62, 200)),
        ),
        (),
    )
    blocks = make_blocks(_lines_of(page_0, *pages[1:], page_3), _NO_WORDS, workers=1)
    assert tuple(note.origin[0].page_index for note in blocks.notes) == (0, 3)
    assert _page_1_kinds(blocks)[-3:] == _NOTES_AS_LIST_ITEMS


@pytest.mark.parametrize(("first", "kind"), [("(2)", "paragraph"), ("Two", "quote")])
def test_quote_never_a_block_led_by_the_book_s_marker_form(
    first: str, kind: str
) -> None:
    # Section 16: a body block of small dense type whose first word has the
    # book's marker form (bracketed, from page 1's band) is a note section
    # 11 did not take, and stays a paragraph.
    texts = (f"{first} quoted words of small type", *_QUOTE_TEXTS[1:])
    page_1 = PageLayout(
        1,
        (
            _region(*_five_full_lines(70, "one")),
            _region(_note_line("(1) A note in the band.", 300, 62, 200)),
        ),
        (),
    )
    lines = _lines_of(_quote_page(0, *_quote_lines(115, 8.5, texts)), page_1)
    blocks = make_blocks(lines, _NO_WORDS, workers=1)
    assert _kinds(blocks)[1] == kind


# Guards that no fixture of the excerpts reaches (review of work package 4).


@pytest.mark.parametrize("label", ["VIII", "XIII.", "Ill"])
def test_heading_label_of_a_roman_numeral_of_up_to_5_characters(label: str) -> None:
    # Haskins page 233 prints "VIII" above its title.
    blocks = make_blocks(
        _lines_of(
            _around(
                _centred_line(label, 130, width=25),
                _centred_line("THE NORMAN KINGDOM OF SICILY", 143.5, width=160),
            )
        ),
        _NO_WORDS,
        workers=1,
    )
    assert _kinds_and_texts(blocks)[1] == (
        "heading",
        1,
        label,
        "THE NORMAN KINGDOM OF SICILY",
    )


@pytest.mark.parametrize(
    ("text", "heading"),
    [("ABCDEFGhij", True), ("ABCDEFghij", False), ("THE EARLY YEArs", True)],
)
def test_heading_line_in_capitals_needs_0_7_of_its_letters_upper_case(
    text: str, heading: bool
) -> None:
    # 1.5 pitches below the line before, so the gap branch does not hold:
    # 7 of 10 letters upper case is a heading, 6 of 10 is not; 11 of 13,
    # under the 0.9 a continuation needs, is one.
    blocks = make_blocks(
        _lines_of(_around(_centred_line(text, 122.5))), _NO_WORDS, workers=1
    )
    assert (_kinds_and_texts(blocks)[1][0] == "heading") is heading


def test_margin_note_beside_an_indented_verse_line_keeps_the_verse_whole() -> None:
    # Only a paragraph is split beside a margin note (section 13, rule 3).
    body = _around(
        *(_verse_line(text, 122.5 + 15 * n) for n, text in enumerate(_VERSE))
    ).regions[0]
    margin = _region(_spread("Aside", 310, 340, 137.5))
    blocks = make_blocks(
        _lines_of(PageLayout(0, (body, margin), ())), _NO_WORDS, workers=1
    )
    assert _kinds(blocks) == ("paragraph", "margin_note", "verse", "paragraph")
    assert block_text(blocks.blocks[2]) == "\n".join(_VERSE)


def test_chapter_summary_ends_before_the_next_heading() -> None:
    # A heading straight after the summary's indented lines is a heading of
    # its own, not more of the summary, though centred lines are indented.
    blocks = make_blocks(
        _lines_of(
            _summary_page(
                _hanging(_SUMMARY_TEXTS[0], 0),
                _hanging(_SUMMARY_TEXTS[1], 9),
                _centred_line("THE FIRST PART", 0),
            )
        ),
        _NO_WORDS,
        workers=1,
    )
    assert _kinds(blocks)[1:4] == ("heading", "chapter_summary", "heading")


def test_note_marker_taken_as_a_whole_word_shifts_the_positions_of_its_changes() -> (
    None
):
    # The block "1 Ali- son wrote" with its join at word 1: once the marker
    # "1" is dropped, the join is at word 0, as its word is.
    join = WordChange(
        page_index=0,
        before=("Ali-", "son"),
        after=("Alison",),
        reason=ChangeReason.HYPHEN_JOIN,
    )
    block = Unnumbered(
        kind=BlockKind.PARAGRAPH,
        words=("1", "Alison", "wrote"),
        word_pages=(0, 0, 0),
        origin=(Origin(0, Box(50, 300, 300, 307)),),
        changes=((1, join),),
        line_starts=frozenset({2}),
    )
    without, marker = without_marker(block, NoteMarker("1", "", 1))
    assert marker == "1"
    assert without.words == ("Alison", "wrote")
    assert without.changes == ((0, join),)
    assert without.line_starts == frozenset({1})


# The fidelity check at the structure boundary


def test_fidelity_check_passes_on_the_blocks_of_hand_made_lines() -> None:
    check_stage(
        FidelityBoundary.STRUCTURE, _LINES, make_blocks(_LINES, _NO_WORDS, workers=1)
    )


def test_fidelity_check_fails_when_a_word_is_dropped_from_a_line() -> None:
    dropped = replace(_FIRST_LINE, words=_FIRST_LINE.words[1:])
    lines_without_alpha = replace(
        _LINES,
        pages=(
            PageLayout(0, (replace(_REGION, lines=(dropped, _SECOND_LINE)),), ()),
            *_LINES.pages[1:],
        ),
    )
    with pytest.raises(FidelityError) as raised:
        check_stage(
            FidelityBoundary.STRUCTURE,
            lines_without_alpha,
            make_blocks(_LINES, _NO_WORDS, workers=1),
        )
    assert raised.value.missing == frozendict()
    assert raised.value.invented == frozendict({"Alpha": 1})


# run, on a book folder of its own


_PDF_BYTES = b"%PDF-1.4 a stand-in: structure reads only its hash"
_PDF_HASH = hashlib.sha256(_PDF_BYTES).hexdigest()


@pytest.fixture
def cached_word_list(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A word list of English cached in a folder of the test's own, so that
    run neither runs Tesseract nor writes to ~/.cache."""
    cache_dir = tmp_path / "word-list-cache"
    cache_dir.mkdir()
    (cache_dir / "eng.txt").write_text("alpha\nbeta\n", encoding="utf-8")
    monkeypatch.setattr(wordlist, "DEFAULT_CACHE_DIR", cache_dir)


def _book(root: Path) -> tuple[BookFolder, BookConfig]:
    """A book folder with pages.json and lines.json of 3 pages written by hand."""
    pdf = root / "book.pdf"
    pdf.write_bytes(_PDF_BYTES)
    folder = BookFolder(root)
    pages = PagesFile(
        source_pdf_sha256=_PDF_HASH,
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
            for index in range(3)
        ),
        ocr_audit=None,
    )
    write_pages(folder.pages_json, pages)
    write_lines(folder.lines_json, replace(_LINES, source_pdf_sha256=_PDF_HASH))
    config = BookConfig(
        pdf=pdf, title="A Book", authors=("An Author",), language=Language.EN
    )
    return folder, config


def _replace_hash(path: Path) -> None:
    stale = path.read_text(encoding="utf-8").replace(_PDF_HASH, "f" * 64)
    path.write_text(stale, encoding="utf-8")


@pytest.mark.thread_unsafe
@pytest.mark.usefixtures("cached_word_list")
def test_run_writes_a_paragraph_that_runs_over_a_blank_page(tmp_path: Path) -> None:
    folder, config = _book(tmp_path)
    structure.run(folder, config, workers=1)
    assert read_blocks(folder.blocks_json) == BlocksFile(
        source_pdf_sha256=_PDF_HASH,
        blocks=(
            Block(
                id="b-p0000-001",
                kind=BlockKind.PARAGRAPH,
                level=None,
                label=None,
                spans=(
                    Span("Alpha beta, gamma delta. gamma delta.", Emphasis.NONE, None),
                ),
                figure=None,
                origin=(
                    Origin(0, Box(40, 100, 130, 132)),
                    Origin(2, Box(40, 120, 130, 132)),
                ),
            ),
        ),
        notes=(),
        removals=(),
        word_changes=(),
        page_numbers=(),
    )


@pytest.mark.thread_unsafe
@pytest.mark.usefixtures("cached_word_list")
def test_run_with_a_config_of_another_pdf_names_analyze(tmp_path: Path) -> None:
    folder, config = _book(tmp_path)
    other_pdf = tmp_path / "other.pdf"
    other_pdf.write_bytes(b"%PDF-1.4 another book")
    with pytest.raises(InputFileError, match=r"pages\.json.*galley2epub analyze"):
        structure.run(folder, replace(config, pdf=other_pdf), workers=1)
    assert not folder.blocks_json.exists()


@pytest.mark.thread_unsafe
@pytest.mark.usefixtures("cached_word_list")
def test_run_with_a_pages_json_of_another_pdf_names_analyze(tmp_path: Path) -> None:
    folder, config = _book(tmp_path)
    write_blocks(folder.blocks_json, make_blocks(_LINES, _NO_WORDS, workers=1))
    _replace_hash(folder.pages_json)
    with pytest.raises(InputFileError, match=r"pages\.json.*galley2epub analyze"):
        structure.run(folder, config, workers=1)
    assert not folder.blocks_json.exists()


@pytest.mark.thread_unsafe
@pytest.mark.usefixtures("cached_word_list")
def test_run_with_a_lines_json_of_another_pdf_names_layout(tmp_path: Path) -> None:
    folder, config = _book(tmp_path)
    _replace_hash(folder.lines_json)
    with pytest.raises(InputFileError, match=r"lines\.json.*galley2epub layout"):
        structure.run(folder, config, workers=1)
    assert not folder.blocks_json.exists()


@pytest.mark.thread_unsafe
@pytest.mark.usefixtures("cached_word_list")
def test_run_that_loses_a_word_raises_and_writes_no_blocks_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder, config = _book(tmp_path)

    def make_blocks_losing_a_word(
        lines: LinesFile,
        word_list: frozenset[str],
        *,
        language: Language,
        contents_pages: frozenset[int],
        workers: int,
    ) -> BlocksFile:
        blocks = make_blocks(
            lines,
            word_list,
            language=language,
            contents_pages=contents_pages,
            workers=workers,
        )
        first = blocks.blocks[0]
        shorter = replace(
            first,
            spans=(replace(first.spans[0], text=first.spans[0].text.split(" ", 1)[1]),),
        )
        return replace(blocks, blocks=(shorter, *blocks.blocks[1:]))

    monkeypatch.setattr(structure, "make_blocks", make_blocks_losing_a_word)
    with pytest.raises(FidelityError):
        structure.run(folder, config, workers=1)
    assert not folder.blocks_json.exists()


# The two reference pages that an excerpt cannot get right (tests/
# test_excerpts.py records what the excerpt gives): the running-head and
# signature rules compare a page with others the excerpt lacks. On the
# whole books, Gierke's page index 270 loses its head line "Notes. 185" as
# a running head and a page number, and Mariéjol's page index 210 its foot
# line as a signature mark and the page number "(l93)". The configs are
# those of tests/conftest.py, WHOLE_BOOK_CONFIGS.


type WholeBookStructure = Callable[[str], tuple[LinesFile, BlocksFile]]


@pytest.fixture(scope="module")
def whole_book_structure(
    whole_book_run: Callable[[str], BookFolder],
) -> WholeBookStructure:
    """A function that gives lines.json and blocks.json of a whole book, by
    Internet Archive identifier, from the session's run of the book
    (tests/conftest.py), read the first time a test of this module asks
    for the book and kept for the others. Books may be asked for from
    several threads at once."""

    @functools.cache
    def structure_of(book: str) -> tuple[LinesFile, BlocksFile]:
        folder = whole_book_run(book)
        return read_lines(folder.lines_json), read_blocks(folder.blocks_json)

    return structure_of


def _removed_on(blocks: BlocksFile, page: int) -> tuple[tuple[RemovalReason, str], ...]:
    return tuple(
        (removal.reason, removal.text)
        for removal in blocks.removals
        if removal.page_index == page
    )


def _numbers_on(blocks: BlocksFile, page: int) -> tuple[PageNumber, ...]:
    return tuple(number for number in blocks.page_numbers if number.page_index == page)


@pytest.fixture(scope="module")
def gierke_blocks(whole_book_structure: WholeBookStructure) -> BlocksFile:
    """blocks.json of the whole Gierke book, made once for its tests."""
    return whole_book_structure("politicaltheorie00gieruoft")[1]


@pytest.mark.whole_book
@pytest.mark.thread_unsafe
@pytest.mark.timeout(600)
def test_whole_book_gierke_270_loses_its_notes_head_and_page_number(
    gierke_blocks: BlocksFile,
) -> None:
    blocks = gierke_blocks
    assert _removed_on(blocks, 270) == (
        (RemovalReason.RUNNING_HEAD, "Notes."),
        (RemovalReason.PAGE_NUMBER, "185"),
    )
    assert _numbers_on(blocks, 270) == (
        PageNumber(270, "185", PageNumberPosition.HEAD),
    )


@pytest.mark.whole_book
@pytest.mark.thread_unsafe
@pytest.mark.timeout(600)
def test_whole_book_gierke_endnote_section_runs_from_186_to_282(
    gierke_blocks: BlocksFile,
) -> None:
    # Structure spec, section 12: 299 endnotes on pages 186 to 282, the
    # library card of page 288 (excluded) not among them, and "NOTES."
    # a heading of the body (section 14). Numbered through the book, they
    # are one note group, without a group heading.
    endnotes = tuple(
        note for note in gierke_blocks.notes if note.kind is NoteKind.ENDNOTE
    )
    assert len(endnotes) == 299
    assert not any(note.group is not None for note in endnotes)
    pages = {origin.page_index for note in endnotes for origin in note.origin}
    assert (min(pages), max(pages)) == (186, 282)
    assert endnotes[0].marker == "1."
    assert any(
        block_text(block) == "NOTES."
        and block.kind is BlockKind.HEADING
        and block.origin[0].page_index == 186
        for block in gierke_blocks.blocks
    )


@pytest.mark.whole_book
@pytest.mark.thread_unsafe
@pytest.mark.timeout(600)
def test_whole_book_haskins_quotes_and_bibliographical_notes(
    whole_book_structure: WholeBookStructure,
) -> None:
    # Structure spec, section 16: the quotes in smaller type across the
    # column on page 53, the quote over two page breaks from 71 to 73, and
    # the band of small type under "BIBLIOGRAPHICAL NOTE" on page 129 as
    # paragraphs. The excerpt haskins_quotes_index measures its body type
    # smaller than the book's and cannot show the quotes.
    blocks = whole_book_structure("normansineuropea00hask")[1]

    def kinds_from(page: int) -> tuple[tuple[str, list[int]], ...]:
        return tuple(
            (block.kind.value, [origin.page_index for origin in block.origin])
            for block in blocks.blocks
            if block.origin[0].page_index == page
            and block.kind is not BlockKind.MARGIN_NOTE
        )

    assert kinds_from(53) == (
        ("quote", [53]),
        ("quote", [53]),
        ("quote", [53]),
        ("paragraph", [53]),
        ("quote", [53, 54]),
    )
    assert kinds_from(71) == (("quote", [71, 72, 73]),)
    assert kinds_from(129) == (
        ("heading", [129]),
        ("paragraph", [129]),
        ("paragraph", [129, 130]),
    )
    assert not any(note.origin[0].page_index == 129 for note in blocks.notes)


# The head of a short section on the six whole books (structure spec,
# section 3, its last paragraph): the rule takes three head lines,
# Haskins' page index 13 "vlil PREFACE", Domesday's "vi Preface." and
# Gierke's 58 "Analytical Snnittniry. liii". The
# pages it takes are those whose head line is a running head with the rule
# and not without it.

_WHOLE_BOOKS = (
    "battleofkadeshst00breauoft",
    "domesdaybook00maituoft",
    "earlyplantagenet01stub",
    "normansineuropea00hask",
    "politicaltheorie00gieruoft",
)


def _no_short_section_head(
    _page_index: int, _line: Line, _top_letters: frozendict[int, str]
) -> bool:
    return False


@pytest.mark.whole_book
@pytest.mark.thread_unsafe
@pytest.mark.timeout(900)
def test_whole_book_short_section_rule_removes_only_the_haskins_and_domesday_heads(
    whole_book_structure: WholeBookStructure, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The books' runs go side by side, as the excerpts' do (tests/conftest.py).
    with ThreadPoolExecutor(max_workers=len(_WHOLE_BOOKS)) as pool:
        outputs = dict(
            zip(_WHOLE_BOOKS, pool.map(whole_book_structure, _WHOLE_BOOKS), strict=True)
        )
    with_rule = {
        book: survey_book(lines).running_heads for book, (lines, _) in outputs.items()
    }
    monkeypatch.setattr(_survey, "_is_short_section_head", _no_short_section_head)
    without_rule = {
        book: survey_book(lines).running_heads for book, (lines, _) in outputs.items()
    }

    assert {
        book: tuple(sorted(with_rule[book] - without_rule[book]))
        for book in _WHOLE_BOOKS
    } == {
        "battleofkadeshst00breauoft": (),
        "domesdaybook00maituoft": (13,),
        "earlyplantagenet01stub": (),
        "normansineuropea00hask": (13,),
        # With the likeness at 0.70, the running head of Gierke's
        # analytical summary (spec section 3).
        "politicaltheorie00gieruoft": (58,),
    }
    assert all(without_rule[book] <= with_rule[book] for book in _WHOLE_BOOKS)
    haskins_blocks = outputs["normansineuropea00hask"][1]
    domesday_blocks = outputs["domesdaybook00maituoft"][1]
    assert _removed_on(haskins_blocks, 13) == (
        (RemovalReason.RUNNING_HEAD, "vlil PREFACE"),
    )
    assert _numbers_on(haskins_blocks, 13) == ()
    assert _removed_on(domesday_blocks, 13) == (
        (RemovalReason.PAGE_NUMBER, "vi"),
        (RemovalReason.RUNNING_HEAD, "Preface."),
    )
    assert _numbers_on(domesday_blocks, 13) == (
        PageNumber(13, "vi", PageNumberPosition.HEAD),
    )


# Index pages and guide words (structure spec, section 17). An index page
# has a head line, a left column at 50 pt and a right one at 200 pt, lines
# 12 pt apart from 80 pt; a first line starts at its column's edge and a
# continuation line 9 pt in.

_INDEX_LEFT_PT = 50.0
_INDEX_RIGHT_PT = 200.0
_INDEX_TOP_PT = 80.0
_INDEX_PITCH_PT = 12.0
_INDEX_INDENT_PT = 9.0


def _index_column(
    x0: float,
    texts: tuple[str, ...],
    top: float = _INDEX_TOP_PT,
    skew_pt: float = 0.0,
) -> Region:
    """A column region 130 pt wide, as a justified column is, of one line per
    text; a text starting with ">" is a continuation line, indented 9 pt.
    The column's left edge drifts right by `skew_pt` from its first line to
    its last."""
    last = max(len(texts) - 1, 1)
    lines = tuple(
        _line(
            text.removeprefix(">"),
            x0
            + skew_pt * number / last
            + (_INDEX_INDENT_PT if text.startswith(">") else 0.0),
            top + _INDEX_PITCH_PT * number,
        )
        for number, text in enumerate(texts)
    )
    box = _box(tuple(line.box for line in lines))
    return Region(Box(x0, box.top, max(box.x1, x0 + 130), box.bottom), lines)


def _index_page(
    index: int,
    head: str,
    left: tuple[str, ...],
    right: tuple[str, ...],
    *others: Region,
) -> PageLayout:
    return PageLayout(
        index,
        (
            _region(_line(head, 155, 36)),
            *others,
            _index_column(_INDEX_LEFT_PT, left),
            _index_column(_INDEX_RIGHT_PT, right),
        ),
        (),
    )


_LEFT_ENTRIES = (
    "Abacus, 106.",
    "Abruzzi, 196, 204.",
    "Anjou, counts of, 61,",
    ">85; relations, 61.",
    "Apulia, 186, 197.",
)
_RIGHT_ENTRIES = (
    "Bari, 189, 197.",
    "Bayeux, 10, 46,",
    ">49, 67, 76.",
    "Becket, 4, 100.",
    "Bessin, 10, 28.",
)


def _column_lines(page: PageLayout) -> tuple[str, ...]:
    """The lines of the index page's columns, left then right, as rule 2 of
    section 17 reads them."""
    kinds = region_kinds(page, _WORD_HEIGHT_PT, frozenset())
    return tuple(
        " ".join(word.text for word in line.words)
        for line in index_page(page, kinds, frozenset()).lines
    )


def test_index_page_columns_are_read_left_then_right() -> None:
    page = _index_page(0, "INDEX", _LEFT_ENTRIES, _RIGHT_ENTRIES)
    assert _column_lines(page) == (
        *(text.removeprefix(">") for text in _LEFT_ENTRIES),
        *(text.removeprefix(">") for text in _RIGHT_ENTRIES),
    )


def test_index_page_columns_leave_the_body_and_the_band() -> None:
    page = _index_page(0, "INDEX", _LEFT_ENTRIES, _RIGHT_ENTRIES)
    blocks = make_blocks(_lines_of(page), _NO_WORDS, workers=1)
    assert block_text(blocks.blocks[0]) == "INDEX"
    assert blocks.blocks[0].kind is BlockKind.HEADING
    assert blocks.notes == ()
    assert "Abacus, 106." in block_text(blocks.blocks[1])


def test_guide_words_line_is_removed_as_guide_words() -> None:
    # Spec section 17, rule 2: the line "BUR CON" read as the first line of
    # the left column, where the test of the columns' first lines, one word
    # each, cannot find it.
    page = _index_page(0, "INDEX", ("BUR CON", *_LEFT_ENTRIES), _RIGHT_ENTRIES)
    blocks = make_blocks(_lines_of(page), _NO_WORDS, workers=1)
    assert _removals_of(0, blocks) == (
        Removal(
            page_index=0,
            box=Box(50, 80, 85, 90),
            text="BUR CON",
            reason=RemovalReason.GUIDE_WORDS,
        ),
    )
    assert "BUR" not in " ".join(block_text(block) for block in blocks.blocks)
    check_stage(FidelityBoundary.STRUCTURE, _lines_of(page), blocks)


def test_guide_words_split_into_the_columns_first_lines_are_one_removal() -> None:
    page = _index_page(0, "INDEX", ("BUR", *_LEFT_ENTRIES), ("CON", *_RIGHT_ENTRIES))
    blocks = make_blocks(_lines_of(page), _NO_WORDS, workers=1)
    assert [(removal.reason, removal.text) for removal in _removals_of(0, blocks)] == [
        (RemovalReason.GUIDE_WORDS, "BUR CON")
    ]
    assert _column_lines(page)[0] == "Abacus, 106."
    check_stage(FidelityBoundary.STRUCTURE, _lines_of(page), blocks)


def test_guide_words_not_removed_when_the_first_lines_are_not_level_or_not_three_capitals() -> (
    None
):
    lowered = _index_page(0, "INDEX", ("BUR", *_LEFT_ENTRIES), ("Con", *_RIGHT_ENTRIES))
    assert _removals_of(0, make_blocks(_lines_of(lowered), _NO_WORDS, workers=1)) == ()
    apart = replace(
        lowered,
        regions=(
            lowered.regions[0],
            lowered.regions[1],
            _index_column(_INDEX_RIGHT_PT, ("CON", *_RIGHT_ENTRIES), top=84.0),
        ),
    )
    assert _removals_of(0, make_blocks(_lines_of(apart), _NO_WORDS, workers=1)) == ()


def test_gutter_row_read_across_both_columns_is_cut_and_read_with_each() -> None:
    # Spec section 17, rule 2: layout read the first two rows across the
    # gutter as one region; each word goes to the column of its middle.
    across = _region(
        Line(
            Box(50, 56, 285, 66),
            (*_words_at("Caen, 10.", 50, 56), *_words_at("Clermont, 211.", 200, 56)),
        ),
        Line(
            Box(59, 68, 260, 78),
            (*_words_at("160, 166.", 59, 68), *_words_at("Clovis, 207.", 200, 68)),
        ),
    )
    page = _index_page(0, "INDEX", ("Calabria, 176.",), ("Cluny, 164.",), across)
    assert _column_lines(page) == (
        "Caen, 10.",
        "160, 166.",
        "Calabria, 176.",
        "Clermont, 211.",
        "Clovis, 207.",
        "Cluny, 164.",
    )


def test_gutter_region_with_a_third_of_its_lines_over_it_keeps_its_kind() -> None:
    # Spec section 17, rule 2: a note at the foot, one line of two across
    # the gutter, is not cut.
    note = _region(
        # "reader" runs from 163 to 193 pt, over the gutter at 190.
        _line("This Index may help a reader to pass", 53, 300),
        _line("Authorities.", 50, 312),
    )
    page = _index_page(0, "INDEX", _LEFT_ENTRIES, _RIGHT_ENTRIES, note)
    blocks = make_blocks(_lines_of(page), _NO_WORDS, workers=1)
    assert "This Index may help a reader to pass Authorities." in _texts(blocks.blocks)
    assert "Authorities." not in _column_lines(page)


def test_gutter_margin_region_goes_into_its_column_by_its_top() -> None:
    # Spec section 17, rule 2: a page number that overhangs the right
    # column follows the line it ends, a line of the same top.
    overhang = _region(_line("509", 335, _INDEX_TOP_PT + _INDEX_PITCH_PT))
    page = _index_page(0, "INDEX", _LEFT_ENTRIES, _RIGHT_ENTRIES, overhang)
    assert _column_lines(page)[5:9] == (
        "Bari, 189, 197.",
        "Bayeux, 10, 46,",
        "509",
        "49, 67, 76.",
    )


def test_gutter_margin_region_lines_go_each_beside_the_line_of_their_row() -> None:
    # Spec section 17, rule 2: Domesday 546's page numbers "509" and "519",
    # one margin region, each follow the line they end; Stubbs 321's letter
    # initial "W", left of the column, goes before the line it starts.
    overhang = _region(
        _line("509", 335, _INDEX_TOP_PT),
        _line("519", 335, _INDEX_TOP_PT + 2 * _INDEX_PITCH_PT),
    )
    initial = _region(_line("W", 35, _INDEX_TOP_PT + 4 * _INDEX_PITCH_PT))
    page = _index_page(0, "INDEX", _LEFT_ENTRIES, _RIGHT_ENTRIES, overhang, initial)
    assert _column_lines(page) == (
        "Abacus, 106.",
        "Abruzzi, 196, 204.",
        "Anjou, counts of, 61,",
        "85; relations, 61.",
        "W",
        "Apulia, 186, 197.",
        "Bari, 189, 197.",
        "509",
        "Bayeux, 10, 46,",
        "49, 67, 76.",
        "519",
        "Becket, 4, 100.",
        "Bessin, 10, 28.",
    )


def test_gutter_margin_region_above_the_columns_beside_the_head_stays_out() -> None:
    # Spec section 17, rule 2: Gierke 84's folio "lxxix", a margin region
    # beside the head line, does not end the column's last entry.
    folio = _region(_line("lxxix", 335, 36))
    page = _index_page(0, "INDEX", _LEFT_ENTRIES, _RIGHT_ENTRIES, folio)
    assert "lxxix" not in _column_lines(page)
    blocks = make_blocks(_lines_of(page), _NO_WORDS, workers=1)
    assert "lxxix" in _texts(blocks.blocks)


def test_index_pages_start_at_a_running_head_index_and_end_without_columns() -> None:
    before = _page_with_head(0, "THE BOOK")
    continued = _index_page(1, "252 INDEX", _LEFT_ENTRIES, _RIGHT_ENTRIES)
    blank = PageLayout(2, (), ())
    also = _index_page(3, "253", _LEFT_ENTRIES, _RIGHT_ENTRIES)
    after = PageLayout(
        4,
        (_region(_line("ADVERTISEMENTS", 140, 36)), _body(80, *_BODY_TEXTS)),
        (),
    )
    lines = _lines_of(before, continued, blank, also, after)
    assert survey_book(lines, workers=1).index_pages == frozenset({1, 2, 3})


def test_index_pages_none_without_a_title_that_starts_with_index() -> None:
    page = _index_page(0, "252 CHAPTER", _LEFT_ENTRIES, _RIGHT_ENTRIES)
    assert survey_book(_lines_of(page), workers=1).index_pages == frozenset()


# Index entries (structure spec, section 17, rules 3 and 4).


def _index_entries_of(blocks: BlocksFile) -> tuple[str, ...]:
    return tuple(
        block_text(block)
        for block in blocks.blocks
        if block.kind is BlockKind.INDEX_ENTRY
    )


def test_index_entries_one_per_line_at_the_edge_left_column_then_right() -> None:
    page = _index_page(0, "INDEX", _LEFT_ENTRIES, _RIGHT_ENTRIES)
    blocks = make_blocks(_lines_of(page), _NO_WORDS, workers=1)
    assert [block.kind for block in blocks.blocks] == [BlockKind.HEADING] + [
        BlockKind.INDEX_ENTRY
    ] * 9
    assert block_text(blocks.blocks[0]) == "INDEX"
    assert _index_entries_of(blocks) == (
        "Abacus, 106.",
        "Abruzzi, 196, 204.",
        "Anjou, counts of, 61, 85;",
        "relations, 61.",
        "Apulia, 186, 197.",
        "Bari, 189, 197.",
        "Bayeux, 10, 46, 49, 67, 76.",
        "Becket, 4, 100.",
        "Bessin, 10, 28.",
    )
    assert [block.level for block in blocks.blocks[1:]] == [1, 1, 1, 2, 1, 1, 1, 1, 1]


def test_index_entry_continues_over_the_column_and_the_page_with_one_origin_each() -> (
    None
):
    first = _index_page(
        0,
        "INDEX",
        _LEFT_ENTRIES,
        (">197, 202.", *_RIGHT_ENTRIES[:-1], "Calabria, 176,"),
    )
    second = _index_page(
        1, "254 INDEX", (">237, 246.", "Caliphs, 196."), ("Canne, 199.",)
    )
    blocks = make_blocks(_lines_of(first, second), _NO_WORDS, workers=1)
    entries = tuple(
        block for block in blocks.blocks if block.kind is BlockKind.INDEX_ENTRY
    )
    assert block_text(entries[4]) == "Apulia, 186, 197. 197, 202."
    assert block_text(entries[-3]) == "Calabria, 176, 237, 246."
    assert [origin.page_index for origin in entries[-3].origin] == [0, 1]
    assert _index_entries_of(blocks)[-2:] == ("Caliphs, 196.", "Canne, 199.")


def test_index_entry_hyphens_are_joined_and_page_numbers_kept() -> None:
    page = _index_page(
        0,
        "INDEX",
        ("Commerce, Norman, 72-", ">81; Vik-", ">ing, 37.", *_LEFT_ENTRIES),
        _RIGHT_ENTRIES,
    )
    blocks = make_blocks(_lines_of(page), frozenset({"viking"}), workers=1)
    assert _index_entries_of(blocks)[:2] == ("Commerce, Norman, 72-81;", "Viking, 37.")


def test_index_entr_skewed_column_edge_does_not_start_entries() -> None:
    # Spec section 17, rule 3: the column's left edge drifts 12 pt over 20
    # lines, more than the 5 pt that a straight edge would allow; a first
    # line follows it and a continuation line is 9 pt in.
    texts = tuple(
        f">cont {number}," if number % 2 else f"Entry {number}," for number in range(20)
    )
    page = PageLayout(
        0,
        (
            _region(_line("INDEX", 155, 36)),
            _index_column(_INDEX_LEFT_PT, texts, skew_pt=12.0),
            _index_column(_INDEX_RIGHT_PT, _RIGHT_ENTRIES),
        ),
        (),
    )
    entries = _index_entries_of(make_blocks(_lines_of(page), _NO_WORDS, workers=1))
    assert entries[:10] == tuple(
        f"Entry {number}, cont {number + 1}," for number in range(0, 20, 2)
    )


def test_index_entr_column_of_more_continuation_lines_than_first_lines() -> None:
    # Spec section 17, rule 3: the commonest left side is the indent; the
    # first lines, more than 5 pt left of it, give the edge.
    left = (
        "John, son of Henry,",
        ">99, cursed, 109,",
        ">his reign, 125,",
        ">loses Normandy, 142,",
        ">his death, 160.",
        "Jews, 112,",
        ">banished, 239.",
    )
    page = _index_page(0, "INDEX", left, _RIGHT_ENTRIES)
    assert _index_entries_of(make_blocks(_lines_of(page), _NO_WORDS, workers=1))[
        :2
    ] == (
        (
            "John, son of Henry, 99, cursed, 109, his reign, 125, loses Normandy,"
            " 142, his death, 160."
        ),
        "Jews, 112, banished, 239.",
    )


def test_entry_side_is_the_commonest_or_the_commonest_of_two_left_of_it() -> None:
    assert entry_side((50.0, 50.0, 59.0)) == 50.0
    assert entry_side((50.0, 59.0, 59.0, 59.0)) == 59.0
    assert entry_side((50.0, 50.0, 59.0, 59.0, 59.0)) == 50.0
    # Left sides 5 pt left of the commonest are not further left than 5 pt.
    assert entry_side((54.0, 54.0, 59.0, 59.0, 59.0)) == 59.0


def test_index_entr_no_paragraph_runs_on_over_the_index() -> None:
    before = _page_with_head(0, "THE BOOK")
    continued = _index_page(1, "252 INDEX", _LEFT_ENTRIES, _RIGHT_ENTRIES)
    after = PageLayout(
        2,
        (_region(_line("ADVERTISEMENTS", 140, 36)), _body(80, *_BODY_TEXTS)),
        (),
    )
    lines = _lines_of(before, continued, after)
    assert survey_book(lines, workers=1).index_pages == frozenset({1})
    blocks = make_blocks(lines, _NO_WORDS, workers=1)
    # The paragraph of page 0 does not run on over the index into page 2.
    assert [
        (block.kind, [origin.page_index for origin in block.origin])
        for block in blocks.blocks
    ] == [
        (BlockKind.PARAGRAPH, [0]),
        *[(BlockKind.INDEX_ENTRY, [1])] * 9,
        (BlockKind.PARAGRAPH, [2]),
    ]


@pytest.mark.parametrize("workers", [1, 3])
def test_index_entries_with_1_and_3_workers_give_the_same_blocks(workers: int) -> None:
    pages = (
        _index_page(0, "INDEX", ("BUR", *_LEFT_ENTRIES), ("CON", *_RIGHT_ENTRIES)),
        *(
            _index_page(index, f"{index + 250} INDEX", _LEFT_ENTRIES, _RIGHT_ENTRIES)
            for index in range(1, 5)
        ),
    )
    assert make_blocks(_lines_of(*pages), _NO_WORDS, workers=workers) == make_blocks(
        _lines_of(*pages), _NO_WORDS, workers=1
    )


@pytest.mark.whole_book
@pytest.mark.thread_unsafe
@pytest.mark.timeout(600)
def test_whole_book_gierke_index_entr_one_per_line_on_its_skewed_pages(
    gierke_blocks: BlocksFile,
) -> None:
    # Structure spec section 17: Gierke's index of authorities, pages 83 to
    # 85, has one line per entry ("Accursius No. 105"); page 84 drifts from
    # 42 to 47 pt. Every entry holds one "No" but "Tr. U. J. [tractatus
    # universi iuris]", printed without one, whose "No. 53" on the line
    # below the OCR laid over "Torquemada No. 97" on page 85: in the PDF's
    # order (extract spec section 3) its words are whole but in that entry,
    # "Torquemada No. 53 No. 97", where the default options mixed them
    # ("TorNqou.e m 5 a 3 d a No. 97"). Its last word, "iuris]", printed in
    # the right margin, is a note band that layout re-reads (reocr spec,
    # section 3, kind 2): Tesseract's "rsi iuris]" is kept and becomes a
    # paragraph of its own, so the entry ends at "universi".
    entries = tuple(
        block_text(block)
        for block in gierke_blocks.blocks
        if block.kind is BlockKind.INDEX_ENTRY
    )
    assert {
        origin.page_index
        for block in gierke_blocks.blocks
        if block.kind is BlockKind.INDEX_ENTRY
        for origin in block.origin
    } == {83, 84, 85}
    assert len(entries) == 213
    assert [entry for entry in entries if entry.count("No") != 1] == [
        "Torquemada No. 53 No. 97",
        "Tr. U. J. [tractatus universi",
    ]


@pytest.mark.whole_book
@pytest.mark.thread_unsafe
@pytest.mark.timeout(600)
def test_whole_book_stubbs_guide_words_on_each_of_its_ten_index_pages(
    whole_book_structure: WholeBookStructure,
) -> None:
    blocks = whole_book_structure("earlyplantagenet01stub")[1]
    assert tuple(
        (removal.page_index, removal.text)
        for removal in blocks.removals
        if removal.reason is RemovalReason.GUIDE_WORDS
    ) == (
        # The ten index pages are small-print pages read whole by Tesseract
        # and kept (reocr spec, section 3, kind 1): page 312's guide words
        # are found too, where the layer's spaced letters left "BAL BEC" a
        # paragraph.
        (312, "BAL BEC"),
        (313, "BUR CON"),
        (314, "EDM EDW"),
        (315, "FRA HAR"),
        (316, "HEN HUG"),
        (317, "JOH LEW"),
        (318, "MAT ORD"),
        (319, "PUI ROB"),
        (320, "SPA TRA"),
        (321, "WAR YPR"),
    )
    # Spec section 17, rule 3: the fitted edge gives 910 entries and
    # sub-entries; a straight edge at the entry side gave 916 (16 November
    # 2026), "Baldwin of Redvers, 18" and others cut in two. With the words
    # in the PDF's order, page 312's 74 entries were 34 notes and 839
    # entries were left; with the pages read by Tesseract (17 November
    # 2026), 936, and 935 once a layer word read off Tesseract's reading of
    # it is replaced too (reocr spec, section 4); 934 once Tesseract's junk
    # is dropped, "~" having started a line of its own before "171 : his
    # death, 177" (page 317); no note on the index pages.
    assert sum(block.kind is BlockKind.INDEX_ENTRY for block in blocks.blocks) == 934
    assert not any(312 <= note.origin[0].page_index <= 321 for note in blocks.notes)


@pytest.mark.whole_book
@pytest.mark.tesseract
@pytest.mark.thread_unsafe
@pytest.mark.timeout(600)
@pytest.mark.usefixtures("tesseract_of_the_literals")
def test_reread_whole_stubbs_index_pages_312_to_321_are_read_whole_and_kept(
    whole_book_run: Callable[[str], BookFolder],
    whole_book_structure: WholeBookStructure,
) -> None:
    # Reocr spec, section 3, kind 1, and section 9, "Whole-book tests": the
    # ten index pages are small-print pages of the whole book, read whole
    # below their running heads and kept. The running head keeps the
    # layer's words. Page 312's entry "Acre, siege of, 116; the English at,
    # 118;" has both ";" (Tesseract read "116 ;", which structure attaches,
    # spec section 23), and structure cuts it in two after the first. Its guide words, and the book's 935 index
    # entries, are tested above (test_whole_book_stubbs_guide_words_on_
    # each_of_its_ten_index_pages).
    words = read_words(whole_book_run("earlyplantagenet01stub").words_json)
    lines, blocks = whole_book_structure("earlyplantagenet01stub")
    index_records = tuple(
        record for record in lines.rereads if 312 <= record.page_index <= 321
    )
    assert tuple(
        (record.page_index, record.kind, record.kept) for record in index_records
    ) == tuple((page, RereadKind.SMALL_PRINT_PAGE, True) for page in range(312, 322))
    for record in index_records:
        head = tuple(
            word
            for word in words.pages[record.page_index].words
            if word.box.bottom <= record.box.top
        )
        laid_out = {
            word
            for region in lines.pages[record.page_index].regions
            for line in region.lines
            for word in line.words
        }
        assert "index." in {word.text.casefold() for word in head}, record.page_index
        assert not set(head) & set(record.layer_words), record.page_index
        assert set(head) <= laid_out, record.page_index
    assert any(
        "Acre, siege of, 116 ; the English"
        in " ".join(word.text for word in line.words)
        for region in lines.pages[312].regions
        for line in region.lines
    )
    entries = tuple(
        block_text(block)
        for block in blocks.blocks
        if block.kind is BlockKind.INDEX_ENTRY and block.origin[0].page_index == 312
    )
    acre = next(
        position
        for position, entry in enumerate(entries)
        if entry.endswith("Acre, siege of, 116;")
    )
    assert entries[acre + 1] == "the English at, 118;"


def test_index_entr_sub_entries_cut_after_each_semicolon_inside_a_line() -> None:
    # Spec section 17, rule 5: "Henry II, ..., 219; empire, 86-90;
    # character, 92." is an entry and two sub-entries, the second cut in
    # the middle of a printed line; each part's origin has its own words.
    left = (
        "Henry II, king, 49, 219;",
        ">empire, 86-90; char-",
        ">acter, 92.",
        *_LEFT_ENTRIES,
    )
    page = _index_page(0, "INDEX", left, _RIGHT_ENTRIES)
    blocks = make_blocks(_lines_of(page), frozenset({"character"}), workers=1)
    parts = tuple(
        (block_text(block), block.level, block.origin[0].box)
        for block in blocks.blocks
        if block.kind is BlockKind.INDEX_ENTRY
    )[:3]
    assert parts == (
        ("Henry II, king, 49, 219;", 1, Box(50, 80, 170, 90)),
        ("empire, 86-90;", 2, Box(59, 92, 129, 102)),
        ("character, 92.", 2, Box(59, 92, 159, 114)),
    )
    check_stage(FidelityBoundary.STRUCTURE, _lines_of(page), blocks)


def test_index_entr_is_not_searched_for_note_references() -> None:
    # Spec section 17, rule 4: Stubbs 312's "^" in an entry linked to a
    # garbled region made a note. The same words in a paragraph are a
    # candidate.
    def block(kind: BlockKind) -> Unnumbered:
        return Unnumbered(
            kind=kind,
            words=("Acre,^", "siege", "of,", "116"),
            word_pages=(0, 0, 0, 0),
            origin=(Origin(0, Box(50, 300, 300, 307)),),
            changes=(),
            level=1 if kind is BlockKind.INDEX_ENTRY else None,
        )

    assert len(body_candidates((block(BlockKind.PARAGRAPH),))) == 1
    assert body_candidates((block(BlockKind.INDEX_ENTRY),)) == ()


def test_index_page_head_region_of_index_and_a_page_number_is_removed() -> None:
    # Spec section 17, rule 2: Domesday 547's head region "Index." over
    # "522", two lines, is its running head and page number.
    head = _region(_line("Index.", 200, 20), _line("522", 79, 28))
    page = PageLayout(
        0,
        (
            head,
            _index_column(_INDEX_LEFT_PT, _LEFT_ENTRIES),
            _index_column(_INDEX_RIGHT_PT, _RIGHT_ENTRIES),
        ),
        (),
    )
    lines = _lines_of(
        _index_page(0, "INDEX", _LEFT_ENTRIES, _RIGHT_ENTRIES), replace(page, index=1)
    )
    blocks = make_blocks(lines, _NO_WORDS, workers=1)
    assert [(removal.reason, removal.text) for removal in _removals_of(1, blocks)] == [
        (RemovalReason.RUNNING_HEAD, "Index."),
        (RemovalReason.PAGE_NUMBER, "522"),
    ]
    assert blocks.page_numbers == (PageNumber(1, "522", PageNumberPosition.HEAD),)
    assert not any(
        block.origin[0].page_index == 1 and block.kind is not BlockKind.INDEX_ENTRY
        for block in blocks.blocks
    )
    check_stage(FidelityBoundary.STRUCTURE, lines, blocks)


# The rules of sections 17 and 18 that no test held (review T2, T5).


def test_index_title_table_alphabetique_and_a_page_number_before_index() -> None:
    french = _index_page(0, "TABLE ALPHABÉTIQUE", _LEFT_ENTRIES, _RIGHT_ENTRIES)
    assert survey_book(_lines_of(french), workers=1).index_pages == frozenset({0})
    numbered = _index_page(0, "253 INDEX", _LEFT_ENTRIES, _RIGHT_ENTRIES)
    assert survey_book(_lines_of(numbered), workers=1).index_pages == frozenset({0})
    table = _index_page(0, "TABLE DES MATIÈRES", _LEFT_ENTRIES, _RIGHT_ENTRIES)
    assert survey_book(_lines_of(table), workers=1).index_pages == frozenset()


def _two_columns(left_x1: float, right_x0: float, right_x1: float) -> PageLayout:
    """A page after an index page, its title no index's, with a left column
    from 50 pt to `left_x1`, a right one from `right_x0` to `right_x1`, and
    a speck at 440 to 450 pt, so that the regions span 400 pt."""
    left = _index_column(_INDEX_LEFT_PT, ("Abacus, 106.",))
    right = _index_column(right_x0, ("Bari, 189.",))
    return PageLayout(
        1,
        (
            _region(_line("CONTINUED", 155, 36)),
            replace(left, box=replace(left.box, x1=left_x1)),
            replace(right, box=replace(right.box, x1=right_x1)),
            _region(_line("..", 440, 400)),
        ),
        (),
    )


@pytest.mark.parametrize(
    ("left_x1", "right_x0", "right_x1", "columns"),
    [
        (150.0, 200.0, 400.0, False),  # left 0.25 of the span
        (330.0, 330.0, 450.0, False),  # left 0.7
        (290.0, 290.0, 430.0, True),  # left 0.6, right 0.35
    ],
)
def test_index_columns_are_0_3_to_0_65_of_the_width_the_regions_span(
    left_x1: float, right_x0: float, right_x1: float, columns: bool
) -> None:
    start = _index_page(0, "INDEX", _LEFT_ENTRIES, _RIGHT_ENTRIES)
    page = _two_columns(left_x1, right_x0, right_x1)
    assert (1 in survey_book(_lines_of(start, page), workers=1).index_pages) is columns


def test_index_columns_none_when_a_region_lies_both_left_and_right_of_others() -> None:
    # Three columns side by side: the middle one is both.
    page = PageLayout(
        0,
        (
            _region(_line("INDEX", 155, 36)),
            _index_column(20.0, ("Abacus, 106.",), skew_pt=0.0),
            _index_column(160.0, ("Bari, 189.",)),
            _index_column(300.0, ("Caen, 10.",)),
        ),
        (),
    )
    narrow = PageLayout(
        0,
        tuple(
            replace(region, box=replace(region.box, x1=region.box.x0 + 125))
            if number
            else region
            for number, region in enumerate(page.regions)
        ),
        (),
    )
    assert _column_lines(narrow) == ()


@pytest.mark.parametrize("texts", [("BURR", "CON"), ("BU", "CO"), ("Bur", "Con")])
def test_guide_words_are_two_words_of_three_capitals_only(
    texts: tuple[str, str],
) -> None:
    page = _index_page(
        0, "INDEX", (texts[0], *_LEFT_ENTRIES), (texts[1], *_RIGHT_ENTRIES)
    )
    assert _removals_of(0, make_blocks(_lines_of(page), _NO_WORDS, workers=1)) == ()


def test_guide_words_in_the_head_line_are_not_removed() -> None:
    # The second page of an index, whose head line reads like guide words.
    start = _index_page(0, "INDEX", _LEFT_ENTRIES, _RIGHT_ENTRIES)
    page = _index_page(1, "BUR CON", _LEFT_ENTRIES, _RIGHT_ENTRIES)
    lines = _lines_of(start, page)
    assert survey_book(lines, workers=1).index_pages == frozenset({0, 1})
    assert not any(
        removal.reason is RemovalReason.GUIDE_WORDS
        for removal in make_blocks(lines, _NO_WORDS, workers=1).removals
    )


@pytest.mark.parametrize(("crossing", "cut"), [(1, True), (2, False)])
def test_gutter_region_is_cut_when_two_thirds_of_its_lines_do_not_cross_it(
    crossing: int, cut: bool
) -> None:
    # Spec section 17, rule 2: 3 lines, of which 1 (two thirds uncrossed)
    # or 2 have a word over the gutter at 190 pt; a word goes by its middle,
    # so "overs" (180 to 205 pt) goes right.
    def row(top: float, *, over: bool) -> Line:
        right = _words_at("overs" if over else "Clovis,", 180 if over else 200, top)
        words = (*_words_at("Caen, 10.", 50, top), *right)
        return Line(_box(tuple(word.box for word in words)), words)

    across = _region(
        *(row(20 + 12 * number, over=number < crossing) for number in range(3))
    )
    page = _index_page(0, "INDEX", _LEFT_ENTRIES, _RIGHT_ENTRIES, across)
    lines = _column_lines(page)
    assert ("overs" in lines) is cut
    if cut:
        assert lines[:3] == ("Caen, 10.", "Caen, 10.", "Caen, 10.")


@pytest.mark.parametrize(("indent", "starts"), [(4.0, True), (6.0, False)])
def test_index_entr_starts_within_5_pt_of_the_edge(indent: float, starts: bool) -> None:
    left = (*_LEFT_ENTRIES[:2], "Anjou, counts of, 61,")
    page = _index_page(0, "INDEX", left, _RIGHT_ENTRIES)
    column = page.regions[1]
    moved = _line("relations, 61.", _INDEX_LEFT_PT + indent, 116)
    page = replace(
        page,
        regions=(
            page.regions[0],
            Region(column.box, (*column.lines, moved)),
            page.regions[2],
        ),
    )
    entries = _index_entries_of(make_blocks(_lines_of(page), _NO_WORDS, workers=1))
    assert ("relations, 61." in entries) is starts


def _index_parts(index: int, *, index_lines: int = 0, band: int = 0) -> PageParts:
    line = PlacedLine(
        index, _line("Abacus, 106.", 50, 80), Edges(50, 180), Edges(50, 180)
    )
    return PageParts(
        index=index,
        removals=(),
        page_numbers=(),
        body=(),
        margin_notes=(),
        band_regions=((line,),) if band else (),
        band_blocks=(),
        index_lines=(line,) * index_lines,
    )


def test_index_entr_run_goes_on_over_a_blank_page_and_ends_at_a_band_page() -> None:
    # Spec section 17, rule 1: a page without words does not end an index;
    # one with only a band does, so the next index page starts another.
    pages = (
        _index_parts(0, index_lines=1),
        _index_parts(1),
        _index_parts(2, index_lines=1),
        _index_parts(3, band=1),
        _index_parts(4, index_lines=1),
    )
    assert _index_runs(pages) == (_IndexRun(0, 2), _IndexRun(4, 4))


def test_index_entr_page_gives_no_notes_taken_from_its_body() -> None:
    # Spec section 2, step 2.5: notes left in the body are not taken on an
    # index page; on another page the same lines are.
    above = tuple(
        PlacedLine(
            0, _line(f"Text line {n}", 50, 80 + 15 * n), Edges(50, 300), Edges(50, 300)
        )
        for n in range(3)
    )
    note = PlacedLine(
        0,
        _line("1 See the rolls.", 50, 140, height=8.0),
        Edges(50, 300),
        Edges(50, 300),
    )
    page = replace(_index_parts(0), body=(*above, note))
    taken = _taken_body_notes(
        (page,),
        ((),),
        Numbering.PER_PAGE,
        MarkerForm.DIGITS,
        10.0,
        range(0),
        frozenset(),
    )
    assert taken[0].body == above
    index = replace(page, index_lines=(note,))
    kept = _taken_body_notes(
        (index,),
        ((),),
        Numbering.PER_PAGE,
        MarkerForm.DIGITS,
        10.0,
        range(0),
        frozenset(),
    )
    assert kept[0].body == (*above, note)


def test_plate_running_head_of_section_3_is_removed_and_rule_1_takes_no_more() -> None:
    # Spec section 18, rule 1: Kadesh 19 and 24; the line under the head,
    # alike to the book's running heads, stays a caption line.
    plate = PageLayout(
        16,
        (
            _region(_line("31 THE BOOK", 50, 36)),
            _region(_line("THE BOOK", 50, 120), _line("THE CAMP", 50, 500)),
        ),
        (
            Figure(
                box=_PLATE_BOX,
                image="images/plate-0016.png",
                dpi=300,
                kind=FigureKind.PLATE,
            ),
        ),
    )
    blocks = make_blocks(
        _lines_of(*_numbered_heads(), plate),
        frozenset({"the", "book", "camp"}),
        workers=1,
    )
    assert _removed(blocks, 16) == (("page_number", "31"), ("running_head", "THE BOOK"))
    assert blocks.page_numbers[-1] == PageNumber(16, "31", PageNumberPosition.HEAD)
    assert block_text(blocks.blocks[-1]) == "THE BOOK THE CAMP"


def test_plate_survey_takes_a_running_head_below_a_speck() -> None:
    speck_page = PageLayout(
        16,
        (_region(_line("d", 120, 20)), _body(36, "THE BOOKS 31", *_BODY_TEXTS)),
        (),
    )
    lines = _lines_of(*_numbered_heads(), speck_page)
    survey = survey_book(lines, workers=1)
    assert survey.heads_below_specks == frozenset({16})
    assert "thebooks" in plate_survey(lines, survey).running_head_letters


def test_figure_block_goes_after_the_margin_notes_of_earlier_pages() -> None:
    # Spec section 18, rule 3: after the paragraph in which the body before
    # the plate ends and the margin notes that stay after it.
    def block(kind: BlockKind, page: int) -> Unnumbered:
        return Unnumbered(
            kind=kind,
            words=("word",),
            word_pages=(page,),
            origin=(Origin(page, Box(50, 100, 300, 110)),),
            changes=(),
        )

    body = (
        block(BlockKind.PARAGRAPH, 0),
        block(BlockKind.MARGIN_NOTE, 0),
        block(BlockKind.PARAGRAPH, 2),
    )
    plate = replace(
        _index_parts(1),
        figure=PageFigure("images/plate-0001.png", _PLATE_BOX, Piece(())),
    )
    placed = with_figures(body, (plate,), _NO_WORDS, _NO_WORDS)
    assert [unnumbered.kind for unnumbered in placed] == [
        BlockKind.PARAGRAPH,
        BlockKind.MARGIN_NOTE,
        BlockKind.FIGURE,
        BlockKind.PARAGRAPH,
    ]


def test_plate_page_with_two_figures_is_refused_naming_the_page() -> None:
    # Plates spec section 3: a plate page has one figure.
    plate = replace(
        _plate(1, _spread("THE CAMP", 60, 300, 520)),
        figures=(
            Figure(
                box=_PLATE_BOX,
                image="images/plate-0001.png",
                dpi=300,
                kind=FigureKind.PLATE,
            ),
            Figure(
                box=_PLATE_BOX,
                image="images/plate-0001b.png",
                dpi=300,
                kind=FigureKind.PLATE,
            ),
        ),
    )
    with pytest.raises(InputFileError, match="page 1 has 2 figures"):
        make_blocks(
            _lines_of(_body_page(0, *_five_full_lines(70, "first")), plate),
            _NO_WORDS,
            workers=1,
        )
