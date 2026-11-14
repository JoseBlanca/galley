"""The galley2epub command: `run` makes book.epub from a book folder through
every stage, and a stage's name runs that stage alone (spec section 9).

The command reads `book.toml` from the folder and calls each stage's `run`.
Before any stage, it checks that Pandoc is installed when a stage it runs
needs it. Errors propagate to `main`, which logs them and raises them
again (architecture section 14).
"""

import argparse
import logging
import shutil
import sys
from collections.abc import Sequence
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from galley import analyze, epub, extract, layout, markdown, structure
from galley.book_folder import BookFolder
from galley.config import BookConfig, read_config
from galley.errors import ConfigError, ExternalProgramError
from galley.parallel import DEFAULT_WORKERS

__all__ = ["main"]

_logger = logging.getLogger(__name__)


class _Command(StrEnum):
    """The subcommands of galley2epub: `run` and the stages, in pipeline
    order. The correct stage and `edits-from` are not in the skeleton."""

    RUN = "run"
    ANALYZE = "analyze"
    EXTRACT = "extract"
    LAYOUT = "layout"
    STRUCTURE = "structure"
    MARKDOWN = "markdown"
    EPUB = "epub"


class _StageRun(Protocol):
    def __call__(
        self, folder: BookFolder, config: BookConfig, *, workers: int = ...
    ) -> None: ...


# In the order `run` calls them.
_STAGE_RUNS: frozendict[_Command, _StageRun] = frozendict(
    {
        _Command.ANALYZE: analyze.run,
        _Command.EXTRACT: extract.run,
        _Command.LAYOUT: layout.run,
        _Command.STRUCTURE: structure.run,
        _Command.MARKDOWN: markdown.run,
        _Command.EPUB: epub.run,
    }
)

# markdown reads book.md back with Pandoc for the fidelity check; epub
# writes the EPUB with it.
_NEEDS_PANDOC = frozenset({_Command.RUN, _Command.MARKDOWN, _Command.EPUB})

_HELP = frozendict(
    {
        _Command.RUN: "every stage in order, from the PDF to book.epub",
        _Command.ANALYZE: "what each page is: pages.json",
        _Command.EXTRACT: "the words of every page and the cover: words.json, images/",
        _Command.LAYOUT: "the words grouped into regions and lines: lines.json",
        _Command.STRUCTURE: "the book as blocks: blocks.json",
        _Command.MARKDOWN: "the Markdown to proofread: book.md",
        _Command.EPUB: "the EPUB, built by Pandoc: book.epub",
    }
)


def _workers(text: str) -> int:
    """The value of --workers: a whole number of at least 1 (spec section 9)."""
    try:
        workers = int(text)
    except ValueError as error:
        message = f"must be a whole number, not {text!r}"
        raise argparse.ArgumentTypeError(message) from error
    if workers < 1:
        message = f"must be at least 1, not {workers}"
        raise argparse.ArgumentTypeError(message)
    return workers


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="galley2epub",
        description="Turns the PDF of a scanned book into an EPUB, "
        "from a book folder that holds its book.toml.",
    )
    subcommands = parser.add_subparsers(dest="command", required=True)
    for command in _Command:
        subcommand = subcommands.add_parser(
            command.value, help=_HELP[command], description=_HELP[command]
        )
        subcommand.add_argument(
            "folder", type=Path, help="the book folder, which holds book.toml"
        )
        subcommand.add_argument(
            "--workers",
            type=_workers,
            default=DEFAULT_WORKERS,
            help=f"threads for the per-page stages (default {DEFAULT_WORKERS})",
        )
    return parser


def _stages(command: _Command) -> tuple[_Command, ...]:
    """The stages a command runs, in order."""
    if command is _Command.RUN:
        return tuple(_STAGE_RUNS)
    return (command,)


def _require_pandoc(command: _Command) -> None:
    """Raise ExternalProgramError when the command needs Pandoc and it is
    not on the PATH."""
    if command in _NEEDS_PANDOC and shutil.which("pandoc") is None:
        message = (
            f"galley2epub {command} needs pandoc, which is not installed; "
            "install it with `brew install pandoc`"
        )
        raise ExternalProgramError(message)


def _run_command(command: _Command, folder: BookFolder, workers: int) -> None:
    _require_pandoc(command)
    config = read_config(folder.book_toml)
    if command is _Command.RUN and config.correct:
        message = (
            f"{folder.book_toml} has correct = true, but the walking skeleton "
            "has no correct stage; set correct = false"
        )
        raise ConfigError(message)
    for stage in _stages(command):
        _logger.info("running %s on %s", stage, folder.root)
        _STAGE_RUNS[stage](folder, config, workers=workers)


def main(argv: Sequence[str] | None = None) -> None:
    """Run galley2epub with the arguments `argv`, or those of the command
    line when it is None.

    argparse exits with code 2 on arguments it rejects. Any other error is
    logged and raised again, unchanged.
    """
    arguments = _parser().parse_args(argv)
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stderr,
        format="%(levelname)s %(name)s: %(message)s",
    )
    command = _Command(arguments.command)
    try:
        _run_command(command, BookFolder(arguments.folder), arguments.workers)
    # The one broad except of galley (coding skill, "Errors"): it only logs.
    except Exception as error:
        # Python prints the traceback once, when the error is raised again.
        _logger.error("galley2epub %s failed: %s", command, error)  # noqa: TRY400
        raise
