"""The scores of one stage output against the reference (spec section 6).

The text scores count the states of the tokens, for each part of the
book apart: the body, the notes, the index, tables and figure captions.
The structure scores, at blocks and markdown, say whether galley's
paragraph boundaries, block kinds, notes and margin notes are where the
reference has them.

How the spec is read here, where it leaves a choice:

- A reference token's part is that of its block: notes for a token of a
  note, index for an index entry, tables for a table, figures for a
  figure, body for any other block, headings, quotes and margin notes
  included. An extra token's part is the part of most of the placed
  reference tokens of its page, the first in the order body, notes,
  index, tables, figures on a tie, and the body on a page with none.
- A reference token that is unplaced, or on a page of `exclude_pages` or
  `not_in_reference`, is not scored: it is counted only in `unplaced`,
  for the first, and nowhere for the second. An extra galley token on
  such a page is not scored either.
- A pairing other than matched whose subkind is `reference_correction`
  counts its reference tokens there, and not under its state.
- `token_error_rate` divides by the scored reference tokens of the part.
- Paragraph boundaries are those between the body blocks other than
  margin notes, on both sides, and the margin notes are skipped: a margin
  note between two paragraphs makes no boundary. A galley boundary is
  mapped to the gap before the reference token aligned to the first
  aligned body token after it, so that a boundary inside a split word is
  never right; with no aligned token after it, to the gap after the last
  aligned one. A boundary's part is that of the reference
  token after its gap. Two galley boundaries mapped to the same gap count
  as one right one and one wrong one.
- The boundary between two consecutive reference headings is left out
  when one galley heading with a label holds both, more than half of the
  first's held tokens in its label and more than half of the second's
  outside it.
- For a block kind, note or margin note, a reference token's galley token
  is the first galley token of its pairing; only aligned tokens (matched,
  changed, split, glued) are counted. A reference block with no aligned
  token is paired with the galley kind `none`. The block that holds a
  reference block is the one that holds most of those tokens, the first
  seen on a tie.
- `kinds_right` counts, per part, the reference blocks held by a galley
  block of the same kind; a table is never right.
- The headings of the body range are those of the body stream. A galley
  heading is right when it holds a reference heading, in the range or
  not.
- A note's reference is right when any galley reference to the galley
  note that holds the note is within 3 tokens of any of Gutenberg's
  references to it.
- A margin note's position is right when, in galley's order of blocks at
  that output, the first block after the galley margin note that holds it
  and is not a margin note is the block that holds the first aligned
  token of the reference paragraph the margin note precedes. Other margin
  notes between them are skipped.
"""

import itertools
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import assert_never

from galley.model import BlockKind, NoteKind
from galley_eval.align import (
    Alignment,
    GalleyStream,
    GalleyToken,
    ReferencePlace,
    State,
    Subkind,
)
from galley_eval.galley_side import GalleyBlock, GalleyNoteReference
from galley_eval.reader import ReferenceKind, ReferenceText, Stream

__all__ = [
    "BoundaryScores",
    "GalleyKind",
    "HeadingScores",
    "KindCount",
    "MarginNoteScores",
    "NoteScores",
    "Part",
    "Placement",
    "TextScores",
    "block_kinds",
    "endnote_notes",
    "galley_parts",
    "heading_scores",
    "kinds_right",
    "margin_note_scores",
    "note_scores",
    "notes_found_as_notes",
    "page_parts",
    "paragraph_boundaries",
    "reference_part",
    "share",
    "text_scores",
]


class Part(StrEnum):
    """What a token belongs to, for the scores (spec section 6)."""

    BODY = "body"
    NOTES = "notes"
    INDEX = "index"
    TABLES = "tables"
    FIGURES = "figures"


class Placement(StrEnum):
    """Whether a reference token is scored: placed on a page that is
    scored, unplaced, or on a page that is not scored."""

    SCORED = "scored"
    UNPLACED = "unplaced"
    NOT_SCORED = "not_scored"


