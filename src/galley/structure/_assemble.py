"""The work after the per-page parts (spec section 2, steps 2.5 and 3),
in page order: the notes left in the body, the paragraphs of the body
stream, the endnote section, the footnotes, the references linked to
their notes, the margin notes placed (`_margins`), and the ids
(`_ids`)."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import assert_never

from galley.config import Language
from galley.model import (
    Block,
    BlockKind,
    Note,
    NoteKind,
    Removal,
    WordChange,
    block_text,
)
from galley.structure._bibliography import (
    bibliography,
    in_bibliographical_notes,
    with_band_as_body,
)
from galley.structure._body_notes import take_body_notes
from galley.structure._case_split import split_glued_words
from galley.structure._contents import (
    ContentsEntry,
    contents_entries,
    is_link_candidate,
    run_links,
)
from galley.structure._endnotes import (
    NoteGroup,
    endnote_section,
    group_reaches,
    note_groups,
    with_group_headings_cut,
    with_run_on_endnotes_split,
)
from galley.structure._figure_blocks import with_figures, with_in_page_figures
from galley.structure._ids import numbered
from galley.structure._index_entries import with_index_breaks, with_index_entries
from galley.structure._lines import Piece, PlacedLine, first_word
from galley.structure._linking import body_candidates, linked
from galley.structure._lists import StreamPage, list_items
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
from galley.structure._markers import (
    MarkerForm,
    NoteMarker,
    book_marker_form,
    endnote_candidate,
)
from galley.structure._measures import letters
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
    ContentsLine,
    Entry,
    LineRole,
    MarginNote,
    PageParts,
    body_entries,
)
from galley.structure._quotes import book_density, with_quotes
from galley.structure._references import (
    BodyWord,
    Link,
    NoteToMatch,
    foreign_signs,
    gap_links,
    match_endnotes,
    match_footnotes,
    with_values_in_order,
)
from galley.structure._runs import EpigraphParts, LabelLine, QuotationForm
from galley.structure._spaced import with_spaced_signs
from galley.structure._unnumbered import (
    Unnumbered,
    UnnumberedNote,
    changes_in_order,
    first_page,
    joined,
    joined_margin_note,
    merged_origin,
    piece_origin,
    with_list_marker,
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
    """The book's blocks and notes in order, with their ids, the word
    changes of their hyphen joins and note markers in reading order, and
    what was removed across pages: the leader dots of the contents
    entries (spec section 30, rule 6)."""

    blocks: tuple[Block, ...]
    notes: tuple[Note, ...]
    word_changes: tuple[WordChange, ...]
    removals: tuple[Removal, ...]


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


def _mended(
    block: Unnumbered,
    word_list: frozenset[str],
    book_words: frozenset[str],
    common_inner_words: frozenset[str],
    language: Language,
) -> Unnumbered:
    """`block` with its words glued at a case change split (spec section
    24) and then its spaced signs attached, or given a no-break space in a
    French book (section 23)."""
    return with_spaced_signs(
        split_glued_words(block, word_list, book_words, common_inner_words),
        language,
    )


def _body_block(
    block: BodyBlock, book_words: frozenset[str], word_list: frozenset[str]
) -> Unnumbered:
    """A block of the body stream with its hyphens joined; a heading whose
    first line is its chapter label has that line's words, joined by single
    spaces, as its label, and the lines after it as its text (spec section
    14, "Heading blocks"); an epigraph has its quotation's lines as its
    text and its source apart (`_epigraph_block`)."""
    if block.epigraph is not None:
        return _epigraph_block(block.piece, block.epigraph, book_words, word_list)
    if block.contents is not None:
        return _contents_block(block.piece, block.contents, book_words, word_list)
    if block.marker is not None:
        # Spec section 29, "Blocks": joined as a paragraph, the marker its
        # label.
        return with_list_marker(
            replace(
                joined(block.piece, BlockKind.LIST_ITEM, book_words, word_list),
                origin=piece_origin(block.piece),
            ),
            block.marker,
        )
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


def _contents_block(
    piece: Piece,
    entry: ContentsEntry,
    book_words: frozenset[str],
    word_list: frozenset[str],
) -> Unnumbered:
    """A contents entry's block (spec section 30, rule 10): its title's
    lines joined as a paragraph's, hyphens joined; its label, page number
    and depth; its origin all its lines, `piece`."""
    return replace(
        joined(Piece(entry.title), BlockKind.CONTENTS_ENTRY, book_words, word_list),
        origin=piece_origin(piece),
        level=entry.level,
        label=entry.label,
        page_number=entry.page_number,
    )


def _epigraph_block(
    piece: Piece,
    parts: EpigraphParts,
    book_words: frozenset[str],
    word_list: frozenset[str],
) -> Unnumbered:
    """An epigraph block (spec section 22, "The block"): its text the
    quotation's lines joined as a paragraph's, hyphens joined, with a line
    feed between them when it is verse; its source apart, with the record
    of its dash's removal after the quotation's word changes; its origin
    the quotation's and the source's lines."""
    quotation = joined(
        Piece(piece.lines[: parts.quotation_lines]),
        BlockKind.EPIGRAPH,
        book_words,
        word_list,
    )
    match parts.form:
        case QuotationForm.VERSE:
            line_starts = quotation.line_starts
        case QuotationForm.PROSE:
            line_starts = frozenset()
        case _:
            assert_never(parts.form)
    dash = (
        ((len(quotation.words), parts.source_dash),)
        if parts.source_dash is not None
        else ()
    )
    return replace(
        quotation,
        origin=piece_origin(piece),
        changes=quotation.changes + dash,
        line_starts=line_starts,
        source=parts.source,
    )


@dataclass(frozen=True, slots=True)
class _Endnote:
    """An endnote before it is made: its marker, None for the endnote before
    the section's first marker, its paragraphs, the position of its note
    group among the section's, and, on a group's first endnote, the
    group's heading as printed (spec section 12)."""

    marker: NoteMarker | None
    paragraphs: tuple[Piece, ...]
    group: int
    group_heading: str | None


