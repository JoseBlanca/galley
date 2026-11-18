"""Whole-book tests of lists and the printed contents on the owner's two
modern books (docs/specs/structure.md, section 32, "Whole-book tests").

The books are copyrighted: these tests count what galley gives on them and
never quote their text. `owner_book_run` finds each PDF in the samples
folder and skips, with the reason, when it is absent.
"""

from collections.abc import Callable

import pytest

from galley.model import BlockKind, BlocksFile, ChangeReason

pytestmark = [pytest.mark.whole_book, pytest.mark.timeout(900)]

# Structure spec section 32, the table of "Whole-book tests": list items,
# those with the label "—", and list_marker changes.
_LIST_ITEMS = {"turney": (0, 0, 0), "haynes": (11, 6, 6)}
# The same table: the contents page, its entries, those with a page number
# and those with a heading reference.
_CONTENTS_PAGE = {"turney": 10, "haynes": 8}
_CONTENTS = {"turney": (16, 16, 16), "haynes": (22, 21, 22)}


@pytest.mark.parametrize("book", ["turney", "haynes"])
def test_owner_book_list_items_labels_and_list_marker_changes(
    owner_book_run: Callable[[str], BlocksFile], book: str
) -> None:
    blocks = owner_book_run(book)
    items = tuple(b for b in blocks.blocks if b.kind is BlockKind.LIST_ITEM)
    assert (
        len(items),
        sum(item.label == "—" for item in items),
        sum(c.reason is ChangeReason.LIST_MARKER for c in blocks.word_changes),
    ) == _LIST_ITEMS[book]


@pytest.mark.parametrize("book", ["turney", "haynes"])
def test_owner_book_contents_entries_of_depth_1_with_page_numbers_and_links(
    owner_book_run: Callable[[str], BlocksFile], book: str
) -> None:
    blocks = owner_book_run(book)
    on_page = tuple(
        block
        for block in blocks.blocks
        if block.origin[0].page_index == _CONTENTS_PAGE[book]
    )
    entries = tuple(b for b in on_page if b.kind is BlockKind.CONTENTS_ENTRY)
    headings = frozenset(b.id for b in blocks.blocks if b.kind is BlockKind.HEADING)
    assert (
        len(entries),
        sum(entry.page_number is not None for entry in entries),
        sum(entry.heading_ref in headings for entry in entries),
    ) == _CONTENTS[book]
    assert {entry.level for entry in entries} == {1}


@pytest.mark.parametrize("book", ["turney", "haynes"])
def test_owner_book_contents_title_is_the_one_level_1_heading_of_its_page(
    owner_book_run: Callable[[str], BlocksFile], book: str
) -> None:
    blocks = owner_book_run(book)
    assert (
        sum(
            block.kind is BlockKind.HEADING and block.level == 1
            for block in blocks.blocks
            if block.origin[0].page_index == _CONTENTS_PAGE[book]
        )
        == 1
    )
