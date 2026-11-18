"""Whole-book tests of the in-page figures on the owner's two modern books
(docs/specs/figures.md, section 10, "Whole-book tests").

The books are copyrighted: they sit in the samples folder, ignored by git,
and these tests count what galley finds on them and compare page indices,
never quote their text. Each test finds its book's PDF by a pattern of its
file name and skips, with the reason, when the PDF is absent.
"""

import functools
import threading
from collections.abc import Callable

import pytest

from galley import analyze
from galley.book_folder import BookFolder
from galley.config import read_config
from galley.model import PageInfo, PageKind, read_pages

pytestmark = [pytest.mark.whole_book, pytest.mark.timeout(900)]

# Figures spec section 2: the in-page figures of each book, by page index
# and count. Haynes has one on each of 25 pages; Turney 14 on 11 pages, the
# insert of illustrations and the back cover.
_FIGURES = {
    "haynes": dict.fromkeys(
        (
            *(15, 25, 34, 45, 53, 58, 64, 71, 84, 95, 97, 111, 114),
            *(119, 124, 133, 142, 143, 145, 162, 180, 182, 253, 254, 310),
        ),
        1,
    ),
    "turney": {
        164: 1,
        166: 1,
        167: 1,
        169: 1,
        172: 1,
        173: 1,
        174: 2,
        175: 2,
        176: 2,
        179: 1,
        311: 1,
    },
}


@pytest.fixture(scope="module")
def owner_book_analyzed(
    owner_book_toml: Callable[[str], str], tmp_path_factory: pytest.TempPathFactory
) -> Callable[[str], tuple[PageInfo, ...]]:
    """A function that gives the pages of one of the owner's books, "turney"
    or "haynes", as analyze finds them with the config of tests/conftest.py,
    run the first time a test asks for the book. Skips the test when the
    book's PDF is not in the samples folder."""
    roots = {book: tmp_path_factory.mktemp(book) for book in ("turney", "haynes")}
    locks = {book: threading.Lock() for book in roots}

    def analyzed(book: str) -> tuple[PageInfo, ...]:
        toml = owner_book_toml(book)
        with locks[book]:
            return analyzed_once(book, toml)

    @functools.cache
    def analyzed_once(book: str, toml: str) -> tuple[PageInfo, ...]:
        folder = BookFolder(roots[book])
        folder.book_toml.write_text(toml, encoding="utf-8")
        analyze.run(folder, read_config(folder.book_toml))
        return read_pages(folder.pages_json).pages

    return analyzed


@pytest.mark.parametrize("book", ["haynes", "turney"])
def test_owner_book_analyze_finds_the_in_page_figures_of_section_2_and_no_other(
    owner_book_analyzed: Callable[[str], tuple[PageInfo, ...]], book: str
) -> None:
    pages = owner_book_analyzed(book)
    assert {
        page.index: len(page.figure_boxes) for page in pages if page.figure_boxes
    } == _FIGURES[book]
    assert all(page.kind is PageKind.TEXT for page in pages if page.figure_boxes)
