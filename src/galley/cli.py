"""The galley2epub command: `run` makes book.epub from a book folder through
every stage, and a stage's name runs that stage alone (spec section 9).

The command reads `book.toml` from the folder and calls each stage's `run`.
`run` also takes the book's PDF with `--title`, `--author` and
`--language`, and then first writes the book folder beside the PDF and
its `book.toml`, or reuses an equal one (architecture section 14).
`run` runs the correct stage only when the config has `correct = true`,
unless its flag `--correct` or `--no-correct` decides for that run
(architecture section 14).
Before any stage, it checks that LM Studio answers and has the config's
models when the command runs correct (docs/specs/correct.md, section 4),
and that Pandoc is installed when a stage it runs needs it; Tesseract
whenever analyze runs, which reads the pages without a text layer with
it (analyze spec section 7), before any other check for Tesseract or its
tools; Tesseract's tools when analyze or structure runs, or layout
re-reads small print, and the word list of the book's language is not
cached; Tesseract when layout runs and the config's `ocr` is `verify`;
and Tesseract when extract runs and the config's `ocr` is `redo`, under
which extract reads every text page with it (architecture section 7b).
Errors propagate to `main`, which logs them and raises them again
(architecture section 14).
"""

import argparse
import logging
import shutil
import sys
from collections.abc import Sequence
from dataclasses import dataclass, replace
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
from galley.config import (
    BookConfig,
    Language,
    OcrMode,
    book_toml_text,
    read_config,
    tesseract_language,
)
from galley.errors import ConfigError, ExternalProgramError
from galley.parallel import DEFAULT_WORKERS

__all__ = ["main"]

_logger = logging.getLogger(__name__)

_RUN = "run"
_RUN_HELP = "every stage in order, from the PDF to book.epub"
_PDF_SUFFIX = ".pdf"
_PDF_OPTIONS = ("--title", "--author", "--language")


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
    word list too; whether it reads the pages without a text layer with
    Tesseract whatever the config's `ocr`, as analyze does (analyze spec
    section 7); whether it needs Tesseract
    under `ocr = "redo"`, as extract does to read every text page
    (architecture section 7b); and whether
    `run` runs it only when the config has `correct = true`, as the correct
    stage."""

    name: str
    help: str
    run: _StageRun
    needs_pandoc: bool
    needs_word_list: bool
    reads_with_tesseract: bool
    reads_pages_without_layer: bool
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
        reads_pages_without_layer=True,
        needs_tesseract_under_redo=False,
    ),
    _Stage(
        name="extract",
        help="the words of every page and the cover: words.json, images/",
        run=extract.run,
        needs_pandoc=False,
        needs_word_list=False,
        reads_with_tesseract=False,
        reads_pages_without_layer=False,
        needs_tesseract_under_redo=True,
    ),
    _Stage(
        name="layout",
        help="the words grouped into regions and lines: lines.json",
        run=layout.run,
        needs_pandoc=False,
        needs_word_list=False,
        reads_with_tesseract=True,
        reads_pages_without_layer=False,
        needs_tesseract_under_redo=False,
    ),
    _Stage(
        name="structure",
        help="the book as blocks: blocks.json",
        run=structure.run,
        needs_pandoc=False,
        needs_word_list=True,
        reads_with_tesseract=False,
        reads_pages_without_layer=False,
        needs_tesseract_under_redo=False,
    ),
    _Stage(
        name="correct",
        help="a local vision model's fixes to the words: edits/correct.jsonl",
        run=correct.run,
        needs_pandoc=False,
        needs_word_list=True,
        reads_with_tesseract=False,
        reads_pages_without_layer=False,
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
        reads_pages_without_layer=False,
        needs_tesseract_under_redo=False,
    ),
    _Stage(
        name="epub",
        help="the EPUB, built by Pandoc: book.epub",
        run=epub.run,
        needs_pandoc=True,
        needs_word_list=False,
        reads_with_tesseract=False,
        reads_pages_without_layer=False,
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
        if name == _RUN:
            subcommand.add_argument(
                "path",
                type=Path,
                help="the book folder, which holds book.toml, or the book's PDF "
                "for a simple book",
            )
        else:
            subcommand.add_argument(
                "path",
                metavar="folder",
                type=Path,
                help="the book folder, which holds book.toml",
            )
        subcommand.add_argument(
            "--workers",
            type=_workers,
            default=DEFAULT_WORKERS,
            help=f"threads for the per-page stages (default {DEFAULT_WORKERS})",
        )
        if name == _RUN:
            subcommand.add_argument(
                "--correct",
                action=argparse.BooleanOptionalAction,
                default=None,
                help="run the correct stage, or with --no-correct skip it, "
                "whatever book.toml's correct says (default: as book.toml says)",
            )
            subcommand.add_argument(
                "--title", help="with a PDF: the book's title (required)"
            )
            subcommand.add_argument(
                "--author",
                action="append",
                dest="authors",
                help="with a PDF: an author, once for each in printed order (required)",
            )
            subcommand.add_argument(
                "--language",
                choices=tuple(language.value for language in Language),
                help="with a PDF: the book's language (required)",
            )
    # The other subcommands have no flag, and so the config decides; and
    # they take only a book folder.
    parser.set_defaults(correct=None, title=None, authors=None, language=None)
    return parser


@dataclass(frozen=True, slots=True)
class _PdfOptions:
    """The options of run that give a PDF's book.toml; None when not given."""

    title: str | None
    authors: tuple[str, ...] | None
    language: str | None


