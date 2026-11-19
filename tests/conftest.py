"""Fixtures shared by every stage's tests.

The excerpt PDFs are public domain and committed under tests/fixtures/pdf/.
The whole books are ignored by git, so a worktree does not have them. They
are found through the GALLEY_SAMPLES environment variable, or else in
`samples/` of the main checkout, which git reports as the parent of the
common git directory. `scripts/fetch_samples.py` downloads them.

`excerpt_books` runs `galley2epub run` once per session on a book folder
for each excerpt, so that the excerpt tests of every stage read the files of
one run; `whole_book_run` does the same for the whole books, up to
structure, the first time a test asks for a book, and `owner_book_run` for
the owner's two books, which tests of several modules count on. `lists_book`
and `lists_book_epub` hold the lists book that the markdown tests of lists
read and whose EPUB the epub tests validate.
"""

import functools
import hashlib
import json
import os
import shutil
import subprocess
import sys
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

import pytest

from galley import epub, markdown
from galley.book_folder import BookFolder
from galley.cli import main
from galley.config import BookConfig, Language
from galley.model import (
    Block,
    BlockKind,
    BlocksFile,
    Box,
    Emphasis,
    Origin,
    PageInfo,
    PageKind,
    PagesFile,
    Span,
    TextSource,
    read_blocks,
    write_blocks,
    write_pages,
)

EXCERPTS_DIR = Path(__file__).parent / "fixtures" / "pdf"

# The excerpts' runs go side by side, each `galley2epub run` a process of
# its own with galley's own workers. In one process every PDFium call of
# every run waits for the one PDFium thread: measured on 19 November 2026
# on an M5 Pro (18 cores), the 24 excerpts as threads of the test process,
# 6 at once, took 32.6 s, analyze alone up to 6.4 s on an excerpt that
# takes 0.3 s by itself. As processes they took 14.3 and 18.9 s with 6 at
# once, 11.7 and 12.3 s with 9, 11.2 and 11.6 s with 12, and 12.3 s with
# 18 of 2 workers each. The files written are the same bytes either way,
# but for book.epub's identifier and date, which differ between any two
# runs.
_EXCERPT_RUNS_AT_ONCE = 12
# A whole excerpt's run takes up to 6 s by itself; guessed, not measured,
# as a bound far above it that still ends a run that hangs.
_EXCERPT_RUN_TIMEOUT_S = 300

