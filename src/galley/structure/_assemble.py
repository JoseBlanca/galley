"""The work after the per-page parts (spec section 2, steps 2.5 and 3),
in page order: the notes left in the body, the paragraphs of the body
stream, the endnote section, the footnotes, the references linked to
their notes, the margin notes placed (`_margins`), and the ids
(`_ids`)."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import assert_never

from galley.model import Block, BlockKind, Note, NoteKind, WordChange
from galley.structure._bibliography import (
    bibliography,
    in_bibliographical_notes,
    with_band_as_body,
)
from galley.structure._body_notes import take_body_notes
from galley.structure._endnotes import EndnoteSection, endnote_groups, endnote_section
from galley.structure._ids import numbered
from galley.structure._index_entries import with_index_breaks, with_index_entries
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
from galley.structure._markers import MarkerForm, NoteMarker, book_marker_form
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
from galley.structure._plates import with_figures
from galley.structure._quotes import book_density, with_quotes
from galley.structure._references import (
    Link,
    NoteToMatch,
    match_endnotes,
    match_footnotes,
)
from galley.structure._runs import LabelLine
from galley.structure._unnumbered import (
    Unnumbered,
    UnnumberedNote,
    changes_in_order,
    first_page,
    joined,
    joined_margin_note,
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
    entries: Sequence[Entry],
    book_words: frozenset[str],
    word_list: frozenset[str],
    common_inner_words: frozenset[str],
) -> tuple[Unnumbered, ...]:
    """The body's entries as blocks, with their hyphens joined, and in a
    margin note the words whose hyphen was lost (spec section 5)."""
    body: list[Unnumbered] = []
    for entry in entries:
        match entry:
            case BodyBlock():
                body.append(_body_block(entry, book_words, word_list))
            case MarginNote(piece):
                body.append(
                    joined_margin_note(piece, book_words, word_list, common_inner_words)
                )
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
    match block.label_line:
        case LabelLine.FIRST:
            label = " ".join(word.text for word in lines[0].line.words)
            text = Piece(lines[1:])
        case LabelLine.NONE:
            label = None
            text = block.piece
        case _:
            assert_never(block.label_line)
    return replace(
        joined(text, block.kind, book_words, word_list),
        origin=piece_origin(block.piece),
        level=block.level,
        label=label,
    )


@dataclass(frozen=True, slots=True)
class _Endnote:
    """An endnote before it is made: its marker, None for the endnote before
    the section's first marker, and its paragraphs (spec section 12)."""

    marker: NoteMarker | None
    paragraphs: tuple[Piece, ...]


type _NoteSource = _Endnote | Footnote


def _source_lines(source: _NoteSource) -> tuple[tuple[PlacedLine, ...], ...]:
    """The lines of each block of the note `source` will make."""
    match source:
        case _Endnote(_, paragraphs):
            return tuple(piece.lines for piece in paragraphs)
        case Footnote(lines, _, _):
            return (lines,)
        case _:
            assert_never(source)


def _note_sources(
    entries: Sequence[Entry],
    section: EndnoteSection | None,
    book_footnotes: Sequence[Footnote],
) -> tuple[_NoteSource, ...]:
    """The book's notes before they are made, in the order of `notes` (spec
    section 7): by their first page and, on a page, the endnotes, which
    come from the body, before the footnotes of the band. The endnotes are
    the groups of the endnote section `section` of `entries`."""
    groups = endnote_groups(entries, section) if section is not None else ()
    endnotes = tuple(
        _Endnote(
            group.marker,
            tuple(entries[position].piece for position in group.paragraphs),
        )
        for group in groups
    )
    keyed = [
        (note.paragraphs[0].lines[0].page_index, 0, position, note)
        for position, note in enumerate(endnotes)
    ] + [
        (note.lines[0].page_index, 1, position, note)
        for position, note in enumerate(book_footnotes)
    ]
    return tuple(note for *_, note in sorted(keyed, key=lambda item: item[:3]))


def _note(
    source: _NoteSource,
    blocks_of: Mapping[Piece, Unnumbered],
    book_words: frozenset[str],
    word_list: frozenset[str],
) -> UnnumberedNote:
    """The note of `source`, its marker taken off its first block (spec
    sections 11 and 12): an endnote's blocks are the body blocks
    `blocks_of` its paragraphs."""
    match source:
        case _Endnote(marker, paragraphs):
            first, taken = without_marker(blocks_of[paragraphs[0]], marker)
            blocks = (first, *(blocks_of[piece] for piece in paragraphs[1:]))
            return UnnumberedNote(
                kind=NoteKind.ENDNOTE,
                marker=taken,
                blocks=blocks,
                origin=merged_origin(blocks),
                referenced=False,
            )
        case Footnote():
            return _footnote(source, book_words, word_list)
        case _:
            assert_never(source)


