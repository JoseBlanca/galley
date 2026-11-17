"""Tests of structure's running heads, page numbers and headings for the
plan owner-books (docs/specs/structure.md, sections 2 to 4 and 14; the
unit tests of section 26).

Every page is written by hand, as in tests/test_structure.py: a word is 5
pt wide per character and 10 pt high, with one character's width between
words, and body lines lie 15 pt apart.
"""

import functools
from collections.abc import Callable

import pytest

from galley.book_folder import BookFolder
from galley.model import (
    BlockKind,
    BlocksFile,
    Box,
    Line,
    LinesFile,
    PageLayout,
    PageNumber,
    PageNumberPosition,
    Region,
    RemovalReason,
    Word,
    block_text,
    read_blocks,
)
from galley.structure import make_blocks, survey_book

_HASH = "a" * 64
_NO_WORDS: frozenset[str] = frozenset()
_CHAR_PT = 5.0
_WORD_HEIGHT_PT = 10.0
_PITCH_PT = 15.0
_BODY_LEFT_PT = 50.0
# The body lines below are 26 characters, 130 pt wide: the column runs from
# 50 to 180 pt.
_BODY_TEXTS = (
    "the first line of the body",
    "the second line of the body",
    "the third line of the body",
    "the fourth line of the body",
    "the fifth line of the body",
    "the sixth line of the body",
)


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


def _lines_of(*pages: PageLayout) -> LinesFile:
    return LinesFile(source_pdf_sha256=_HASH, pages=pages, rereads=())


def _removed(blocks: BlocksFile, page_index: int) -> tuple[tuple[str, str], ...]:
    return tuple(
        (removal.reason.value, removal.text)
        for removal in blocks.removals
        if removal.page_index == page_index
    )


def _texts_on(blocks: BlocksFile, page_index: int) -> tuple[str, ...]:
    """The text of each block with a line on `page_index`, margin notes
    included."""
    return tuple(
        block_text(block)
        for block in blocks.blocks
        if any(origin.page_index == page_index for origin in block.origin)
    )


# A short region beside the head (spec section 2, "What each region is",
# and section 3, "A short region beside the head"): Turney prints its page
# number outside the column, level with the head, which layout makes a
# margin region after the body's.


def _page_with_number_beside(
    index: int, number: str, number_top: float = 36.0
) -> PageLayout:
    """A page whose head "THE BOOK" lies at 36 pt, with its page number a
    region of one line ending 14 pt left of it, at `number_top`."""
    width = _CHAR_PT * len(number)
    return PageLayout(
        index,
        (
            _region(_line("THE BOOK", _BODY_LEFT_PT, 36)),
            _body(70, *_BODY_TEXTS),
            _region(_line(number, _BODY_LEFT_PT - 14 - width, number_top)),
        ),
        (),
    )


def _pages_with_numbers_beside(test_page: PageLayout) -> LinesFile:
    """Pages 10 to 15 printed 224 to 229, the number beside the head, with
    page 10 replaced by `test_page`."""
    return _lines_of(
        test_page,
        *(_page_with_number_beside(index, str(index + 214)) for index in range(11, 16)),
    )


def test_number_beside_head_is_taken_into_the_head_line_and_removed() -> None:
    lines = _pages_with_numbers_beside(_page_with_number_beside(10, "224"))
    blocks = make_blocks(lines, _NO_WORDS, workers=1)
    assert _removed(blocks, 10) == (
        ("page_number", "224"),
        ("running_head", "THE BOOK"),
    )
    assert PageNumber(10, "224", PageNumberPosition.HEAD) in blocks.page_numbers
    assert not any(block.kind is BlockKind.MARGIN_NOTE for block in blocks.blocks)


def test_number_beside_head_5_pt_lower_leaves_the_head_in_the_text() -> None:
    lines = _pages_with_numbers_beside(_page_with_number_beside(10, "224", 41.0))
    blocks = make_blocks(lines, _NO_WORDS, workers=1)
    assert _removed(blocks, 10) == ()
    assert any(text.startswith("THE BOOK") for text in _texts_on(blocks, 10))
    assert ("page_number", "225") in _removed(blocks, 11)


