"""Tests of structure's notes collected at the back for the plan
owner-books (docs/specs/structure.md, section 6, rule 3, and section 12;
the unit tests of section 26): a hanging number starts a paragraph, a
bare number is an endnote marker, and the endnote section is cut into
note groups whose notes are linked to their own chapter.

Every page is written by hand: a word is 5 pt wide per character and 10
pt high, with one character's width between words. Body lines lie 15 pt
apart; the notes' lines lie 12 pt apart, Turney's 0.8 pitch.
"""

from dataclasses import replace

import pytest

from galley.model import (
    BlockKind,
    BlocksFile,
    Box,
    Line,
    LinesFile,
    NoteKind,
    Origin,
    PageLayout,
    Region,
    Word,
    block_text,
)
from galley.structure import make_blocks, reference_candidate
from galley.structure._assemble import _links
from galley.structure._endnotes import group_reaches
from galley.structure._markers import Reference, ReferenceForm, endnote_candidate
from galley.structure._notes import Numbering
from galley.structure._references import (
    BodyWord,
    Candidate,
    Link,
    NoteToMatch,
    foreign_signs,
    gap_links,
    match_endnotes,
    with_values_in_order,
)
from galley.structure._unnumbered import Unnumbered, UnnumberedNote

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
    # Spec section 30: no paragraph either; the first line is the run's
    # title, and each hung note a contents entry.
    assert {block.kind for block in blocks.blocks} == {
        BlockKind.HEADING,
        BlockKind.CONTENTS_ENTRY,
    }


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
    assert blocks.notes[0].group == "Introduction"


# Spec section 12: note groups, their headings and the chapter of each.
# The body: a chapter per page, its centred title the page's first line
# (a level-1 heading, the page having no running head), then a paragraph
# whose lines end with the references "word1." to "word9.".

_CHAPTERS = ("Clockwork Garden Story", "Silent Harbour Rebuilt")
# The body's and the Haynes-form notes' column runs from 50 to 300 pt.
_LEFT_PT = 50.0
_RIGHT_PT = 300.0


def _spread(text: str, x0: float, x1: float, top: float) -> Line:
    """A line of the words of `text` spread from `x0` to `x1`."""
    parts = text.split(" ")
    step = (x1 - x0) / len(parts)
    words = tuple(
        Word(
            part,
            Box(
                x0 + step * n,
                top,
                x1 if n == len(parts) - 1 else x0 + step * (n + 1) - 2,
                top + _WORD_HEIGHT_PT,
            ),
            None,
        )
        for n, part in enumerate(parts)
    )
    return Line(_box(tuple(word.box for word in words)), words)


def _chapter_page(
    index: int,
    title: str,
    ends: tuple[str, ...] = tuple(f"word{n}." for n in range(1, 10)),
) -> PageLayout:
    """A chapter's page whose nine full lines end with the words `ends`,
    "word1." to "word9." unless given."""
    width = _CHAR_PT * len(title)
    lines = (
        _spread(title, 175 - width / 2, 175 + width / 2, 50.0),
        _spread("The chapter opens here and", _LEFT_PT + 20, _RIGHT_PT, 85.0),
        *(
            _spread(f"a full line goes on to {end}", _LEFT_PT, _RIGHT_PT, 85.0 + 15 * n)
            for n, end in enumerate(ends, start=1)
        ),
        _spread("and it ends.", _LEFT_PT, 150.0, 235.0),
    )
    return PageLayout(index, (_region(*lines),), ())


def _dotted_notes(top: float) -> tuple[Line, ...]:
    """Haynes' form: notes "1." to "9.", each an indented first line, a full
    line and a short last line, 15 pt apart."""
    return tuple(
        line
        for n in range(1, 10)
        for line in (
            _spread(
                f"{n}. The note of its", _LEFT_PT + 20, _RIGHT_PT, top + 45 * (n - 1)
            ),
            _spread(
                "chapter goes on over a full",
                _LEFT_PT,
                _RIGHT_PT,
                top + 45 * (n - 1) + 15,
            ),
            _spread("line and ends.", _LEFT_PT, 150.0, top + 45 * (n - 1) + 30),
        )
    )


def _group_heading(number: int, title: str, top: float) -> tuple[Line, ...]:
    """A two-line group heading at the left edge."""
    first, *rest = title.split(" ")
    return (
        _spread(f"Chapter {number}. {first}", _LEFT_PT, 160.0, top),
        _spread(" ".join(rest), _LEFT_PT, 140.0, top + _PITCH_PT),
    )


def _links_by_chapter(blocks: BlocksFile) -> tuple[tuple[int, str], ...]:
    """Each reference to an endnote: the page of its block and the marker
    of its note, with the group of the note's group as its number."""
    group_of: dict[str, int] = {}
    group = -1
    for note in blocks.notes:
        if note.group is not None:
            group += 1
        group_of[note.id] = group
    markers = {note.id: note.marker for note in blocks.notes}
    return tuple(
        (
            block.origin[0].page_index,
            f"{group_of[span.note_ref]}:{markers[span.note_ref]}",
        )
        for block in blocks.blocks
        for span in block.spans
        if span.note_ref is not None
    )


def _expected_links(marker: str) -> tuple[tuple[int, str], ...]:
    return tuple((page, f"{page}:{n}{marker}") for page in (0, 1) for n in range(1, 10))


def test_note_groups_link_each_note_to_the_references_of_its_own_chapter() -> None:
    # Two groups of notes "1." to "9." on one page, each under a two-line
    # group heading 1.8 pitches (27 pt) below the note before, the first at
    # the page's top.
    first = (*_group_heading(1, _CHAPTERS[0], 50.0), *_dotted_notes(80.0))
    second_top = first[-1].box.top + 27.0
    second = (
        *_group_heading(2, _CHAPTERS[1], second_top),
        *_dotted_notes(second_top + 30.0),
    )
    pages = (
        _chapter_page(0, _CHAPTERS[0]),
        _chapter_page(1, _CHAPTERS[1]),
        PageLayout(2, (_region(*first, *second),), ()),
    )
    blocks = make_blocks(_lines_of(*pages), _NO_WORDS, workers=1)
    assert _links_by_chapter(blocks) == _expected_links(".")
    assert tuple(note.group for note in blocks.notes if note.group is not None) == (
        f"Chapter 1. {_CHAPTERS[0]}",
        f"Chapter 2. {_CHAPTERS[1]}",
    )
    assert len(_endnotes(blocks)) == 18


def _turney_group(number: int, title: str, top: float) -> tuple[Line, ...]:
    """Turney's form: a group heading hung like a note, "2 Silent ...",
    and notes "1" to "9" hung 17 pt, each of three lines 12 pt apart."""
    heading = _line(f"{number} {title}", _HUNG_PT, top)
    return (heading, *_hung_notes(tuple(str(n) for n in range(1, 10)), top + 27.0))


def test_note_groups_in_turney_form_link_each_note_to_its_own_chapter() -> None:
    # The first group heading starts with a bare "1", as Turney's chapter
    # One does: it is the heading, and no group starts at it.
    first = _turney_group(1, _CHAPTERS[0], 50.0)
    second = _turney_group(2, _CHAPTERS[1], first[-1].box.top + 30.0)
    pages = (
        _chapter_page(0, _CHAPTERS[0]),
        _chapter_page(1, _CHAPTERS[1]),
        PageLayout(2, (_region(*first, *second),), ()),
    )
    blocks = make_blocks(_lines_of(*pages), _NO_WORDS, workers=1)
    assert _links_by_chapter(blocks) == _expected_links("")
    assert tuple(note.group for note in blocks.notes if note.group is not None) == (
        f"1 {_CHAPTERS[0]}",
        f"2 {_CHAPTERS[1]}",
    )


