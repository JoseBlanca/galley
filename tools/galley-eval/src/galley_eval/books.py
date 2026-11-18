"""The evaluation set: `evaluation/books.toml`, read into EvaluationBook
values (spec section 3).

Each `[[book]]` table of the file is one evaluation book: its name, its
Gutenberg ebook number and Internet Archive identifier, the title, authors
and language that galley's `book.toml` needs, the pages without a text
layer (`exclude_pages`), and the book config's `contents_pages` and
`plate_pages` (architecture section 6), which galley-eval passes into the
`book.toml` it writes; the pages whose text Gutenberg left out
(`not_in_reference`), the `id` of the element of the HTML where the
reference ends (`reference_ends_at`), whether Gutenberg moved the margin
notes (`margin_notes_moved`), the first and last page index of the body range,
on which the headings are scored (`body_pages`), the SHA-256 of the HTML
file the rules and counts were written for (`html_sha256`), the counts
the reader must find in the HTML and the first five tokens of its body
(`expected_counts`), and the reading rules, as changes to the defaults
of `galley_eval.rules`:

    [book.rules.add]
    heading = ["p.ph3"]
    [book.rules.replace]
    start = ["h1"]

An unknown key or a value of the wrong type is a BooksFileError that names
the file and the key.
"""

import re
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
    margin notes, note references in the body, page anchors (in the body
    and among the notes), headings in the body, and the first five tokens
    of the body."""

    notes: int
    margin_notes: int
    note_references: int
    page_anchors: int
    headings: int
    first_tokens: tuple[str, ...]


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
    contents_pages: tuple[int, ...]
    plate_pages: tuple[int, ...]
    not_in_reference: tuple[int, ...]
    # The `id` of the element of the HTML where the reference ends, that
    # element left out; None when the reference runs to the end.
    reference_ends_at: str | None
    margin_notes_moved: bool
    body_pages: tuple[int, int]
    html_sha256: str
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
    "body_pages",
    "html_sha256",
    "expected_counts",
)
_OPTIONAL_KEYS = (
    "contents_pages",
    "plate_pages",
    "not_in_reference",
    "reference_ends_at",
    "margin_notes_moved",
    "rules",
)
_COUNT_KEYS = ("notes", "margin_notes", "note_references", "page_anchors", "headings")
_FIRST_TOKENS = 5
_SHA256 = re.compile(r"[0-9a-f]{64}")


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
    return _books_from_toml(content, path)


def _books_from_toml(
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
        contents_pages=_page_indices(
            book.get("contents_pages", []), f"{key}.contents_pages", path
        ),
        plate_pages=_page_indices(
            book.get("plate_pages", []), f"{key}.plate_pages", path
        ),
        not_in_reference=_page_indices(
            book.get("not_in_reference", []), f"{key}.not_in_reference", path
        ),
        reference_ends_at=_optional_id(
            book.get("reference_ends_at"), f"{key}.reference_ends_at", path
        ),
        margin_notes_moved=_bool(
            book.get("margin_notes_moved", False), f"{key}.margin_notes_moved", path
        ),
        body_pages=_page_range(book["body_pages"], f"{key}.body_pages", path),
        html_sha256=_sha256(book["html_sha256"], f"{key}.html_sha256", path),
        expected_counts=_counts(
            book["expected_counts"], f"{key}.expected_counts", path
        ),
        rules=_rules(book.get("rules", {}), f"{key}.rules", path),
    )


def _counts(value: object, key: str, path: Path) -> ExpectedCounts:
    table = _table(value, key, path)
    _check_keys(table, (*_COUNT_KEYS, "first_tokens"), (), f"{key}.", path)
    counts = {name: _count(table[name], f"{key}.{name}", path) for name in _COUNT_KEYS}
    return ExpectedCounts(
        notes=counts["notes"],
        margin_notes=counts["margin_notes"],
        note_references=counts["note_references"],
        page_anchors=counts["page_anchors"],
        headings=counts["headings"],
        first_tokens=_first_tokens(table["first_tokens"], f"{key}.first_tokens", path),
    )


def _first_tokens(value: object, key: str, path: Path) -> tuple[str, ...]:
    tokens = _strings(value, key, path)
    if len(tokens) != _FIRST_TOKENS:
        raise _error(path, key, f"expected five tokens, found {len(tokens)}")
    for position, token in enumerate(tokens):
        if token == "" or len(token.split()) != 1:
            raise _error(
                path,
                f"{key}[{position}]",
                f"a token has no white space, found {token!r}",
            )
    return tokens


def _sha256(value: object, key: str, path: Path) -> str:
    text = _string(value, key, path)
    if _SHA256.fullmatch(text) is None:
        raise _error(
            path, key, f"expected 64 hexadecimal digits in lower case, found {text!r}"
        )
    return text


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


def _optional_id(value: object, key: str, path: Path) -> str | None:
    if value is None:
        return None
    return _not_empty(_string(value, key, path), key, path)


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


def _page_range(value: object, key: str, path: Path) -> tuple[int, int]:
    pages = _page_indices(value, key, path)
    match pages:
        case (first, last) if first <= last:
            return first, last
        case (first, last):
            raise _error(
                path, key, f"the first page, {first}, is above the last, {last}"
            )
        case _:
            raise _error(path, key, f"expected two page indices, found {len(pages)}")


def _language(value: object, key: str, path: Path) -> Language:
    codes = tuple(language.value for language in Language)
    if not isinstance(value, str) or value not in codes:
        raise _error(path, key, f"expected one of {', '.join(codes)}, found {value!r}")
    return Language(value)