# The configs of spec section 9, "The end-to-end test", without `pdf`.
# Kadesh's region on page 0 holds the page number 81. Its page 8 (book page
# 16) is the scan of a cover, not a plate (the owner, 16 November 2026),
# which analyze's plate rule would take; its page 9, without a text layer,
# is a plate, which analyze takes (plates spec section 6).
EXCERPT_CONFIGS = frozendict(
    {
        "kadesh_8-17": (
            'title = "The Battle of Kadesh"\n'
            'authors = ["J. H. Breasted"]\n'
            'language = "en"\n'
            "cover_page = 0\n"
            "exclude_regions = [{page = 0, box = [240, 620, 252, 632]}]\n"
            "exclude_pages = [8]\n"
        ),
        "gierke_86-93_270-271": (
            'title = "Political Theories of the Middle Age"\n'
            'authors = ["O. Gierke", "F. W. Maitland"]\n'
            'language = "en"\n'
        ),
        # Haskins page 8, the blank page before the index, has no text layer.
        "haskins_eval": (
            'title = "The Normans in European History"\n'
            'authors = ["Charles Homer Haskins"]\n'
            'language = "en"\n'
            "exclude_pages = [8]\n"
        ),
        "stubbs_51_56-64": (
            'title = "The Early Plantagenets"\n'
            'authors = ["William Stubbs"]\n'
            'language = "en"\n'
        ),
        "domesday_74-83": (
            'title = "Domesday Book and Beyond"\n'
            'authors = ["Frederic William Maitland"]\n'
            'language = "en"\n'
        ),
        "mariejol_210-219": (
            'title = "Catherine de Médicis"\n'
            'authors = ["Jean H. Mariéjol"]\n'
            'language = "fr"\n'
        ),
        # The excerpts of structure spec section 9, "The second plan".
        "haskins_quotes_index": (
            'title = "The Normans in European History"\n'
            'authors = ["Charles Homer Haskins"]\n'
            'language = "en"\n'
        ),
        # Excerpt page 0 is book page index 16, a printed contents page.
        "stubbs_summaries_index": (
            'title = "The Early Plantagenets"\n'
            'authors = ["William Stubbs"]\n'
            'language = "en"\n'
            "contents_pages = [0]\n"
        ),
        # Excerpt page 0 is book page index 14, a printed contents page.
        "domesday_headings_quotes": (
            'title = "Domesday Book and Beyond"\n'
            'authors = ["Frederic William Maitland"]\n'
            'language = "en"\n'
            "contents_pages = [0]\n"
        ),
        "mariejol_headings_verse": (
            'title = "Catherine de Médicis"\n'
            'authors = ["Jean H. Mariéjol"]\n'
            'language = "fr"\n'
        ),
        "kadesh_59-68": (
            'title = "The Battle of Kadesh"\n'
            'authors = ["J. H. Breasted"]\n'
            'language = "en"\n'
        ),
        # The excerpts of docs/specs/front-matter.md section 6, "Excerpt
        # tests", which open with the book's front pages. Excerpt page 7 is
        # Haskins' page index 14, and Gierke's page 5 its page index 10,
        # each a printed contents page.
        "haskins_front": (
            'title = "The Normans in European History"\n'
            'authors = ["Charles Homer Haskins"]\n'
            'language = "en"\n'
            "contents_pages = [7]\n"
        ),
        "domesday_front_flow": (
            'title = "Domesday Book and Beyond"\n'
            'authors = ["Frederic William Maitland"]\n'
            'language = "en"\n'
        ),
        "gierke_front_flow": (
            'title = "Political Theories of the Middle Age"\n'
            'authors = ["O. Gierke", "F. W. Maitland"]\n'
            'language = "en"\n'
            "contents_pages = [5]\n"
        ),
        # The excerpts of structure spec section 26, "Excerpt tests", for
        # the plan owner-books. Their pages are text pages with a text
        # layer, and none is a printed contents page: Gierke's list of
        # authorities (excerpt pages 0 to 11) is a list of books, not of
        # the book's chapters.
        "haskins_heads_notes": (
            'title = "The Normans in European History"\n'
            'authors = ["Charles Homer Haskins"]\n'
            'language = "en"\n'
        ),
        "stubbs_heads": (
            'title = "The Early Plantagenets"\n'
            'authors = ["William Stubbs"]\n'
            'language = "en"\n'
        ),
        "gierke_intro_heads": (
            'title = "Political Theories of the Middle Age"\n'
            'authors = ["O. Gierke", "F. W. Maitland"]\n'
            'language = "en"\n'
        ),
        "domesday_rereads": (
            'title = "Domesday Book and Beyond"\n'
            'authors = ["Frederic William Maitland"]\n'
            'language = "en"\n'
        ),
        # The excerpts of the plan lists-figures: Kadesh's reference pages
        # of docs/specs/figures.md section 10, with the whole book's config,
        # which excludes none of its pages and names none a plate; and
        # Domesday's tables of structure spec section 32.
        "kadesh_29-38": (
            'title = "The Battle of Kadesh"\n'
            'authors = ["J. H. Breasted"]\n'
            'language = "en"\n'
        ),
        "domesday_lists": (
            'title = "Domesday Book and Beyond"\n'
            'authors = ["Frederic William Maitland"]\n'
            'language = "en"\n'
        ),
        # The excerpts of the plan stray-text (docs/plans/stray-text.md):
        # Haskins' excerpt page 1 is its page index 276, which the whole
        # book's config excludes; Gierke's excerpt page 6 is its page index
        # 63, a printed contents page. Both begin with pages after the front
        # matter, which the front-matter rule would otherwise find later in
        # the excerpt (at its contents page, for Gierke).
        "haskins_endpapers": (
            'title = "The Normans in European History"\n'
            'authors = ["Charles Homer Haskins"]\n'
            'language = "en"\n'
            "exclude_pages = [1]\n"
            "front_matter_end = 0\n"
        ),
        "domesday_run_on": (
            'title = "Domesday Book and Beyond"\n'
            'authors = ["Frederic William Maitland"]\n'
            'language = "en"\n'
        ),
        "domesday_notes": (
            'title = "Domesday Book and Beyond"\n'
            'authors = ["Frederic William Maitland"]\n'
            'language = "en"\n'
        ),
        "gierke_notes_heads": (
            'title = "Political Theories of the Middle Age"\n'
            'authors = ["O. Gierke", "F. W. Maitland"]\n'
            'language = "en"\n'
            "contents_pages = [6]\n"
            "front_matter_end = 0\n"
        ),
        "stubbs_cut_in": (
            'title = "The Early Plantagenets"\n'
            'authors = ["William Stubbs"]\n'
            'language = "en"\n'
        ),
    }
)


