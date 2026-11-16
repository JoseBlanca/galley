"""Where a margin note stands (spec section 13): the regions of one printed
note joined (rule 1), the line of the page it is beside (rule 2), the
indented line beside it that starts a paragraph (rule 3), and its place,
before the paragraph that holds that line (rule 4), inside the note that
holds it (rule 5), or where section 6 puts side text (rule 6)."""

import itertools
from collections.abc import Sequence
from dataclasses import dataclass, replace

from galley.model import BlockKind
from galley.structure._lines import INDENT_MIN_PT, Piece, PlacedLine, hyphen_between
from galley.structure._paragraphs import BodyBlock, Entry, MarginNote

# Spec section 13, rule 2: a paragraph's first line whose top lies within
# 0.5 pitch of the margin note's top is the line beside, before any other
# (519 of Domesday's 613 margin notes have one, 379 of Gierke's 658).
_FIRST_LINE_PITCHES = 0.5
# Spec section 13, rule 1: a margin region whose top is at most 2.5 pitches
# below the region above it is part of the same printed note (268 of
# Gierke's regions not beside a paragraph's first line lie so, against 38
# that are beside one).
_SAME_NOTE_PITCHES = 2.5


@dataclass(frozen=True, slots=True)
class InParagraph:
    """A line of the body: the position of its paragraph among the body's
    entries and the line's number in the paragraph, from 0."""

    entry: int
    number: int


@dataclass(frozen=True, slots=True)
class InNote:
    """A line of a note: the note's position among the notes and its
    block's among the note's blocks."""

    note: int
    block: int


@dataclass(frozen=True, slots=True)
class BesideLine:
    """A line of a page that a margin note may stand beside: the line,
    whether it is the first line of its block, and the paragraph or note
    that holds it."""

    line: PlacedLine
    first: bool
    holder: InParagraph | InNote


def line_beside(
    top: float, lines: Sequence[BesideLine], pitch: float
) -> BesideLine | None:
    """The line beside a margin note whose first line's top is `top`, among
    the `lines` of its page (spec section 13, rule 2): a block's first line
    whose top is within 0.5 `pitch` of it, the nearest; otherwise the line
    whose top is nearest; the first in the order of `lines` on a tie. None
    when the page has no line. `top` and `pitch`, the body line pitch, are
    in points."""

    def distance(beside: BesideLine) -> float:
        return abs(beside.line.line.box.top - top)

    firsts = tuple(
        beside
        for beside in lines
        if beside.first and distance(beside) <= _FIRST_LINE_PITCHES * pitch
    )
    candidates = firsts or tuple(lines)
    return min(candidates, key=distance, default=None)


def beside_lines(
    entries: Sequence[Entry],
    in_notes: frozenset[int],
    note_block_lines: Sequence[Sequence[Sequence[PlacedLine]]],
) -> frozendict[int, tuple[BesideLine, ...]]:
    """The lines a margin note may stand beside, by page index: those of
    the body's paragraphs, except the paragraphs at the positions
    `in_notes` (the endnote section's), and those of every note's blocks,
    `note_block_lines` giving the lines of each block of each note."""
    body = (
        BesideLine(line, number == 0, InParagraph(position, number))
        for position, entry in enumerate(entries)
        if isinstance(entry, BodyBlock) and position not in in_notes
        for number, line in enumerate(entry.piece.lines)
    )
    notes = (
        BesideLine(line, number == 0, InNote(note_position, block_position))
        for note_position, blocks in enumerate(note_block_lines)
        for block_position, lines in enumerate(blocks)
        for number, line in enumerate(lines)
    )
    by_page: dict[int, list[BesideLine]] = {}
    for beside in (*body, *notes):
        by_page.setdefault(beside.line.page_index, []).append(beside)
    return frozendict({page: tuple(lines) for page, lines in by_page.items()})


def _top(piece: Piece) -> float:
    return piece.lines[0].line.box.top


def _bottom(piece: Piece) -> float:
    return max(line.line.box.bottom for line in piece.lines)


def _left(piece: Piece) -> float:
    return min(line.line.box.x0 for line in piece.lines)


def _right(piece: Piece) -> float:
    return max(line.line.box.x1 for line in piece.lines)


def _beside(
    piece: Piece, lines: frozendict[int, tuple[BesideLine, ...]], pitch: float
) -> BesideLine | None:
    """The line beside the margin note of `piece` (rule 2)."""
    return line_beside(_top(piece), lines.get(piece.lines[0].page_index, ()), pitch)


def _starts_beside(note: Piece, beside: BesideLine, before: PlacedLine) -> bool:
    """Spec section 13, rule 3: the line beside `note`, which is not its
    paragraph's first line and follows `before`, starts a paragraph: it is
    indented at least 5 pt, `before` does not end with a hyphen, and the
    note is printed outside the column, its middle left of the line's
    region's left edge or right of its right edge. A note cut into the
    column (Stubbs) indents the lines beside it by its own width."""
    line = beside.line
    middle = (_left(note) + _right(note)) / 2
    return (
        line.line.box.x0 - line.edges.left >= INDENT_MIN_PT
        and not hyphen_between(before, line)
        and not line.edges.left <= middle <= line.edges.right
    )


