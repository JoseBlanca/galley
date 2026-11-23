"""Matching the note references in the text to their notes (spec section
11, "References"): the candidates of each page, the book's reference
form, and the alignment of a page's notes with its candidates."""

import itertools
import re
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, replace

from galley.note_references import after_last_letter, is_punctuation
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


def with_values_in_order(notes: Sequence[NoteToMatch]) -> tuple[NoteToMatch, ...]:
    """The endnotes of one note group, in the book's order, with the value
    N given to a note whose value is not N but which lies between a note of
    value N - 1 and one of value N + 1 (spec section 12, "The gap between
    linked neighbours"): its marker was misread, "37." between "56." and
    "58."."""

    def in_order(place: int) -> NoteToMatch:
        note = notes[place]
        if place == 0 or place == len(notes) - 1:
            return note
        low, high = notes[place - 1].value, notes[place + 1].value
        if low is None or high is None or high != low + 2 or note.value == low + 1:
            return note
        return replace(note, value=low + 1)

    return tuple(in_order(place) for place in range(len(notes)))


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


# Spec section 12, "The gap between linked neighbours".


@dataclass(frozen=True, slots=True)
class BodyWord:
    """A word of a paragraph of the body where a reference may hide: the
    position of its block among the body's blocks and of the word in the
    block, its page index, its text, and the texts of the words before and
    after it in its block ("" at either end)."""

    block: int
    word: int
    page_index: int
    text: str
    previous: str
    following: str


