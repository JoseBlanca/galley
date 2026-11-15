"""The galley-eval command: `run`, `compare` and `summary` (spec section 9).

- `run [<name> ...]` writes each book's `book.toml` from
  `evaluation/books.toml` into `runs/evaluation/<name>/`, runs
  `galley2epub run` on that folder as a separate process, then compares;
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
error and the others go on; the command then exits with code 1.
"""

import argparse
import datetime
import importlib.metadata
import logging
import os
import shutil
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from pathlib import Path

from galley.book_folder import BookFolder
from galley.errors import GalleyError
from galley_eval.books import EvaluationBook, read_books
from galley_eval.errors import EvaluationError, GalleyRunError
from galley_eval.evaluate import Evaluation, evaluate
from galley_eval.output import RunInfo, write_books_summary, write_evaluation

__all__ = [
    "book_toml",
    "compare_books",
    "main",
    "run_galley",
]

_BOOK_NAMES_HELP = "names of books in evaluation/books.toml; all books when none"

# (subcommand, help, whether it takes book names)
_SUBCOMMANDS = (
    ("run", "run galley on each book, then compare", True),
    ("compare", "compare the files already in the book folders", True),
    ("summary", "rewrite runs/evaluation/summary.md from the scorecards", False),
)

# A whole book took galley 15 s at most on an M5 Pro (spec section 2); ten
# minutes means a hang. Guessed from that measurement.
_GALLEY_TIMEOUT_S = 600
_GIT_TIMEOUT_S = 10

# The lines of galley's standard error given when it fails; its last lines
# hold the error, the earlier ones the traceback. A choice.
_STDERR_LINES = 5

_logger = logging.getLogger(__name__)

type RunGalley = Callable[[BookFolder], None]
type Compare = Callable[[EvaluationBook, BookFolder, Path], Evaluation]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="galley-eval",
        description="Compares galley's output for the books of the evaluation "
        "set with their Project Gutenberg editions.",
    )
    subcommands = parser.add_subparsers(dest="command", required=True)
    for name, help_text, takes_books in _SUBCOMMANDS:
        subcommand = subcommands.add_parser(name, help=help_text, description=help_text)
        if takes_books:
            subcommand.add_argument("names", nargs="*", help=_BOOK_NAMES_HELP)
    return parser


def _git(*arguments: str) -> str:
    return subprocess.run(
        ["git", *arguments],
        capture_output=True,
        text=True,
        check=True,
        timeout=_GIT_TIMEOUT_S,
    ).stdout.strip()


def _samples_dir() -> Path:
    """GALLEY_SAMPLES, or else `samples/` of the main checkout."""
    env = os.environ.get("GALLEY_SAMPLES")
    if env is not None and env != "":
        return Path(env)
    common = _git("rev-parse", "--path-format=absolute", "--git-common-dir")
    return Path(common).parent / "samples"


def _run_info(root: Path) -> RunInfo:
    commit = _git("-C", str(root), "describe", "--always", "--dirty", "--abbrev=12")
    return RunInfo(
        galley_commit=commit,
        date=datetime.date.today().isoformat(),
        tool_version=importlib.metadata.version("galley-eval"),
    )


def _toml_string(text: str) -> str:
    """A TOML basic string: JSON's escapes are TOML's for these characters."""
    escaped = text.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def book_toml(book: EvaluationBook, pdf: Path) -> str:
    """The text of galley's `book.toml` for `book`, whose PDF is `pdf`."""
    authors = ", ".join(_toml_string(author) for author in book.authors)
    pages = ", ".join(str(page) for page in book.exclude_pages)
    return (
        f"pdf = {_toml_string(str(pdf))}\n"
        f"title = {_toml_string(book.title)}\n"
        f"authors = [{authors}]\n"
        f"language = {_toml_string(book.language.value)}\n"
        f"exclude_pages = [{pages}]\n"
    )


def run_galley(folder: BookFolder) -> None:
    """Run `galley2epub run` on `folder` as a separate process. Raises
    GalleyRunError with the end of galley's standard error when it is not
    installed, fails, or runs longer than _GALLEY_TIMEOUT_S."""
    program = shutil.which("galley2epub")
    if program is None:
        message = "galley2epub is not on the PATH; run galley-eval with `uv run`"
        raise GalleyRunError(message)
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
        tail = "\n".join(err.stderr.strip().splitlines()[-_STDERR_LINES:])
        message = f"galley2epub run {folder.root} exited with {err.returncode}:\n{tail}"
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
    run: RunInfo,
    galley: RunGalley | None,
    compare: Compare = evaluate,
) -> tuple[str, ...]:
    """For each book, in order: with `galley`, write its book.toml and run
    galley on its folder under `runs_dir`; then compare and write the
    tool's files. A book that fails is logged with its error and the
    others go on; the timings of the others are logged. Returns the names
    of the books that failed."""
    failed: list[str] = []
    for book in books:
        folder = BookFolder(runs_dir / book.name)
        try:
            timings = _one_book(
                book,
                folder,
                samples_dir=samples_dir,
                run=run,
                galley=galley,
                compare=compare,
            )
        except (EvaluationError, GalleyError) as err:
            _logger.error("%s: failed: %s", book.name, err)  # noqa: TRY400
            failed.append(book.name)
            continue
        _logger.info("%s: %s", book.name, timings)
    return tuple(failed)


def _one_book(
    book: EvaluationBook,
    folder: BookFolder,
    *,
    samples_dir: Path,
    run: RunInfo,
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
    if not folder.root.is_dir():
        message = f"{folder.root} does not exist; run `galley-eval run {book.name}`"
        raise EvaluationError(message)
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


def main(argv: Sequence[str] | None = None) -> None:
    """Run galley-eval with the arguments `argv`, or those of the command
    line when it is None. argparse exits with code 2 on arguments it
    rejects, among them an unknown book; the command exits with code 1
    when a book failed."""
    parser = _parser()
    arguments = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, stream=sys.stderr, format="%(levelname)s %(message)s"
    )
    root = Path(_git("rev-parse", "--show-toplevel"))
    books = read_books(root / "evaluation" / "books.toml")
    runs_dir = root / "runs" / "evaluation"
    runs_dir.mkdir(parents=True, exist_ok=True)
    match arguments.command:
        case "summary":
            failed: tuple[str, ...] = ()
        case "run" | "compare":
            failed = compare_books(
                _selected(books, arguments.names, parser),
                runs_dir=runs_dir,
                samples_dir=_samples_dir(),
                run=_run_info(root),
                galley=run_galley if arguments.command == "run" else None,
            )
        case _:
            message = f"unknown subcommand {arguments.command!r}"
            raise AssertionError(message)
    summary = write_books_summary(runs_dir, tuple(book.name for book in books))
    _logger.info("wrote %s", summary)
    if failed:
        parser.exit(1, f"galley-eval: failed: {', '.join(failed)}\n")
