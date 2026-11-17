"""Tests of spaced punctuation and of words glued at a case change
(docs/specs/structure.md, sections 23 and 24; the spaced-signs and
case-split bullets of section 26).

Every value is written by hand. The passes run on a block before
references are looked for; the reference that a sign attached to
"hides4" gives is checked with `reference_candidate`, since wiring the
passes into structure is a later task.
"""

import pytest

from galley.model import BlockKind, Box, ChangeReason, Origin, WordChange
from galley.structure import reference_candidate
from galley.structure._case_split import CASE_SPLIT, split_at_case, split_glued_words
from galley.structure._markers import Reference, ReferenceForm
from galley.structure._spaced import (
    PUNCTUATION_ATTACHED,
    attach_spaced_sign,
    attach_spaced_signs,
    no_break_positions,
)
from galley.structure._unnumbered import Unnumbered

_ORIGIN = (Origin(4, Box(72.0, 100.0, 400.0, 160.0)),)


def _block(
    words: tuple[str, ...],
    *,
    kind: BlockKind = BlockKind.PARAGRAPH,
    pages: tuple[int, ...] | None = None,
    changes: tuple[tuple[int, WordChange], ...] = (),
    line_starts: frozenset[int] = frozenset(),
) -> Unnumbered:
    return Unnumbered(
        kind,
        words,
        pages if pages is not None else tuple(4 for _ in words),
        _ORIGIN,
        changes,
        line_starts=line_starts,
    )


# The reasons task 2.1 adds to ChangeReason.


def test_new_reasons_have_the_names_of_the_spec() -> None:
    assert PUNCTUATION_ATTACHED == "punctuation_attached"
    assert CASE_SPLIT == "case_split"


@pytest.mark.parametrize("value", ["punctuation_attached", "case_split"])
def test_change_reason_lacks_the_new_reason_until_task_2_1_is_merged(
    value: str,
) -> None:
    # When this fails, task 2.1 is merged: PUNCTUATION_ATTACHED and
    # CASE_SPLIT become ChangeReason's members and this test goes.
    with pytest.raises(ValueError, match=value):
        ChangeReason(value)


# attach_spaced_sign


@pytest.mark.parametrize(
    ("before", "word", "attached"),
    [
        ("subjection", ";", "subjection;"),
        ("pursued", "?", "pursued?"),
        ("follows", ":", "follows:"),
        ("alas", "!", "alas!"),
        ("hides4", ";", "hides4;"),
        ("(1)", ";", "(1);"),
        ("[sic]", ":", "[sic]:"),
        ("subjection", ";^", "subjection;^"),
        ("he", "?'", "he?'"),
    ],
)
def test_spaced_sign_after_a_letter_digit_or_bracket_is_attached(
    before: str, word: str, attached: str
) -> None:
    assert attach_spaced_sign(before, word) == attached


@pytest.mark.parametrize(
    ("before", "word"),
    [
        ("—", ";"),
        ("'", "?"),
        ("said’", ";"),
        ('said"', ":"),
        ("dit»", "!"),
        ("etc.", ";"),
        ("subjection", "and"),
        ("subjection", ","),
    ],
)
def test_sign_after_a_dash_or_quotation_mark_or_a_word_not_a_sign_stays(
    before: str, word: str
) -> None:
    assert attach_spaced_sign(before, word) is None


# attach_spaced_signs


def test_spaced_sign_in_a_block_is_attached_with_its_change() -> None:
    hyphen = WordChange(
        page_index=4,
        before=("re-", "plied"),
        after=("replied",),
        reason=ChangeReason.HYPHEN_JOIN,
    )
    later = WordChange(
        page_index=5,
        before=("con-", "quest"),
        after=("conquest",),
        reason=ChangeReason.HYPHEN_JOIN,
    )
    block = _block(
        ("He", "replied", ";", "the", "conquest", "ended"),
        pages=(4, 4, 4, 5, 5, 5),
        changes=((1, hyphen), (4, later)),
        line_starts=frozenset({3}),
    )

    attached = attach_spaced_signs(block)

    assert attached.words == ("He", "replied;", "the", "conquest", "ended")
    assert attached.word_pages == (4, 4, 5, 5, 5)
    assert attached.line_starts == frozenset({2})
    assert attached.changes == (
        (1, hyphen),
        (3, later),
        (
            1,
            WordChange(
                page_index=4,
                before=("replied", ";"),
                after=("replied;",),
                reason=PUNCTUATION_ATTACHED,
            ),
        ),
    )


def test_spaced_sign_on_the_next_line_of_a_paragraph_is_attached() -> None:
    block = _block(
        ("of", "subjection", ";", "and"),
        pages=(4, 4, 5, 5),
        line_starts=frozenset({2}),
    )

    attached = attach_spaced_signs(block)

    assert attached.words == ("of", "subjection;", "and")
    assert attached.word_pages == (4, 4, 5)
    assert attached.line_starts == frozenset()
    assert attached.changes[0][1].page_index == 4


def test_sign_that_starts_a_block_or_follows_a_dash_stays() -> None:
    block = _block((";", "the", "—", ";", "'", "?"))

    assert attach_spaced_signs(block) == block