_MONTHS = frozenset(
    {
        *("january", "february", "march", "april", "may", "june", "july"),
        *("august", "september", "october", "november", "december"),
        *("jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "sept"),
        *("oct", "nov", "dec"),
    }
)
# The signs the OCR gives for a raised number that a book's body never
# prints as text: "^" and "~" in every book, a straight quotation mark in a
# book that prints curly ones more often.
_ALWAYS_SIGNS = frozenset("^~")
_CURLY = frozendict({"'": "‘’", '"': "“”"})
_LONE_NUMBER = re.compile(r"[0-9]{1,3}")
# 1 to 3 digits after a letter or punctuation, and no letter or digit after.
_GLUED_DIGITS = re.compile(
    r"(?P<before>.*[^\W\d_]|.*[^\w\s])(?P<reference>[0-9]{1,3})(?P<after>[^\w\s]*)"
)


# What before glued digits makes them part of a number, not a reference:
# a number's own punctuation or a range's hyphen or dash after a digit
# ("10.35" a time, "2,718" a number, "1914-18" a range), or a currency or
# section sign with any punctuation after it ("£16", "§.12").
_NUMBER_PUNCTUATION = re.compile(r".*(?:[0-9][.,:;\-–—]*|[£$§][^\w\s]*)")


def foreign_signs(words: Iterable[str]) -> frozenset[str]:
    """The signs that stand for a raised number in a book whose body holds
    `words` (spec section 12, "The gap between linked neighbours"): "^"
    and "~", and each straight quotation mark whose curly forms the words
    hold more often than it."""
    counts = Counter(character for word in words for character in word)
    return _ALWAYS_SIGNS | frozenset(
        straight
        for straight, curly in _CURLY.items()
        if sum(counts[character] for character in curly) > counts[straight]
    )


def _one_digit_confused(digits: str, number: str) -> bool:
    """Whether `digits` and `number` differ in one digit, a pair the OCR
    confuses."""
    differing = tuple(
        frozenset(pair)
        for pair in zip(digits, number, strict=False)
        if len(set(pair)) > 1
    )
    return (
        len(digits) == len(number)
        and len(differing) == 1
        and differing[0] in _CONFUSED_DIGITS
    )


def gap_reference(
    word: BodyWord, value: int, signs: frozenset[str]
) -> Reference | None:
    """The reference to note `value` that `word` may be when it lies in the
    gap between the references of the notes before and after it (spec
    section 12, "The gap between linked neighbours"), or None: the lone
    number `value` ("14"), unless a month's name is beside it; digits
    glued after a letter or punctuation, with no letter or digit after,
    that are `value`, the start or end of its digits ("'9" for 19), or one
    confused digit away from it; or one of `signs` after a letter and
    punctuation ("river.\""), or alone after such a word, with only
    punctuation after."""
    number = str(value)
    if _LONE_NUMBER.fullmatch(word.text):
        beside = {
            word.previous.strip(".,;:").lower(),
            word.following.strip(".,;:").lower(),
        }
        if beside & _MONTHS or not (
            word.text == number
            or (
                _ends_a_phrase(word.previous)
                and (number.startswith(word.text) or number.endswith(word.text))
            )
        ):
            return None
        return Reference("", word.text, "", ReferenceForm.GLUED, int(word.text))
    glued = _GLUED_DIGITS.fullmatch(word.text)
    if glued is not None:
        digits = glued.group("reference")
        if _NUMBER_PUNCTUATION.fullmatch(glued.group("before")) or not (
            digits == number
            or number.startswith(digits)
            or number.endswith(digits)
            or _one_digit_confused(digits, number)
        ):
            return None
        return Reference(
            glued.group("before"),
            digits,
            glued.group("after"),
            ReferenceForm.GLUED,
            int(digits),
        )
    sign = _sign_reference(word.text, signs)
    if sign is not None and not sign.before and not _ends_a_phrase(word.previous):
        return None
    return sign


def _ends_a_phrase(text: str) -> bool:
    """Whether `text` is a word with a letter and punctuation after its last
    letter ("river.")."""
    return any(character.isalpha() for character in text) and bool(
        (tail := after_last_letter(text)) and is_punctuation(tail)
    )


def _sign_reference(text: str, signs: frozenset[str]) -> Reference | None:
    """The last of `signs` in `text` as a reference: alone, or after a
    letter and then punctuation, with only punctuation after ("river.\"").
    A sign straight after a letter is none: "river'" may be a closing
    quotation mark the OCR read straight."""
    places = tuple(place for place, character in enumerate(text) if character in signs)
    if not places:
        return None
    place = places[-1]
    before, sign, after = text[:place], text[place], text[place + 1 :]
    if not is_punctuation(after):
        return None
    if before and not _ends_a_phrase(before):
        return None
    return Reference(before, sign, after, ReferenceForm.SIGN, None)


def _unlinked_runs(
    valued: Sequence[NoteToMatch], linked: Mapping[int, tuple[int, int]]
) -> tuple[tuple[tuple[NoteToMatch, ...], tuple[int, int], tuple[int, int]], ...]:
    """The runs of notes of consecutive values, none linked, between a
    linked note of the value before the run and one of the value after it,
    each with the places (block, word) of those two notes' references."""
    by_value = {note.value: note for note in valued if note.value is not None}

    def is_linked(value: int) -> bool:
        return value in by_value and by_value[value].note in linked

    runs: list[tuple[tuple[NoteToMatch, ...], tuple[int, int], tuple[int, int]]] = []
    for first in sorted(by_value):
        if is_linked(first) or not is_linked(first - 1):
            continue
        last = first
        while last + 1 in by_value and not is_linked(last + 1):
            last += 1
        if is_linked(last + 1):
            runs.append(
                (
                    tuple(by_value[value] for value in range(first, last + 1)),
                    linked[by_value[first - 1].note],
                    linked[by_value[last + 1].note],
                )
            )
    return tuple(runs)


def gap_links(
    notes: Sequence[NoteToMatch],
    words: Sequence[BodyWord],
    links: Sequence[Link],
    signs: frozenset[str],
) -> tuple[Link, ...]:
    """The endnotes of one note group that `links` left unlinked, linked in
    the gap between linked neighbours (spec section 12, "The gap between
    linked neighbours"): for a run of k notes of consecutive values none
    of which is linked, whose value before and value after are linked, the
    words of `words` between those two references that `gap_reference`
    reads as a reference to one of the run's notes, when there are exactly
    k of them and the i-th reads as the i-th note's. `words` are the
    group's chapter's words in reading order, which may hold the words
    `links` took: those lie at the ends of the gaps, never inside; a link
    made here is never a neighbour of another. `links` are expected in the
    reading order of their notes' values, as the matching makes them; a
    run whose first reference does not come before its second takes
    nothing, and a word taken by one run, in the order of the runs'
    values, is in no other run's gap."""
    valued = tuple(note for note in notes if note.value is not None)
    linked = {link.note: (link.candidate.block, link.candidate.word) for link in links}
    made: list[Link] = []
    taken: set[tuple[int, int]] = set()
    for run, start, end in _unlinked_runs(valued, linked):
        if not start < end:
            continue
        gap = tuple(
            word
            for word in words
            if start < (word.block, word.word) < end
            and (word.block, word.word) not in taken
        )
        found = tuple(
            word
            for word in gap
            if any(
                gap_reference(word, note.value, signs) is not None
                for note in run
                if note.value is not None
            )
        )
        if len(found) != len(run):
            continue
        readings = tuple(
            gap_reference(word, note.value, signs) if note.value is not None else None
            for word, note in zip(found, run, strict=True)
        )
        if any(reading is None for reading in readings):
            continue
        made.extend(
            Link(Candidate(word.block, word.word, word.page_index, reading), note.note)
            for word, note, reading in zip(found, run, readings, strict=True)
            if reading is not None
        )
        taken.update((word.block, word.word) for word in found)
    return tuple(made)
