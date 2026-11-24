"""Whole-book tests of lists and the printed contents on the owner's two
modern books (docs/specs/structure.md, section 32, "Whole-book tests").

The books are copyrighted: these tests count what galley gives on them and
never quote their text. `owner_book_run` finds each PDF in the samples
folder and skips, with the reason, when it is absent.
"""

from collections.abc import Callable
from difflib import SequenceMatcher

import pytest

from galley.model import BlockKind, BlocksFile, ChangeReason, block_text

pytestmark = [pytest.mark.whole_book, pytest.mark.timeout(900)]

# Structure spec section 32, the table of "Whole-book tests": list items,
# those with the label "—", and list_marker changes.
_LIST_ITEMS = {"turney": (0, 0, 0), "haynes": (11, 6, 6)}
# The same table: the contents page, its entries, those with a page number
# and those with a heading reference.
_CONTENTS_PAGE = {"turney": 10, "haynes": 8}
_CONTENTS = {"turney": (16, 16, 16), "haynes": (22, 21, 22)}
# The chapters among the linked entries: Turney's 10 and Haynes' 16.
_CHAPTERS = {"turney": 10, "haynes": 16}


@pytest.mark.parametrize("book", ["turney", "haynes"])
def test_owner_book_list_items_labels_and_list_marker_changes(
    owner_book_run: Callable[[str], BlocksFile], book: str
) -> None:
    blocks = owner_book_run(book)
    # Counts made first, so that a failure prints no text of the owner's
    # books (pytest shows the arguments of a call in an assert).
    items = tuple(b for b in blocks.blocks if b.kind is BlockKind.LIST_ITEM)
    counts = (
        len(items),
        sum(item.label == "—" for item in items),
        sum(c.reason is ChangeReason.LIST_MARKER for c in blocks.word_changes),
    )
    assert counts == _LIST_ITEMS[book]


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
    counts = (
        len(entries),
        sum(entry.page_number is not None for entry in entries),
        sum(entry.heading_ref in headings for entry in entries),
    )
    levels = frozenset(entry.level for entry in entries)
    assert counts == _CONTENTS[book]
    assert levels == {1}


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


# Structure spec section 32, the same table: chapter entries without a
# label, and linked entries whose title differs from its heading's words
# (section 30, rules 11 and 12). Two words agree as rule 11 has it: the
# ratio of their case-folded cores is at least 0.7.
_AGREE_MIN_RATIO = 0.7


def _core(word: str) -> str:
    folded = word.casefold()
    while folded and not folded[-1].isalnum():
        folded = folded[:-1]
    return folded


def _agree(first: str, second: str) -> bool:
    ratio = SequenceMatcher(None, _core(first), _core(second), autojunk=False).ratio()
    return ratio >= _AGREE_MIN_RATIO


@pytest.mark.parametrize("book", ["turney", "haynes"])
def test_owner_book_chapter_entries_have_labels_and_their_headings_words(
    owner_book_run: Callable[[str], BlocksFile], book: str
) -> None:
    blocks = owner_book_run(book)
    by_id = {block.id: block for block in blocks.blocks}
    linked = tuple(
        (block, by_id[block.heading_ref])
        for block in blocks.blocks
        if block.kind is BlockKind.CONTENTS_ENTRY and block.heading_ref is not None
    )
    chapter_entries = tuple(
        entry
        for entry, heading in linked
        if heading.label is not None and heading.label.casefold().startswith("chapter")
    )
    chapter_count = len(chapter_entries)
    unlabelled_count = sum(1 for entry in chapter_entries if entry.label is None)
    differing_count = sum(
        1
        for entry, heading in linked
        for title, words in ((block_text(entry).split(), block_text(heading).split()),)
        if len(title) != len(words)
        or not _agree(title[0], words[0])
        or not _agree(title[-1], words[-1])
    )
    assert chapter_count == _CHAPTERS[book]
    assert unlabelled_count == 0
    assert differing_count == 0