def test_group_heading_left_at_the_end_of_a_note_is_cut_off_it() -> None:
    # The first test's second heading runs on from note 9's short last
    # line, flush left: the paragraph rules do not cut it, the group rule
    # does, and note 9 keeps only its own words.
    first = (*_group_heading(1, _CHAPTERS[0], 50.0), *_dotted_notes(80.0))
    second_top = first[-1].box.top + 27.0
    second = (
        *_group_heading(2, _CHAPTERS[1], second_top),
        *_dotted_notes(second_top + 30.0),
    )
    pages = (
        _chapter_page(0, _CHAPTERS[0]),
        _chapter_page(1, _CHAPTERS[1]),
        PageLayout(2, (_region(*first, *second),), ()),
    )
    blocks = make_blocks(_lines_of(*pages), _NO_WORDS, workers=1)
    assert _endnotes(blocks)[8] == (
        "9.",
        "The note of its chapter goes on over a full line and ends.",
    )


def test_group_heading_at_a_gap_of_1_2_pitches_is_no_heading() -> None:
    # The second heading 18 pt (1.2 pitches) below note 9 stays in it, and
    # its group takes the chapter after the first group's: the links stay.
    first = (*_group_heading(1, _CHAPTERS[0], 50.0), *_dotted_notes(80.0))
    second_top = first[-1].box.top + 18.0
    second = (
        *_group_heading(2, _CHAPTERS[1], second_top),
        *_dotted_notes(second_top + 30.0),
    )
    pages = (
        _chapter_page(0, _CHAPTERS[0]),
        _chapter_page(1, _CHAPTERS[1]),
        PageLayout(2, (_region(*first, *second),), ()),
    )
    blocks = make_blocks(_lines_of(*pages), _NO_WORDS, workers=1)
    assert tuple(note.group for note in blocks.notes if note.group is not None) == (
        f"Chapter 1. {_CHAPTERS[0]}",
    )
    assert _endnotes(blocks)[8][1].endswith(f"Chapter 2. {_CHAPTERS[1]}")


def test_chapter_of_group_is_the_heading_its_title_matches_not_the_next() -> None:
    # The groups are printed in the order of the chapters, but a third
    # chapter "Silent Harbour Rebuilt" comes first in the body: each group
    # takes the heading its title is alike to.
    first = (*_group_heading(1, _CHAPTERS[0], 50.0), *_dotted_notes(80.0))
    second_top = first[-1].box.top + 27.0
    second = (
        *_group_heading(2, _CHAPTERS[1], second_top),
        *_dotted_notes(second_top + 30.0),
    )
    pages = (
        _chapter_page(0, "An Unrelated Opening Chapter"),
        _chapter_page(1, _CHAPTERS[0]),
        _chapter_page(2, _CHAPTERS[1]),
        PageLayout(3, (_region(*first, *second),), ()),
    )
    blocks = make_blocks(_lines_of(*pages), _NO_WORDS, workers=1)
    pages_linked = tuple(page for page, _ in _links_by_chapter(blocks))
    assert pages_linked == (*(1,) * 9, *(2,) * 9)


def test_chapter_of_group_without_heading_is_the_one_after_the_group_before() -> None:
    first = (*_group_heading(1, _CHAPTERS[0], 50.0), *_dotted_notes(80.0))
    second = _dotted_notes(first[-1].box.top + _PITCH_PT)
    pages = (
        _chapter_page(0, _CHAPTERS[0]),
        _chapter_page(1, _CHAPTERS[1]),
        PageLayout(2, (_region(*first, *second),), ()),
    )
    blocks = make_blocks(_lines_of(*pages), _NO_WORDS, workers=1)
    pages_linked = tuple(page for page, _ in _links_by_chapter(blocks))
    assert pages_linked == (*(0,) * 9, *(1,) * 9)


def test_note_group_is_one_when_no_marker_reads_1_again() -> None:
    # Gierke's form: one run "1." to "18." under a centred "NOTES": one
    # group, no group heading, and its notes matched over the whole body.
    notes = tuple(
        line
        for n in range(1, 19)
        for line in (
            _spread(f"{n}. The note which", _LEFT_PT + 20, _RIGHT_PT, 35.0 + 45 * n),
            _spread("goes on over a full", _LEFT_PT, _RIGHT_PT, 50.0 + 45 * n),
            _spread("line and ends.", _LEFT_PT, 150.0, 65.0 + 45 * n),
        )
    )
    later = tuple(
        _spread(f"a full line goes on to word{n}.", _LEFT_PT, _RIGHT_PT, 50.0 + 15 * n)
        for n in range(10, 19)
    )
    pages = (
        _chapter_page(0, _CHAPTERS[0]),
        PageLayout(1, (_region(*later),), ()),
        PageLayout(
            2,
            (_region(_spread("NOTES", 160.0, 190.0, 40.0)), _region(*notes)),
            (),
        ),
    )
    blocks = make_blocks(_lines_of(*pages), _NO_WORDS, workers=1)
    assert not any(note.group for note in blocks.notes)
    assert sum(note.referenced for note in blocks.notes) == 18


def test_heading_block_inside_a_note_group_is_made_a_paragraph_of_its_note() -> None:
    # A centred line between notes 4 and 5, a heading block in the body,
    # is a later block of note 4 and no heading.
    notes = _dotted_notes(80.0)
    centred = _spread("SEE ALSO", 155.0, 195.0, notes[11].box.top + 15)
    later = tuple(
        Line(
            Box(line.box.x0, line.box.top + 30, line.box.x1, line.box.bottom + 30),
            tuple(
                Word(
                    word.text,
                    Box(
                        word.box.x0,
                        word.box.top + 30,
                        word.box.x1,
                        word.box.bottom + 30,
                    ),
                    None,
                )
                for word in line.words
            ),
        )
        for line in notes[12:]
    )
    first = (*_group_heading(1, _CHAPTERS[0], 50.0), *notes[:12], centred, *later)
    second_top = first[-1].box.top + 27.0
    second = (
        *_group_heading(2, _CHAPTERS[1], second_top),
        *_dotted_notes(second_top + 30.0),
    )
    pages = (
        _chapter_page(0, _CHAPTERS[0]),
        _chapter_page(1, _CHAPTERS[1]),
        PageLayout(2, (_region(*first, *second),), ()),
    )
    blocks = make_blocks(_lines_of(*pages), _NO_WORDS, workers=1)
    note_4 = next(note for note in blocks.notes if note.marker == "4.")
    assert tuple((block.kind, block_text(block)) for block in note_4.blocks[1:]) == (
        (BlockKind.PARAGRAPH, "SEE ALSO"),
    )
    assert not any(
        block.kind is BlockKind.HEADING and "SEE" in block_text(block)
        for block in blocks.blocks
    )


