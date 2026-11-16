"""The work across pages (spec section 2, step 3), in page order: the
paragraphs of the body stream with their hyphens joined, the margin notes
after the paragraph in which their page's body ends, the footnotes cut
from the band with their markers, and the ids of the blocks and notes
(spec section 6, "Order" and "Ids and origins")."""

import bisect
import itertools
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import assert_never

from galley.model import (
    Block,
    BlockKind,
    ChangeReason,
    Emphasis,
    Note,
    NoteKind,
    Origin,
    Span,
    WordChange,
)
from galley.structure._body_notes import take_body_notes
from galley.structure._endnotes import EndnoteGroup, endnote_groups, endnote_section
from galley.structure._hyphens import PageLine, join_lines
from galley.structure._lines import Piece, first_word
from galley.structure._markers import (
    MarkerForm,
    NoteMarker,
    Reference,
    book_marker_form,
    reference_candidate,
)
from galley.structure._measures import box_of
from galley.structure._notes import Footnote, footnotes, numbered_per_page, page_notes
from galley.structure._paragraphs import (
    Entry,
    MarginNote,
    PageParts,
    Paragraph,
    body_entries,
)
from galley.structure._references import (
    Candidate,
    Link,
    NoteToMatch,
    match_endnotes,
    match_footnotes,
)


@dataclass(frozen=True, slots=True)
class _Unnumbered:
    """A block before it has its id: its kind, its words with the page of
    each, its origin, its word changes, each with the position of the word
    it gave, so that a block's changes are in the order of its words, and
    its note references: for the position of a word, the reference it
    holds and the position of its note among the notes."""

    kind: BlockKind
    words: tuple[str, ...]
    word_pages: tuple[int, ...]
    origin: tuple[Origin, ...]
    changes: tuple[tuple[int, WordChange], ...]
    links: frozendict[int, tuple[Reference, int]] = frozendict()


@dataclass(frozen=True, slots=True)
class _UnnumberedNote:
    """A note before it has its id."""

    kind: NoteKind
    marker: str
    blocks: tuple[_Unnumbered, ...]
    origin: tuple[Origin, ...]
    referenced: bool


def _origin(piece: Piece) -> tuple[Origin, ...]:
    """One origin per page the piece has lines on, with the box of those
    lines."""
    return tuple(
        Origin(page_index, box_of(tuple(line.line.box for line in lines)))
        for page_index, lines in itertools.groupby(
            piece.lines, key=lambda line: line.page_index
        )
    )


def _joined(
    piece: Piece,
    kind: BlockKind,
    book_words: frozenset[str],
    word_list: frozenset[str],
) -> _Unnumbered:
    joined = join_lines(
        tuple(
            PageLine(line.page_index, tuple(word.text for word in line.line.words))
            for line in piece.lines
        ),
        book_words,
        word_list,
    )
    return _Unnumbered(
        kind,
        joined.words,
        joined.pages,
        _origin(piece),
        tuple(zip(joined.positions, joined.changes, strict=True)),
    )


def _without_marker(
    block: _Unnumbered, marker: NoteMarker | None
) -> tuple[_Unnumbered, str]:
    """The note block without its marker, and the marker; the block as it is
    and "" when the note has no marker, or when the marker is all of its
    text (spec section 11, "The marker of a note"). A marker glued to a
    word is split off it by a note_marker word change on the note's page."""
    if (
        marker is None
        or not block.words
        or not block.words[0].startswith(marker.marker)
    ):
        return block, ""
    first = block.words[0]
    rest = first[len(marker.marker) :]
    if not rest:
        if len(block.words) == 1:
            return block, ""
        return replace(
            block, words=block.words[1:], word_pages=block.word_pages[1:]
        ), marker.marker
    change = WordChange(
        page_index=block.word_pages[0],
        before=(first,),
        after=(marker.marker, rest),
        reason=ChangeReason.NOTE_MARKER,
    )
    return replace(
        block,
        words=(rest, *block.words[1:]),
        changes=((-1, change), *block.changes),
    ), marker.marker


def _footnote(
    footnote: Footnote, book_words: frozenset[str], word_list: frozenset[str]
) -> _UnnumberedNote:
    block, marker = _without_marker(
        _joined(Piece(footnote.lines), BlockKind.PARAGRAPH, book_words, word_list),
        footnote.marker,
    )
    return _UnnumberedNote(
        kind=NoteKind.FOOTNOTE,
        marker=marker,
        blocks=(block,),
        origin=block.origin,
        referenced=False,
    )