# The excerpts read with `ocr = "redo"` (docs/specs/extract.md, section 9;
# docs/plans/ocr-redo.md), without `pdf`. They are kept out of
# EXCERPT_CONFIGS: `redo_excerpt_run` runs them the first time a test
# asks, analyze to structure only, so that the tests of the tasks still
# to come are strict xfails rather than errors of the session's run of
# every excerpt. Kadesh's excerpt page 8 is its page index 16, the scan
# of a cover, which the whole book's config excludes. Its region on page
# 0 holds the journal's page number 81 where Tesseract boxes it, 634.8 to
# 641.8 pt from the top, and nothing else (checked on the page at 300 dpi
# on 19 November 2026); kadesh_8-17's region is 12 pt higher, where the
# text layer misplaces it.
REDO_EXCERPT_CONFIGS = frozendict(
    {
        "kadesh_redo": (
            'title = "The Battle of Kadesh"\n'
            'authors = ["James Henry Breasted"]\n'
            'language = "en"\n'
            'ocr = "redo"\n'
            "exclude_regions = [{page = 0, box = [240, 632, 252, 644]}]\n"
            "exclude_pages = [8]\n"
        ),
    }
)

# The configs of the five whole books, by Internet Archive identifier,
# without `pdf`: the one place the whole_book tests of every stage take
# them from. Each has the book's title and authors, so that an EPUB made
# from it is titled as the book is (docs/plans/ocr-redo.md). The three
# books of the evaluation set have the same title, authors and pages as in
# evaluation/books.toml, which test_end_to_end.py checks. Mariéjol
# (catherinedemedic00mariuoft) left the whole-book tests on 19 November
# 2026: neither its text layer nor Tesseract reads its worn print; its
# excerpts stay.
#
# exclude_pages: the pages without a text layer that are not plates, which
# analyze refuses unless excluded (the evaluation books' as in
# evaluation/books.toml, Kadesh's and Gierke's as analyze listed them on 15
# November 2026), and the pages that analyze's plate rule takes wrongly
# (docs/specs/plates.md, sections 1 and 2): Kadesh 0, the cover, 16, the
# scan of a cover (the owner, 16 November 2026), and 49 and 65, backs of
# plates. The plates without a text layer (Kadesh 17, 23, 35, 43, 57 and 69;
# Stubbs 9, 11, 52 and 54) are not excluded: analyze takes them as plates
# (16 November 2026).
#
# contents_pages: the printed table of contents, found on 16 November 2026
# by "CONTENTS" at the top of the page and checked
# by reading each page's text layer. Kadesh has none. Gierke has two more
# lists of its chapters' parts: the "ANALYTICAL SUMMARY", pages 52 to 60,
# which centres the ten section headings, and the "SUBJECT MATTER OF THE
# NOTES", pages 61 to 67, ending before the "LIST OF AUTHORITIES" on 68
# (read in the text layer on 16 November 2026).
#
# plate_pages: Kadesh 23, a faint relief that analyze's rule misses.
WHOLE_BOOK_CONFIGS = frozendict(
    {
        "normansineuropea00hask": (
            'title = "The Normans in European History"\n'
            'authors = ["Charles Homer Haskins"]\n'
            'language = "en"\n'
            "exclude_pages = [0, 3, 4, 5, 7, 11, 15, 265, 274, 276, 279]\n"
            "contents_pages = [14]\n"
        ),
        # Stubbs' pages 322 to 337, the publisher's lists after its text,
        # are excluded: the heading rule takes their lines for headings
        # (structure spec section 27, point 4, settled 17 November 2026).
        "earlyplantagenet01stub": (
            'title = "The Early Plantagenets"\n'
            'authors = ["William Stubbs"]\n'
            'language = "en"\n'
            "exclude_pages = [0, 2, 3, 4, 5, 8, 10, 53, 55, 322, 323, 324, 325, "
            "326, 327, 328, 329, 330, 331, 332, 333, 334, 335, 336, 337, 338, 339, "
            "340, 341, 342, 343]\n"
            "contents_pages = [14, 15, 16]\n"
        ),
        "domesdaybook00maituoft": (
            'title = "Domesday Book and Beyond"\n'
            'authors = ["Frederic William Maitland"]\n'
            'language = "en"\n'
            "exclude_pages = [0, 1, 2, 3, 5, 6, 7, 38, 41, 554, 555, 557]\n"
            "contents_pages = [14, 15, 16, 17, 18, 19, 20]\n"
        ),
        # Kadesh is read with ocr = "redo": its text layer is bad throughout
        # (docs/plans/ocr-redo.md). Its page 74 is the library's card pocket,
        # excluded on 19 November 2026.
        "battleofkadeshst00breauoft": (
            'title = "The Battle of Kadesh"\n'
            'authors = ["James Henry Breasted"]\n'
            'language = "en"\n'
            'ocr = "redo"\n'
            "exclude_pages = [0, 1, 2, 3, 16, 49, 65, 70, 71, 72, 73, 74, 75]\n"
            "plate_pages = [23]\n"
        ),
        "politicaltheorie00gieruoft": (
            'title = "Political Theories of the Middle Age"\n'
            'authors = ["Otto Gierke"]\n'
            'language = "en"\n'
            "exclude_pages = [0, 2, 3, 4, 5, 51, 283, 284, 285, 286, 287, 288, 289]\n"
            "contents_pages = [10, 52, 53, 54, 55, 56, 57, 58, 59, 60, 61, 62, 63, "
            "64, 65, 66, 67]\n"
        ),
    }
)