@dataclass(frozen=True, slots=True, kw_only=True)
class TextScores:
    """The text scores of one part at one output (spec section 6, "Text").
    `reference_tokens` counts the scored ones; with `unplaced` and
    `not_scored` they add up to the reference's tokens of the part.
    `galley_tokens` counts the galley tokens aligned to a reference token
    of the part and the extra ones on its pages, scored or not.
    `repaired` is None at words; `token_error_rate` is None when the part
    has no scored reference token."""

    reference_tokens: int
    matched: int
    changed_convention: int
    changed_case: int
    changed_punctuation: int
    changed_diacritic: int
    changed_letters: int
    split: int
    glued: int
    missing: int
    extra: int
    reference_correction: int
    unplaced: int
    not_scored: int
    galley_tokens: int
    edge_of_page_extra: int
    repaired: int | None
    token_error_rate: float | None


@dataclass(frozen=True, slots=True, kw_only=True)
class BoundaryScores:
    """Paragraph boundaries of one part: galley's, how many of them are
    right, the reference's, and how many of those galley has."""

    galley_boundaries: int
    right: int
    reference_boundaries: int
    found: int
    precision: float | None
    recall: float | None


class GalleyKind(StrEnum):
    """The kind of the galley block that holds a reference block: galley's
    block kinds, and `none` when no token of the reference block is
    aligned."""

    HEADING = "heading"
    PARAGRAPH = "paragraph"
    QUOTE = "quote"
    VERSE = "verse"
    CHAPTER_SUMMARY = "chapter_summary"
    FIGURE = "figure"
    MARGIN_NOTE = "margin_note"
    INDEX_ENTRY = "index_entry"
    NONE = "none"


@dataclass(frozen=True, slots=True)
class KindCount:
    """How many reference blocks of `reference` kind are held mostly by a
    galley block of `galley` kind."""

    reference: ReferenceKind
    galley: GalleyKind
    count: int


@dataclass(frozen=True, slots=True, kw_only=True)
class HeadingScores:
    """The headings of the body range (spec section 6, "Headings"): the
    reference's, those of them held by a galley heading, galley's, and
    those of galley's that hold a reference heading."""

    reference_headings: int
    in_heading_blocks: int
    galley_headings: int
    galley_headings_right: int


@dataclass(frozen=True, slots=True, kw_only=True)
class NoteScores:
    """The reference's notes found as a galley note, in the body, or not
    at all, and the notes found as a note whose reference is right."""

    as_note: int
    in_body: int
    missing: int
    reference_right: int


@dataclass(frozen=True, slots=True, kw_only=True)
class MarginNoteScores:
    """The reference's margin notes found as a galley margin note, in the
    body, or not at all, and those found in their place; `position_right`
    is None when Gutenberg moved the book's margin notes."""

    as_margin_note: int
    in_body: int
    missing: int
    position_right: int | None


_ALIGNED = frozenset((State.MATCHED, State.CHANGED, State.SPLIT, State.GLUED))

_KIND_PARTS = frozendict(
    {
        ReferenceKind.INDEX_ENTRY: Part.INDEX,
        ReferenceKind.TABLE: Part.TABLES,
        ReferenceKind.FIGURE: Part.FIGURES,
    }
)


def reference_part(place: ReferencePlace) -> Part:
    """The part of a reference token: notes in a note, else by its block's
    kind, the body for headings, paragraphs, quotes and margin notes."""
    if place.stream is Stream.NOTES:
        return Part.NOTES
    return _KIND_PARTS.get(place.kind, Part.BODY)


def page_parts(
    places: tuple[ReferencePlace, ...], page_indices: tuple[int | None, ...]
) -> frozendict[int, Part]:
    """The part of each page that holds placed reference tokens: the part
    of most of them, on a tie the first in Part's order, the body first."""
    counts: dict[int, Counter[Part]] = {}
    for place, page in zip(places, page_indices, strict=True):
        if page is not None:
            counts.setdefault(page, Counter())[reference_part(place)] += 1
    return frozendict(
        {
            page: max(Part, key=lambda part: counter[part])
            for page, counter in counts.items()
        }
    )


def galley_parts(
    galley: tuple[GalleyToken, ...], parts_of_pages: frozendict[int, Part]
) -> tuple[Part, ...]:
    """The part of each galley token: the part of its page, the body on a
    page with no placed reference token."""
    return tuple(parts_of_pages.get(token.page_index, Part.BODY) for token in galley)


# Text


def _pairing_of(alignment: Alignment, index: int) -> int:
    return alignment.reference_pairing[index]


