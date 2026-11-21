"""The changes the model's reading of a page makes to galley's reading
(docs/specs/correct.md, section 7), the second reading's values (section
9), and the edits they become (section 8)."""

import logging
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import assert_never

from galley.correct._align import Pair, align
from galley.correct._reading import GalleyToken, Place
from galley.correct._tokens import (
    LineEndJoin,
    Token,
    alike,
    cleaned_answer,
    comparison_form,
    tokens,
)
from galley.model import Block, Edit, block_sha256, only_occurrence

_logger = logging.getLogger(__name__)

AUTHOR = "correct"
# Section 7: two forms less alike than this give no replacement: a pair a
# word out of place makes, "kadesh" with "city", is 0, "puem" with "poem"
# 0.75, "3%" with "305" 0.5. Measured on the six reference pages with the
# recorded answers, 19 November 2026: notes 3.8 wrong words in 100 and 14
# fluent wrong words without it, 5.3 and 11 with 0.3, 6.7 and 8 with 0.5.
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
    """A model's answer cut into tokens: `text` as cleaned and its tokens;
    `joins` gives, by token position, the line-end join inside the token,
    for a word the model printed broken at a line end."""

    text: str
    tokens: tuple[Token, ...]
    joins: Mapping[int, LineEndJoin] = frozendict()


def answer(raw: str) -> Answer:
    """The model's raw answer as cleaned text and its tokens."""
    text, joins = cleaned_answer(raw)
    answer_tokens = tokens(text)
    return Answer(
        text,
        answer_tokens,
        frozendict(
            {
                position: join
                for join in joins
                for position, token in enumerate(answer_tokens)
                if token.start < join.offset < token.end
            }
        ),
    )


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


# Section 7: the marks inside a core that part two printed words.
_SEPARATOR = re.compile(r"(?<=[^\W_])[,.:\-\u2013](?=[^\W_])")


_DIGIT_RUN = re.compile(r"\d\d")
# Section 7, (c): digits and marker signs glued before or after two letters
# or more, a note marker misread ("1%The", Kadesh page 53).
# One digit alone is not such a piece: it is often a letter misread
# ("1bid" for "ibid", "4meni" for "Ameni" on the excerpt kadesh_redo).
_PIECE = r"(?:[\d*\u2020\u2021%]{2,}|[\d]*[*\u2020\u2021%][\d*\u2020\u2021%]*)"
_GLUED_PIECE = re.compile(rf"^{_PIECE}(?=[^\W\d_]{{2}})|(?<=[^\W\d_]{{2}}){_PIECE}$")


def _alphanumerics(core: str) -> int:
    return sum(character.isalnum() for character in core)


def may_hold_more_words(galley_core: str, model_core: str) -> bool:
    """Whether galley's core may hold more printed words than the model's
    (section 7): more commas, full stops, hyphens or en dashes between two
    letters or digits; more digits when it has two side by side (a lone
    digit is often a letter misread: "a3", "V1"); or a piece of digits and
    marker signs glued before or after two letters that the model's core
    lacks ("1%The")."""
    glued = _GLUED_PIECE.search(galley_core)
    return (
        len(_SEPARATOR.findall(galley_core)) > len(_SEPARATOR.findall(model_core))
        or (
            _DIGIT_RUN.search(galley_core) is not None
            and sum(c.isdigit() for c in galley_core)
            > sum(c.isdigit() for c in model_core)
        )
        or (glued is not None and glued.group() not in model_core)
    )


def glued_span(
    galley_core: str, model_answer: Answer, position: int, unpaired: frozenset[int]
) -> tuple[int, int] | None:
    """The first and last positions of the model's tokens that read the two
    printed words galley glued into one (section 7): the token at
    `position` and an unpaired one beside it, when galley's core has more
    letters and digits than the token alone and the two joined are more
    alike galley's than the token alone; None otherwise."""
    if _alphanumerics(galley_core) <= _alphanumerics(_core(model_answer, position)):
        return None
    forms = [token.form for token in model_answer.tokens]
    galley_form = comparison_form(galley_core)
    alone = alike(galley_form, forms[position])
    best = None
    for first, last in ((position - 1, position), (position, position + 1)):
        beside = first if first != position else last
        if beside not in unpaired:
            continue
        likeness = alike(galley_form, forms[first] + forms[last])
        if likeness > alone and (best is None or likeness > best[0]):
            best = (likeness, first, last)
    return None if best is None else (best[1], best[2])


