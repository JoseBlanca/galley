"""Matching the note references in the text to their notes (spec section
11, "References"): the candidates of each page, the book's reference
form, and the alignment of a page's notes with its candidates."""

from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass

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
    values: Sequence[int | None], references: Sequence[Reference]
) -> tuple[tuple[int, int], ...]:
    """The pairs (note position, candidate position) of the alignment of
    notes of `values` with `references`, both in reading order, whose total
    score is highest: each note with at most one candidate and each
    candidate with at most one note, a later note never with an earlier
    candidate. Of two alignments with the same total, the one that pairs
    the first note with the earlier candidate wins, then the second note,
    and so on; a note left alone counts as paired after every candidate."""
    note_count, candidate_count = len(values), len(references)
    scores = tuple(
        tuple(pair_score(reference, value) for reference in references)
        for value in values
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
    notes: Sequence[NoteToMatch], candidates: Sequence[Candidate]
) -> tuple[Link, ...]:
    """The links of an alignment of `notes` with `candidates`."""
    return tuple(
        Link(candidates[candidate], notes[note].note)
        for note, candidate in align(
            tuple(note.value for note in notes),
            tuple(candidate.reference for candidate in candidates),
        )
    )


def _per_page(
    notes: Sequence[NoteToMatch],
    candidates: Sequence[Candidate],
    keep: Callable[[Candidate], bool],
) -> tuple[Link, ...]:
    """The links of each page's notes with the page's candidates that
    `keep` keeps, page by page."""
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
        for link in _matched(
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


def match_footnotes(
    notes: Sequence[NoteToMatch], candidates: Sequence[Candidate]
) -> tuple[Link, ...]:
    """The footnotes linked to the candidates of their page, in page order
    (spec section 11, "Matching"): only candidates of the book's reference
    form are kept, and signs too unless that form is the bracketed number."""
    form = reference_form(notes, candidates)

    def keep(candidate: Candidate) -> bool:
        candidate_form = candidate.reference.form
        return candidate_form is form or (
            candidate_form is ReferenceForm.SIGN and form is not ReferenceForm.BRACKETED
        )

    return _per_page(notes, candidates, keep)