def _given(pdf_options: _PdfOptions) -> tuple[str, ...]:
    """The options of `pdf_options` given, by their names on the command line."""
    values = (pdf_options.title, pdf_options.authors, pdf_options.language)
    return tuple(
        option
        for option, value in zip(_PDF_OPTIONS, values, strict=True)
        if value is not None
    )


def _with_correct_flag(config: BookConfig, *, correct_flag: bool | None) -> BookConfig:
    """The config a run uses: `config` with its `correct` replaced by the
    flag of run, `--correct` (True) or `--no-correct` (False), and `config`
    itself when no flag was given (None)."""
    if correct_flag is None:
        return config
    return replace(config, correct=correct_flag)


def _stages_of(command: str, config: BookConfig) -> tuple[_Stage, ...]:
    """The stages a command runs, in order: under run, correct only when the
    config has `correct = true`."""
    if command == _RUN:
        return tuple(
            stage for stage in _STAGES if config.correct or not stage.only_when_correct
        )
    return tuple(stage for stage in _STAGES if stage.name == command)


def _is_pdf(path: Path) -> bool:
    """Whether the name of `path` ends in .pdf, in any case."""
    return path.suffix.lower() == _PDF_SUFFIX


def _book_folder(command: str, path: Path, pdf_options: _PdfOptions) -> BookFolder:
    """The book folder of `command` at `path`: under run, when `path` is
    a PDF, the folder beside it with its book.toml, made from
    `pdf_options` (architecture section 14); otherwise `path` itself.
    ConfigError when `path` is another file, a missing PDF, or a folder
    given with options of a PDF."""
    if command == _RUN and path.is_file() and _is_pdf(path):
        return _folder_of_pdf(path, pdf_options)
    if command == _RUN and (path.is_file() or (_is_pdf(path) and not path.exists())):
        problem = "is a file but not a PDF" if path.is_file() else "does not exist"
        message = (
            f"{path} {problem}; run takes the book's PDF or its book folder, "
            "which holds book.toml"
        )
        raise ConfigError(message)
    given = _given(pdf_options)
    if given:
        message = (
            f"{given[0]} is taken only with a PDF; the settings of the book "
            f"folder {path} are in its book.toml"
        )
        raise ConfigError(message)
    if path.is_file():
        message = (
            f"{path} is a file; the argument must be the book folder, "
            "which holds book.toml"
        )
        raise ConfigError(message)
    return BookFolder(path)


