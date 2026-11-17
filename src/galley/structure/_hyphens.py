"""Hyphens at line ends (spec section 5): whether two words split by a
hyphen are joined, with the hyphen dropped or kept, and the joins of a
block's lines."""

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import NamedTuple, assert_never

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
# Spec section 5: the first part of a word whose hyphen was lost has 2
# letters or more ("im" "munist.", Domesday page 311), so that "a" "piece"
# is not joined.
_LOST_HYPHEN_MIN_LETTERS = 2
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


def _is_joined_word(
    key: str, second: str, book_words: frozenset[str], word_list: frozenset[str]
) -> bool:
    """Whether `key`, the key of a word joined from two parts, is among
    `book_words`, or in `word_list` when `second`, the second part, has
    `_WORD_LIST_MIN_LETTERS` letters or more (spec section 5)."""
    return key in book_words or (
        sum(character.isalpha() for character in second) >= _WORD_LIST_MIN_LETTERS
        and key in word_list
    )


def join_hyphen(
    first: str, second: str, book_words: frozenset[str], word_list: frozenset[str]
) -> HyphenJoin | None:
    """The word made of `first`, the last word of a line, and `second`, the
    first word of the next, or None when they are not joined (spec section
    5): `first` must end with "-" or "¬" after a letter or digit and `second`
    start with a letter or digit, and with an ASCII digit after an ASCII
    digit, in which case the hyphen is always kept (`hyphen_kept`): "235-"
    "37-" gives "235-37-". After a
    lower-case letter, a `second` that starts with a capital is joined
    only when the book prints the hyphenated word (`hyphen_kept`), and
    else not at all. A kept hyphen is "-", whichever `first` ends with:
    "1830¬" "40" gives "1830-40".

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
        return HyphenJoin(first[:-1] + "-" + second, ChangeReason.HYPHEN_KEPT)
    hyphenated = first[:-1] + "-" + second
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
    if any(_is_joined_word(key, second, book_words, word_list) for key in keys):
        return HyphenJoin(joined, ChangeReason.HYPHEN_JOIN)
    return HyphenJoin(joined, ChangeReason.HYPHEN_JOIN_GUESSED)


def join_lost_hyphen(
    first: str,
    second: str,
    book_words: frozenset[str],
    word_list: frozenset[str],
    common_inner_words: frozenset[str],
) -> HyphenJoin | None:
    """The word made of `first`, the last word of a line of a margin note,
    and `second`, the first word of the next, when the OCR lost the
    hyphen between them or read it as a full stop (`hyphen_lost`), or None
    (spec section 5): "move." "ment," gives "movement,".

    `first` ends with a letter, or a letter and one ".", and has
    `_LOST_HYPHEN_MIN_LETTERS` letters or more without the stop; `second`
    starts with a lower-case letter and its key is not among
    `common_inner_words` (`BookSurvey.common_inner_words`, the words
    printed whole); and the joined word is known (`_is_joined_word`)
    against `book_words` and `word_list`, which is in lower case.
    """
    stem = first.removesuffix(".")
    if not (
        stem[-1:].isalpha()
        and sum(character.isalpha() for character in stem) >= _LOST_HYPHEN_MIN_LETTERS
        and second[:1].isalpha()
        and second[0].islower()
        and word_key(second) not in common_inner_words
    ):
        return None
    joined = stem + second
    key = word_key(joined)
    if _is_joined_word(key, second, book_words, word_list):
        return HyphenJoin(joined, ChangeReason.HYPHEN_LOST)
    return None


class LostHyphens(StrEnum):
    """Whether a block's line ends whose hyphen the OCR lost are joined
    (`join_lost_hyphen`): in a margin note only (spec section 5)."""

    JOINED = "joined"
    NOT_JOINED = "not_joined"


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
    lines: Sequence[PageLine],
    book_words: frozenset[str],
    word_list: frozenset[str],
    unjoined: frozenset[int] = frozenset(),
    *,
    lost_hyphens: LostHyphens,
    common_inner_words: frozenset[str],
) -> JoinedWords:
    """The words of `lines`, one block's lines in order, possibly over a
    page break, with the last word of each line joined to the first of the
    next when `join_hyphen` joins them. A change is on the page of its
    first word. A line of one word between two hyphens is joined twice. A
    line that holds only a reference sign ("^") after a line ending with a
    hyphen is passed over, and the sign goes after the word the join gives
    (spec section 5). A line whose position is in `unjoined` is never
    joined to the line before. With `lost_hyphens` JOINED, as in a margin
    note, a line whose last word `join_hyphen` does not join is joined by
    `join_lost_hyphen`, against `common_inner_words`, when it gives a
    word; with NOT_JOINED, `common_inner_words` is not used."""
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
        joinable = bool(words) and bool(texts) and number not in unjoined
        joined = (
            join_hyphen(words[-1], texts[0], book_words, word_list)
            if joinable
            else None
        )
        if joined is None and joinable:
            match lost_hyphens:
                case LostHyphens.JOINED:
                    joined = join_lost_hyphen(
                        words[-1], texts[0], book_words, word_list, common_inner_words
                    )
                case LostHyphens.NOT_JOINED:
                    pass
                case _:
                    assert_never(lost_hyphens)
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