def text_scores(
    alignment: Alignment,
    galley: tuple[GalleyToken, ...],
    *,
    parts: tuple[Part, ...],
    placements: tuple[Placement, ...],
    galley_part: tuple[Part, ...],
    galley_scored: tuple[bool, ...],
    repaired: tuple[bool, ...] | None,
) -> frozendict[Part, TextScores]:
    """The text scores of one output, for every part. `parts` and
    `placements` are those of each reference token; `galley_part` and
    `galley_scored` those of each galley token; `repaired` says, for each
    reference token, whether this output repaired it, None at words."""
    counts: dict[Part, Counter[str]] = {part: Counter() for part in Part}
    for index, pairing_index in enumerate(alignment.reference_pairing):
        counter = counts[parts[index]]
        match placements[index]:
            case Placement.UNPLACED:
                counter["unplaced"] += 1
                continue
            case Placement.NOT_SCORED:
                counter["not_scored"] += 1
                continue
            case Placement.SCORED:
                pass
            case _:
                assert_never(placements[index])
        pairing = alignment.pairings[pairing_index]
        counter["reference_tokens"] += 1
        counter[_counted_as(pairing.state, pairing.subkind)] += 1
        if repaired is not None and repaired[index]:
            counter["repaired"] += 1
    for index, token in enumerate(galley):
        pairing = alignment.pairings[alignment.galley_pairing[index]]
        if pairing.state is not State.EXTRA:
            counts[parts[pairing.reference_indices[0]]]["galley_tokens"] += 1
            continue  # counted with its reference token
        counter = counts[galley_part[index]]
        counter["galley_tokens"] += 1
        if galley_scored[index]:
            counter["extra"] += 1
            counter["edge_of_page_extra"] += token.edge_of_page
    return frozendict(
        {
            part: _text_scores(counter, with_repaired=repaired is not None)
            for part, counter in counts.items()
        }
    )


def _counted_as(state: State, subkind: Subkind | None) -> str:
    if subkind is Subkind.REFERENCE_CORRECTION:
        return "reference_correction"
    match state:
        case State.CHANGED:
            assert subkind is not None  # a changed pairing has its subkind
            return f"changed_{subkind.value}"
        case State.MATCHED | State.SPLIT | State.GLUED | State.MISSING | State.EXTRA:
            return state.value
        case _:
            assert_never(state)


def _text_scores(counter: Counter[str], *, with_repaired: bool) -> TextScores:
    errors = (
        counter["missing"]
        + counter["extra"]
        + counter["changed_case"]
        + counter["changed_punctuation"]
        + counter["changed_diacritic"]
        + counter["changed_letters"]
        + counter["split"]
        + counter["glued"]
    )
    reference_tokens = counter["reference_tokens"]
    return TextScores(
        reference_tokens=reference_tokens,
        matched=counter["matched"],
        changed_convention=counter["changed_convention"],
        changed_case=counter["changed_case"],
        changed_punctuation=counter["changed_punctuation"],
        changed_diacritic=counter["changed_diacritic"],
        changed_letters=counter["changed_letters"],
        split=counter["split"],
        glued=counter["glued"],
        missing=counter["missing"],
        extra=counter["extra"],
        reference_correction=counter["reference_correction"],
        unplaced=counter["unplaced"],
        not_scored=counter["not_scored"],
        galley_tokens=counter["galley_tokens"],
        edge_of_page_extra=counter["edge_of_page_extra"],
        repaired=counter["repaired"] if with_repaired else None,
        token_error_rate=errors / reference_tokens if reference_tokens else None,
    )


# Where a reference token's galley token is


def _first_galley(alignment: Alignment, index: int) -> int | None:
    """The first galley token of a reference token's pairing, None when it
    is not aligned."""
    pairing = alignment.pairings[_pairing_of(alignment, index)]
    if pairing.state not in _ALIGNED:
        return None
    return pairing.galley_indices[0]


def _is_paragraph_place(place: ReferencePlace) -> bool:
    return place.stream is Stream.BODY and place.kind is not ReferenceKind.MARGIN_NOTE


