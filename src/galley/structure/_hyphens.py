"""Hyphens at line ends (spec section 5): whether two words split by a
hyphen are joined, with the hyphen dropped or kept, and the joins of a
block's lines."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import NamedTuple

from galley.model import ChangeReason, WordChange
from galley.structure._measures import (
    ASCII_DIGITS,
    is_digit_before_hyphen,
    is_hyphen_first_part,
)
from galley.wordlist import APOSTROPHES, word_key

# Spec section 5: the word list is no evidence for a second part of fewer
# than 2 letters ("Con-" "1", "na-" "R": junk keys it happens to hold).
_WORD_LIST_MIN_LETTERS = 2
# Spec section 5: a line of one of these signs of a note reference
# (section 11) between a hyphen and the next line is passed over (Haskins
# page 71, "fol-" "^" "lows:").
_LONE_SIGNS = frozenset({("^",), ("*",), ("•",)})


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
    the page index of each word (a joined word's is its first part's), and
    a word change for each join, in the order of the lines, with the
    position in `words` of the word it gave, and the positions of the words
    that start a line after the first, unless a hyphen join made that line
    one with the line before."""

    words: tuple[str, ...]
    pages: tuple[int, ...]
    changes: tuple[WordChange, ...]
    positions: tuple[int, ...]
    line_starts: tuple[int, ...]


def join_lines(
    lines: Sequence[PageLine], book_words: frozenset[str], word_list: frozenset[str]
) -> JoinedWords:
    """The words of `lines`, one block's lines in order, possibly over a
    page break, with the last word of each line joined to the first of the
    next when `join_hyphen` joins them. A change is on the page of its
    first word. A line of one word between two hyphens is joined twice. A
    line that holds only a reference sign ("^") after a line ending with a
    hyphen is passed over, and the sign goes after the word the join gives
    (spec section 5)."""
    words: list[str] = []
    pages: list[int] = []
    changes: list[WordChange] = []
    positions: list[int] = []
    line_starts: list[int] = []
    passed_over: PageLine | None = None
    for number, line in enumerate(lines):
        texts = line.words
        if (
            passed_over is None
            and texts in _LONE_SIGNS
            and words
            and is_hyphen_first_part(words[-1])
            and number + 1 < len(lines)
        ):
            passed_over = line
            continue
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
            positions.append(len(words) - 1)
            texts = texts[1:]
        elif words and texts:
            line_starts.append(len(words))
        if passed_over is not None:
            words.extend(passed_over.words)
            pages.extend(passed_over.page_index for _ in passed_over.words)
            passed_over = None
        words.extend(texts)
        pages.extend(line.page_index for _ in texts)
    return JoinedWords(
        tuple(words),
        tuple(pages),
        tuple(changes),
        tuple(positions),
        tuple(line_starts),
    )
