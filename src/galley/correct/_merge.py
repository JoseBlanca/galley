"""The changes the model's reading of a page makes to galley's reading
(docs/specs/correct.md, section 7), the second reading's values (section
9), and the edits they become (section 8)."""

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import assert_never

from galley.correct._align import Pair, align
from galley.correct._reading import GalleyToken, Place
from galley.correct._tokens import Token, alike, clean_answer, tokens
from galley.model import Block, Edit, block_sha256

_logger = logging.getLogger(__name__)

AUTHOR = "correct"
# Section 7: two forms less alike than this give no replacement; guessed,
# not measured: a pair a word out of place makes, "kadesh" with "city", is
# 0, "puem" with "poem" 0.75, "3%" with "305" 0.5.
_LEAST_ALIKE = 0.3
_ROMAN_LETTERS = frozenset("IVXLCDM")


class ChangeKind(StrEnum):
    """A replacement of a core, or words put in after or before one."""

    REPLACE = "replace"
    INSERT_AFTER = "insert_after"
    INSERT_BEFORE = "insert_before"


class EditReason(StrEnum):
    """The reason an edit of the correct stage gives (section 8)."""

    VISION_WORD = "vision_word"
    VISION_MISSING_WORDS = "vision_missing_words"


@dataclass(frozen=True, slots=True, kw_only=True)
class Change:
    """One change the model proposes on page `page_index`: at `place`, the
    core of a token of galley's, `text` replaces the core (REPLACE) or goes
    after or before it with a space (INSERT_AFTER, INSERT_BEFORE).
    `second_reading` is what the second model read there, None without a
    second reading or outside the notes."""

    kind: ChangeKind
    page_index: int
    place: Place
    text: str
    second_reading: str | None


@dataclass(frozen=True, slots=True)
class Answer:
    """A model's answer cut into tokens: `text` as cleaned and its tokens."""

    text: str
    tokens: tuple[Token, ...]


def answer(raw: str) -> Answer:
    """The model's raw answer as cleaned text and its tokens."""
    text = clean_answer(raw)
    return Answer(text, tokens(text))


def _core(reading_answer: Answer, position: int) -> str:
    token = reading_answer.tokens[position]
    return reading_answer.text[token.start : token.end]


def _is_roman(core: str) -> bool:
    letters = [character for character in core if character.isalpha()]
    return bool(letters) and all(letter in _ROMAN_LETTERS for letter in letters)


def cased(model_core: str, galley_core: str) -> str:
    """The model's core with galley's case when the model wrote small
    capitals as capitals (section 7): the model's core, less a final "'s",
    has no lower-case letter, galley's has one, and the model's is not a
    roman numeral."""
    stem = model_core.removesuffix("'s").removesuffix("’s")
    if (
        any(character.islower() for character in stem)
        or not any(character.islower() for character in galley_core)
        or not any(character.isalpha() for character in stem)
        or _is_roman(stem)
    ):
        return model_core
    if galley_core[:1].isupper():
        return model_core[:1] + model_core[1:].lower()
    return model_core.lower()


def _runs(pairs: Sequence[Pair]) -> tuple[tuple[int | None, tuple[int, ...]], ...]:
    """Each run of the model's tokens that pair with none of galley's: the
    position of galley's token before it (None at the start) and the
    positions of the run's tokens."""
    found = []
    before: int | None = None
    run: list[int] = []
    for pair in pairs:
        if pair.first is None and pair.second is not None:
            run.append(pair.second)
            continue
        if run:
            found.append((before, tuple(run)))
            run = []
        before = pair.first
    if run:
        found.append((before, tuple(run)))
    return tuple(found)


def _paired(pairs: Sequence[Pair]) -> dict[int, int]:
    return {
        pair.first: pair.second
        for pair in pairs
        if pair.first is not None and pair.second is not None
    }


def _gap_words(model_answer: Answer, run: tuple[int, ...]) -> tuple[str, ...]:
    """The cores of a run's tokens that are not only digits (section 7)."""
    return tuple(
        _core(model_answer, position)
        for position in run
        if not model_answer.tokens[position].form.isdigit()
    )


def _inside_note(reading: Sequence[GalleyToken], before: int, after: int) -> bool:
    """Whether a run between galley's tokens `before` and `after` is inside
    a note: the token before is the note's, the one after is the same
    note's or starts the next note."""
    note = reading[before].note_id
    if note is None:
        return False
    following = reading[after]
    return following.note_id == note or (
        following.note_id is not None and following.starts_note
    )


