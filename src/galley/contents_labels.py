"""The number labels of a printed contents (structure spec section 30,
rule 12): a number of 1 or 2 digits with ".", "7.", or a well-formed roman
numeral in capitals with ".", "IV.". structure infers a lost label by
them and the fidelity check admits an inferred one by them, so the two
read a label alike."""

import itertools
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import assert_never


class LabelStyle(StrEnum):
    """How a number label writes its value."""

    DIGITS = "digits"
    ROMAN = "roman"


@dataclass(frozen=True, slots=True)
class NumberLabel:
    """A number label's style and value, from 1."""

    style: LabelStyle
    value: int


_DIGITS = re.compile(r"[0-9]{1,2}\.")
# A well-formed roman numeral in capitals, 1 to 3999, with ".".
_ROMAN = re.compile(
    r"(?=[MDCLXVI])M{0,3}(CM|CD|D?C{0,3})(XC|XL|L?X{0,3})(IX|IV|V?I{0,3})\."
)
_ROMAN_VALUES = (
    (1000, "M"),
    (900, "CM"),
    (500, "D"),
    (400, "CD"),
    (100, "C"),
    (90, "XC"),
    (50, "L"),
    (40, "XL"),
    (10, "X"),
    (9, "IX"),
    (5, "V"),
    (4, "IV"),
    (1, "I"),
)


def _roman(value: int) -> str:
    letters = []
    for part, numeral in _ROMAN_VALUES:
        while value >= part:
            letters.append(numeral)
            value -= part
    return "".join(letters)


def label_text(style: LabelStyle, value: int) -> str:
    """The label of `value`, from 1, in `style`: "7." or "VII."."""
    match style:
        case LabelStyle.DIGITS:
            return f"{value}."
        case LabelStyle.ROMAN:
            return f"{_roman(value)}."
        case _:
            assert_never(style)


def _roman_value(numeral: str) -> int:
    """The value of a well-formed roman numeral in capitals."""
    value = 0
    rest = numeral
    for part, letters in _ROMAN_VALUES:
        while rest.startswith(letters):
            value += part
            rest = rest[len(letters) :]
    return value


def number_label(label: str | None) -> NumberLabel | None:
    """The style and value of a number label, None for any other label
    and for None."""
    if label is None:
        return None
    if _DIGITS.fullmatch(label):
        value = int(label[:-1])
        return NumberLabel(LabelStyle.DIGITS, value) if value > 0 else None
    if _ROMAN.fullmatch(label):
        return NumberLabel(LabelStyle.ROMAN, _roman_value(label[:-1]))
    return None


def contents_runs(pages: Iterable[int]) -> tuple[tuple[int, ...], ...]:
    """The contents runs of the contents pages `pages`, page indices from
    0: each run its consecutive pages, in order (structure spec section
    30, "Terms")."""
    runs: list[tuple[int, ...]] = []
    for page_index in sorted(frozenset(pages)):
        if runs and runs[-1][-1] == page_index - 1:
            runs[-1] = (*runs[-1], page_index)
        else:
            runs.append((page_index,))
    return tuple(runs)


def _gap_labels(
    labels: Sequence[str | None],
    levels: Sequence[int],
    gap: range,
    level: int,
    first: NumberLabel,
) -> tuple[tuple[int, str], ...]:
    """The labels of the entries of `gap`, from `first` up, when each of
    them has no label and is at `level`; none otherwise."""
    if not all(
        labels[position] is None and levels[position] == level for position in gap
    ):
        return ()
    return tuple(
        (position, label_text(first.style, value))
        for value, position in enumerate(gap, start=first.value)
    )


def _leading_labels(
    labels: Sequence[str | None],
    levels: Sequence[int],
    first_labelled: tuple[int, NumberLabel],
) -> tuple[tuple[int, str], ...]:
    """The labels of the N−1 entries just before the run's first number
    label N, `first_labelled` with its position, when they fit."""
    position, first = first_labelled
    if position < first.value - 1:
        return ()
    return _gap_labels(
        labels,
        levels,
        range(position - (first.value - 1), position),
        levels[position],
        NumberLabel(first.style, 1),
    )


def inferred_labels(
    labels: Sequence[str | None], levels: Sequence[int]
) -> frozendict[int, str]:
    """The labels rule 12 of structure spec section 30 infers for the
    entries of one contents run, whose labels (None for none) and depths
    are `labels` and `levels`, by position: the N−M−1 entries without a
    label between number labels M and N of one style at one depth, all at
    that depth, get M+1 to N−1; the N−1 entries without a label just
    before the run's first number label N, at its depth, get 1 to N−1."""
    labelled = tuple(
        (position, number)
        for position, label in enumerate(labels)
        if (number := number_label(label)) is not None
    )
    leading = _leading_labels(labels, levels, labelled[0]) if labelled else ()
    between = tuple(
        label
        for (before, low), (after, high) in itertools.pairwise(labelled)
        if low.style is high.style
        and levels[before] == levels[after]
        and high.value - low.value == after - before
        for label in _gap_labels(
            labels,
            levels,
            range(before + 1, after),
            levels[before],
            NumberLabel(low.style, low.value + 1),
        )
    )
    return frozendict(leading + between)
