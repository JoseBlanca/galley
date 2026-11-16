"""Fixtures of the evaluation tool's tests.

The whole books and their Gutenberg HTML are ignored by git, so a worktree
does not have them. They are found as galley's tests find the books
(tests/conftest.py of the repository): through the GALLEY_SAMPLES
environment variable, or else in `samples/` of the main checkout, which git
reports as the parent of the common git directory.
`scripts/fetch_samples.py` downloads them.

The small book is a reference of one paragraph compared with a hand-made
galley side, for the tests of the files the tool writes and its command.
"""

import os
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

from galley.config import Language
from galley.model import BlockKind, Box, PageWords, TextSource, Word, WordsFile
from galley_eval.align import GalleyStream, GalleyToken
from galley_eval.books import EvaluationBook, ExpectedCounts
from galley_eval.evaluate import Evaluation, evaluation_of
from galley_eval.galley_side import GalleyBlock, GalleySide
from galley_eval.reader import (
    ReferenceBlock,
    ReferenceKind,
    ReferenceText,
    ReferenceToken,
)
from galley_eval.rules import DEFAULT_RULES


def _main_checkout_samples() -> Path:
    # The tests run inside a git checkout or one of its worktrees; if git
    # fails here, that is an error to see, not a reason to skip.
    common = subprocess.run(
        ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
        capture_output=True,
        text=True,
        check=True,
        timeout=10,
    ).stdout.strip()
    return Path(common).parent / "samples"


@pytest.fixture(scope="session")
def books_dir() -> Path:
    """The directory of the whole public-domain books, whose `gutenberg/`
    holds their HTML editions, for whole_book tests.

    Skips the test, with the reason, when the books were never downloaded.
    """
    env = os.environ.get("GALLEY_SAMPLES")
    samples = Path(env) if env is not None and env != "" else _main_checkout_samples()
    path = samples / "public_domain"
    if not any(path.glob("*.pdf")):
        pytest.skip(
            f"no whole books in {path}; run `uv run python scripts/fetch_samples.py`"
        )
    return path


# A small book compared with galley's hand-made side, for the tests of the
# files the tool writes and of its command: a running head never removed,
# a hyphen at a line end joined by structure (spec section 5), and "werk"
# misread.


def _small_book(name: str = "small") -> EvaluationBook:
    return EvaluationBook(
        name=name,
        gutenberg_number=42,
        archive_id=f"{name}00",
        title="A “Small” Book",
        authors=("Ann Author", 'Bo "B" Writer'),
        language=Language.EN,
        exclude_pages=(0, 3),
        contents_pages=(1,),
        plate_pages=(2,),
        not_in_reference=(),
        margin_notes_moved=False,
        html_sha256="0" * 64,
        expected_counts=ExpectedCounts(
            notes=0,
            margin_notes=0,
            note_references=0,
            page_anchors=0,
            headings=0,
            first_tokens=(),
        ),
        rules=DEFAULT_RULES,
    )


def _tokens(
    text: str, *, edge_of_page: bool = False, block_id: str | None = None
) -> tuple[GalleyToken, ...]:
    return tuple(
        GalleyToken(
            text=word,
            page_index=1,
            stream=GalleyStream.BODY,
            edge_of_page=edge_of_page,
            block_id=block_id,
        )
        for word in text.split()
    )


def _small_evaluation(book: EvaluationBook | None = None) -> Evaluation:
    reference = ReferenceText(
        blocks=(
            ReferenceBlock(
                ReferenceKind.PARAGRAPH,
                tuple(
                    ReferenceToken(word, marked_correction=False)
                    for word in (
                        [
                            "We",
                            "must",
                            "replicate",
                            "the",
                            "work",
                            "of",
                            "the",
                            "Normans",
                            "in",
                            "Sicily",
                        ]
                    )
                ),
            ),
        ),
        notes=(),
        note_references=(),
        page_anchors=(),
        anchors_in_notes=(),
    )
    words = _tokens("RUNNING HEAD", edge_of_page=True) + _tokens(
        "We must repli- cate the werk of the Normans in Sicily"
    )
    blocks = _tokens(
        "RUNNING HEAD We must replicate the werk of the Normans in Sicily",
        block_id="b-p0001-001",
    )
    side = GalleySide(
        words=words,
        lines=words,
        blocks=blocks,
        markdown=blocks,
        galley_blocks=frozendict(
            {
                "b-p0001-001": GalleyBlock(
                    kind=BlockKind.PARAGRAPH, stream=GalleyStream.BODY, note_id=None
                )
            }
        ),
        note_references=(),
        words_file=WordsFile(
            source_pdf_sha256="0" * 64,
            pages=(
                PageWords(
                    index=1,
                    text_source=TextSource.TEXT_LAYER,
                    words=tuple(
                        Word(token.text, Box(0.0, 0.0, 1.0, 1.0), None)
                        for token in words
                    ),
                    figures=(),
                ),
            ),
            removals=(),
        ),
    )
    return evaluation_of(
        book if book is not None else _small_book(),
        reference,
        side,
        frozenset(("we", "must", "the")),
    )


@pytest.fixture
def small_book() -> Callable[[str], EvaluationBook]:
    """Makes the small book's entry, under a name."""
    return _small_book


@pytest.fixture
def small_evaluation() -> Callable[[EvaluationBook | None], Evaluation]:
    """Compares the small book, or another entry with its pages, with
    galley's hand-made side."""
    return _small_evaluation