# Section 7: a run of this many words or more that the page already holds
# is not put in again; one word, "the", is everywhere.
_LEAST_REPEATED = 2


# Section 7: a block part with at least this many unequal pairs whose mean
# likeness is below _LEAST_MEAN_ALIKE has its words out of place. Measured
# with the recorded answers on 19 November 2026: Kadesh page 14's note
# blocks 0.00 to 0.19, the six reference pages 0.36 to 0.93 but for page
# 27's rotated words, 0.22.
_LEAST_UNEQUAL = 3
_LEAST_MEAN_ALIKE = 0.3


def _out_of_place(
    reading: Sequence[GalleyToken], model_answer: Answer, pairs: Sequence[Pair]
) -> frozenset[str]:
    """The blocks whose words on the page are out of place against the
    model's: 3 unequal pairs or more, less than 0.3 alike on average."""
    likeness: dict[str, list[float]] = {}
    for pair in pairs:
        if pair.first is None or pair.second is None:
            continue
        token = reading[pair.first]
        model_form = model_answer.tokens[pair.second].form
        if token.place is not None and token.form != model_form:
            likeness.setdefault(token.place.block_id, []).append(
                alike(token.form, model_form)
            )
    return frozenset(
        block_id
        for block_id, values in likeness.items()
        if len(values) >= _LEAST_UNEQUAL
        and sum(values) / len(values) < _LEAST_MEAN_ALIKE
    )


def _forms(words: Sequence[str]) -> tuple[str, ...]:
    return tuple(token.form for word in words for token in tokens(word))


def _holds(forms: Sequence[str], run: tuple[str, ...]) -> bool:
    """Whether `forms` hold `run`, of two words or more, one after the
    other (section 7: a run the page already holds is not put in again)."""
    if len(run) < _LEAST_REPEATED:
        return False
    length = len(run)
    return any(
        tuple(forms[start : start + length]) == run
        for start in range(len(forms) - length + 1)
    )


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


def _replacement(
    galley_core: str, model_answer: Answer, position: int, unpaired: frozenset[int]
) -> tuple[str, int | None] | None:
    """The core that replaces galley's, from the model's token at
    `position`, and the unpaired model token it also takes when galley glued
    two words; None when the pair may hold more words on galley's side."""
    glued = glued_span(galley_core, model_answer, position, unpaired)
    if glued is not None:
        first, last = glued
        model_core = model_answer.text[
            model_answer.tokens[first].start : model_answer.tokens[last].end
        ]
        # The model's line break between the two words is one space, or
        # nothing after a hyphen ("non-" and "Libyan" are "non-Libyan").
        model_core = re.sub(r"\s+", " ", model_core).replace("- ", "-")
        # The space between the two words counts as one more mark.
        if (
            len(_SEPARATOR.findall(galley_core))
            > len(_SEPARATOR.findall(model_core)) + 1
        ):
            return None
        return cased(model_core, galley_core), first if first != position else last
    model_core = _core(model_answer, position)
    if may_hold_more_words(galley_core, model_core):
        return None
    return cased(model_core, galley_core), None


