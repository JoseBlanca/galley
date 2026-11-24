"""Tests of the plan wrong-links, work package 3: footnotes the OCR read as
one (docs/specs/structure.md, section 11, "Where a note starts" and
"Two notes on one line").

The unit tests write a page's note lines by hand, made up in the form of
Domesday's notes. The excerpt tests run on domesday_joined_notes; the
expected notes and references of each page are those of its file in
tests/fixtures/expected/wrong_links/, read from the page image. Page 8 of
the excerpt (Domesday's page index 504), whose "6" the OCR reads "8" less
than 10 pt after the note before, stays one note, and page 7 (445) is
for the next task; neither is tested here.
"""

import json
from collections.abc import Sequence
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

import pytest

from galley.book_folder import BookFolder
from galley.model import BlocksFile, Box, Line, Note, Word, block_text, read_blocks
from galley.structure._lines import PlacedLine
from galley.structure._measures import Edges
from galley.structure._notes import page_notes

_EXPECTED = Path(__file__).parent / "fixtures" / "expected" / "wrong_links"

# A made-up band: 4 pt a character, 3 pt between words, from 30 to 300 pt.
_CHAR_PT = 4.0
_SPACE_PT = 3.0
_EDGES = Edges(30.0, 300.0)
_LEFT_PT = 30.0
_FULL = 300.0


def _line(text: str, top: float, x1: float | None = None) -> PlacedLine:
    """A note line of `text` from the band's left edge; "|NN|" between two
    words sets a gap of NN pt there. It ends at `x1` when given, its last
    word moved there."""
    words: list[Word] = []
    left = _LEFT_PT
    gap = 0.0
    for part in text.split(" "):
        if part.startswith("|") and part.endswith("|"):
            gap = float(part.strip("|"))
            continue
        if words:
            left += gap or _SPACE_PT
        right = left + _CHAR_PT * len(part)
        words.append(Word(part, Box(left, top, right, top + 8.0), None))
        left = right
        gap = 0.0
    if x1 is not None:
        last = words[-1]
        width = last.box.x1 - last.box.x0
        words[-1] = Word(last.text, Box(x1 - width, top, x1, top + 8.0), None)
    box = Box(_LEFT_PT, top, words[-1].box.x1, top + 8.0)
    return PlacedLine(0, Line(box, tuple(words)), _EDGES, _EDGES)


def _notes(*lines: PlacedLine) -> tuple[str, ...]:
    """The texts of the notes `page_notes` cuts from one band region."""
    return tuple(
        " ".join(word.text for line in note.lines for word in line.line.words)
        for note in page_notes((lines,), frozenset())
    )


def test_marker_reading_the_next_value_after_a_quotation_starts_a_note() -> None:
    # Domesday's page 177: the OCR's line holds the end of note 2 and the
    # start of note 3, at the gap between two words.
    assert _notes(
        _line("1 D. B. i. 4 b.", 10.0),
        _line("2 D. B. i. 129 b: 'Postea tenuit de Rege.' 3 But, as in general", 20.0),
    ) == (
        "1 D. B. i. 4 b.",
        "2 D. B. i. 129 b: 'Postea tenuit de Rege.'",
        "3 But, as in general",
    )


def test_next_value_after_an_abbreviation_and_a_word_gap_starts_no_note() -> None:
    assert _notes(_line("1 D. B. i. 2 D. B. ii. 5.", 10.0)) == (
        "1 D. B. i. 2 D. B. ii. 5.",
    )


def test_next_value_after_a_wide_gap_before_a_sign_starts_a_note() -> None:
    # Domesday's page 52: "4 Æthelb. 26." read "4 ^thelb. 26.".
    assert _notes(_line("3 D. B. i. 136, Sandone. |17| 4 ^thelb. 26.", 10.0)) == (
        "3 D. B. i. 136, Sandone.",
        "4 ^thelb. 26.",
    )


def test_sign_between_a_note_and_the_number_after_the_next_starts_a_note() -> None:
    # Domesday's page 440: "4 … & …" then "6": the "&" is the misread 5.
    assert _notes(
        _line("4 D. B. i. 339, Agetorne. |19| & D. B. i. 174.", 10.0),
        _line("6 D. B. i. 163, Bercbelai.", 20.0),
    ) == ("4 D. B. i. 339, Agetorne.", "& D. B. i. 174.", "6 D. B. i. 163, Bercbelai.")