def test_sign_after_a_line_feed_of_verse_stays() -> None:
    block = _block(
        ("O", "Death", "?", "where"),
        kind=BlockKind.VERSE,
        line_starts=frozenset({2}),
    )

    assert attach_spaced_signs(block) == block


def test_sign_attached_to_a_glued_reference_gives_the_reference_and_the_sign() -> None:
    attached = attach_spaced_signs(_block(("five", "hides4", ";", "and")))

    assert attached.words[1] == "hides4;"
    assert reference_candidate(attached.words[1]) == Reference(
        "hides", "4", ";", ReferenceForm.GLUED, 4
    )


def test_sign_glued_to_a_sign_reference_becomes_a_candidate() -> None:
    assert reference_candidate(";^") is None

    attached = attach_spaced_signs(_block(("of", "subjection", ";^")))

    assert attached.words == ("of", "subjection;^")
    assert reference_candidate(attached.words[1]) == Reference(
        "subjection;", "^", "", ReferenceForm.SIGN, None
    )


# no_break_positions, for a French book


def test_spaced_sign_in_french_takes_a_no_break_space_and_no_change() -> None:
    block = _block(
        ("complète", ";", "(1)", ":", "—", "?", "hides4", "!"),
        line_starts=frozenset({3}),
    )

    assert no_break_positions(block) == frozenset({1, 3, 7})


def test_no_break_space_is_not_put_at_a_line_feed_of_verse_or_a_block_start() -> None:
    block = _block(
        ("?", "mort", "!", "vie"),
        kind=BlockKind.VERSE,
        line_starts=frozenset({2}),
    )

    assert no_break_positions(block) == frozenset()


# split_at_case

_LOWER_CASE_WORDS = frozenset({"the", "of", "in", "de", "le", "guin", "ab"})
_BOOK_WORDS = frozenset({"avre", "william", "ab", "guin", "out"})


@pytest.mark.parametrize(
    ("word", "parts"),
    [
        ("theAvre", ("the", "Avre")),
        ("ofWilliam,", ("of", "William,")),
        ("(theAvre).", ("(the", "Avre).")),
    ],
)
def test_word_glued_at_a_case_change_is_split_when_the_book_prints_the_right_part(
    word: str, parts: tuple[str, str]
) -> None:
    assert split_at_case(word, _LOWER_CASE_WORDS, _BOOK_WORDS) == parts


@pytest.mark.parametrize(
    ("word", "book_words", "lower_case_words"),
    [
        ("theAvre", frozenset({"william"}), _LOWER_CASE_WORDS),
        ("LeGuin", _BOOK_WORDS, _LOWER_CASE_WORDS),
        ("deUver", _BOOK_WORDS, _LOWER_CASE_WORDS),
        ("ofAb", _BOOK_WORDS, _LOWER_CASE_WORDS),
        ("aWilliam", _BOOK_WORDS, _LOWER_CASE_WORDS | {"a"}),
        ("xyWilliam", _BOOK_WORDS, _LOWER_CASE_WORDS),
        ("theAvre", _BOOK_WORDS, _LOWER_CASE_WORDS | {"theavre"}),
        ("ofWilliAm", _BOOK_WORDS, _LOWER_CASE_WORDS),
        ("of-William", _BOOK_WORDS, _LOWER_CASE_WORDS),
        ("ofWilliam's", _BOOK_WORDS, _LOWER_CASE_WORDS),
        ("theavre", _BOOK_WORDS, _LOWER_CASE_WORDS),
    ],
)
def test_word_not_glued_at_a_case_change_or_without_evidence_stays(
    word: str, book_words: frozenset[str], lower_case_words: frozenset[str]
) -> None:
    assert split_at_case(word, lower_case_words, book_words) is None


# split_glued_words


def test_glued_word_in_a_block_is_split_with_its_change() -> None:
    hyphen = WordChange(
        page_index=4,
        before=("Wil-", "liam"),
        after=("William",),
        reason=ChangeReason.HYPHEN_JOIN,
    )
    later = WordChange(
        page_index=5,
        before=("Nor-", "mandy"),
        after=("Normandy",),
        reason=ChangeReason.HYPHEN_JOIN,
    )
    joined = WordChange(
        page_index=4,
        before=("ofWil-", "liam,"),
        after=("ofWilliam,",),
        reason=ChangeReason.HYPHEN_JOIN,
    )
    block = _block(
        ("William", "came", "ofWilliam,", "to", "Normandy"),
        pages=(4, 4, 4, 5, 5),
        changes=((0, hyphen), (2, joined), (4, later)),
        line_starts=frozenset({3}),
    )

    split = split_glued_words(block, _LOWER_CASE_WORDS, _BOOK_WORDS)

    assert split.words == ("William", "came", "of", "William,", "to", "Normandy")
    assert split.word_pages == (4, 4, 4, 4, 5, 5)
    assert split.line_starts == frozenset({4})
    assert split.changes == (
        (0, hyphen),
        (2, joined),
        (5, later),
        (
            2,
            WordChange(
                page_index=4,
                before=("ofWilliam,",),
                after=("of", "William,"),
                reason=CASE_SPLIT,
            ),
        ),
    )


def test_block_without_glued_words_is_unchanged() -> None:
    block = _block(("the", "Avre", "deUver", "LeGuin"))

    assert split_glued_words(block, _LOWER_CASE_WORDS, _BOOK_WORDS) == block