def _main_checkout_samples() -> Path:
    # The tests run inside a git checkout or one of its worktrees; if git
    # fails here, that is an error to see, not a reason to skip.
    common = subprocess.run(
        ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
        capture_output=True,
        text=True,
        check=True,
        timeout=10,
    ).stdout.strip()
    return Path(common).parent / "samples"


@pytest.fixture(scope="session")
def excerpt_pdf() -> frozendict[str, Path]:
    """The committed excerpt PDFs, by name (the file name without .pdf)."""
    return frozendict({path.stem: path for path in sorted(EXCERPTS_DIR.glob("*.pdf"))})


@pytest.fixture(scope="session")
def excerpt_book_toml(excerpt_pdf: frozendict[str, Path]) -> frozendict[str, str]:
    """The `book.toml` of each excerpt, by excerpt name: the configs of spec
    section 9, with the absolute path of the excerpt's PDF."""
    # A TOML literal string: no escapes, so any path but one with a quote.
    return frozendict(
        {
            name: f"pdf = '{excerpt_pdf[name]}'\n{toml}"
            for name, toml in EXCERPT_CONFIGS.items()
        }
    )


@pytest.fixture(scope="session")
def excerpt_books(
    tmp_path_factory: pytest.TempPathFactory, excerpt_book_toml: frozendict[str, str]
) -> frozendict[str, BookFolder]:
    """A book folder for each excerpt, by excerpt name, with its `book.toml`
    (the configs of spec section 9) and the files `galley2epub run` wrote
    in it, book.epub last (spec section 9, "The end-to-end test").

    Session-scoped: the stages run once, also under --parallel-threads=8,
    and the excerpts' runs go side by side, each in a process of its own.
    A test reads these folders and never writes in them. Skips every test
    that uses it when Pandoc is missing, which markdown and epub need, or
    Tesseract, with which layout re-reads small print (docs/specs/reocr.md).
    """
    _require_program("pandoc")
    _require_program("tesseract")
    folders = {
        name: BookFolder(tmp_path_factory.mktemp(name)) for name in excerpt_book_toml
    }
    for name, folder in folders.items():
        folder.book_toml.write_text(excerpt_book_toml[name], encoding="utf-8")
    with ThreadPoolExecutor(max_workers=_EXCERPT_RUNS_AT_ONCE) as pool:
        # list() waits for every run and raises the first run's error.
        list(pool.map(_run_excerpt, folders.values()))
    return frozendict(folders)


def _run_excerpt(folder: BookFolder) -> None:
    """`galley2epub run` on `folder`, in a process of its own; its error
    output becomes the message of the failure."""
    command = [
        str(Path(sys.executable).parent / "galley2epub"),
        "run",
        str(folder.root),
    ]
    try:
        subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=True,
            timeout=_EXCERPT_RUN_TIMEOUT_S,
        )
    except subprocess.CalledProcessError as err:
        msg = (
            f"galley2epub run failed on {folder.root} with exit status "
            f"{err.returncode}:\n{err.stderr}"
        )
        raise RuntimeError(msg) from err


