"""Tests of structure's running heads, page numbers and headings for the
plan owner-books (docs/specs/structure.md, sections 2 to 4 and 14; the
unit tests of section 26).

Every page is written by hand, as in tests/test_structure.py: a word is 5
pt wide per character and 10 pt high, with one character's width between
words, and body lines lie 15 pt apart.
"""

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
    Word,
    block_text,
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
    assert any(text.startswith("THE BOOK the first") for text in _texts_on(blocks, 10))
    assert ("page_number", "225") in _removed(blocks, 11)


def test_region_of_6_characters_beside_head_leaves_the_head_in_the_text() -> None:
    lines = _pages_with_numbers_beside(_page_with_number_beside(10, "224224"))
    blocks = make_blocks(lines, _NO_WORDS, workers=1)
    assert _removed(blocks, 10) == ()
    assert any(text.startswith("THE BOOK the first") for text in _texts_on(blocks, 10))


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
