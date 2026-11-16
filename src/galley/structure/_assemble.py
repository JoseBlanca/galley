"""The work after the per-page parts (spec section 2, steps 2.5 and 3),
in page order: the notes left in the body, the paragraphs of the body
stream, the endnote section, the footnotes, the references linked to
their notes, the margin notes beside a note's line put inside it, and
the ids (`_ids`)."""

from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import assert_never

from galley.model import Block, BlockKind, Note, NoteKind, WordChange
from galley.structure._body_notes import take_body_notes
from galley.structure._endnotes import EndnoteGroup, endnote_groups, endnote_section
from galley.structure._ids import numbered
from galley.structure._lines import Piece, PlacedLine, first_word
from galley.structure._linking import body_candidates, linked
from galley.structure._margins import BesideLine, line_beside
from galley.structure._markers import MarkerForm, book_marker_form
from galley.structure._notes import (
    Footnote,
    Numbering,
    PageNote,
    book_numbering,
    footnotes,
    page_notes,
)
from galley.structure._paragraphs import (
    Entry,
    MarginNote,
    PageParts,
    Paragraph,
    body_entries,
)
from galley.structure._references import NoteToMatch, match_endnotes, match_footnotes
from galley.structure._unnumbered import (
    Unnumbered,
    UnnumberedNote,
    changes_in_order,
    first_page,
    joined,
    merged_origin,
    without_marker,
)


def _footnote(
    footnote: Footnote, book_words: frozenset[str], word_list: frozenset[str]
) -> UnnumberedNote:
    block, marker = without_marker(
        joined(Piece(footnote.lines), BlockKind.PARAGRAPH, book_words, word_list),
        footnote.marker,
    )
    return UnnumberedNote(
        kind=NoteKind.FOOTNOTE,
        marker=marker,
        blocks=(block,),
        origin=block.origin,
        referenced=False,
    )


@dataclass(frozen=True, slots=True)
class Assembled:
    """The book's blocks and notes in order, with their ids, and the word
    changes of their hyphen joins and note markers in reading order."""

    blocks: tuple[Block, ...]
    notes: tuple[Note, ...]
    word_changes: tuple[WordChange, ...]


def _body(
    entries: Sequence[Entry], book_words: frozenset[str], word_list: frozenset[str]
) -> tuple[Unnumbered, ...]:
    """The body's entries as blocks, with their hyphens joined."""
    body: list[Unnumbered] = []
    for entry in entries:
        match entry:
            case Paragraph(piece):
                kind = BlockKind.PARAGRAPH
            case MarginNote(piece):
                kind = BlockKind.MARGIN_NOTE
            case _:
                assert_never(entry)
        body.append(joined(piece, kind, book_words, word_list))
    return tuple(body)


def _endnote(group: EndnoteGroup, body: Sequence[Unnumbered]) -> UnnumberedNote:
    """An endnote of the paragraphs of `group`, its marker taken off the
    first (spec section 12)."""
    first, marker = without_marker(body[group.paragraphs[0]], group.marker)
    blocks = (first, *(body[position] for position in group.paragraphs[1:]))
    return UnnumberedNote(
        kind=NoteKind.ENDNOTE,
        marker=marker,
        blocks=blocks,
        origin=merged_origin(blocks),
        referenced=False,
    )


@dataclass(frozen=True, slots=True)
class _NoteWithLines:
    """A note before its id, with what matching and the margin notes need
    of it: its value (spec section 11, "Its value"; section 12) and the
    lines of each of its blocks."""

    note: UnnumberedNote
    value: int | None
    block_lines: tuple[tuple[PlacedLine, ...], ...]


def _in_order(
    endnotes: Sequence[_NoteWithLines], page_footnotes: Sequence[_NoteWithLines]
) -> tuple[_NoteWithLines, ...]:
    """The notes by their first page and, on a page, the endnotes, which
    come from the body, before the footnotes of the band (spec section 7)."""
    keyed = [
        (first_page(note.note.origin), 0, position, note)
        for position, note in enumerate(endnotes)
    ] + [
        (first_page(note.note.origin), 1, position, note)
        for position, note in enumerate(page_footnotes)
    ]
    return tuple(note for *_, note in sorted(keyed, key=lambda item: item[:3]))


