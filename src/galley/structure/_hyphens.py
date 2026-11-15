"""Hyphens at line ends (spec section 5): whether two words split by a
hyphen are joined, with the hyphen dropped or kept, and the joins of a
block's lines."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import NamedTuple

from galley.model import ChangeReason, WordChange
from galley.structure._measures import (
    APOSTROPHES,
    ASCII_DIGITS,
    is_digit_before_hyphen,
    is_hyphen_first_part,
    word_key,
)

# Spec section 5: the word list is no evidence for a second part of fewer
# than 2 letters ("Con-" "1", "na-" "R": junk keys it happens to hold).
_WORD_LIST_MIN_LETTERS = 2


class HyphenJoin(NamedTuple):
    """The word two parts make, and why: `hyphen_join`, `hyphen_join_guessed`
    or `hyphen_kept`."""

    word: str
    reason: ChangeReason


def _after_last_apostrophe(key: str) -> str:
    cut = max(key.rfind(apostrophe) for apostrophe in APOSTROPHES)
    return key[cut + 1 :]


def join_hyphen(
    first: str, second: str, book_words: frozenset[str], word_list: frozenset[str]
) -> HyphenJoin | None:
    """The word made of `first`, the last word of a line, and `second`, the
    first word of the next, or None when they are not joined (spec section
    5): `first` must end with "-" after a letter or digit and `second`
    start with a letter or digit, and with an ASCII digit after an ASCII
    digit, in which case the hyphen is always kept (`hyphen_kept`): "235-"
    "37-" gives "235-37-". After a
    lower-case letter, a `second` that starts with a capital is joined
    only when the book prints the hyphenated word (`hyphen_kept`), and
    else not at all.

    The hyphen is kept (`hyphen_kept`) when the hyphenated word is among
    `book_words`, the keys of the words the book prints whole, and the
    joined word is not; it is dropped
    (`hyphen_join`) when the joined word is in `word_list`, which is in
    lower case (unless `second` has fewer than 2 letters), or among
    `book_words`, and dropped as a guess
    (`hyphen_join_guessed`) otherwise. When `first` holds an apostrophe,
    the joined word's part after its last apostrophe is looked up too.
    """
    if not (is_hyphen_first_part(first) and second[:1].isalnum()):
        return None
    if is_digit_before_hyphen(first):
        if second[0] not in ASCII_DIGITS:
            return None
        return HyphenJoin(first + second, ChangeReason.HYPHEN_KEPT)
    hyphenated = first + second
    joined = first[:-1] + second
    if first[-2].islower() and second[0].isupper():
        if word_key(hyphenated) in book_words:
            return HyphenJoin(hyphenated, ChangeReason.HYPHEN_KEPT)
        return None
    joined_key = word_key(joined)
    if word_key(hyphenated) in book_words and joined_key not in book_words:
        return HyphenJoin(hyphenated, ChangeReason.HYPHEN_KEPT)
    keys = (joined_key,)
    if any(apostrophe in first for apostrophe in APOSTROPHES):
        keys = (joined_key, _after_last_apostrophe(joined_key))
    word_list_counts = (
        sum(character.isalpha() for character in second) >= _WORD_LIST_MIN_LETTERS
    )
    if any(
        key in book_words or (word_list_counts and key in word_list) for key in keys
    ):
        return HyphenJoin(joined, ChangeReason.HYPHEN_JOIN)
    return HyphenJoin(joined, ChangeReason.HYPHEN_JOIN_GUESSED)


@dataclass(frozen=True, slots=True)
class PageLine:
    """The words of one line of a block, and the index of its page."""

    page_index: int
    words: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class JoinedWords:
    """The words of a block's lines, with the hyphens at line ends joined,
    and a word change for each join, in the order of the lines."""

    words: tuple[str, ...]
    changes: tuple[WordChange, ...]


def join_lines(
    lines: Sequence[PageLine], book_words: frozenset[str], word_list: frozenset[str]
) -> JoinedWords:
    """The words of `lines`, one block's lines in order, possibly over a
    page break, with the last word of each line joined to the first of the
    next when `join_hyphen` joins them. A change is on the page of its
    first word. A line of one word between two hyphens is joined twice."""
    words: list[str] = []
    pages: list[int] = []
    changes: list[WordChange] = []
    for line in lines:
        texts = line.words
        joined = (
            join_hyphen(words[-1], texts[0], book_words, word_list)
            if words and texts
            else None
        )
        if joined is not None:
            changes.append(
                WordChange(
                    page_index=pages[-1],
                    before=(words[-1], texts[0]),
                    after=(joined.word,),
                    reason=joined.reason,
                )
            )
            words[-1] = joined.word
            texts = texts[1:]
        words.extend(texts)
        pages.extend(line.page_index for _ in texts)
    return JoinedWords(tuple(words), tuple(changes))