type _NoteSource = _Endnote | Footnote


def _source_lines(source: _NoteSource) -> tuple[tuple[PlacedLine, ...], ...]:
    """The lines of each block of the note `source` will make."""
    match source:
        case _Endnote(paragraphs=paragraphs):
            return tuple(piece.lines for piece in paragraphs)
        case Footnote(lines, _, _):
            return (lines,)
        case _:
            assert_never(source)


def _heading_text(piece: Piece) -> str:
    """A group heading as printed: the words of its lines joined by single
    spaces (spec section 12)."""
    return " ".join(word.text for line in piece.lines for word in line.line.words)


def _note_sources(
    entries: Sequence[Entry],
    groups: Sequence[NoteGroup],
    book_footnotes: Sequence[Footnote],
) -> tuple[_NoteSource, ...]:
    """The book's notes before they are made, in the order of `notes` (spec
    section 7): by their first page and, on a page, the endnotes, which
    come from the body, before the footnotes of the band. The endnotes are
    those of the note groups `groups` of the endnote section of
    `entries`."""
    endnotes = tuple(
        _Endnote(
            endnote.marker,
            tuple(entries[position].piece for position in endnote.paragraphs),
            number,
            _heading_text(entries[group.heading].piece)
            if group.heading is not None and first
            else None,
        )
        for number, group in enumerate(groups)
        for first, endnote in zip(
            (True, *(False for _ in group.endnotes[1:])), group.endnotes, strict=True
        )
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
        case _Endnote(marker, paragraphs, _, group_heading):
            first, taken = without_marker(blocks_of[paragraphs[0]], marker)
            blocks = (first, *(blocks_of[piece] for piece in paragraphs[1:]))
            return UnnumberedNote(
                kind=NoteKind.ENDNOTE,
                marker=taken,
                blocks=blocks,
                origin=merged_origin(blocks),
                referenced=False,
                group=group_heading,
            )
        case Footnote():
            return _footnote(source, book_words, word_list)
        case _:
            assert_never(source)


def _value(source: _NoteSource) -> int | None:
    """The note's value (spec section 11, "Its value"; section 12)."""
    match source:
        case _Endnote(marker=marker):
            return marker.value if marker is not None else None
        case Footnote(_, _, value):
            return value
        case _:
            assert_never(source)


def _group(source: _NoteSource) -> int | None:
    """The position of an endnote's note group, None for a footnote."""
    match source:
        case _Endnote(group=group):
            return group
        case Footnote():
            return None
        case _:
            assert_never(source)


def _headings_in_notes_as_paragraphs(
    entries: Sequence[Entry], groups: Sequence[NoteGroup]
) -> tuple[Entry, ...]:
    """`entries` with each heading block of an endnote made a paragraph
    (spec section 12, "Note groups"; section 14, "Levels"): a heading in
    the notes would enter the EPUB's table of contents."""
    in_notes = frozenset(
        position
        for group in groups
        for endnote in group.endnotes
        for position in endnote.paragraphs
    )
    return tuple(
        BodyBlock(piece=entry.piece)
        if position in in_notes
        and isinstance(entry, BodyBlock)
        and entry.kind is BlockKind.HEADING
        else entry
        for position, entry in enumerate(entries)
    )


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


def _section_pages(
    entries: Sequence[Entry], contents_pages: frozenset[int], body_line_pitch: float
) -> range:
    """The page indices of the endnote section, empty without one."""
    section = endnote_section(entries, contents_pages, body_line_pitch)
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
    uncounted: frozenset[int],
    groups: Sequence[int | None],
    group_headings: Sequence[str | None],
    before_section: int,
    last_contents_page: int,
) -> tuple[Link, ...]:
    """The references of `body`, the body's blocks but the endnote
    section's, matched to `notes`, whose values are `values` and whose
    note groups are `groups` (spec sections 11 and 12): the footnotes
    first, but those at the positions `uncounted`, which their page's
    numbering leaves out, then the endnotes, among the candidates of the first
    `before_section` blocks after the last contents page that no footnote
    took; with several note groups, whose headings are `group_headings`,
    each group's endnotes among the candidates of its chapter."""
    candidates = body_candidates(body)
    footnote_links = match_footnotes(
        tuple(
            NoteToMatch(position, first_page(note.origin), value)
            for position, (note, value) in enumerate(zip(notes, values, strict=True))
            if note.kind is NoteKind.FOOTNOTE and position not in uncounted
        ),
        candidates,
    )
    footnoted = frozenset(
        (link.candidate.block, link.candidate.word) for link in footnote_links
    )
    # Endnotes take more forms of reference than footnotes (spec section 12,
    # "The candidates of endnotes").
    free = tuple(
        candidate
        for candidate in body_candidates(body, endnote_candidate)
        if candidate.block < before_section
        and candidate.page_index > last_contents_page
        and (candidate.block, candidate.word) not in footnoted
    )
    reaches = group_reaches(
        tuple(
            (position, letters(" ".join(block.words)))
            for position, block in enumerate(body[:before_section])
            if block.kind is BlockKind.HEADING
            and block.level == 1
            and first_page(block.origin) > last_contents_page
        ),
        group_headings,
        before_section,
    )
    # Spec section 12, "The gap between linked neighbours": the words of
    # the body's paragraphs where a reference the candidates missed may
    # lie, and the signs that stand for a raised number in this book.
    signs = foreign_signs(
        word for block in body[:before_section] for word in block.words
    )
    words = tuple(
        BodyWord(
            position,
            place,
            block.word_pages[place],
            word,
            block.words[place - 1] if place > 0 else "",
            block.words[place + 1] if place + 1 < len(block.words) else "",
        )
        for position, block in enumerate(body[:before_section])
        if block.kind is BlockKind.PARAGRAPH
        for place, word in enumerate(block.words)
        if block.word_pages[place] > last_contents_page
        and (position, place) not in footnoted
    )

    def group_links(group: int, start: int, end: int) -> tuple[Link, ...]:
        group_notes = with_values_in_order(
            tuple(
                NoteToMatch(position, first_page(note.origin), value)
                for position, (note, value, note_group) in enumerate(
                    zip(notes, values, groups, strict=True)
                )
                if note.kind is NoteKind.ENDNOTE and note_group == group
            )
        )
        matched = match_endnotes(
            group_notes,
            tuple(candidate for candidate in free if start <= candidate.block < end),
        )
        taken = frozenset(
            (link.candidate.block, link.candidate.word) for link in matched
        )
        return matched + gap_links(
            group_notes,
            tuple(
                word
                for word in words
                if start <= word.block < end and (word.block, word.word) not in taken
            ),
            matched,
            signs,
        )

    return footnote_links + tuple(
        link
        for group, (start, end) in enumerate(reaches)
        for link in group_links(group, start, end)
    )


