"""The page of every reference token, from the alignment of galley's words
with the reference (spec section 5, "Pages").

A reference token aligned to a galley token takes that token's page. An
unaligned one takes the page of the tokens of its note or margin note
that are aligned, or of the page anchor before it, whose page is its
printed page number plus an offset measured on the aligned tokens after
it. A token whose page cannot be known is unplaced.

How the spec is read here, where it leaves a choice:

- An anchor with no aligned token before the next anchor has no offset
  of its own; it borrows the offset of the nearest anchor before it that
  has one, else of the nearest after. It is never an anchor mismatch.
- An anchor mismatch has two neighbours: the first and last anchors are
  never mismatches. The neighbours' offsets are their own or borrowed.
- An anchor whose printed page is neither an arabic nor a roman number
  has no page and is passed over, as if it were not there.
- An unaligned token of a margin note with no aligned token, like any
  unaligned body token, takes the page of the anchor before it.
- An unaligned body token after an aligned token but before the first
  anchor takes the page of the nearest aligned token before it, as in a
  book without anchors.
- A note with no aligned token takes the page of the body token just
  before its first reference; with no reference, it is unplaced.
- An excluded page lies between two anchors when it is greater than the
  first anchor's page and less than the second's.
- An offset is the lower median, so that it is a whole number of pages.
"""

import bisect
import re
import statistics
from dataclasses import dataclass

from galley_eval.align import Alignment, GalleyToken, ReferencePlace, State
from galley_eval.reader import PageAnchor, ReferenceKind, ReferenceText, Stream

__all__ = ["AnchorPage", "ReferencePages", "printed_page_number", "reference_pages"]


@dataclass(frozen=True, slots=True, kw_only=True)
class AnchorPage:
    """A page anchor of the body and the page found for it.
    `printed_number` is its printed page as a number, roman ones included;
    `offset` is the lower median of page index minus printed number over
    the aligned tokens between it and the next anchor, None when there is
    none; `page_index` is the printed number plus that offset, or plus the
    offset it borrows; `mismatch` is true when its offset differs from
    both its neighbours'."""

    anchor: PageAnchor
    printed_number: int | None
    offset: int | None
    page_index: int | None
    mismatch: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class ReferencePages:
    """The page index of each reference token, in the order of
    reference_places, None for an unplaced token; and each body page
    anchor in order with its page."""

    page_indices: tuple[int | None, ...]
    anchors: tuple[AnchorPage, ...]


_ARABIC = re.compile(r"\d+")
_ROMAN = re.compile(r"m{0,3}(cm|cd|d?c{0,3})(xc|xl|l?x{0,3})(ix|iv|v?i{0,3})")
_ROMAN_VALUES = {"i": 1, "v": 5, "x": 10, "l": 50, "c": 100, "d": 500, "m": 1000}


def printed_page_number(printed_page: str) -> int | None:
    """The number of a printed page, "199" or "vii" (either case), or None
    when it is neither an arabic nor a roman number."""
    if _ARABIC.fullmatch(printed_page):
        return int(printed_page)
    lowered = printed_page.lower()
    if lowered == "" or not _ROMAN.fullmatch(lowered):
        return None
    values = tuple(_ROMAN_VALUES[char] for char in lowered)
    return sum(
        -value if position + 1 < len(values) and value < values[position + 1] else value
        for position, value in enumerate(values)
    )


_ALIGNED = frozenset((State.MATCHED, State.CHANGED, State.SPLIT, State.GLUED))


def reference_pages(
    reference: ReferenceText,
    places: tuple[ReferencePlace, ...],
    alignment: Alignment,
    galley: tuple[GalleyToken, ...],
    exclude_pages: frozenset[int],
) -> ReferencePages:
    """The page of each token of `reference`, whose places are `places`,
    from its alignment with galley's words `galley`. `exclude_pages` are
    the book's page indices without a text layer; a body token placed by
    the anchors between two anchors whose pages have one of them between
    is unplaced. The page anchors among the notes are not used."""
    aligned = tuple(
        _aligned_page(alignment, galley, index) for index in range(len(places))
    )
    body_count = sum(1 for place in places if place.stream is Stream.BODY)
    anchors = _anchor_pages(reference.page_anchors, aligned, body_count)
    numbered = tuple(anchor for anchor in anchors if anchor.page_index is not None)
    starts = tuple(anchor.anchor.gap.token_index for anchor in numbered)
    excluded_after = tuple(
        position + 1 < len(numbered)
        and _excluded_between(
            numbered[position].page_index,
            numbered[position + 1].page_index,
            exclude_pages,
        )
        for position in range(len(numbered))
    )
    before = _running_before(aligned[:body_count])
    after = _running_after(aligned[:body_count])
    in_margin_note = _nearest_in_groups(
        aligned,
        tuple(
            (place.block_index, index)
            for index, place in enumerate(places[:body_count])
            if place.kind is ReferenceKind.MARGIN_NOTE
        ),
    )

    def body_page(index: int) -> int | None:
        if aligned[index] is not None:
            return aligned[index]
        if in_margin_note.get(index) is not None:
            return in_margin_note[index]
        position = bisect.bisect_right(starts, index) - 1
        if position >= 0:
            return None if excluded_after[position] else numbered[position].page_index
        return before[index] if before[index] is not None else after[index]

    body_pages = tuple(body_page(index) for index in range(body_count))
    in_note = _nearest_in_groups(
        aligned,
        tuple(
            (place.note_index, index)
            for index, place in enumerate(places)
            if place.note_index is not None
        ),
    )
    reference_pages_of_notes = _note_reference_pages(reference, body_pages)
    note_pages = tuple(
        in_note[index]
        if in_note[index] is not None
        else reference_pages_of_notes.get(_note_id(reference, places[index]))
        for index in range(body_count, len(places))
    )
    return ReferencePages(page_indices=body_pages + note_pages, anchors=anchors)


