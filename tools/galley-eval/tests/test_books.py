"""Tests of galley_eval.books, reading evaluation/books.toml (spec section 3),
and of the rules' selectors (spec section 4, "The rules")."""

import re
from pathlib import Path

import pytest

from galley.config import Language
from galley_eval.books import EvaluationBook, ExpectedCounts, read_books
from galley_eval.errors import BooksFileError
from galley_eval.rules import DEFAULT_RULES, Selector, SimpleSelector, parse_selector

BOOKS_TOML = Path(__file__).parents[3] / "evaluation" / "books.toml"

MINIMAL_BOOK = """
[[book]]
name = "haskins"
gutenberg_number = 72514
archive_id = "normansineuropea00hask"
title = "The Normans in European History"
authors = ["Charles Homer Haskins"]
language = "en"
exclude_pages = [0, 3]
html_sha256 = "d88ef036c5def555a899a2df51aea1d337cd2583ca9ae5d154c06185ed552ea7"
expected_counts = { notes = 72, margin_notes = 0, note_references = 72, page_anchors = 260, headings = 21, first_tokens = ["THE", "NORMANS", "IN", "EUROPEAN", "HISTORY"] }
"""

HASKINS_SHA256 = "d88ef036c5def555a899a2df51aea1d337cd2583ca9ae5d154c06185ed552ea7"


def _write(folder: Path, text: str) -> Path:
    path = folder / "books.toml"
    path.write_text(text, encoding="utf-8")
    return path


def test_the_evaluation_set_has_the_four_books_of_the_spec() -> None:
    books = read_books(BOOKS_TOML)
    assert [book.name for book in books] == [
        "haskins",
        "stubbs",
        "domesday",
        "mariejol",
    ]
    assert [book.gutenberg_number for book in books] == [72514, 70828, 43255, 36315]
    mariejol = books[3]
    assert mariejol.language is Language.FR
    assert mariejol.not_in_reference == (14, 15, 16)
    assert mariejol.html_name == "pg36315-images.html"
    assert mariejol.pdf_name == "catherinedemedic00mariuoft.pdf"
    assert books[2].margin_notes_moved
    assert books[2].expected_counts == ExpectedCounts(
        notes=1729,
        margin_notes=593,
        note_references=1731,
        page_anchors=537,
        headings=28,
        first_tokens=("DOMESDAY", "BOOK", "AND", "BEYOND", "THREE"),
    )


def test_book_with_only_required_keys_takes_the_defaults(tmp_path: Path) -> None:
    (book,) = read_books(_write(tmp_path, MINIMAL_BOOK))
    assert book == EvaluationBook(
        name="haskins",
        gutenberg_number=72514,
        archive_id="normansineuropea00hask",
        title="The Normans in European History",
        authors=("Charles Homer Haskins",),
        language=Language.EN,
        exclude_pages=(0, 3),
        not_in_reference=(),
        margin_notes_moved=False,
        html_sha256=HASKINS_SHA256,
        expected_counts=ExpectedCounts(
            notes=72,
            margin_notes=0,
            note_references=72,
            page_anchors=260,
            headings=21,
            first_tokens=("THE", "NORMANS", "IN", "EUROPEAN", "HISTORY"),
        ),
        rules=DEFAULT_RULES,
    )


def test_rules_are_added_to_or_replace_the_defaults(tmp_path: Path) -> None:
    text = (
        MINIMAL_BOOK
        + "not_in_reference = [14, 16]\nmargin_notes_moved = true\n"
        + "[book.rules.add]\nheading = ['p.ph3']\ndrop_text = ['Note \\d+:']\n"
        + "[book.rules.replace]\nstart = ['h1']\nnote_reference = ['#footnote\\d+']\n"
    )
    (book,) = read_books(_write(tmp_path, text))
    assert book.not_in_reference == (14, 16)
    assert book.margin_notes_moved
    assert book.rules.heading == (*DEFAULT_RULES.heading, parse_selector("p.ph3"))
    assert book.rules.start == (parse_selector("h1"),)
    assert book.rules.drop_text == (re.compile(r"Note \d+:"),)
    assert book.rules.note_reference == (re.compile(r"#footnote\d+"),)
    assert book.rules.drop == DEFAULT_RULES.drop


@pytest.mark.parametrize(
    ("text", "selector"),
    [
        ("p", Selector("p", SimpleSelector("p", None), None)),
        ("p.ph3", Selector("p.ph3", SimpleSelector("p", "ph3"), None)),
        (".label", Selector(".label", SimpleSelector(None, "label"), None)),
        (
            ".footnotes > h2",
            Selector(
                ".footnotes > h2",
                SimpleSelector("h2", None),
                SimpleSelector(None, "footnotes"),
            ),
        ),
    ],
)
def test_selector_is_parsed_into_element_and_parent(
    text: str, selector: Selector
) -> None:
    assert parse_selector(text) == selector


