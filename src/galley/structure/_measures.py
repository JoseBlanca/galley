"""Measures of words, lines and regions that structure's rules share.

Positions are PDF points, origin at the top left of the page (architecture
section 7).
"""

import bisect
import re
import statistics
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from galley.model import Box, Line, Region, Word

# layout section 3, measured: body lines start within 2.2 pt of the edge on
# 99% of Haskins' lines, so the commonest edge counts the edges within 2 pt.
_COMMONEST_EDGE_PT = 2
# Spec section 6: a region of fewer lines takes its box's sides as edges.
_LINES_FOR_COMMONEST_EDGES = 5

# Spec section 1: a page-number form is 1 to 3 digits, or a well-formed
# roman numeral in lower case, with at most one "." or "," after it.
_ARABIC_FORM = re.compile(r"([0-9]{1,3})[.,]?")
_ROMAN_FORM = re.compile(
    r"(?=[ivxlcdm])m{0,3}(cm|cd|d?c{0,3})(xc|xl|l?x{0,3})(ix|iv|v?i{0,3})[.,]?"
)


def word_height(word: Word) -> float:
    """The height of a word's box, in points."""
    return word.box.bottom - word.box.top


def median_word_height(words: Iterable[Word]) -> float:
    """The median height of `words`, in points; 0 for no word."""
    heights = tuple(word_height(word) for word in words)
    return statistics.median(heights) if heights else 0.0


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


def commonest(edges: Iterable[float]) -> float:
    """The commonest of `edges` (layout sections 1 and 3): each edge rounded to the
    point, the value with the most edges within 2 pt of it, the smallest
    on a tie. `edges` is not empty."""
    rounded = sorted(round(edge) for edge in edges)
    best_value = rounded[0]
    best_count = 0
    for value in sorted(set(rounded)):
        count = bisect.bisect_right(
            rounded, value + _COMMONEST_EDGE_PT
        ) - bisect.bisect_left(rounded, value - _COMMONEST_EDGE_PT)
        if count > best_count:
            best_value, best_count = value, count
    return float(best_value)


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


# Spec section 5: the apostrophes a key keeps, and after which a French
# elision's word is looked up.
APOSTROPHES = ("'", "’")


def _kept_in_key(character: str) -> bool:
    return character.isalnum() or character == "-" or character in APOSTROPHES


def word_key(text: str) -> str:
    """The key of a word for the hyphen rule (spec section 5): lower case,
    with the characters that are not letters, digits, hyphens or
    apostrophes stripped from both ends."""
    lowered = text.lower()
    start = 0
    end = len(lowered)
    while start < end and not _kept_in_key(lowered[start]):
        start += 1
    while end > start and not _kept_in_key(lowered[end - 1]):
        end -= 1
    return lowered[start:end]


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
