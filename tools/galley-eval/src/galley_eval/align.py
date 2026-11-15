"""Aligning one stage output of galley with the reference text, and the
state of every token on both sides (spec section 5, "Alignment" and
"Differences").

A stage output comes in as galley tokens: each word with its page index,
the stream it is in (the body, a margin note or a note), whether it sits
on the first or last line of its page, and its block's id where it has
one. The reference comes in as its places: every token of the reference
with its stream, block and note. The result says, for each token of
either side, which pairing it is in: matched, changed, split, glued,
missing or extra.

How the spec is read here, where it leaves a choice:

- The body pass aligns the reference's body without its margin notes,
  which wait for the margin notes pass, as the spec's second pass names
  them as a stream of their own.
- Pairs found in a replaced stretch, `changed` ones included, are aligned
  and are not offered to a later pass; only the tokens left over are.
- The last pass takes the reference's leftover tokens in the reference's
  order: the body, margin notes in place, then the notes.
- A `split` or `glued` joins only tokens whose key is not empty, so that
  a dash or a lone quote is never part of one.
- `reference_correction` is the subkind of any pairing other than
  matched whose reference tokens include a marked correction, missing,
  split and glued ones too, so that all of them are counted apart from
  the errors.
- The tests of `case` and `punctuation` compare the two texts after
  quotes, dashes and ligatures are written one way, so that "’Tis" and
  "'TIS" differ only in case.
"""

import bisect
import re
import unicodedata
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from difflib import SequenceMatcher
from enum import StrEnum
from typing import assert_never

from galley_eval.reader import ReferenceKind, ReferenceText, ReferenceToken, Stream

__all__ = [
    "Alignment",
    "AlignmentPass",
    "GalleyStream",
    "GalleyToken",
    "Operation",
    "Pairing",
    "ReferencePlace",
    "State",
    "Stretch",
    "Subkind",
    "align",
    "alignment_key",
    "anchored_pass",
    "changed_subkind",
    "equal_key_share",
    "extra_tokens",
    "reference_places",
    "reference_states",
]


class GalleyStream(StrEnum):
    """The stream a galley token is in. At words and lines every token is
    in the body."""

    BODY = "body"
    MARGIN_NOTE = "margin_note"
    NOTE = "note"


# Book order: within a page, the body first, then margin notes, then notes.
_BOOK_ORDER = {GalleyStream.BODY: 0, GalleyStream.MARGIN_NOTE: 1, GalleyStream.NOTE: 2}


@dataclass(frozen=True, slots=True, kw_only=True)
class GalleyToken:
    """A word of a stage output of galley, split on white space as the
    fidelity check splits words. `page_index` counts PDF pages from 0;
    `edge_of_page` is true for a word of words or lines on the first or
    last line of its page; `block_id` is the id of the block it is in, at
    blocks and markdown, and None at words and lines."""

    text: str
    page_index: int
    stream: GalleyStream
    edge_of_page: bool
    block_id: str | None


@dataclass(frozen=True, slots=True, kw_only=True)
class ReferencePlace:
    """A token of the reference and where it is. `stream` and the token's
    index in the tuple of reference_places give its gap: the body's tokens
    come first, so that a body token's index is its index in the body
    stream, and a note token's index minus the number of body tokens is
    its index in the notes stream. `block_index` is the index of its block
    in the reference's blocks, or in its note's blocks; `note_index` the
    index of its note in the reference's notes, None in the body."""

    token: ReferenceToken
    stream: Stream
    kind: ReferenceKind
    block_index: int
    note_index: int | None


class State(StrEnum):
    """What became of a token (spec section 5, "Differences")."""

    MATCHED = "matched"
    CHANGED = "changed"
    SPLIT = "split"
    GLUED = "glued"
    MISSING = "missing"
    EXTRA = "extra"


class Subkind(StrEnum):
    """How a changed pair differs, the first that applies in this order;
    `reference_correction` before all when the reference token is a
    correction Gutenberg marked."""

    CONVENTION = "convention"
    CASE = "case"
    PUNCTUATION = "punctuation"
    DIACRITIC = "diacritic"
    LETTERS = "letters"
    REFERENCE_CORRECTION = "reference_correction"