def _spans(unnumbered: _Unnumbered, note_ids: Sequence[str]) -> tuple[Span, ...]:
    """The block's words joined by single spaces, each note reference a span
    of its own with the id of its note; the spaces stay with the spans
    around it (spec section 11, "What is changed")."""
    spans: list[Span] = []
    text = ""
    for position, word in enumerate(unnumbered.words):
        space = " " if position > 0 else ""
        link = unnumbered.links.get(position)
        if link is None:
            text += space + word
            continue
        reference, note = link
        text += space + reference.before
        if text:
            spans.append(Span(text, Emphasis.NONE, None))
        spans.append(Span(reference.reference, Emphasis.NONE, note_ids[note]))
        text = reference.after
    if text or not spans:
        spans.append(Span(text, Emphasis.NONE, None))
    return tuple(spans)


def _block(block_id: str, unnumbered: _Unnumbered, note_ids: Sequence[str]) -> Block:
    return Block(
        id=block_id,
        kind=unnumbered.kind,
        level=None,
        label=None,
        spans=_spans(unnumbered, note_ids),
        figure=None,
        origin=unnumbered.origin,
    )


def _first_page(origin: tuple[Origin, ...]) -> int:
    return origin[0].page_index


def _note_places(
    blocks: tuple[_Unnumbered, ...], notes: tuple[_UnnumberedNote, ...]
) -> tuple[int, ...]:
    """For each note, the position in `blocks` of the block markdown writes
    it after, -1 for first of all (spec section 6, "Order"): the last block
    whose first origin is on the note's first page or an earlier one."""
    first_pages = tuple(_first_page(block.origin) for block in blocks)
    last_by_page: dict[int, int] = {}
    for position, page_index in enumerate(first_pages):
        last_by_page[page_index] = position
    pages = sorted(last_by_page)
    last_up_to = tuple(
        itertools.accumulate((last_by_page[page] for page in pages), max)
    )

    def place(note: _UnnumberedNote) -> int:
        up_to = bisect.bisect_right(pages, _first_page(note.origin))
        return last_up_to[up_to - 1] if up_to > 0 else -1

    return tuple(place(note) for note in notes)


def _numbered(
    blocks: tuple[_Unnumbered, ...], notes: tuple[_UnnumberedNote, ...]
) -> tuple[tuple[Block, ...], tuple[Note, ...]]:
    """Block and note ids (spec section 6): a block's counts the blocks that
    start on its page in reading order, each note's blocks where markdown
    writes the note; a note's counts the notes that start on its page."""
    note_counts: Counter[int] = Counter()
    note_ids: list[str] = []
    for note in notes:
        page_index = _first_page(note.origin)
        note_counts[page_index] += 1
        note_ids.append(f"n-p{page_index:04d}-{note_counts[page_index]:03d}")
    places = _note_places(blocks, notes)
    notes_after: dict[int, list[int]] = {}
    for note_number, position in enumerate(places):
        notes_after.setdefault(position, []).append(note_number)
    block_counts: Counter[int] = Counter()

    def next_id(unnumbered: _Unnumbered) -> str:
        page_index = _first_page(unnumbered.origin)
        block_counts[page_index] += 1
        return f"b-p{page_index:04d}-{block_counts[page_index]:03d}"

    note_blocks: dict[int, tuple[Block, ...]] = {}
    body: list[Block] = []
    for position in range(-1, len(blocks)):
        if position >= 0:
            body.append(_block(next_id(blocks[position]), blocks[position], note_ids))
        for note_number in notes_after.get(position, []):
            note_blocks[note_number] = tuple(
                _block(next_id(block), block, note_ids)
                for block in notes[note_number].blocks
            )
    numbered_notes: list[Note] = []
    for note_number, note in enumerate(notes):
        numbered_notes.append(
            Note(
                id=note_ids[note_number],
                kind=note.kind,
                marker=note.marker,
                blocks=note_blocks[note_number],
                origin=note.origin,
                referenced=note.referenced,
            )
        )
    return tuple(body), tuple(numbered_notes)


@dataclass(frozen=True, slots=True)
class Assembled:
    """The book's blocks and notes in order, with their ids, and the word
    changes of their hyphen joins and note markers in reading order."""

    blocks: tuple[Block, ...]
    notes: tuple[Note, ...]
    word_changes: tuple[WordChange, ...]


