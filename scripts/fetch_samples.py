"""Download the public-domain sample books and cut the committed excerpts.

The books are scans from the Internet Archive with an OCR text layer, like
the PDFs galley is written for, and are out of copyright, so excerpts of
them can be committed as test fixtures. The whole books go to
`samples/public_domain/`, which git ignores; the excerpts go to
`tests/fixtures/pdf/`, which is committed.

    uv run python scripts/fetch_samples.py            # download and cut
    uv run python scripts/fetch_samples.py --cut-only # cut from books on disk

Excerpt pages are page indices from 0 of the Internet Archive PDF.
"""

import argparse
import logging
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import pypdfium2

logger = logging.getLogger("fetch_samples")

REPO = Path(__file__).resolve().parent.parent
BOOKS_DIR = REPO / "samples" / "public_domain"
EXCERPTS_DIR = REPO / "tests" / "fixtures" / "pdf"

# The Internet Archive asks automated clients to go slowly.
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
    archive_id: str
    title: str
    excerpts: tuple[Excerpt, ...]


BOOKS = (
    Book(
        archive_id="battleofkadeshst00breauoft",
        title="J. H. Breasted, The Battle of Kadesh (University of Chicago, 1903)",
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


def _book_path(book: Book) -> Path:
    return BOOKS_DIR / f"{book.archive_id}.pdf"


def _download(book: Book) -> None:
    url = f"https://archive.org/download/{book.archive_id}/{book.archive_id}.pdf"
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=DOWNLOAD_TIMEOUT_S) as response:
        content = response.read()
    BOOKS_DIR.mkdir(parents=True, exist_ok=True)
    _book_path(book).write_bytes(content)
    logger.info("downloaded %s (%d bytes)", book.archive_id, len(content))


def _cut(book: Book, excerpt: Excerpt) -> Path:
    source = pypdfium2.PdfDocument(_book_path(book))
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

    for position, book in enumerate(BOOKS):
        if not args.cut_only:
            if position > 0:
                time.sleep(SECONDS_BETWEEN_DOWNLOADS)
            _download(book)
        for excerpt in book.excerpts:
            _cut(book, excerpt)


if __name__ == "__main__":
    main()
