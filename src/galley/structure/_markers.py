"""The marker of a note and what it reads as a number (spec section 11,
"The marker of a note" and "Its value"), and the book's marker form
(section 1)."""

import re
import unicodedata
from collections import Counter
from collections.abc import Iterable
from enum import StrEnum
from typing import NamedTuple

# Spec section 11, "Its value": the letters the OCR gives for digits, read
# as those digits; inside brackets also "a" for 2 and "t" for 1.
_DIGIT_LIKE = frozendict(
    {
        **{letter: "1" for letter in "ilI|!J"},
        "o": "0",
        "O": "0",
        "s": "5",
        "S": "5",
        "z": "2",
        "Z": "2",
    }
)
_DIGIT_LIKE_IN_BRACKETS = frozendict({**_DIGIT_LIKE, "a": "2", "t": "1"})

# Spec section 11, "The marker of a note": 1 to 3 digits, with or without
# a "." after them ("8", "291.").
_DIGITS_FORM = re.compile(r"[0-9]{1,3}\.?")
# 1 to 3 digits glued to a word that starts with a capital or a quotation
# mark ("13The", Kadesh).
_GLUED_FORM = re.compile(r"([0-9]{1,3})([A-Z\"'“‘’«].*)")
# A bracketed marker: 1 or 2 letters or digits followed by ")", "]", "}"
# or "J", with "(", "[" or "{" before them or not, and an optional "."
# after ("(3)", "(t)", "U)", "(3J").
_BRACKETED_FORM = re.compile(r"[(\[{]?([A-Za-z0-9]{1,2})[)\]}J]\.?")
# Or a word of at most 4 characters, with at most 2 letters or digits,
# that starts with an opening bracket or ends with a closing one
# (Mariéjol's damaged "(4", "i»)", "(*)").
_LOOSE_BRACKETED_MAX_CHARACTERS = 4
_LOOSE_BRACKETED_MAX_ALNUM = 2
_OPENING_BRACKETS = "([{"
_CLOSING_BRACKETS = ")]}"
# 1 or 2 signs among * ^ • † ‡ § » > ' ".
_SIGNS = r"[*^•†‡§»>'\"]{1,2}"
_SIGNS_FORM = re.compile(_SIGNS)
# In an endnote section, 1 to 3 digits followed by "." or "-", where "I",
# "l", "!" and "o" count as digits ("I39-", "!6o."); at least one is a
# digit, so that the word "I." is no marker.
_ENDNOTE_FORM = re.compile(r"(?=[Il!o]*[0-9])[0-9Il!o]{1,3}[.\-]")


class MarkerForm(StrEnum):
    """The forms of a note's marker that a book's notes share (spec section
    1, the book's marker form): digits, bracketed or a sign."""

    DIGITS = "digits"
    BRACKETED = "bracketed"
    SIGN = "sign"


class NoteMarker(NamedTuple):
    """The marker of a note's first word: `marker` as the OCR read it
    ("13", "(t)", "291."), `rest` what follows it in the word ("The" for
    "13The", else ""), and `value` the number it reads, digit-like letters
    read as digits, or None (a sign)."""

    marker: str
    rest: str
    value: int | None


def read_number(text: str, *, in_brackets: bool = False) -> int | None:
    """The number `text`, which holds only letters and digits, reads once
    the letters the OCR gives for digits are read as those digits ("l3"
    reads 13; inside brackets "a" reads 2 and "t" 1); None when a
    character is neither or `text` is empty."""
    table = _DIGIT_LIKE_IN_BRACKETS if in_brackets else _DIGIT_LIKE
    digits = "".join(
        character
        if character.isascii() and character.isdigit()
        else table.get(character, "")
        for character in text
    )
    if not text or len(digits) != len(text):
        return None
    return int(digits)


def _bracketed(word: str) -> NoteMarker | None:
    match = _BRACKETED_FORM.fullmatch(word)
    if match is not None:
        return NoteMarker(word, "", read_number(match.group(1), in_brackets=True))
    alnum = "".join(character for character in word if character.isalnum())
    if (
        len(word) <= _LOOSE_BRACKETED_MAX_CHARACTERS
        and len(alnum) <= _LOOSE_BRACKETED_MAX_ALNUM
        and (word[:1] in _OPENING_BRACKETS or word[-1:] in _CLOSING_BRACKETS)
        and word
    ):
        return NoteMarker(word, "", read_number(alnum, in_brackets=True))
    return None


