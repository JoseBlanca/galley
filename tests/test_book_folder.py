"""Tests of galley.book_folder (spec section 3, architecture section 5)."""

from pathlib import Path

from galley.book_folder import BookFolder


def test_every_path_is_the_one_of_the_book_folder() -> None:
    root = Path("/books/kadesh")
    folder = BookFolder(root)

    assert folder.root == root
    assert folder.book_toml == root / "book.toml"
    assert folder.pages_json == root / "pages.json"
    assert folder.words_json == root / "words.json"
    assert folder.images_dir == root / "images"
    assert folder.cover_png == root / "images" / "cover.png"
    assert folder.lines_json == root / "lines.json"
    assert folder.blocks_json == root / "blocks.json"
    assert folder.edits_dir == root / "edits"
    assert folder.book_md == root / "book.md"
    assert folder.book_epub == root / "book.epub"