def test_bare_number_in_a_section_of_dotted_markers_is_no_marker() -> None:
    # Gierke's form: notes "1." to "9." and, inside note 4, a paragraph
    # starting with a bare "1" hung left of the text (a margin note left in
    # the body): it stays a later block of note 4, and no group starts.
    notes = _dotted_notes(80.0)
    bare = _hung_note("1", 0.0, hung=33.0, x0=_LEFT_PT)
    shifted = tuple(
        Line(
            Box(line.box.x0, top, line.box.x1, top + _WORD_HEIGHT_PT),
            tuple(
                Word(word.text, Box(word.box.x0, top, word.box.x1, top + 10), None)
                for word in line.words
            ),
        )
        for line, top in zip(bare, (230.0, 245.0, 260.0), strict=True)
    )
    later = tuple(
        Line(
            Box(line.box.x0, line.box.top + 45, line.box.x1, line.box.bottom + 45),
            tuple(
                Word(
                    word.text,
                    Box(
                        word.box.x0,
                        word.box.top + 45,
                        word.box.x1,
                        word.box.bottom + 45,
                    ),
                    None,
                )
                for word in line.words
            ),
        )
        for line in notes[12:]
    )
    page = PageLayout(0, (_region(*notes[:12], *shifted, *later),), ())
    blocks = make_blocks(_lines_of(page), _NO_WORDS, workers=1)
    assert tuple(marker for marker, _ in _endnotes(blocks)) == tuple(
        f"{n}." for n in range(1, 10)
    )
    assert not any(note.group for note in blocks.notes)


def test_group_heading_above_a_speck_is_still_the_group_heading() -> None:
    # Turney's page 268: a "/" 5 pt high under the second heading, between
    # it and note 1, is passed over; it stays a block of the note before.
    first = _turney_group(1, _CHAPTERS[0], 50.0)
    second = _turney_group(2, _CHAPTERS[1], first[-1].box.top + 30.0)
    top = second[0].box.top + 14.0
    speck = Line(
        Box(310, top, 313, top + 5), (Word("/", Box(310, top, 313, top + 5), None),)
    )
    pages = (
        _chapter_page(0, _CHAPTERS[0]),
        _chapter_page(1, _CHAPTERS[1]),
        PageLayout(2, (_region(*first, second[0], speck, *second[1:]),), ()),
    )
    blocks = make_blocks(_lines_of(*pages), _NO_WORDS, workers=1)
    assert tuple(note.group for note in blocks.notes if note.group is not None) == (
        f"1 {_CHAPTERS[0]}",
        f"2 {_CHAPTERS[1]}",
    )
    assert _endnotes(blocks)[8][1].endswith(" / /")


def test_bare_number_run_starts_at_a_misread_marker_before_2_3_and_4() -> None:
    # Turney's page 258: the second group's "1" read as "x". It starts a
    # paragraph and a run, its marker "x" as read and its value 1 by its
    # place: the group and its links are kept.
    first = _turney_group(1, _CHAPTERS[0], 50.0)
    heading_top = first[-1].box.top + 30.0
    misread = tuple(
        line
        for position, number in enumerate(("x", *(str(n) for n in range(2, 10))))
        for line in _hung_note(number, heading_top + 27.0 + 36.0 * position)
    )
    second = (_line(f"2 {_CHAPTERS[1]}", _HUNG_PT, heading_top), *misread)
    pages = (
        _chapter_page(0, _CHAPTERS[0]),
        _chapter_page(1, _CHAPTERS[1]),
        PageLayout(2, (_region(*first, *second),), ()),
    )
    blocks = make_blocks(_lines_of(*pages), _NO_WORDS, workers=1)
    markers = tuple(marker for marker, _ in _endnotes(blocks))
    assert markers == (
        *(str(n) for n in range(1, 10)),
        "x",
        *(str(n) for n in range(2, 10)),
    )
    assert tuple(page for page, _ in _links_by_chapter(blocks)) == (
        *(0,) * 9,
        *(1,) * 9,
    )


def test_chapter_of_first_group_without_heading_counts_back_from_the_next() -> None:
    # The body has an opening chapter before the two the groups belong to;
    # the first group has no heading, the second names its chapter: the
    # first takes the chapter before the second's, not the first of all.
    second_top = 80.0 + 27 * _PITCH_PT + 27.0
    notes = (
        *_dotted_notes(80.0),
        *_group_heading(2, _CHAPTERS[1], second_top),
        *_dotted_notes(second_top + 30.0),
    )
    pages = (
        _chapter_page(0, "An Unrelated Opening Chapter"),
        _chapter_page(1, _CHAPTERS[0]),
        _chapter_page(2, _CHAPTERS[1]),
        PageLayout(3, (_region(*notes),), ()),
    )
    blocks = make_blocks(_lines_of(*pages), _NO_WORDS, workers=1)
    pages_linked = tuple(page for page, _ in _links_by_chapter(blocks))
    assert pages_linked == (*(1,) * 9, *(2,) * 9)


def test_later_paragraph_of_note_1_opening_with_i_is_no_misread_marker() -> None:
    # Note 1's second paragraph opens with "I", indented, before notes 2 to
    # 9: it stays a block of note 1, and note 1 is no group heading.
    top = 70.0
    lines = list(_hung_note("1", top))
    top += 3 * _NOTE_PITCH_PT
    lines += [
        _line("I think this is a further", _TEXT_EDGE_PT + 15, top),
        _line("on over a full line of the", _TEXT_EDGE_PT, top + _NOTE_PITCH_PT),
        _line("second paragraph.", _TEXT_EDGE_PT, top + 2 * _NOTE_PITCH_PT),
    ]
    top += 3 * _NOTE_PITCH_PT
    for number in range(2, 10):
        lines += _hung_note(str(number), top)
        top += 3 * _NOTE_PITCH_PT
    blocks = make_blocks(
        _lines_of(PageLayout(0, (_region(*lines),), ())), _NO_WORDS, workers=1
    )
    assert tuple(marker for marker, _ in _endnotes(blocks)) == tuple(
        str(n) for n in range(1, 10)
    )
    assert not any(note.group for note in blocks.notes)


def test_hung_misread_marker_after_note_1_is_no_marker() -> None:
    # The same "I" paragraph hung like a number: the bare number before it
    # reads 1, so it is no misread marker.
    top = 70.0
    lines = list(_hung_note("1", top))
    top += 3 * _NOTE_PITCH_PT
    lines += _hung_note("I", top)
    top += 3 * _NOTE_PITCH_PT
    for number in range(2, 10):
        lines += _hung_note(str(number), top)
        top += 3 * _NOTE_PITCH_PT
    blocks = make_blocks(
        _lines_of(PageLayout(0, (_region(*lines),), ())), _NO_WORDS, workers=1
    )
    assert tuple(marker for marker, _ in _endnotes(blocks)) == tuple(
        str(n) for n in range(1, 10)
    )


def test_short_last_note_at_a_page_top_is_no_group_heading() -> None:
    # Group one's last note, "10.", two lines at the top of page 3, before
    # group two's notes: it stays a note, and no group has a heading.
    last = (
        _spread("10. A short last note of", _LEFT_PT + 20, _RIGHT_PT, 50.0),
        _spread("its group.", _LEFT_PT, 120.0, 65.0),
    )
    pages = (
        _chapter_page(0, _CHAPTERS[0]),
        _chapter_page(1, _CHAPTERS[1]),
        PageLayout(2, (_region(*_dotted_notes(50.0)),), ()),
        PageLayout(3, (_region(*last, *_dotted_notes(95.0)),), ()),
    )
    blocks = make_blocks(_lines_of(*pages), _NO_WORDS, workers=1)
    assert "10." in tuple(marker for marker, _ in _endnotes(blocks))
    assert not any(note.group for note in blocks.notes)