def _reference_gaps(
    alignment: Alignment,
    places: tuple[ReferencePlace, ...],
    galley: tuple[GalleyToken, ...],
) -> tuple[int | None, ...]:
    """For each galley position, and the position after the last token,
    the gap of the reference body it maps onto: before the reference token
    aligned to the first aligned body token at or after it; else after the reference token of the last
    aligned body token; None when no body token is aligned."""
    before: list[int | None] = [None] * len(galley)
    after: list[int | None] = [None] * len(galley)
    for index, token in enumerate(galley):
        if token.stream is not GalleyStream.BODY:
            continue  # only body tokens map onto the body's gaps
        pairing = alignment.pairings[alignment.galley_pairing[index]]
        if pairing.state not in _ALIGNED:
            continue  # an extra token has no place in the reference
        if not _is_paragraph_place(places[pairing.reference_indices[0]]):
            continue  # aligned to a note or margin note, not to the body
        before[index] = min(pairing.reference_indices)
        after[index] = max(pairing.reference_indices) + 1
    gaps: list[int | None] = [None] * (len(galley) + 1)
    following: int | None = None
    for index in range(len(galley) - 1, -1, -1):
        following = before[index] if before[index] is not None else following
        gaps[index] = following
    last: int | None = None
    for index in range(len(galley) + 1):
        if gaps[index] is None:
            gaps[index] = last
        if index < len(galley) and after[index] is not None:
            last = after[index]
    return tuple(gaps)


# Paragraph boundaries


_NO_BLOCKS = frozendict[str, GalleyBlock]()


def paragraph_boundaries(
    alignment: Alignment,
    places: tuple[ReferencePlace, ...],
    galley: tuple[GalleyToken, ...],
    parts: tuple[Part, ...],
    *,
    galley_blocks: frozendict[str, GalleyBlock] = _NO_BLOCKS,
) -> frozendict[Part, BoundaryScores]:
    """Paragraph boundary precision and recall, for every part, of one
    output: blocks or markdown, whose tokens have their block ids. With
    `galley_blocks`, the boundary between a chapter's label and title
    that one galley heading holds is not a reference boundary."""
    paragraph = tuple(
        index for index, place in enumerate(places) if _is_paragraph_place(place)
    )
    reference_boundaries = frozenset(
        current
        for previous, current in itertools.pairwise(paragraph)
        if places[previous].block_index != places[current].block_index
    ) - _label_and_title_gaps(alignment, places, galley, galley_blocks)
    gaps = _reference_gaps(alignment, places, galley)
    body = tuple(
        index for index, token in enumerate(galley) if token.stream is GalleyStream.BODY
    )
    galley_counts: Counter[Part] = Counter()
    right_counts: Counter[Part] = Counter()
    claimed: set[int] = set()
    for previous, current in itertools.pairwise(body):
        if galley[previous].block_id == galley[current].block_id:
            continue  # inside a block, not a boundary
        gap = gaps[current]
        part = parts[gap] if gap is not None and gap < len(places) else Part.BODY
        galley_counts[part] += 1
        if gap in reference_boundaries and gap not in claimed:
            right_counts[part] += 1
            claimed.add(gap)
    reference_counts = Counter(parts[gap] for gap in reference_boundaries)
    found_counts = Counter(parts[gap] for gap in claimed)
    return frozendict(
        {
            part: BoundaryScores(
                galley_boundaries=galley_counts[part],
                right=right_counts[part],
                reference_boundaries=reference_counts[part],
                found=found_counts[part],
                precision=share(right_counts[part], galley_counts[part]),
                recall=share(found_counts[part], reference_counts[part]),
            )
            for part in Part
            if part is not Part.NOTES
        }
    )


def _label_and_title_gaps(
    alignment: Alignment,
    places: tuple[ReferencePlace, ...],
    galley: tuple[GalleyToken, ...],
    galley_blocks: frozendict[str, GalleyBlock],
) -> frozenset[int]:
    """The gaps between two consecutive reference headings of the body
    that one galley heading with a label holds, the first mostly in its
    label and the second mostly outside it."""
    groups = tuple(
        indices
        for indices in _groups(places)
        if places[indices[0]].stream is Stream.BODY
        and places[indices[0]].kind is not ReferenceKind.MARGIN_NOTE
    )
    gaps: set[int] = set()
    for first, second in itertools.pairwise(groups):
        if not (
            places[first[0]].kind is ReferenceKind.HEADING
            and places[second[0]].kind is ReferenceKind.HEADING
        ):
            continue
        holder = _holder(alignment, first, galley)
        if (
            holder is None
            or holder != _holder(alignment, second, galley)
            or not galley_blocks[holder].has_label
        ):
            continue
        if _label_share(alignment, first, galley, holder) > _HALF and (
            _label_share(alignment, second, galley, holder) < _HALF
        ):
            gaps.add(second[0])
    return frozenset(gaps)