def test_region_of_6_characters_beside_head_leaves_the_head_in_the_text() -> None:
    lines = _pages_with_numbers_beside(_page_with_number_beside(10, "224224"))
    blocks = make_blocks(lines, _NO_WORDS, workers=1)
    assert _removed(blocks, 10) == ()
    assert any(text.startswith("THE BOOK") for text in _texts_on(blocks, 10))


# A chapter label is never a running head (spec section 3).


def _page_with_head(index: int, head: str, head_top: float = 36.0) -> PageLayout:
    """A page with a head line at `head_top` and six body lines from 70 pt."""
    return PageLayout(
        index,
        (_region(_line(head, _BODY_LEFT_PT, head_top)), _body(70, *_BODY_TEXTS)),
        (),
    )


def _chapter_opening(index: int, label: str, title: str) -> PageLayout:
    """A chapter's first page: its label centred at 50 pt, 0.9 pitch below
    the heads' 36 pt, its title centred 1.5 pitches below, and the body."""
    return PageLayout(
        index,
        (
            _region(_line(label, 115 - _CHAR_PT * len(label) / 2, 50)),
            _region(_line(title, 115 - _CHAR_PT * len(title) / 2, 72.5)),
            _body(110, *_BODY_TEXTS),
        ),
        (),
    )


def _book_with_chapter_labels() -> LinesFile:
    return _lines_of(
        *(_page_with_head(index, "THE BOOK") for index in range(10, 14)),
        _chapter_opening(14, "CHAPTER ONE", "THE BEGINNING"),
        _chapter_opening(15, "CHAPTER TWO", "THE MIDDLE PART"),
        _chapter_opening(16, "CHAPTER THREE", "THE ENDING"),
    )


def test_chapter_label_alike_to_others_near_the_head_top_is_no_running_head() -> None:
    survey = survey_book(_book_with_chapter_labels(), workers=1)
    assert survey.running_heads == frozenset(range(10, 14))


def test_chapter_label_stays_in_the_text_as_its_headings_label() -> None:
    blocks = make_blocks(_book_with_chapter_labels(), _NO_WORDS, workers=1)
    headings = tuple(
        (block.level, block.label, block_text(block))
        for block in blocks.blocks
        if block.kind is BlockKind.HEADING
    )
    assert headings == (
        (1, "CHAPTER ONE", "THE BEGINNING"),
        (1, "CHAPTER TWO", "THE MIDDLE PART"),
        (1, "CHAPTER THREE", "THE ENDING"),
    )
    assert all(_removed(blocks, page) == () for page in (14, 15, 16))


def test_head_whose_first_word_only_starts_with_a_chapter_label_word_stays_a_head() -> (
    None
):
    # Domesday's running head "Book-land and the Land-book." (28 pages).
    pages = tuple(
        _page_with_head(index, "Book-land and the Land-book.")
        for index in range(10, 13)
    )
    survey = survey_book(_lines_of(*pages), workers=1)
    assert survey.running_heads == frozenset(range(10, 13))


# A page number at the foot by its value (spec section 4): Turney prints the
# number of a chapter's first page at the foot, under the label's indent.


def _page_with_number_at_the_foot(index: int, number: str) -> PageLayout:
    """A chapter's first page with no head: its body, and a lowest line of
    one word, `number`, at the column's left edge."""
    return PageLayout(
        index,
        (
            _body(110, *_BODY_TEXTS),
            _region(_line(number, _BODY_LEFT_PT, 230)),
        ),
        (),
    )


def _book_with_a_number_at_the_foot(number: str) -> LinesFile:
    """Pages 185 to 193 printed 156 to 164, the number at the end of the
    head, but page 189, a chapter's first page, with `number` at the foot."""
    return _lines_of(
        *(
            _page_with_head(index, f"THE BOOK {index - 29}")
            for index in range(185, 194)
            if index != 189
        ),
        _page_with_number_at_the_foot(189, number),
    )


def test_page_number_at_the_foot_by_value_is_removed_off_centre() -> None:
    lines = _book_with_a_number_at_the_foot("160")
    survey = survey_book(lines, workers=1)
    assert survey.head_numbers[188] == 159
    assert survey.head_numbers[190] == 161
    blocks = make_blocks(lines, _NO_WORDS, workers=1)
    assert _removed(blocks, 189) == (("page_number", "160"),)
    assert PageNumber(189, "160", PageNumberPosition.FOOT) in blocks.page_numbers


