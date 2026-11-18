"""Tests of structure's notes collected at the back for the plan
owner-books (docs/specs/structure.md, section 6, rule 3, and section 12;
the unit tests of section 26): a hanging number starts a paragraph, a
bare number is an endnote marker, and the endnote section is cut into
note groups whose notes are linked to their own chapter.

Every page is written by hand: a word is 5 pt wide per character and 10
pt high, with one character's width between words. Body lines lie 15 pt
apart; the notes' lines lie 12 pt apart, Turney's 0.8 pitch.
"""

from galley.model import (
    BlockKind,
    BlocksFile,
    Box,
    Line,
    LinesFile,
    NoteKind,
    PageLayout,
    Region,
    Word,
    block_text,
)
from galley.structure import make_blocks

_HASH = "a" * 64
_NO_WORDS: frozenset[str] = frozenset()
_CHAR_PT = 5.0
_WORD_HEIGHT_PT = 10.0
_PITCH_PT = 15.0
_NOTE_PITCH_PT = 12.0
# Structure spec section 26: the notes' text edge at 251 pt, their numbers
# hung at 234 pt, 17 pt left of it.
_TEXT_EDGE_PT = 251.0
_HUNG_PT = 234.0


def _words_at(text: str, x0: float, top: float) -> tuple[Word, ...]:
    words = []
    left = x0
    for part in text.split(" "):
        right = left + _CHAR_PT * len(part)
        words.append(Word(part, Box(left, top, right, top + _WORD_HEIGHT_PT), None))
        left = right + _CHAR_PT
    return tuple(words)


def _box(boxes: tuple[Box, ...]) -> Box:
    return Box(
        min(box.x0 for box in boxes),
        min(box.top for box in boxes),
        max(box.x1 for box in boxes),
        max(box.bottom for box in boxes),
    )


def _line(text: str, x0: float, top: float) -> Line:
    words = _words_at(text, x0, top)
    return Line(_box(tuple(word.box for word in words)), words)


def _region(*lines: Line) -> Region:
    return Region(_box(tuple(line.box for line in lines)), lines)


def _lines_of(*pages: PageLayout) -> LinesFile:
    return LinesFile(source_pdf_sha256=_HASH, pages=pages, rereads=())


def _texts(blocks: BlocksFile) -> tuple[str, ...]:
    return tuple(block_text(block) for block in blocks.blocks)


def _endnotes(blocks: BlocksFile) -> tuple[tuple[str, str], ...]:
    """Each endnote's marker and the text of its blocks, joined by " / "."""
    return tuple(
        (note.marker, " / ".join(block_text(block) for block in note.blocks))
        for note in blocks.notes
        if note.kind is NoteKind.ENDNOTE
    )


# The lines of a hung note: its number hung left of the text edge, then a
# full line and a short last line at the text edge. The full lines end at
# 391 pt, the short ones at 331.
def _hung_note(
    number: str, top: float, hung: float = _HUNG_PT, x0: float = _TEXT_EDGE_PT
) -> tuple[Line, ...]:
    return (
        _line(f"{number} Compare the note which runs", hung, top),
        _line("on over a full line of the", x0, top + _NOTE_PITCH_PT),
        _line("note ends here.", x0, top + 2 * _NOTE_PITCH_PT),
    )


def _hung_notes(
    numbers: tuple[str, ...], top: float = 70.0, hung: float = _HUNG_PT
) -> tuple[Line, ...]:
    return tuple(
        line
        for position, number in enumerate(numbers)
        for line in _hung_note(number, top + 3 * _NOTE_PITCH_PT * position, hung)
    )


