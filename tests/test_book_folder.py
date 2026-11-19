"""Tests of galley.book_folder (spec section 3, architecture section 5)."""

from pathlib import Path

import pytest

from galley.book_folder import BookFolder, Stage, delete_stage_outputs


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
    assert folder.correct_jsonl == root / "edits" / "correct.jsonl"
    assert folder.book_md == root / "book.md"
    assert folder.book_epub == root / "book.epub"


# The files each stage deletes: its own and every later stage's (spec section 3).
_DELETED = {
    Stage.ANALYZE: [
        "blocks.json",
        "book.epub",
        "book.md",
        "images",
        "lines.json",
        "pages.json",
        "words.json",
    ],
    Stage.EXTRACT: [
        "blocks.json",
        "book.epub",
        "book.md",
        "images",
        "lines.json",
        "words.json",
    ],
    Stage.LAYOUT: ["blocks.json", "book.epub", "book.md", "lines.json"],
    Stage.STRUCTURE: ["blocks.json", "book.epub", "book.md"],
    Stage.CORRECT: ["book.epub", "book.md"],
    Stage.MARKDOWN: ["book.epub", "book.md"],
    Stage.EPUB: ["book.epub"],
}
_EVERY_FILE = sorted(
    {name for names in _DELETED.values() for name in names}
    | {"book.toml", "edits", "notes.txt"}
)


@pytest.mark.parametrize("stage", list(Stage))
def test_a_stage_deletes_its_own_file_and_every_later_one_and_nothing_else(
    stage: Stage, tmp_path: Path
) -> None:
    folder = BookFolder(tmp_path)
    for name in (
        "book.toml",
        "notes.txt",
        "pages.json",
        "words.json",
        "lines.json",
        "blocks.json",
        "book.md",
        "book.epub",
    ):
        (tmp_path / name).write_text(name, encoding="utf-8")
    folder.images_dir.mkdir()
    folder.cover_png.write_bytes(b"png")
    folder.edits_dir.mkdir()
    (folder.edits_dir / "owner.jsonl").write_text("", encoding="utf-8")
    folder.correct_jsonl.write_text("", encoding="utf-8")

    delete_stage_outputs(folder, stage)

    assert sorted(path.name for path in tmp_path.iterdir()) == sorted(
        set(_EVERY_FILE) - set(_DELETED[stage])
    )
    # correct.jsonl goes with structure and every stage before it, and with
    # correct itself (correct spec, section 8); no other edits file ever.
    deletes_correct = list(Stage).index(stage) <= list(Stage).index(Stage.CORRECT)
    assert sorted(path.name for path in folder.edits_dir.iterdir()) == (
        ["owner.jsonl"] if deletes_correct else ["correct.jsonl", "owner.jsonl"]
    )


def test_deleting_from_an_empty_folder_is_no_error(tmp_path: Path) -> None:
    delete_stage_outputs(BookFolder(tmp_path), Stage.ANALYZE)

    assert list(tmp_path.iterdir()) == []