def _aligned_page(
    alignment: Alignment, galley: tuple[GalleyToken, ...], index: int
) -> int | None:
    """The page of the galley token a reference token is aligned to, the
    first one of a split; None when it is not aligned."""
    pairing = alignment.pairings[alignment.reference_pairing[index]]
    if pairing.state not in _ALIGNED:
        return None
    return galley[pairing.galley[0]].page_index


def _anchor_pages(
    anchors: tuple[PageAnchor, ...], aligned: tuple[int | None, ...], body_count: int
) -> tuple[AnchorPage, ...]:
    numbers = tuple(printed_page_number(anchor.printed_page) for anchor in anchors)
    numbered = tuple(
        position for position, number in enumerate(numbers) if number is not None
    )
    own: dict[int, int | None] = {}
    for rank, position in enumerate(numbered):
        number = numbers[position]
        assert number is not None  # numbered holds only anchors with a number
        start = anchors[position].gap.token_index
        end = (
            anchors[numbered[rank + 1]].gap.token_index
            if rank + 1 < len(numbered)
            else body_count
        )
        differences = tuple(
            page - number for page in aligned[start:end] if page is not None
        )
        own[position] = statistics.median_low(differences) if differences else None
    own_offsets = tuple(own[position] for position in numbered)
    effective = tuple(
        _effective_offset(own_offsets, rank) for rank in range(len(own_offsets))
    )
    found: dict[int, AnchorPage] = {}
    for rank, position in enumerate(numbered):
        number = numbers[position]
        assert number is not None  # numbered holds only anchors with a number
        offset = effective[rank]
        mismatch = (
            own_offsets[rank] is not None
            and 0 < rank < len(numbered) - 1
            and own_offsets[rank] != effective[rank - 1]
            and own_offsets[rank] != effective[rank + 1]
        )
        found[position] = AnchorPage(
            anchor=anchors[position],
            printed_number=number,
            offset=own_offsets[rank],
            page_index=None if offset is None else number + offset,
            mismatch=mismatch,
        )
    return tuple(
        found.get(
            position,
            AnchorPage(
                anchor=anchor,
                printed_number=None,
                offset=None,
                page_index=None,
                mismatch=False,
            ),
        )
        for position, anchor in enumerate(anchors)
    )


def _effective_offset(offsets: tuple[int | None, ...], rank: int) -> int | None:
    """The offset of the anchor at `rank`: its own, else that of the nearest
    anchor before it that has one, else of the nearest after."""
    before = (offset for offset in reversed(offsets[: rank + 1]) if offset is not None)
    after = (offset for offset in offsets[rank + 1 :] if offset is not None)
    return next(before, next(after, None))


def _excluded_between(
    first: int | None, second: int | None, exclude_pages: frozenset[int]
) -> bool:
    if first is None or second is None:
        return False
    return any(first < page < second for page in exclude_pages)


def _running_before(pages: tuple[int | None, ...]) -> tuple[int | None, ...]:
    """For each position, the last page given at or before it."""
    found: list[int | None] = []
    last: int | None = None
    for page in pages:
        last = page if page is not None else last
        found.append(last)
    return tuple(found)


def _running_after(pages: tuple[int | None, ...]) -> tuple[int | None, ...]:
    """For each position, the first page given at or after it."""
    return tuple(reversed(_running_before(tuple(reversed(pages)))))


def _nearest_in_groups(
    aligned: tuple[int | None, ...], members: tuple[tuple[int | None, int], ...]
) -> dict[int, int | None]:
    """For each token index of `members`, (group, index) pairs in order, the
    page of the nearest aligned token of its group, before it on a tie;
    None when no token of its group is aligned."""
    groups: dict[int | None, list[int]] = {}
    for group, index in members:
        groups.setdefault(group, []).append(index)
    nearest: dict[int, int | None] = {}
    for indices in groups.values():
        positions = tuple(index for index in indices if aligned[index] is not None)
        for index in indices:
            if not positions:
                nearest[index] = None
                continue
            found = bisect.bisect_left(positions, index)
            options = positions[max(found - 1, 0) : found + 1]
            closest = min(options, key=lambda position: abs(position - index))
            nearest[index] = aligned[closest]
    return nearest


def _note_reference_pages(
    reference: ReferenceText, body_pages: tuple[int | None, ...]
) -> dict[str, int | None]:
    """For each note id, the page of the body token just before its first
    reference (the first token when the reference comes before all)."""
    pages: dict[str, int | None] = {}
    for note_reference in reference.note_references:
        if (
            note_reference.note_id in pages
            or note_reference.gap.stream is not Stream.BODY
        ):
            continue
        if not body_pages:
            pages[note_reference.note_id] = None
            continue
        before = min(max(note_reference.gap.token_index - 1, 0), len(body_pages) - 1)
        pages[note_reference.note_id] = body_pages[before]
    return pages


def _note_id(reference: ReferenceText, place: ReferencePlace) -> str:
    assert place.note_index is not None  # only note tokens come here
    return reference.notes[place.note_index].note_id
