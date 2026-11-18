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
from galley.model import (
    Block,
    BlockKind,
    BlocksFile,
    PageInfo,
    PageKind,
    block_text,
    read_pages,
)

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


# structure's part (figures spec section 10): a figure block for each
# in-page figure, and the first words of their captions. Only numerals and
# a label word of the books are written here.


def _figure_blocks(blocks: BlocksFile) -> tuple[Block, ...]:
    return tuple(
        block
        for block in blocks.blocks
        if block.kind is BlockKind.FIGURE and "/figure-" in (block.figure or "")
    )


@pytest.mark.parametrize("book", ["haynes", "turney"])
def test_owner_book_figure_blocks_are_one_for_each_in_page_figure(
    owner_book_run: Callable[[str], BlocksFile], book: str
) -> None:
    pages: dict[int, int] = {}
    for block in _figure_blocks(owner_book_run(book)):
        index = block.origin[0].page_index
        pages[index] = pages.get(index, 0) + 1
    assert pages == _FIGURES[book]


# Haynes' 25 figures: each caption's second word, the figure's number as
# the OCR read it ("li." for 11, "l6." for 16), after "figure" in any case.
_HAYNES_NUMBERS = (
    *("1.", "2.", "3.", "4.", "5.", "6.", "7.", "8.", "9.", "10.", "li."),
    *("12.", "13.", "14.", "15.", "l6.", "17.", "18.", "19.", "20.", "21."),
    *("22.", "23.", "24.", "25."),
)


# The number of words of each of Haynes' captions, from its label to its
# last word, as galley gives them on 18 November 2026; each caption's last
# words were read against its page and none was cut short or ran on.
_HAYNES_CAPTION_WORDS = (
    *(12, 12, 21, 40, 14, 50, 21, 44, 75, 40, 19, 24, 10, 95, 15, 14, 26),
    *(19, 15, 16, 24, 25, 30, 16, 13),
)


def test_haynes_caption_of_each_figure_opens_with_figure_and_its_number(
    owner_book_run: Callable[[str], BlocksFile],
) -> None:
    figures = _figure_blocks(owner_book_run("haynes"))
    assert tuple(
        (words[0].lower(), words[1])
        for words in (block_text(block).split(" ") for block in figures)
    ) == tuple(("figure", number) for number in _HAYNES_NUMBERS)
    assert (
        tuple(len(block_text(block).split(" ")) for block in figures)
        == _HAYNES_CAPTION_WORDS
    )


# Turney's 14 figures, in order: the number that opens each caption as the
# OCR read it ("i." for 1, "2i." for 21), None for the 3 without one: the
# second cover of page 174, the film still of 167 and the back cover.
_TURNEY_NUMBERS = (
    *("i.", "4.", None, "8.", "12.", "13.", "14", None, "15.", "16.", "17."),
    *("18.", "2i.", None),
)


# The number of words of each of Turney's captions, 0 for the 3 without
# one, as galley gives them on 18 November 2026: 15 and 17 (pages 175 and
# 176) whole with their last rows, which layout joined with lettering.
_TURNEY_CAPTION_WORDS = (34, 32, 0, 41, 18, 41, 62, 0, 41, 31, 33, 30, 42, 0)


def test_turney_caption_of_11_figures_and_no_heading_on_page_174(
    owner_book_run: Callable[[str], BlocksFile],
) -> None:
    blocks = owner_book_run("turney")
    assert (
        tuple(
            block_text(block).split(" ")[0] if block.spans else None
            for block in _figure_blocks(blocks)
        )
        == _TURNEY_NUMBERS
    )
    assert (
        tuple(
            len(block_text(block).split(" ")) if block.spans else 0
            for block in _figure_blocks(blocks)
        )
        == _TURNEY_CAPTION_WORDS
    )
    assert not any(
        block.kind is BlockKind.HEADING
        and any(origin.page_index == 174 for origin in block.origin)
        for block in blocks.blocks
    )