def _taken_body_notes(
    parts: Sequence[PageParts],
    band_notes: Sequence[Sequence[PageNote]],
    numbering: Numbering,
    form: MarkerForm | None,
    body_word_height: float,
    section_pages: range,
) -> tuple[PageParts, ...]:
    """The pages with the notes left at the foot of their body taken, in a
    book numbered per page, except on the pages of the endnote section
    (spec section 11, "Notes left in the body"), and each page's body
    notes put before its band regions. `band_notes` are each page's notes
    of its band; `body_word_height` is in points."""
    taken = tuple(
        take_body_notes(page, notes, form, body_word_height)
        if numbering is Numbering.PER_PAGE and page.index not in section_pages
        else page
        for page, notes in zip(parts, band_notes, strict=True)
    )
    return tuple(
        page
        if not page.body_notes
        else replace(page, band_regions=(page.body_notes, *page.band_regions))
        for page in taken
    )


def _section_pages(entries: Sequence[Entry]) -> range:
    """The page indices of the endnote section, empty without one."""
    section = endnote_section(entries)
    if section is None:
        return range(0)
    last = entries[section.paragraphs[-1]].piece.lines[0].page_index
    return range(section.first_page, last + 1)


def _beside_lines(
    entries: Sequence[Entry],
    in_section: frozenset[int],
    notes: Sequence[_NoteWithLines],
) -> frozendict[int, tuple[BesideLine, ...]]:
    """The lines a margin note may stand beside, by page index: those of
    the body's paragraphs and of every note's blocks."""
    body = (
        BesideLine(line, number == 0, None)
        for position, entry in enumerate(entries)
        if isinstance(entry, Paragraph) and position not in in_section
        for number, line in enumerate(entry.piece.lines)
    )
    in_notes = (
        BesideLine(line, number == 0, (note_position, block_position))
        for note_position, note in enumerate(notes)
        for block_position, lines in enumerate(note.block_lines)
        for number, line in enumerate(lines)
    )
    by_page: dict[int, list[BesideLine]] = {}
    for beside in (*body, *in_notes):
        by_page.setdefault(beside.line.page_index, []).append(beside)
    return frozendict({page: tuple(lines) for page, lines in by_page.items()})


def _margin_notes_in_notes(
    entries: Sequence[Entry],
    in_section: frozenset[int],
    notes: Sequence[_NoteWithLines],
    pitch: float,
) -> frozendict[int, tuple[int, int]]:
    """For each margin note beside a line of a note (spec section 13, rule
    5), by its position among the entries: the note's position and that of
    the note's block that holds the line. `pitch` is the body line pitch,
    in points."""
    by_page = _beside_lines(entries, in_section, notes)
    besides = (
        (
            position,
            line_beside(
                entry.piece.lines[0].line.box.top,
                by_page.get(entry.piece.lines[0].page_index, ()),
                pitch,
            ),
        )
        for position, entry in enumerate(entries)
        if isinstance(entry, MarginNote)
    )
    return frozendict(
        {
            position: beside.note_block
            for position, beside in besides
            if beside is not None and beside.note_block is not None
        }
    )


def _with_margin_notes_inside(
    body: tuple[Unnumbered, ...],
    notes: tuple[UnnumberedNote, ...],
    kept_positions: Sequence[int],
    placed: frozendict[int, tuple[int, int]],
) -> tuple[tuple[Unnumbered, ...], tuple[UnnumberedNote, ...]]:
    """The body without the margin notes of `placed`, and the notes with
    each of them as a block before the block it is beside, after those
    already placed there. `kept_positions` gives the entry position of
    each block of `body`."""
    before_block: dict[tuple[int, int], list[Unnumbered]] = {}
    for block, entry_position in zip(body, kept_positions, strict=True):
        if entry_position in placed:
            before_block.setdefault(placed[entry_position], []).append(block)
    return (
        tuple(
            block
            for block, entry_position in zip(body, kept_positions, strict=True)
            if entry_position not in placed
        ),
        tuple(
            replace(
                note,
                blocks=tuple(
                    block
                    for number, note_block in enumerate(note.blocks)
                    for block in (
                        *before_block.get((note_position, number), ()),
                        note_block,
                    )
                ),
            )
            for note_position, note in enumerate(notes)
        ),
    )


