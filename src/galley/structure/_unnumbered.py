"""Blocks and notes before their ids (spec section 6, "Ids and origins"):
a block's words with the page of each, its word changes and its note
references, and the notes made of such blocks."""

import itertools
from collections.abc import Sequence
from dataclasses import dataclass, replace

from galley.model import BlockKind, ChangeReason, NoteKind, Origin, WordChange
from galley.structure._hyphens import PageLine, join_lines
from galley.structure._lines import Piece
from galley.structure._markers import NoteMarker, Reference
from galley.structure._measures import box_of


@dataclass(frozen=True, slots=True)
class Unnumbered:
    """A block before it has its id: its kind, its words with the page of
    each, its origin, its word changes, each with the position of the word
    it gave, so that a block's changes are in the order of its words, and
    its note references: for the position of a word, the reference it
    holds and the position of its note among the notes; a heading's level
    and chapter label; and the positions of the words that start a printed
    line after the first, which a verse block keeps (spec section 16)."""

    kind: BlockKind
    words: tuple[str, ...]
    word_pages: tuple[int, ...]
    origin: tuple[Origin, ...]
    changes: tuple[tuple[int, WordChange], ...]
    links: frozendict[int, tuple[Reference, int]] = frozendict()
    level: int | None = None
    label: str | None = None
    line_starts: frozenset[int] = frozenset()


@dataclass(frozen=True, slots=True)
class UnnumberedNote:
    """A note before it has its id."""

    kind: NoteKind
    marker: str
    blocks: tuple[Unnumbered, ...]
    origin: tuple[Origin, ...]
    referenced: bool


def piece_origin(piece: Piece) -> tuple[Origin, ...]:
    """One origin per page the piece has lines on, with the box of those
    lines."""
    return tuple(
        Origin(page_index, box_of(tuple(line.line.box for line in lines)))
        for page_index, lines in itertools.groupby(
            piece.lines, key=lambda line: line.page_index
        )
    )


def joined(
    piece: Piece,
    kind: BlockKind,
    book_words: frozenset[str],
    word_list: frozenset[str],
) -> Unnumbered:
    joined = join_lines(
        tuple(
            PageLine(line.page_index, tuple(word.text for word in line.line.words))
            for line in piece.lines
        ),
        book_words,
        word_list,
        piece.unjoined,
    )
    return Unnumbered(
        kind,
        joined.words,
        joined.pages,
        piece_origin(piece),
        tuple(zip(joined.positions, joined.changes, strict=True)),
        line_starts=frozenset(joined.line_starts),
    )


def without_marker(
    block: Unnumbered, marker: NoteMarker | None
) -> tuple[Unnumbered, str]:
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
            block,
            words=block.words[1:],
            word_pages=block.word_pages[1:],
            line_starts=frozenset(
                start - 1 for start in block.line_starts if start > 1
            ),
            changes=tuple((position - 1, change) for position, change in block.changes),
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


def changes_in_order(blocks: Sequence[Unnumbered]) -> tuple[WordChange, ...]:
    """The word changes of `blocks`, block by block, each block's in the
    order of its words."""
    return tuple(
        change
        for block in blocks
        for _, change in sorted(block.changes, key=lambda placed: placed[0])
    )


def merged_origin(blocks: Sequence[Unnumbered]) -> tuple[Origin, ...]:
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


def first_page(origin: tuple[Origin, ...]) -> int:
    return origin[0].page_index
