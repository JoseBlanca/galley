"""The reading rules of each book of the evaluation set, on its whole
Gutenberg HTML: the reader finds the counts that books.toml gives, counted
by hand (spec section 10). Marked whole_book: the HTML is downloaded by
scripts/fetch_samples.py and ignored by git."""

from pathlib import Path

import pytest

from galley_eval.books import EvaluationBook, ExpectedCounts, read_books
from galley_eval.reader import ReferenceKind, read_reference_file

BOOKS = read_books(Path(__file__).parents[3] / "evaluation" / "books.toml")


@pytest.mark.whole_book
@pytest.mark.parametrize("book", BOOKS, ids=[book.name for book in BOOKS])
def test_reader_finds_the_expected_counts_in_the_html(
    book: EvaluationBook, books_dir: Path
) -> None:
    html = books_dir / "gutenberg" / book.html_name
    if not html.is_file():
        pytest.skip(f"{html} is missing; run `uv run python scripts/fetch_samples.py`")
    reference = read_reference_file(html, book.rules)
    found = ExpectedCounts(
        notes=len(reference.notes),
        margin_notes=sum(
            1 for block in reference.blocks if block.kind is ReferenceKind.MARGIN_NOTE
        ),
        note_references=len(reference.note_references),
        # The count in the HTML holds the anchors left among the notes.
        page_anchors=len(reference.page_anchors) + len(reference.anchors_in_notes),
    )
    assert found == book.expected_counts
