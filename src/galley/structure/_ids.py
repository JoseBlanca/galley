"""The ids of the blocks and notes and the spans of each block (spec
section 6, "Order" and "Ids and origins"; section 11, "What is
changed")."""

from collections import Counter
from collections.abc import Sequence

from galley.model import Block, BlockKind, Emphasis, Note, Span, note_places
from galley.structure._markers import Reference, ReferenceForm
from galley.structure._unnumbered import Unnumbered, UnnumberedNote, first_page

# Spec section 23: the space before a spaced sign in a French book.
_NO_BREAK_SPACE = "\u00a0"
# Spec section 11, "What is changed": a backslash of its own, Domesday's
# reading of a raised number, is written against the word before it.
_BACKSLASH = "\\"


def _against_the_word_before(reference: Reference) -> bool:
    """Whether a reference that is a word of its own is written against the
    word before it (spec section 11, "What is changed"): a number, or a
    backslash; not a bracketed number nor a sign "^", "*" or "•"."""
    return not reference.before and (
        reference.form is ReferenceForm.GLUED or reference.reference == _BACKSLASH
    )


def _spans(unnumbered: Unnumbered, note_ids: Sequence[str]) -> tuple[Span, ...]:
    """The block's words joined by single spaces, or by a no-break space
    before the words of its `no_break` (section 23), or in a verse block and
    a verse epigraph by a line feed where a printed line starts, each note reference a span
    of its own with the id of its note; the spaces stay with the spans
    around it, but the one before a reference that is a number or a
    backslash of its own, which is written against the word before it
    (spec section 11, "What is changed"). A figure block without
    a caption has no span (section 18)."""
    if unnumbered.kind is BlockKind.FIGURE and not unnumbered.words:
        return ()
    spans: list[Span] = []
    text = ""
    # A verse epigraph keeps its line starts, a prose one has none (spec
    # section 22, "The block").
    verse = unnumbered.kind in {BlockKind.VERSE, BlockKind.EPIGRAPH}
    for position, word in enumerate(unnumbered.words):
        # A verse block keeps its printed lines (spec section 16).
        if verse and position in unnumbered.line_starts:
            space = "\n"
        elif position in unnumbered.no_break:
            space = _NO_BREAK_SPACE
        else:
            space = " " if position > 0 else ""
        link = unnumbered.links.get(position)
        if link is None:
            text += space + word
            continue
        reference, note = link
        if not _against_the_word_before(reference):
            text += space
        text += reference.before
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
        source=unnumbered.source,
        page_number=unnumbered.page_number,
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