@pytest.fixture(scope="session")
def redo_excerpt_run(
    tmp_path_factory: pytest.TempPathFactory, excerpt_pdf: frozendict[str, Path]
) -> Callable[[str], BookFolder]:
    """A function that gives the book folder of an excerpt of
    REDO_EXCERPT_CONFIGS, by name, with the files analyze, extract, layout
    and structure wrote in it, each stage a process of its own, run the
    first time a test asks for it and kept for the session. The run is
    made inside the test, not in the fixture's setup, so that a test of a
    task not yet done fails as its strict xfail expects instead of
    erroring. Skips when Tesseract is missing. A test reads the folder and
    never writes in it."""
    _require_program("tesseract")
    roots = frozendict(
        {name: tmp_path_factory.mktemp(name) for name in REDO_EXCERPT_CONFIGS}
    )
    locks = frozendict({name: threading.Lock() for name in REDO_EXCERPT_CONFIGS})

    def run(name: str) -> BookFolder:
        with locks[name]:
            return run_once(name)

    @functools.cache
    def run_once(name: str) -> BookFolder:
        folder = BookFolder(roots[name])
        folder.book_toml.write_text(
            f"pdf = '{excerpt_pdf[name]}'\n{REDO_EXCERPT_CONFIGS[name]}",
            encoding="utf-8",
        )
        for stage in ("analyze", "extract", "layout", "structure"):
            _run_stage(stage, folder)
        return folder

    return run


def _run_stage(stage: str, folder: BookFolder) -> None:
    """`galley2epub <stage>` on `folder`, in a process of its own; its error
    output becomes the message of the failure."""
    command = [
        str(Path(sys.executable).parent / "galley2epub"),
        stage,
        str(folder.root),
    ]
    try:
        subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=True,
            timeout=_EXCERPT_RUN_TIMEOUT_S,
        )
    except subprocess.CalledProcessError as err:
        msg = (
            f"galley2epub {stage} failed on {folder.root} with exit status "
            f"{err.returncode}:\n{err.stderr}"
        )
        raise RuntimeError(msg) from err


@pytest.fixture(scope="session")
def samples_dir() -> Path:
    """The samples folder, where the owner's own PDFs sit, for whole_book
    tests: GALLEY_SAMPLES, or samples/ of the main checkout. It does not
    skip; a test that needs a PDF in it skips when the PDF is absent."""
    env = os.environ.get("GALLEY_SAMPLES")
    return Path(env) if env is not None and env != "" else _main_checkout_samples()


@pytest.fixture(scope="session")
def books_dir() -> Path:
    """The directory of the whole public-domain books, for whole_book tests.

    Skips the test, with the reason, when the books were never downloaded.
    """
    env = os.environ.get("GALLEY_SAMPLES")
    samples = Path(env) if env is not None and env != "" else _main_checkout_samples()
    path = samples / "public_domain"
    if not any(path.glob("*.pdf")):
        pytest.skip(
            f"no whole books in {path}; run `uv run python scripts/fetch_samples.py`"
        )
    return path


@pytest.fixture(scope="session")
def whole_book_configs() -> frozendict[str, str]:
    """WHOLE_BOOK_CONFIGS: the configs of the five whole books, by Internet
    Archive identifier, without `pdf`."""
    return WHOLE_BOOK_CONFIGS


@pytest.fixture(scope="session")
def whole_book_toml(
    books_dir: Path, whole_book_configs: frozendict[str, str]
) -> frozendict[str, str]:
    """The `book.toml` of each whole book, by Internet Archive identifier:
    its config of WHOLE_BOOK_CONFIGS, with the path of its PDF in
    `books_dir`."""
    # TOML basic strings take JSON's escapes, so json.dumps quotes any path.
    return frozendict(
        {
            book: f"pdf = {json.dumps(str(books_dir / f'{book}.pdf'))}\n{toml}"
            for book, toml in whole_book_configs.items()
        }
    )


# The workers of layout in the whole-book runs: the number of reocr spec
# section 7's timings and of its test that 1 worker and 6 give the same
# bytes, whatever the machine's default.
_WHOLE_BOOK_LAYOUT_WORKERS = 6


