"""Fixtures shared by every stage's tests.

The excerpt PDFs are public domain and committed under tests/fixtures/pdf/.
The whole books are ignored by git, so a worktree does not have them. They
are found through the GALLEY_SAMPLES environment variable, or else in
`samples/` of the main checkout, which git reports as the parent of the
common git directory. `scripts/fetch_samples.py` downloads them.

`excerpt_books` runs the stages once per session on a book folder for each
excerpt, so that the excerpt tests of every stage read the files of one run.
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from galley import analyze, extract
from galley.book_folder import BookFolder
from galley.config import read_config

EXCERPTS_DIR = Path(__file__).parent / "fixtures" / "pdf"

# The configs of spec section 9, "The end-to-end test", without `pdf`.
# Kadesh page 9 has no text layer, and its region holds the page number 81.
EXCERPT_CONFIGS = frozendict(
    {
        "kadesh_8-17": (
            'title = "The Battle of Kadesh"\n'
            'authors = ["J. H. Breasted"]\n'
            'language = "en"\n'
            "cover_page = 0\n"
            "exclude_pages = [9]\n"
            "exclude_regions = [{page = 0, box = [240, 620, 252, 632]}]\n"
        ),
        "gierke_86-93_270-271": (
            'title = "Political Theories of the Middle Age"\n'
            'authors = ["O. Gierke", "F. W. Maitland"]\n'
            'language = "en"\n'
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
def excerpt_books(
    tmp_path_factory: pytest.TempPathFactory, excerpt_pdf: frozendict[str, Path]
) -> frozendict[str, BookFolder]:
    """A book folder for each excerpt, by excerpt name, with its `book.toml`
    (the configs of spec section 9) and the files analyze and extract
    wrote.

    Session-scoped: the stages run once, also under --parallel-threads=8.
    A test reads these folders and never writes in them.
    """
    folders = {}
    for name, toml in EXCERPT_CONFIGS.items():
        folder = BookFolder(tmp_path_factory.mktemp(name))
        # A TOML literal string: no escapes, so any path but one with a quote.
        folder.book_toml.write_text(
            f"pdf = '{excerpt_pdf[name]}'\n{toml}", encoding="utf-8"
        )
        config = read_config(folder.book_toml)
        analyze.run(folder, config)
        extract.run(folder, config)
        folders[name] = folder
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


def _require_program(name: str) -> None:
    if shutil.which(name) is None:
        pytest.skip(f"{name} is not installed")


def pytest_runtest_setup(item: pytest.Item) -> None:
    for program in ("tesseract", "pandoc", "epubcheck"):
        if item.get_closest_marker(program) is not None:
            _require_program(program)
