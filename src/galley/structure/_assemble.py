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
from galley.structure._hyphens import PageLine, join_lines
from galley.structure._lines import Piece, first_word
from galley.structure._markers import NoteMarker, book_marker_form
from galley.structure._measures import box_of
from galley.structure._notes import Footnote, footnotes, numbered_per_page, page_notes
from galley.structure._paragraphs import MarginNote, PageParts, Paragraph, body_entries


@dataclass(frozen=True, slots=True)
class _Unnumbered:
    """A block before it has its id: its kind, its words with the page of
    each, its origin, and its word changes, each with the position of the
    word it gave, so that a block's changes are in the order of its words."""

    kind: BlockKind
    words: tuple[str, ...]
    word_pages: tuple[int, ...]
    origin: tuple[Origin, ...]
    changes: tuple[tuple[int, WordChange], ...]


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


def _block(block_id: str, unnumbered: _Unnumbered) -> Block:
    return Block(
        id=block_id,
        kind=unnumbered.kind,
        level=None,
        label=None,
        spans=(Span(" ".join(unnumbered.words), Emphasis.NONE, None),),
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
            body.append(_block(next_id(blocks[position]), blocks[position]))
        for note_number in notes_after.get(position, []):
            note_blocks[note_number] = tuple(
                _block(next_id(block), block) for block in notes[note_number].blocks
            )
    note_counts: Counter[int] = Counter()
    numbered_notes: list[Note] = []
    for note_number, note in enumerate(notes):
        page_index = _first_page(note.origin)
        note_counts[page_index] += 1
        numbered_notes.append(
            Note(
                id=f"n-p{page_index:04d}-{note_counts[page_index]:03d}",
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
    the notes of the band and of the body with their markers, and the ids.
    `word_list` is in lower case; `body_word_height` is in points."""
    form = book_marker_form(
        first_word(piece.lines[0]) for page in parts for piece in page.band_blocks
    )
    band_notes = tuple(page_notes(page.band_regions) for page in parts)
    taken = (
        tuple(
            take_body_notes(page, notes, form, body_word_height)
            for page, notes in zip(parts, band_notes, strict=True)
        )
        if numbered_per_page(band_notes)
        else tuple(parts)
    )
    pages = tuple(
        page
        if not page.body_notes
        else replace(page, band_regions=(page.body_notes, *page.band_regions))
        for page in taken
    )
    body: list[_Unnumbered] = []
    for entry in body_entries(pages, form):
        match entry:
            case Paragraph(piece):
                kind = BlockKind.PARAGRAPH
            case MarginNote(piece):
                kind = BlockKind.MARGIN_NOTE
            case _:
                assert_never(entry)
        body.append(_joined(piece, kind, book_words, word_list))
    notes = tuple(
        _footnote(footnote, book_words, word_list)
        for footnote in footnotes(
            tuple(page_notes(page.band_regions) for page in pages),
            tuple(bool(page.body) for page in pages),
        )
    )
    blocks, numbered_notes = _numbered(tuple(body), notes)
    return Assembled(
        blocks=blocks,
        notes=numbered_notes,
        word_changes=tuple(
            sorted(
                _changes(body)
                + _changes(tuple(block for note in notes for block in note.blocks)),
                key=lambda change: change.page_index,
            )
        ),
    )