def note_marker(word: str, *, endnote: bool = False) -> NoteMarker | None:
    """The marker of a note whose first word is `word`, by the forms of spec
    section 11, or None when the word has none of them: digits ("8",
    "291."), digits glued to a capitalised word ("13The": marker "13",
    rest "The"), a bracketed marker ("(3)", "(t)", "U)", "(3J"), or 1 or 2
    signs ("*"). With `endnote`, also the endnote form, digits followed by
    "." or "-" where "I", "l", "!" and "o" count as digits ("I39-")."""
    if _DIGITS_FORM.fullmatch(word):
        return NoteMarker(word, "", int(word.rstrip(".")))
    glued = _GLUED_FORM.fullmatch(word)
    if glued is not None:
        return NoteMarker(glued.group(1), glued.group(2), int(glued.group(1)))
    bracketed = _bracketed(word)
    if bracketed is not None:
        return bracketed
    if _SIGNS_FORM.fullmatch(word):
        return NoteMarker(word, "", None)
    return endnote_marker(word) if endnote else None


# Spec section 11: 1 or 2 signs glued to a word that starts with a capital
# ("'There", Kadesh page 8), a marker only of a note started by its indent.
_GLUED_SIGNS_FORM = re.compile(rf"({_SIGNS})([A-Z].*)")


def glued_sign_marker(word: str) -> NoteMarker | None:
    """The signs at the start of `word` as a marker, the rest of the word as
    its rest, when `word` is 1 or 2 signs glued to a word that starts with
    a capital ("'There": marker "'", rest "There"); None otherwise."""
    match = _GLUED_SIGNS_FORM.fullmatch(word)
    if match is None:
        return None
    return NoteMarker(match.group(1), match.group(2), None)


def endnote_marker(word: str) -> NoteMarker | None:
    """The marker of an endnote whose first word is `word`: 1 to 3 digits
    followed by "." or "-", "I", "l", "!" and "o" counting as digits
    ("291.", "I39-"), with what it reads; None otherwise (spec section 11,
    the last form)."""
    if not _ENDNOTE_FORM.fullmatch(word):
        return None
    return NoteMarker(word, "", read_number(word[:-1]))


def marker_form(word: str) -> MarkerForm | None:
    """The form of the note marker `word` has, without the endnote form, or
    None when it has none."""
    if _DIGITS_FORM.fullmatch(word) or _GLUED_FORM.fullmatch(word):
        return MarkerForm.DIGITS
    if _bracketed(word) is not None:
        return MarkerForm.BRACKETED
    if _SIGNS_FORM.fullmatch(word):
        return MarkerForm.SIGN
    return None


def book_marker_form(first_words: Iterable[str]) -> MarkerForm | None:
    """The book's marker form (spec section 1): the form that the most of
    `first_words`, the first words of the book's band blocks, have, the
    first of digits, bracketed and sign on a tie; None when none has one."""
    counts = Counter(
        form for word in first_words if (form := marker_form(word)) is not None
    )
    if not counts:
        return None
    return max(MarkerForm, key=lambda form: counts[form])


