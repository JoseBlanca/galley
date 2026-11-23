"""A footnote's reference that the OCR set apart as a word of its own (spec
section 11, "A lone number"): "child 3." for "child³.", linked only to
the note after the last one its page linked."""

import re
from collections.abc import Sequence

from galley.note_references import is_punctuation
from galley.structure._markers import Reference, ReferenceForm
from galley.structure._references import BodyWord, Candidate, Link, NoteToMatch

# 1 or 2 digits, then only punctuation.
_LONE_NUMBER = re.compile(r"(?P<reference>[0-9]{1,2})(?P<after>[^\w\s]*)")
# What may start the word after a lone number that has no punctuation of
# its own: a capital, or an opening bracket ("8s. 9 (iv)", Domesday page
# 142).
_OPENING_BRACKETS = "(["
# The sign the OCR gives for a raised number at the end of a sentence in
# Domesday ("hides \\ Moreover", page 483): alone, or after a letter and
# punctuation ("burh'\\").
_BACKSLASH = "\\"
_GLUED_BACKSLASH = re.compile(r"(?P<before>.*[^\W\d_][^\w\s]+)\\(?P<after>[^\w\s]*)")
# The end of the word before a lone number: a letter, or the end of a
# sentence and a closing quotation mark ('time." 1', Haskins page 154).
_ENDS_A_WORD = re.compile(r".*(?:[^\W\d_]|[.!?][\"'’”])")
# A number ("£11 1.", page 83), before a lone number with punctuation.
_ENDS_A_NUMBER = re.compile(r".*[0-9]")
# A star glued after a number, then punctuation ("15*.", page 139).
_STAR_AFTER_A_NUMBER = re.compile(r"(?P<before>.*[0-9])\*(?P<after>[^\w\s]+)")


def lone_reference(word: BodyWord, value: int) -> Reference | None:
    """The reference to the note of `value` that `word` is, or None: 1 or 2
    digits that read `value`, with only punctuation after, after a word
    that ends with a letter or with a sentence's end and a closing
    quotation mark, and with punctuation after it or before a word that
    starts with a capital or an opening bracket ("child", "3."); or a
    backslash, alone after a word with a letter or a digit and before a
    word that starts with a capital ("80", "\\", "Moreover"), or after a
    letter and punctuation ("burh'\\")."""
    glued = _GLUED_BACKSLASH.fullmatch(word.text)
    if glued is not None and is_punctuation(glued.group("after")):
        return Reference(
            glued.group("before"),
            _BACKSLASH,
            glued.group("after"),
            ReferenceForm.SIGN,
            None,
        )
    star = _STAR_AFTER_A_NUMBER.fullmatch(word.text)
    if star is not None and is_punctuation(star.group("after")):
        return Reference(
            star.group("before"), "*", star.group("after"), ReferenceForm.SIGN, None
        )
    if word.text == _BACKSLASH:
        if word.following[:1].isupper() and any(
            character.isalnum() for character in word.previous
        ):
            return Reference("", _BACKSLASH, "", ReferenceForm.SIGN, None)
        return None
    match = _LONE_NUMBER.fullmatch(word.text)
    if (
        match is None
        or int(match.group("reference")) != value
        or not is_punctuation(match.group("after"))
        or not (
            _ENDS_A_WORD.fullmatch(word.previous) is not None
            or (
                match.group("after")
                and _ENDS_A_NUMBER.fullmatch(word.previous) is not None
            )
        )
    ):
        return None
    if not match.group("after") and not (
        word.following[:1].isupper() or word.following[:1] in _OPENING_BRACKETS
    ):
        return None
    return Reference(
        "", match.group("reference"), match.group("after"), ReferenceForm.GLUED, value
    )


def _reads(word: BodyWord, value: int) -> bool:
    """Whether `word` ends with the digits of `value` and then only
    punctuation ("2.", "42."): another place the reference may be, unless
    it is the word just before the lone number ("£11 1.")."""
    return re.fullmatch(rf".*{value}[^\w\s]*", word.text) is not None


def lone_links(
    notes: Sequence[NoteToMatch], words: Sequence[BodyWord], links: Sequence[Link]
) -> tuple[Link, ...]:
    """The footnotes that `links` left unlinked, linked to a lone number
    (spec section 11, "A lone number"): on each page, a note is linked
    when it is the page's first note or the note before it is linked, and
    exactly one of `words`, the body's paragraph words in reading order
    that no link took, between the reference of the note before (or the
    page's start) and that of the next linked note of the page (or the
    page's end), is `lone_reference` to its value."""
    linked = {link.note: (link.candidate.block, link.candidate.word) for link in links}
    by_page: dict[int, list[NoteToMatch]] = {}
    for note in notes:
        by_page.setdefault(note.page_index, []).append(note)
    words_by_page: dict[int, list[BodyWord]] = {}
    for word in words:
        words_by_page.setdefault(word.page_index, []).append(word)
    made: list[Link] = []
    for page_index, page_notes in sorted(by_page.items()):
        start: tuple[int, int] | None = None
        eligible = True
        for place, note in enumerate(page_notes):
            if note.note in linked:
                start, eligible = linked[note.note], True
                continue
            if not eligible or note.value is None:
                eligible = False
                continue
            end = next(
                (
                    linked[later.note]
                    for later in page_notes[place + 1 :]
                    if later.note in linked
                ),
                None,
            )
            gap = tuple(
                word
                for word in words_by_page.get(page_index, ())
                if (start is None or (word.block, word.word) > start)
                and (end is None or (word.block, word.word) < end)
            )
            found = tuple(
                (word, reading)
                for word in gap
                if (reading := lone_reference(word, note.value)) is not None
            )
            if len(found) != 1 or any(
                _reads(word, note.value)
                for word in gap
                if word is not found[0][0]
                and (word.block, word.word + 1) != (found[0][0].block, found[0][0].word)
            ):
                eligible = False
                continue
            word, reading = found[0]
            made.append(
                Link(
                    Candidate(word.block, word.word, word.page_index, reading),
                    note.note,
                )
            )
            start = (word.block, word.word)
    return tuple(made)