# Spec section 12, "References": a reference that reads another number than
# a note's is left unlinked when the note has its own reference or the
# reference stands for a lost note.


def _matched_pairs(
    note_values: tuple[int, ...], references: tuple[str, ...]
) -> tuple[tuple[str, int], ...]:
    """Each link as (the reference's word, the linked note's value), of
    endnotes `note_values` against glued references in reading order."""
    notes = tuple(
        NoteToMatch(position, 9, value) for position, value in enumerate(note_values)
    )
    candidates = tuple(
        Candidate(0, position, 1, reference)
        for position, word in enumerate(references)
        if (reference := reference_candidate(word)) is not None
    )
    return tuple(
        (references[link.candidate.word], note_values[link.note])
        for link in match_endnotes(notes, candidates)
    )


def test_endnote_reference_of_a_note_whose_marker_was_lost_stays_unlinked() -> None:
    # Haynes' page 301: notes 47 and 49 lost their markers into 46 and 48,
    # and reference 46 was not read; 48 and 49 took notes 46 and 48.
    assert _matched_pairs(
        (45, 46, 48, 50),
        ("word45.", "word47.", "word48.", "word49.", "word50."),
    ) == (("word45.", 45), ("word48.", 48), ("word50.", 50))


def test_endnote_reference_misread_with_a_confused_digit_keeps_its_link() -> None:
    # Turney: printed 5 read "3", a digit pair the OCR confuses; no other
    # reference reads 5 and note 3 has its own.
    assert _matched_pairs(
        (1, 2, 3, 4, 5, 6),
        ("word1.", "word2.", "word3.", "word4.", "word3.", "word6."),
    ) == tuple((f"word{n}.", n) for n in (1, 2, 3, 4)) + (
        ("word3.", 5),
        ("word6.", 6),
    )


def test_endnote_reference_standing_for_a_lost_note_stays_unlinked() -> None:
    # Haynes' page 234: note 18 lost its marker and reference 19 was not
    # read; reference 18 took note 19.
    assert _matched_pairs((17, 19, 20), ("word17.", "word18.", "word20.")) == (
        ("word17.", 17),
        ("word20.", 20),
    )


# Spec section 12, "The candidates of endnotes": three forms of reference
# that endnotes take and footnotes do not.


@pytest.mark.parametrize(
    ("word", "reference"),
    [
        # A glued number without the citation exclusion.
        ("art.27", ("art.", "27", "")),
        ("Q.19", ("Q.", "19", "")),
        # After a year and sentence punctuation.
        ("1911.34", ("1911.", "34", "")),
        ("1886,57", ("1886,", "57", "")),
        ("1871\u2019.42", ("1871\u2019.", "42", "")),
        # After a closing bracket and any sentence punctuation.
        ("(61).29", ("(61).", "29", "")),
        ("[1862]).38", ("[1862]).", "38", "")),
        ("5)16", ("5)", "16", "")),
        ("(1936)41", ("(1936)", "41", "")),
        ("[1862]38", ("[1862]", "38", "")),
        # Followed by a dash and a word.
        ("river20\u2014and", ("river", "20", "\u2014and")),
        ("rivers?25\u2014Then", ("rivers?", "25", "\u2014Then")),
        ("(6)3\u2014so", ("(6)", "3", "\u2014so")),
        ("tide4\u2013and", ("tide", "4", "\u2013and")),
    ],
)
def test_endnote_candidate_of_each_form_splits_off_its_number(
    word: str, reference: tuple[str, str, str]
) -> None:
    before, number, after = reference
    assert endnote_candidate(word) == Reference(
        before, number, after, ReferenceForm.GLUED, int(number)
    )
    # Footnotes keep the candidates of section 11.
    assert reference_candidate(word) is None


@pytest.mark.parametrize(
    "word",
    [
        "10.35",  # a time
        "10:35",
        "14",  # "7 September": a lone number is no candidate
        "4.6",  # a decimal
        "14.9.73",  # a date
        "19731",  # a year with no punctuation before the number
        "12345.6",  # five digits are no year
        "river20\u20141914",  # a dash and a number, not a word
        "1914-18",  # a range
        "1914\u201318",
        "(612-19)",
        "(71-72)-46",
        "10,000.5",
        "word4-but",  # a hyphen is not a dash before a word
        "word4.\u2014but",  # punctuation between the number and the dash
    ],
)
def test_endnote_candidate_is_none_for_a_number_that_is_no_reference(
    word: str,
) -> None:
    assert endnote_candidate(word) is None


def test_endnote_candidate_keeps_a_bracketed_number_as_section_11_reads_it() -> None:
    candidate = endnote_candidate("(1).")
    assert candidate == reference_candidate("(1).")
    assert candidate is not None
    assert candidate.form is ReferenceForm.BRACKETED


def test_endnotes_link_the_references_only_endnotes_take() -> None:
    # One chapter whose nine lines end with a reference of each form, a
    # glued one, and a time that would read note 6 but is passed over.
    ends = (
        "cap.1",
        "1911.2",
        "(61).3",
        "7)4",
        "word5\u2014and",
        "at 11.6",
        "word6.",
        "word7.",
        "1886,8",
    )
    first = (*_group_heading(1, _CHAPTERS[0], 50.0), *_dotted_notes(80.0))
    pages = (
        _chapter_page(0, _CHAPTERS[0], ends),
        PageLayout(1, (_region(*first),), ()),
    )
    blocks = make_blocks(_lines_of(*pages), _NO_WORDS, workers=1)
    markers = {note.id: note.marker for note in blocks.notes}
    links = tuple(
        (span.text, markers[span.note_ref])
        for block in blocks.blocks
        for span in block.spans
        if span.note_ref is not None
    )
    assert links == tuple((str(n), f"{n}.") for n in range(1, 9))
    text = block_text(blocks.blocks[1])
    assert "at 11.6 " in text
    assert "word5\u2014and" in text


# Spec section 12, "The gap between linked neighbours". Made-up words: a
# gap's paragraph is block 1; notes are given by value, the note at
# position i of `values`; links of the matching sit in block 0 (before)
# and block 2 (after).

_CURLY_BOOK = frozenset("^~'\"")
_STRAIGHT_BOOK = frozenset("^~")


def _gap_words(text: str) -> tuple[BodyWord, ...]:
    words = text.split(" ")
    return tuple(
        BodyWord(
            1,
            place,
            5,
            word,
            words[place - 1] if place > 0 else "",
            words[place + 1] if place + 1 < len(words) else "",
        )
        for place, word in enumerate(words)
    )


def _gap_made(
    text: str,
    values: tuple[int, ...] = (6, 7, 8),
    linked: tuple[int, ...] = (6, 8),
    signs: frozenset[str] = _CURLY_BOOK,
) -> tuple[Link, ...]:
    """The links made in the gap, for notes of `values` of which those of
    `linked` are linked, the first in block 0 and the others in block 2,
    around the words of `text`."""
    notes = tuple(
        NoteToMatch(position, 9, value) for position, value in enumerate(values)
    )
    reference = reference_candidate("word1.")
    assert reference is not None
    links = tuple(
        Link(Candidate(0 if order == 0 else 2, order, 5, reference), position)
        for order, (position, value) in enumerate(
            (position, value)
            for position, value in enumerate(values)
            if value in linked
        )
    )
    return gap_links(notes, _gap_words(text), links, signs)