@pytest.fixture(scope="session")
def whole_book_run(
    whole_book_toml: frozendict[str, str], tmp_path_factory: pytest.TempPathFactory
) -> Callable[[str], BookFolder]:
    """A function that gives the book folder of a whole book, by Internet
    Archive identifier, with the files analyze, extract, layout (with 6
    workers) and structure wrote in it, run the
    first time a test asks for the book and kept for the session, so that
    every stage's whole_book tests share one run per book: layout re-reads
    Domesday and Gierke for about a minute each. Books may be asked for
    from several threads at once: a book's run holds that book's lock, so
    a second thread asking for it waits for the first run and gets its
    folder, and different books run side by side. A test reads these
    folders and never writes in them."""
    # The folders are made here, in one thread: pytest's tmp_path_factory
    # is not thread-safe, and its first mktemp from 6 threads at once
    # raised ValueError (17 November 2026).
    roots = frozendict(
        {book: tmp_path_factory.mktemp(book) for book in whole_book_toml}
    )
    # functools.cache alone lets two threads that miss the cache at once
    # both run the book, writing the same folder.
    locks = frozendict({book: threading.Lock() for book in whole_book_toml})

    def run(book: str) -> BookFolder:
        with locks[book]:
            return run_once(book)

    @functools.cache
    def run_once(book: str) -> BookFolder:
        folder = BookFolder(roots[book])
        folder.book_toml.write_text(whole_book_toml[book], encoding="utf-8")
        root = str(folder.root)
        main(["analyze", root])
        main(["extract", root])
        main(["layout", "--workers", str(_WHOLE_BOOK_LAYOUT_WORKERS), root])
        main(["structure", root])
        return folder

    return run


# The owner's two books, which are copyrighted: their whole_book tests
# count what galley gives and never quote their text.
# Structure spec section 21, "Their configs", as the survey of 17 November
# 2026 ran them; the pattern finds each PDF in the samples folder.
_OWNER_BOOK_PATTERNS = {"turney": "*Turney*.pdf", "haynes": "*Haynes*.pdf"}
_OWNER_BOOK_CONFIGS = {
    "turney": (
        "exclude_pages = [2, 3, 5, 9, 165, 168, 171, 306, 307, 308, 309]\n"
        "contents_pages = [10]\n"
    ),
    "haynes": (
        "exclude_pages = [0, 1, 3, 7, 11, 13, 329, 389, 431, 432, 434]\n"
        "contents_pages = [8]\n"
    ),
}


@pytest.fixture(scope="session")
def owner_book_toml(samples_dir: Path) -> Callable[[str], str]:
    """A function that gives the `book.toml` of one of the owner's books,
    by the name "turney" or "haynes": its PDF in the samples folder, its
    config of _OWNER_BOOK_CONFIGS, a made-up title and author, and `ocr =
    "trust"`. Skips the test when the book's PDF is not in the samples
    folder. Every whole_book test of the owner's books takes its config
    from here."""

    def toml(book: str) -> str:
        pdfs = sorted(samples_dir.glob(_OWNER_BOOK_PATTERNS[book]))
        if not pdfs:
            pytest.skip(
                f"no PDF matching {_OWNER_BOOK_PATTERNS[book]} in {samples_dir}"
            )
        return (
            f"pdf = {json.dumps(str(pdfs[0]))}\n"
            'title = "An owner\'s book"\n'
            'authors = ["An Author"]\n'
            'language = "en"\n'
            'ocr = "trust"\n'
            f"{_OWNER_BOOK_CONFIGS[book]}"
        )

    return toml


@pytest.fixture(scope="session")
def owner_book_run(
    owner_book_toml: Callable[[str], str], tmp_path_factory: pytest.TempPathFactory
) -> Callable[[str], BlocksFile]:
    """A function that gives blocks.json of one of the owner's books, by
    the name "turney" or "haynes", run from its PDF to structure the first
    time a test asks for it and kept for the session. Skips the test when
    the book's PDF is not in the samples folder. A book's run holds its
    lock, so that two threads asking for it share one run."""
    roots = {book: tmp_path_factory.mktemp(book) for book in _OWNER_BOOK_PATTERNS}
    locks = {book: threading.Lock() for book in _OWNER_BOOK_PATTERNS}

    def run(book: str) -> BlocksFile:
        toml = owner_book_toml(book)
        with locks[book]:
            return run_once(book, toml)

    @functools.cache
    def run_once(book: str, toml: str) -> BlocksFile:
        folder = BookFolder(roots[book])
        folder.book_toml.write_text(toml, encoding="utf-8")
        for stage in ("analyze", "extract", "layout", "structure"):
            main([stage, str(folder.root)])
        return read_blocks(folder.blocks_json)

    return run


