"""Whole-book tests on the owner's two modern books (docs/specs/structure.md,
sections 21 and 26, "Whole-book tests").

The books are copyrighted: they sit in the samples folder, ignored by git,
and these tests count what galley gives on them, never quote their text.
Each test finds its book's PDF by a pattern of its file name and skips,
with the reason, when the PDF is absent. The pipeline runs to blocks.json
once per session and book, with the configs of structure spec section 21,
`ocr = "trust"`, and a placeholder title and author, so that no title of
the owner's is written in the repository.
"""

import bisect
import itertools
import re
from collections.abc import Callable

import pytest

from galley.model import (
    BlockKind,
    BlocksFile,
    ChangeReason,
    Note,
    NoteKind,
    PageNumberPosition,
    RemovalReason,
    block_text,
)

pytestmark = [pytest.mark.whole_book, pytest.mark.timeout(900)]

# Structure spec section 21: the chapters each book numbers ("Chapter One"
# to "Chapter Ten"; "CHAPTER ONE" to "CHAPTER SIXTEEN").
_CHAPTERS = {"turney": 10, "haynes": 16}
# Structure spec section 4: Turney prints the number of a chapter's first
# page at the foot, on these 15 opening pages.
_TURNEY_OPENING_PAGES = frozenset(
    {14, 26, 39, 56, 77, 104, 134, 148, 189, 217, 229, 252, 278, 300, 301}
)
# Structure spec section 21: the first page of the introduction, of each
# chapter and of a closing chapter, then of the notes, in page indices.
_OPENINGS = {
    "turney": (14, 26, 39, 56, 77, 104, 134, 148, 189, 217, 229, 252),
    "haynes": (
        *(14, 22, 36, 48, 63, 79, 87, 105, 117, 141),
        *(156, 175, 200, 224, 249, 281, 308, 326, 330),
    ),
}
# Structure spec section 26, "Whole-book tests": the endnotes, the note
# groups (notes with a group), and the endnotes linked, at least.
_ENDNOTES = {"turney": 580, "haynes": 620}
_NOTE_GROUPS = {"turney": 11, "haynes": 18}
_LINKED = {"turney": 450, "haynes": 550}
# Structure spec sections 3 and 14: the words that start a chapter label.
_LABEL_WORDS = frozenset(
    {"chapter", "chapitre", "essay", "part", "partie", "book", "livre"}
)


def _level_1_headings(blocks: BlocksFile) -> tuple[str | None, ...]:
    """The label of each level-1 heading, None for one without."""
    return tuple(
        block.label
        for block in blocks.blocks
        if block.kind is BlockKind.HEADING and block.level == 1
    )


@pytest.mark.parametrize("book", ["turney", "haynes"])
def test_every_chapter_is_a_level_1_heading_with_its_label(
    owner_book_run: Callable[[str], BlocksFile], book: str
) -> None:
    labels = _level_1_headings(owner_book_run(book))
    # Distinct labels, so that a chapter found twice does not stand for a
    # chapter missed.
    chapters = tuple(
        label.lower()
        for label in labels
        if label is not None and label.lower().startswith("chapter")
    )
    assert len(set(chapters)) == len(chapters) == _CHAPTERS[book]


@pytest.mark.parametrize("book", ["turney", "haynes"])
def test_at_least_5_level_1_headings_have_no_label(
    owner_book_run: Callable[[str], BlocksFile], book: str
) -> None:
    # The introduction, the notes, the bibliography, the index, and others.
    labels = _level_1_headings(owner_book_run(book))
    assert sum(label is None for label in labels) >= 5


@pytest.mark.parametrize("book", ["turney", "haynes"])
def test_no_running_head_removed_starts_with_a_chapter_label_word(
    owner_book_run: Callable[[str], BlocksFile], book: str
) -> None:
    blocks = owner_book_run(book)
    heads = tuple(
        removal.text
        for removal in blocks.removals
        if removal.reason is RemovalReason.RUNNING_HEAD
    )
    assert heads
    assert not any(
        head.split()[0].rstrip(".,:;").lower() in _LABEL_WORDS for head in heads
    )


