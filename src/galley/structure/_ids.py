"""The ids of the blocks and notes and the spans of each block (spec
section 6, "Order" and "Ids and origins"; section 11, "What is
changed")."""

from collections import Counter
from collections.abc import Sequence

from galley.model import Block, BlockKind, Emphasis, Note, Span, note_places
from galley.structure._unnumbered import Unnumbered, UnnumberedNote, first_page


def _spans(unnumbered: Unnumbered, note_ids: Sequence[str]) -> tuple[Span, ...]:
    """The block's words joined by single spaces, or in a verse block by a
    line feed where a printed line starts, each note reference a span
    of its own with the id of its note; the spaces stay with the spans
    around it (spec section 11, "What is changed"). A figure block without
    a caption has no span (section 18)."""
    if unnumbered.kind is BlockKind.FIGURE and not unnumbered.words:
        return ()
    spans: list[Span] = []
    text = ""
    verse = unnumbered.kind is BlockKind.VERSE
    for position, word in enumerate(unnumbered.words):
        # A verse block keeps its printed lines (spec section 16).
        if verse and position in unnumbered.line_starts:
            space = "\n"
        else:
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
        level=unnumbered.level,
        label=unnumbered.label,
        spans=_spans(unnumbered, note_ids),
        figure=unnumbered.figure,
        origin=unnumbered.origin,
    )


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
    # note_places counts the blocks written before a note; -1 is first of all.
    places = tuple(
        count - 1
        for count in note_places(
            tuple(first_page(block.origin) for block in blocks),
            tuple(first_page(note.origin) for note in notes),
        )
    )
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
                group=note.group,
            )
        )
    return tuple(body), tuple(numbered_notes)