def _value(source: _NoteSource) -> int | None:
    """The note's value (spec section 11, "Its value"; section 12)."""
    match source:
        case _Endnote(marker, _):
            return marker.value if marker is not None else None
        case Footnote(_, _, value):
            return value
        case _:
            assert_never(source)


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
    (spec section 11, "Notes left in the body"), those of `bibliography`,
    in a bibliographical note (section 16), and those of an index (section
    17), and each page's body
    notes put before its band regions. `band_notes` are each page's notes
    of its band; `body_word_height` is in points."""
    taken = tuple(
        take_body_notes(page, notes, form, body_word_height)
        if numbering is Numbering.PER_PAGE
        and page.index not in section_pages
        and page.index not in bibliography
        and not page.index_lines
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


def _in_section(
    entries: Sequence[Entry], section_pieces: frozenset[Piece]
) -> frozenset[int]:
    """The positions in `entries` of the endnote section's paragraphs, given
    by their pieces, which splitting paragraphs and joining margin notes
    leave as they are (spec section 13, rule 3, splits only paragraphs of
    the body)."""
    return frozenset(
        position
        for position, entry in enumerate(entries)
        if isinstance(entry, BodyBlock) and entry.piece in section_pieces
    )


def _beside(
    entries: Sequence[Entry],
    section_pieces: frozenset[Piece],
    sources: Sequence[_NoteSource],
) -> frozendict[int, tuple[BesideLine, ...]]:
    """The lines a margin note may stand beside, by page index: the body's
    blocks but the endnote section's paragraphs, and the lines of each
    note's blocks, the notes in the order of `sources` (spec section 13,
    rules 1 to 3)."""
    return beside_lines(
        entries,
        _in_section(entries, section_pieces),
        tuple(_source_lines(source) for source in sources),
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


def _links(
    body: Sequence[Unnumbered],
    notes: Sequence[UnnumberedNote],
    values: Sequence[int | None],
    before_section: int,
    last_contents_page: int,
) -> tuple[Link, ...]:
    """The references of `body`, the body's blocks but the endnote
    section's, matched to `notes`, whose values are `values` (spec
    sections 11 and 12): the footnotes first, then the endnotes, among the
    candidates of the first `before_section` blocks after the last
    contents page that no footnote took."""
    candidates = body_candidates(body)
    footnote_links = match_footnotes(
        tuple(
            NoteToMatch(position, first_page(note.origin), value)
            for position, (note, value) in enumerate(zip(notes, values, strict=True))
            if note.kind is NoteKind.FOOTNOTE
        ),
        candidates,
    )
    footnoted = frozenset(link.candidate for link in footnote_links)
    endnote_links = match_endnotes(
        tuple(
            NoteToMatch(position, first_page(note.origin), value)
            for position, (note, value) in enumerate(zip(notes, values, strict=True))
            if note.kind is NoteKind.ENDNOTE
        ),
        tuple(
            candidate
            for candidate in candidates
            if candidate.block < before_section
            and candidate.page_index > last_contents_page
            and candidate not in footnoted
        ),
    )
    return footnote_links + endnote_links


def assemble(
    parts: Sequence[PageParts],
    book_words: frozenset[str],
    word_list: frozenset[str],
    common_inner_words: frozenset[str],
    body_word_height: float,
    body_line_pitch: float,
    contents_pages: frozenset[int],
) -> Assembled:
    """The work after the per-page parts (spec section 2, steps 2.5 and 3),
    in page order: the notes left at the foot of each page's body taken
    out of it, the blocks of the body stream (paragraphs, headings,
    summaries and verse) with their hyphens joined,
    split at the indented lines beside margin notes, the regions of one
    printed margin note joined, the footnotes of the band and of the body
    with their markers, the endnotes, the references linked to their
    notes, the quotes, each margin note placed before the paragraph whose
    line it is beside or inside the note whose line it is beside, the
    figure block of each plate page, and the ids. A bibliographical note's band blocks are body paragraphs (spec
    section 16). `word_list` is in lower case; `body_word_height` and
    `body_line_pitch` are in points; `contents_pages` are the pages of the
    printed table of contents, whose lines are never quotes and after the
    last of which the references to endnotes are taken."""
    form = book_marker_form(
        first_word(piece.lines[0]) for page in parts for piece in page.band_blocks
    )
    density = book_density(tuple(line for page in parts for line in page.body))
    # Spec section 16: a bibliographical note's band blocks are paragraphs,
    # and its pages' notes are not taken from the body.
    found = bibliography(parts)
    parts = with_index_breaks(
        tuple(with_band_as_body(page, found, form) for page in parts)
    )
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
    entries = body_entries(pages, form, section_pages)
    section = endnote_section(entries)
    section_pieces = frozenset(
        entries[position].piece for position in (section.paragraphs if section else ())
    )
    sources = _note_sources(entries, section, book_footnotes)
    # Spec section 2, step 3.2, then section 13, rule 1: the paragraphs are
    # split beside the margin regions as layout gives them, then the
    # regions of one printed note are joined.
    entries = split_beside_margin_notes(
        entries, _beside(entries, section_pieces, sources), body_line_pitch
    )
    entries = joined_margin_notes(
        entries, _beside(entries, section_pieces, sources), body_line_pitch
    )
    # Spec section 2, step 3.4: the index entries.
    entries = with_index_entries(entries, pages)
    in_section = _in_section(entries, section_pieces)
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
    body = _body(entries, book_words, word_list, common_inner_words)
    blocks_of = {entry.piece: block for entry, block in zip(entries, body, strict=True)}
    notes = tuple(_note(source, blocks_of, book_words, word_list) for source in sources)
    kept_positions = tuple(
        position for position in range(len(entries)) if position not in in_section
    )
    kept = tuple(body[position] for position in kept_positions)
    linked_body, linked_notes = linked(
        kept,
        notes,
        _links(
            kept,
            notes,
            tuple(_value(source) for source in sources),
            sum(1 for p in kept_positions if p < min(in_section, default=len(entries))),
            max(contents_pages, default=-1),
        ),
    )
    places = margin_note_places(
        entries, _beside(entries, section_pieces, sources), body_line_pitch
    )
    linked_body, linked_notes = _with_margin_notes_placed(
        linked_body, linked_notes, kept_positions, entries, places
    )
    # Spec section 18: the figure blocks, side text of their pages.
    linked_body = with_figures(linked_body, parts, book_words, word_list)
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