class AlignmentPass(StrEnum):
    """The pass that aligned a pairing: galley's body against the
    reference's body, galley's leftovers against the reference's notes,
    then against its margin notes, and the leftovers of both sides against
    each other."""

    BODY = "body"
    NOTES = "notes"
    MARGIN_NOTES = "margin_notes"
    REMAINDER = "remainder"


@dataclass(frozen=True, slots=True, kw_only=True)
class Pairing:
    """Reference tokens and galley tokens in one state, by their indices
    in the reference places and in the galley tokens. A missing pairing
    has no galley token, an extra one no reference token. `subkind` is
    given for a changed pairing, and for any other than matched that
    holds a marked correction; None otherwise. `found_in` is the pass that
    aligned it, None for missing and extra."""

    state: State
    subkind: Subkind | None
    reference: tuple[int, ...]
    galley: tuple[int, ...]
    found_in: AlignmentPass | None


@dataclass(frozen=True, slots=True, kw_only=True)
class Alignment:
    """A stage output aligned with the reference: every pairing, and for
    each reference token and each galley token, in their order, the index
    of the pairing it is in."""

    pairings: tuple[Pairing, ...]
    reference_pairing: tuple[int, ...]
    galley_pairing: tuple[int, ...]


class Operation(StrEnum):
    """What a stretch of an anchored pass is, as difflib names them."""

    EQUAL = "equal"
    REPLACE = "replace"
    DELETE = "delete"
    INSERT = "insert"


@dataclass(frozen=True, slots=True)
class Stretch:
    """A stretch of an anchored pass: reference positions from
    `reference_start` up to `reference_end`, not included, against galley
    positions from `galley_start` up to `galley_end`."""

    operation: Operation
    reference_start: int
    reference_end: int
    galley_start: int
    galley_end: int


# The alignment key

_SPELLED = str.maketrans({"æ": "ae", "œ": "oe", "ð": "d", "þ": "th"})


def alignment_key(text: str) -> str:
    """The form of a token the two texts are aligned on (spec section 1):
    decomposed with accents dropped, lower case, æ œ ð þ spelled ae oe d
    th, and only letters and digits kept. "Pamphlets," and "pamphlets"
    have the same key."""
    decomposed = unicodedata.normalize("NFKD", text)
    bare = "".join(char for char in decomposed if not unicodedata.combining(char))
    return "".join(char for char in bare.lower().translate(_SPELLED) if char.isalnum())


# The anchored pass


def anchored_pass(
    reference_keys: Sequence[str], galley_keys: Sequence[str]
) -> tuple[Stretch, ...]:
    """The stretches that align two sequences of alignment keys, in order,
    covering both. The anchors are the keys found exactly once on each
    side, the longest run of them in the same order on both sides; each
    anchor is an equal stretch of one, and the stretches between anchors
    are difflib's, with no automatic junk."""
    anchors = _anchors(reference_keys, galley_keys)
    stretches: list[Stretch] = []
    reference_from, galley_from = 0, 0
    ends = (*anchors, (len(reference_keys), len(galley_keys)))
    for position, (reference_at, galley_at) in enumerate(ends):
        stretches.extend(
            _between(
                reference_keys[reference_from:reference_at],
                galley_keys[galley_from:galley_at],
                reference_from,
                galley_from,
            )
        )
        if position < len(anchors):
            stretches.append(
                Stretch(
                    Operation.EQUAL,
                    reference_at,
                    reference_at + 1,
                    galley_at,
                    galley_at + 1,
                )
            )
        reference_from, galley_from = reference_at + 1, galley_at + 1
    return tuple(stretches)


def _anchors(
    reference_keys: Sequence[str], galley_keys: Sequence[str]
) -> tuple[tuple[int, int], ...]:
    """The positions of the unique keys shared by both sides that form the
    longest subsequence increasing on both sides."""
    reference_counts = Counter(reference_keys)
    galley_counts = Counter(galley_keys)
    galley_position = {
        key: position
        for position, key in enumerate(galley_keys)
        if galley_counts[key] == 1 and reference_counts[key] == 1
    }
    pairs = tuple(
        (position, galley_position[key])
        for position, key in enumerate(reference_keys)
        if key in galley_position
    )
    return _longest_increasing(pairs)


