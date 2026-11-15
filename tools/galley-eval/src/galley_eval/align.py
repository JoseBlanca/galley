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

- The margin notes pass takes the margin notes of the body only. A block
  of kind margin_note inside a note is part of its note and is aligned
  by the notes pass.
- Pairs found in a replaced stretch, `changed` ones included, are aligned
  and are not offered to a later pass; the tokens left unpaired are.
- In passes 2 and 3, a token whose rule for its provisional page finds
  nothing (a margin note before a paragraph with no aligned token, a
  token before every aligned one) takes the page of the nearest aligned
  body token before it, else after it; the tokens of each provisional
  page are aligned in the reference's order, the pages in increasing
  order, so that galley tokens a page took are not offered to the next.
- In passes 2 and 3, every provisional page is aligned with the galley
  tokens of its own page before any is offered the pages either side, so
  that a page does not take a token its neighbour would have paired on
  the neighbour's own page; the pages either side are offered the
  tokens left after that, without the provisional page's own leftovers,
  which the first round has already compared.
- In a replaced stretch, when neither a join nor a changed pair is found
  and one of the two current tokens has an empty key, that one is left
  unpaired, whatever its position: such a token can join nothing and
  pair only with another empty key, while the token across may still
  join or pair. On Haskins' note 40, galley's "*" before
  "GiraldusCambrensis" otherwise left "Giraldus" missing and paired
  "Cambrensis" with the glued word as changed.
- `reference_correction` is the subkind of any pairing other than
  matched whose reference tokens include a marked correction, missing,
  split and glued ones too, so that all of them are counted apart from
  the errors.
- The tests of `case` and `punctuation` compare the two texts after
  quotes, dashes and ligatures are written one way, so that "’Tis" and
  "'TIS" differ only in case.
- For `diacritic`, the letters æ œ ð þ count as accents, as the
  alignment key spells them out: "Æthelred" and "AEthelred" differ by a
  diacritic. Equal keys with no accent differing, such as the long s
  "ſerfs" and "serfs", are `letters`.
- In a replaced stretch, when neither current token can be paired, the
  one further behind is the one whose middle, (position + 1/2) divided
  by its side's length, is lower; on a tie, the one of the side with more
  tokens left, the reference's when both have as many.
"""

import bisect
import re
import unicodedata
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from difflib import SequenceMatcher
from enum import StrEnum
from typing import assert_never

from galley_eval.errors import AlignmentInvariantError
from galley_eval.reader import ReferenceKind, ReferenceText, ReferenceToken, Stream

__all__ = [
    "Alignment",
    "AlignmentPass",
    "GalleyStream",
    "GalleyToken",
    "Operation",
    "Pairing",
    "ReferencePlace",
    "ReferenceSide",
    "State",
    "Stretch",
    "Subkind",
    "align",
    "alignment_key",
    "anchor_pairs",
    "anchored_pass",
    "changed_subkind",
    "equal_key_share",
    "extra_tokens",
    "reference_places",
    "reference_side",
    "reference_states",
]


class GalleyStream(StrEnum):
    """The stream a galley token is in. At words and lines every token is
    in the body."""

    BODY = "body"
    MARGIN_NOTES = "margin_notes"
    NOTES = "notes"


# Book order: within a page, the body first, then margin notes, then notes.
_BOOK_ORDER = frozendict(
    {GalleyStream.BODY: 0, GalleyStream.MARGIN_NOTES: 1, GalleyStream.NOTES: 2}
)


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
    reference_indices: tuple[int, ...]
    galley_indices: tuple[int, ...]
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
    side, other than empty keys, the longest run of them in the same order
    on both sides; each anchor is an equal stretch of one, and the stretches between anchors
    are difflib's, with no automatic junk."""
    anchors = anchor_pairs(reference_keys, galley_keys)
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