_HALF = 0.5


def _label_share(
    alignment: Alignment,
    indices: tuple[int, ...],
    galley: tuple[GalleyToken, ...],
    holder: str,
) -> float:
    """The share of a reference block's tokens held by `holder` that are
    in its label."""
    held = tuple(
        galley[galley_index]
        for index in indices
        if (galley_index := _first_galley(alignment, index)) is not None
        and galley[galley_index].block_id == holder
    )
    return sum(token.in_label for token in held) / len(held) if held else 0.0


def share(count: int, total: int) -> float | None:
    """`count` divided by `total`; None when `total` is 0."""
    return count / total if total else None


# Block kinds


def _groups(places: tuple[ReferencePlace, ...]) -> tuple[tuple[int, ...], ...]:
    """The token indices of each reference block, the body's then the
    notes', in order."""
    grouped: dict[tuple[int | None, int], list[int]] = {}
    for index, place in enumerate(places):
        grouped.setdefault((place.note_index, place.block_index), []).append(index)
    return tuple(tuple(indices) for indices in grouped.values())


def block_kinds(
    alignment: Alignment,
    places: tuple[ReferencePlace, ...],
    galley: tuple[GalleyToken, ...],
    galley_blocks: frozendict[str, GalleyBlock],
    parts: tuple[Part, ...],
) -> frozendict[Part, tuple[KindCount, ...]]:
    """For every part, how many reference blocks of each kind are held
    mostly by a galley block of each kind, in the order first seen."""
    counts: dict[Part, Counter[tuple[ReferenceKind, GalleyKind]]] = {
        part: Counter() for part in Part
    }
    for indices in _groups(places):
        holder = _holder(alignment, indices, galley)
        galley_kind = (
            GalleyKind(galley_blocks[holder].kind.value)
            if holder is not None
            else GalleyKind.NONE
        )
        place = places[indices[0]]
        counts[parts[indices[0]]][place.kind, galley_kind] += 1
    return frozendict(
        {
            part: tuple(
                KindCount(reference, galley_kind, count)
                for (reference, galley_kind), count in counter.items()
            )
            for part, counter in counts.items()
        }
    )


def _holder(
    alignment: Alignment, indices: tuple[int, ...], galley: tuple[GalleyToken, ...]
) -> str | None:
    """The id of the galley block that holds most of the aligned tokens of
    a reference block, None when none is aligned."""
    holders = Counter(
        block_id
        for index in indices
        if (galley_index := _first_galley(alignment, index)) is not None
        and (block_id := galley[galley_index].block_id) is not None
    )
    return holders.most_common(1)[0][0] if holders else None


def kinds_right(
    kinds: frozendict[Part, tuple[KindCount, ...]],
) -> frozendict[Part, int]:
    """For every part, the reference blocks held by a galley block of the
    same kind (spec section 6, "Block kinds"): a quote by a quote, verse by
    verse, a chapter summary by a chapter summary; a table never."""
    return frozendict(
        {
            part: sum(
                count.count
                for count in counts
                if count.reference.value == count.galley.value
            )
            for part, counts in kinds.items()
        }
    )


# Headings


def heading_scores(
    alignment: Alignment,
    places: tuple[ReferencePlace, ...],
    galley: tuple[GalleyToken, ...],
    galley_blocks: frozendict[str, GalleyBlock],
    *,
    page_indices: tuple[int | None, ...],
    body_pages: tuple[int, int],
) -> HeadingScores:
    """The headings of the body range, `body_pages`, first and last page
    index: the reference's headings whose first token's page, from
    `page_indices`, is in it, and galley's body headings whose first
    origin is; and which of each the other side holds."""
    first, last = body_pages
    reference = 0
    found = 0
    holders: set[str] = set()
    for indices in _groups(places):
        place = places[indices[0]]
        if place.stream is not Stream.BODY or place.kind is not ReferenceKind.HEADING:
            continue
        holder = _holder(alignment, indices, galley)
        is_heading = False
        if holder is not None and galley_blocks[holder].kind is BlockKind.HEADING:
            holders.add(holder)
            is_heading = True
        page = page_indices[indices[0]]
        if page is not None and first <= page <= last:
            reference += 1
            found += is_heading
    galley_headings = tuple(
        block_id
        for block_id, block in galley_blocks.items()
        if block.kind is BlockKind.HEADING
        and block.stream is GalleyStream.BODY
        and block.first_page is not None
        and first <= block.first_page <= last
    )
    return HeadingScores(
        reference_headings=reference,
        in_heading_blocks=found,
        galley_headings=len(galley_headings),
        galley_headings_right=sum(1 for block in galley_headings if block in holders),
    )