def _longest_increasing(
    pairs: tuple[tuple[int, int], ...],
) -> tuple[tuple[int, int], ...]:
    """The longest subsequence of `pairs`, which increase in their first
    member, whose second members increase too (patience sorting)."""
    tails: list[int] = []  # the second member at the end of each length's best run
    tail_index: list[int] = []
    previous: list[int] = []
    for index, (_, galley_at) in enumerate(pairs):
        length = bisect.bisect_left(tails, galley_at)
        if length == len(tails):
            tails.append(galley_at)
            tail_index.append(index)
        else:
            tails[length] = galley_at
            tail_index[length] = index
        previous.append(tail_index[length - 1] if length > 0 else -1)
    run: list[tuple[int, int]] = []
    index = tail_index[-1] if tail_index else -1
    while index >= 0:
        run.append(pairs[index])
        index = previous[index]
    return tuple(reversed(run))


def _between(
    reference_keys: Sequence[str],
    galley_keys: Sequence[str],
    reference_offset: int,
    galley_offset: int,
) -> tuple[Stretch, ...]:
    if not reference_keys and not galley_keys:
        return ()
    if not galley_keys:
        return (
            Stretch(
                Operation.DELETE,
                reference_offset,
                reference_offset + len(reference_keys),
                galley_offset,
                galley_offset,
            ),
        )
    if not reference_keys:
        return (
            Stretch(
                Operation.INSERT,
                reference_offset,
                reference_offset,
                galley_offset,
                galley_offset + len(galley_keys),
            ),
        )
    matcher = SequenceMatcher(None, reference_keys, galley_keys, autojunk=False)
    return tuple(
        Stretch(
            Operation(tag),
            reference_offset + reference_start,
            reference_offset + reference_end,
            galley_offset + galley_start,
            galley_offset + galley_end,
        )
        for tag, reference_start, reference_end, galley_start, galley_end in (
            matcher.get_opcodes()
        )
    )


# The subkinds

_CONVENTION = str.maketrans(
    {"’": "'", "‘": "'", "“": '"', "”": '"', "—": "--", "–": "--"}
    | {"ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl", "ﬃ": "ffi", "ﬄ": "ffl", "ﬅ": "st", "ﬆ": "st"}
)
_EN_DASH_BETWEEN_DIGITS = re.compile(r"(?<=\d)–(?=\d)")


def _conventional(text: str) -> str:
    """`text` with quotes, dashes and ligatures written one way: ’ ‘ as ',
    “ ” as ", – and — as -- but – between digits as -, ﬁ as fi."""
    return _EN_DASH_BETWEEN_DIGITS.sub("-", text).translate(_CONVENTION)


def changed_subkind(reference: ReferenceToken, galley_text: str) -> Subkind:
    """How a reference token and the galley text paired with it differ:
    `reference_correction` when the reference token is a marked
    correction, else the first of convention, case, punctuation, diacritic
    and letters that applies (spec section 5). The two are taken to
    differ."""
    if reference.marked_correction:
        return Subkind.REFERENCE_CORRECTION
    reference_text = _conventional(reference.text)
    galley_conventional = _conventional(galley_text)
    if reference_text == galley_conventional:
        return Subkind.CONVENTION
    if reference_text.lower() == galley_conventional.lower():
        return Subkind.CASE
    if _letters_and_digits(reference_text) == _letters_and_digits(galley_conventional):
        return Subkind.PUNCTUATION
    if alignment_key(reference.text) == alignment_key(galley_text):
        return Subkind.DIACRITIC
    return Subkind.LETTERS


def _letters_and_digits(text: str) -> str:
    return "".join(char for char in text if char.isalnum())


# The three passes