@pytest.fixture(scope="session")
def check_epubs() -> Callable[..., None]:
    """A function that runs epubcheck on each EPUB it is given, all at once,
    and fails naming every EPUB epubcheck rejects, with epubcheck's report.

    epubcheck is Java, which starts in about a second and a half: measured
    on 16 November 2026 on an M5 Pro, one run took 1.35 s, two at once 1.6 s
    and five at once 2.5 s. A test with several EPUBs to check passes them
    in one call. Skips the test when epubcheck is missing.
    """
    _require_program("epubcheck")
    epubcheck = shutil.which("epubcheck")
    assert epubcheck is not None

    def check(*epubs: Path) -> None:
        with ThreadPoolExecutor(max_workers=len(epubs)) as pool:
            runs = tuple(
                pool.map(
                    lambda epub: subprocess.run(
                        [epubcheck, str(epub)],
                        capture_output=True,
                        text=True,
                        check=False,
                        timeout=60,
                    ),
                    epubs,
                )
            )
        rejected = tuple(
            f"{epub}:\n{run.stdout}{run.stderr}"
            for epub, run in zip(epubs, runs, strict=True)
            if run.returncode != 0
        )
        assert rejected == (), "\n".join(rejected)

    return check


# The Tesseract whose readings the excerpt and whole-book tests of
# re-reading hold as literals (docs/specs/reocr.md, section 9): Homebrew's,
# with its `eng` data, on 17 November 2026.
_TESSERACT_OF_THE_LITERALS = "tesseract 5.5.4"


