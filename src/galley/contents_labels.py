"""The number labels of a printed contents (structure spec section 30,
rule 12): a number of 1 or 2 digits with ".", "7.", or a well-formed roman
numeral in capitals with ".", "IV.". structure infers a lost label by
them and the fidelity check admits an inferred one by them, so the two
read a label alike."""

import re
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