def split_beside_margin_notes(
    entries: Sequence[Entry],
    lines: frozendict[int, tuple[BesideLine, ...]],
    pitch: float,
) -> tuple[Entry, ...]:
    """The entries with each paragraph split at an indented line beside a
    margin note (spec section 13, rule 3). `lines` are the lines beside
    which a margin note may stand, by page index (`beside_lines`); `pitch`
    is the body line pitch, in points."""
    starts: dict[int, set[int]] = {}
    for entry in entries:
        if not isinstance(entry, MarginNote):
            continue
        beside = _beside(entry.piece, lines, pitch)
        if beside is None or not isinstance(beside.holder, InParagraph):
            continue
        holder = beside.holder
        held = entries[holder.entry]
        # Only a paragraph is split; a heading, summary or verse stays whole.
        if (
            holder.number == 0
            or not isinstance(held, BodyBlock)
            or held.kind is not BlockKind.PARAGRAPH
        ):
            continue
        paragraph = held.piece.lines
        if _starts_beside(entry.piece, beside, paragraph[holder.number - 1]):
            starts.setdefault(holder.entry, set()).add(holder.number)
    split: list[Entry] = []
    for position, entry in enumerate(entries):
        cuts = sorted(starts.get(position, ()))
        if not cuts:
            split.append(entry)
            continue
        bounds = (0, *cuts, len(entry.piece.lines))
        split.extend(
            replace(entry, piece=Piece(entry.piece.lines[start:end]))
            for start, end in itertools.pairwise(bounds)
        )
    return tuple(split)


def _side_overlaps(upper: Piece, lower: Piece) -> bool:
    """Whether two margin notes are on the same side: their spans across
    the page overlap."""
    return _left(upper) < _right(lower) and _left(lower) < _right(upper)


def joined_margin_notes(
    entries: Sequence[Entry],
    lines: frozendict[int, tuple[BesideLine, ...]],
    pitch: float,
) -> tuple[Entry, ...]:
    """The entries with the margin regions of one printed note joined (spec
    section 13, rule 1): a region whose top is at most 2.5 pitches below
    the nearest region above it on its page and side, and whose first line
    is not beside a block's first line (rule 2), is part of that region's
    note. A joined note takes the place of its first region, its lines
    from the top down. `lines` are as `split_beside_margin_notes` takes
    them; `pitch` is in points."""
    by_page: dict[int, list[int]] = {}
    for position, entry in enumerate(entries):
        if isinstance(entry, MarginNote):
            by_page.setdefault(entry.piece.lines[0].page_index, []).append(position)
    # Each joined note by the position of its first region: its regions.
    groups: dict[int, list[int]] = {}
    for positions in by_page.values():
        heads: list[int] = []
        for position in sorted(positions, key=lambda p: _top(entries[p].piece)):
            piece = entries[position].piece
            above = [
                head
                for head in heads
                if _side_overlaps(_group_piece(entries, groups[head]), piece)
                and _bottom(_group_piece(entries, groups[head])) <= _top(piece)
            ]
            nearest = max(
                above,
                key=lambda head: _bottom(_group_piece(entries, groups[head])),
                default=None,
            )
            beside = _beside(piece, lines, pitch)
            if (
                nearest is not None
                and _top(piece) - _bottom(_group_piece(entries, groups[nearest]))
                <= _SAME_NOTE_PITCHES * pitch
                and not (beside is not None and beside.first)
            ):
                groups[nearest].append(position)
            else:
                heads.append(position)
                groups[position] = [position]
    joined_into = {
        position: head for head, members in groups.items() for position in members
    }
    result: list[Entry] = []
    for position, entry in enumerate(entries):
        head = joined_into.get(position)
        if head is None:
            result.append(entry)
        elif head == position:
            result.append(MarginNote(_group_piece(entries, groups[head])))
    return tuple(result)


def _group_piece(entries: Sequence[Entry], positions: Sequence[int]) -> Piece:
    """The lines of the margin notes at `positions`, one after another."""
    return Piece(tuple(line for p in positions for line in entries[p].piece.lines))


@dataclass(frozen=True, slots=True)
class Stays:
    """A margin note with no line of the body or of a note on its page,
    which stays where section 6 puts side text (rule 6)."""


type Place = InParagraph | InNote | Stays


def margin_note_places(
    entries: Sequence[Entry],
    lines: frozendict[int, tuple[BesideLine, ...]],
    pitch: float,
) -> frozendict[int, Place]:
    """Where each margin note of the entries goes, by its position among
    them (spec section 13, rules 4 to 6): before the paragraph that holds
    the line beside it (`InParagraph`, whose `number` is that line's),
    inside the note that holds it (`InNote`), or where it is (`Stays`).
    `lines` are as `split_beside_margin_notes` takes them, with each note
    at its position among the notes; `pitch` is in points."""
    places: dict[int, Place] = {}
    for position, entry in enumerate(entries):
        if isinstance(entry, MarginNote):
            beside = _beside(entry.piece, lines, pitch)
            places[position] = Stays() if beside is None else beside.holder
    return frozendict(places)


def placing_order(
    entries: Sequence[Entry], positions: Sequence[int]
) -> tuple[int, ...]:
    """The margin notes at `positions` in the order they go before one
    paragraph or note block: by page, and on a page from the top down."""
    return tuple(
        sorted(
            positions,
            key=lambda p: (
                entries[p].piece.lines[0].page_index,
                _top(entries[p].piece),
            ),
        )
    )
