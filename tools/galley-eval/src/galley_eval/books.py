"""The evaluation set: `evaluation/books.toml`, read into EvaluationBook
values (spec section 3).

Each `[[book]]` table of the file is one evaluation book: its name, its
Gutenberg ebook number and Internet Archive identifier, the title, authors
and language that galley's `book.toml` needs, the pages without a text
layer (`exclude_pages`), the pages whose text Gutenberg left out
(`not_in_reference`), whether Gutenberg moved the margin notes
(`margin_notes_moved`), the counts the reader must find in the HTML
(`expected_counts`), and the reading rules, as changes to the defaults of
`galley_eval.rules`:

    [book.rules.add]
    heading = ["p.ph3"]
    [book.rules.replace]
    start = ["h1"]

An unknown key or a value of the wrong type is a BooksFileError that names
the file and the key.
"""

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from galley.config import Language
from galley_eval.errors import BooksFileError
from galley_eval.rules import DEFAULT_RULES, ReadingRules, RuleChange, change_rules

__all__ = ["EvaluationBook", "ExpectedCounts", "read_books"]


@dataclass(frozen=True, slots=True, kw_only=True)
class ExpectedCounts:
    """What the reader must find in a book's HTML, counted by hand: notes,
    margin notes, note references in the body, and page anchors."""

    notes: int
    margin_notes: int
    note_references: int
    page_anchors: int


@dataclass(frozen=True, slots=True, kw_only=True)
class EvaluationBook:
    """One book of the evaluation set (spec section 3). Page indices count
    from 0 in the Internet Archive PDF."""

    name: str
    gutenberg_number: int
    archive_id: str
    title: str
    authors: tuple[str, ...]
    language: Language
    exclude_pages: tuple[int, ...]
    not_in_reference: tuple[int, ...]
    margin_notes_moved: bool
    expected_counts: ExpectedCounts
    rules: ReadingRules

    @property
    def pdf_name(self) -> str:
        """The PDF's file name in `samples/public_domain/`."""
        return f"{self.archive_id}.pdf"

    @property
    def html_name(self) -> str:
        """The HTML edition's file name in `samples/public_domain/gutenberg/`."""
        return f"pg{self.gutenberg_number}-images.html"


_REQUIRED_KEYS = (
    "name",
    "gutenberg_number",
    "archive_id",
    "title",
    "authors",
    "language",
    "exclude_pages",
    "expected_counts",
)
_OPTIONAL_KEYS = ("not_in_reference", "margin_notes_moved", "rules")
_COUNT_KEYS = ("notes", "margin_notes", "note_references", "page_anchors")


