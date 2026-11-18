"""Excerpt tests of the plan stray-text for the stream structure: running
heads compared up to 14 letters apart (docs/specs/structure.md, section 3,
"Heads of different lengths") and a reference followed by punctuation
(section 11, "References"). The expected output of each page is that of
its file in tests/fixtures/expected/stray_text/, transcribed from the page
rendered at 300 dpi. A test whose work package has not landed is a strict
xfail naming it; the task that makes it pass removes the mark."""

import json
from pathlib import Path
from typing import Any

import pytest

from galley.book_folder import BookFolder
from galley.model import BlockKind, RemovalReason, block_text, read_blocks

_EXPECTED = Path(__file__).parent / "fixtures" / "expected" / "stray_text"

_TASK_3_2 = (
    "task 3.2 of docs/plans/stray-text.md: the survey's length limit and the "
    "reference candidates"
)


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
@pytest.mark.xfail(strict=True, reason=_TASK_3_2)
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