def _insertions(
    page_index: int,
    reading: Sequence[GalleyToken],
    model_answer: Answer,
    pairs: Sequence[Pair],
    consumed: frozenset[int],
    out_of_place: frozenset[str],
    second: _Second,
) -> tuple[tuple[float, Change], ...]:
    """The insertions of section 7, each with its place in the reading: the
    model's runs inside a note, less the tokens a replacement took, the
    digits, a run the page holds already and a block out of place."""
    reading_forms = tuple(token.form for token in reading)
    changes: list[tuple[float, Change]] = []
    for before, whole_run in _runs(pairs):
        run = tuple(position for position in whole_run if position not in consumed)
        after = _next_galley(pairs, before)
        if before is None or after is None or not _inside_note(reading, before, after):
            continue
        words = _gap_words(model_answer, run)
        if not words:
            continue
        if _holds(reading_forms, _forms(words)):
            _logger.info(
                "page %d: %r is already in galley's reading; not put in again",
                page_index,
                " ".join(words),
            )
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
        if place.block_id in out_of_place:
            continue
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
    return tuple(changes)


def _whole_word(
    reading: Sequence[GalleyToken],
    position: int,
    place: Place,
    model_form: str,
    galley_text: Mapping[Place, str],
    paired: Mapping[int, int],
) -> tuple[Place, str, Place | None]:
    """The place a replacement of galley's token at `position`, whose core
    is at `place`, covers, galley's core there for checks (a) to (c), and
    the place of the first half when it covers two: the token's own; or
    both halves of a word split at a line end, their cores joined without
    the hyphen, when the token is the second half, the first half is the
    token before, pairs with nothing, and joined with it is more alike the
    model's form (section 7)."""
    token = reading[position]
    head = token.first_half
    if (
        head is None
        or position == 0
        or reading[position - 1].place != head
        or position - 1 in paired
        or alike(reading[position - 1].form + token.form, model_form)
        <= alike(token.form, model_form)
    ):
        return place, galley_text[place], None
    return (
        Place(place.block_id, place.span_index, head.start, place.end),
        galley_text[head][:-1] + galley_text[place],
        head,
    )