class ReferenceForm(StrEnum):
    """The kinds of a note reference in the text (spec section 11,
    "References"): a number glued after a word, a bracketed number, or a
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


# Spec section 11, "References". The patterns take as punctuation a
# character that is neither a letter, a digit, "_" nor white space;
# `_is_punctuation` then keeps only Unicode's punctuation, so that "£2"
# (Domesday page 83, "of this £2 is due") is no candidate.
_PUNCTUATION = r"[^\w\s]"
# A letter, any punctuation, 1 to 3 digits, then only punctuation
# ("land3.", "Kadesh,12", "causa)27.", "12s.2").
_GLUED_AFTER_A_LETTER = re.compile(
    rf"(?P<before>.*[^\W\d_]{_PUNCTUATION}*)(?P<reference>[0-9]{{1,3}})"
    rf"(?P<after>{_PUNCTUATION}*)"
)
# Punctuation, 1 to 3 digits and only punctuation after, with no letter
# (Kadesh page 10's ";13"); a number with punctuation after it only, "13,",
# is none.
_GLUED_TO_PUNCTUATION = re.compile(
    rf"(?P<before>{_PUNCTUATION}*)(?P<reference>[0-9]{{1,3}})"
    rf"(?P<after>{_PUNCTUATION}*)"
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
_CITATION = re.compile(rf"{_PUNCTUATION}*(?P<letters>[^\W\d_]+){_PUNCTUATION}*")
# An opening bracket, 1 or 2 digits or letters read as digits, a closing
# bracket, and only punctuation after ("(1)", "(i).", "{2).").
_BRACKETED_REFERENCE = re.compile(
    rf"(?P<reference>[(\[{{](?P<inner>[0-9A-Za-z]{{1,2}})[)\]}}])"
    rf"(?P<after>{_PUNCTUATION}*)"
)
# The word "^", "*" or "•", or a letter, any punctuation and one of them,
# then only punctuation ("rulers.^", "servus*."). A lone "'" or "t" is
# none: in Domesday such a match was right 28 times in 82. The punctuation
# after the sign was added on 18 November 2026: 20 of the 178 notes of
# Domesday then not linked had such a reference. Such a word whose part
# before the sign holds one letter alone is none: Domesday's "St.", read
# "S*." 28 times, made 2 wrong links of those 23 new ones (pages 285 and
# 333). Without punctuation after, a word of one letter stays a candidate.
_SIGN_REFERENCE = re.compile(
    rf"(?P<before>(?:.*[^\W\d_]{_PUNCTUATION}*)?)(?P<reference>[\^*•])"
    rf"(?P<after>{_PUNCTUATION}*)"
)


def _is_punctuation(text: str) -> bool:
    """Whether every character of `text` is punctuation in Unicode's sense
    (category P): "," ")" "'" "/", not "£" or "^"."""
    return all(unicodedata.category(character).startswith("P") for character in text)


def _after_last_letter(text: str) -> str:
    return text[max(position for position, c in enumerate(text) if c.isalpha()) + 1 :]


def _glued(word: str) -> Reference | None:
    after_letter = _GLUED_AFTER_A_LETTER.fullmatch(word)
    if after_letter is not None and not (
        _is_punctuation(_after_last_letter(after_letter.group("before")))
        and _is_punctuation(after_letter.group("after"))
    ):
        return None
    if after_letter is not None:
        citation = _CITATION.fullmatch(after_letter.group("before"))
        if (
            citation is not None
            and citation.group("letters").lower() in _CITATION_ABBREVIATIONS
        ):
            return None
        match = after_letter
    else:
        match = _GLUED_TO_PUNCTUATION.fullmatch(word)
        if (
            match is None
            or not match.group("before")
            or not _is_punctuation(match.group("before") + match.group("after"))
        ):
            return None
    return Reference(
        match.group("before"),
        match.group("reference"),
        match.group("after"),
        ReferenceForm.GLUED,
        int(match.group("reference")),
    )


def reference_candidate(word: str) -> Reference | None:
    """The candidate note reference in a word of the body, by the forms of
    spec section 11, "References", or None: a glued number ("land3."
    gives ("land", "3", ".")), unless the word starts with a citation's
    abbreviation and has no other letter ("p.12"); a bracketed number
    ("(i)." gives ("", "(i)", ".") of value 1); or a sign ("rulers.^", and
    "servus*." gives ("servus", "*", "."))."""
    bracketed = _BRACKETED_REFERENCE.fullmatch(word)
    if bracketed is not None and _is_punctuation(bracketed.group("after")):
        value = read_number(bracketed.group("inner"), in_brackets=True)
        if value is None:
            return None
        return Reference(
            "",
            bracketed.group("reference"),
            bracketed.group("after"),
            ReferenceForm.BRACKETED,
            value,
        )
    glued = _glued(word)
    if glued is not None:
        return glued
    sign = _SIGN_REFERENCE.fullmatch(word)
    if sign is not None and (
        (not sign.group("before") and not sign.group("after"))
        or (
            sign.group("before")
            and (
                not sign.group("after")
                or sum(character.isalpha() for character in sign.group("before")) > 1
            )
            and _is_punctuation(_after_last_letter(sign.group("before")))
            and _is_punctuation(sign.group("after"))
        )
    ):
        return Reference(
            sign.group("before"),
            sign.group("reference"),
            sign.group("after"),
            ReferenceForm.SIGN,
            None,
        )
    return None