def test_number_at_the_foot_of_another_value_by_value_stays_in_the_text() -> None:
    blocks = make_blocks(_book_with_a_number_at_the_foot("161"), _NO_WORDS, workers=1)
    assert _removed(blocks, 189) == ()
    assert any(text.endswith("161") for text in _texts_on(blocks, 189))


def test_page_number_by_value_takes_the_local_offset_not_the_commonest() -> None:
    # Pages 180 to 184 print 167 to 171 (offset 13), 185 to 193 156 to 164
    # (offset 29, the commonest); page 182, between pages of offset 13,
    # prints "169" at the foot.
    lines = _book_with_a_number_at_the_foot("160")
    early = tuple(
        _page_with_head(index, f"THE BOOK {index - 13}")
        for index in range(180, 185)
        if index != 182
    )
    lines = _lines_of(*early, _page_with_number_at_the_foot(182, "169"), *lines.pages)
    blocks = make_blocks(lines, _NO_WORDS, workers=1)
    assert _removed(blocks, 182) == (("page_number", "169"),)
    assert _removed(blocks, 189) == (("page_number", "160"),)


# Headings: the flush-left and tall branches (spec section 14, "The rule").
# The body lines below are 27 characters, 135 pt wide: a region of them
# has its edges at 50 and 185 pt.


def _running_text(
    top: float, count: int, height: float = _WORD_HEIGHT_PT
) -> tuple[Line, ...]:
    return tuple(
        _line(
            f"line {number:02} of the running text",
            _BODY_LEFT_PT,
            top + _PITCH_PT * number,
            height,
        )
        for number in range(count)
    )


def _headings(blocks: BlocksFile) -> tuple[tuple[int | None, str | None, str], ...]:
    return tuple(
        (block.level, block.label, block_text(block))
        for block in blocks.blocks
        if block.kind is BlockKind.HEADING
    )


def _page_with_a_line_among_the_text(
    index: int, line: Line, gap_below: float
) -> PageLayout:
    """A page of one region: 6 lines of running text from 100 pt, `line`,
    and 6 more lines from `gap_below` pitches under it."""
    above = _running_text(100, 6)
    below = _running_text(line.box.top + gap_below * _PITCH_PT, 6)
    return PageLayout(index, (_region(*above, line, *below),), ())


def test_flush_left_line_in_capitals_2_4_pitches_below_the_text_is_a_heading() -> None:
    line = _line("A NEW SECTION", _BODY_LEFT_PT, 175 + 2.4 * _PITCH_PT)
    page = _page_with_a_line_among_the_text(20, line, 2.0)
    blocks = make_blocks(_lines_of(page), _NO_WORDS, workers=1)
    assert _headings(blocks) == ((2, None, "A NEW SECTION"),)


@pytest.mark.parametrize(
    ("text", "heading"),
    [("as the author wrote:", False), ("as the author wrote", True)],
)
def test_flush_left_line_in_lower_case_set_apart_ending_with_a_colon_is_no_heading(
    text: str, heading: bool
) -> None:
    line = _line(text, _BODY_LEFT_PT, 175 + 2.0 * _PITCH_PT)
    page = _page_with_a_line_among_the_text(20, line, 2.0)
    blocks = make_blocks(_lines_of(page), _NO_WORDS, workers=1)
    assert bool(_headings(blocks)) is heading


def test_tall_line_flush_left_below_a_tall_chapter_label_is_its_level_1_heading() -> (
    None
):
    # The label 1.3 times the body's height, indented 45 pt and not
    # centred; the title 2.4
    # times, flush left, 1.5 pitches below it.
    label = _line("Chapter Twelve", _BODY_LEFT_PT + 45, 100, 1.3 * _WORD_HEIGHT_PT)
    title = _line(
        "The Long Title", _BODY_LEFT_PT, 100 + 1.5 * _PITCH_PT, 2.4 * _WORD_HEIGHT_PT
    )
    page = PageLayout(
        20,
        (
            _region(label),
            _region(title),
            _region(*_running_text(100 + 3.5 * _PITCH_PT, 12)),
        ),
        (),
    )
    blocks = make_blocks(_lines_of(page), _NO_WORDS, workers=1)
    assert _headings(blocks) == ((1, "Chapter Twelve", "The Long Title"),)