def _halves(
    model_core: str, join: LineEndJoin, start: int, first: str, second: str
) -> str:
    """The model's word broken in capitals at a line end, with its hyphen,
    each half in the case of galley's half: "DINDORF-MÜLLER" against
    "Dirporr-" and "MCiuer" is "Dindorf-Müller" (section 7)."""
    cut = join.offset - start
    return cased(model_core[:cut], first) + "-" + cased(model_core[cut:], second)


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
    unpaired = frozenset(
        pair.second for pair in pairs if pair.first is None and pair.second is not None
    )
    out_of_place = _out_of_place(reading, model_answer, pairs)
    for block_id in sorted(out_of_place):
        _logger.info(
            "page %d: the words of block %s are out of place against the "
            "model's; no edit there",
            page_index,
            block_id,
        )
    changes: list[tuple[float, Change]] = []
    consumed: set[int] = set()
    paired = _paired(pairs)
    for pair in pairs:
        if pair.first is None or pair.second is None:
            continue
        token = reading[pair.first]
        model_form = model_answer.tokens[pair.second].form
        if (
            token.place is None
            or token.place.block_id in out_of_place
            or token.form == model_form
            or alike(token.form, model_form) < _LEAST_ALIKE
        ):
            continue
        place, galley_core, head = _whole_word(
            reading, pair.first, token.place, model_form, galley_text, paired
        )
        join = model_answer.joins.get(pair.second)
        if head is not None and join is None:
            # The model printed the word whole: galley's hyphen may be one
            # the word has; leave it alone (section 7).
            continue
        replacement = _replacement(galley_core, model_answer, pair.second, unpaired)
        if replacement is None:
            continue
        new_core, beside = replacement
        if head is not None and join is not None and join.capitals:
            new_core = _halves(
                _core(model_answer, pair.second),
                join,
                model_answer.tokens[pair.second].start,
                galley_text[head][:-1],
                galley_text[token.place],
            )
        if beside is not None:
            consumed.add(beside)
        changes.append(
            (
                pair.first,
                Change(
                    kind=ChangeKind.REPLACE,
                    page_index=page_index,
                    place=place,
                    text=new_core,
                    second_reading=second.replaced(pair.first)
                    if token.note_id is not None
                    else None,
                ),
            )
        )
    changes.extend(
        _insertions(
            page_index,
            reading,
            model_answer,
            pairs,
            frozenset(consumed),
            out_of_place,
            second,
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
        return _Second(present=False, paired=frozendict(), gaps=frozendict())
    notes = [
        position for position, token in enumerate(reading) if token.note_id is not None
    ]
    pairs = align(
        [reading[position].form for position in notes],
        [token.form for token in second_answer.tokens],
    )
    paired = frozendict(
        {
            notes[first]: _core(second_answer, second)
            for first, second in _paired(pairs).items()
        }
    )
    gaps = frozendict(
        {
            notes[before]: " ".join(_gap_words(second_answer, run))
            for before, run in _runs(pairs)
            if before is not None
        }
    )
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


def block_edits(
    block: Block, changes: Sequence[Change], model: str
) -> tuple[Edit, ...]:
    """The edits of one block from its changes (section 8): one edit for
    each word changed, in the order of the text, each `old` widened by
    neighbouring words of the span that no other change touches until it
    occurs once in the block's text as structure wrote it and as the edits
    before it leave it. A change no such `old` can hold is not proposed,
    and logged."""
    span_words = {index: _words(span.text) for index, span in enumerate(block.spans)}
    by_word = _by_word(changes, span_words)
    original = "".join(span.text for span in block.spans)
    spans = [span.text for span in block.spans]
    shift = dict.fromkeys(range(len(spans)), 0)
    edits = []
    for (span_index, first, last), word_changes in sorted(by_word.items()):
        words = span_words[span_index]
        text = block.spans[span_index].text
        start, end = words[first].start, words[last].end
        new_word = _changed_word(text[start:end], start, word_changes)
        if new_word == text[start:end]:
            continue
        changed = {
            index
            for key in by_word
            if key[0] == span_index
            for index in range(key[1], key[2] + 1)
        }
        bounds = _context(
            words, (first, last), changed, text, (original, "".join(spans))
        )
        first_change = word_changes[0]
        if bounds is None:
            _logger.info(
                "page %d, block %s: %r occurs more than once however widened; "
                "not proposed",
                first_change.page_index,
                block.id,
                text[start:end],
            )
            continue
        low, high = bounds
        old = text[words[low].start : words[high].end]
        new = text[words[low].start : start] + new_word + text[end : words[high].end]
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


def _by_word(
    changes: Sequence[Change], span_words: Mapping[int, Sequence[_Word]]
) -> dict[tuple[int, int, int], list[Change]]:
    """The changes grouped by the whitespace words they touch: by span, and
    first and last word of the span, one word but for a replacement of
    both halves of a word split at a line end (section 7). Changes whose
    words overlap are in one group."""
    ranges = []
    for change in changes:
        words = span_words[change.place.span_index]
        first = next(
            index
            for index, word in enumerate(words)
            if word.start <= change.place.start < word.end
        )
        last = next(
            index
            for index in range(first, len(words))
            if change.place.end <= words[index].end
        )
        ranges.append((change.place.span_index, first, last, change))
    merged: list[tuple[int, int, int, list[Change]]] = []
    for span_index, first, last, change in sorted(ranges, key=lambda r: r[:3]):
        if merged and merged[-1][0] == span_index and first <= merged[-1][2]:
            _, low, high, group = merged[-1]
            merged[-1] = (span_index, low, max(last, high), [*group, change])
        else:
            merged.append((span_index, first, last, [change]))
    return {(span, low, high): group for span, low, high, group in merged}


def _context(
    words: Sequence[_Word],
    positions: tuple[int, int],
    changed: set[int],
    text: str,
    texts: tuple[str, str],
) -> tuple[int, int] | None:
    """The first and last word of `old` around the words `positions`, first
    and last, of the span `text`, widened alternately after and before,
    never over a word another change touches, until `old` occurs once in
    each of `texts`, the block's text as structure wrote it and as edited
    so far; None when it never does."""
    low, high = positions
    toward_end = True
    while True:
        old = text[words[low].start : words[high].end]
        if all(only_occurrence(block_text, old) is not None for block_text in texts):
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
