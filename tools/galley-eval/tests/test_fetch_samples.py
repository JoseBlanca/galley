"""Tests of scripts/fetch_samples.py where it meets the evaluation set: it
takes the books from evaluation/books.toml, never rewrites a committed
excerpt, and never leaves a partial download where a whole file goes."""

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

from galley_eval.books import read_books

REPO = Path(__file__).parents[3]


def _script() -> ModuleType:
    path = REPO / "scripts" / "fetch_samples.py"
    spec = importlib.util.spec_from_file_location("fetch_samples", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_evaluation_books_and_their_html_come_from_books_toml(
    tmp_path: Path,
) -> None:
    script = _script()
    evaluation = read_books(REPO / "evaluation" / "books.toml")
    books = {book.archive_id: book for book in script.all_books()}
    for book in evaluation:
        downloads = script.downloads(tmp_path, books[book.archive_id])
        assert [path for _, path in downloads] == [
            tmp_path / book.pdf_name,
            tmp_path / "gutenberg" / book.html_name,
        ]


@pytest.mark.thread_unsafe
def test_an_excerpt_already_there_is_not_cut_again(tmp_path: Path) -> None:
    script = _script()
    book = script.BOOKS[0]
    excerpt = book.excerpts[0]
    committed = tmp_path / f"{excerpt.name}.pdf"
    committed.write_bytes(b"committed bytes")
    # The whole book is not in tmp_path: cutting would fail to open it.
    script.cut(tmp_path, tmp_path, book, excerpt)
    assert committed.read_bytes() == b"committed bytes"


def test_a_download_is_written_whole_or_not_at_all(tmp_path: Path) -> None:
    script = _script()
    path = tmp_path / "gutenberg" / "pg1-images.html"

    def chunks() -> object:
        yield b"<html>"
        message = "connection reset"
        raise OSError(message)

    with pytest.raises(OSError, match="connection reset"):
        script.save(path, chunks())
    assert not path.exists()
    script.save(path, iter((b"<html>", b"</html>")))
    assert path.read_bytes() == b"<html></html>"
    assert list(path.parent.iterdir()) == [path]
