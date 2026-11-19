"""The book folder: the folder that holds a book's config, every file the
stages write, and the edits (architecture section 5), and the deletion of
what a stage and the stages after it wrote."""

import shutil
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


@dataclass(frozen=True, slots=True)
class BookFolder:
    """The paths of one book's files, each under `root`.

    Only paths: nothing is read or created here.
    """

    root: Path

    @property
    def book_toml(self) -> Path:
        """The config, written by the owner."""
        return self.root / "book.toml"

    @property
    def pages_json(self) -> Path:
        """Written by analyze."""
        return self.root / "pages.json"

    @property
    def words_json(self) -> Path:
        """Written by extract."""
        return self.root / "words.json"

    @property
    def images_dir(self) -> Path:
        """Written by extract: figures and the cover, grayscale PNG."""
        return self.root / "images"

    @property
    def cover_png(self) -> Path:
        """The cover rendered by extract when the config has `cover_page`."""
        return self.images_dir / "cover.png"

    @property
    def lines_json(self) -> Path:
        """Written by layout."""
        return self.root / "lines.json"

    @property
    def blocks_json(self) -> Path:
        """Written by structure."""
        return self.root / "blocks.json"

    @property
    def edits_dir(self) -> Path:
        """The edits files, `<author>.jsonl`; never written by a stage run."""
        return self.root / "edits"

    @property
    def correct_jsonl(self) -> Path:
        """Written by correct: its edits, the only edits file a stage writes."""
        return self.edits_dir / "correct.jsonl"

    @property
    def book_md(self) -> Path:
        """Written by markdown."""
        return self.root / "book.md"

    @property
    def book_epub(self) -> Path:
        """Written by epub."""
        return self.root / "book.epub"


class Stage(StrEnum):
    """The stages that write files in the book folder, in pipeline order.
    The correct stage writes edits/correct.jsonl, the one edits file a stage
    writes (docs/specs/correct.md, section 8)."""

    ANALYZE = "analyze"
    EXTRACT = "extract"
    LAYOUT = "layout"
    STRUCTURE = "structure"
    CORRECT = "correct"
    MARKDOWN = "markdown"
    EPUB = "epub"


def _stage_outputs(folder: BookFolder) -> tuple[tuple[Stage, tuple[Path, ...]], ...]:
    """Each stage with the files it writes, in pipeline order (spec section 3)."""
    return (
        (Stage.ANALYZE, (folder.pages_json,)),
        (Stage.EXTRACT, (folder.words_json, folder.images_dir)),
        (Stage.LAYOUT, (folder.lines_json,)),
        (Stage.STRUCTURE, (folder.blocks_json,)),
        (Stage.CORRECT, (folder.correct_jsonl,)),
        (Stage.MARKDOWN, (folder.book_md,)),
        (Stage.EPUB, (folder.book_epub,)),
    )


def delete_stage_outputs(folder: BookFolder, stage: Stage) -> None:
    """Delete the files `stage` writes and those of every later stage, so
    that no file in the folder outlives the file it was made from (spec
    section 3). A file that does not exist is skipped; `images/` is deleted
    with what it holds. Nothing else is touched: never book.toml, and of
    edits/ only correct.jsonl, the correct stage's file.
    """
    outputs = _stage_outputs(folder)
    first = [listed for listed, _ in outputs].index(stage)
    for _, paths in outputs[first:]:
        for path in paths:
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink(missing_ok=True)