def _changes(blocks: Sequence[_Unnumbered]) -> tuple[WordChange, ...]:
    """The word changes of `blocks`, block by block, each block's in the
    order of its words."""
    return tuple(
        change
        for block in blocks
        for _, change in sorted(block.changes, key=lambda placed: placed[0])
    )


def _linkable(reference: Reference) -> bool:
    """Whether a candidate can be linked: its reference span has no letter,
    since a span that was a whole word holds only digits and symbols
    (architecture section 13), and every reference with a letter is a
    bracketed word of its own ("(i)", "(li)"), which stays in its word."""
    return not any(character.isalpha() for character in reference.reference)


def _candidates(body: Sequence[_Unnumbered]) -> tuple[Candidate, ...]:
    """The candidate references of the body's paragraphs, in reading order."""
    return tuple(
        Candidate(block_position, word_position, page_index, reference)
        for block_position, block in enumerate(body)
        if block.kind is BlockKind.PARAGRAPH
        for word_position, (word, page_index) in enumerate(
            zip(block.words, block.word_pages, strict=True)
        )
        if (reference := reference_candidate(word)) is not None and _linkable(reference)
    )


def _with_links(block: _Unnumbered, links: Sequence[Link]) -> _Unnumbered:
    """`block` with `links`, its references to notes, each glued reference
    split off its word by a note_marker word change on the word's page."""
    changes = tuple(
        (
            link.candidate.word,
            WordChange(
                page_index=link.candidate.page_index,
                before=(block.words[link.candidate.word],),
                after=parts,
                reason=ChangeReason.NOTE_MARKER,
            ),
        )
        for link in links
        if len(
            parts := tuple(
                part
                for part in (
                    link.candidate.reference.before,
                    link.candidate.reference.reference,
                    link.candidate.reference.after,
                )
                if part
            )
        )
        > 1
    )
    return replace(
        block,
        changes=block.changes + changes,
        links=frozendict(
            block.links
            | {
                link.candidate.word: (link.candidate.reference, link.note)
                for link in links
            }
        ),
    )


def _linked(
    body: tuple[_Unnumbered, ...],
    notes: tuple[_UnnumberedNote, ...],
    links: Sequence[Link],
) -> tuple[tuple[_Unnumbered, ...], tuple[_UnnumberedNote, ...]]:
    """The body's blocks with `links`, and the notes linked to marked as
    referenced."""
    by_block: dict[int, list[Link]] = {}
    for link in links:
        by_block.setdefault(link.candidate.block, []).append(link)
    referenced = frozenset(link.note for link in links)
    return (
        tuple(
            _with_links(block, by_block[position]) if position in by_block else block
            for position, block in enumerate(body)
        ),
        tuple(
            replace(note, referenced=True) if position in referenced else note
            for position, note in enumerate(notes)
        ),
    )


def _body(
    entries: Sequence[Entry], book_words: frozenset[str], word_list: frozenset[str]
) -> tuple[_Unnumbered, ...]:
    """The body's entries as blocks, with their hyphens joined."""
    body: list[_Unnumbered] = []
    for entry in entries:
        match entry:
            case Paragraph(piece):
                kind = BlockKind.PARAGRAPH
            case MarginNote(piece):
                kind = BlockKind.MARGIN_NOTE
            case _:
                assert_never(entry)
        body.append(_joined(piece, kind, book_words, word_list))
    return tuple(body)


def _endnote(group: EndnoteGroup, body: Sequence[_Unnumbered]) -> _UnnumberedNote:
    """An endnote of the paragraphs of `group`, its marker taken off the
    first (spec section 12)."""
    first, marker = _without_marker(body[group.paragraphs[0]], group.marker)
    blocks = (first, *(body[position] for position in group.paragraphs[1:]))
    return _UnnumberedNote(
        kind=NoteKind.ENDNOTE,
        marker=marker,
        blocks=blocks,
        origin=_merged_origin(blocks),
        referenced=False,
    )


def _merged_origin(blocks: Sequence[_Unnumbered]) -> tuple[Origin, ...]:
    """One origin per page that `blocks` have lines on, with the box that
    holds their lines there."""
    by_page: dict[int, list[Origin]] = {}
    for block in blocks:
        for origin in block.origin:
            by_page.setdefault(origin.page_index, []).append(origin)
    return tuple(
        Origin(page_index, box_of(tuple(origin.box for origin in origins)))
        for page_index, origins in by_page.items()
    )


