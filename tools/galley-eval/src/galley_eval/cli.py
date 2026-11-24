"""The galley-eval command: `run`, `compare` and `summary` (spec section 9).

- `run [<name> ...]` writes each book's `book.toml` from
  `evaluation/books.toml` into `runs/evaluation/<name>/`, runs
  `galley2epub run` on that folder as a separate process, records the
  commit of galley that made the files, then compares;
- `compare [<name> ...]` compares the files already in the book folders;
- `summary` rewrites `runs/evaluation/summary.md` from the scorecards.

With no name, every book of `evaluation/books.toml`. The paths are those of
the repository the command is run in (git's top level): its
`evaluation/books.toml` and its `runs/evaluation/`. The PDFs and HTML
editions are those `scripts/fetch_samples.py` downloads, in
`samples/public_domain/` of the folder named by GALLEY_SAMPLES, or else of
the main checkout, which git reports as the parent of the common git
directory, as the tests find them.

A book that fails, in galley or in the comparison, is reported with its
error, recorded so that the books' summary shows it failed, and the others
go on; the command then exits with code 1. galley's own errors, raised
when the comparison reads its files, are caught by galley's GalleyError,
the one module of galley outside spec section 9's list that the tool
imports, since they are the errors a book's files can cause.
"""

import argparse
import datetime
import importlib.metadata
import json
import logging
import os
import shutil
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import assert_never

from galley.book_folder import BookFolder
from galley.errors import GalleyError
from galley_eval.books import EvaluationBook, read_books
from galley_eval.errors import EvaluationError, GalleyRunError
from galley_eval.evaluate import Evaluation, evaluate
from galley_eval.output import (
    RunInfo,
    read_galley_commit,
    write_books_summary,
    write_evaluation,
    write_failure,
    write_galley_commit,
)

__all__ = [
    "Subcommand",
    "book_toml",
    "compare_books",
    "galley_error_lines",
    "main",
    "run_galley",
]


class Subcommand(StrEnum):
    """The subcommands of galley-eval."""

    RUN = "run"
    COMPARE = "compare"
    SUMMARY = "summary"


_BOOK_NAMES_HELP = "names of books in evaluation/books.toml; all books when none"

_HELP = frozendict(
    {
        Subcommand.RUN: "run galley on each book, then compare",
        Subcommand.COMPARE: "compare the files already in the book folders",
        Subcommand.SUMMARY: "rewrite runs/evaluation/summary.md from the scorecards",
    }
)

# A whole book took galley 15.5 s at most on an M5 Pro (spec section 2 and
# the first run); ten minutes means a hang. Guessed from that measurement.
_GALLEY_TIMEOUT_S = 600
_GIT_TIMEOUT_S = 10

# galley logs the error that stopped it on a line starting with this, which
# names the stage (galley.cli).
_GALLEY_ERROR_PREFIX = "ERROR "

_logger = logging.getLogger(__name__)

type RunGalley = Callable[[BookFolder], None]
type Compare = Callable[[EvaluationBook, BookFolder, Path], Evaluation]


@dataclass(frozen=True, slots=True, kw_only=True)
class _Repository:
    """The repository the command runs in: git, found once, its top level
    and its commit."""

    git: str
    root: Path
    commit: str


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="galley-eval",
        description="Compares galley's output for the books of the evaluation "
        "set with their Project Gutenberg editions.",
    )
    subcommands = parser.add_subparsers(dest="command", required=True)
    for subcommand in Subcommand:
        sub = subcommands.add_parser(
            subcommand.value, help=_HELP[subcommand], description=_HELP[subcommand]
        )
        match subcommand:
            case Subcommand.RUN | Subcommand.COMPARE:
                sub.add_argument("names", nargs="*", help=_BOOK_NAMES_HELP)
            case Subcommand.SUMMARY:
                pass  # takes no book
            case _:
                assert_never(subcommand)
    return parser


def _git(git: str, *arguments: str) -> str:
    return subprocess.run(
        [git, *arguments],
        capture_output=True,
        text=True,
        check=True,
        timeout=_GIT_TIMEOUT_S,
    ).stdout.strip()


