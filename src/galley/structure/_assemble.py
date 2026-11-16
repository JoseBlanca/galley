"""The work after the per-page parts (spec section 2, steps 2.5 and 3),
in page order: the notes left in the body, the paragraphs of the body
stream, the endnote section, the footnotes, the references linked to
their notes, the margin notes placed (`_margins`), and the ids
(`_ids`)."""

from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import assert_never

from galley.model import Block, BlockKind, Note, NoteKind, WordChange
from galley.structure._bibliography import (
    bibliography,
    in_bibliographical_notes,
    with_band_as_body,
)
from galley.structure._body_notes import take_body_notes
from galley.structure._endnotes import EndnoteGroup, endnote_groups, endnote_section
from galley.structure._ids import numbered
from galley.structure._lines import Piece, PlacedLine, first_word
from galley.structure._linking import body_candidates, linked
from galley.structure._margins import (
    BesideLine,
    InNote,
    InParagraph,
    Place,
    Stays,
    beside_lines,
    joined_margin_notes,
    margin_note_places,
    placing_order,
    split_beside_margin_notes,
)
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
    BodyBlock,
    Entry,
    MarginNote,
    PageParts,
    body_entries,
)
from galley.structure._quotes import book_density, with_quotes
from galley.structure._references import NoteToMatch, match_endnotes, match_footnotes
from galley.structure._runs import Label
from galley.structure._unnumbered import (
    Unnumbered,
    UnnumberedNote,
    changes_in_order,
    first_page,
    joined,
    merged_origin,
    piece_origin,
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
            case BodyBlock():
                body.append(_body_block(entry, book_words, word_list))
            case MarginNote(piece):
                body.append(joined(piece, BlockKind.MARGIN_NOTE, book_words, word_list))
            case _:
                assert_never(entry)
    return tuple(body)


def _body_block(
    block: BodyBlock, book_words: frozenset[str], word_list: frozenset[str]
) -> Unnumbered:
    """A block of the body stream with its hyphens joined; a heading whose
    first line is its chapter label has that line's words, joined by single
    spaces, as its label, and the lines after it as its text (spec section
    14, "Heading blocks")."""
    lines = block.piece.lines
    match block.label:
        case Label.FIRST_LINE:
            label = " ".join(word.text for word in lines[0].line.words)
            text = Piece(lines[1:])
        case Label.NONE:
            label = None
            text = block.piece
        case _:
            assert_never(block.label)
    return replace(
        joined(text, block.kind, book_words, word_list),
        origin=piece_origin(block.piece),
        level=block.level,
        label=label,
    )


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
    bibliography: frozenset[int],
) -> tuple[PageParts, ...]:
    """The pages with the notes left at the foot of their body taken, in a
    book numbered per page, except on the pages of the endnote section
    (spec section 11, "Notes left in the body") and those of `bibliography`,
    in a bibliographical note (section 16), and each page's body
    notes put before its band regions. `band_notes` are each page's notes
    of its band; `body_word_height` is in points."""
    taken = tuple(
        take_body_notes(page, notes, form, body_word_height)
        if numbering is Numbering.PER_PAGE
        and page.index not in section_pages
        and page.index not in bibliography
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


def _lines_before_notes(
    entries: Sequence[Entry], book_footnotes: Sequence[Footnote]
) -> frozendict[int, tuple[BesideLine, ...]]:
    """The lines a margin note may stand beside, by page index, before the
    notes are made: the body's paragraphs, the endnote section's paragraphs
    as the lines of their endnotes, and the footnotes' lines (spec section
    13, rules 1 and 3)."""
    section = endnote_section(entries)
    groups = endnote_groups(entries, section) if section is not None else ()
    return beside_lines(
        entries,
        frozenset(section.paragraphs if section is not None else ()),
        (
            *(
                tuple(entries[position].piece.lines for position in group.paragraphs)
                for group in groups
            ),
            *((footnote.lines,) for footnote in book_footnotes),
        ),
    )


def _with_margin_notes_placed(
    body: tuple[Unnumbered, ...],
    notes: tuple[UnnumberedNote, ...],
    kept_positions: Sequence[int],
    entries: Sequence[Entry],
    places: frozendict[int, Place],
) -> tuple[tuple[Unnumbered, ...], tuple[UnnumberedNote, ...]]:
    """The body with each margin note of `places` before its paragraph or
    where it stands, and the notes with each margin note placed inside one
    as a block before the block it is beside (spec section 13, rules 4 to
    6). Several before one paragraph or block go by page and from the top
    down. `kept_positions` gives the entry position of each block of
    `body`; `places` holds the place of each margin note by its entry
    position."""
    block_of = dict(zip(kept_positions, body, strict=True))
    before_paragraph: dict[int, list[int]] = {}
    before_block: dict[tuple[int, int], list[int]] = {}
    for position, place in places.items():
        match place:
            case InParagraph(entry, _):
                before_paragraph.setdefault(entry, []).append(position)
            case InNote(note, block):
                before_block.setdefault((note, block), []).append(position)
            case Stays():
                pass
            case _:
                assert_never(place)

    def placed_before(positions: Sequence[int]) -> tuple[Unnumbered, ...]:
        return tuple(block_of[p] for p in placing_order(entries, positions))

    ordered = tuple(
        block
        for position in kept_positions
        if position not in places or isinstance(places[position], Stays)
        for block in (
            *placed_before(before_paragraph.get(position, ())),
            block_of[position],
        )
    )
    return (
        ordered,
        tuple(
            replace(
                note,
                blocks=tuple(
                    block
                    for number, note_block in enumerate(note.blocks)
                    for block in (
                        *placed_before(before_block.get((note_position, number), ())),
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
    contents_pages: frozenset[int],
) -> Assembled:
    """The work after the per-page parts (spec section 2, steps 2.5 and 3),
    in page order: the notes left at the foot of each page's body taken
    out of it, the paragraphs of the body stream with their hyphens joined,
    split at the indented lines beside margin notes, the regions of one
    printed margin note joined, the footnotes of the band and of the body
    with their markers, the endnotes, the references linked to their
    notes, the quotes, each margin note placed before the paragraph whose
    line it is beside or inside the note whose line it is beside, and the
    ids. A bibliographical note's band blocks are body paragraphs (spec
    section 16). `word_list` is in lower case; `body_word_height` and
    `body_line_pitch` are in points; `contents_pages` are the pages of the
    printed table of contents, whose lines are never quotes and after the
    last of which the references to endnotes are taken."""
    last_contents_page = max(contents_pages, default=-1)
    form = book_marker_form(
        first_word(piece.lines[0]) for page in parts for piece in page.band_blocks
    )
    density = book_density(tuple(line for page in parts for line in page.body))
    # Spec section 16: a bibliographical note's band blocks are paragraphs,
    # and its pages' notes are not taken from the body.
    found = bibliography(parts)
    parts = tuple(with_band_as_body(page, found, form) for page in parts)
    band_notes = tuple(page_notes(page.band_regions, word_list) for page in parts)
    numbering = book_numbering(band_notes)
    # The paragraphs are found twice: the first time only for the pages of
    # the endnote section, which the notes left in the body (step 2.5) skip
    # and whose first page starts a paragraph; both change the paragraphs,
    # so the section's paragraphs are taken from the second.
    section_pages = _section_pages(body_entries(parts, form))
    pages = _taken_body_notes(
        parts,
        band_notes,
        numbering,
        form,
        body_word_height,
        section_pages,
        found.pages,
    )
    book_footnotes = footnotes(
        tuple(page_notes(page.band_regions, word_list) for page in pages),
        tuple(bool(page.body) for page in pages),
        numbering,
    )
    # Spec section 2, step 3.2, then section 13, rule 1: the paragraphs are
    # split beside the margin regions as layout gives them, then the
    # regions of one printed note are joined.
    entries = body_entries(pages, form, section_pages)
    entries = split_beside_margin_notes(
        entries, _lines_before_notes(entries, book_footnotes), body_line_pitch
    )
    entries = joined_margin_notes(
        entries, _lines_before_notes(entries, book_footnotes), body_line_pitch
    )
    section = endnote_section(entries)
    in_section = frozenset(section.paragraphs if section is not None else ())
    # Spec section 2, step 3.5: the quotes, among the body's paragraphs.
    entries = with_quotes(
        entries,
        frozenset(
            position
            for position, entry in enumerate(entries)
            if entry.piece.lines[0].page_index not in contents_pages
        )
        - in_section
        - in_bibliographical_notes(entries),
        form,
        body_word_height,
        density,
    )
    body = _body(entries, book_words, word_list)
    groups = endnote_groups(entries, section) if section is not None else ()
    endnotes = tuple(
        _NoteWithLines(
            _endnote(group, body),
            group.marker.value if group.marker else None,
            tuple(entries[position].piece.lines for position in group.paragraphs),
        )
        for group in groups
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
    places = margin_note_places(
        entries,
        beside_lines(entries, in_section, tuple(note.block_lines for note in notes)),
        body_line_pitch,
    )
    kept_positions = tuple(
        position for position in range(len(entries)) if position not in in_section
    )
    linked_body, linked_notes = _with_margin_notes_placed(
        linked_body, linked_notes, kept_positions, entries, places
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
