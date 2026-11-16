"""The ids of the blocks and notes and the spans of each block (spec
section 6, "Order" and "Ids and origins"; section 11, "What is
changed")."""

import bisect
import itertools
from collections import Counter
from collections.abc import Sequence

from galley.model import Block, Emphasis, Note, Span
from galley.structure._unnumbered import Unnumbered, UnnumberedNote, first_page


def _spans(unnumbered: Unnumbered, note_ids: Sequence[str]) -> tuple[Span, ...]:
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


def _block(block_id: str, unnumbered: Unnumbered, note_ids: Sequence[str]) -> Block:
    return Block(
        id=block_id,
        kind=unnumbered.kind,
        level=None,
        label=None,
        spans=_spans(unnumbered, note_ids),
        figure=None,
        origin=unnumbered.origin,
    )


def _note_places(
    blocks: tuple[Unnumbered, ...], notes: tuple[UnnumberedNote, ...]
) -> tuple[int, ...]:
    """For each note, the position in `blocks` of the block markdown writes
    it after, -1 for first of all (spec section 6, "Order"): the last block
    whose first origin is on the note's first page or an earlier one."""
    first_pages = tuple(first_page(block.origin) for block in blocks)
    last_by_page: dict[int, int] = {}
    for position, page_index in enumerate(first_pages):
        last_by_page[page_index] = position
    pages = sorted(last_by_page)
    last_up_to = tuple(
        itertools.accumulate((last_by_page[page] for page in pages), max)
    )

    def place(note: UnnumberedNote) -> int:
        up_to = bisect.bisect_right(pages, first_page(note.origin))
        return last_up_to[up_to - 1] if up_to > 0 else -1

    return tuple(place(note) for note in notes)


def numbered(
    blocks: tuple[Unnumbered, ...], notes: tuple[UnnumberedNote, ...]
) -> tuple[tuple[Block, ...], tuple[Note, ...]]:
    """Block and note ids (spec section 6): a block's counts the blocks that
    start on its page in reading order, each note's blocks where markdown
    writes the note; a note's counts the notes that start on its page."""
    note_counts: Counter[int] = Counter()
    note_ids: list[str] = []
    for note in notes:
        page_index = first_page(note.origin)
        note_counts[page_index] += 1
        note_ids.append(f"n-p{page_index:04d}-{note_counts[page_index]:03d}")
    places = _note_places(blocks, notes)
    notes_after: dict[int, list[int]] = {}
    for note_number, position in enumerate(places):
        notes_after.setdefault(position, []).append(note_number)
    block_counts: Counter[int] = Counter()

    def next_id(unnumbered: Unnumbered) -> str:
        page_index = first_page(unnumbered.origin)
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
