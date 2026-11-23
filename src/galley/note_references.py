"""Note references glued to a word (structure spec section 11,
"Candidates"; architecture section 12).

structure looks for a note's reference in the words of the body with
`glued_reference`, and extract, under `ocr = "redo"`, puts back the layer's
reference where Tesseract lost it only when the layer's word has one by the
same test (extract spec section 9), so that the two read a reference alike.
Moved from `structure/_markers.py` on 19 November 2026.
"""

import re
import unicodedata
from enum import StrEnum
from typing import Final, NamedTuple

__all__ = [
    "PUNCTUATION",
    "Reference",
    "ReferenceForm",
    "after_last_letter",
    "endnote_reference",
    "glued_reference",
    "is_punctuation",
]


class ReferenceForm(StrEnum):
    """The kinds of a note reference in the text (structure spec
    section 11, "References"): a number glued after a word, a bracketed number, or a
    sign."""

    GLUED = "glued"
    BRACKETED = "bracketed"
    SIGN = "sign"


class Reference(NamedTuple):
    """A candidate note reference in a word: what comes `before` it in the
    word ("land" for "land3."), the `reference` itself ("3"), what comes
    `after` it ("."), its `form`, and the number it reads, digit-like
    letters inside brackets read as digits, or None (a sign)."""

    before: str
    reference: str
    after: str
    form: ReferenceForm
    value: int | None


# Structure spec section 11, "References". The patterns take as
# punctuation a character that is neither a letter, a digit, "_" nor white
# space; `is_punctuation` then keeps only Unicode's punctuation, so that "£2"
# (Domesday page 83, "of this £2 is due") is no candidate.
PUNCTUATION: Final[str] = r"[^\w\s]"
# A letter, any punctuation, 1 to 3 digits, then only punctuation
# ("land3.", "Kadesh,12", "causa)27.", "12s.2").
_GLUED_AFTER_A_LETTER = re.compile(
    rf"(?P<before>.*[^\W\d_]{PUNCTUATION}*)(?P<reference>[0-9]{{1,3}})"
    rf"(?P<after>{PUNCTUATION}*)"
)
# Punctuation, 1 to 3 digits and only punctuation after, with no letter
# (Kadesh page 10's ";13"); a number with punctuation after it only, "13,",
# is none.
_GLUED_TO_PUNCTUATION = re.compile(
    rf"(?P<before>{PUNCTUATION}*)(?P<reference>[0-9]{{1,3}})"
    rf"(?P<after>{PUNCTUATION}*)"
)
# The abbreviations a number follows in citations ("p.12", "vol.3"): a
# word that starts with one of them and has no other letter is no
# candidate.
_CITATION_ABBREVIATIONS = frozenset(
    [
        "c",
        "p",
        "pp",
        "f",
        "ff",
        "n",
        "nr",
        "no",
        "vol",
        "ch",
        "cap",
        "art",
        "l",
        "ll",
        "q",
        "a",
        "t",
        "v",
        "s",
        "d",
        "m",
    ]
)
_CITATION = re.compile(rf"{PUNCTUATION}*(?P<letters>[^\W\d_]+){PUNCTUATION}*")
# Structure spec section 12, "The candidates of endnotes": 1 to 3 digits
# glued after a number of 4 digits, a year ("1911.34"), or after a closing
# bracket ("(61).29", "5)16"), with only the punctuation that ends a
# sentence, a clause or a quotation between them; a dash is none of it, so
# "1914-18" and "(612-19)" are no candidates, and a time "10.35" has 2
# digits before.
_SENTENCE_PUNCTUATION = "[.,;:!?)\\]'\"\u2019\u201d]"
_GLUED_AFTER_A_NUMBER = re.compile(
    rf"(?P<before>(?:(?:.*[^0-9])?[0-9]{{4}}{_SENTENCE_PUNCTUATION}+|.*[)\]]"
    rf"{_SENTENCE_PUNCTUATION}*))(?P<reference>[0-9]{{1,3}})"
    rf"(?P<after>{PUNCTUATION}*)"
)
# For endnotes only: a reference followed straight by a dash and a word,
# "river20—and"; the dash is an em or en dash, a hyphen is none.
_DASH_AND_WORD = re.compile(r"(?P<head>.*?[0-9])(?P<tail>[\u2014\u2013][^\W\d_].*)")


