"""Fixtures shared by every stage's tests.

The excerpt PDFs are public domain and committed under tests/fixtures/pdf/.
The whole books are ignored by git, so a worktree does not have them. They
are found through the GALLEY_SAMPLES environment variable, or else in
`samples/` of the main checkout, which git reports as the parent of the
common git directory. `scripts/fetch_samples.py` downloads them.
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

EXCERPTS_DIR = Path(__file__).parent / "fixtures" / "pdf"


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
