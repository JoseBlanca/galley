"""Tests of galley.structure (docs/specs/structure.md, section 9).

Every value is written by hand: structure's tests need no output of layout.
The excerpt tests of structure on the reference pages are in
tests/test_excerpts.py; the whole_book tests here check the two reference
pages an excerpt cannot get right.
"""

import hashlib
from dataclasses import replace
from pathlib import Path

import pytest

from galley import structure, wordlist
from galley.book_folder import BookFolder
from galley.cli import main
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
    Span,
    TextSource,
    Word,
    WordChange,
    block_text,
    read_blocks,
    write_blocks,
    write_lines,
    write_pages,
)
from galley.structure import (
    HyphenJoin,
    NoteMarker,
    Reference,
    ReferenceForm,
    join_hyphen,
    make_blocks,
    note_marker,
    reference_candidate,
    survey_book,
)
from galley.structure._lines import PlacedLine
from galley.structure._margins import BesideLine, line_beside
from galley.structure._measures import Edges
from galley.structure._references import align


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
    return LinesFile(source_pdf_sha256=_HASH, pages=pages)


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
        (("ABCDEFGHIJ", "ABCDEFGXYZ"), False),
        (("ABCD", "ABCD"), True),
        (("ABC", "ABC"), False),
        (
            (
                "ABCDEFGHIJKLMNOPQRSTUVWXYZABCDE",
                "ABCDEFGHIJKLMNOPQRSTUVWXYZABCDEFGHIJKLM",
            ),
            True,
        ),
        (
            (
                "ABCDEFGHIJKLMNOPQRSTUVWXYZABCDE",
                "ABCDEFGHIJKLMNOPQRSTUVWXYZABCDEFGHIJKLMN",
            ),
            False,
        ),
    ],
    ids=[
        "0.75 alike",
        "0.70 alike",
        "4 letters",
        "3 letters",
        "31 and 39 letters",
        "31 and 40 letters",
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


def test_page_after_a_plate_and_a_blank_page_starts_a_paragraph() -> None:
    plate = PageLayout(
        1,
        (_region(_spread(", ' ..", 60, 90, 300)),),
        (Figure(Box(40, 40, 300, 500), "images/p0001.png", 150),),
    )
    pages = (
        _body_page(0, *_five_full_lines(70, "first")),
        plate,
        PageLayout(2, (), ()),
        _body_page(3, *_five_full_lines(70, "third")),
    )
    blocks = make_blocks(_lines_of(*pages), _NO_WORDS, workers=1)
    assert blocks.blocks[-1].id == "b-p0003-001"


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
            _region(_spread("Lower", 310, 340, 120)),
            band,
        ),
        (),
    )
    blocks = make_blocks(_lines_of(page), _NO_WORDS, workers=1)
    assert _texts(blocks.blocks)[1:] == ("Upper", "Lower")
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


def test_words_of_a_plate_are_a_paragraph_of_their_own() -> None:
    plate = PageLayout(
        1,
        (_region(_spread(", ' ..", 60, 90, 300)),),
        (Figure(Box(40, 40, 300, 500), "images/p0001.png", 150),),
    )
    pages = (
        _body_page(0, *_five_full_lines(70, "first")),
        plate,
        _body_page(2, *_five_full_lines(70, "third")),
    )
    blocks = make_blocks(_lines_of(*pages), _NO_WORDS, workers=1)
    assert tuple(block.id for block in blocks.blocks) == (
        "b-p0000-001",
        "b-p0001-001",
        "b-p0002-001",
    )
    assert block_text(blocks.blocks[1]) == ", ' .."


def test_hyphen_before_a_plate_page_is_joined_across_it() -> None:
    plate = PageLayout(
        1,
        (_region(_spread("cate the plate", 60, 160, 300)),),
        (Figure(Box(40, 40, 300, 500), "images/p0001.png", 150),),
    )
    pages = (
        _body_page(0, *_five_full_lines(70, "first"), _full("we repli-", 145)),
        plate,
    )
    blocks = make_blocks(_lines_of(*pages), frozenset({"replicate"}), workers=1)
    assert len(blocks.blocks) == 1
    assert block_text(blocks.blocks[0]).endswith("we replicate the plate")


def test_page_with_a_figure_after_a_number_and_hyphen_starts_a_paragraph() -> None:
    # "136-39-" is a number before a word, not a hyphen to join: the plate's
    # first line starts a paragraph, and so does the indented "Bryce," after.
    plate = PageLayout(
        1,
        (_region(_spread("Plate one", 60, 160, 300)),),
        (Figure(Box(40, 40, 300, 500), "images/p0001.png", 150),),
    )
    pages = (
        _body_page(0, *_five_full_lines(70, "first"), _short("Britain, 136-39-", 145)),
        plate,
        _body_page(2, _indented("Bryce, James, 12", 70), _full("and so on", 85)),
    )
    blocks = make_blocks(_lines_of(*pages), _NO_WORDS, workers=1)
    assert _texts(blocks.blocks)[1:] == ("Plate one", "Bryce, James, 12 and so on")
    assert block_text(blocks.blocks[0]).endswith("Britain, 136-39-")
    assert blocks.word_changes == ()


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