def _gap_linked(
    text: str,
    values: tuple[int, ...] = (6, 7, 8),
    linked: tuple[int, ...] = (6, 8),
    signs: frozenset[str] = _CURLY_BOOK,
) -> tuple[tuple[str, int], ...]:
    """Each link `_gap_made` makes: the linked word's text and the note's
    value."""
    words = _gap_words(text)
    return tuple(
        (words[link.candidate.word].text, values[link.note])
        for link in _gap_made(text, values, linked, signs)
    )


def test_gap_lone_number_equal_to_the_note_is_linked() -> None:
    assert _gap_linked("the river 7 then ran on") == (("7", 7),)


def test_gap_lone_number_beside_a_month_stays_unlinked() -> None:
    assert _gap_linked("on 7 September the river ran") == ()
    assert _gap_linked("in June 7 the river ran") == ()


def test_gap_lone_number_that_ends_the_note_is_linked_after_a_phrase_end() -> None:
    values, linked = (78, 79, 80), (78, 80)
    assert _gap_linked("the river ran. 9 Then it", values, linked) == (("9", 79),)
    assert _gap_linked("the river ran 9 then it", values, linked) == ()


@pytest.mark.parametrize(
    ("text", "values", "linked", "word"),
    [
        ("the river ran!\u2019'9 Then", (18, 19, 20), (18, 20), "ran!\u2019'9"),
        ("the river ran/0 Then", (29, 30, 31), (29, 31), "ran/0"),
        ("the river ran.4 Then", (44, 45, 46), (44, 46), "ran.4"),
        # 3 for 8, a pair the OCR confuses.
        ("the river ran.13 Then", (17, 18, 19), (17, 19), "ran.13"),
        ("the hills (12-13)-18 Then", (17, 18, 19), (17, 19), "(12-13)-18"),
    ],
)
def test_gap_glued_digits_of_the_note_are_linked(
    text: str, values: tuple[int, ...], linked: tuple[int, ...], word: str
) -> None:
    assert _gap_linked(text, values, linked) == ((word, values[1]),)


@pytest.mark.parametrize(
    "text",
    [
        "at 10.35 the river ran",  # a time
        "some 1,547 rivers ran",  # a number
        "the river ran.2 Then",  # not part of 47
        "the river ran.47a Then",  # a letter after
        "in 1914-47 the river ran",  # a range
        "see pp.12-47 then",
        "see pp.12\u201347 then",
        "it cost \u00a347 then",  # a currency sign
        "it cost $47. Then",
        "see \u00a747 then",  # a section sign
        "see \u00a7.47 then",
    ],
)
def test_gap_digits_that_are_no_reference_stay_unlinked(text: str) -> None:
    assert _gap_linked(text, (46, 47, 48), (46, 48)) == ()


def test_gap_sign_the_book_does_not_print_is_linked() -> None:
    assert _gap_linked('the river ran." Then') == (('ran."', 7),)
    assert _gap_linked("the river ran. ' Then") == (("'", 7),)
    assert _gap_linked("the river ran.^ Then", signs=_STRAIGHT_BOOK) == (("ran.^", 7),)


def test_gap_sign_the_book_prints_or_straight_after_a_letter_stays_unlinked() -> None:
    assert _gap_linked('the river ran." Then', signs=_STRAIGHT_BOOK) == ()
    assert _gap_linked("the river Ran' Then") == ()
    assert _gap_linked("the river a ^ then") == ()


def test_gap_with_two_words_that_read_as_the_note_stays_unlinked() -> None:
    assert _gap_linked("the river 7 ran.7 Then") == ()


def test_gap_run_of_two_notes_links_two_words_in_order() -> None:
    values, linked = (5, 6, 7, 8), (5, 8)
    assert _gap_linked('the river ran.6 Then it ran." So', values, linked) == (
        ("ran.6", 6),
        ('ran."', 7),
    )
    # One word for two notes: neither is linked.
    assert _gap_linked("the river ran.6 Then it ran", values, linked) == ()


def test_gap_needs_both_neighbours_linked_by_the_matching() -> None:
    # Note 8 is not linked: the gap of 7 has no end, and no run is linked.
    assert _gap_linked("the river 7 then ran", (6, 7, 8, 9), (6,)) == ()


def test_gap_run_whose_words_read_out_of_order_stays_unlinked() -> None:
    # Two words for notes 6 and 7, but the first reads only as 7.
    values, linked = (5, 6, 7, 8), (5, 8)
    assert _gap_linked('the river ran.7 Then it ran." So', values, linked) == ()


def test_gap_digits_of_another_length_never_read_as_one_confused_digit() -> None:
    # "18" against 137: 8 and 3 are confused, but the lengths differ.
    assert _gap_linked("the river ran.18 Then", (136, 137, 138), (136, 138)) == ()


def test_gap_sign_read_is_the_last_of_the_word() -> None:
    made = _gap_made("the river ran.\"' Then")
    assert tuple(link.candidate.reference.reference for link in made) == ("'",)


def test_gap_sign_with_a_symbol_after_it_is_no_reading() -> None:
    assert _gap_linked('the river ran."\u00a3 Then') == ()


# Spec section 12, "The gap between linked neighbours": which words of the
# body the gap rule looks at, through the links of the body's blocks.


def _block(
    kind: BlockKind, text: str, page: int = 5, level: int | None = None
) -> Unnumbered:
    words = tuple(text.split(" "))
    return Unnumbered(
        kind=kind,
        words=words,
        word_pages=(page,) * len(words),
        origin=(Origin(page, Box(50.0, 50.0, 300.0, 60.0)),),
        changes=(),
        level=level,
    )


def _note(kind: NoteKind, marker: str, page: int = 9) -> UnnumberedNote:
    return UnnumberedNote(
        kind, marker, (), (Origin(page, Box(50.0, 50.0, 300.0, 60.0)),), False
    )


def _body_links(
    gap: Unnumbered,
    values: tuple[int, ...] = (6, 7, 8),
    footnote: bool = False,
    last_contents_page: int = -1,
) -> tuple[tuple[str, str], ...]:
    """The links of a chapter whose paragraphs end with references to
    endnotes 6 and 8 around `gap`, as (the linked word, the note's
    marker); with `footnote`, a footnote of value 7 on the gap's page."""
    body = (
        _block(BlockKind.HEADING, "Chapter One", level=1),
        _block(BlockKind.PARAGRAPH, "the river ran word6. and on"),
        gap,
        _block(BlockKind.PARAGRAPH, "the river ran word8. and on"),
    )
    notes = tuple(_note(NoteKind.ENDNOTE, f"{value}.") for value in values)
    note_values: tuple[int | None, ...] = values
    groups: tuple[int | None, ...] = (0,) * len(values)
    if footnote:
        notes = (*notes, _note(NoteKind.FOOTNOTE, "7", gap.word_pages[0]))
        note_values, groups = (*values, 7), (*groups, None)
    links = _links(
        body,
        notes,
        note_values,
        frozenset(),
        groups,
        ("Chapter One",),
        len(body),
        last_contents_page,
        Numbering.BY_MARKER,
        frozenset(),
    )
    return tuple(
        (body[link.candidate.block].words[link.candidate.word], notes[link.note].marker)
        for link in links
    )


