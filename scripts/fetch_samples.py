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
            Excerpt(
                name="kadesh_59-68",
                page_indices=tuple(range(59, 69)),
                covers=(
                    "plates with captions and the series head over them, a "
                    "running head on page index 64 and a caption line on 68, "
                    "and the back of a plate (65), which analyze takes for a "
                    "plate (docs/specs/structure.md, section 9, and "
                    "docs/specs/plates.md)"
                ),
            ),
            Excerpt(
                name="kadesh_29-38",
                page_indices=tuple(range(29, 39)),
                covers=(
                    "the reference pages of docs/specs/figures.md, section 10: "
                    "maps printed on text pages with a caption below (page "
                    "indices 29, 33), maps set beside the text (36, 38), a "
                    "caption on the row of a footnote (36) and on the row of "
                    "the text beside it (38), and quotations printed in "
                    "hieroglyphs, a block of ten rows (37) and smaller ones "
                    "(31, 32, 36, 38); 34 is a plate with a text layer and 35 "
                    "the back of it, without one"
                ),
            ),
            Excerpt(
                name="kadesh_redo",
                page_indices=(*range(8, 17), 32, 34),
                covers=(
                    'the book read with ocr = "redo" (docs/plans/ocr-redo.md, '
                    "docs/specs/extract.md, section 9): pages whose text layer "
                    'is bad and Tesseract good (page index 9: "Me^iddo. '
                    'already in tli.- sixti-fiith"), note references glued '
                    "to their words that Tesseract reads as a sign (8, 10, "
                    "14), footnotes in two columns, running heads, the scan "
                    "of a cover that the config excludes (16), rows of "
                    "hieroglyphs that are no figure and that Tesseract reads "
                    "as centred junk (32), and a plate with a text layer (34)"
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
            Excerpt(
                name="gierke_front_flow",
                page_indices=(1, 6, 7, 8, 9, 10, 11, 12, 13, 100),
                covers=(
                    "the front matter of docs/specs/front-matter.md, section 6: "
                    "the binder's label (page index 1), half-title (6), "
                    "publisher's page (7), title page (8) and edition (9), "
                    "then the printed contents (10) and the errata (11), which "
                    "are not front matter; and the words that pdfplumber's "
                    "sorting cuts (docs/specs/extract.md, section 7): a word "
                    '"T" on page index 13, "h" and "im" on 100'
                ),
            ),
            Excerpt(
                name="gierke_intro_heads",
                # Page index 87, a body page, keeps the excerpt's body line
                # pitch near the book's: 11.79 pt by structure's survey
                # against 11.84, where pages 68 to 79 alone measure 11.67
                # and join page 75's margin notes otherwise than the book
                # does (17 November 2026).
                page_indices=(*range(68, 80), 87),
                covers=(
                    "the list of authorities (docs/specs/structure.md, "
                    "section 26): running heads with a roman page number "
                    "beside them, removed with it, and the list's section "
                    "headings, which the tall branch of the heading rule "
                    "takes"
                ),
            ),
            Excerpt(
                name="gierke_notes_heads",
                # Page index 78, whose running head "List of slnthoriti* ixxiii"
                # is the one 84's is alike to; 83, which the plan named for
                # it, is the index's title page, and 82's head "List of
                # Authorities." is not alike enough (0.70) to 84's.
                page_indices=(14, 15, 16, 17, 18, 40, 63, 78, 84, 146),
                covers=(
                    "the cases of the plan stray-text (docs/plans/stray-text.md): "
                    "footnotes of the translator's introduction, set in 8 pt "
                    "under a body of 10 to 11 pt, which no band holds at "
                    "a0a1675 (page indices 15 to 18, 40), and the translator's "
                    'footnote marked "*" (146); running heads the OCR damaged '
                    'beyond the survey\'s length limit, "s Introduction." (16) '
                    'and "JH if ex to List of slntlioritic*. Ixxix" (84), with '
                    "the alike heads of 14, 15, 17, 18 and 78; and a contents "
                    "page whose text-layer boxes sit off the print, which "
                    "must not be taken for an inkless page (63)"
                ),
            ),
        ),
    ),
    # Mariéjol left the evaluation set on 19 November 2026 (docs/plans/ocr-redo.md):
    # neither its text layer nor Tesseract reads its worn print, but its
    # excerpts cover rules no other excerpt does.
    Book(
        archive_id="catherinedemedic00mariuoft",
        title="J.-H. Mariéjol, Catherine de Médicis",
        gutenberg_number=None,
        excerpts=(
            Excerpt(
                name="mariejol_210-219",
                page_indices=tuple(range(210, 220)),
                covers=(
                    "the excerpt of layout's reference pages "
                    "(docs/specs/layout.md, section 8): page numbers at the "
                    "foot in parentheses, a foot line holding the signature "
                    "and the page number (page index 210), and footnotes in "
                    "poor OCR"
                ),
            ),
            Excerpt(
                name="mariejol_headings_verse",
                # Six pages, the cases of docs/specs/structure.md, section 9.
                page_indices=(18, 51, 52, 142, 229, 430),
                covers=(
                    "a chapter opening, CHAPITRE and its title (page index "
                    "18), verse over a page break (51, 52), a title that fills "
                    "the column (142), two verse quotes on one page (229), and "
                    "a heading of three lines (430)"
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
                name="haskins_front",
                page_indices=(1, 2, 8, 9, 10, 12, 13, 14, 16, 17, 18),
                covers=(
                    "the front matter of docs/specs/front-matter.md, section 6: "
                    "patterned endpapers read as garbage (page indices 1, 2), "
                    "title page (8), copyright (9) and dedication (10); then "
                    "the two pages of the preface (12, 13), the printed "
                    "contents (14), the start of chapter I (16) and two pages "
                    "with running heads (17, 18); page index 12's words are "
                    "an exact test of extract (docs/specs/extract.md, "
                    "section 7)"
                ),
            ),
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
            Excerpt(
                name="haskins_quotes_index",
                page_indices=(39, 41, 53, 71, 72, 73, 129, 209, 234, 267, 269),
                covers=(
                    "a level-2 heading BIBLIOGRAPHICAL NOTE mid-page with "
                    "paragraphs of small type after it (page index 39), "
                    "ended by the heading of chapter II (41), and "
                    "above a band of small type (129), quotes in smaller type "
                    "(53), a quote over two page breaks (71 to 73), Latin and "
                    "English verse (209, 234), and index pages whose rows are "
                    "read across both columns, with an entry from the foot of "
                    "one column to the top of the next (267, 269)"
                ),
            ),
            Excerpt(
                name="haskins_heads_notes",
                # The pages added to those of the cases (17 November 2026):
                # 64, whose running head "THE COMING OF THE NORTHMEN" is
                # the one other page's that 66's is alike to (structure
                # spec, section 3), and 24, 27 and 31, body pages that keep
                # the excerpt's measures at the book's, 8.23 pt and 15.17
                # pt against 8.31 and 15.19, and its marker form a sign, as
                # the book's. The nine pages of the cases alone measure a
                # pitch of 15.09 pt and the marker form digits, and page
                # 55's note row, 16.6 pt below the row above, then falls
                # within 1.1 pitches and makes a band the book does not
                # have. And 163, the first page of chapter VI: without a
                # chapter heading between page 66's "BIBLIOGRAPHICAL NOTE"
                # and page 195, structure took 195's footnotes for that
                # note's paragraphs (structure spec section 16).
                page_indices=(
                    22,
                    23,
                    24,
                    27,
                    28,
                    29,
                    30,
                    31,
                    55,
                    64,
                    66,
                    163,
                    195,
                    235,
                ),
                covers=(
                    "the cases of docs/specs/structure.md, section 26: a "
                    'word glued at a case change, "theAvre" (page index '
                    "22); running heads whose next row has a word boxed "
                    "tall (23, 30, 66, 235), with a speck above page 23's; "
                    "footnotes set close under the text, with no gap above "
                    'them (28, 55, 195), and page 28\'s "subjection ;" with '
                    "its note's sign; 29 holds the paragraph that runs on "
                    "from 28"
                ),
            ),
            Excerpt(
                name="haskins_endpapers",
                page_indices=(275, 276, 277, 278),
                covers=(
                    "the inkless pages of docs/specs/plates.md, section 2b: "
                    "the printer's colophon, a page of print (page index "
                    "275), a page without a text layer, which the book's config excludes (276), and the "
                    "patterned back endpapers whose text layer holds only OCR "
                    "junk (277, 278)"
                ),
            ),
        ),
        "earlyplantagenet01stub": (
            Excerpt(
                name="stubbs_51_56-64",
                # Page indices 52 to 55 are maps and blank pages without a text layer.
                page_indices=(51, *range(56, 65)),
                covers=(
                    "the excerpt of layout's reference pages "
                    "(docs/specs/layout.md, section 8): a chapter opening with "
                    "a summary in small type, margin notes cut into the text "
                    "column on both sides, running heads with dates, specks "
                    "above the head, and a hyphen across a page break"
                ),
            ),
            Excerpt(
                name="stubbs_summaries_index",
                page_indices=(16, 28, 79, 157, 312, 313, 316, 318, 319, 321),
                covers=(
                    "a printed contents page (page index 16), chapter summaries "
                    "whose OCR is out of order (28) or whose last line is "
                    'centred (79), "John." in lower case under "CHAPTER VII." '
                    "(157), and the index: guide words, columns read as a band, "
                    "rows across the columns, letter initials and spaced "
                    "letters (312 to 321)"
                ),
            ),
            Excerpt(
                name="stubbs_cut_in",
                page_indices=(19, 34, 37, 120, 125, 143),
                covers=(
                    "cut-in margin notes whose lines share the body's "
                    "baselines, which the test by size of "
                    "docs/specs/layout.md, step 2b, takes (page indices 19, "
                    "37) or leaves in the body (34, where the text layer "
                    "mixes the rows; 143, a gap under 8 pt), and body lines "
                    "with a wide space at the inset beside a note, whose "
                    'words must stay ("The same", 120; "open war.", 125)'
                ),
            ),
            Excerpt(
                name="stubbs_heads",
                # The pages added to those of the cases (17 November 2026):
                # 22, 98, 102, 150, 154, 160, 164, 184, 204, 208 and 212,
                # whose running heads are alike to those of the cases, so
                # that each case's head has another page's to be alike to
                # (structure spec, section 3), as on the whole book; they
                # are even pages with their margin notes on the right, as
                # the cases have. The skew splits the rows of pages 100,
                # 152, 186, 202 and 210: the seven pages of the cases alone
                # measure a body line pitch of 7.68 pt against the book's
                # 12.87, and no cut-in inset; with the pages added, 12.27 pt
                # and a right inset of 58.0 pt against 59.0. Page 152's
                # cut-in notes still differ from the book's.
                page_indices=(
                    20,
                    22,
                    98,
                    100,
                    102,
                    150,
                    152,
                    154,
                    158,
                    160,
                    164,
                    184,
                    186,
                    202,
                    204,
                    208,
                    210,
                    212,
                ),
                covers=(
                    "the cases of docs/specs/structure.md, section 26: "
                    "running heads whose date at the outer end the scan's "
                    'skew sets a row lower (every page), and a ";" set '
                    "apart from its word by a space"
                ),
            ),
        ),
        "domesdaybook00maituoft": (
            Excerpt(
                name="domesday_front_flow",
                page_indices=(4, 8, 9, 10, 11, 12, 13, 23, 24, 200),
                covers=(
                    "the front matter of docs/specs/front-matter.md, section 6: "
                    "a flyleaf with handwriting (page index 4), half-title (8), "
                    "publisher's page (9), title page (10) and edition (11), "
                    "then the preface (12, 13); and the words that "
                    "pdfplumber's sorting cuts (docs/specs/extract.md, "
                    'section 7): "s" and "ome" on page index 23, "i" and "t" '
                    'on 24, "W", "L" and "ter" on 200'
                ),
            ),
            Excerpt(
                name="domesday_74-83",
                page_indices=tuple(range(74, 84)),
                covers=(
                    "the excerpt of layout's reference pages "
                    "(docs/specs/layout.md, section 8): outer margin notes on "
                    "both sides, footnotes, short notes side by side, and the "
                    'signature marks "M. 4" (page index 74) and "4—2" (76)'
                ),
            ),
            Excerpt(
                name="domesday_headings_quotes",
                page_indices=(14, 22, 30, 39, 40, 42, 47, 93, 272, 274, 406),
                covers=(
                    "a printed contents page (page index 14), an essay's label "
                    "3.4 pitches above its title (22), a section heading in "
                    "lower case mid-page (30), maps as plates with a caption "
                    "and the binder's note (39, 40), a table's title in "
                    "capitals (42), tables read as verse (47, 406), inset "
                    "quotes (93) and quotes in smaller type (274) above "
                    "footnotes; 47 and 272 repeat the running heads of 93 and "
                    "274 and keep the excerpt's body measures at the book's "
                    "(structure spec, section 9)"
                ),
            ),
            Excerpt(
                name="domesday_rereads",
                # Page indices 34, 140 and 158 repeat the running heads of
                # 36, 136 and 160, which the excerpt otherwise keeps in the
                # text where the book removes them (17 November 2026).
                page_indices=(26, 34, 36, 97, 136, 138, 139, 140, 150, 158, 160),
                covers=(
                    "the cases of docs/specs/structure.md, section 26: "
                    "margin notes whose words the text layer and "
                    "re-reading both give (docs/specs/reocr.md, section 4: "
                    '"tem," on page index 26, and 36, 139, 150, 160); '
                    "footnotes set close under the text, with no gap above "
                    "them (97, 138); and two text lines of page 136 that "
                    "the tall branch of the heading rule takes for "
                    "headings, a known failure"
                ),
            ),
            Excerpt(
                name="domesday_lists",
                # Pages 133, 143, 147, 155, 161, 162 and 163 are body pages
                # that bring the excerpt's body measures near the book's
                # (structure spec, section 32), measured by structure's
                # survey on 18 November 2026: a body word height of 10.0 pt
                # and a body line pitch of 11.65 pt, against the book's
                # 10.0 and 11.98. The five pages of the cases alone measure
                # 9.0 and 10.39: their tables set the rows close. Page 146,
                # tried first, kept its running head, which the book
                # removes by its other pages' heads.
                page_indices=(133, 141, 143, 147, 155, 156, 157, 158, 161, 162, 163),
                covers=(
                    "the cases of docs/specs/structure.md, section 32: the "
                    "tables of the Wetherley hundred, each vill's rows "
                    "numbered and their second lines hung (page indices 156 "
                    "to 158), which the list rules make numbered lists; "
                    'enumerations "(i)" to "(vi)" set as paragraphs (141), '
                    'and "(iv)" to "(viii)", which start with no first value '
                    "(143)"
                ),
            ),
            Excerpt(
                name="domesday_notes",
                # Page index 430, whose running head "Domesday Statistics." is
                # the one 428's is alike to.
                page_indices=(24, 35, 55, 89, 163, 174, 278, 428, 430, 481),
                covers=(
                    "the cases of the plan stray-text (docs/plans/stray-text.md): "
                    "one-line footnotes boxed as tall as the body (page "
                    "indices 163, 174, 278); references the OCR glued to a "
                    'number ("£16,0002", 24), followed by punctuation '
                    '("servus*.", 55) or read as a letter ("villV", 89); '
                    "three notes kept as one (35); a page number boxed "
                    'apart above its running head ("403" over "Domesday '
                    "Statistics.\", 428, alike to 430's head); and a table "
                    "whose column heads are "
                    "printed sideways, a page of print with words without "
                    "ink (481)"
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