# Notes and margin notes


class _Found(StrEnum):
    AS_ITSELF = "as_itself"
    IN_BODY = "in_body"
    MISSING = "missing"


def _found_where(
    alignment: Alignment,
    indices: tuple[int, ...],
    galley: tuple[GalleyToken, ...],
    holder: Callable[[GalleyToken], str | None],
) -> tuple[_Found, str | None]:
    """Where most of a reference note's or margin note's aligned tokens
    are: in one galley holder, as `holder` names it (a note's id, a margin
    note's block id), or in the body, and that holder."""
    tokens = tuple(
        galley[galley_index]
        for index in indices
        if (galley_index := _first_galley(alignment, index)) is not None
    )
    if not tokens:
        return _Found.MISSING, None
    holders = Counter(
        name for token in tokens if (name := holder(token)) is not None
    ).most_common(1)
    half = len(tokens) / 2
    if holders and holders[0][1] >= half:
        return _Found.AS_ITSELF, holders[0][0]
    if sum(1 for token in tokens if token.stream is GalleyStream.BODY) >= half:
        return _Found.IN_BODY, None
    return _Found.MISSING, None


def note_scores(
    reference: ReferenceText,
    alignment: Alignment,
    places: tuple[ReferencePlace, ...],
    galley: tuple[GalleyToken, ...],
    galley_blocks: frozendict[str, GalleyBlock],
    galley_note_references: tuple[GalleyNoteReference, ...],
) -> NoteScores:
    """Each reference note found as a galley note, in the body or not at
    all, and whether galley's reference to a note found as a note is
    within 3 tokens of Gutenberg's."""

    def note_of(token: GalleyToken) -> str | None:
        if token.stream is not GalleyStream.NOTES or token.block_id is None:
            return None
        return galley_blocks[token.block_id].note_id

    by_note: dict[int, list[int]] = {}
    for index, place in enumerate(places):
        if place.note_index is not None:
            by_note.setdefault(place.note_index, []).append(index)
    gaps = _reference_gaps(alignment, places, galley)
    block_positions = _block_positions(galley)
    galley_gaps: dict[str, list[int]] = {}
    for note_reference in galley_note_references:
        positions = block_positions.get(note_reference.block_id, ())
        if not positions:
            continue  # a block with no token at this output has no place
        at = (
            positions[note_reference.tokens_before]
            if note_reference.tokens_before < len(positions)
            else positions[-1] + 1
        )
        gap = gaps[at]
        if gap is not None:
            galley_gaps.setdefault(note_reference.note_id, []).append(gap)
    gutenberg_gaps: dict[str, list[int]] = {}
    for note_reference in reference.note_references:
        if note_reference.gap.stream is Stream.BODY:
            gutenberg_gaps.setdefault(note_reference.note_id, []).append(
                note_reference.gap.token_index
            )
    found: Counter[_Found] = Counter()
    right = 0
    for note_index, note in enumerate(reference.notes):
        where, galley_note = _found_where(
            alignment, tuple(by_note.get(note_index, ())), galley, note_of
        )
        found[where] += 1
        if galley_note is not None and any(
            abs(galley_gap - gutenberg_gap) <= _NOTE_REFERENCE_TOKENS
            for galley_gap in galley_gaps.get(galley_note, ())
            for gutenberg_gap in gutenberg_gaps.get(note.note_id, ())
        ):
            right += 1
    return NoteScores(
        as_note=found[_Found.AS_ITSELF],
        in_body=found[_Found.IN_BODY],
        missing=found[_Found.MISSING],
        reference_right=right,
    )


