"""List markers (structure spec section 29, "Terms"): how a word or a list
item's label reads as the marker of a printed list, and whether one marker
follows another.

structure finds lists with these readings, markdown writes a list's items
by them, and the fidelity check compares the numbers Pandoc shows with
them, so the three read a marker alike.
"""

import re
from dataclasses import dataclass
from enum import StrEnum

# Structure spec section 29, "Terms": the dashes, alone or glued before a
# letter, and the bullets.
DASHES = frozenset("—–")
BULLETS = frozenset("•·▪■●◦○‣")
# A number of 1 or 2 digits, a letter, or a roman numeral, followed by "."
# or ")" or between round brackets.
_VALUED = re.compile(r"(?P<open>\(?)(?P<value>[0-9]{1,2}|[a-zA-Z]+)(?P<close>[.)])")
# A roman numeral i to xv in lower case: its tens, an "x" or none, and its
# units.
_ROMAN = re.compile(r"(?P<tens>x?)(?P<units>ix|iv|v?i{0,3})")
_ROMAN_UNITS = frozendict(
    {"": 0, "i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5}
    | {"vi": 6, "vii": 7, "viii": 8, "ix": 9}
)
_ROMAN_TEN = 10
# Structure spec section 29, "Terms": a roman numeral marker is i to xv.
_ROMAN_MAX = 15
_ALPHABET = "abcdefghijklmnopqrstuvwxyz"
# Structure spec section 29, rule 1: the first value of a list of numbers,
# letters or roman numerals.
FIRST_VALUE = 1


class MarkerKind(StrEnum):
    """What a list marker is (structure spec section 29, "Terms")."""

    DASH = "dash"
    BULLET = "bullet"
    NUMBER = "number"
    LETTER = "letter"
    ROMAN = "roman"


@dataclass(frozen=True, slots=True)
class ListMarker:
    """A list marker as one reading of a word (structure spec section 29,
    "Terms"): `text` the marker as printed ("—", "1.", "(b)"); `kind`;
    `form` the dash or bullet itself, or the marker with its value written
    as "1", "a", "A", "i" or "I" ("(b)" has the form "(a)", "iv." the form
    "i."), so that two markers of one form also share their letters' case;
    and `value` the number, the letter's place in the alphabet or the
    numeral's value, None for a dash or a bullet."""

    text: str
    kind: MarkerKind
    form: str
    value: int | None


def _roman_value(letters: str) -> int | None:
    """The value of a roman numeral i to xv in lower case, None when
    `letters` is none."""
    match = _ROMAN.fullmatch(letters)
    if match is None or not letters:
        return None
    value = _ROMAN_TEN * len(match.group("tens")) + _ROMAN_UNITS[match.group("units")]
    return value if value <= _ROMAN_MAX else None


def marker_readings(word: str) -> tuple[ListMarker, ...]:
    """The readings of `word` as a list marker, none when it is not one: a
    dash alone or glued before a letter ("—The" reads as "—"), a bullet
    alone, or a number, letter or roman numeral with its brackets or sign.
    A word of the letters i, v and x only, in one case, reads both as a
    roman numeral and, when it is one letter, as a letter, the numeral
    first; the list around it decides which it is (`follows`)."""
    if word[:1] in DASHES and (len(word) == 1 or word[1:2].isalpha()):
        return (ListMarker(word[0], MarkerKind.DASH, word[0], None),)
    if word in BULLETS:
        return (ListMarker(word, MarkerKind.BULLET, word, None),)
    match = _VALUED.fullmatch(word)
    if match is None or (match.group("open"), match.group("close")) == ("(", "."):
        return ()
    opening = str(match.group("open"))
    value = str(match.group("value"))
    closing = str(match.group("close"))
    readings: list[ListMarker] = []

    def form(placeholder: str) -> str:
        return opening + placeholder + closing

    if value.isdigit():
        readings.append(ListMarker(word, MarkerKind.NUMBER, form("1"), int(value)))
    if value.islower() or value.isupper():
        upper = value.isupper()
        roman = _roman_value(value.lower())
        if roman is not None:
            readings.append(
                ListMarker(word, MarkerKind.ROMAN, form("I" if upper else "i"), roman)
            )
        if len(value) == 1 and value.isalpha():
            readings.append(
                ListMarker(
                    word,
                    MarkerKind.LETTER,
                    form("A" if upper else "a"),
                    _ALPHABET.index(value.lower()) + 1,
                )
            )
    return tuple(readings)


def starts_a_list(marker: ListMarker) -> bool:
    """Whether `marker` can start a list (structure spec section 29, rule
    1): a dash, a bullet, or the first value of its kind."""
    return marker.value in {None, FIRST_VALUE}


def follows(marker: ListMarker, before: ListMarker) -> bool:
    """Whether `marker` follows `before`, the marker of the item before
    (structure spec section 29, rule 3): the same kind and form and, for a
    number, a letter or a roman numeral, the next value."""
    return (
        marker.kind is before.kind
        and marker.form == before.form
        and (
            marker.value is None
            or (before.value is not None and marker.value == before.value + 1)
        )
    )


def is_bulleted(marker: ListMarker) -> bool:
    """Whether a list of `marker` is a bullet list in the EPUB: a dash or a
    bullet (structure spec section 31)."""
    return marker.kind in {MarkerKind.DASH, MarkerKind.BULLET}
