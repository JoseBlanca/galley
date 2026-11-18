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

import functools
import json
import re
import threading
from collections.abc import Callable
from pathlib import Path

import pytest

from galley.book_folder import BookFolder
from galley.cli import main
from galley.model import (
    BlockKind,
    BlocksFile,
    PageNumberPosition,
    RemovalReason,
    block_text,
    read_blocks,
)

pytestmark = pytest.mark.whole_book

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
    chapters = sum(
        1
        for label in labels
        if label is not None and label.lower().startswith("chapter")
    )
    assert chapters == _CHAPTERS[book]


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
        head.split()[0].rstrip(".,").lower() in _LABEL_WORDS for head in heads
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