def test_lone_number_to_an_unmarked_note_after_a_skip_is_undone() -> None:
    # Spec section 11, "Sure links", applied again after the lone numbers:
    # the note with no marker has the value 3 after note 1, so a lone "3."
    # is not the reference the order expects (it would read 2).
    body = (_block(BlockKind.PARAGRAPH, "the land1. and the king 3. Then on", page=9),)
    notes = (_note(NoteKind.FOOTNOTE, "1"), _note(NoteKind.FOOTNOTE, ""))
    links = _links(
        body,
        notes,
        (1, 3),
        frozenset(),
        (None, None),
        (),
        len(body),
        -1,
        Numbering.PER_PAGE,
        frozenset(),
    )
    assert tuple(notes[link.note].marker for link in links) == ("1",)


@pytest.mark.parametrize(
    ("numbering", "linked"),
    [
        (Numbering.PER_PAGE, (("land1.", "1"),)),
        (Numbering.BY_MARKER, (("land1.", "1"), ("table3.", ""))),
    ],
    ids=["per_page", "by_marker"],
)
def test_unmarked_footnote_after_an_unlinked_note_is_linked_only_by_marker(
    numbering: Numbering, linked: tuple[tuple[str, str], ...]
) -> None:
    # Spec section 11, "Sure links": notes 1 and 2 and a table's row
    # without a marker given the value 3; note 2 is unlinked, and in a book
    # numbered per page the row loses "table3.".
    body = (_block(BlockKind.PARAGRAPH, "the land1. and the table3. ran", page=9),)
    notes = (
        _note(NoteKind.FOOTNOTE, "1"),
        _note(NoteKind.FOOTNOTE, "2"),
        _note(NoteKind.FOOTNOTE, ""),
    )
    links = _links(
        body,
        notes,
        (1, 2, 3),
        frozenset(),
        (None, None, None),
        (),
        len(body),
        -1,
        numbering,
        frozenset(),
    )
    assert (
        tuple(
            (
                body[link.candidate.block].words[link.candidate.word],
                notes[link.note].marker,
            )
            for link in links
        )
        == linked
    )


def test_gap_rule_links_a_lone_number_of_a_paragraph() -> None:
    gap = _block(BlockKind.PARAGRAPH, "the river 7 then ran")
    assert ("7", "7.") in _body_links(gap)


@pytest.mark.parametrize(
    ("kind", "level"), [(BlockKind.HEADING, 2), (BlockKind.QUOTE, None)]
)
def test_gap_rule_does_not_look_in_a_heading_or_a_quote(
    kind: BlockKind, level: int | None
) -> None:
    gap = _block(kind, "the river 7 then ran", level=level)
    assert ("7", "7.") not in _body_links(gap)


def test_gap_rule_does_not_look_on_a_contents_page() -> None:
    gap = _block(BlockKind.PARAGRAPH, "the river 7 then ran", page=3)
    assert ("7", "7.") not in _body_links(gap, last_contents_page=4)


def test_gap_rule_does_not_take_a_footnotes_reference() -> None:
    gap = _block(BlockKind.PARAGRAPH, "the river ran7. then")
    assert _body_links(gap, footnote=True).count(("ran7.", "7.")) == 0


def test_gap_rule_matches_a_note_out_of_order_by_its_place() -> None:
    gap = _block(BlockKind.PARAGRAPH, "the river ran word7. then")
    assert ("word7.", "37.") in _body_links(gap, values=(6, 37, 8))


def _out_of_order_links(places: dict[int, int]) -> tuple[Link, ...]:
    """Links of the notes of values 11 to 16 (positions 0 to 5) by value,
    each at a word of block 1 by place."""
    reference = reference_candidate("word1.")
    assert reference is not None
    return tuple(
        Link(Candidate(1, place, 5, reference), value - 11)
        for value, place in places.items()
    )


def test_gap_word_is_taken_by_one_run_only() -> None:
    # Notes 11, 13, 14 and 16 linked at places 10, 50, 20 and 60, out of
    # order: the gaps of 12 (10 to 50) and of 15 (20 to 60) both hold the
    # sign at place 30, which goes to note 12 alone.
    notes = tuple(NoteToMatch(value - 11, 9, value) for value in range(11, 17))
    texts = ["the"] * 70
    texts[29], texts[30] = "river.", "^"
    words = tuple(
        BodyWord(1, place, 5, text, texts[place - 1] if place else "", "")
        for place, text in enumerate(texts)
    )
    links = _out_of_order_links({11: 10, 13: 50, 14: 20, 16: 60})
    made = gap_links(notes, words, links, _CURLY_BOOK)
    assert tuple((link.candidate.word, link.note + 11) for link in made) == ((30, 12),)


def test_gap_run_whose_first_reference_comes_after_its_second_takes_nothing() -> None:
    notes = tuple(NoteToMatch(value - 11, 9, value) for value in range(11, 14))
    words = _gap_words("the river 12 ran on and on")
    links = tuple(
        replace(link, candidate=replace(link.candidate, block=block))
        for link, block in zip(_out_of_order_links({11: 0, 13: 0}), (2, 0), strict=True)
    )
    assert gap_links(notes, words, links, _CURLY_BOOK) == ()


def test_endnote_out_of_order_between_its_neighbours_takes_their_middle_value() -> None:
    notes = tuple(
        NoteToMatch(position, 9, value)
        for position, value in enumerate((55, 56, 37, 58, 59, 7, 62))
    )
    assert tuple(note.value for note in with_values_in_order(notes)) == (
        *(55, 56, 57, 58, 59, 7, 62),
    )


def test_straight_quotation_mark_is_a_sign_in_a_book_of_curly_ones() -> None:
    assert foreign_signs(("\u2018river\u2019", "ran'")) == frozenset("^~'")
    assert foreign_signs(("'river'", "\u2019")) == frozenset("^~")


def test_endnote_linked_in_the_gap_by_make_blocks() -> None:
    # Line 5 ends with a lone "5" where "word5." would be: note 5 is
    # linked to it, between the references of notes 4 and 6.
    ends = tuple(f"word{n}." for n in range(1, 10))
    ends = (*ends[:4], "river 5", *ends[5:])
    first = (*_group_heading(1, _CHAPTERS[0], 50.0), *_dotted_notes(80.0))
    pages = (
        _chapter_page(0, _CHAPTERS[0], ends),
        PageLayout(1, (_region(*first),), ()),
    )
    blocks = make_blocks(_lines_of(*pages), _NO_WORDS, workers=1)
    markers = {note.id: note.marker for note in blocks.notes}
    links = tuple(
        (span.text, markers[span.note_ref])
        for block in blocks.blocks
        for span in block.spans
        if span.note_ref is not None
    )
    assert links == tuple((str(n), f"{n}.") for n in range(1, 10))


# Spec section 12, "Endnotes run into the note before". Made-up notes in
# Haynes' form, one group: each note's first line indented
# 20 pt, its other lines full, its last line short; a run-on note's first
# line is flush left after a full last line, where no paragraph starts.

_FULL = "the note goes on over a full line"