def test_turney_page_numbers_at_the_foot_of_at_least_14_of_its_15_opening_pages(
    owner_book_run: Callable[[str], BlocksFile],
) -> None:
    blocks = owner_book_run("turney")
    at_the_foot = frozenset(
        number.page_index
        for number in blocks.page_numbers
        if number.position is PageNumberPosition.FOOT
        and number.page_index in _TURNEY_OPENING_PAGES
    )
    assert len(at_the_foot) >= len(_TURNEY_OPENING_PAGES) - 1


@pytest.mark.parametrize("book", ["turney", "haynes"])
def test_no_margin_note_is_a_number_of_1_to_3_digits(
    owner_book_run: Callable[[str], BlocksFile], book: str
) -> None:
    blocks = owner_book_run(book)
    assert not any(
        re.fullmatch(r"[0-9]{1,3}", block_text(block))
        for block in blocks.blocks
        if block.kind is BlockKind.MARGIN_NOTE
    )


def _endnotes(blocks: BlocksFile) -> tuple[Note, ...]:
    return tuple(note for note in blocks.notes if note.kind is NoteKind.ENDNOTE)


@pytest.mark.parametrize("book", ["turney", "haynes"])
def test_endnotes_number_at_least_the_target(
    owner_book_run: Callable[[str], BlocksFile], book: str
) -> None:
    assert len(_endnotes(owner_book_run(book))) >= _ENDNOTES[book]


@pytest.mark.parametrize("book", ["turney", "haynes"])
def test_note_groups_with_a_heading_number_at_least_the_target(
    owner_book_run: Callable[[str], BlocksFile], book: str
) -> None:
    endnotes = _endnotes(owner_book_run(book))
    assert sum(note.group is not None for note in endnotes) >= _NOTE_GROUPS[book]


@pytest.mark.parametrize("book", ["turney", "haynes"])
def test_endnotes_linked_number_at_least_the_target(
    owner_book_run: Callable[[str], BlocksFile], book: str
) -> None:
    endnotes = _endnotes(owner_book_run(book))
    assert sum(note.referenced for note in endnotes) >= _LINKED[book]


def _group_starts(endnotes: tuple[Note, ...]) -> tuple[int, ...]:
    """The positions of the endnotes that start a note group: the first,
    each with a group heading, and each whose marker reads 1."""
    return tuple(
        position
        for position, note in enumerate(endnotes)
        if position == 0 or note.group is not None or note.marker.rstrip(".") == "1"
    )


def _chapter_of_page(book: str, page_index: int) -> int:
    """The chapter a body page is in: 0 for the introduction, n for chapter
    n, and the closing chapter after the last."""
    return bisect.bisect_right(_OPENINGS[book], page_index) - 1


@pytest.mark.parametrize("book", ["turney", "haynes"])
def test_no_reference_links_to_a_note_of_another_groups_chapter(
    owner_book_run: Callable[[str], BlocksFile], book: str
) -> None:
    # The groups follow the chapters' order, one per chapter of structure
    # spec section 21's openings (the introduction first): the n-th group's
    # chapter is the n-th. A link from a page of another chapter is wrong.
    blocks = owner_book_run(book)
    endnotes = _endnotes(blocks)
    starts = (*_group_starts(endnotes), len(endnotes))
    assert len(starts) - 1 == len(_OPENINGS[book]) - 1
    group_of = {
        note.id: number
        for number, (start, end) in enumerate(itertools.pairwise(starts))
        for note in endnotes[start:end]
    }
    links = tuple(
        (group_of[span.note_ref], _chapter_of_page(book, block.origin[0].page_index))
        for block in blocks.blocks
        for span in block.spans
        if span.note_ref in group_of
    )
    assert links
    assert sum(group != chapter for group, chapter in links) == 0