@dataclass(frozen=True, slots=True)
class _Note:
    """A note before it has its id, with its value (spec section 11, "Its
    value"; section 12)."""

    note: _UnnumberedNote
    value: int | None


def _in_order(
    endnotes: Sequence[_Note], footnotes_: Sequence[_Note]
) -> tuple[_Note, ...]:
    """The notes by their first page and, on a page, the endnotes, which
    come from the body, before the footnotes of the band (spec section 7)."""
    keyed = [
        (_first_page(note.note.origin), 0, n, note) for n, note in enumerate(endnotes)
    ]
    keyed += [
        (_first_page(note.note.origin), 1, n, note) for n, note in enumerate(footnotes_)
    ]
    return tuple(note for *_, note in sorted(keyed, key=lambda item: item[:3]))


def _taken_body_notes(
    parts: Sequence[PageParts],
    form: MarkerForm | None,
    body_word_height: float,
    section_pages: range,
) -> tuple[PageParts, ...]:
    """The pages with the notes left at the foot of their body taken, in a
    book numbered per page, except on the pages of the endnote section
    (spec section 11, "Notes left in the body"), and each page's body
    notes put before its band regions."""
    band_notes = tuple(page_notes(page.band_regions) for page in parts)
    per_page = numbered_per_page(band_notes)
    taken = tuple(
        take_body_notes(page, notes, form, body_word_height)
        if per_page and page.index not in section_pages
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


def assemble(
    parts: Sequence[PageParts],
    book_words: frozenset[str],
    word_list: frozenset[str],
    body_word_height: float,
) -> Assembled:
    """The work after the per-page parts (spec section 2, steps 2.5 and 3),
    in page order: the notes left at the foot of each page's body taken
    out of it, the paragraphs of the body stream with their hyphens joined,
    the margin notes after the paragraph in which their page's body ends,
    the footnotes of the band and of the body with their markers, the
    endnotes, the references linked to their notes, and the ids.
    `word_list` is in lower case; `body_word_height` is in points."""
    form = book_marker_form(
        first_word(piece.lines[0]) for page in parts for piece in page.band_blocks
    )
    section_pages = _section_pages(body_entries(parts, form))
    pages = _taken_body_notes(parts, form, body_word_height, section_pages)
    entries = body_entries(pages, form, section_pages.start if section_pages else None)
    section = endnote_section(entries)
    body = _body(entries, book_words, word_list)
    groups = endnote_groups(entries, section) if section is not None else ()
    in_section = frozenset(section.paragraphs if section is not None else ())
    endnotes = tuple(
        _Note(_endnote(group, body), group.marker.value if group.marker else None)
        for group in groups
    )
    book_footnotes = footnotes(
        tuple(page_notes(page.band_regions) for page in pages),
        tuple(bool(page.body) for page in pages),
    )
    notes = _in_order(
        endnotes,
        tuple(
            _Note(_footnote(footnote, book_words, word_list), footnote.value)
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
    candidates = _candidates(kept)
    footnote_links = match_footnotes(
        tuple(
            NoteToMatch(position, _first_page(note.note.origin), note.value)
            for position, note in enumerate(notes)
            if note.note.kind is NoteKind.FOOTNOTE
        ),
        candidates,
    )
    footnoted = frozenset(link.candidate for link in footnote_links)
    endnote_links = match_endnotes(
        tuple(
            NoteToMatch(position, _first_page(note.note.origin), note.value)
            for position, note in enumerate(notes)
            if note.note.kind is NoteKind.ENDNOTE
        ),
        tuple(
            candidate
            for candidate in candidates
            if candidate.block < before_section and candidate not in footnoted
        ),
    )
    linked_body, linked_notes = _linked(
        kept, tuple(note.note for note in notes), footnote_links + endnote_links
    )
    blocks, numbered_notes = _numbered(linked_body, linked_notes)
    return Assembled(
        blocks=blocks,
        notes=numbered_notes,
        word_changes=tuple(
            sorted(
                _changes(linked_body)
                + _changes(
                    tuple(block for note in linked_notes for block in note.blocks)
                ),
                key=lambda change: change.page_index,
            )
        ),
    )