def _run_on_page(
    notes: tuple[tuple[str, bool], ...], ending: str = "here."
) -> PageLayout:
    """A page of notes, each (its first line's text,
    whether it is run into the note before): a note run in has its first
    line flush left, and the note before it ends with a full line ending
    with the word `ending`; any other ends with a short line."""
    lines: list[Line] = []
    top = 50.0
    for number, (first, run_on) in enumerate(notes):
        following_runs_on = number + 1 < len(notes) and notes[number + 1][1]
        lines.append(
            _spread(first, _LEFT_PT if run_on else _LEFT_PT + 20, _RIGHT_PT, top)
        )
        lines.append(_spread(_FULL, _LEFT_PT, _RIGHT_PT, top + 15))
        lines.append(
            _spread(f"{_FULL} {ending}", _LEFT_PT, _RIGHT_PT, top + 30)
            if following_runs_on
            else _spread("line and ends.", _LEFT_PT, 150.0, top + 30)
        )
        top += 45
    return PageLayout(1, (_region(*lines),), ())


def _run_on_markers(
    notes: tuple[tuple[str, bool], ...], ending: str = "here."
) -> tuple[str, ...]:
    pages = (_chapter_page(0, _CHAPTERS[0]), _run_on_page(notes, ending))
    blocks = make_blocks(_lines_of(*pages), _NO_WORDS, workers=1)
    return tuple(marker for marker, _ in _endnotes(blocks))


def _notes_with(run_on: dict[int, str]) -> tuple[tuple[str, bool], ...]:
    """Notes "1." to "12.", the first line of note n replaced by
    `run_on[n]` and run into the note before."""
    return tuple(
        (run_on.get(n, f"{n}. The note of its"), n in run_on) for n in range(1, 13)
    )


def test_note_run_into_the_note_before_is_cut_off_it() -> None:
    notes = _notes_with({4: "4. The note of its", 5: "5. The note of its"})
    assert _run_on_markers(notes) == tuple(f"{n}." for n in range(1, 13))


def test_note_run_in_with_a_hyphen_marker_is_cut_off_it() -> None:
    notes = _notes_with({4: "4- The note of its"})
    assert _run_on_markers(notes)[:5] == ("1.", "2.", "3.", "4-", "5.")


def test_number_that_is_not_the_next_value_stays_text_of_its_note() -> None:
    # "40." starts a line inside note 3, where note 4 is next: it stays
    # text of note 3, and note 4 is missing.
    markers = _run_on_markers(_notes_with({4: "40. The note of its"}))
    assert markers == ("1.", "2.", "3.", *(f"{n}." for n in range(5, 13)))


def test_next_value_whose_own_paragraph_follows_stays_text() -> None:
    # Note 3 holds a line "4." run in, and note 4 has its own paragraph
    # after it: the line is not a second note 4.
    notes = (
        *_notes_with({})[:3],
        ("4. The note of its", True),
        *_notes_with({})[3:],
    )
    assert _run_on_markers(notes).count("4.") == 1


def test_next_value_after_a_line_that_ends_no_note_stays_text() -> None:
    # The line before "4." ends "see" with no full stop: not a note's end.
    notes = _notes_with({4: "4. The note of its"})
    page = _run_on_page(notes)
    region = page.regions[0]
    lines = list(region.lines)
    end = next(
        number for number, line in enumerate(lines) if line.words[0].text == "4."
    )
    before = lines[end - 1]
    lines[end - 1] = _spread(
        " ".join(word.text for word in before.words[:-1]) + " see",
        _LEFT_PT,
        _RIGHT_PT,
        before.box.top,
    )
    pages = (
        _chapter_page(0, _CHAPTERS[0]),
        PageLayout(1, (_region(*lines),), ()),
    )
    blocks = make_blocks(_lines_of(*pages), _NO_WORDS, workers=1)
    assert "4." not in tuple(marker for marker, _ in _endnotes(blocks))


def test_note_run_in_after_a_full_stop_and_a_closing_quote_is_cut_off() -> None:
    notes = _notes_with({4: "4. The note of its"})
    assert "4." in _run_on_markers(notes, ending='here."')


def test_note_run_in_after_a_word_broken_by_a_hyphen_stays_text() -> None:
    notes = _notes_with({4: "4. The note of its"})
    assert "4." not in _run_on_markers(notes, ending="con-")


def test_bare_number_run_into_a_section_of_dotted_markers_stays_text() -> None:
    # Not cut off: note 3 stays one paragraph, the bare "4" inside it.
    notes = _notes_with({4: "4 The note of its"})
    pages = (_chapter_page(0, _CHAPTERS[0]), _run_on_page(notes))
    blocks = make_blocks(_lines_of(*pages), _NO_WORDS, workers=1)
    third = next(text for marker, text in _endnotes(blocks) if marker == "3.")
    assert " / " not in third
    assert " 4 The note of its " in third


def test_note_run_into_a_later_paragraph_takes_the_value_after_a_cut() -> None:
    # Note 3, then "4." run into it, then a paragraph of note 4 without a
    # marker (indented) into which "5." runs: 5 is the next value there.
    lines: list[Line] = []
    top = 50.0
    for number in (1, 2):
        lines += [
            _spread(f"{number}. The note of its", _LEFT_PT + 20, _RIGHT_PT, top),
            _spread("line and ends.", _LEFT_PT, 150.0, top + 15),
        ]
        top += 30
    # Note 4's paragraph ends with a short line, so that the indented line
    # after it starts a paragraph of its own.
    for first, indent, full in (
        ("3. The note of its", 20, True),
        ("4. The note of its", 0, False),
        ("And it goes on", 20, True),
        ("5. The note of its", 0, False),
    ):
        lines += [
            _spread(first, _LEFT_PT + indent, _RIGHT_PT, top),
            _spread(f"{_FULL} here.", _LEFT_PT, _RIGHT_PT, top + 15)
            if full
            else _spread("line and ends.", _LEFT_PT, 150.0, top + 15),
        ]
        top += 30
    for number in range(6, 13):
        lines += [
            _spread(f"{number}. The note of its", _LEFT_PT + 20, _RIGHT_PT, top),
            _spread("line and ends.", _LEFT_PT, 150.0, top + 15),
        ]
        top += 30
    pages = (_chapter_page(0, _CHAPTERS[0]), PageLayout(1, (_region(*lines),), ()))
    blocks = make_blocks(_lines_of(*pages), _NO_WORDS, workers=1)
    assert tuple(marker for marker, _ in _endnotes(blocks)) == tuple(
        f"{n}." for n in range(1, 13)
    )


def test_bare_number_run_into_a_note_after_a_number_and_hyphen_is_cut_off() -> None:
    # Turney's form: notes hung as bare numbers; note 5's number starts the
    # line after one that ends "p. 487-", the OCR's full stop, and is not
    # hung, so no paragraph starts there.
    numbers = ("1", "2", "3", "4", "5", "6", "7", "8", "9")
    lines = list(_hung_notes(numbers))
    four = next(n for n, line in enumerate(lines) if line.words[0].text == "4")
    five = next(n for n, line in enumerate(lines) if line.words[0].text == "5")
    lines[five - 1] = _line("see p. 487-", _TEXT_EDGE_PT, lines[five - 1].box.top)
    lines[five] = _line(
        "5 Compare the note which runs", _TEXT_EDGE_PT, lines[five].box.top
    )
    assert four < five
    page = PageLayout(0, (_region(*lines),), ())
    blocks = make_blocks(_lines_of(page), _NO_WORDS, workers=1)
    assert tuple(marker for marker, _ in _endnotes(blocks)) == numbers


# Review of work package 3: hand-written cases for the rules the mutation
# of the suite left alive.