@pytest.mark.parametrize(("gap", "heading"), [(0.8, False), (1.5, True)])
def test_tall_line_0_8_pitch_below_the_line_before_is_no_heading(
    gap: float, heading: bool
) -> None:
    # As wide as the text, neither centred nor flush left.
    line = _line(
        "line 06 of the running text",
        _BODY_LEFT_PT,
        175 + gap * _PITCH_PT,
        2.4 * _WORD_HEIGHT_PT,
    )
    page = _page_with_a_line_among_the_text(20, line, 2.5)
    blocks = make_blocks(_lines_of(page), _NO_WORDS, workers=1)
    assert bool(_headings(blocks)) is heading


@pytest.mark.parametrize(
    ("head", "headings"),
    [("A STRANGE LINE", ()), ("CHAPTER SEVEN", ((1, None, "CHAPTER SEVEN"),))],
)
def test_flush_left_head_line_left_in_the_text_near_the_head_top_is_no_heading(
    head: str, headings: tuple[tuple[int, None, str], ...]
) -> None:
    # Pages 10 to 13 have the running head "THE BOOK" at 36 pt; page 14's
    # head line, at 50 pt, is alike to none.
    page = PageLayout(
        14,
        (_region(_line(head, _BODY_LEFT_PT, 50)), _region(*_running_text(100, 12))),
        (),
    )
    lines = _lines_of(
        *(_page_with_head(index, "THE BOOK") for index in range(10, 14)), page
    )
    blocks = make_blocks(lines, _NO_WORDS, workers=1)
    assert _headings(blocks) == headings


@pytest.mark.parametrize(("tall_lines", "headings"), [(6, 1), (7, 0)])
def test_tall_lines_of_text_over_small_type_are_no_headings_past_6_on_a_page(
    tall_lines: int, headings: int
) -> None:
    # 20 lines of small type (7 pt) above `tall_lines` lines of text in the
    # body's type (10 pt), 1.5 pitches below them: the text's lines stand
    # 1.43 times the page's median line height.
    small = tuple(
        _line(
            f"line {number:02} of the small type", _BODY_LEFT_PT, 100 + 10 * number, 7
        )
        for number in range(20)
    )
    text = _running_text(100 + 10 * 19 + 1.5 * _PITCH_PT, tall_lines)
    page = PageLayout(20, (_region(*small, *text),), ())
    blocks = make_blocks(_lines_of(page), _NO_WORDS, workers=1)
    assert len(_headings(blocks)) == headings


def test_tall_chapter_label_under_a_speck_is_its_headings_label() -> None:
    # Turney's page 134: a speck "#" 6 pt above the label, in its region.
    speck = _line("#", 140, 94)
    label = _line("Chapter Twelve", _BODY_LEFT_PT + 45, 100, 1.3 * _WORD_HEIGHT_PT)
    title = _line(
        "The Long Title", _BODY_LEFT_PT, 100 + 1.5 * _PITCH_PT, 2.4 * _WORD_HEIGHT_PT
    )
    page = PageLayout(
        20,
        (
            _region(speck, label),
            _region(title),
            _region(*_running_text(100 + 3.5 * _PITCH_PT, 12)),
        ),
        (),
    )
    blocks = make_blocks(_lines_of(page), _NO_WORDS, workers=1)
    assert _headings(blocks) == ((1, "Chapter Twelve", "The Long Title"),)


@pytest.mark.parametrize(("gap", "label"), [(2.9, "CHAPTER TWELVE"), (4.1, None)])
def test_title_line_in_capitals_continues_up_to_4_pitches_below_a_chapter_label(
    gap: float, label: str | None
) -> None:
    # Haynes' page 249: the label flush left in capitals; the title's first
    # line in capitals, as wide as the text but for 15 pt, neither flush
    # left nor tall; its second line tall, 1.9 pitches lower.
    head = _line("CHAPTER TWELVE", _BODY_LEFT_PT, 60)
    first = _line("A RATHER LONG FIRST TITLE", _BODY_LEFT_PT, 60 + gap * _PITCH_PT)
    second = _line(
        "THE SECOND LINE",
        _BODY_LEFT_PT,
        first.box.top + 1.9 * _PITCH_PT,
        1.4 * _WORD_HEIGHT_PT,
    )
    text = _running_text(second.box.top + 3 * _PITCH_PT, 12)
    page = PageLayout(20, (_region(head), _region(first, second, *text)), ())
    blocks = make_blocks(_lines_of(page), _NO_WORDS, workers=1)
    if label is None:
        assert (1, None, "CHAPTER TWELVE") in _headings(blocks)
    else:
        assert _headings(blocks) == (
            (1, label, "A RATHER LONG FIRST TITLE THE SECOND LINE"),
        )


