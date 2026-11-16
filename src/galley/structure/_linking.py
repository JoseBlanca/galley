"""The note references linked into the body's blocks (spec section 11,
"References" and "What is changed"): the candidates of the body's
paragraphs, and each matched one split off its word."""

from collections.abc import Sequence
from dataclasses import replace

from galley.model import BlockKind, ChangeReason, WordChange
from galley.structure._markers import Reference, reference_candidate
from galley.structure._references import Candidate, Link
from galley.structure._unnumbered import Unnumbered, UnnumberedNote


def _linkable(reference: Reference) -> bool:
    """Whether a candidate can be linked: its reference span has no letter,
    since a span that was a whole word holds only digits and symbols
    (architecture section 13), and every reference with a letter is a
    bracketed word of its own ("(i)", "(li)"), which stays in its word."""
    return not any(character.isalpha() for character in reference.reference)


# Spec sections 13 and 17: a margin note and an index entry hold no
# reference to a note.
_NOT_SEARCHED = frozenset({BlockKind.MARGIN_NOTE, BlockKind.INDEX_ENTRY})


def body_candidates(body: Sequence[Unnumbered]) -> tuple[Candidate, ...]:
    """The candidate references of the body's blocks other than margin notes
    and index entries (spec section 17, rule 4), in reading order: a
    heading holds them too (Kadesh's title, "STRATEGY*")."""
    return tuple(
        Candidate(block_position, word_position, page_index, reference)
        for block_position, block in enumerate(body)
        if block.kind not in _NOT_SEARCHED
        for word_position, (word, page_index) in enumerate(
            zip(block.words, block.word_pages, strict=True)
        )
        if (reference := reference_candidate(word)) is not None and _linkable(reference)
    )


def _with_links(block: Unnumbered, links: Sequence[Link]) -> Unnumbered:
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


def linked(
    body: tuple[Unnumbered, ...],
    notes: tuple[UnnumberedNote, ...],
    links: Sequence[Link],
) -> tuple[tuple[Unnumbered, ...], tuple[UnnumberedNote, ...]]:
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