def reference_places(reference: ReferenceText) -> tuple[ReferencePlace, ...]:
    """Every token of `reference` with its place: the body blocks' tokens
    in order, margin notes in place, then the notes' tokens in order."""
    body = tuple(
        ReferencePlace(
            token=token,
            stream=Stream.BODY,
            kind=block.kind,
            block_index=block_index,
            note_index=None,
        )
        for block_index, block in enumerate(reference.blocks)
        for token in block.tokens
    )
    notes = tuple(
        ReferencePlace(
            token=token,
            stream=Stream.NOTES,
            kind=block.kind,
            block_index=block_index,
            note_index=note_index,
        )
        for note_index, note in enumerate(reference.notes)
        for block_index, block in enumerate(note.blocks)
        for token in block.tokens
    )
    return body + notes


def align(
    places: tuple[ReferencePlace, ...], galley: tuple[GalleyToken, ...]
) -> Alignment:
    """A stage output aligned with the reference by the three passes of
    spec section 5. The tokens of each galley stream must come in `galley`
    in the stream's order; the streams may be interleaved or one after
    another. Each galley token is in exactly one pairing, and so is each
    reference token."""
    reference_keys = tuple(alignment_key(place.token.text) for place in places)
    galley_keys = tuple(alignment_key(token.text) for token in galley)
    book_order = tuple(
        sorted(
            range(len(galley)),
            key=lambda index: (
                galley[index].page_index,
                _BOOK_ORDER[galley[index].stream],
            ),
        )
    )
    reference_aligned = [False] * len(places)
    galley_aligned = [False] * len(galley)
    pairings: list[Pairing] = []

    def run(
        found_in: AlignmentPass,
        reference_indices: tuple[int, ...],
        galley_indices: tuple[int, ...],
    ) -> None:
        found = _pass(
            found_in,
            places,
            galley,
            reference_keys,
            galley_keys,
            reference_indices,
            galley_indices,
        )
        for pairing in found:
            for index in pairing.reference:
                reference_aligned[index] = True
            for index in pairing.galley:
                galley_aligned[index] = True
        pairings.extend(found)

    def galley_left() -> tuple[int, ...]:
        return tuple(index for index in book_order if not galley_aligned[index])

    run(
        AlignmentPass.BODY,
        tuple(
            index
            for index, place in enumerate(places)
            if place.stream is Stream.BODY
            and place.kind is not ReferenceKind.MARGIN_NOTE
        ),
        tuple(
            index
            for index, token in enumerate(galley)
            if token.stream is GalleyStream.BODY
        ),
    )
    run(
        AlignmentPass.NOTES,
        tuple(
            index for index, place in enumerate(places) if place.stream is Stream.NOTES
        ),
        galley_left(),
    )
    run(
        AlignmentPass.MARGIN_NOTES,
        tuple(
            index
            for index, place in enumerate(places)
            if place.kind is ReferenceKind.MARGIN_NOTE
        ),
        galley_left(),
    )
    run(
        AlignmentPass.REMAINDER,
        tuple(index for index in range(len(places)) if not reference_aligned[index]),
        galley_left(),
    )
    pairings.extend(
        Pairing(
            state=State.MISSING,
            subkind=_correction_subkind(places, (index,)),
            reference=(index,),
            galley=(),
            found_in=None,
        )
        for index in range(len(places))
        if not reference_aligned[index]
    )
    pairings.extend(
        Pairing(
            state=State.EXTRA,
            subkind=None,
            reference=(),
            galley=(index,),
            found_in=None,
        )
        for index in range(len(galley))
        if not galley_aligned[index]
    )
    reference_pairing = [0] * len(places)
    galley_pairing = [0] * len(galley)
    for pairing_index, pairing in enumerate(pairings):
        for index in pairing.reference:
            reference_pairing[index] = pairing_index
        for index in pairing.galley:
            galley_pairing[index] = pairing_index
    return Alignment(
        pairings=tuple(pairings),
        reference_pairing=tuple(reference_pairing),
        galley_pairing=tuple(galley_pairing),
    )