def notes_found_as_notes(
    alignment: Alignment,
    places: tuple[ReferencePlace, ...],
    galley: tuple[GalleyToken, ...],
    galley_blocks: frozendict[str, GalleyBlock],
) -> frozendict[int, str]:
    """The indices of the reference's notes found `as_note` at the output
    of `alignment`, each with the id of the galley note that holds it."""

    def note_of(token: GalleyToken) -> str | None:
        if token.stream is not GalleyStream.NOTES or token.block_id is None:
            return None
        return galley_blocks[token.block_id].note_id

    by_note: dict[int, list[int]] = {}
    for index, place in enumerate(places):
        if place.note_index is not None:
            by_note.setdefault(place.note_index, []).append(index)
    found: dict[int, str] = {}
    for note_index, indices in by_note.items():
        where, holder = _found_where(alignment, tuple(indices), galley, note_of)
        if where is _Found.AS_ITSELF and holder is not None:
            found[note_index] = holder
    return frozendict(found)


def endnote_notes(
    alignment: Alignment,
    places: tuple[ReferencePlace, ...],
    galley: tuple[GalleyToken, ...],
    galley_blocks: frozendict[str, GalleyBlock],
) -> frozenset[int]:
    """The indices of the reference's notes found `as_note` in a galley
    endnote, at the output of `alignment`, blocks (spec section 5)."""
    endnote_ids = frozenset(
        block.note_id
        for block in galley_blocks.values()
        if block.note_kind is NoteKind.ENDNOTE
    )
    if not endnote_ids:
        return frozenset()
    return frozenset(
        note_index
        for note_index, holder in notes_found_as_notes(
            alignment, places, galley, galley_blocks
        ).items()
        if holder in endnote_ids
    )


# A guess, to be set again once structure finds notes (spec section 6).
_NOTE_REFERENCE_TOKENS = 3


def _block_positions(
    galley: tuple[GalleyToken, ...],
) -> frozendict[str, tuple[int, ...]]:
    positions: dict[str, list[int]] = {}
    for index, token in enumerate(galley):
        if token.block_id is not None:
            positions.setdefault(token.block_id, []).append(index)
    return frozendict({block: tuple(found) for block, found in positions.items()})


def margin_note_scores(
    alignment: Alignment,
    places: tuple[ReferencePlace, ...],
    galley: tuple[GalleyToken, ...],
) -> MarginNoteScores:
    """Each reference margin note of the body found as a galley margin
    note, in the body or not at all, and how many galley put just before
    the block that holds the paragraph it precedes in the reference. The
    caller leaves the position out for a book whose margin notes
    Gutenberg moved."""

    def margin_note_of(token: GalleyToken) -> str | None:
        if token.stream is not GalleyStream.MARGIN_NOTES:
            return None
        return token.block_id

    blocks: dict[int, list[int]] = {}
    for index, place in enumerate(places):
        if place.stream is Stream.BODY:
            blocks.setdefault(place.block_index, []).append(index)
    order = tuple(dict.fromkeys(token.block_id for token in galley))
    stream_of = {token.block_id: token.stream for token in galley}
    found: Counter[_Found] = Counter()
    right = 0
    block_indices = sorted(blocks)
    for position, block_index in enumerate(block_indices):
        indices = tuple(blocks[block_index])
        if places[indices[0]].kind is not ReferenceKind.MARGIN_NOTE:
            continue  # only margin notes are scored here
        where, galley_block = _found_where(alignment, indices, galley, margin_note_of)
        found[where] += 1
        if galley_block is None:
            continue  # no margin note to place
        paragraph = next(
            (
                blocks[later]
                for later in block_indices[position + 1 :]
                if places[blocks[later][0]].kind is not ReferenceKind.MARGIN_NOTE
            ),
            None,
        )
        target = _first_aligned_block(alignment, paragraph or [], galley)
        after = order.index(galley_block) + 1
        following = next(
            (
                block_id
                for block_id in order[after:]
                if stream_of[block_id] is not GalleyStream.MARGIN_NOTES
            ),
            None,
        )
        if target is not None and following == target:
            right += 1
    return MarginNoteScores(
        as_margin_note=found[_Found.AS_ITSELF],
        in_body=found[_Found.IN_BODY],
        missing=found[_Found.MISSING],
        position_right=right,
    )


def _first_aligned_block(
    alignment: Alignment, indices: list[int], galley: tuple[GalleyToken, ...]
) -> str | None:
    for index in indices:
        galley_index = _first_galley(alignment, index)
        if galley_index is not None:
            return galley[galley_index].block_id
    return None
