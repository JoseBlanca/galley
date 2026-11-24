"""The wrong note links and the joined notes of one stage output (spec
section 6, "Wrong note links and joined notes"): the note links that go
to a note other than the reference text's, and the galley notes that also
hold the start of the next reference note, each with its page index, for
a person to check on the page image.

Both compare how the texts of the notes begin, by their alignment keys,
not which galley note the alignment puts most of a reference note in.

How the spec is read here, where it leaves a choice:

- A galley note's text is the keys of its tokens at the output, in their
  order through all its blocks, without the marker tokens its block
  starts with; a reference note's, the keys of its tokens.
- The reference notes a link is compared with are those Gutenberg
  references at a body gap within NOTE_REFERENCE_TOKENS gaps of the gap
  the link maps onto, in the order of Gutenberg's references; a link
  whose block has no token at the output, or that maps onto no gap, is
  not judged.
- A wrong link's `reference_notes` are those notes, by their ids.
"""

import difflib
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

from galley_eval.align import (
    Alignment,
    GalleyStream,
    GalleyToken,
    ReferencePlace,
    alignment_key,
)
from galley_eval.galley_side import GalleyBlock, GalleyNoteReference
from galley_eval.reader import ReferenceText, Stream
from galley_eval.scores import (
    NOTE_REFERENCE_TOKENS,
    aligned_galley_index,
    note_reference_gaps,
)

__all__ = [
    "JoinedNote",
    "LinkFault",
    "NoteLinks",
    "WrongLink",
    "begins_as",
    "note_links",
]

# The characters of two notes' texts compared, and the least ratio of
# difflib for them to begin alike; guesses, checked on Domesday's and
# Haskins' links of 23 November 2026 (spec section 6).
_START_CHARACTERS = 30
_LEAST_RATIO = 0.6

# The fewest characters a galley note must hold past its reference note's
# text to hold the start of the next note; a guess, under which the one
# or two letters OCR adds at a note's end were taken for a next note on
# Domesday's output of 23 November 2026.
_LEAST_REST = 4


class LinkFault(StrEnum):
    """Why a note link is wrong."""

    # Gutenberg references a note near the link, but not the link's note.
    OTHER_NOTE = "other_note"
    # Gutenberg references no note within NOTE_REFERENCE_TOKENS of the link.
    NO_REFERENCE = "no_reference"


