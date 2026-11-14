"""Fixtures shared by every stage's tests.

The sample PDFs are copyrighted and ignored by git, so a worktree does not
have them. They are found through the GALLEY_SAMPLES environment variable,
or else in `samples/` of the main checkout, which git reports as the parent
of the common git directory.
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest


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
def samples_dir() -> Path:
    """The directory of the sample PDFs; skips the test when it is missing."""
    env = os.environ.get("GALLEY_SAMPLES")
    path = Path(env) if env is not None and env != "" else _main_checkout_samples()
    if not any(path.glob("*.pdf")):
        pytest.skip(f"no sample PDFs found (looked in {path})")
    return path


def _require_program(name: str) -> None:
    if shutil.which(name) is None:
        pytest.skip(f"{name} is not installed")


def pytest_runtest_setup(item: pytest.Item) -> None:
    for program in ("tesseract", "pandoc"):
        if item.get_closest_marker(program) is not None:
            _require_program(program)