def read_books(path: Path) -> tuple[EvaluationBook, ...]:
    """The books of the evaluation set in the file at `path`, in its order.

    Raises BooksFileError, naming the file and the key, when the file is
    missing or not TOML, has no book, a key is unknown or a required one
    missing, a value has the wrong type, a string or list that must not be
    empty is, a page index or count is negative, two books have the same
    name, a selector does not parse, or a regular expression does not
    compile.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as err:
        message = f"{path} does not exist; the evaluation set is listed there"
        raise BooksFileError(message) from err
    try:
        content = tomllib.loads(text)
    except tomllib.TOMLDecodeError as err:
        message = f"{path} is not valid TOML: {err}"
        raise BooksFileError(message) from err
    return books_from_toml(content, path)


def books_from_toml(
    content: dict[str, object], path: Path
) -> tuple[EvaluationBook, ...]:
    """The books in the parsed TOML `content`; `path` names the file in a
    BooksFileError. Touches no file."""
    _check_keys(content, ("book",), (), "", path)
    tables = _list(content["book"], "book", path)
    if len(tables) == 0:
        raise _error(path, "book", "must list at least one book")
    books = tuple(
        _book(table, f"book[{position}]", path) for position, table in enumerate(tables)
    )
    names = [book.name for book in books]
    for name in names:
        if names.count(name) > 1:
            raise _error(path, "book", f"the name {name!r} is used twice")
    return books


def _book(table: object, key: str, path: Path) -> EvaluationBook:
    book = _table(table, key, path)
    _check_keys(book, _REQUIRED_KEYS, _OPTIONAL_KEYS, f"{key}.", path)
    return EvaluationBook(
        name=_not_empty(
            _string(book["name"], f"{key}.name", path), f"{key}.name", path
        ),
        gutenberg_number=_positive(
            book["gutenberg_number"], f"{key}.gutenberg_number", path
        ),
        archive_id=_not_empty(
            _string(book["archive_id"], f"{key}.archive_id", path),
            f"{key}.archive_id",
            path,
        ),
        title=_not_empty(
            _string(book["title"], f"{key}.title", path), f"{key}.title", path
        ),
        authors=_not_empty(
            _strings(book["authors"], f"{key}.authors", path), f"{key}.authors", path
        ),
        language=_language(book["language"], f"{key}.language", path),
        exclude_pages=_page_indices(
            book["exclude_pages"], f"{key}.exclude_pages", path
        ),
        not_in_reference=_page_indices(
            book.get("not_in_reference", []), f"{key}.not_in_reference", path
        ),
        margin_notes_moved=_bool(
            book.get("margin_notes_moved", False), f"{key}.margin_notes_moved", path
        ),
        expected_counts=_counts(
            book["expected_counts"], f"{key}.expected_counts", path
        ),
        rules=_rules(book.get("rules", {}), f"{key}.rules", path),
    )


def _counts(value: object, key: str, path: Path) -> ExpectedCounts:
    table = _table(value, key, path)
    _check_keys(table, _COUNT_KEYS, (), f"{key}.", path)
    counts = {name: _count(table[name], f"{key}.{name}", path) for name in _COUNT_KEYS}
    return ExpectedCounts(
        notes=counts["notes"],
        margin_notes=counts["margin_notes"],
        note_references=counts["note_references"],
        page_anchors=counts["page_anchors"],
    )


def _rules(value: object, key: str, path: Path) -> ReadingRules:
    table = _table(value, key, path)
    changes = tuple(change.value for change in RuleChange)
    _check_keys(table, (), changes, f"{key}.", path)
    rules = DEFAULT_RULES
    seen: set[str] = set()
    for change in RuleChange:
        changed = _table(table.get(change.value, {}), f"{key}.{change.value}", path)
        for rule, values in changed.items():
            rule_key = f"{key}.{change.value}.{rule}"
            if rule in seen:
                raise _error(path, rule_key, "the rule is both added to and replaced")
            seen.add(rule)
            try:
                rules = change_rules(
                    rules, change, rule, _strings(values, rule_key, path)
                )
            except ValueError as err:
                raise _error(path, rule_key, str(err)) from err
    return rules


def _error(path: Path, key: str, problem: str) -> BooksFileError:
    return BooksFileError(f"{path}: key `{key}`: {problem}")


def _check_keys(
    table: dict[str, object],
    required: tuple[str, ...],
    optional: tuple[str, ...],
    prefix: str,
    path: Path,
) -> None:
    for key in required:
        if key not in table:
            raise _error(path, prefix + key, "missing; it is required")
    for key in table:
        if key not in required + optional:
            known = ", ".join(required + optional)
            raise _error(path, prefix + key, f"unknown; the keys are {known}")


def _table(value: object, key: str, path: Path) -> dict[str, object]:
    if not isinstance(value, dict):
        raise _error(path, key, f"expected a table, found {value!r}")
    # tomllib makes every table a dict with string keys.
    return cast("dict[str, object]", value)


def _list(value: object, key: str, path: Path) -> tuple[object, ...]:
    if not isinstance(value, list):
        raise _error(path, key, f"expected a list, found {value!r}")
    return tuple(value)


def _string(value: object, key: str, path: Path) -> str:
    if not isinstance(value, str):
        raise _error(path, key, f"expected a string, found {value!r}")
    return value


def _strings(value: object, key: str, path: Path) -> tuple[str, ...]:
    return tuple(
        _string(item, f"{key}[{position}]", path)
        for position, item in enumerate(_list(value, key, path))
    )


def _not_empty[T: (str, tuple[str, ...])](value: T, key: str, path: Path) -> T:
    if len(value) == 0:
        raise _error(path, key, "must not be empty")
    return value


def _bool(value: object, key: str, path: Path) -> bool:
    if not isinstance(value, bool):
        raise _error(path, key, f"expected true or false, found {value!r}")
    return value


def _int(value: object, key: str, path: Path) -> int:
    # TOML true is a bool, which Python counts as an int; it is not a number.
    if isinstance(value, bool) or not isinstance(value, int):
        raise _error(path, key, f"expected a whole number, found {value!r}")
    return value


def _count(value: object, key: str, path: Path) -> int:
    count = _int(value, key, path)
    if count < 0:
        raise _error(path, key, f"a count is 0 or more, found {count}")
    return count


def _positive(value: object, key: str, path: Path) -> int:
    number = _int(value, key, path)
    if number < 1:
        raise _error(path, key, f"expected a number of 1 or more, found {number}")
    return number


def _page_indices(value: object, key: str, path: Path) -> tuple[int, ...]:
    pages = tuple(
        _int(page, f"{key}[{position}]", path)
        for position, page in enumerate(_list(value, key, path))
    )
    for position, page in enumerate(pages):
        if page < 0:
            raise _error(
                path, f"{key}[{position}]", f"a page index counts from 0, found {page}"
            )
    return pages


def _language(value: object, key: str, path: Path) -> Language:
    codes = tuple(language.value for language in Language)
    if not isinstance(value, str) or value not in codes:
        raise _error(path, key, f"expected one of {', '.join(codes)}, found {value!r}")
    return Language(value)
