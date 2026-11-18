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
from galley.structure import make_blocks, reference_candidate
from galley.structure._endnotes import group_reaches
from galley.structure._references import Candidate, NoteToMatch, match_endnotes

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
    # No hanging number starts a paragraph there either (spec section 6).
    assert len(blocks.blocks) == 1


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

_CHAPTERS = ("Mary Shelley Creation", "Hideous Progeny Retold")
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


def _chapter_page(index: int, title: str) -> PageLayout:
    width = _CHAR_PT * len(title)
    lines = (
        _spread(title, 175 - width / 2, 175 + width / 2, 50.0),
        _spread("The chapter opens here and", _LEFT_PT + 20, _RIGHT_PT, 85.0),
        *(
            _spread(
                f"a full line goes on to word{n}.", _LEFT_PT, _RIGHT_PT, 85.0 + 15 * n
            )
            for n in range(1, 10)
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
    """Turney's form: a group heading hung like a note, "2 Hideous ...",
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
    # chapter "Hideous Progeny Retold" comes first in the body: each group
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
    page = PageLayout(0, (_region(*_hung_notes(("8", "9", "10", "11"))),), ())
    blocks = make_blocks(
        _lines_of(page), _NO_WORDS, contents_pages=frozenset({0}), workers=1
    )
    assert len(blocks.blocks) == 1


def test_group_reach_ends_at_the_next_group_that_has_a_chapter() -> None:
    # Two groups without a chapter between "alpha" and "betagamma": the
    # first reaches to "betagamma"'s chapter, not over it to the section.
    assert group_reaches(
        ((10, "alpha"), (20, "betagamma"), (30, "delta")),
        ("alpha", "zzzz", "qqqq", "betagamma"),
        40,
    ) == ((10, 20), (0, 0), (0, 0), (20, 40))
