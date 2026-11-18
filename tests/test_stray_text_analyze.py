"""Excerpt tests of the plan stray-text for the stream analyze: the
inkless page (docs/specs/plates.md, section 2b). The expected output of
each page is that of its file in tests/fixtures/expected/stray_text/,
transcribed from the page rendered at 300 dpi."""

import json
from pathlib import Path
from typing import Any

import pytest

from galley.book_folder import BookFolder
from galley.model import PageKind, RemovalReason, read_pages, read_words

_EXPECTED = Path(__file__).parent / "fixtures" / "expected" / "stray_text"


def _expected(excerpt: str, page: int) -> dict[str, Any]:
    return json.loads(
        (_EXPECTED / f"{excerpt}_page{page}.json").read_text(encoding="utf-8")
    )["expected"]


def _kind_and_kept_words(folder: BookFolder, page: int) -> tuple[str, list[str]]:
    kind = read_pages(folder.pages_json).pages[page].kind
    words = read_words(folder.words_json).pages[page].words
    return kind.value, [word.text for word in words]


@pytest.mark.pandoc
@pytest.mark.tesseract
def test_haskins_colophon_is_a_text_page_with_its_words(
    excerpt_books: frozendict[str, BookFolder],
) -> None:
    expected = _expected("haskins_endpapers", 0)
    assert _kind_and_kept_words(excerpt_books["haskins_endpapers"], 0) == (
        expected["kind"],
        expected["kept_words"],
    )


@pytest.mark.pandoc
@pytest.mark.tesseract
@pytest.mark.parametrize("page", [2, 3])
def test_haskins_back_endpaper_is_inkless_and_every_word_a_removal(
    excerpt_books: frozendict[str, BookFolder], page: int
) -> None:
    folder = excerpt_books["haskins_endpapers"]
    expected = _expected("haskins_endpapers", page)
    removals = [
        removal
        for removal in read_words(folder.words_json).removals
        if removal.page_index == page
    ]
    assert _kind_and_kept_words(folder, page) == (
        expected["kind"],
        expected["kept_words"],
    )
    assert [removal.reason.value for removal in removals] == [
        expected["removal_reason"]
    ] * expected["removals"]


@pytest.mark.pandoc
@pytest.mark.tesseract
@pytest.mark.parametrize(
    ("excerpt", "page"), [("domesday_notes", 9), ("gierke_notes_heads", 6)]
)
def test_page_of_print_with_words_without_ink_stays_a_text_page(
    excerpt_books: frozendict[str, BookFolder], excerpt: str, page: int
) -> None:
    # Domesday 481's sideways column heads and Gierke 63's boxes off the
    # print have no ink under them; their pages keep every word.
    folder = excerpt_books[excerpt]
    assert read_pages(folder.pages_json).pages[page].kind is PageKind.TEXT
    assert _expected(excerpt, page)["kind"] == "text"
    assert not [
        removal
        for removal in read_words(folder.words_json).removals
        if removal.page_index == page and removal.reason is RemovalReason.INKLESS_PAGE
    ]
