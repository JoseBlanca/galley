"""The page number at either end of a head line (spec section 3): its first
or last word, or a run of digit words there that the OCR split ("5 1")."""

import re
from collections.abc import Sequence
from dataclasses import dataclass

from galley.structure._measures import arabic_value, is_roman_form

# Spec section 3: a word of digits, the last of a run possibly followed by
# "." or ",".
_DIGIT_WORD = re.compile(r"[0-9]+[.,]?")
# Spec section 3: a head number counts when its value plus the offset gives
# the page index within 2 (Stubbs' offset is 17 on pages 19 to 51 and 21
# after; its heads there are alike by their letters).
_HEAD_NUMBER_SLACK = 2
# Spec sections 3 and 14: the words that start a chapter label.
CHAPTER_LABEL_WORDS = frozenset(
    {"chapter", "chapitre", "essay", "part", "partie", "book", "livre"}
)
# Spec section 3, the head of a short section: a word that may be a page
# number, misread or not.
_NUMBER_LIKE = re.compile(r"[0-9ivxlcdmIVXLCDM]{1,4}[.,]?")


@dataclass(frozen=True, slots=True)
class EndNumber:
    """Words at one end of a head line that may be its page number: the
    positions of the first and last (inclusive), and their texts joined
    without spaces."""

    first: int
    last: int
    text: str


def without(candidate: EndNumber, texts: tuple[str, ...]) -> tuple[str, ...]:
    """`texts`, the line's words, without the candidate's."""
    return texts[: candidate.first] + texts[candidate.last + 1 :]


def _run_length(texts: tuple[str, ...]) -> int:
    """The number of digit words `texts` starts with, at least 1."""
    length = 0
    while length < len(texts) and _DIGIT_WORD.fullmatch(texts[length]):
        length += 1
    return max(length, 1)


def end_numbers(texts: tuple[str, ...]) -> tuple[EndNumber, ...]:
    """The words at the start and at the end of a head line, `texts`, that
    may be its page number: a run of digit words joined, or else the one
    end word; one candidate when they meet. No words give none."""
    if not texts:
        return ()
    lead = _run_length(texts)
    start = EndNumber(0, lead - 1, "".join(texts[:lead]))
    trail = _run_length(texts[::-1])
    end = EndNumber(len(texts) - trail, len(texts) - 1, "".join(texts[-trail:]))
    if end.first <= start.last:
        return (start,)
    return (start, end)


def arabic_number(candidate: EndNumber) -> int | None:
    """The value of a candidate that is an arabic page-number form."""
    return arabic_value(candidate.text)


def is_roman_number(candidate: EndNumber) -> bool:
    """Whether a candidate of one word is a roman page-number form."""
    return candidate.first == candidate.last and is_roman_form(candidate.text)


def is_confirmed(page_index: int, value: int | None, offset: int | None) -> bool:
    """Whether an arabic head number `value` lies where the book's head
    offset puts it: its value plus `offset` within 2 of `page_index`."""
    return (
        value is not None
        and offset is not None
        and abs(value + offset - page_index) <= _HEAD_NUMBER_SLACK
    )


def is_number_like(text: str) -> bool:
    """Whether `text` is number-like, as the head of a short section's first
    or last word is (spec section 3): 1 to 4 characters, each a digit or
    one of the letters i, v, x, l, c, d, m in either case, with at most one
    "." or "," after them ("vi", "vlil", "xiv.", "47")."""
    return _NUMBER_LIKE.fullmatch(text) is not None


def starts_with_chapter_label_word(texts: Sequence[str]) -> bool:
    """Whether the first of a line's words `texts` is a chapter label word
    (spec section 3): one of `CHAPTER_LABEL_WORDS` in any case, with ".",
    ",", ":" or ";" after it or not: "CHAPTER", "Book." but not
    "Book-land"."""
    return bool(texts) and texts[0].rstrip(".,:;").lower() in CHAPTER_LABEL_WORDS
