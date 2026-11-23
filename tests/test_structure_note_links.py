"""Excerpt tests of the plan more-note-links, work package 4, for
Domesday's footnotes (docs/specs/structure.md, section 11): a note under a
short line starts at its marker ("Where a note starts", rule 5), a page's
notes are numbered by what their markers read ("Its value"), and the
references the OCR glued to a number, read as a sign, split off as a word
or misread ("References"). The expected output of each page is that of
its file in tests/fixtures/expected/more_note_links/, read from the page
rendered at 200 dpi."""

import json
from pathlib import Path
from typing import Any

import pytest

from galley.book_folder import BookFolder
from galley.model import BlocksFile, Note, block_text, read_blocks

_EXPECTED = Path(__file__).parent / "fixtures" / "expected" / "more_note_links"


def _expected(excerpt: str, page: int) -> dict[str, Any]:
    return json.loads(
        (_EXPECTED / f"{excerpt}_page{page}.json").read_text(encoding="utf-8")
    )["expected"]


def _note_text(note: Note) -> str:
    return " ".join(block_text(block) for block in note.blocks)


def _page_notes(blocks: BlocksFile, page: int) -> tuple[str, ...]:
    return tuple(
        _note_text(note) for note in blocks.notes if note.origin[0].page_index == page
    )


def _linked(blocks: BlocksFile, page: int) -> tuple[tuple[str, str, str], ...]:
    """Each reference of the page in reading order: the text of the span
    before it, its own text and its note's text."""
    notes = {note.id: note for note in blocks.notes}
    return tuple(
        (
            block.spans[number - 1].text if number else "",
            span.text,
            _note_text(notes[span.note_ref]),
        )
        for block in blocks.blocks
        if block.origin[0].page_index == page
        for number, span in enumerate(block.spans)
        if span.note_ref is not None
    )


def _links_to(
    blocks: BlocksFile, page: int, word: str, reference: str
) -> tuple[str, ...]:
    """The texts of the notes linked to `reference` after `word` on the
    page."""
    return tuple(
        note
        for before, text, note in _linked(blocks, page)
        if before.rstrip().endswith(word) and text == reference
    )


@pytest.mark.pandoc
@pytest.mark.tesseract
def test_note_under_a_short_line_starts_at_its_marker_and_takes_its_reference(
    excerpt_books: frozendict[str, BookFolder],
) -> None:
    # Domesday's page 35: "2 A good many cases…" and "8 Inq. Com.…" sit at
    # the band's left edge under short lines; "8" reads 3 misread.
    blocks = read_blocks(excerpt_books["domesday_notes"].blocks_json)
    expected = _expected("domesday_notes", 1)
    assert expected["own_note"] in _page_notes(blocks, 1)
    linked = _links_to(blocks, 1, expected["reference_word"], expected["reference"])
    assert len(linked) == 1
    assert linked[0].startswith(expected["note_of_reference_starts"])


@pytest.mark.pandoc
@pytest.mark.tesseract
def test_sign_between_two_numbers_starts_a_note_and_each_takes_its_reference(
    excerpt_books: frozendict[str, BookFolder],
) -> None:
    # Domesday's page 141: "3 …", "* …" (for 4), "5 …", "6 …", one to a
    # line, "* …" the longest line of the band.
    blocks = read_blocks(excerpt_books["domesday_lists"].blocks_json)
    expected = _expected("domesday_lists", 1)
    assert _page_notes(blocks, 1) == tuple(expected["notes"])
    assert tuple(note for _, _, note in _linked(blocks, 1)) == tuple(expected["notes"])


@pytest.mark.pandoc
@pytest.mark.tesseract
def test_notes_reading_1_and_2_after_a_table_cut_into_notes_take_1_and_2(
    excerpt_books: frozendict[str, BookFolder],
) -> None:
    # Domesday's page 42: the band holds a table's rows cut into five notes
    # before the page's notes 1 and 2; numbered by place they were 6 and 7.
    blocks = read_blocks(excerpt_books["domesday_headings_quotes"].blocks_json)
    for word, reference, note_starts in _expected("domesday_headings_quotes", 5)[
        "references"
    ]:
        linked = _links_to(blocks, 5, word, reference)
        assert len(linked) == 1
        assert linked[0].startswith(note_starts)
