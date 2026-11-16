"""Fixtures shared by every stage's tests.

The excerpt PDFs are public domain and committed under tests/fixtures/pdf/.
The whole books are ignored by git, so a worktree does not have them. They
are found through the GALLEY_SAMPLES environment variable, or else in
`samples/` of the main checkout, which git reports as the parent of the
common git directory. `scripts/fetch_samples.py` downloads them.

`excerpt_books` runs `galley2epub run` once per session on a book folder
for each excerpt, so that the excerpt tests of every stage read the files of
one run.
"""

import json
import os
import shutil
import subprocess
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from galley.book_folder import BookFolder
from galley.cli import main

EXCERPTS_DIR = Path(__file__).parent / "fixtures" / "pdf"

# The excerpts' runs go side by side, each with galley's own workers.
# Measured on 16 November 2026 on an M5 Pro, the eleven excerpts, as the
# setup time of excerpt_books: 7.5 to 8.1 s one after another, 6.1 to 6.3 s
# with 2 at once, 4.4 to 4.6 s with 6, 5.2 to 5.4 s with 11. The files
# written are the same bytes either way, but for book.epub's identifier
# and date, which differ between any two runs.
_EXCERPT_RUNS_AT_ONCE = 6

# The configs of spec section 9, "The end-to-end test", without `pdf`.
# Kadesh's region on page 0 holds the page number 81. Its page 9, without a
# text layer, is a plate, which analyze takes (plates spec section 6).
EXCERPT_CONFIGS = frozendict(
    {
        "kadesh_8-17": (
            'title = "The Battle of Kadesh"\n'
            'authors = ["J. H. Breasted"]\n'
            'language = "en"\n'
            "cover_page = 0\n"
            "exclude_regions = [{page = 0, box = [240, 620, 252, 632]}]\n"
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
    }
)


# The configs of the six whole books, by Internet Archive identifier,
# without `pdf`, `title` and `authors`: the one place the whole_book tests
# of every stage take them from. The four books of the evaluation set have
# the same pages as in evaluation/books.toml, which test_end_to_end.py
# checks.
#
# exclude_pages: the pages without a text layer that are not plates, which
# analyze refuses unless excluded (the evaluation books' as in
# evaluation/books.toml, Kadesh's and Gierke's as analyze listed them on 15
# November 2026), and the pages that analyze's plate rule takes wrongly
# (docs/specs/plates.md, section 2): Kadesh 0, the cover, and 49 and 65,
# backs of plates; Mariéjol 1 and 2, marbled endpapers, and 457 and 458,
# an endpaper and the library's card pocket; Mariéjol 0, its cover, has no
# layer. The plates without a text layer (Kadesh 17, 23, 35, 43, 57 and 69;
# Stubbs 9, 11, 52 and 54) are not excluded: analyze takes them as plates
# (16 November 2026).
#
# contents_pages: the printed table of contents, found on 16 November 2026
# by "CONTENTS" or "TABLE DES MATIERES" at the top of the page and checked
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
            'language = "en"\n'
            "exclude_pages = [0, 3, 4, 5, 7, 11, 15, 265, 274, 276, 279]\n"
            "contents_pages = [14]\n"
        ),
        "earlyplantagenet01stub": (
            'language = "en"\n'
            "exclude_pages = [0, 2, 3, 4, 5, 8, 10, 53, 55, "
            "338, 339, 340, 341, 342, 343]\n"
            "contents_pages = [14, 15, 16]\n"
        ),
        "domesdaybook00maituoft": (
            'language = "en"\n'
            "exclude_pages = [0, 1, 2, 3, 5, 6, 7, 38, 41, 554, 555, 557]\n"
            "contents_pages = [14, 15, 16, 17, 18, 19, 20]\n"
        ),
        "catherinedemedic00mariuoft": (
            'language = "fr"\n'
            "exclude_pages = [0, 1, 2, 3, 4, 5, 17, 449, 451, 453, 454, 455, 456, "
            "457, 458]\n"
            "contents_pages = [450]\n"
        ),
        "battleofkadeshst00breauoft": (
            'language = "en"\n'
            "exclude_pages = [0, 1, 2, 3, 49, 65, 70, 71, 72, 73, 75]\n"
            "plate_pages = [23]\n"
        ),
        "politicaltheorie00gieruoft": (
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
    and the excerpts' runs go side by side in threads.
    A test reads these folders and never writes in them. Skips every test
    that uses it when Pandoc is missing, which markdown and epub need.
    """
    _require_program("pandoc")
    folders = {
        name: BookFolder(tmp_path_factory.mktemp(name)) for name in excerpt_book_toml
    }
    for name, folder in folders.items():
        folder.book_toml.write_text(excerpt_book_toml[name], encoding="utf-8")
    with ThreadPoolExecutor(max_workers=_EXCERPT_RUNS_AT_ONCE) as pool:
        # list() waits for every run and raises the first run's error.
        list(pool.map(lambda folder: main(["run", str(folder.root)]), folders.values()))
    return frozendict(folders)


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
    """WHOLE_BOOK_CONFIGS: the configs of the six whole books, by Internet
    Archive identifier, without `pdf`, `title` and `authors`."""
    return WHOLE_BOOK_CONFIGS


@pytest.fixture(scope="session")
def whole_book_toml(
    books_dir: Path, whole_book_configs: frozendict[str, str]
) -> frozendict[str, str]:
    """The `book.toml` of each whole book, by Internet Archive identifier:
    its config of WHOLE_BOOK_CONFIGS, with the path of its PDF in
    `books_dir`, the identifier as its title and one made-up author."""
    # TOML basic strings take JSON's escapes, so json.dumps quotes any path.
    return frozendict(
        {
            book: (
                f"pdf = {json.dumps(str(books_dir / f'{book}.pdf'))}\n"
                f"title = {json.dumps(book)}\n"
                'authors = ["An Author"]\n'
                f"{toml}"
            )
            for book, toml in whole_book_configs.items()
        }
    )


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


def _require_program(name: str) -> None:
    if shutil.which(name) is None:
        pytest.skip(f"{name} is not installed")


def pytest_runtest_setup(item: pytest.Item) -> None:
    for program in ("tesseract", "pandoc", "epubcheck"):
        if item.get_closest_marker(program) is not None:
            _require_program(program)
