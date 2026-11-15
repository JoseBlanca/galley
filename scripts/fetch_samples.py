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
The evaluation books, with their Internet Archive identifier and Gutenberg
number, are read from evaluation/books.toml. A book, an HTML file or an
excerpt already there is not downloaded or cut again; delete an excerpt
to cut it again. A download is written to `<file>.part` and renamed when
whole.

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
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pypdfium2

from galley_eval.books import read_books

logger = logging.getLogger("fetch_samples")

REPO = Path(__file__).resolve().parent.parent
EXCERPTS_DIR = REPO / "tests" / "fixtures" / "pdf"

# The Internet Archive and Project Gutenberg ask automated clients to go slowly.
SECONDS_BETWEEN_DOWNLOADS = 5
DOWNLOAD_TIMEOUT_S = 300
CHUNK_BYTES = 1 << 20
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
)

EVALUATION_BOOKS_TOML = REPO / "evaluation" / "books.toml"

# The excerpts cut from books of the evaluation set, by Internet Archive
# identifier.
EVALUATION_EXCERPTS = frozendict(
    {
        "normansineuropea00hask": (
            Excerpt(
                name="haskins_eval",
                # Printed pages 116 to 123, 250 and 251: page index = printed
                # page + 15. Page 250 is the blank page before the index, as in
                # the book; it keeps the index more than a page from the body.
                page_indices=(*range(131, 139), 265, 266),
                covers=(
                    "the excerpt of the evaluation tool's test "
                    "(docs/specs/evaluation.md, section 10): a chapter start "
                    "with a drop capital, running heads with page numbers, "
                    "footnotes on three pages, hyphens at line ends and one "
                    "across a page break, a section break, a blank page without "
                    "a text layer, and the first page of the two-column index"
                ),
            ),
        ),
    }
)


def all_books() -> tuple[Book, ...]:
    """The books with excerpts, then the evaluation set of
    evaluation/books.toml (docs/specs/evaluation.md, section 3), whose
    Gutenberg HTML is downloaded too, with the excerpts of
    EVALUATION_EXCERPTS."""
    evaluation = tuple(
        Book(
            archive_id=book.archive_id,
            title=f"{', '.join(book.authors)}, {book.title}",
            gutenberg_number=book.gutenberg_number,
            excerpts=EVALUATION_EXCERPTS.get(book.archive_id, ()),
        )
        for book in read_books(EVALUATION_BOOKS_TOML)
    )
    return (*BOOKS, *evaluation)


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


def downloads(books_dir: Path, book: Book) -> tuple[tuple[str, Path], ...]:
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
        size = save(path, iter(lambda: response.read(CHUNK_BYTES), b""))
    logger.info("downloaded %s (%d bytes)", path.name, size)


def save(path: Path, chunks: Iterator[bytes]) -> int:
    """Write `chunks` to `path` and return the bytes written. They go first
    to `<path>.part`, renamed to `path` only once the last chunk is
    written, so that an interrupted download is never taken for a whole
    file. A partial file left by a failure is overwritten by the next try."""
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(path.name + ".part")
    size = 0
    with partial.open("wb") as out:
        for chunk in chunks:
            out.write(chunk)
            size += len(chunk)
    partial.replace(path)
    return size


def cut(books_dir: Path, excerpts_dir: Path, book: Book, excerpt: Excerpt) -> Path:
    """Cut `excerpt` from `book` into `excerpts_dir`, unless it is there:
    pypdfium2 does not save the same pages to the same bytes twice, and a
    committed excerpt must not change. Delete it to cut it again."""
    out_path = excerpts_dir / f"{excerpt.name}.pdf"
    if out_path.exists():
        logger.info("already there: %s", out_path)
        return out_path
    source = pypdfium2.PdfDocument(_book_path(books_dir, book))
    target = pypdfium2.PdfDocument.new()
    try:
        target.import_pages(source, list(excerpt.page_indices))
        excerpts_dir.mkdir(parents=True, exist_ok=True)
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
    for book in all_books():
        if not args.cut_only:
            for url, path in downloads(books_dir, book):
                if path.exists():
                    logger.info("already there: %s", path)
                    continue
                if downloaded > 0:
                    time.sleep(SECONDS_BETWEEN_DOWNLOADS)
                _download(url, path)
                downloaded += 1
        for excerpt in book.excerpts:
            cut(books_dir, EXCERPTS_DIR, book, excerpt)
    logger.info("downloaded %d files into %s", downloaded, books_dir)


if __name__ == "__main__":
    main()
