"""Download the public-domain sample books and cut the committed excerpts.

The books are scans from the Internet Archive with an OCR text layer, like
the PDFs galley is written for, and are out of copyright, so excerpts of
them can be committed as test fixtures. The whole books go to
`samples/public_domain/`, and the Project Gutenberg HTML edition of the
books of the evaluation set (docs/specs/evaluation.md, section 3) to
`samples/public_domain/gutenberg/`; git ignores both. The excerpts go to
`tests/fixtures/pdf/`, which is committed.

`samples/` is that of the main checkout, also when the script runs in a
worktree, or the folder that GALLEY_SAMPLES names, as the tests find it.
A book or an HTML file already there is not downloaded again.

    uv run python scripts/fetch_samples.py            # download and cut
    uv run python scripts/fetch_samples.py --cut-only # cut from books on disk

Excerpt pages are page indices from 0 of the Internet Archive PDF.
"""

import argparse
import logging
import os
import subprocess
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import pypdfium2

logger = logging.getLogger("fetch_samples")

REPO = Path(__file__).resolve().parent.parent
EXCERPTS_DIR = REPO / "tests" / "fixtures" / "pdf"

# The Internet Archive and Project Gutenberg ask automated clients to go slowly.
SECONDS_BETWEEN_DOWNLOADS = 5
DOWNLOAD_TIMEOUT_S = 300
USER_AGENT = "galley-dev/0.1"


@dataclass(frozen=True, slots=True)
class Excerpt:
    name: str
    page_indices: tuple[int, ...]
    covers: str


@dataclass(frozen=True, slots=True)
class Book:
    """A public-domain book: its Internet Archive identifier, its Project
    Gutenberg ebook number when it is in the evaluation set, else None, and
    the excerpts cut from it."""

    archive_id: str
    title: str
    gutenberg_number: int | None
    excerpts: tuple[Excerpt, ...]


BOOKS = (
    Book(
        archive_id="battleofkadeshst00breauoft",
        title="J. H. Breasted, The Battle of Kadesh (University of Chicago, 1903)",
        gutenberg_number=None,
        excerpts=(
            Excerpt(
                name="kadesh_8-17",
                page_indices=tuple(range(8, 18)),
                covers=(
                    "chapter opening, running heads alternating author and title, "
                    "footnotes, a second page-number sequence at the foot, "
                    "a plate and a blank page"
                ),
            ),
        ),
    ),
    Book(
        archive_id="politicaltheorie00gieruoft",
        title="O. Gierke, Political Theories of the Middle Age, tr. F. W. Maitland (1900)",
        gutenberg_number=None,
        excerpts=(
            Excerpt(
                name="gierke_86-93_270-271",
                page_indices=(*range(86, 94), 270, 271),
                covers=(
                    "chapter opening, running heads alternating book and section "
                    "title, a printer's signature mark at a page foot, endnotes"
                ),
            ),
        ),
    ),
    # The evaluation set of docs/specs/evaluation.md, section 3.
    Book(
        archive_id="normansineuropea00hask",
        title="C. H. Haskins, The Normans in European History (1915)",
        gutenberg_number=72514,
        excerpts=(),
    ),
    Book(
        archive_id="earlyplantagenet01stub",
        title="W. Stubbs, The Early Plantagenets (1900)",
        gutenberg_number=70828,
        excerpts=(),
    ),
    Book(
        archive_id="domesdaybook00maituoft",
        title="F. W. Maitland, Domesday Book and Beyond (1897)",
        gutenberg_number=43255,
        excerpts=(),
    ),
    Book(
        archive_id="catherinedemedic00mariuoft",
        title="J. H. Mariéjol, Catherine de Médicis (1920)",
        gutenberg_number=36315,
        excerpts=(),
    ),
)


def _samples_dir() -> Path:
    """GALLEY_SAMPLES, or else `samples/` of the main checkout, which git
    reports as the parent of the common git directory (tests/conftest.py)."""
    env = os.environ.get("GALLEY_SAMPLES")
    if env is not None and env != "":
        return Path(env)
    common = subprocess.run(
        ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
        capture_output=True,
        text=True,
        check=True,
        timeout=10,
        cwd=REPO,
    ).stdout.strip()
    return Path(common).parent / "samples"


def _book_path(books_dir: Path, book: Book) -> Path:
    return books_dir / f"{book.archive_id}.pdf"


def _downloads(books_dir: Path, book: Book) -> tuple[tuple[str, Path], ...]:
    """The (url, path) of each file of `book` to download: its PDF and, for
    a book of the evaluation set, its Gutenberg HTML edition."""
    pdf = (
        f"https://archive.org/download/{book.archive_id}/{book.archive_id}.pdf",
        _book_path(books_dir, book),
    )
    if book.gutenberg_number is None:
        return (pdf,)
    number = book.gutenberg_number
    html = (
        f"https://www.gutenberg.org/cache/epub/{number}/pg{number}-images.html",
        books_dir / "gutenberg" / f"pg{number}-images.html",
    )
    return (pdf, html)


def _download(url: str, path: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=DOWNLOAD_TIMEOUT_S) as response:
        content = response.read()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    logger.info("downloaded %s (%d bytes)", path.name, len(content))


def _cut(books_dir: Path, book: Book, excerpt: Excerpt) -> Path:
    source = pypdfium2.PdfDocument(_book_path(books_dir, book))
    target = pypdfium2.PdfDocument.new()
    try:
        target.import_pages(source, list(excerpt.page_indices))
        EXCERPTS_DIR.mkdir(parents=True, exist_ok=True)
        out_path = EXCERPTS_DIR / f"{excerpt.name}.pdf"
        with out_path.open("wb") as out:
            target.save(out)
    finally:
        target.close()
        source.close()
    logger.info("cut %s: %d pages", out_path.name, len(excerpt.page_indices))
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--cut-only", action="store_true", help="do not download")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    books_dir = _samples_dir() / "public_domain"
    downloaded = 0
    for book in BOOKS:
        if not args.cut_only:
            for url, path in _downloads(books_dir, book):
                if path.exists():
                    logger.info("already there: %s", path)
                    continue
                if downloaded > 0:
                    time.sleep(SECONDS_BETWEEN_DOWNLOADS)
                _download(url, path)
                downloaded += 1
        for excerpt in book.excerpts:
            _cut(books_dir, book, excerpt)
    logger.info("downloaded %d files into %s", downloaded, books_dir)


if __name__ == "__main__":
    main()
