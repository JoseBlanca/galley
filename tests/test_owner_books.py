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
import functools
import itertools
import json
import re
import threading
from collections import Counter
from collections.abc import Callable
from pathlib import Path

import pytest

from galley.book_folder import BookFolder
from galley.cli import main
from galley.model import (
    BlockKind,
    BlocksFile,
    Note,
    NoteKind,
    PageNumberPosition,
    RemovalReason,
    block_text,
    read_blocks,
)

pytestmark = [pytest.mark.whole_book, pytest.mark.timeout(900)]

# Structure spec section 21, "Their configs", as the survey of 17 November
# 2026 ran them; the pattern finds each PDF in the samples folder.
_PATTERNS = {"turney": "*Turney*.pdf", "haynes": "*Haynes*.pdf"}
_CONFIGS = {
    "turney": (
        "exclude_pages = [2, 3, 5, 9, 165, 168, 171, 306, 307, 308, 309]\n"
        "contents_pages = [10]\n"
    ),
    "haynes": (
        "exclude_pages = [0, 1, 3, 7, 11, 13, 329, 389, 431, 432, 434]\n"
        "contents_pages = [8]\n"
    ),
}
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
# Turney's notes miss three targets (18 November 2026), for causes outside
# the rules of section 12: layout puts the right column's numbers 12 to 31
# of page 262 into the left column's lines, which loses 20 notes and
# chapter Four's group heading; the OCR reads chapter Three's first "1" as
# "x" (page 258), so its notes 2 to 48 stay in chapter Two's last note and
# its group is lost; a stray "/" under chapter Six's heading (page 268) is
# the block before its first note, so that group has no heading either.
_TURNEY_LAYOUT_AND_OCR = pytest.mark.xfail(
    strict=True,
    reason="Turney: layout's page 262, the OCR's 'x' for 1 on page 258 and a "
    "stray '/' on page 268 (structure spec section 12)",
)
_TURNEY_MISSED = pytest.param("turney", marks=_TURNEY_LAYOUT_AND_OCR)
# Structure spec sections 3 and 14: the words that start a chapter label.
_LABEL_WORDS = frozenset(
    {"chapter", "chapitre", "essay", "part", "partie", "book", "livre"}
)


@pytest.fixture(scope="session")
def owner_book_run(
    samples_dir: Path, tmp_path_factory: pytest.TempPathFactory
) -> Callable[[str], BlocksFile]:
    """A function that gives blocks.json of one of the owner's books, by
    the name "turney" or "haynes", run from its PDF to structure the first
    time a test asks for it and kept for the session. Skips the test when
    the book's PDF is not in the samples folder. A book's run holds its
    lock, so that two threads asking for it share one run."""
    roots = {book: tmp_path_factory.mktemp(book) for book in _PATTERNS}
    locks = {book: threading.Lock() for book in _PATTERNS}

    def run(book: str) -> BlocksFile:
        pdfs = sorted(samples_dir.glob(_PATTERNS[book]))
        if not pdfs:
            pytest.skip(f"no PDF matching {_PATTERNS[book]} in {samples_dir}")
        with locks[book]:
            return run_once(book, pdfs[0])

    @functools.cache
    def run_once(book: str, pdf: Path) -> BlocksFile:
        folder = BookFolder(roots[book])
        folder.book_toml.write_text(
            f"pdf = {json.dumps(str(pdf))}\n"
            'title = "An owner\'s book"\n'
            'authors = ["An Author"]\n'
            'language = "en"\n'
            'ocr = "trust"\n'
            f"{_CONFIGS[book]}",
            encoding="utf-8",
        )
        for stage in ("analyze", "extract", "layout", "structure"):
            main([stage, str(folder.root)])
        return read_blocks(folder.blocks_json)

    return run


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


@pytest.mark.parametrize("book", [_TURNEY_MISSED, "haynes"])
def test_endnotes_number_at_least_the_target(
    owner_book_run: Callable[[str], BlocksFile], book: str
) -> None:
    assert len(_endnotes(owner_book_run(book))) >= _ENDNOTES[book]


@pytest.mark.parametrize("book", [_TURNEY_MISSED, "haynes"])
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


def _heading_chapter(group: str, first: bool, last_chapter: int) -> int:
    """The chapter a group heading names by its first number ("Chapter 5."
    or "5 Into"): the introduction for the first group without a number,
    the closing chapter for a later one."""
    number = next(
        (
            int(word.rstrip(".:"))
            for word in group.split()
            if word.rstrip(".:").isdigit()
        ),
        None,
    )
    if number is not None:
        return number
    return 0 if first else last_chapter


@pytest.mark.parametrize("book", [_TURNEY_MISSED, "haynes"])
def test_no_reference_links_to_a_note_of_another_groups_chapter(
    owner_book_run: Callable[[str], BlocksFile], book: str
) -> None:
    # Each group's chapter is the one its heading names, or, for a group
    # without a heading, the chapter most of its links fall in; a link from
    # a page of another chapter (structure spec section 21) is wrong.
    blocks = owner_book_run(book)
    endnotes = _endnotes(blocks)
    starts = (*_group_starts(endnotes), len(endnotes))
    group_of = {
        note.id: number
        for number, (start, end) in enumerate(itertools.pairwise(starts))
        for note in endnotes[start:end]
    }
    pages_of: dict[int, list[int]] = {}
    for block in blocks.blocks:
        for span in block.spans:
            if span.note_ref in group_of:
                pages_of.setdefault(group_of[span.note_ref], []).append(
                    block.origin[0].page_index
                )
    last_chapter = len(_OPENINGS[book]) - 2
    wrong = 0
    for number, start in enumerate(starts[:-1]):
        chapters = Counter(
            _chapter_of_page(book, page) for page in pages_of.get(number, ())
        )
        heading = endnotes[start].group
        chapter = (
            _heading_chapter(heading, number == 0, last_chapter)
            if heading is not None
            else max(chapters, key=lambda found: chapters[found], default=None)
        )
        wrong += sum(count for found, count in chapters.items() if found != chapter)
    assert pages_of
    assert wrong == 0