def assemble(
    parts: Sequence[PageParts],
    book_words: frozenset[str],
    word_list: frozenset[str],
    body_word_height: float,
    body_line_pitch: float,
    last_contents_page: int,
) -> Assembled:
    """The work after the per-page parts (spec section 2, steps 2.5 and 3),
    in page order: the notes left at the foot of each page's body taken
    out of it, the paragraphs of the body stream with their hyphens joined,
    the margin notes after the paragraph in which their page's body ends,
    the footnotes of the band and of the body with their markers, the
    endnotes, the references linked to their notes, each margin note beside
    a note's line inside that note, and the ids. `word_list` is in lower
    case; `body_word_height` and `body_line_pitch` are in points; the
    references to endnotes are taken from the pages after
    `last_contents_page`, -1 for a book without contents pages."""
    form = book_marker_form(
        first_word(piece.lines[0]) for page in parts for piece in page.band_blocks
    )
    band_notes = tuple(page_notes(page.band_regions) for page in parts)
    numbering = book_numbering(band_notes)
    # The paragraphs are found twice: the first time only for the pages of
    # the endnote section, which the notes left in the body (step 2.5) skip
    # and whose first page starts a paragraph; both change the paragraphs,
    # so the section's paragraphs are taken from the second.
    section_pages = _section_pages(body_entries(parts, form))
    pages = _taken_body_notes(
        parts, band_notes, numbering, form, body_word_height, section_pages
    )
    entries = body_entries(pages, form, section_pages)
    section = endnote_section(entries)
    body = _body(entries, book_words, word_list)
    groups = endnote_groups(entries, section) if section is not None else ()
    in_section = frozenset(section.paragraphs if section is not None else ())
    endnotes = tuple(
        _NoteWithLines(
            _endnote(group, body),
            group.marker.value if group.marker else None,
            tuple(entries[position].piece.lines for position in group.paragraphs),
        )
        for group in groups
    )
    book_footnotes = footnotes(
        tuple(page_notes(page.band_regions) for page in pages),
        tuple(bool(page.body) for page in pages),
        numbering,
    )
    notes = _in_order(
        endnotes,
        tuple(
            _NoteWithLines(
                _footnote(footnote, book_words, word_list),
                footnote.value,
                (footnote.lines,),
            )
            for footnote in book_footnotes
        ),
    )
    kept = tuple(
        block for position, block in enumerate(body) if position not in in_section
    )
    before_section = (
        sum(1 for position in range(min(in_section)) if position not in in_section)
        if in_section
        else len(kept)
    )
    candidates = body_candidates(kept)
    footnote_links = match_footnotes(
        tuple(
            NoteToMatch(position, first_page(note.note.origin), note.value)
            for position, note in enumerate(notes)
            if note.note.kind is NoteKind.FOOTNOTE
        ),
        candidates,
    )
    footnoted = frozenset(link.candidate for link in footnote_links)
    endnote_links = match_endnotes(
        tuple(
            NoteToMatch(position, first_page(note.note.origin), note.value)
            for position, note in enumerate(notes)
            if note.note.kind is NoteKind.ENDNOTE
        ),
        tuple(
            candidate
            for candidate in candidates
            if candidate.block < before_section
            and candidate.page_index > last_contents_page
            and candidate not in footnoted
        ),
    )
    linked_body, linked_notes = linked(
        kept, tuple(note.note for note in notes), footnote_links + endnote_links
    )
    placed = _margin_notes_in_notes(entries, in_section, notes, body_line_pitch)
    kept_positions = tuple(
        position for position in range(len(entries)) if position not in in_section
    )
    linked_body, linked_notes = _with_margin_notes_inside(
        linked_body, linked_notes, kept_positions, placed
    )
    blocks, numbered_notes = numbered(linked_body, linked_notes)
    return Assembled(
        blocks=blocks,
        notes=numbered_notes,
        word_changes=tuple(
            sorted(
                changes_in_order(linked_body)
                + changes_in_order(
                    tuple(block for note in linked_notes for block in note.blocks)
                ),
                key=lambda change: change.page_index,
            )
        ),
    )