def test_sign_before_a_note_that_reads_the_next_value_starts_no_note() -> None:
    assert _notes(
        _line("4 D. B. i. 339, Agetorne. |19| & D. B. i. 174.", 10.0),
        _line("5 D. B. i. 163, Bercbelai.", 20.0),
    ) == ("4 D. B. i. 339, Agetorne. & D. B. i. 174.", "5 D. B. i. 163, Bercbelai.")


def test_dash_after_a_wide_gap_as_the_page_last_starts_a_note() -> None:
    # Domesday's page 213: "1 D. B. i. 154. - D. B. i. 262 b.", the 2 read
    # as a dash.
    assert _notes(_line("1 D. B. i. 154. |30| - D. B. i. 262 b.", 10.0)) == (
        "1 D. B. i. 154.",
        "- D. B. i. 262 b.",
    )


def test_dash_after_a_narrower_gap_as_the_page_last_starts_no_note() -> None:
    assert _notes(_line("1 D. B. i. 154. |15| - D. B. i. 262 b.", 10.0)) == (
        "1 D. B. i. 154. - D. B. i. 262 b.",
    )


def test_sign_under_a_short_line_and_notes_on_a_row_start_their_notes() -> None:
    # Domesday's page 517: "4" read "*" under a short line, before a 5 read
    # "6" on its own line; then "6" under that row of two notes.
    assert _notes(
        _line("3 K. 986-988 (v. 14-21); B. i. 55-9, 64.", 10.0),
        _line("* Plummer, Bede, ii. 217. |30| 6 K. 917 (iv. 165).", 20.0, _FULL),
        _line("6 D. B. i. 66 b, 67.", 30.0),
    ) == (
        "3 K. 986-988 (v. 14-21); B. i. 55-9, 64.",
        "* Plummer, Bede, ii. 217.",
        "6 K. 917 (iv. 165).",
        "6 D. B. i. 66 b, 67.",
    )


# Excerpt tests.

_EXCERPT = "domesday_joined_notes"
# The characters of a note's start compared, as in
# test_structure_note_links.py.
_START_CHARACTERS = 20


def _expected(page: int) -> dict[str, Any]:
    return json.loads(
        (_EXPECTED / f"{_EXCERPT}_page{page}.json").read_text(encoding="utf-8")
    )["expected"]


def _note_text(note: Note) -> str:
    return " ".join(block_text(block) for block in note.blocks)


def _most_alike(text: str, printed: Sequence[dict[str, str]]) -> str:
    """The number of the printed note whose start is most alike that of
    `text`."""
    return max(
        printed,
        key=lambda note: SequenceMatcher(
            None,
            text[:_START_CHARACTERS].lower(),
            note["text"][:_START_CHARACTERS].lower(),
        ).ratio(),
    )["number"]


def _page_numbers(blocks: BlocksFile, page: int) -> tuple[str, ...]:
    """The printed number of each note galley starts on the page, in order."""
    printed = _expected(page)["notes"]
    return tuple(
        _most_alike(_note_text(note), printed)
        for note in blocks.notes
        if note.origin[0].page_index == page
    )


@pytest.mark.pandoc
@pytest.mark.tesseract
@pytest.mark.parametrize("page", [0, 1, 2, 3, 4, 5, 6, 9])
def test_each_printed_note_is_a_note_of_its_own(
    excerpt_books: frozendict[str, BookFolder], page: int
) -> None:
    blocks = read_blocks(excerpt_books[_EXCERPT].blocks_json)
    printed = tuple(note["number"] for note in _expected(page)["notes"])
    assert _page_numbers(blocks, page) == printed


@pytest.mark.pandoc
@pytest.mark.tesseract
@pytest.mark.parametrize("page", [6, 9])
def test_reference_links_the_note_of_its_number(
    excerpt_books: frozendict[str, BookFolder], page: int
) -> None:
    blocks = read_blocks(excerpt_books[_EXCERPT].blocks_json)
    printed = _expected(page)["notes"]
    notes = {note.id: note for note in blocks.notes}
    linked = tuple(
        (block.spans[number - 1].text.rstrip(), span.text, notes[span.note_ref])
        for block in blocks.blocks
        if any(origin.page_index == page for origin in block.origin)
        for number, span in enumerate(block.spans)
        if span.note_ref is not None and number > 0
    )
    for reference in _expected(page)["references"]:
        found = tuple(
            _most_alike(_note_text(note), printed)
            for before, text, note in linked
            if before.endswith(reference["word"]) and text == reference["reference"]
        )
        assert found == (reference["note"],), reference