def anchor_pairs(
    reference_keys: Sequence[str], galley_keys: Sequence[str]
) -> tuple[tuple[int, int], ...]:
    """The anchors of an anchored pass, as (reference position, galley
    position) pairs in order: the tokens whose key is not empty and is
    found exactly once on each side, the longest run of them in the same
    order on both sides."""
    reference_counts = Counter(reference_keys)
    galley_counts = Counter(galley_keys)
    galley_position = {
        key: position
        for position, key in enumerate(galley_keys)
        if key and galley_counts[key] == 1 and reference_counts[key] == 1
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
    if (
        _letters_and_digits(reference_text).lower()
        == _letters_and_digits(galley_conventional).lower()
    ):
        return Subkind.PUNCTUATION
    if alignment_key(reference.text) == alignment_key(galley_text) and _accents(
        reference.text
    ) != _accents(galley_text):
        return Subkind.DIACRITIC
    return Subkind.LETTERS


def _letters_and_digits(text: str) -> str:
    return "".join(char for char in text if char.isalnum())


_ACCENTED_LETTERS = frozenset("æœðþ")


def _accents(text: str) -> tuple[str, ...]:
    """The accents of `text` in order, once decomposed, and the letters æ œ
    ð þ, which the alignment key spells out as it drops accents."""
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return tuple(
        char
        for char in decomposed
        if unicodedata.combining(char) or char in _ACCENTED_LETTERS
    )


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


@dataclass(frozen=True, slots=True, kw_only=True)
class ReferenceSide:
    """The reference's places and their alignment keys, computed once per
    book and given to align for each of its stage outputs."""

    places: tuple[ReferencePlace, ...]
    keys: tuple[str, ...]


def reference_side(reference: ReferenceText) -> ReferenceSide:
    """The places of `reference` and the alignment key of each."""
    places = reference_places(reference)
    return ReferenceSide(
        places=places, keys=tuple(alignment_key(place.token.text) for place in places)
    )


def align(
    reference: ReferenceText,
    galley: tuple[GalleyToken, ...],
    prepared: ReferenceSide | None = None,
) -> Alignment:
    """A stage output aligned with `reference` by the three passes of spec
    section 5. The tokens of each galley stream must come in `galley` in
    the stream's order; the streams may be interleaved or one after
    another. The reference's tokens are counted as reference_places gives
    them; `prepared`, the reference_side of `reference`, saves computing
    it again for each output. Each galley token is in exactly one pairing,
    and so is each reference token; AlignmentInvariantError says which one
    is not, should the passes ever break that."""
    side = prepared if prepared is not None else reference_side(reference)
    places = side.places
    sides = _Sides(
        places=places,
        galley=galley,
        reference_keys=side.keys,
        galley_keys=tuple(alignment_key(token.text) for token in galley),
    )
    book_order = tuple(
        sorted(
            range(len(galley)),
            key=lambda index: (
                galley[index].page_index,
                _BOOK_ORDER[galley[index].stream],
            ),
        )
    )
    body = _pass(
        AlignmentPass.BODY,
        sides,
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
    notes = _near_page_pass(
        AlignmentPass.NOTES,
        sides,
        reference,
        body,
        tuple(
            index for index, place in enumerate(places) if place.stream is Stream.NOTES
        ),
        _left(book_order, body, _galley_side),
    )
    margin_notes = _near_page_pass(
        AlignmentPass.MARGIN_NOTES,
        sides,
        reference,
        body + notes,
        tuple(
            index
            for index, place in enumerate(places)
            if place.stream is Stream.BODY and place.kind is ReferenceKind.MARGIN_NOTE
        ),
        _left(book_order, body + notes, _galley_side),
    )
    found = body + notes + margin_notes
    remainder = _near_page_pass(
        AlignmentPass.REMAINDER,
        sides,
        reference,
        found,
        _left(tuple(range(len(places))), found, _reference_side),
        _left(book_order, found, _galley_side),
    )
    found += remainder
    missing = tuple(
        Pairing(
            state=State.MISSING,
            subkind=_correction_subkind(places, (index,)),
            reference_indices=(index,),
            galley_indices=(),
            found_in=None,
        )
        for index in _left(tuple(range(len(places))), found, _reference_side)
    )
    extra = tuple(
        Pairing(
            state=State.EXTRA,
            subkind=None,
            reference_indices=(),
            galley_indices=(index,),
            found_in=None,
        )
        for index in _left(tuple(range(len(galley))), found, _galley_side)
    )
    pairings = found + missing + extra
    return Alignment(
        pairings=pairings,
        reference_pairing=_pairing_of_each(
            pairings, len(places), _reference_side, "reference"
        ),
        galley_pairing=_pairing_of_each(pairings, len(galley), _galley_side, "galley"),
    )


@dataclass(frozen=True, slots=True, kw_only=True)
class _Sides:
    """The two sides being aligned and their alignment keys."""

    places: tuple[ReferencePlace, ...]
    galley: tuple[GalleyToken, ...]
    reference_keys: tuple[str, ...]
    galley_keys: tuple[str, ...]


def _reference_side(pairing: Pairing) -> tuple[int, ...]:
    return pairing.reference_indices


def _galley_side(pairing: Pairing) -> tuple[int, ...]:
    return pairing.galley_indices


def _left(
    indices: tuple[int, ...],
    pairings: tuple[Pairing, ...],
    side: Callable[[Pairing], tuple[int, ...]],
) -> tuple[int, ...]:
    """The indices, in their order, that no pairing holds on its `side`."""
    taken = frozenset(index for pairing in pairings for index in side(pairing))
    return tuple(index for index in indices if index not in taken)


def _pairing_of_each(
    pairings: tuple[Pairing, ...],
    count: int,
    side: Callable[[Pairing], tuple[int, ...]],
    side_name: str,
) -> tuple[int, ...]:
    """For each of the `count` tokens of a side, the index of the one
    pairing that holds it. Raises AlignmentInvariantError when a token is in no
    pairing or in two."""
    found: dict[int, int] = {}
    for pairing_index, pairing in enumerate(pairings):
        for index in side(pairing):
            if index in found:
                message = (
                    f"{side_name} token {index} is in pairings {found[index]} "
                    f"and {pairing_index}"
                )
                raise AlignmentInvariantError(message)
            found[index] = pairing_index
    lost = tuple(index for index in range(count) if index not in found)
    if lost or len(found) != count:
        message = f"{side_name} tokens in no pairing: {lost[:10]}"
        raise AlignmentInvariantError(message)
    return tuple(found[index] for index in range(count))


def _near_page_pass(
    found_in: AlignmentPass,
    sides: _Sides,
    reference: ReferenceText,
    found: tuple[Pairing, ...],
    reference_indices: tuple[int, ...],
    galley_indices: tuple[int, ...],
) -> tuple[Pairing, ...]:
    """The pairings of a pass that works near the page (passes 2 and 3):
    the reference tokens are taken page by page of their provisional page,
    from the pairings `found` before. First each page's are aligned by an
    anchored pass with the galley tokens still unpaired on that page; then
    the reference tokens every page left unpaired, with the galley tokens
    still unpaired on the page before and the page after, in book order (`galley_indices` is in book order). A reference token with
    no provisional page is left unpaired."""
    provisional = _provisional_pages(sides, reference, found)
    by_page: dict[int, list[int]] = {}
    for index in reference_indices:
        page = provisional[index]
        if page is not None:
            by_page.setdefault(page, []).append(index)
    galley_by_page: dict[int, list[int]] = {}
    for index in galley_indices:
        galley_by_page.setdefault(sides.galley[index].page_index, []).append(index)
    taken: set[int] = set()
    pairings: list[Pairing] = []
    for offsets in ((0,), _EITHER_SIDE):
        paired = frozenset(
            index for pairing in pairings for index in pairing.reference_indices
        )
        for page in sorted(by_page):
            candidates = tuple(
                index
                for offset in offsets
                for index in galley_by_page.get(page + offset, ())
                if index not in taken
            )
            page_pairings = _pass(
                found_in,
                sides,
                tuple(index for index in by_page[page] if index not in paired),
                candidates,
            )
            taken.update(
                index for pairing in page_pairings for index in pairing.galley_indices
            )
            pairings.extend(page_pairings)
    return tuple(pairings)


# Passes 2 and 3 pair a reference token only with galley tokens within one
# page of its provisional page (spec section 5): these are the offsets of
# the pages either side, offered after the provisional page itself.
_EITHER_SIDE = (-1, 1)


def _provisional_pages(
    sides: _Sides, reference: ReferenceText, found: tuple[Pairing, ...]
) -> tuple[int | None, ...]:
    """The provisional page of each reference token from the pairings
    `found` so far (spec section 5): a note token's, the page of its note
    reference, that is of the body token before it; a margin note token's,
    the page of the first aligned token of the paragraph it precedes; any
    other body token's, the page of the nearest aligned token before it.
    Where these find nothing, the page of the nearest aligned body token
    before, else after; None when there is none, or for a note with no
    reference."""
    places = sides.places
    aligned: list[int | None] = [None] * len(places)
    for pairing in found:
        page = sides.galley[pairing.galley_indices[0]].page_index
        for index in pairing.reference_indices:
            aligned[index] = page
    body_count = sum(1 for place in places if place.stream is Stream.BODY)
    before = _running(tuple(aligned[:body_count]))
    after = tuple(reversed(_running(tuple(reversed(aligned[:body_count])))))
    nearest = tuple(
        found_before if found_before is not None else after[index]
        for index, found_before in enumerate(before)
    )
    first_of_block: dict[int, int] = {}
    for index in range(body_count):
        page = aligned[index]
        if page is not None:
            first_of_block.setdefault(places[index].block_index, page)
    following = _following_paragraphs(reference)

    def body_page(index: int) -> int | None:
        place = places[index]
        if place.kind is ReferenceKind.MARGIN_NOTE:
            paragraph = following[place.block_index]
            if paragraph is not None and paragraph in first_of_block:
                return first_of_block[paragraph]
        return nearest[index]

    body_pages = tuple(body_page(index) for index in range(body_count))
    reference_before: dict[str, int] = {}
    for note_reference in reference.note_references:
        if note_reference.gap.stream is Stream.BODY and body_count > 0:
            reference_before.setdefault(
                note_reference.note_id,
                min(max(note_reference.gap.token_index - 1, 0), body_count - 1),
            )

    def note_page(place: ReferencePlace) -> int | None:
        before_reference = reference_before.get(
            reference.notes[_note_index(place)].note_id
        )
        return None if before_reference is None else body_pages[before_reference]

    return body_pages + tuple(note_page(place) for place in places[body_count:])


def _note_index(place: ReferencePlace) -> int:
    if place.note_index is None:
        message = "a token of the notes stream has no note"
        raise AlignmentInvariantError(message)
    return place.note_index


def _running(pages: tuple[int | None, ...]) -> tuple[int | None, ...]:
    """For each position, the last page given at or before it."""
    found: list[int | None] = []
    last: int | None = None
    for page in pages:
        last = page if page is not None else last
        found.append(last)
    return tuple(found)


def _following_paragraphs(reference: ReferenceText) -> tuple[int | None, ...]:
    """For each body block, the index of the first block after it that is
    not a margin note, None when there is none."""
    following: list[int | None] = []
    next_block: int | None = None
    for block_index in range(len(reference.blocks) - 1, -1, -1):
        following.append(next_block)
        if reference.blocks[block_index].kind is not ReferenceKind.MARGIN_NOTE:
            next_block = block_index
    return tuple(reversed(following))


def _pass(
    found_in: AlignmentPass,
    sides: _Sides,
    reference_indices: tuple[int, ...],
    galley_indices: tuple[int, ...],
) -> tuple[Pairing, ...]:
    """The pairings one anchored pass finds between the reference tokens
    and galley tokens at the given indices; tokens left out of every
    pairing are left for the next pass."""
    stretches = anchored_pass(
        tuple(sides.reference_keys[index] for index in reference_indices),
        tuple(sides.galley_keys[index] for index in galley_indices),
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
                    _pair(found_in, sides, reference_index, galley_index)
                    for reference_index, galley_index in zip(
                        reference_stretch, galley_stretch, strict=True
                    )
                )
            case Operation.REPLACE:
                pairings.extend(
                    _replaced(found_in, sides, reference_stretch, galley_stretch)
                )
            case Operation.DELETE | Operation.INSERT:
                pass  # no partner in this pass; the next pass may find one
            case _:
                assert_never(stretch.operation)
    return tuple(pairings)


def _pair(
    found_in: AlignmentPass, sides: _Sides, reference_index: int, galley_index: int
) -> Pairing:
    """One reference token aligned to one galley token: matched when the
    texts are equal, else changed."""
    reference_token = sides.places[reference_index].token
    galley_text = sides.galley[galley_index].text
    same = reference_token.text == galley_text
    return Pairing(
        state=State.MATCHED if same else State.CHANGED,
        subkind=None if same else changed_subkind(reference_token, galley_text),
        reference_indices=(reference_index,),
        galley_indices=(galley_index,),
        found_in=found_in,
    )


# The most tokens a split or glued joins (spec section 5): the text layer
# glued ten words into one on Haskins page index 28; 12 leaves room.
_MOST_JOINED = 12

# Two tokens are alike, and may be paired as changed, when difflib's ratio
# of their keys' characters is at least this: a guess, to be checked on the
# baseline (spec section 5).
_ALIKE = 0.5


def _replaced(
    found_in: AlignmentPass,
    sides: _Sides,
    reference_stretch: tuple[int, ...],
    galley_stretch: tuple[int, ...],
) -> tuple[Pairing, ...]:
    """The pairings of a replaced stretch, walked in order on both sides at
    once. At each step: a split or glued at the current positions; else a
    changed pair when the two current tokens are alike; else, when one of
    the two has an empty key, that one is left unpaired; else the token
    further behind on its side, as _reference_behind measures it, is left
    unpaired. The tokens left unpaired are offered to the next pass."""
    reference_keys = tuple(sides.reference_keys[index] for index in reference_stretch)
    galley_keys = tuple(sides.galley_keys[index] for index in galley_stretch)
    reference_count, galley_count = len(reference_stretch), len(galley_stretch)
    pairings: list[Pairing] = []
    reference_at, galley_at = 0, 0
    while reference_at < reference_count and galley_at < galley_count:
        join = _join_at(reference_keys, reference_at, galley_keys, galley_at)
        if join is not None:
            state, reference_end, galley_end = join
            reference_joined = reference_stretch[reference_at:reference_end]
            pairings.append(
                Pairing(
                    state=state,
                    subkind=_correction_subkind(sides.places, reference_joined),
                    reference_indices=reference_joined,
                    galley_indices=galley_stretch[galley_at:galley_end],
                    found_in=found_in,
                )
            )
            reference_at, galley_at = reference_end, galley_end
        elif _alike(reference_keys[reference_at], galley_keys[galley_at]):
            pairings.append(
                _pair(
                    found_in,
                    sides,
                    reference_stretch[reference_at],
                    galley_stretch[galley_at],
                )
            )
            reference_at, galley_at = reference_at + 1, galley_at + 1
        elif not reference_keys[reference_at] and galley_keys[galley_at]:
            reference_at += 1
        elif not galley_keys[galley_at] and reference_keys[reference_at]:
            galley_at += 1
        elif _reference_behind(reference_at, reference_count, galley_at, galley_count):
            reference_at += 1
        else:
            galley_at += 1
    return tuple(pairings)


def _reference_behind(
    reference_at: int, reference_count: int, galley_at: int, galley_count: int
) -> bool:
    """Whether the current reference token is further behind in its
    stretch than the current galley token: its middle, (position + 1/2)
    over the side's length, is lower; on a tie, whether the reference has
    at least as many tokens left."""
    reference_middle = (2 * reference_at + 1) * galley_count
    galley_middle = (2 * galley_at + 1) * reference_count
    if reference_middle != galley_middle:
        return reference_middle < galley_middle
    return reference_count - reference_at >= galley_count - galley_at


def _join_at(
    reference_keys: tuple[str, ...],
    reference_at: int,
    galley_keys: tuple[str, ...],
    galley_at: int,
) -> tuple[State, int, int] | None:
    """A split or glued starting at the current positions, with its state
    and the ends it reaches on each side; None when there is neither."""
    split_end = _joined_end(galley_keys, galley_at, reference_keys[reference_at])
    if split_end is not None:
        return State.SPLIT, reference_at + 1, split_end
    glued_end = _joined_end(reference_keys, reference_at, galley_keys[galley_at])
    if glued_end is not None:
        return State.GLUED, glued_end, galley_at + 1
    return None


def _joined_end(keys: tuple[str, ...], start: int, whole: str) -> int | None:
    """The end of the run of 2 to _MOST_JOINED tokens of `keys` from
    `start` whose joined keys equal `whole`, joining tokens with a
    non-empty key while what they join is a beginning of `whole`; None
    when there is no such run."""
    if not whole:
        return None
    joined = ""
    for end in range(start, min(start + _MOST_JOINED, len(keys))):
        if not keys[end]:
            return None
        joined += keys[end]
        if not whole.startswith(joined):
            return None
        if joined == whole:
            return end + 1 if end > start else None
    return None


def _alike(reference_key: str, galley_key: str) -> bool:
    """Whether two tokens may be paired as changed: both keys empty, or
    both non-empty with a character similarity of at least 0.5."""
    if not reference_key or not galley_key:
        return reference_key == galley_key
    matcher = SequenceMatcher(None, reference_key, galley_key, autojunk=False)
    return matcher.ratio() >= _ALIKE


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
        and alignment_key(places[pairing.reference_indices[0]].token.text)
        == alignment_key(galley[pairing.galley_indices[0]].text)
    )
    return equal / len(places)