def test_chapter_of_group_alike_by_0_76_to_another_chapter_is_counted() -> None:
    # A made-up chapter 9 heading, 0.76 alike to chapter 11's as Haynes'
    # is: below 0.85, so the group is counted on from the introduction's,
    # not matched.
    chapters = (
        (10, "introduction"),
        (20, "anotherchapter"),
        (30, "thebuilderashero"),
    )
    assert group_reaches(
        chapters, ("Introduction", "Chapter 9. The Builder as Traveller"), 40
    ) == ((10, 20), (20, 40))


def test_chapter_of_group_counted_onto_the_next_groups_chapter_is_none() -> None:
    # The group between two found by their headings, whose chapters are
    # next to each other, has no chapter left: counting on would reach the
    # next group's, counting back the group before's.
    chapters = ((10, "alpha"), (20, "beta"))
    assert group_reaches(chapters, ("alpha", None, "beta"), 30) == (
        (10, 20),
        (0, 0),
        (20, 30),
    )


def test_chapter_of_groups_without_any_heading_counts_from_the_first() -> None:
    chapters = ((10, "alpha"), (20, "beta"))
    assert group_reaches(chapters, (None, None), 30) == ((10, 20), (20, 30))


def test_group_heading_of_4_lines_left_at_the_end_of_a_note_is_not_cut() -> None:
    # Four lines set apart after note 9: more than a group heading holds,
    # they stay in note 9's paragraph and the second group has no heading.
    first = (*_group_heading(1, _CHAPTERS[0], 50.0), *_dotted_notes(80.0))
    top = first[-1].box.top + 27.0
    heading = tuple(
        _spread(text, _LEFT_PT, 160.0, top + _PITCH_PT * number)
        for number, text in enumerate(
            ("Chapter 2. Silent", "Harbour", "Rebuilt Once", "More Again")
        )
    )
    second = (*heading, *_dotted_notes(top + 4 * _PITCH_PT + 15.0))
    pages = (
        _chapter_page(0, _CHAPTERS[0]),
        _chapter_page(1, _CHAPTERS[1]),
        PageLayout(2, (_region(*first, *second),), ()),
    )
    blocks = make_blocks(_lines_of(*pages), _NO_WORDS, workers=1)
    assert tuple(note.group for note in blocks.notes if note.group is not None) == (
        f"Chapter 1. {_CHAPTERS[0]}",
    )
    note_9 = next(note for note in blocks.notes if note.marker == "9.")
    assert len(note_9.blocks) == 1


def _speck(x0: float, top: float) -> Line:
    return Line(
        Box(x0, top, x0 + 3, top + 5), (Word("/", Box(x0, top, x0 + 3, top + 5), None),)
    )


def test_group_heading_measures_its_gap_past_a_speck_just_above_it() -> None:
    # A speck 5 pt above the second heading, which lies 27 pt below note 9:
    # the gap is measured from note 9's last line, so the heading is set
    # apart.
    first = _turney_group(1, _CHAPTERS[0], 50.0)
    second = _turney_group(2, _CHAPTERS[1], first[-1].box.top + 30.0)
    speck = _speck(310.0, second[0].box.top - 8.0)
    pages = (
        _chapter_page(0, _CHAPTERS[0]),
        _chapter_page(1, _CHAPTERS[1]),
        PageLayout(2, (_region(*first, speck, *second),), ()),
    )
    blocks = make_blocks(_lines_of(*pages), _NO_WORDS, workers=1)
    assert tuple(note.group for note in blocks.notes if note.group is not None) == (
        f"1 {_CHAPTERS[0]}",
        f"2 {_CHAPTERS[1]}",
    )


def test_heading_with_a_1_followed_by_a_speck_stays_a_note() -> None:
    # The first group's "1 ..." heading is followed by a speck before its
    # note 1: the heading is the first block of an endnote that keeps a
    # later block, so it is not taken, and stays note "1" with the speck.
    first = _turney_group(1, _CHAPTERS[0], 50.0)
    speck = _speck(310.0, first[0].box.top + 14.0)
    second = _turney_group(2, _CHAPTERS[1], first[-1].box.top + 30.0)
    pages = (
        _chapter_page(0, _CHAPTERS[0]),
        _chapter_page(1, _CHAPTERS[1]),
        PageLayout(2, (_region(first[0], speck, *first[1:], *second),), ()),
    )
    blocks = make_blocks(_lines_of(*pages), _NO_WORDS, workers=1)
    endnotes = _endnotes(blocks)
    assert endnotes[0] == ("1", f"{_CHAPTERS[0]} / /")
    assert tuple(note.group for note in blocks.notes if note.group is not None) == (
        f"2 {_CHAPTERS[1]}",
    )


def test_misread_marker_before_2_3_and_5_is_no_marker() -> None:
    # "x" before 2, 3 and 5 (not 4): no misread marker, and the second
    # group is lost as before the rule.
    first = _turney_group(1, _CHAPTERS[0], 50.0)
    heading_top = first[-1].box.top + 30.0
    numbers = ("x", "2", "3", "5", "6", "7", "8", "9", "10")
    misread = tuple(
        line
        for position, number in enumerate(numbers)
        for line in _hung_note(number, heading_top + 27.0 + 36.0 * position)
    )
    second = (_line(f"2 {_CHAPTERS[1]}", _HUNG_PT, heading_top), *misread)
    pages = (
        _chapter_page(0, _CHAPTERS[0]),
        _chapter_page(1, _CHAPTERS[1]),
        PageLayout(2, (_region(*first, *second),), ()),
    )
    blocks = make_blocks(_lines_of(*pages), _NO_WORDS, workers=1)
    assert "x" not in tuple(marker for marker, _ in _endnotes(blocks))


def test_hanging_number_before_a_number_starts_no_paragraph() -> None:
    # A table's column of numbers, "1 10", "3 0)": no note text after it.
    lines = tuple(
        line
        for number in ("8", "9", "10", "11")
        for line in (
            _line(f"{number} 10 4", _HUNG_PT, 70.0 + 36 * int(number)),
            _line("on over a full line of the", _TEXT_EDGE_PT, 82.0 + 36 * int(number)),
            _line("note ends here.", _TEXT_EDGE_PT, 94.0 + 36 * int(number)),
        )
    )
    blocks = make_blocks(
        _lines_of(PageLayout(0, (_region(*lines),), ())), _NO_WORDS, workers=1
    )
    assert len(blocks.blocks) == 1


def test_hanging_number_on_a_contents_page_starts_no_paragraph() -> None:
    # Spec section 30: on a contents page an indented line runs on the
    # entry above it, so each hung note after the title is one entry.
    page = PageLayout(0, (_region(*_hung_notes(("8", "9", "10", "11"))),), ())
    blocks = make_blocks(
        _lines_of(page), _NO_WORDS, contents_pages=frozenset({0}), workers=1
    )
    assert not any(block.kind is BlockKind.PARAGRAPH for block in blocks.blocks)
    assert tuple(
        block_text(block).split(" ")[0]
        for block in blocks.blocks
        if block.kind is BlockKind.CONTENTS_ENTRY
    ) == ("on", "note", "9", "10", "11")


def test_group_reach_ends_at_the_next_group_that_has_a_chapter() -> None:
    # Two groups without a chapter between "alpha" and "betagamma": the
    # first reaches to "betagamma"'s chapter, not over it to the section.
    assert group_reaches(
        ((10, "alpha"), (20, "betagamma"), (30, "delta")),
        ("alpha", "zzzz", "qqqq", "betagamma"),
        40,
    ) == ((10, 20), (0, 0), (0, 0), (20, 40))
