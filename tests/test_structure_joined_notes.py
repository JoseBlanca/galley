"""Tests of the plan wrong-links, work package 3, and of its review:
footnotes the OCR read as one (docs/specs/structure.md, section 11,
"Where a note starts", "Two notes on one line" and "Sure links").

The unit tests write a page's note lines by hand, made up in the form of
Domesday's notes. The excerpt tests run on domesday_joined_notes; the
expected notes and references of each page are those of its file in
tests/fixtures/expected/wrong_links/, read from the page image.
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
from galley.structure._markers import Reference, ReferenceForm
from galley.structure._measures import Edges
from galley.structure._notes import page_notes
from galley.structure._references import (
    Candidate,
    Link,
    NoteToMatch,
    sure_links,
)

_EXPECTED = Path(__file__).parent / "fixtures" / "expected" / "wrong_links"

# A made-up band: 4 pt a character, 3 pt between words, from 30 to 300 pt.
_CHAR_PT = 4.0
_SPACE_PT = 3.0
_EDGES = Edges(30.0, 300.0)
_LEFT_PT = 30.0
_FULL = 300.0


def _line(
    text: str, top: float, x1: float | None = None, x0: float = _LEFT_PT
) -> PlacedLine:
    """A note line of `text` from the band's left edge; "|NN|" between two
    words sets a gap of NN pt there. It ends at `x1` when given, its last
    word moved there."""
    words: list[Word] = []
    left = x0
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
    box = Box(x0, top, words[-1].box.x1, top + 8.0)
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


def test_number_starting_a_line_after_no_sentence_end_starts_no_note() -> None:
    # Domesday's page 445: "…post et modo 2...et" / "2 carucae possunt…".
    assert _notes(
        _line("1 Thus, D. B. ii. 39: 'Tunc 4 carucae post et modo 2...et", 10.0, _FULL),
        _line("2 carucae possunt restaurari.' To use our symbols", 20.0),
    ) == (
        (
            "1 Thus, D. B. ii. 39: 'Tunc 4 carucae post et modo 2...et "
            "2 carucae possunt restaurari.' To use our symbols"
        ),
    )


def test_number_starting_a_line_after_a_sentence_end_starts_a_note() -> None:
    assert _notes(
        _line("1 Thus, D. B. ii. 39: 'Tunc 4 carucae post et modo.'", 10.0, _FULL),
        _line("2 carucae possunt restaurari.' To use our symbols", 20.0),
    ) == (
        "1 Thus, D. B. ii. 39: 'Tunc 4 carucae post et modo.'",
        "2 carucae possunt restaurari.' To use our symbols",
    )


def _notes_of(*regions: tuple[PlacedLine, ...]) -> tuple[str, ...]:
    """The texts of the notes `page_notes` cuts from the band regions."""
    return tuple(
        " ".join(word.text for line in note.lines for word in line.line.words)
        for note in page_notes(regions, frozenset())
    )


def test_marker_one_confused_digit_from_the_next_value_starts_a_note() -> None:
    # Domesday's page 504: notes 5 and 6 side by side, the 6 read "8" 9.9
    # pt after the note before.
    assert _notes(
        _line("5 D. B. iv. 3-4, 9, 15 (Chinbrige). |9.9| 8 D. B. iv. 61-2-3.", 10.0)
    ) == ("5 D. B. iv. 3-4, 9, 15 (Chinbrige).", "8 D. B. iv. 61-2-3.")


def test_marker_two_values_past_the_next_after_8_pt_starts_no_note() -> None:
    assert _notes(
        _line("5 D. B. iv. 3-4, 9, 15 (Chinbrige). |9.9| 9 D. B. iv. 61-2-3.", 10.0)
    ) == ("5 D. B. iv. 3-4, 9, 15 (Chinbrige). 9 D. B. iv. 61-2-3.",)


def test_line_under_a_row_after_no_sentence_end_starts_no_note() -> None:
    assert _notes(
        _line("1 D. B. i. 41. |19| 2 Stat. of Westminster, c. 3, and of", 10.0, _FULL),
        _line("3 Edward I. c. 4.", 20.0),
    ) == (
        "1 D. B. i. 41.",
        "2 Stat. of Westminster, c. 3, and of 3 Edward I. c. 4.",
    )


_ROW = "1 D. B. i. 41. |19| 2 Ibid. 42."


@pytest.mark.parametrize(
    "text",
    [
        # A marker of two characters.
        "12 Edward I. c. 4.",
        # A marker glued to its word.
        "5Edward I. c. 4.",
        # A marker before a word in lower case.
        "5 hidae et 4 car.",
    ],
    ids=["two_characters", "glued", "lower_case"],
)
def test_line_under_a_row_without_a_lone_marker_before_a_capital_starts_no_note(
    text: str,
) -> None:
    assert _notes(_line(_ROW, 10.0), _line(text, 20.0)) == (
        "1 D. B. i. 41.",
        f"2 Ibid. 42. {text}",
    )


def test_sign_under_a_short_line_looks_ahead_in_its_own_line() -> None:
    # Domesday's page 169: "*" for 4 under a short line, and 5 and 6 on
    # its own line, the page's last.
    assert _notes(
        _line("3 D. B. ii. 404 b.", 10.0),
        _line("* D. B. ii. 291 b. |23| 5 D. B. ii. 24 b. |22| 6 D. B. ii. 438.", 20.0),
    ) == (
        "3 D. B. ii. 404 b.",
        "* D. B. ii. 291 b.",
        "5 D. B. ii. 24 b.",
        "6 D. B. ii. 438.",
    )


def test_stand_in_looks_ahead_to_the_next_band_region() -> None:
    # The note after the stand-in tops the next column, a region of its own.
    assert _notes_of(
        (_line("4 D. B. i. 339, Agetorne. |19| & D. B. i. 174.", 10.0),),
        (_line("6 D. B. i. 163, Bercbelai.", 10.0, x0=200.0),),
    ) == ("4 D. B. i. 339, Agetorne.", "& D. B. i. 174.", "6 D. B. i. 163, Bercbelai.")


def test_stand_in_before_a_marker_starts_no_note() -> None:
    # Domesday's page 500: the "." 70 pt after note 4 stands for 5, but no
    # text follows it before note 6.
    assert _notes(
        _line("4 D. B. i. 364 (Lincoln). |70| . |16| 6 See above.", 10.0)
    ) == (
        "4 D. B. i. 364 (Lincoln). .",
        "6 See above.",
    )


def test_last_stand_in_after_a_note_whose_value_is_its_place_starts_no_note() -> None:
    # Domesday's page 240: the "»" note's value is its place, and the
    # spaced "«" would take the value of the glued one.
    assert _notes(
        _line("8 See above, p. 183.", 10.0),
        _line("» D. B. 38 b, 44. |19| «D. B. C4b. |20| « D. B. 66.", 20.0, x0=42.0),
    ) == ("8 See above, p. 183.", "» D. B. 38 b, 44. «D. B. C4b. « D. B. 66.")


@pytest.mark.parametrize(
    "text",
    [
        # The word "A", not a stand-in, before a note 6.
        "4 D. B. i. 339. |19| A Treatise, p. 3. |19| 6 Ibid. 4.",
        # A stand-in after a word that ends no sentence.
        "4 D. B. i. 339, Agetorne |19| & D. B. i. 174. |19| 6 Ibid. 4.",
        # A word of two letters.
        "4 This we can not find. |19| If Kent were. |19| 6 Ibid. 4.",
    ],
    ids=["word_a", "no_sentence_end", "two_letters"],
)
def test_word_that_is_no_stand_in_between_two_notes_starts_no_note(
    text: str,
) -> None:
    notes = _notes(_line(text, 10.0))
    assert len(notes) == 2
    assert notes[1] == "6 Ibid. 4."


def test_last_stand_in_before_a_word_in_lower_case_starts_no_note() -> None:
    assert _notes(_line("1 D. B. i. 154. |30| - and so on.", 10.0)) == (
        "1 D. B. i. 154. - and so on.",
    )


def _sign_links(linked: tuple[int, ...], guessed: frozenset[int]) -> tuple[int, ...]:
    """The notes whose sign link `sure_links` keeps, of one page's three
    notes 1 to 3, the notes `linked` each linked to a sign "^", those at
    `guessed` started by a row of notes."""
    notes = tuple(NoteToMatch(place, 0, place + 1) for place in range(3))
    links = tuple(
        Link(
            Candidate(
                0, word, 0, Reference("Gummere", "^", "", ReferenceForm.SIGN, None)
            ),
            note,
        )
        for word, note in enumerate(linked)
    )
    return tuple(link.note for link in sure_links(notes, links, frozenset(), guessed))


def test_sign_to_the_note_before_a_note_under_a_row_is_unlinked_alone() -> None:
    # Haskins' page 56: notes 1 and 2 on a row, 3 under it (rule 6); the
    # reference to 2 is lost, and the sign that refers to 3 took 2.
    assert _sign_links((0, 1), frozenset({2})) == (0,)


def test_signs_to_both_notes_of_a_cut_keep_their_links() -> None:
    # Haskins' page 29: the same row, each note with its sign.
    assert _sign_links((0, 1, 2), frozenset({2})) == (0, 1, 2)


def test_sign_with_no_note_started_by_a_row_keeps_its_link() -> None:
    assert _sign_links((0, 1), frozenset()) == (0, 1)


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
@pytest.mark.parametrize("page", [0, 1, 2, 3, 4, 5, 6, 7, 8, 9])
def test_each_printed_note_is_a_note_of_its_own(
    excerpt_books: frozendict[str, BookFolder], page: int
) -> None:
    blocks = read_blocks(excerpt_books[_EXCERPT].blocks_json)
    printed = tuple(note["number"] for note in _expected(page)["notes"])
    assert _page_numbers(blocks, page) == printed


@pytest.mark.pandoc
@pytest.mark.tesseract
@pytest.mark.parametrize("page", [6, 7, 8, 9])
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