# On the six public-domain books (spec section 26, "Whole-book tests"), from
# the session's run of each whole book (tests/conftest.py).

_PUBLIC_DOMAIN_BOOKS = (
    "normansineuropea00hask",
    "earlyplantagenet01stub",
    "domesdaybook00maituoft",
    "catherinedemedic00mariuoft",
    "battleofkadeshst00breauoft",
    "politicaltheorie00gieruoft",
)
_LABEL_WORDS = frozenset(
    {"chapter", "chapitre", "essay", "part", "partie", "book", "livre"}
)
# The pages whose running head layout's step 3 or the regions beside the
# head (spec section 3) now remove. Gierke's 72 and 78 are not among them:
# their heads, read "List of ~-l ntlioritics." and "List of slnthoriti*
# ixxiii", are 0.74 and 0.70 alike to the others, below the 0.75 of
# section 3, and stay in the text.
_HEADS_REMOVED = {
    "normansineuropea00hask": (23, 30, 66, 235),
    "earlyplantagenet01stub": (20, 100, 152, 158, 186, 202, 210),
    "politicaltheorie00gieruoft": (69, 70, 71, 73, 74, 75, 76, 77, 79),
}


@pytest.fixture(scope="module")
def whole_book_blocks(
    whole_book_run: Callable[[str], BookFolder],
) -> Callable[[str], BlocksFile]:
    """A function that gives blocks.json of a whole public-domain book, by
    Internet Archive identifier, read once from the session's run."""

    @functools.cache
    def blocks_of(book: str) -> BlocksFile:
        return read_blocks(whole_book_run(book).blocks_json)

    return blocks_of


@pytest.mark.whole_book
@pytest.mark.thread_unsafe
@pytest.mark.parametrize("book", _PUBLIC_DOMAIN_BOOKS)
def test_whole_book_no_running_head_removed_starts_with_a_chapter_label_word(
    whole_book_blocks: Callable[[str], BlocksFile], book: str
) -> None:
    heads = tuple(
        removal.text
        for removal in whole_book_blocks(book).removals
        if removal.reason is RemovalReason.RUNNING_HEAD
    )
    assert heads
    assert not any(
        head.split()[0].rstrip(".,").lower() in _LABEL_WORDS for head in heads
    )


@pytest.mark.whole_book
@pytest.mark.thread_unsafe
@pytest.mark.parametrize("book", sorted(_HEADS_REMOVED))
def test_whole_book_running_heads_of_the_reference_pages_are_removed(
    whole_book_blocks: Callable[[str], BlocksFile], book: str
) -> None:
    removed = frozenset(
        removal.page_index
        for removal in whole_book_blocks(book).removals
        if removal.reason is RemovalReason.RUNNING_HEAD
    )
    assert set(_HEADS_REMOVED[book]) <= removed
    if book == "politicaltheorie00gieruoft":
        assert not {72, 78} & removed


@pytest.mark.whole_book
@pytest.mark.thread_unsafe
def test_whole_book_haskins_195_notes_set_close_under_the_text_are_notes(
    whole_book_blocks: Callable[[str], BlocksFile],
) -> None:
    # The excerpt cannot give them: its page 195 follows page 66's
    # "BIBLIOGRAPHICAL NOTE" with no chapter heading between, so its band
    # is taken for that note's paragraphs (spec section 16).
    blocks = whole_book_blocks("normansineuropea00hask")
    assert tuple(
        (note.marker, note.origin[0].page_index)
        for note in blocks.notes
        if note.origin[0].page_index == 195
    ) == (("^", 195), ("^", 195))