@pytest.fixture(scope="session")
def tesseract_of_the_literals() -> None:
    """Skips the test, with the reason, when Tesseract is missing or is not
    the version whose readings the tests of re-reading hold as literals."""
    _require_program("tesseract")
    tesseract = shutil.which("tesseract")
    assert tesseract is not None
    # Tesseract prints its version on standard output or standard error,
    # depending on the build; both are read.
    version = subprocess.run(
        [tesseract, "--version"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=True,
        timeout=10,
    ).stdout.splitlines()[0]
    if version != _TESSERACT_OF_THE_LITERALS:
        pytest.skip(
            f"the readings of this test are those of {_TESSERACT_OF_THE_LITERALS}, "
            f"not of {version}"
        )


def _require_program(name: str) -> None:
    if shutil.which(name) is None:
        pytest.skip(f"{name} is not installed")


def pytest_runtest_setup(item: pytest.Item) -> None:
    for program in ("tesseract", "pandoc", "epubcheck"):
        if item.get_closest_marker(program) is not None:
            _require_program(program)


# The lists book of the markdown tests (structure spec sections 31 and 32):
# a printed contents with depths 1 and 2, a numbered list in its first
# chapter and a dash list, in the geometry of the owner's book, in its
# second. test_markdown_lists.py reads its parts and its EPUB, and
# test_epub.py validates the EPUB with epubcheck in one call with its own:
# a call of its own started Java again, about 1.5 s of the default run (18
# November 2026).
_LISTS_PDF_BYTES = b"%PDF-1.4 a stand-in: markdown reads only its hash"

LISTS_CONFIG = BookConfig(
    pdf=Path("/books/lists.pdf"),
    title="A Book",
    authors=("A. Author",),
    language=Language.EN,
)


def _lists_block(
    block_id: str,
    kind: BlockKind,
    text: str,
    *,
    level: int | None = None,
    label: str | None = None,
    page_number: str | None = None,
    heading_ref: str | None = None,
) -> Block:
    return Block(
        id=block_id,
        kind=kind,
        level=level,
        label=label,
        page_number=page_number,
        heading_ref=heading_ref,
        spans=(Span(text, Emphasis.NONE, None),),
        figure=None,
        origin=(Origin(int(block_id[3:7]), Box(10.0, 20.0, 300.0, 400.0)),),
    )


def _lists_file(blocks: tuple[Block, ...]) -> BlocksFile:
    return BlocksFile(
        source_pdf_sha256=hashlib.sha256(_LISTS_PDF_BYTES).hexdigest(),
        blocks=blocks,
        notes=(),
        removals=(),
        word_changes=(),
        page_numbers=(),
    )


def _lists_book_parts() -> frozendict[str, BlocksFile]:
    dash_list = _lists_file(
        (
            _lists_block(
                "b-p0016-001", BlockKind.PARAGRAPH, "The figure comes in six kinds:"
            ),
            *(
                _lists_block(
                    f"b-p0016-{number:03d}",
                    BlockKind.LIST_ITEM,
                    f"The kind {number}, as it stands.",
                    label="—",
                )
                for number in range(2, 8)
            ),
            _lists_block(
                "b-p0017-001", BlockKind.PARAGRAPH, "After the list, the text goes on."
            ),
        )
    )
    # A numbered list "1." to "5." whose third and fourth items have one line.
    numbered_list = _lists_file(
        (
            _lists_block("b-p0226-001", BlockKind.PARAGRAPH, "The steps are these:"),
            *(
                _lists_block(
                    f"b-p0226-{number + 1:03d}",
                    BlockKind.LIST_ITEM,
                    f"Step {number} is done.",
                    label=f"{number}.",
                )
                for number in range(1, 6)
            ),
        )
    )
    chapter_one = _lists_block(
        "b-p0036-001", BlockKind.HEADING, "The Old Masters", level=1
    )
    chapter_two = _lists_block(
        "b-p0050-001", BlockKind.HEADING, "New Engineers", level=1
    )
    contents_entries = (
        _lists_block("b-p0008-001", BlockKind.HEADING, "CONTENTS", level=1),
        _lists_block(
            "b-p0008-002",
            BlockKind.CONTENTS_ENTRY,
            "The Old Masters",
            level=1,
            label="1.",
            page_number="9",
            heading_ref="b-p0036-001",
        ),
        _lists_block(
            "b-p0008-003",
            BlockKind.CONTENTS_ENTRY,
            "Their workshops",
            level=2,
            page_number="12",
        ),
        _lists_block(
            "b-p0008-004",
            BlockKind.CONTENTS_ENTRY,
            "New Engineers",
            level=1,
            label="2.",
            page_number="23",
            heading_ref="b-p0050-001",
        ),
    )
    contents = _lists_file(
        (
            *contents_entries,
            chapter_one,
            _lists_block(
                "b-p0036-002", BlockKind.PARAGRAPH, "The masters worked alone."
            ),
            chapter_two,
            _lists_block(
                "b-p0050-002", BlockKind.PARAGRAPH, "The scientists worked together."
            ),
        )
    )
    epub_book = _lists_file(
        (
            *contents_entries,
            chapter_one,
            *numbered_list.blocks,
            chapter_two,
            *dash_list.blocks,
        )
    )
    return frozendict(
        {
            "dash_list": dash_list,
            "numbered_list": numbered_list,
            "contents": contents,
            "epub_book": epub_book,
        }
    )


@pytest.fixture(scope="session")
def lists_book() -> frozendict[str, BlocksFile]:
    """The parts of the lists book, by name: "dash_list", "numbered_list",
    "contents" (the printed contents and the two chapters it links to, a
    paragraph each), and "epub_book", the contents with the numbered list
    in the first chapter and the dash list in the second."""
    return _lists_book_parts()


@pytest.fixture(scope="session")
def lists_book_epub(
    tmp_path_factory: pytest.TempPathFactory, lists_book: frozendict[str, BlocksFile]
) -> BookFolder:
    """A book folder holding the lists book's "epub_book", with book.pdf,
    pages.json of 300 text pages, and the book.md and book.epub markdown
    and epub wrote from it. Built once per session; a test reads it and
    never writes in it. Skips every test that uses it when Pandoc is
    missing."""
    _require_program("pandoc")
    root = tmp_path_factory.mktemp("lists_book")
    pdf = root / "book.pdf"
    pdf.write_bytes(_LISTS_PDF_BYTES)
    folder = BookFolder(root)
    write_pages(
        folder.pages_json,
        PagesFile(
            source_pdf_sha256=hashlib.sha256(_LISTS_PDF_BYTES).hexdigest(),
            pages=tuple(
                PageInfo(
                    index=index,
                    width_pt=432.0,
                    height_pt=648.0,
                    kind=PageKind.TEXT,
                    text_source=TextSource.TEXT_LAYER,
                    text_layer_score=None,
                    exclude_regions=(),
                    figure_boxes=(),
                    blank_checked_by_ocr=False,
                )
                for index in range(300)
            ),
            ocr_audit=None,
        ),
    )
    write_blocks(folder.blocks_json, lists_book["epub_book"])
    config = replace(LISTS_CONFIG, pdf=pdf)
    markdown.run(folder, config)
    epub.run(folder, config)
    return folder