def test_margin_and_band_follow_the_paragraph_in_which_the_page_ends() -> None:
    lines = _lines_of(*_side_text_pages())
    blocks = make_blocks(lines, _NO_WORDS, workers=1)
    assert tuple((block.id, block.kind) for block in blocks.blocks) == (
        ("b-p0000-001", BlockKind.PARAGRAPH),
        ("b-p0000-002", BlockKind.MARGIN_NOTE),
        ("b-p0001-001", BlockKind.PARAGRAPH),
    )
    assert tuple(origin.page_index for origin in blocks.blocks[0].origin) == (0, 1)
    assert block_text(blocks.blocks[1]) == "Margin note"
    assert block_text(blocks.blocks[2]) == "Another paragraph"
    (note,) = blocks.notes
    assert (note.id, note.marker, note.referenced) == ("n-p0000-001", "1", False)
    # Markdown writes the note after the margin note, the last block whose
    # origin includes page 0, so its block is the third to start there.
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
    # band, and no paragraph of its own. Markdown writes page 1's note after
    # the last block whose first origin is on page 1 or earlier, the margin
    # note of page 1, not after the paragraph that has a line on page 1
    # (structure spec, section 6, "Order").
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
        ("b-p0000-001", BlockKind.PARAGRAPH),
        ("b-p0001-001", BlockKind.MARGIN_NOTE),
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
    assert _page_1_blocks(blocks)[-3:] == (
        "(1) Note (1) in small type.",
        "(2) Note (2) in small type.",
        "(3) Note (3) in small type.",
    )


def test_footnote_lines_in_the_body_below_text_as_small_stay() -> None:
    blocks = make_blocks(
        _body_notes_pages(("(1)", "(2)", "(3)"), text_height=_SMALL_PT),
        _NO_WORDS,
        workers=1,
    )
    assert len(blocks.notes) == 1
    assert _page_1_blocks(blocks) == (
        "(1) Note (1) in small type.",
        "(2) Note (2) in small type.",
        "(3) Note (3) in small type.",
    )


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
        BlockKind.PARAGRAPH,
        BlockKind.MARGIN_NOTE,
    )
    assert tuple(block.kind for block in blocks.notes[0].blocks) == (
        BlockKind.PARAGRAPH,
    )


def _beside(top: float, *, first: bool) -> BesideLine:
    line = _spread("a line", 50, 300, top)
    edges = Edges(50, 300)
    return BesideLine(PlacedLine(0, line, edges, edges), first, None)


def test_beside_a_paragraph_s_first_line_within_half_a_pitch_before_a_nearer_one() -> (
    None
):
    # The margin note's top is 100: the middle line at 101 is nearer, but a
    # first line at 107 is within 0.5 of a 15 pt pitch.
    lines = (_beside(101, first=False), _beside(107, first=True))
    assert line_beside(100, lines, 15.0) == lines[1]
    assert line_beside(100, (lines[0], _beside(108, first=True)), 15.0) == lines[0]


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
        contents_pages: frozenset[int],
        workers: int,
    ) -> BlocksFile:
        blocks = make_blocks(
            lines, word_list, contents_pages=contents_pages, workers=workers
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


def _blocks_of_whole_book(book_toml: str, root: Path) -> BlocksFile:
    folder = BookFolder(root)
    folder.book_toml.write_text(book_toml, encoding="utf-8")
    for stage in ("analyze", "extract", "layout", "structure"):
        main([stage, str(root)])
    return read_blocks(folder.blocks_json)


def _removed_on(blocks: BlocksFile, page: int) -> tuple[tuple[RemovalReason, str], ...]:
    return tuple(
        (removal.reason, removal.text)
        for removal in blocks.removals
        if removal.page_index == page
    )


def _numbers_on(blocks: BlocksFile, page: int) -> tuple[PageNumber, ...]:
    return tuple(number for number in blocks.page_numbers if number.page_index == page)


@pytest.fixture(scope="module")
def gierke_blocks(
    whole_book_toml: frozendict[str, str], tmp_path_factory: pytest.TempPathFactory
) -> BlocksFile:
    """blocks.json of the whole Gierke book, made once for its tests."""
    return _blocks_of_whole_book(
        whole_book_toml["politicaltheorie00gieruoft"],
        tmp_path_factory.mktemp("gierke"),
    )


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
    # a block of the body (a heading once work package 4 finds headings).
    endnotes = tuple(
        note for note in gierke_blocks.notes if note.kind is NoteKind.ENDNOTE
    )
    assert len(endnotes) == 299
    pages = {origin.page_index for note in endnotes for origin in note.origin}
    assert (min(pages), max(pages)) == (186, 282)
    assert endnotes[0].marker == "1."
    assert any(
        block_text(block) == "NOTES." and block.origin[0].page_index == 186
        for block in gierke_blocks.blocks
    )


@pytest.mark.whole_book
@pytest.mark.thread_unsafe
@pytest.mark.timeout(600)
def test_whole_book_mariejol_210_foot_line_gives_page_number_and_signature_mark(
    whole_book_toml: frozendict[str, str], tmp_path: Path
) -> None:
    blocks = _blocks_of_whole_book(
        whole_book_toml["catherinedemedic00mariuoft"], tmp_path
    )
    assert _removed_on(blocks, 210) == (
        (RemovalReason.RUNNING_HEAD, "L'EXTERMINATION DU PARTI PROTESTANT"),
        (RemovalReason.SIGNATURE_MARK, "UAMiàjoL. CmOl da Médidib 13"),
        (RemovalReason.PAGE_NUMBER, "(l93)"),
    )
    assert _numbers_on(blocks, 210) == (
        PageNumber(210, "(l93)", PageNumberPosition.FOOT),
    )
