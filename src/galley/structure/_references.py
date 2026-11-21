"""Matching the note references in the text to their notes (spec section
11, "References"): the candidates of each page, the book's reference
form, and the alignment of a page's notes with its candidates."""

import itertools
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace

from galley.structure._markers import Reference, ReferenceForm

# Spec section 11, "Matching": the scores of a pair. The digit pairs the
# OCR confuses, as a candidate's number and a note's value that differ in
# one digit.
_EXACT = 3
_CONFUSED = 2
_SIGN_WITHOUT_VALUE = 2
_SIGN_WITH_VALUE = 1
_CONFUSED_DIGITS = frozenset(
    frozenset(pair) for pair in ("38", "56", "17", "35", "68", "14", "89", "28")
)
# Spec section 11, "References": a candidate that is an opening single
# quotation mark after a letter ("Salvolini‘").
_OPENING_QUOTE = "\u2018"


@dataclass(frozen=True, slots=True)
class Candidate:
    """A candidate reference: the position of its block among the body's
    blocks and of its word in the block, the word's page index, and the
    reference the word holds."""

    block: int
    word: int
    page_index: int
    reference: Reference


@dataclass(frozen=True, slots=True)
class NoteToMatch:
    """A note to match: its position among the notes, its first page index
    and its value."""

    note: int
    page_index: int
    value: int | None


@dataclass(frozen=True, slots=True)
class Link:
    """A candidate linked to a note, both given by position."""

    candidate: Candidate
    note: int


def pair_score(reference: Reference, note_value: int | None) -> int:
    """The score of pairing a candidate with a note of `note_value`, 0 when
    they are never paired (spec section 11, "Matching")."""
    if reference.form is ReferenceForm.SIGN:
        return _SIGN_WITHOUT_VALUE if note_value is None else _SIGN_WITH_VALUE
    if reference.value is None or note_value is None:
        return 0
    if reference.value == note_value:
        return _EXACT
    candidate, note = str(reference.value), str(note_value)
    differing = tuple(
        frozenset((one, other))
        for one, other in zip(candidate, note, strict=False)
        if one != other
    )
    if len(candidate) == len(note) and len(differing) == 1:
        return _CONFUSED if differing[0] in _CONFUSED_DIGITS else 0
    return 0


def align(
    values: Sequence[int | None],
    references: Sequence[Reference],
    score: Callable[[Reference, int | None], int] = pair_score,
) -> tuple[tuple[int, int], ...]:
    """The pairs (note position, candidate position) of the alignment of
    notes of `values` with `references`, both in reading order, whose total
    score is highest: each note with at most one candidate and each
    candidate with at most one note, a later note never with an earlier
    candidate. Of two alignments with the same total, the one that pairs
    the first note with the earlier candidate wins, then the second note,
    and so on; a note left alone counts as paired after every candidate.
    `score` gives each pair's score, `pair_score` unless given."""
    note_count, candidate_count = len(values), len(references)
    scores = tuple(
        tuple(score(reference, value) for reference in references) for value in values
    )
    # best[i][j]: the highest total of the notes from i and the candidates
    # from j.
    best = [[0] * (candidate_count + 1) for _ in range(note_count + 1)]
    for i in range(note_count - 1, -1, -1):
        row, below = best[i], best[i + 1]
        for j in range(candidate_count - 1, -1, -1):
            paired = scores[i][j] + below[j + 1] if scores[i][j] else 0
            row[j] = max(paired, below[j], row[j + 1])
    pairs: list[tuple[int, int]] = []
    j = 0
    for i in range(note_count):
        target = best[i][j]
        chosen = next(
            (
                k
                for k in range(j, candidate_count)
                if scores[i][k] and scores[i][k] + best[i + 1][k + 1] == target
            ),
            None,
        )
        if chosen is not None:
            pairs.append((i, chosen))
            j = chosen + 1
    return tuple(pairs)


def _matched(
    notes: Sequence[NoteToMatch],
    candidates: Sequence[Candidate],
    score: Callable[[Reference, int | None], int] = pair_score,
) -> tuple[Link, ...]:
    """The links of an alignment of `notes` with `candidates`, by `score`."""
    return tuple(
        Link(candidates[candidate], notes[note].note)
        for note, candidate in align(
            tuple(note.value for note in notes),
            tuple(candidate.reference for candidate in candidates),
            score,
        )
    )


def _matched_with_quotes(
    notes: Sequence[NoteToMatch], candidates: Sequence[Candidate]
) -> tuple[Link, ...]:
    """The links of one page's `notes` with its `candidates`, those that are
    an opening single quotation mark only when they pair more notes than
    without them (spec section 11, "References": "Kings‘" may be a misread
    closing quote)."""
    without = _matched(
        notes,
        tuple(
            candidate
            for candidate in candidates
            if candidate.reference.reference != _OPENING_QUOTE
        ),
    )
    with_quotes = _matched(notes, candidates)
    return with_quotes if len(with_quotes) > len(without) else without


