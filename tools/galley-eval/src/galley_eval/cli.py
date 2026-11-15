"""The galley-eval command: `run`, `compare` and `summary` (spec section 9).

The three subcommands are parsed but not built yet: each stops with exit
code 1 and says so. Work package 4 of docs/plans/evaluation.md builds them.
"""

import argparse
from collections.abc import Sequence

__all__ = ["main"]

_BOOK_NAMES_HELP = "names of books in evaluation/books.toml; all books when none"

# (subcommand, help, whether it takes book names)
_SUBCOMMANDS = (
    ("run", "run galley on each book, then compare", True),
    ("compare", "compare the files already in the book folders", True),
    ("summary", "rewrite runs/evaluation/summary.md from the scorecards", False),
)


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


def main(argv: Sequence[str] | None = None) -> None:
    """Run galley-eval with the arguments `argv`, or those of the command
    line when it is None. argparse exits with code 2 on arguments it
    rejects; every subcommand exits with code 1, since none is built yet."""
    parser = _parser()
    arguments = parser.parse_args(argv)
    parser.exit(
        1,
        f"galley-eval {arguments.command}: not built yet "
        "(work package 4 of docs/plans/evaluation.md)\n",
    )
