"""Excerpt tests of the plan stray-text for the stream structure: running
heads compared up to 14 letters apart (docs/specs/structure.md, section 3,
"Heads of different lengths"), a reference followed by punctuation
(section 11, "References"), and a heading alone above a table in small
type and a signature mark beside the table (sections 14 and 4). The
expected output of each page is that of its file in
tests/fixtures/expected/stray_text/, transcribed from the page rendered
at 300 dpi. A test whose work package has not landed is a strict
xfail naming it; the task that makes it pass removes the mark."""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from galley.book_folder import BookFolder
from galley.model import BlockKind, RemovalReason, block_text, read_blocks

_EXPECTED = Path(__file__).parent / "fixtures" / "expected" / "stray_text"


def _expected(excerpt: str, page: int) -> dict[str, Any]:
    return json.loads(
        (_EXPECTED / f"{excerpt}_page{page}.json").read_text(encoding="utf-8")
    )["expected"]


@pytest.mark.pandoc
@pytest.mark.tesseract
@pytest.mark.parametrize("page", [2, 8])
def test_head_damaged_beyond_eight_letters_is_removed_as_a_running_head(
    excerpt_books: frozendict[str, BookFolder], page: int
) -> None:
    blocks = read_blocks(excerpt_books["gierke_notes_heads"].blocks_json)
    expected = _expected("gierke_notes_heads", page)
    assert expected["running_head"] in [
        removal.text
        for removal in blocks.removals
        if removal.page_index == page and removal.reason is RemovalReason.RUNNING_HEAD
    ]
    assert not [
        block
        for block in blocks.blocks
        if block.kind is BlockKind.HEADING and block.origin[0].page_index == page
    ]


@pytest.mark.pandoc
@pytest.mark.tesseract
def test_sign_followed_by_punctuation_is_linked_to_its_note(
    excerpt_books: frozendict[str, BookFolder],
) -> None:
    blocks = read_blocks(excerpt_books["domesday_notes"].blocks_json)
    expected = _expected("domesday_notes", 2)
    notes = {note.id: note for note in blocks.notes}
    linked = [
        (span.text, block_text(notes[span.note_ref].blocks[0]))
        for block in blocks.blocks
        if block.origin[0].page_index == 2
        for span in block.spans
        if span.note_ref is not None and span.text == expected["split"][1]
    ]
    assert len(linked) == 1
    assert linked[0][1].startswith(expected["note_text_starts"])


# Spec section 11, "References": the notes of Domesday whose reference is
# not linked. 343 on the starting commit of the plan (a0a1675, 18 November
# 2026); 322 with the sign followed by punctuation, which links 21 more,
# each checked on the page image.
# The plan asks for a fall of at least 15: at most 328.
_DOMESDAY_UNREFERENCED_NOTES_AT_MOST = 328


@pytest.mark.whole_book
@pytest.mark.thread_unsafe
@pytest.mark.timeout(900)
def test_whole_book_domesday_signs_followed_by_punctuation_link_their_notes(
    whole_book_run: Callable[[str], BookFolder],
) -> None:
    blocks = read_blocks(whole_book_run("domesdaybook00maituoft").blocks_json)
    unreferenced = sum(1 for note in blocks.notes if not note.referenced)
    assert unreferenced <= _DOMESDAY_UNREFERENCED_NOTES_AT_MOST


# Domesday's page 428 (excerpt page 7): the heading "AVERAGES." alone in the
# body above a table that layout makes a band (section 14, rule 1), and the
# signature mark "26—2" beside the table's "[0", which the text layer boxes
# lower (section 4).


@pytest.mark.pandoc
@pytest.mark.tesseract
def test_heading_alone_above_a_table_in_the_band_is_a_heading(
    excerpt_books: frozendict[str, BookFolder],
) -> None:
    blocks = read_blocks(excerpt_books["domesday_notes"].blocks_json)
    expected = _expected("domesday_notes", 7)
    assert [
        block_text(block)
        for block in blocks.blocks
        if block.kind is BlockKind.HEADING and block.origin[0].page_index == 7
    ] == [expected["heading"]]


@pytest.mark.pandoc
@pytest.mark.tesseract
def test_signature_mark_beside_a_word_boxed_lower_is_removed(
    excerpt_books: frozendict[str, BookFolder],
) -> None:
    blocks = read_blocks(excerpt_books["domesday_notes"].blocks_json)
    expected = _expected("domesday_notes", 7)
    assert [
        removal.text
        for removal in blocks.removals
        if removal.page_index == 7 and removal.reason is RemovalReason.SIGNATURE_MARK
    ] == [expected["signature_mark"]]