def _note_texts(numbers: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(
        f"{number} Compare the note which runs on over a full line of the "
        "note ends here."
        for number in numbers
    )


# Spec section 6, rule 3: a hanging number starts a paragraph.


def test_hanging_number_starts_a_paragraph_at_each_note_of_a_region() -> None:
    # Twelve lines, eight at the text edge (251 pt), four hung at 234 pt.
    numbers = ("8", "9", "10", "11")
    page = PageLayout(0, (_region(*_hung_notes(numbers)),), ())
    blocks = make_blocks(_lines_of(page), _NO_WORDS, workers=1)
    assert _texts(blocks) == _note_texts(numbers)


def test_hanging_number_3_pt_left_of_the_text_edge_starts_no_paragraph() -> None:
    numbers = ("8", "9", "10", "11")
    page = PageLayout(0, (_region(*_hung_notes(numbers, hung=248.0)),), ())
    blocks = make_blocks(_lines_of(page), _NO_WORDS, workers=1)
    assert _texts(blocks) == (" ".join(_note_texts(numbers)),)


def test_hanging_number_in_a_region_of_2_other_lines_starts_no_paragraph() -> None:
    # Two hung lines and two at the text edge: the region has no text edge.
    lines = (*_hung_note("8", 70.0)[:2], *_hung_note("9", 106.0)[:2])
    page = PageLayout(0, (_region(*lines),), ())
    blocks = make_blocks(_lines_of(page), _NO_WORDS, workers=1)
    assert len(blocks.blocks) == 1


def test_hanging_number_starts_a_paragraph_at_a_page_break() -> None:
    # Page 0's last line is a full one; page 1 opens with note 10.
    first = _hung_notes(("8", "9"))
    full_last = (*first[:-1], _line("on over a full line of the", _TEXT_EDGE_PT, 130))
    pages = (
        PageLayout(0, (_region(*full_last),), ()),
        PageLayout(1, (_region(*_hung_notes(("10", "11"))),), ()),
    )
    blocks = make_blocks(_lines_of(*pages), _NO_WORDS, workers=1)
    assert _texts(blocks)[-2:] == _note_texts(("10", "11"))


def test_hanging_number_after_a_hyphen_starts_no_paragraph() -> None:
    notes = _hung_notes(("8", "9"))
    hyphened = (*notes[:2], _line("note ends with a hyphen-", _TEXT_EDGE_PT, 94))
    page = PageLayout(0, (_region(*hyphened, *notes[3:]),), ())
    blocks = make_blocks(_lines_of(page), _NO_WORDS, workers=1)
    assert len(blocks.blocks) == 1


# Spec section 12: a bare number is an endnote marker in a run from 1,
# outside the contents pages.


def _bare_notes_page(index: int, first: int, count: int) -> PageLayout:
    numbers = tuple(str(number) for number in range(first, first + count))
    return PageLayout(index, (_region(*_hung_notes(numbers)),), ())


def test_bare_number_run_from_1_makes_an_endnote_section() -> None:
    page = _bare_notes_page(0, 1, 9)
    blocks = make_blocks(_lines_of(page), _NO_WORDS, workers=1)
    assert _endnotes(blocks) == tuple(
        (
            str(number),
            "Compare the note which runs on over a full line of the note ends here.",
        )
        for number in range(1, 10)
    )
    assert blocks.blocks == ()


def test_bare_number_run_from_139_makes_no_endnote_section() -> None:
    page = _bare_notes_page(0, 139, 9)
    blocks = make_blocks(_lines_of(page), _NO_WORDS, workers=1)
    assert not blocks.notes
    assert len(blocks.blocks) == 9


def test_bare_number_run_on_a_contents_page_makes_no_endnote_section() -> None:
    page = _bare_notes_page(0, 1, 9)
    blocks = make_blocks(
        _lines_of(page), _NO_WORDS, contents_pages=frozenset({0}), workers=1
    )
    assert not blocks.notes
    assert len(blocks.blocks) == 9


def test_bare_number_that_does_not_rise_is_a_later_block_of_its_note() -> None:
    # "3" after "4" (an OCR misreading of "5") starts no run, since it
    # does not read 1: it is a later block of note 4, and "6" goes on.
    numbers = ("1", "2", "3", "4", "3", "6", "7", "8", "9")
    page = PageLayout(0, (_region(*_hung_notes(numbers)),), ())
    blocks = make_blocks(_lines_of(page), _NO_WORDS, workers=1)
    endnotes = _endnotes(blocks)
    assert tuple(marker for marker, _ in endnotes) == (
        *("1", "2", "3", "4"),
        *("6", "7", "8", "9"),
    )
    assert endnotes[3][1].count(" / ") == 1


# Spec section 12: the section reaches back over the paragraphs before its
# first marker, up to the first heading block that is not a group heading.


def _centred(text: str, top: float) -> Line:
    """A line centred in the notes' column, from 234 to 391 pt."""
    width = _CHAR_PT * len(text)
    return _line(text, (234 + 391) / 2 - width / 2, top)


def test_endnote_section_reaches_back_over_a_group_heading_to_the_notes_title() -> None:
    # "NOTES" and "Introduction" are centred, 3 pitches apart, above the
    # first group's notes 1 to 9; "Chapter One" heads the second group.
    first = _hung_notes(tuple(str(n) for n in range(1, 10)), top=100.0)
    second = _hung_notes(tuple(str(n) for n in range(1, 10)), top=70.0)
    pages = (
        PageLayout(
            0,
            (
                _region(_centred("NOTES", 40.0)),
                _region(_centred("Introduction", 85.0), *first),
            ),
            (),
        ),
        PageLayout(
            1,
            (_region(_centred("Chapter One", 40.0), *second),),
            (),
        ),
    )
    blocks = make_blocks(_lines_of(*pages), _NO_WORDS, workers=1)
    assert _texts(blocks) == ("NOTES",)
    assert blocks.blocks[0].kind is BlockKind.HEADING
    assert _endnotes(blocks)[0][1].startswith("Introduction")