def is_punctuation(text: str) -> bool:
    """Whether every character of `text` is punctuation in Unicode's sense
    (category P): "," ")" "'" "/", not "£" or "^"."""
    return all(unicodedata.category(character).startswith("P") for character in text)


def after_last_letter(text: str) -> str:
    """What follows the last letter of `text`, which holds one ("," for
    "Kadesh,")."""
    return text[max(position for position, c in enumerate(text) if c.isalpha()) + 1 :]


def glued_reference(word: str) -> Reference | None:
    """The number glued to `word` as a note reference, by structure spec
    section 11, "Candidates", or None: a letter, any punctuation or none, 1
    to 3 digits and only punctuation ("land3." gives ("land", "3", "."),
    "Kadesh,12" gives ("Kadesh,", "12", "")), unless the word starts with a
    citation's abbreviation and has no other letter ("p.12"); or
    punctuation, 1 to 3 digits and only punctuation, with no letter
    (";13")."""
    return _glued(word, citations=True)


def endnote_reference(word: str) -> Reference | None:
    """The number glued to `word` as a reference to an endnote, by
    structure spec section 12, "The candidates of endnotes", or None: a
    glued reference without the citation exclusion ("art.27"); a number of
    4 digits or a closing bracket, then sentence punctuation, then 1 to 3
    digits and only punctuation ("1911.34" gives ("1911.", "34", ""),
    "(61).29" gives ("(61).", "29", "")), so that a time "10.35" is none;
    and either of these followed by a dash and a word ("river20—and" gives
    ("river", "20", "—and"))."""
    dashed = _DASH_AND_WORD.fullmatch(word)
    if dashed is not None:
        head = _endnote_glued(dashed.group("head"))
        return (
            None
            if head is None
            else head._replace(after=head.after + dashed.group("tail"))
        )
    return _endnote_glued(word)


def _endnote_glued(word: str) -> Reference | None:
    """A glued reference of `word` with no citation exclusion, or one after
    a number of 4 digits or a closing bracket and sentence punctuation."""
    glued = _glued(word, citations=False)
    if glued is not None:
        return glued
    match = _GLUED_AFTER_A_NUMBER.fullmatch(word)
    if match is None or not is_punctuation(match.group("after")):
        return None
    return Reference(
        match.group("before"),
        match.group("reference"),
        match.group("after"),
        ReferenceForm.GLUED,
        int(match.group("reference")),
    )


def _glued(word: str, *, citations: bool) -> Reference | None:
    """The glued reference of `word` by `glued_reference`, with the citation
    exclusion only when `citations` is true."""
    after_letter = _GLUED_AFTER_A_LETTER.fullmatch(word)
    if after_letter is not None and not (
        is_punctuation(after_last_letter(after_letter.group("before")))
        and is_punctuation(after_letter.group("after"))
    ):
        return None
    if after_letter is not None:
        citation = _CITATION.fullmatch(after_letter.group("before"))
        if (
            citations
            and citation is not None
            and citation.group("letters").lower() in _CITATION_ABBREVIATIONS
        ):
            return None
        match = after_letter
    else:
        match = _GLUED_TO_PUNCTUATION.fullmatch(word)
        if (
            match is None
            or not match.group("before")
            or not is_punctuation(match.group("before") + match.group("after"))
        ):
            return None
    return Reference(
        match.group("before"),
        match.group("reference"),
        match.group("after"),
        ReferenceForm.GLUED,
        int(match.group("reference")),
    )