@dataclass(frozen=True, slots=True, kw_only=True)
class WrongLink:
    """A galley note reference to a note other than the reference text's:
    the page index of its place, its note and its block, why it is wrong,
    and the ids of the reference notes Gutenberg references near it."""

    page_index: int
    note_id: str
    block_id: str
    fault: LinkFault
    reference_notes: tuple[str, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class JoinedNote:
    """A galley note that also holds the start of the next reference
    note: the page index of its first token, its id, and the ids of the
    reference note it begins as and of the next one."""

    page_index: int
    note_id: str
    reference_note: str
    next_reference_note: str


@dataclass(frozen=True, slots=True, kw_only=True)
class NoteLinks:
    """The wrong note links, in the order of galley's note references, and
    the joined notes, in the order of galley's notes."""

    wrong_links: tuple[WrongLink, ...]
    joined_notes: tuple[JoinedNote, ...]


def _likeness(galley_keys: str, reference_keys: str) -> float:
    """The ratio of difflib of the two texts' starts, both cut to the
    length of the shorter, at most _START_CHARACTERS; 0 when one is
    empty."""
    length = min(_START_CHARACTERS, len(galley_keys), len(reference_keys))
    if length == 0:
        return 0.0
    return difflib.SequenceMatcher(
        None, galley_keys[:length], reference_keys[:length], autojunk=False
    ).ratio()


def begins_as(galley_keys: str, reference_keys: str) -> bool:
    """Whether a text of alignment keys written one after the other begins
    as another: their first characters, as many as the shorter has and at
    most 30, have a difflib ratio of 0.6 or more. An empty text begins as
    nothing."""
    return _likeness(galley_keys, reference_keys) >= _LEAST_RATIO


def _keys(texts: Iterable[str]) -> str:
    return "".join(alignment_key(text) for text in texts)


def _galley_notes(
    galley: tuple[GalleyToken, ...], galley_blocks: frozendict[str, GalleyBlock]
) -> tuple[frozendict[str, str], frozendict[str, int], frozendict[int, str]]:
    """Each galley note's text without its marker tokens, and the page of
    its first token, by note id; and the note id of each galley token of a
    note, by its index."""
    texts: dict[str, list[str]] = {}
    pages: dict[str, int] = {}
    note_of: dict[int, str] = {}
    position_in_block: dict[str, int] = {}
    for index, token in enumerate(galley):
        if token.stream is not GalleyStream.NOTES or token.block_id is None:
            continue  # not a token of a note
        block = galley_blocks[token.block_id]
        if block.note_id is None:
            continue  # a block of the notes stream outside a note has no note
        position = position_in_block.get(token.block_id, 0)
        position_in_block[token.block_id] = position + 1
        note_of[index] = block.note_id
        pages.setdefault(block.note_id, token.page_index)
        text = texts.setdefault(block.note_id, [])
        if position >= block.marker_tokens:
            text.append(token.text)
    return (
        frozendict({note_id: _keys(text) for note_id, text in texts.items()}),
        frozendict(pages),
        frozendict(note_of),
    )


def note_links(
    reference: ReferenceText,
    alignment: Alignment,
    places: tuple[ReferencePlace, ...],
    galley: tuple[GalleyToken, ...],
    galley_blocks: frozendict[str, GalleyBlock],
    note_references: tuple[GalleyNoteReference, ...],
) -> NoteLinks:
    """The wrong note links of `note_references` and the joined notes of
    the galley tokens `galley`, aligned with `reference` by `alignment`."""
    galley_texts, galley_pages, note_of = _galley_notes(galley, galley_blocks)
    words: list[list[str]] = [[] for _ in reference.notes]
    for place in places:
        if place.note_index is not None:
            words[place.note_index].append(place.token.text)
    reference_texts = tuple(_keys(note_words) for note_words in words)
    return NoteLinks(
        wrong_links=_wrong_links(
            reference,
            galley,
            note_references,
            note_reference_gaps(alignment, places, galley, note_references),
            galley_texts,
            reference_texts,
        ),
        joined_notes=_joined_notes(
            reference,
            alignment,
            places,
            note_of,
            galley_texts,
            galley_pages,
            reference_texts,
        ),
    )


def _wrong_links(
    reference: ReferenceText,
    galley: tuple[GalleyToken, ...],
    note_references: tuple[GalleyNoteReference, ...],
    gaps: tuple[int | None, ...],
    galley_texts: frozendict[str, str],
    reference_texts: tuple[str, ...],
) -> tuple[WrongLink, ...]:
    note_index = {note.note_id: index for index, note in enumerate(reference.notes)}
    gutenberg = tuple(
        (note_reference.gap.token_index, note_reference.note_id)
        for note_reference in reference.note_references
        if note_reference.gap.stream is Stream.BODY
    )
    block_tokens: dict[str, list[int]] = {}
    for index, token in enumerate(galley):
        if token.block_id is not None:
            block_tokens.setdefault(token.block_id, []).append(index)
    wrong: list[WrongLink] = []
    for note_reference, gap in zip(note_references, gaps, strict=True):
        if gap is None:
            continue  # no place in the reference to judge it at
        near = tuple(
            note_id
            for gutenberg_gap, note_id in gutenberg
            if abs(gutenberg_gap - gap) <= NOTE_REFERENCE_TOKENS
        )
        text = galley_texts.get(note_reference.note_id, "")
        if any(begins_as(text, reference_texts[note_index[note]]) for note in near):
            continue  # the link goes to a note Gutenberg references there
        positions = block_tokens[note_reference.block_id]
        place = positions[min(note_reference.tokens_before, len(positions) - 1)]
        wrong.append(
            WrongLink(
                page_index=galley[place].page_index,
                note_id=note_reference.note_id,
                block_id=note_reference.block_id,
                fault=LinkFault.OTHER_NOTE if near else LinkFault.NO_REFERENCE,
                reference_notes=near,
            )
        )
    return tuple(wrong)


def _joined_notes(
    reference: ReferenceText,
    alignment: Alignment,
    places: tuple[ReferencePlace, ...],
    note_of: frozendict[int, str],
    galley_texts: frozendict[str, str],
    galley_pages: frozendict[str, int],
    reference_texts: tuple[str, ...],
) -> tuple[JoinedNote, ...]:
    candidates: dict[str, set[int]] = {}
    for index, place in enumerate(places):
        if place.note_index is None:
            continue  # a body token
        galley_index = aligned_galley_index(alignment, index)
        if galley_index is not None and galley_index in note_of:
            candidates.setdefault(note_of[galley_index], set()).add(place.note_index)
    joined: list[JoinedNote] = []
    for note_id, text in galley_texts.items():
        found = sorted(candidates.get(note_id, set()))
        if not found:
            continue  # no reference note aligned to it
        best = max(found, key=lambda index: _likeness(text, reference_texts[index]))
        if best + 1 == len(reference.notes) or not begins_as(
            text, reference_texts[best]
        ):
            continue  # the last note, or a note it does not begin as
        rest = text[len(reference_texts[best]) :]
        if len(rest) >= _LEAST_REST and begins_as(rest, reference_texts[best + 1]):
            joined.append(
                JoinedNote(
                    page_index=galley_pages[note_id],
                    note_id=note_id,
                    reference_note=reference.notes[best].note_id,
                    next_reference_note=reference.notes[best + 1].note_id,
                )
            )
    return tuple(joined)
