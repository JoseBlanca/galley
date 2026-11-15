"""The galley2epub command: `run` makes book.epub from a book folder through
every stage, and a stage's name runs that stage alone (spec section 9).

The command reads `book.toml` from the folder and calls each stage's `run`.
Before any stage, it refuses `correct = true` under `run` and checks that
Pandoc is installed when a stage it runs needs it, and Tesseract when
structure runs and the word list of the book's language is not cached.
Errors propagate to `main`, which logs them and raises them again
(architecture section 14).
"""

import argparse
import logging
import shutil
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from galley import analyze, epub, extract, layout, markdown, structure, wordlist
from galley.book_folder import BookFolder
from galley.config import BookConfig, read_config, tesseract_language
from galley.errors import ConfigError, ExternalProgramError
from galley.parallel import DEFAULT_WORKERS

__all__ = ["main"]

_logger = logging.getLogger(__name__)

_RUN = "run"
_RUN_HELP = "every stage in order, from the PDF to book.epub"


class _StageRun(Protocol):
    def __call__(
        self, folder: BookFolder, config: BookConfig, *, workers: int = ...
    ) -> None: ...


@dataclass(frozen=True, slots=True, kw_only=True)
class _Stage:
    """A stage the command runs: its subcommand, its help, its `run`,
    whether it calls Pandoc, and whether it needs the word list of the
    book's language, which Tesseract's tools extract the first time."""

    name: str
    help: str
    run: _StageRun
    needs_pandoc: bool
    needs_word_list: bool


# The stages in the order `run` calls them. The correct stage and
# `edits-from` are not in the skeleton. markdown reads book.md back with
# Pandoc for the fidelity check; epub writes the EPUB with it.
_STAGES: tuple[_Stage, ...] = (
    _Stage(
        name="analyze",
        help="what each page is: pages.json",
        run=analyze.run,
        needs_pandoc=False,
        needs_word_list=False,
    ),
    _Stage(
        name="extract",
        help="the words of every page and the cover: words.json, images/",
        run=extract.run,
        needs_pandoc=False,
        needs_word_list=False,
    ),
    _Stage(
        name="layout",
        help="the words grouped into regions and lines: lines.json",
        run=layout.run,
        needs_pandoc=False,
        needs_word_list=False,
    ),
    _Stage(
        name="structure",
        help="the book as blocks: blocks.json",
        run=structure.run,
        needs_pandoc=False,
        needs_word_list=True,
    ),
    _Stage(
        name="markdown",
        help="the Markdown to proofread: book.md",
        run=markdown.run,
        needs_pandoc=True,
        needs_word_list=False,
    ),
    _Stage(
        name="epub",
        help="the EPUB, built by Pandoc: book.epub",
        run=epub.run,
        needs_pandoc=True,
        needs_word_list=False,
    ),
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
    commands = ((_RUN, _RUN_HELP), *((stage.name, stage.help) for stage in _STAGES))
    for name, help_text in commands:
        subcommand = subcommands.add_parser(name, help=help_text, description=help_text)
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


def _stages_of(command: str) -> tuple[_Stage, ...]:
    """The stages a command runs, in order."""
    if command == _RUN:
        return _STAGES
    return tuple(stage for stage in _STAGES if stage.name == command)


def _book_folder(path: Path) -> BookFolder:
    """The book folder at `path`; ConfigError when `path` is a file."""
    if path.is_file():
        message = (
            f"{path} is a file; the argument must be the book folder, "
            "which holds book.toml"
        )
        raise ConfigError(message)
    return BookFolder(path)


def _check_before_any_stage(
    command: str, stages: tuple[_Stage, ...], folder: BookFolder, config: BookConfig
) -> None:
    """ConfigError for `correct = true` under run, then ExternalProgramError
    when a stage needs Pandoc and it is not on the PATH (spec section 9),
    or structure needs Tesseract's tools to extract the word list."""
    if command == _RUN and config.correct:
        message = (
            f"{folder.book_toml} has correct = true, but the walking skeleton "
            "has no correct stage; set correct = false"
        )
        raise ConfigError(message)
    if any(stage.needs_pandoc for stage in stages) and shutil.which("pandoc") is None:
        message = "pandoc is not installed; install it with `brew install pandoc`"
        raise ExternalProgramError(message)
    if any(stage.needs_word_list for stage in stages):
        _check_word_list_tools(config)


def _check_word_list_tools(config: BookConfig) -> None:
    """ExternalProgramError when the word list of the book's language is
    not in the word list's cache folder and Tesseract's tools are not on
    the PATH (structure spec, section 8)."""
    # The cache folder is read here, as structure.run reads it, so that both
    # look at the same folder and a test can point it elsewhere.
    missing = wordlist.missing_tools(config.language, wordlist.DEFAULT_CACHE_DIR)
    if not missing:
        return
    names = (
        missing[0]
        if len(missing) == 1
        else ", ".join(missing[:-1]) + " and " + missing[-1]
    )
    verb, pronoun = ("is", "it") if len(missing) == 1 else ("are", "them")
    code = tesseract_language(config.language)
    message = (
        f"{names} {verb} not installed; structure needs {pronoun} once to "
        f"extract the word list of {code} from Tesseract's data: install "
        f"{pronoun} with `brew install tesseract`"
    )
    raise ExternalProgramError(message)


def _failed(command: str, stage: str | None) -> str:
    """What the logged error line starts with: the command and, under run,
    the stage that was running."""
    if stage is None or stage == command:
        return f"galley2epub {command} failed"
    return f"galley2epub {command} failed in {stage}"


def main(argv: Sequence[str] | None = None) -> None:
    """Run galley2epub with the arguments `argv`, or those of the command
    line when it is None.

    argparse exits with code 2 on arguments it rejects. Any other error is
    logged, with the stage that was running, and raised again unchanged.
    """
    arguments = _parser().parse_args(argv)
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stderr,
        format="%(levelname)s %(name)s: %(message)s",
    )
    command = str(arguments.command)
    running: str | None = None
    try:
        folder = _book_folder(arguments.folder)
        config = read_config(folder.book_toml)
        stages = _stages_of(command)
        _check_before_any_stage(command, stages, folder, config)
        for stage in stages:
            running = stage.name
            _logger.info("running %s on %s", stage.name, folder.root)
            stage.run(folder, config, workers=arguments.workers)
    # The one broad except of galley (coding skill, "Errors"): it only logs.
    except Exception as error:
        # Python prints the traceback once, when the error is raised again.
        _logger.error("%s: %s", _failed(command, running), error)  # noqa: TRY400
        raise