def _per_page(
    notes: Sequence[NoteToMatch],
    candidates: Sequence[Candidate],
    keep: Callable[[Candidate], bool],
    match: Callable[
        [Sequence[NoteToMatch], Sequence[Candidate]], tuple[Link, ...]
    ] = _matched,
) -> tuple[Link, ...]:
    """The links of each page's notes with the page's candidates that
    `keep` keeps, page by page, each page's by `match`."""
    notes_by_page: dict[int, list[NoteToMatch]] = {}
    for note in notes:
        notes_by_page.setdefault(note.page_index, []).append(note)
    candidates_by_page: dict[int, list[Candidate]] = {}
    for candidate in candidates:
        if keep(candidate):
            candidates_by_page.setdefault(candidate.page_index, []).append(candidate)
    return tuple(
        link
        for page_index in sorted(notes_by_page)
        for link in match(
            notes_by_page[page_index], candidates_by_page.get(page_index, ())
        )
    )


def reference_form(
    notes: Sequence[NoteToMatch], candidates: Sequence[Candidate]
) -> ReferenceForm | None:
    """The book's reference form (spec section 11): the kind of candidate
    with the most exact matches when every candidate is matched page by
    page; None when no candidate matches exactly. On a tie, the first of
    glued, bracketed and sign."""
    values = {note.note: note.value for note in notes}
    exact = Counter(
        link.candidate.reference.form
        for link in _per_page(notes, candidates, lambda _: True)
        if link.candidate.reference.value is not None
        and link.candidate.reference.value == values[link.note]
    )
    if not exact:
        return None
    return max(ReferenceForm, key=lambda form: exact[form])


def _with_values_between(notes: Sequence[NoteToMatch]) -> tuple[NoteToMatch, ...]:
    """`notes` with a value given to each note without one that lies between
    two notes of its page with values `a` and `b`, `k` places after the
    first, when `b - a` is the number of places from the first to the
    second: it is matched as a note of value `a + k` (spec section 11,
    "Matching"; Kadesh's page 10)."""
    given = list(notes)
    valued = [
        (place, note.value)
        for place, note in enumerate(notes)
        if note.value is not None
    ]
    # The notes are in the book's order, so those between two notes of one
    # page are on that page.
    for (first, low), (second, high) in itertools.pairwise(valued):
        if (
            notes[first].page_index == notes[second].page_index
            and high - low == second - first
        ):
            for place in range(first + 1, second):
                given[place] = replace(notes[place], value=low + place - first)
    return tuple(given)


def match_footnotes(
    notes: Sequence[NoteToMatch], candidates: Sequence[Candidate]
) -> tuple[Link, ...]:
    """The footnotes linked to the candidates of their page, in page order
    (spec section 11, "Matching"): a note without a value between two of
    its page whose values its place fits is matched with the value of its
    place; only candidates of the book's reference form are kept, and signs
    too unless that form is the bracketed number; a page's opening single
    quotation marks only when they pair more of its notes."""
    notes = _with_values_between(notes)
    form = reference_form(notes, candidates)

    def keep(candidate: Candidate) -> bool:
        candidate_form = candidate.reference.form
        return candidate_form is form or (
            candidate_form is ReferenceForm.SIGN and form is not ReferenceForm.BRACKETED
        )

    return _per_page(notes, candidates, keep, _matched_with_quotes)


def match_endnotes(
    notes: Sequence[NoteToMatch], candidates: Sequence[Candidate]
) -> tuple[Link, ...]:
    """The endnotes of one note group linked to the glued numbers of its
    chapter (spec section 12, "References"): the endnotes with a value in
    the order of their values, against `candidates` in reading order, by
    the scores of footnotes, but a candidate that reads another number
    than a note's never takes it when another glued candidate reads the
    note's number, or when its own number lies among the notes' numbers
    and no note reads it: the note it stands for lost its marker to the
    OCR (Haynes' pages 234 and 301)."""
    valued = sorted(
        (note for note in notes if note.value is not None),
        key=lambda note: note.value if note.value is not None else 0,
    )
    glued = tuple(
        candidate
        for candidate in candidates
        if candidate.reference.form is ReferenceForm.GLUED
    )
    read = Counter(candidate.reference.value for candidate in glued)
    values = frozenset(note.value for note in valued if note.value is not None)
    lowest, highest = min(values, default=0), max(values, default=0)

    def score(reference: Reference, note_value: int | None) -> int:
        # A candidate reading another number never takes a note whose own
        # number another candidate reads, nor stands for a missing note.
        value = reference.value
        if value != note_value and (
            read[note_value] > 0
            or (
                value is not None and lowest <= value <= highest and value not in values
            )
        ):
            return 0
        return pair_score(reference, note_value)

    return _matched(valued, glued, score)
