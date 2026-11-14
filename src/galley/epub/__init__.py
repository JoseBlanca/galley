"""The epub stage: book.md to book.epub, built by Pandoc with galley's style
sheet and, when the config has a `cover_page`, the cover extract rendered.

The style sheet is `style.css`, a file of this package, empty in the
walking skeleton (spec section 8). The stage does not run epubcheck, which
only the tests use (architecture section 16).
"""

import logging
import shutil
import subprocess
from importlib.resources import as_file, files
from pathlib import Path
from typing import assert_never

from galley.book_folder import BookFolder, Stage, delete_stage_outputs
from galley.config import BookConfig
from galley.errors import ExternalProgramError, InputFileError
from galley.parallel import DEFAULT_WORKERS

__all__ = ["pandoc_arguments", "run"]

_logger = logging.getLogger(__name__)

# Spec section 8: Pandoc writes an EPUB of a whole book in seconds; two
# minutes means it hangs.
_PANDOC_TIMEOUT_S = 120
_STYLE_SHEET = "style.css"
# Spec section 8: the format fidelity.read_markdown reads book.md with, so
# that the EPUB is made from the reading the word check passed.
_INPUT_FORMAT = "markdown-smart-auto_identifiers"


def pandoc_arguments(
    folder: BookFolder, config: BookConfig, style_sheet: Path
) -> tuple[str, ...]:
    """The arguments Pandoc runs with, after the program's name: book.md
    read as Markdown with smart quotes and automatic heading ids off, written as EPUB 3 to book.epub
    with `style_sheet` in place of Pandoc's own, failing on any warning,
    and with images/cover.png as the cover when the config has a
    `cover_page`. The paths are written as given; run gives absolute ones.
    """
    cover = (
        ("--epub-cover-image", str(folder.cover_png))
        if config.cover_page is not None
        else ()
    )
    return (
        str(folder.book_md),
        "--from",
        _INPUT_FORMAT,
        "--to",
        "epub3",
        "--output",
        str(folder.book_epub),
        "--css",
        str(style_sheet),
        "--fail-if-warnings",
        *cover,
    )


def _check_inputs(folder: BookFolder, config: BookConfig) -> None:
    """Raise InputFileError, naming the stage to run, when book.md is
    missing, or images/cover.png when the config has a `cover_page`."""
    if not folder.book_md.is_file():
        message = (
            f"{folder.book_md} does not exist; run `galley2epub markdown` to write it"
        )
        raise InputFileError(message)
    if config.cover_page is not None and not folder.cover_png.is_file():
        message = (
            f"{folder.cover_png} does not exist and the config has cover_page = "
            f"{config.cover_page}; run `galley2epub extract` to render it"
        )
        raise InputFileError(message)


def _stderr_text(stderr: str | bytes | None) -> str:
    match stderr:
        case None:
            return ""
        case bytes():
            return stderr.decode("utf-8", errors="replace").strip()
        case str():
            return stderr.strip()
        case _:
            assert_never(stderr)


def _run_pandoc(arguments: tuple[str, ...]) -> None:
    """Run pandoc with `arguments`; ExternalProgramError, with Pandoc's
    standard error, when pandoc is missing, fails, warns or runs longer
    than _PANDOC_TIMEOUT_S."""
    pandoc = shutil.which("pandoc")
    if pandoc is None:
        message = "pandoc is not installed; install it with `brew install pandoc`"
        raise ExternalProgramError(message)
    try:
        subprocess.run(
            [pandoc, *arguments],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
            timeout=_PANDOC_TIMEOUT_S,
        )
    except subprocess.CalledProcessError as error:
        message = (
            f"pandoc exited with {error.returncode} writing the EPUB: "
            f"{_stderr_text(error.stderr)}"
        )
        raise ExternalProgramError(message) from error
    except subprocess.TimeoutExpired as error:
        message = (
            f"pandoc did not finish writing the EPUB in {_PANDOC_TIMEOUT_S} s: "
            f"{_stderr_text(error.stderr)}"
        )
        raise ExternalProgramError(message) from error


def run(
    folder: BookFolder, config: BookConfig, *, workers: int = DEFAULT_WORKERS
) -> None:
    """Write book.epub from book.md with Pandoc.

    Deletes book.epub first. Raises InputFileError when book.md is missing,
    or images/cover.png when the config has a `cover_page`, and
    ExternalProgramError when Pandoc is missing or fails. epub runs once,
    so `workers` is not used.
    """
    del workers  # every stage's run takes it; epub is not per page
    absolute = BookFolder(folder.root.resolve())
    delete_stage_outputs(absolute, Stage.EPUB)
    _check_inputs(absolute, config)
    # as_file gives a path on disk even if the package is not a folder.
    with as_file(files(__package__).joinpath(_STYLE_SHEET)) as style_sheet:
        _run_pandoc(pandoc_arguments(absolute, config, style_sheet))
    _logger.info("wrote %s", folder.book_epub)