# Structure spec section 26, "Whole-book tests": the endnotes without a
# link, at most (section 12, "The candidates of endnotes"; 65 and 13 on 23
# November 2026, 83 and 50 before).
_UNLINKED = {"turney": 70, "haynes": 15}
# Structure spec section 11, "Matching": the digit pairs the OCR confuses.
_CONFUSED_DIGITS = frozenset(
    frozenset(pair) for pair in ("38", "56", "17", "35", "68", "14", "89", "28")
)


@pytest.mark.parametrize("book", ["turney", "haynes"])
def test_endnotes_without_a_link_number_at_most_the_target(
    owner_book_run: Callable[[str], BlocksFile], book: str
) -> None:
    endnotes = _endnotes(owner_book_run(book))
    assert sum(not note.referenced for note in endnotes) <= _UNLINKED[book]


def _misread(reference: str, number: str) -> bool:
    """Whether `reference` differs from `number` in one digit the OCR
    confuses."""
    differing = tuple(
        frozenset(pair)
        for pair in zip(reference, number, strict=False)
        if len(set(pair)) > 1
    )
    return (
        len(reference) == len(number)
        and len(differing) == 1
        and differing[0] in _CONFUSED_DIGITS
    )


@pytest.mark.parametrize("book", ["turney", "haynes"])
def test_every_endnote_link_reads_its_notes_number(
    owner_book_run: Callable[[str], BlocksFile], book: str
) -> None:
    # The note's number is its marker's digits; a marker the OCR read with
    # no digit ("x") gives none to compare, and a reference misread by one
    # confused digit (Turney's "3" for a printed 5) is its note's.
    blocks = owner_book_run(book)
    numbers = {note.id: note.marker.rstrip(".") for note in _endnotes(blocks)}
    links = tuple(
        (span.text, numbers[span.note_ref])
        for block in blocks.blocks
        for span in block.spans
        if span.note_ref in numbers
    )
    assert links
    wrong = tuple(
        (reference, number)
        for reference, number in links
        if number.isdigit() and reference != number and not _misread(reference, number)
    )
    assert wrong == ()


# Structure spec section 26, "Whole-book tests": the epigraphs (section 22).
_EPIGRAPHS = {"turney": (13, 0), "haynes": (21, 8)}
_SOURCE_DASHES = {"turney": 0, "haynes": 21}
# Structure spec section 22: Turney's own epigraph, alone on its page.
_TURNEY_EPIGRAPH_PAGE = 13


@pytest.mark.parametrize("book", ["turney", "haynes"])
def test_epigraph_blocks_and_those_with_line_feeds_number_the_books_own(
    owner_book_run: Callable[[str], BlocksFile], book: str
) -> None:
    epigraphs = tuple(
        block
        for block in owner_book_run(book).blocks
        if block.kind is BlockKind.EPIGRAPH
    )
    assert (
        len(epigraphs),
        sum("\n" in block_text(block) for block in epigraphs),
    ) == _EPIGRAPHS[book]


@pytest.mark.parametrize("book", ["turney", "haynes"])
def test_source_dash_changes_number_the_dashed_sources(
    owner_book_run: Callable[[str], BlocksFile], book: str
) -> None:
    changes = owner_book_run(book).word_changes
    assert (
        sum(change.reason is ChangeReason.SOURCE_DASH for change in changes)
        == _SOURCE_DASHES[book]
    )


def test_turney_page_13_is_the_origin_of_an_epigraph_block_and_of_no_other(
    owner_book_run: Callable[[str], BlocksFile],
) -> None:
    kinds = tuple(
        block.kind
        for block in owner_book_run("turney").blocks
        if any(origin.page_index == _TURNEY_EPIGRAPH_PAGE for origin in block.origin)
    )
    assert kinds == (BlockKind.EPIGRAPH,)
