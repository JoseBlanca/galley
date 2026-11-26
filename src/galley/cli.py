"""The galley2epub command: `run` makes book.epub from a book folder through
every stage, and a stage's name runs that stage alone (spec section 9).

The command reads `book.toml` from the folder and calls each stage's `run`.
`run` runs the correct stage only when the config has `correct = true`.
Before any stage, it checks that LM Studio answers and has the config's
models when the command runs correct (docs/specs/correct.md, section 4),
and that Pandoc is installed when a stage it runs needs it; Tesseract's tools when
analyze or structure runs, or layout re-reads small print, and the word
list of the book's language is not cached; Tesseract when layout runs
and the config's `ocr` is `verify`; and Tesseract when analyze or extract
runs and the config's `ocr` is `redo`, under which extract reads every
text page with it (architecture section 7b).
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

from galley import (
    analyze,
    correct,
    epub,
    extract,
    layout,
    markdown,
    structure,
    wordlist,
)
from galley.book_folder import BookFolder
from galley.config import BookConfig, OcrMode, read_config, tesseract_language
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
    whether it calls Pandoc, whether it needs the word list of the book's
    language, which Tesseract's tools extract the first time, and whether
    it reads with Tesseract when the config's `ocr` is `verify`, as layout
    re-reads small print (docs/specs/reocr.md, section 3), needing the
    word list too; and whether it needs Tesseract
    under `ocr = "redo"`, as extract does to read every text page and
    analyze, which runs before it (architecture section 7b); and whether
    `run` runs it only when the config has `correct = true`, as the correct
    stage."""

    name: str
    help: str
    run: _StageRun
    needs_pandoc: bool
    needs_word_list: bool
    reads_with_tesseract: bool
    needs_tesseract_under_redo: bool
    only_when_correct: bool = False


# The stages in the order `run` calls them; `edits-from` is not built. markdown reads book.md back with
# Pandoc for the fidelity check; epub writes the EPUB with it.
_STAGES: tuple[_Stage, ...] = (
    _Stage(
        name="analyze",
        help="what each page is: pages.json",
        run=analyze.run,
        needs_pandoc=False,
        needs_word_list=True,
        reads_with_tesseract=False,
        needs_tesseract_under_redo=True,
    ),
    _Stage(
        name="extract",
        help="the words of every page and the cover: words.json, images/",
        run=extract.run,
        needs_pandoc=False,
        needs_word_list=False,
        reads_with_tesseract=False,
        needs_tesseract_under_redo=True,
    ),
    _Stage(
        name="layout",
        help="the words grouped into regions and lines: lines.json",
        run=layout.run,
        needs_pandoc=False,
        needs_word_list=False,
        reads_with_tesseract=True,
        needs_tesseract_under_redo=False,
    ),
    _Stage(
        name="structure",
        help="the book as blocks: blocks.json",
        run=structure.run,
        needs_pandoc=False,
        needs_word_list=True,
        reads_with_tesseract=False,
        needs_tesseract_under_redo=False,
    ),
    _Stage(
        name="correct",
        help="a local vision model's fixes to the words: edits/correct.jsonl",
        run=correct.run,
        needs_pandoc=False,
        needs_word_list=True,
        reads_with_tesseract=False,
        needs_tesseract_under_redo=False,
        only_when_correct=True,
    ),
    _Stage(
        name="markdown",
        help="the Markdown to proofread: book.md",
        run=markdown.run,
        needs_pandoc=True,
        needs_word_list=False,
        reads_with_tesseract=False,
        needs_tesseract_under_redo=False,
    ),
    _Stage(
        name="epub",
        help="the EPUB, built by Pandoc: book.epub",
        run=epub.run,
        needs_pandoc=True,
        needs_word_list=False,
        reads_with_tesseract=False,
        needs_tesseract_under_redo=False,
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


def _stages_of(command: str, config: BookConfig) -> tuple[_Stage, ...]:
    """The stages a command runs, in order: under run, correct only when the
    config has `correct = true`."""
    if command == _RUN:
        return tuple(
            stage for stage in _STAGES if config.correct or not stage.only_when_correct
        )
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
    stages: tuple[_Stage, ...], config: BookConfig, folder: BookFolder
) -> None:
    """ExternalProgramError when the correct stage runs on a book folder
    without kept answers, answers/, and LM Studio does not answer or lacks a
    model of the config (with kept answers the stage checks before its first
    request, and not at all when it sends none: correct spec, section 4); when a stage needs Pandoc and it is not on the PATH (spec section 9);
    when analyze or structure, or layout re-reading small print, needs
    Tesseract's tools to extract the word list; or when layout reads with
    Tesseract, which it does only when the config's `ocr` is `verify`, or
    analyze or extract runs under `ocr = "redo"`, and it is not on the
    PATH."""
    if (
        any(stage.only_when_correct for stage in stages)
        and not folder.answers_dir.exists()
    ):
        correct.check_server(config)
    if any(stage.needs_pandoc for stage in stages) and shutil.which("pandoc") is None:
        message = "pandoc is not installed; install it with `brew install pandoc`"
        raise ExternalProgramError(message)
    needing_word_list = tuple(
        stage.name
        for stage in stages
        if stage.needs_word_list
        or (stage.reads_with_tesseract and config.ocr is OcrMode.VERIFY)
    )
    if needing_word_list:
        _check_word_list_tools(config, needing_word_list[0])
    reading = tuple(stage.name for stage in stages if stage.reads_with_tesseract)
    if reading and config.ocr is OcrMode.VERIFY and shutil.which("tesseract") is None:
        message = (
            f"tesseract is not installed; {reading[0]} reads small print with it "
            f'when the config has ocr = "verify", the default: install it with '
            "`brew install tesseract`"
        )
        raise ExternalProgramError(message)
    reading_under_redo = tuple(
        stage.name for stage in stages if stage.needs_tesseract_under_redo
    )
    if (
        reading_under_redo
        and config.ocr is OcrMode.REDO
        and shutil.which("tesseract") is None
    ):
        message = (
            f'tesseract is not installed; with ocr = "redo" {reading_under_redo[0]} '
            "needs it, as extract reads every text page with it: install it with "
            "`brew install tesseract`"
        )
        raise ExternalProgramError(message)


def _check_word_list_tools(config: BookConfig, first_stage: str) -> None:
    """ExternalProgramError when the word list of the book's language is
    not in the word list's cache folder and Tesseract's tools are not on
    the PATH (structure spec, section 8; plates spec, section 4), naming
    `first_stage`, the first stage to run that needs the list."""
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
        f"{names} {verb} not installed; {first_stage} needs {pronoun} once to "
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
        stages = _stages_of(command, config)
        _check_before_any_stage(stages, config, folder)
        for stage in stages:
            running = stage.name
            _logger.info("running %s on %s", stage.name, folder.root)
            stage.run(folder, config, workers=arguments.workers)
    # The one broad except of galley (coding skill, "Errors"): it only logs.
    except Exception as error:
        # Python prints the traceback once, when the error is raised again.
        _logger.error("%s: %s", _failed(command, running), error)  # noqa: TRY400
        raise