def _repository() -> _Repository:
    git = shutil.which("git")
    if git is None:
        message = "git is not on the PATH; galley-eval runs inside the repository"
        raise EvaluationError(message)
    root = Path(_git(git, "rev-parse", "--show-toplevel"))
    commit = _git(
        git, "-C", str(root), "describe", "--always", "--dirty", "--abbrev=12"
    )
    return _Repository(git=git, root=root, commit=commit)


def _samples_dir(repository: _Repository) -> Path:
    """GALLEY_SAMPLES, or else `samples/` of the main checkout."""
    env = os.environ.get("GALLEY_SAMPLES")
    if env is not None and env != "":
        return Path(env)
    common = _git(
        repository.git, "rev-parse", "--path-format=absolute", "--git-common-dir"
    )
    return Path(common).parent / "samples"


def _toml_string(text: str) -> str:
    """A TOML basic string of `text`, written as a JSON string: every
    escape JSON writes, \\" \\\\ \\n \\t \\uXXXX and the others, is one TOML's
    basic strings read the same way."""
    return json.dumps(text, ensure_ascii=False)


def book_toml(book: EvaluationBook, pdf: Path) -> str:
    """The text of galley's `book.toml` for `book`, whose PDF is `pdf`."""
    authors = ", ".join(_toml_string(author) for author in book.authors)
    return (
        f"pdf = {_toml_string(str(pdf))}\n"
        f"title = {_toml_string(book.title)}\n"
        f"authors = [{authors}]\n"
        f"language = {_toml_string(book.language.value)}\n"
        f"exclude_pages = [{_toml_pages(book.exclude_pages)}]\n"
        f"contents_pages = [{_toml_pages(book.contents_pages)}]\n"
        f"plate_pages = [{_toml_pages(book.plate_pages)}]\n"
    )


def _toml_pages(pages: tuple[int, ...]) -> str:
    """The items of a TOML list of page indices."""
    return ", ".join(str(page) for page in pages)


def galley_error_lines(stderr: str) -> str:
    """What galley's standard error says of its failure: its lines that
    start with "ERROR ", which name the stage, else its last line."""
    lines = stderr.strip().splitlines()
    errors = tuple(line for line in lines if line.startswith(_GALLEY_ERROR_PREFIX))
    if errors:
        return "\n".join(errors)
    return lines[-1] if lines else "(nothing on standard error)"