def _pass(
    found_in: AlignmentPass,
    places: tuple[ReferencePlace, ...],
    galley: tuple[GalleyToken, ...],
    reference_keys: tuple[str, ...],
    galley_keys: tuple[str, ...],
    reference_indices: tuple[int, ...],
    galley_indices: tuple[int, ...],
) -> tuple[Pairing, ...]:
    """The pairings one anchored pass finds between the reference tokens
    and galley tokens at the given indices; tokens left out of every
    pairing are left for the next pass."""
    stretches = anchored_pass(
        tuple(reference_keys[index] for index in reference_indices),
        tuple(galley_keys[index] for index in galley_indices),
    )
    pairings: list[Pairing] = []
    for stretch in stretches:
        reference_stretch = reference_indices[
            stretch.reference_start : stretch.reference_end
        ]
        galley_stretch = galley_indices[stretch.galley_start : stretch.galley_end]
        match stretch.operation:
            case Operation.EQUAL:
                pairings.extend(
                    _pair(found_in, places, galley, reference_index, galley_index)
                    for reference_index, galley_index in zip(
                        reference_stretch, galley_stretch, strict=True
                    )
                )
            case Operation.REPLACE:
                pairings.extend(
                    _replaced(
                        found_in,
                        places,
                        galley,
                        reference_keys,
                        galley_keys,
                        reference_stretch,
                        galley_stretch,
                    )
                )
            case Operation.DELETE | Operation.INSERT:
                pass  # no partner in this pass; the next pass may find one
            case _:
                assert_never(stretch.operation)
    return tuple(pairings)


def _pair(
    found_in: AlignmentPass,
    places: tuple[ReferencePlace, ...],
    galley: tuple[GalleyToken, ...],
    reference_index: int,
    galley_index: int,
) -> Pairing:
    """One reference token aligned to one galley token: matched when the
    texts are equal, else changed."""
    reference_token = places[reference_index].token
    galley_text = galley[galley_index].text
    if reference_token.text == galley_text:
        return Pairing(
            state=State.MATCHED,
            subkind=None,
            reference=(reference_index,),
            galley=(galley_index,),
            found_in=found_in,
        )
    return Pairing(
        state=State.CHANGED,
        subkind=changed_subkind(reference_token, galley_text),
        reference=(reference_index,),
        galley=(galley_index,),
        found_in=found_in,
    )


# The most tokens a split or glued joins: a choice, no case of more was seen
# (spec section 5).
_MOST_JOINED = 4


@dataclass(frozen=True, slots=True)
class _Join:
    """A split or glued found in a replaced stretch, by positions in it."""

    state: State
    reference_start: int
    reference_end: int
    galley_start: int
    galley_end: int


def _replaced(
    found_in: AlignmentPass,
    places: tuple[ReferencePlace, ...],
    galley: tuple[GalleyToken, ...],
    reference_keys: tuple[str, ...],
    galley_keys: tuple[str, ...],
    reference_stretch: tuple[int, ...],
    galley_stretch: tuple[int, ...],
) -> tuple[Pairing, ...]:
    """The pairings of a replaced stretch: splits and glueds first, in
    order; the tokens between them paired in order as changed; the tokens
    left over unpaired."""
    joins = _joins(
        tuple(reference_keys[index] for index in reference_stretch),
        tuple(galley_keys[index] for index in galley_stretch),
    )
    pairings: list[Pairing] = []
    reference_from, galley_from = 0, 0
    for join in (*joins, None):
        reference_to = len(reference_stretch) if join is None else join.reference_start
        galley_to = len(galley_stretch) if join is None else join.galley_start
        pairings.extend(
            _pair(found_in, places, galley, reference_index, galley_index)
            for reference_index, galley_index in zip(
                reference_stretch[reference_from:reference_to],
                galley_stretch[galley_from:galley_to],
                strict=False,
            )
        )
        if join is None:
            break
        reference_joined = reference_stretch[join.reference_start : join.reference_end]
        pairings.append(
            Pairing(
                state=join.state,
                subkind=_correction_subkind(places, reference_joined),
                reference=reference_joined,
                galley=galley_stretch[join.galley_start : join.galley_end],
                found_in=found_in,
            )
        )
        reference_from, galley_from = join.reference_end, join.galley_end
    return tuple(pairings)