def _required[T: (str, tuple[str, ...])](value: T | None, option: str) -> T:
    """The value of an option the PDF form needs; ConfigError when it is
    missing or empty."""
    if value is None:
        message = f"{option} is missing; run on a PDF needs {', '.join(_PDF_OPTIONS)}"
        raise ConfigError(message)
    if len(value) == 0:
        message = f"{option} must not be empty"
        raise ConfigError(message)
    return value


def _folder_of_pdf(pdf: Path, pdf_options: _PdfOptions) -> BookFolder:
    """The book folder of `pdf`, beside it and named after it without its
    extension, holding a book.toml with the four keys of `pdf_options`:
    written when the folder has none, reused when it reads to the same
    config, never overwritten (architecture section 14)."""
    title = _required(pdf_options.title, "--title")
    authors = _required(pdf_options.authors, "--author")
    for author in authors:
        _required(author, "--author")
    language = Language(_required(pdf_options.language, "--language"))
    folder = BookFolder(pdf.parent / pdf.stem)
    if folder.root.exists() and not folder.root.is_dir():
        message = (
            f"{folder.root} is a file, not the book folder of {pdf}; "
            "move it away, or rename the PDF"
        )
        raise ConfigError(message)
    wanted = BookConfig(
        pdf=pdf.resolve(), title=title, authors=authors, language=language
    )
    if folder.book_toml.exists():
        if read_config(folder.book_toml) != wanted:
            message = (
                f"{folder.root} already holds a different book.toml; run "
                f"galley2epub run on {folder.root} instead, or remove its book.toml"
            )
            raise ConfigError(message)
        _logger.info("using %s, which equals the options", folder.book_toml)
        return folder
    folder.root.mkdir(exist_ok=True)
    folder.book_toml.write_text(
        book_toml_text(
            pdf=f"../{pdf.name}", title=title, authors=authors, language=language
        ),
        encoding="utf-8",
    )
    _logger.info("wrote %s", folder.book_toml)
    return folder


def _check_before_any_stage(
    stages: tuple[_Stage, ...], config: BookConfig, folder: BookFolder
) -> None:
    """ExternalProgramError when the correct stage runs on a book folder
    without kept answers, answers/, and LM Studio does not answer or lacks a
    model of the config (with kept answers the stage checks before its first
    request, and not at all when it sends none: correct spec, section 4); when a stage needs Pandoc and it is not on the PATH (spec section 9);
    when analyze runs and Tesseract is not on the PATH, whatever the
    config's `ocr` (analyze spec section 7), checked before Tesseract's
    tools; when analyze or structure, or layout re-reading small print, needs
    Tesseract's tools to extract the word list; or when layout reads with
    Tesseract, which it does only when the config's `ocr` is `verify`, or
    extract runs under `ocr = "redo"`, and it is not on the PATH."""
    if (
        any(stage.only_when_correct for stage in stages)
        and not folder.answers_dir.exists()
    ):
        correct.check_server(config)
    if any(stage.needs_pandoc for stage in stages) and shutil.which("pandoc") is None:
        message = "pandoc is not installed; install it with `brew install pandoc`"
        raise ExternalProgramError(message)
    reading_pages_without_layer = tuple(
        stage.name for stage in stages if stage.reads_pages_without_layer
    )
    if reading_pages_without_layer and shutil.which("tesseract") is None:
        message = (
            f"tesseract is not installed; {reading_pages_without_layer[0]} reads the pages "
            "without a text layer with it: install it with `brew install tesseract`"
        )
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
        authors = arguments.authors
        folder = _book_folder(
            command,
            arguments.path,
            _PdfOptions(
                title=arguments.title,
                authors=None if authors is None else tuple(authors),
                language=arguments.language,
            ),
        )
        config = _with_correct_flag(
            read_config(folder.book_toml), correct_flag=arguments.correct
        )
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