def _contents_runs(contents_pages: frozenset[int]) -> tuple[tuple[int, ...], ...]:
    """The contents runs of `contents_pages`, each its consecutive page
    indices (spec section 30, "Terms")."""
    runs: list[list[int]] = []
    for page_index in sorted(contents_pages):
        if runs and runs[-1][-1] == page_index - 1:
            runs[-1].append(page_index)
        else:
            runs.append([page_index])
    return tuple(tuple(run) for run in runs)


def _run_lines(page: PageParts) -> frozenset[int]:
    """The positions in the page's body stream of the lines of its runs of
    section 2, step 2.3."""
    return frozenset(
        number for run in page.runs for number in range(run.start, run.end)
    )


def _contents_entries(
    pages: Sequence[PageParts], contents_pages: frozenset[int]
) -> tuple[ContentsEntry, ...]:
    """The entries of every contents run of `pages`, in page order (spec
    section 30): each run's body stream but its title."""
    return tuple(
        entry
        for run in _contents_runs(contents_pages)
        for entry in contents_entries(
            tuple(
                line
                for page in pages
                if page.index in run
                for taken in (_run_lines(page),)
                for number, line in enumerate(page.body)
                if number not in taken
            )
        )
    )


def _line_roles(
    pages: Sequence[PageParts],
    entries: Sequence[ContentsEntry],
    contents_pages: frozenset[int],
    section_pages: range,
    body_line_pitch: float,
) -> frozendict[tuple[int, int], LineRole]:
    """The lines of the list items and of the contents `entries`, by page
    index and position in the page's body stream (spec section 2, step
    3.1). The list rules take no line of a run of step 2.3, nor of a page
    of the contents, an index or the endnote section, `section_pages`
    (section 29); `body_line_pitch` is in points."""
    lists = list_items(
        tuple(
            StreamPage(
                page.body,
                frozenset(range(len(page.body)))
                if page.index in contents_pages
                or page.index_lines
                or page.index in section_pages
                else _run_lines(page),
                tuple(figure.box for figure in page.in_page_figures),
            )
            for page in pages
        ),
        body_line_pitch,
    )
    positions = {
        line: (page.index, number)
        for page in pages
        if page.index in contents_pages
        for number, line in enumerate(page.body)
    }
    contents = {
        positions[line]: ContentsLine(entry if number == 0 else None)
        for entry in entries
        for number, line in enumerate(entry.lines)
    }
    return frozendict(lists | contents)