def _joins(
    reference_keys: tuple[str, ...], galley_keys: tuple[str, ...]
) -> tuple[_Join, ...]:
    """The splits and glueds of a replaced stretch, found in the order of
    the reference: for each reference token, the first galley position not
    yet passed where up to four galley tokens join into its key (a split),
    or where its key joined with the next ones, up to four, is one galley
    token's key (a glued); the nearer of the two when both are found."""
    split_at = _joined_positions(galley_keys)
    single_at: dict[str, list[int]] = {}
    for position, key in enumerate(galley_keys):
        if key:
            single_at.setdefault(key, []).append(position)
    joins: list[_Join] = []
    reference_at, galley_from = 0, 0
    while reference_at < len(reference_keys):
        join = _join_at(reference_keys, reference_at, galley_from, split_at, single_at)
        if join is None:
            reference_at += 1
            continue
        joins.append(join)
        reference_at, galley_from = join.reference_end, join.galley_end
    return tuple(joins)


def _joined_positions(keys: tuple[str, ...]) -> dict[str, list[tuple[int, int]]]:
    """For each key made by joining 2 to 4 consecutive non-empty keys, the
    (start, end) of each place where it is made, in order."""
    joined: dict[str, list[tuple[int, int]]] = {}
    for start in range(len(keys)):
        for end in range(start + 2, min(start + _MOST_JOINED, len(keys)) + 1):
            parts = keys[start:end]
            if all(parts):
                joined.setdefault("".join(parts), []).append((start, end))
    return joined


def _join_at(
    reference_keys: tuple[str, ...],
    reference_at: int,
    galley_from: int,
    split_at: dict[str, list[tuple[int, int]]],
    single_at: dict[str, list[int]],
) -> _Join | None:
    candidates: list[_Join] = []
    key = reference_keys[reference_at]
    if key:
        places = split_at.get(key, [])
        found = bisect.bisect_left(places, (galley_from, 0))
        if found < len(places):
            start, end = places[found]
            candidates.append(
                _Join(State.SPLIT, reference_at, reference_at + 1, start, end)
            )
    for end in range(
        reference_at + 2, min(reference_at + _MOST_JOINED, len(reference_keys)) + 1
    ):
        parts = reference_keys[reference_at:end]
        if not all(parts):
            break
        positions = single_at.get("".join(parts), [])
        found = bisect.bisect_left(positions, galley_from)
        if found < len(positions):
            start = positions[found]
            candidates.append(_Join(State.GLUED, reference_at, end, start, start + 1))
    if not candidates:
        return None
    return min(candidates, key=lambda join: join.galley_start)


def _correction_subkind(
    places: tuple[ReferencePlace, ...], reference_indices: tuple[int, ...]
) -> Subkind | None:
    if any(places[index].token.marked_correction for index in reference_indices):
        return Subkind.REFERENCE_CORRECTION
    return None


# Reading an alignment


def reference_states(alignment: Alignment) -> tuple[State, ...]:
    """The state of each reference token, in the reference's order."""
    return tuple(
        alignment.pairings[pairing].state for pairing in alignment.reference_pairing
    )


def extra_tokens(
    alignment: Alignment, galley: tuple[GalleyToken, ...]
) -> tuple[GalleyToken, ...]:
    """The galley tokens with no reference token, in `galley`'s order."""
    return tuple(
        token
        for token, pairing in zip(galley, alignment.galley_pairing, strict=True)
        if alignment.pairings[pairing].state is State.EXTRA
    )


def equal_key_share(
    alignment: Alignment,
    places: tuple[ReferencePlace, ...],
    galley: tuple[GalleyToken, ...],
) -> float:
    """The share of the reference's tokens aligned to a galley token with
    the same alignment key, from 0 to 1; 0 when the reference has no
    token. Spec section 5 stops a book whose words output gives under 0.5."""
    if not places:
        return 0.0
    equal = sum(
        1
        for pairing in alignment.pairings
        if pairing.state in {State.MATCHED, State.CHANGED}
        and alignment_key(places[pairing.reference[0]].token.text)
        == alignment_key(galley[pairing.galley[0]].text)
    )
    return equal / len(places)
