"""The book folder: the folder that holds a book's config, every file the
stages write, and the edits (architecture section 5)."""

from dataclasses import dataclass
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
    def book_md(self) -> Path:
        """Written by markdown."""
        return self.root / "book.md"

    @property
    def book_epub(self) -> Path:
        """Written by epub."""
        return self.root / "book.epub"