@pytest.mark.parametrize(
    "text", ["#Footnote_1", "p.a.b", "div p", "a > b > c", "", "P"]
)
def test_selector_of_another_form_is_a_value_error(text: str) -> None:
    with pytest.raises(ValueError, match="is not a selector"):
        parse_selector(text)


@pytest.mark.parametrize(
    ("change", "key", "problem"),
    [
        ("", "book", "missing"),
        ("book = []", "book", "at least one book"),
        ("[[book]]\nname = 'x'", "book[0].gutenberg_number", "missing"),
        ("year = 1915", "book[0].year", "unknown"),
        ("gutenberg_number = '72514'", "book[0].gutenberg_number", "whole number"),
        ("gutenberg_number = 0", "book[0].gutenberg_number", "1 or more"),
        ("authors = []", "book[0].authors", "must not be empty"),
        ("name = ''", "book[0].name", "must not be empty"),
        ("language = 'la'", "book[0].language", "expected one of"),
        ("exclude_pages = [-1]", "book[0].exclude_pages[0]", "counts from 0"),
        ("exclude_pages = [true]", "book[0].exclude_pages[0]", "whole number"),
        ("not_in_reference = 14", "book[0].not_in_reference", "expected a list"),
        ("margin_notes_moved = 1", "book[0].margin_notes_moved", "true or false"),
        (
            "expected_counts = { notes = 1, margin_notes = 0, note_references = 1, headings = 0, first_tokens = ['a', 'b', 'c', 'd', 'e'] }",
            "book[0].expected_counts.page_anchors",
            "missing",
        ),
        (
            "expected_counts = { notes = -1, margin_notes = 0, note_references = 1, page_anchors = 0, headings = 0, first_tokens = ['a', 'b', 'c', 'd', 'e'] }",
            "book[0].expected_counts.notes",
            "0 or more",
        ),
        (
            "expected_counts = { notes = 1, margin_notes = 0, note_references = 1, page_anchors = 0, headings = 0, first_tokens = ['a', 'b'] }",
            "book[0].expected_counts.first_tokens",
            "five tokens",
        ),
        (
            "expected_counts = { notes = 1, margin_notes = 0, note_references = 1, page_anchors = 0, headings = 0, first_tokens = ['a', 'b', 'c d', 'e', 'f'] }",
            "book[0].expected_counts.first_tokens[2]",
            "white space",
        ),
        ("html_sha256 = 'd88ef036'", "book[0].html_sha256", "64 hexadecimal"),
        ("html_sha256 = 72514", "book[0].html_sha256", "expected a string"),
        ("title = ''", "book[0].title", "must not be empty"),
        ("archive_id = ''", "book[0].archive_id", "must not be empty"),
        ("rules = { remove = {} }", "book[0].rules.remove", "unknown"),
        (
            "rules = { add = { header = ['h1'] } }",
            "book[0].rules.add.header",
            "unknown rule",
        ),
        (
            "rules = { add = { heading = ['#x'] } }",
            "book[0].rules.add.heading",
            "not a selector",
        ),
        (
            "rules = { add = { heading = 'h1' } }",
            "book[0].rules.add.heading",
            "expected a list",
        ),
        (
            "rules = { add = { drop_text = ['(retour'] } }",
            "book[0].rules.add.drop_text",
            "not a regular expression",
        ),
        (
            "rules = { add = { quote = ['p'] }, replace = { quote = ['div'] } }",
            "book[0].rules.replace.quote",
            "both added to and replaced",
        ),
    ],
)
def test_malformed_entry_is_a_books_file_error_naming_the_key(
    tmp_path: Path, change: str, key: str, problem: str
) -> None:
    if change == "":
        text = "title = 'x'\n"
    elif change.startswith(("book =", "[[book]]")):
        text = change + "\n"
    else:
        # A key written after the book's keys belongs to the book's table.
        name = change.split(" = ")[0]
        kept = "\n".join(
            line
            for line in MINIMAL_BOOK.splitlines()
            if not line.startswith(f"{name} = ")
        )
        text = f"{kept}\n{change}\n"
    path = _write(tmp_path, text)
    with pytest.raises(BooksFileError, match=re.escape(f"key `{key}`")) as raised:
        read_books(path)
    assert problem in str(raised.value)
    assert str(path) in str(raised.value)


def test_two_books_of_the_same_name_are_a_books_file_error(tmp_path: Path) -> None:
    with pytest.raises(BooksFileError, match="'haskins' is used twice"):
        read_books(_write(tmp_path, MINIMAL_BOOK + MINIMAL_BOOK))


def test_missing_file_is_a_books_file_error(tmp_path: Path) -> None:
    with pytest.raises(BooksFileError, match="does not exist"):
        read_books(tmp_path / "books.toml")


def test_file_that_is_not_toml_is_a_books_file_error(tmp_path: Path) -> None:
    with pytest.raises(BooksFileError, match="not valid TOML"):
        read_books(_write(tmp_path, "[[book]\nname = "))