def run_galley(program: str, folder: BookFolder) -> None:
    """Run `program`, galley2epub, with `run` on `folder` as a separate
    process. Raises GalleyRunError with galley's error when it fails or
    runs longer than _GALLEY_TIMEOUT_S."""
    try:
        subprocess.run(
            [program, "run", str(folder.root)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
            timeout=_GALLEY_TIMEOUT_S,
        )
    except subprocess.CalledProcessError as err:
        message = (
            f"galley2epub run {folder.root} exited with {err.returncode}: "
            f"{galley_error_lines(err.stderr)}"
        )
        raise GalleyRunError(message) from err
    except subprocess.TimeoutExpired as err:
        message = (
            f"galley2epub run {folder.root} did not finish in {_GALLEY_TIMEOUT_S} s"
        )
        raise GalleyRunError(message) from err


def compare_books(
    books: tuple[EvaluationBook, ...],
    *,
    runs_dir: Path,
    samples_dir: Path,
    commit: str,
    galley: RunGalley | None,
    compare: Compare = evaluate,
) -> tuple[str, ...]:
    """For each book, in order: with `galley`, write its book.toml, run
    galley on its folder under `runs_dir` and record `commit` as the one
    that made its files; then compare, at `commit`, and write the tool's
    files. A book that fails is logged with its error and recorded as
    failed, and the others go on; the timings of the others are logged.
    Returns the names of the books that failed."""
    failed: list[str] = []
    for book in books:
        folder = BookFolder(runs_dir / book.name)
        try:
            timings = _one_book(
                book,
                folder,
                samples_dir=samples_dir,
                commit=commit,
                galley=galley,
                compare=compare,
            )
        except (EvaluationError, GalleyError) as err:
            _logger.error("%s: failed: %s", book.name, err)  # noqa: TRY400
            write_failure(folder, str(err))
            failed.append(book.name)
            continue
        _logger.info("%s: %s", book.name, timings)
    return tuple(failed)


def _one_book(
    book: EvaluationBook,
    folder: BookFolder,
    *,
    samples_dir: Path,
    commit: str,
    galley: RunGalley | None,
    compare: Compare,
) -> str:
    public_domain = samples_dir / "public_domain"
    timings: list[str] = []
    if galley is not None:
        folder.root.mkdir(parents=True, exist_ok=True)
        folder.book_toml.write_text(
            book_toml(book, public_domain / book.pdf_name), encoding="utf-8"
        )
        start = time.perf_counter()
        galley(folder)
        timings.append(f"galley {time.perf_counter() - start:.1f} s")
        write_galley_commit(folder, commit)
    if not folder.root.is_dir():
        message = f"{folder.root} does not exist; run `galley-eval run {book.name}`"
        raise EvaluationError(message)
    run = RunInfo(
        galley_commit=read_galley_commit(folder),
        comparison_commit=commit,
        date=datetime.date.today().isoformat(),
        tool_version=importlib.metadata.version("galley-eval"),
    )
    start = time.perf_counter()
    evaluation = compare(book, folder, public_domain / "gutenberg" / book.html_name)
    timings.append(f"comparison {time.perf_counter() - start:.1f} s")
    write_evaluation(evaluation, folder, run)
    return ", ".join(timings)


def _selected(
    books: tuple[EvaluationBook, ...],
    names: Sequence[str],
    parser: argparse.ArgumentParser,
) -> tuple[EvaluationBook, ...]:
    known = {book.name: book for book in books}
    unknown = tuple(name for name in names if name not in known)
    if unknown:
        parser.error(
            f"no book named {', '.join(unknown)} in evaluation/books.toml; "
            f"the books are {', '.join(known)}"
        )
    if not names:
        return books
    return tuple(known[name] for name in names)


def _galley_program() -> RunGalley:
    program = shutil.which("galley2epub")
    if program is None:
        message = "galley2epub is not on the PATH; run galley-eval with `uv run`"
        raise GalleyRunError(message)
    return lambda folder: run_galley(program, folder)


def main(argv: Sequence[str] | None = None) -> None:
    """Run galley-eval with the arguments `argv`, or those of the command
    line when it is None. argparse exits with code 2 on arguments it
    rejects, among them an unknown book; the command exits with code 1
    when a book failed, after rewriting runs/evaluation/summary.md."""
    parser = _parser()
    arguments = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, stream=sys.stderr, format="%(levelname)s %(message)s"
    )
    repository = _repository()
    books = read_books(repository.root / "evaluation" / "books.toml")
    runs_dir = repository.root / "runs" / "evaluation"
    subcommand = Subcommand(arguments.command)
    # The books are checked before runs/evaluation/ is made, so that an
    # unknown book leaves no folder behind.
    selected = (
        _selected(books, arguments.names, parser)
        if subcommand is not Subcommand.SUMMARY
        else ()
    )
    runs_dir.mkdir(parents=True, exist_ok=True)
    match subcommand:
        case Subcommand.SUMMARY:
            failed: tuple[str, ...] = ()
        case Subcommand.RUN | Subcommand.COMPARE:
            failed = compare_books(
                selected,
                runs_dir=runs_dir,
                samples_dir=_samples_dir(repository),
                commit=repository.commit,
                galley=_galley_program() if subcommand is Subcommand.RUN else None,
            )
        case _:
            assert_never(subcommand)
    summary = write_books_summary(runs_dir, tuple(book.name for book in books))
    _logger.info("wrote %s", summary)
    if failed:
        parser.exit(1, f"galley-eval: failed: {', '.join(failed)}\n")