def _with_contents_links(
    blocks: Sequence[Block],
    entries: Sequence[ContentsEntry],
    contents_pages: frozenset[int],
) -> tuple[Block, ...]:
    """`blocks`, the body's in order, with each contents entry linked to the
    heading of its chapter (spec section 30, rule 9), each run on its own;
    `entries` are the contents entries of the blocks, in their order."""
    entry_positions = tuple(
        position
        for position, block in enumerate(blocks)
        if block.kind is BlockKind.CONTENTS_ENTRY
    )
    heading_positions = tuple(
        position
        for position, block in enumerate(blocks)
        if block.kind is BlockKind.HEADING
    )
    headings = tuple(block_text(blocks[position]) for position in heading_positions)
    refs: dict[int, str] = {}
    for run in _contents_runs(contents_pages):
        candidates = tuple(
            position
            for position, entry in zip(entry_positions, entries, strict=True)
            if entry.lines[0].page_index in run
            and not entry.topics
            and is_link_candidate(block_text(blocks[position]))
        )
        for candidate, heading in run_links(
            tuple(block_text(blocks[position]) for position in candidates), headings
        ):
            refs[candidates[candidate]] = blocks[heading_positions[heading]].id
    return tuple(
        replace(block, heading_ref=refs[position]) if position in refs else block
        for position, block in enumerate(blocks)
    )