def _anchor(
    reading: Sequence[GalleyToken], before: int, after: int
) -> tuple[ChangeKind, Place] | None:
    """Where a run inside a note goes: after galley's token before it when
    that one can change; else before the first changeable token of the
    note after the run; else after the last changeable one of the note
    before it; None when the note has none on the page."""
    token = reading[before]
    if token.place is not None:
        return ChangeKind.INSERT_AFTER, token.place
    note = token.note_id
    for position in range(after, len(reading)):
        if reading[position].note_id != note:
            break
        if (place := reading[position].place) is not None:
            return ChangeKind.INSERT_BEFORE, place
    for position in range(before, -1, -1):
        if reading[position].note_id != note:
            break
        if (place := reading[position].place) is not None:
            return ChangeKind.INSERT_AFTER, place
    return None


def _next_galley(pairs: Sequence[Pair], before: int | None) -> int | None:
    """The position of galley's first token after `before`."""
    start = -1 if before is None else before
    return next(
        (pair.first for pair in pairs if pair.first is not None and pair.first > start),
        None,
    )


def page_changes(
    page_index: int,
    reading: Sequence[GalleyToken],
    model_answer: Answer,
    galley_text: Mapping[Place, str],
    second_answer: Answer | None = None,
) -> tuple[Change, ...]:
    """The changes the model's answer makes to galley's reading of a page,
    in the order of the reading. `galley_text` gives the core of each
    changeable token, by its place. With `second_answer`, the second
    model's reading of the page's footnote band, each change in a note
    records what it read there."""
    pairs = align(
        [token.form for token in reading], [t.form for t in model_answer.tokens]
    )
    second = _second_reading(reading, second_answer)
    changes: list[tuple[float, Change]] = []
    for pair in pairs:
        if pair.first is None or pair.second is None:
            continue
        token = reading[pair.first]
        model_form = model_answer.tokens[pair.second].form
        if (
            token.place is None
            or token.form == model_form
            or alike(token.form, model_form) < _LEAST_ALIKE
        ):
            continue
        new_core = cased(_core(model_answer, pair.second), galley_text[token.place])
        changes.append(
            (
                pair.first,
                Change(
                    kind=ChangeKind.REPLACE,
                    page_index=page_index,
                    place=token.place,
                    text=new_core,
                    second_reading=second.replaced(pair.first)
                    if token.note_id is not None
                    else None,
                ),
            )
        )
    for before, run in _runs(pairs):
        after = _next_galley(pairs, before)
        if before is None or after is None or not _inside_note(reading, before, after):
            continue
        words = _gap_words(model_answer, run)
        if not words:
            continue
        anchor = _anchor(reading, before, after)
        if anchor is None:
            _logger.info(
                "page %d: no word of note %s to put %r beside; not put in",
                page_index,
                reading[before].note_id,
                " ".join(words),
            )
            continue
        kind, place = anchor
        changes.append(
            (
                before + 0.5,
                Change(
                    kind=kind,
                    page_index=page_index,
                    place=place,
                    text=" ".join(words),
                    second_reading=second.inserted(before),
                ),
            )
        )
    return tuple(change for _, change in sorted(changes, key=lambda item: item[0]))


@dataclass(frozen=True, slots=True)
class _Second:
    """The second model's reading lined up with the notes of galley's
    reading: its core paired with each of galley's tokens, and its words
    put in after each, by the position in the whole reading."""

    present: bool
    paired: Mapping[int, str]
    gaps: Mapping[int, str]

    def replaced(self, position: int) -> str | None:
        return self.paired.get(position, "") if self.present else None

    def inserted(self, before: int) -> str | None:
        return self.gaps.get(before, "") if self.present else None


def _second_reading(
    reading: Sequence[GalleyToken], second_answer: Answer | None
) -> _Second:
    if second_answer is None:
        return _Second(present=False, paired={}, gaps={})
    notes = [
        position for position, token in enumerate(reading) if token.note_id is not None
    ]
    pairs = align(
        [reading[position].form for position in notes],
        [token.form for token in second_answer.tokens],
    )
    paired = {
        notes[first]: _core(second_answer, second)
        for first, second in _paired(pairs).items()
    }
    gaps = {
        notes[before]: " ".join(_gap_words(second_answer, run))
        for before, run in _runs(pairs)
        if before is not None
    }
    return _Second(present=True, paired=paired, gaps=gaps)


def is_doubtful(change: Change) -> bool:
    """Whether the second reading differs from the change's words, in
    comparison form (section 9); False without a second reading."""
    if change.second_reading is None:
        return False

    def forms(text: str) -> tuple[str, ...]:
        return tuple(token.form for token in tokens(text))

    return forms(change.second_reading) != forms(change.text)


# The edits.


