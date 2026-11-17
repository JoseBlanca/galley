"""Measures of words, lines and regions that structure's rules share.

Positions are PDF points, origin at the top left of the page (architecture
section 7).
"""

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from galley.body_measures import commonest
from galley.model import Box, Line, Region, Removal, RemovalReason, Word

# Spec section 6: a region of fewer lines takes its box's sides as edges.
_LINES_FOR_COMMONEST_EDGES = 5

# Spec section 1: a page-number form is 1 to 3 digits, or a well-formed
# roman numeral in lower case, with at most one "." or "," after it.
_ARABIC_FORM = re.compile(r"([0-9]{1,3})[.,]?")
_ROMAN_FORM = re.compile(
    r"(?=[ivxlcdm])m{0,3}(cm|cd|d?c{0,3})(xc|xl|l?x{0,3})(ix|iv|v?i{0,3})[.,]?"
)


def region_words(region: Region) -> tuple[Word, ...]:
    return tuple(word for line in region.lines for word in line.words)


def box_of(boxes: Sequence[Box]) -> Box:
    """The smallest box that holds every box of `boxes`, which is not empty."""
    return Box(
        min(box.x0 for box in boxes),
        min(box.top for box in boxes),
        max(box.x1 for box in boxes),
        max(box.bottom for box in boxes),
    )


def words_box(words: Sequence[Word]) -> Box:
    return box_of(tuple(word.box for word in words))


def words_text(words: Iterable[Word]) -> str:
    """The texts of `words` joined by one space."""
    return " ".join(word.text for word in words)


def words_removal(
    page_index: int, words: Sequence[Word], reason: RemovalReason
) -> Removal:
    """One removal of `words`, which are not none, joined by one space, with
    the smallest box that holds them."""
    return Removal(
        page_index=page_index,
        box=words_box(words),
        text=words_text(words),
        reason=reason,
    )


def has_letter_or_digit(text: str) -> bool:
    """Whether `text` holds a character for which str.isalnum is true
    (layout section 1)."""
    return any(character.isalnum() for character in text)


def line_has_letter_or_digit(line: Line) -> bool:
    return any(has_letter_or_digit(word.text) for word in line.words)


def letters(text: str) -> str:
    """The letters of `text` in lower case, everything else dropped."""
    return "".join(character for character in text.lower() if character.isalpha())


def arabic_value(text: str) -> int | None:
    """The number of an arabic page-number form ("47", "47."), or None when
    `text` is not one."""
    match = _ARABIC_FORM.fullmatch(text)
    return int(match.group(1)) if match is not None else None


def is_roman_form(text: str) -> bool:
    """Whether `text` is a well-formed roman numeral in lower case, with at
    most one "." or "," after it ("xiv", not "Ill" or "iiii")."""
    return _ROMAN_FORM.fullmatch(text) is not None


def is_page_number_form(text: str) -> bool:
    """Whether `text` is a page-number form (spec section 1)."""
    return arabic_value(text) is not None or is_roman_form(text)


@dataclass(frozen=True, slots=True)
class Edges:
    """The left and right edges of a region or of a page's body column, in
    points from the left of the page."""

    left: float
    right: float

    @property
    def width(self) -> float:
        return self.right - self.left

    @property
    def middle(self) -> float:
        return (self.left + self.right) / 2


def is_short(region: Region) -> bool:
    """Whether a region has too few lines for commonest edges, fewer than 5
    (spec section 6): its edges are then its box's sides."""
    return len(region.lines) < _LINES_FOR_COMMONEST_EDGES


def region_edges(region: Region) -> Edges:
    """The commonest left and right sides of the region's lines, or, with
    fewer than 5 lines, the sides of its box (spec section 6)."""
    if is_short(region):
        return Edges(region.box.x0, region.box.x1)
    return Edges(
        commonest(line.box.x0 for line in region.lines),
        commonest(line.box.x1 for line in region.lines),
    )


def middle(box: Box) -> float:
    """The horizontal middle of a box."""
    return (box.x0 + box.x1) / 2


def is_hyphen_first_part(text: str) -> bool:
    """Whether a word can be the first part of a hyphen join: it ends with
    the ASCII hyphen-minus after a letter or digit (spec section 5)."""
    return text.endswith("-") and text[:-1][-1:].isalnum()


# Spec section 5: a digit of the hyphen rule is an ASCII digit.
ASCII_DIGITS = frozenset("0123456789")


def is_digit_before_hyphen(text: str) -> bool:
    """Whether `text` ends with a hyphen after an ASCII digit, "1830-"."""
    return text.endswith("-") and text[:-1][-1:] in ASCII_DIGITS


def is_number_before_word(first: str, second: str) -> bool:
    """Whether `first`, the last word of a line, ends with a hyphen after an
    ASCII digit and `second`, the first word of the next, starts with a
    letter (`str.isalpha`): "136-39-" "Bryce,", which are not joined (spec
    section 5), unlike a range, "1830-" "40"."""
    return is_digit_before_hyphen(first) and second[:1].isalpha()