def assemble(
    parts: Sequence[PageParts],
    book_words: frozenset[str],
    word_list: frozenset[str],
    common_inner_words: frozenset[str],
    body_word_height: float,
    body_line_pitch: float,
    contents_pages: frozenset[int],
    language: Language,
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
    last of which the references to endnotes are taken; `language` is the
    book's, which decides what a spaced sign becomes (spec section 23)."""
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
    section_pages = _section_pages(
        body_entries(parts, form, body_word_height=body_word_height),
        contents_pages,
        body_line_pitch,
    )
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
    # Spec section 2, step 3.1: the list items and the contents entries.
    contents = _contents_entries(pages, contents_pages)
    entries = body_entries(
        pages,
        form,
        section_pages,
        _line_roles(pages, contents, contents_pages, section_pages, body_line_pitch),
        body_word_height=body_word_height,
    )
    section = endnote_section(entries, contents_pages, body_line_pitch)
    if section is not None:
        entries = with_group_headings_cut(entries, section, body_line_pitch)
        section = endnote_section(entries, contents_pages, body_line_pitch)
    if section is not None:
        entries = with_run_on_endnotes_split(entries, section)
        section = endnote_section(entries, contents_pages, body_line_pitch)
    section_pieces = frozenset(
        entries[position].piece for position in (section.paragraphs if section else ())
    )
    groups = (
        note_groups(entries, section, body_line_pitch) if section is not None else ()
    )
    group_headings = tuple(
        _heading_text(entries[group.heading].piece)
        if group.heading is not None
        else None
        for group in groups
    )
    entries = _headings_in_notes_as_paragraphs(entries, groups)
    sources = _note_sources(entries, groups, book_footnotes)
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

    def mended(block: Unnumbered) -> Unnumbered:
        return _mended(block, word_list, book_words, common_inner_words, language)

    # Spec section 2, the paragraph after the steps: the case split and the
    # spaced signs, once the words are joined and the notes' markers taken.
    body = tuple(mended(block) for block in body)
    notes = tuple(
        replace(note, blocks=tuple(mended(block) for block in note.blocks))
        for note in notes
    )
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
            frozenset(
                position
                for position, source in enumerate(sources)
                if isinstance(source, Footnote) and not source.counted
            ),
            tuple(_group(source) for source in sources),
            group_headings,
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
    # Figures spec section 5: the in-page figures' blocks, each after the
    # block that holds the body line printed above it; then spec section
    # 18: the plates' figure blocks, side text of their pages.
    linked_body = with_in_page_figures(
        linked_body, pages, book_words, word_list, body_line_pitch
    )
    linked_body = tuple(
        mended(block) if block.kind is BlockKind.FIGURE else block
        for block in with_figures(linked_body, parts, book_words, word_list)
    )
    blocks, numbered_notes = numbered(linked_body, linked_notes)
    # Spec section 2, step 3.4: the links of the contents entries, once
    # every heading is known; made on the numbered blocks, whose ids they
    # name.
    blocks = _with_contents_links(blocks, contents, contents_pages)
    return Assembled(
        blocks=blocks,
        notes=numbered_notes,
        removals=tuple(removal for entry in contents for removal in entry.leader_dots),
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
