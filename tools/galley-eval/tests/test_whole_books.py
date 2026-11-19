"""The reading rules of each book of the evaluation set, on its whole
Gutenberg HTML: the reader finds the counts and first tokens that
books.toml gives, counted by hand (spec section 10), and leaves out the
text Gutenberg added. Marked whole_book: the HTML is downloaded by
scripts/fetch_samples.py and ignored by git."""

from pathlib import Path

import pytest

from galley_eval.books import EvaluationBook, ExpectedCounts, read_books
from galley_eval.reader import ReferenceKind, ReferenceText, read_reference_file

BOOKS = read_books(Path(__file__).parents[3] / "evaluation" / "books.toml")

# Words that Gutenberg added to a book and its rules leave out, found by
# reading the HTML. Each guards a rule that no count does.
GUTENBERG_TOKENS = frozendict(
    {
        "haskins": frozenset(("FOOTNOTES", "*")),
        "stubbs": frozenset(("workPage",)),
        "domesday": frozenset(("NOTES", "map]")),
    }
)


def _reference(book: EvaluationBook, books_dir: Path) -> ReferenceText:
    html = books_dir / "gutenberg" / book.html_name
    if not html.is_file():
        pytest.skip(f"{html} is missing; run `uv run python scripts/fetch_samples.py`")
    return read_reference_file(
        html, book.rules, book.html_sha256, ends_at=book.reference_ends_at
    )


def _tokens(reference: ReferenceText) -> tuple[str, ...]:
    body = (token.text for block in reference.blocks for token in block.tokens)
    notes = (
        token.text
        for note in reference.notes
        for block in note.blocks
        for token in block.tokens
    )
    return (*body, *notes)


@pytest.mark.whole_book
@pytest.mark.parametrize("book", BOOKS, ids=[book.name for book in BOOKS])
def test_reader_finds_the_expected_counts_in_the_html(
    book: EvaluationBook, books_dir: Path
) -> None:
    reference = _reference(book, books_dir)
    found = ExpectedCounts(
        notes=len(reference.notes),
        margin_notes=sum(
            1 for block in reference.blocks if block.kind is ReferenceKind.MARGIN_NOTE
        ),
        note_references=len(reference.note_references),
        # The count in the HTML holds the anchors left among the notes.
        page_anchors=len(reference.page_anchors) + len(reference.anchors_in_notes),
        headings=sum(
            1 for block in reference.blocks if block.kind is ReferenceKind.HEADING
        ),
        first_tokens=tuple(
            token.text for block in reference.blocks for token in block.tokens
        )[:5],
    )
    assert found == book.expected_counts


@pytest.mark.whole_book
@pytest.mark.parametrize("book", BOOKS, ids=[book.name for book in BOOKS])
def test_reader_leaves_out_the_text_gutenberg_added(
    book: EvaluationBook, books_dir: Path
) -> None:
    tokens = _tokens(_reference(book, books_dir))
    assert [
        token
        for token in tokens
        if token in GUTENBERG_TOKENS[book.name]
        or any(pattern.fullmatch(token) for pattern in book.rules.drop_text)
    ] == []