@dataclass(frozen=True, slots=True)
class _Word:
    """A whitespace word of a span: `text[start:end]`."""

    start: int
    end: int


def _words(text: str) -> tuple[_Word, ...]:
    found = []
    start = None
    for position, character in enumerate(text):
        if character.isspace():
            if start is not None:
                found.append(_Word(start, position))
                start = None
        elif start is None:
            start = position
    if start is not None:
        found.append(_Word(start, len(text)))
    return tuple(found)


def _changed_word(word_text: str, offset: int, changes: Sequence[Change]) -> str:
    """The word with its changes made; `offset` is where the word starts in
    its span. Changes later in the word first, so earlier offsets hold."""
    result = word_text
    for change in sorted(changes, key=lambda c: (c.place.start, c.kind), reverse=True):
        start = change.place.start - offset
        end = change.place.end - offset
        match change.kind:
            case ChangeKind.REPLACE:
                result = result[:start] + change.text + result[end:]
            case ChangeKind.INSERT_AFTER:
                result = result + " " + change.text
            case ChangeKind.INSERT_BEFORE:
                result = change.text + " " + result
            case _:
                assert_never(change.kind)
    return result


def _occurs_once(text: str, part: str) -> bool:
    first = text.find(part)
    return first != -1 and text.find(part, first + 1) == -1


def block_edits(
    block: Block, changes: Sequence[Change], model: str
) -> tuple[Edit, ...]:
    """The edits of one block from its changes (section 8): one edit for
    each word changed, in the order of the text, each `old` widened by
    neighbouring words of the span that no other change touches until it
    occurs once in the block's text as structure wrote it and as the edits
    before it leave it. A change no such `old` can hold is not proposed,
    and logged."""
    by_word: dict[tuple[int, int], list[Change]] = {}
    span_words = {index: _words(span.text) for index, span in enumerate(block.spans)}
    for change in changes:
        words = span_words[change.place.span_index]
        position = next(
            index
            for index, word in enumerate(words)
            if word.start <= change.place.start and change.place.end <= word.end
        )
        by_word.setdefault((change.place.span_index, position), []).append(change)
    original = "".join(span.text for span in block.spans)
    spans = [span.text for span in block.spans]
    shift = dict.fromkeys(range(len(spans)), 0)
    edits = []
    for span_index, position in sorted(by_word):
        word_changes = by_word[(span_index, position)]
        words = span_words[span_index]
        text = block.spans[span_index].text
        word = words[position]
        new_word = _changed_word(text[word.start : word.end], word.start, word_changes)
        if new_word == text[word.start : word.end]:
            continue
        changed = {key[1] for key in by_word if key[0] == span_index}
        bounds = _context(words, position, changed, text, (original, "".join(spans)))
        first_change = word_changes[0]
        if bounds is None:
            _logger.info(
                "page %d, block %s: %r occurs more than once however widened; "
                "not proposed",
                first_change.page_index,
                block.id,
                text[word.start : word.end],
            )
            continue
        low, high = bounds
        old = text[words[low].start : words[high].end]
        new = (
            text[words[low].start : word.start]
            + new_word
            + text[word.end : words[high].end]
        )
        reason = (
            EditReason.VISION_WORD
            if any(change.kind is ChangeKind.REPLACE for change in word_changes)
            else EditReason.VISION_MISSING_WORDS
        )
        edits.append(
            Edit(
                block_id=block.id,
                block_sha256=block_sha256(block),
                old=old,
                new=new,
                author=AUTHOR,
                reason=reason.value,
                page_index=first_change.page_index,
                model=model,
                second_reading=first_change.second_reading,
            )
        )
        start = words[low].start + shift[span_index]
        spans[span_index] = (
            spans[span_index][:start] + new + spans[span_index][start + len(old) :]
        )
        shift[span_index] += len(new) - len(old)
    return tuple(edits)


def _context(
    words: Sequence[_Word],
    position: int,
    changed: set[int],
    text: str,
    texts: tuple[str, str],
) -> tuple[int, int] | None:
    """The first and last word of `old` around the word at `position` of
    the span `text`, widened alternately after and before, never over a word
    another change touches, until `old` occurs once in each of `texts`, the
    block's text as structure wrote it and as edited so far; None when it
    never does."""
    low = high = position
    toward_end = True
    while True:
        old = text[words[low].start : words[high].end]
        if all(_occurs_once(block_text, old) for block_text in texts):
            return low, high
        can_end = high + 1 < len(words) and high + 1 not in changed
        can_start = low - 1 >= 0 and low - 1 not in changed
        if not can_end and not can_start:
            return None
        if (toward_end and can_end) or not can_start:
            high += 1
        else:
            low -= 1
        toward_end = not toward_end
