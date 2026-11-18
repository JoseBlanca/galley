"""The excerpt test of the evaluation tool (spec section 10): `evaluate` on
the committed files of the excerpt haskins_eval, ten pages of Haskins,
checked against eight differences the owner checked by eye against the
page images on 15 November 2026. They are listed, with what is on each
page, in tests/fixtures/evaluation/haskins_eval_checked_differences.toml.

galley's files beside the excerpt were made once by the walking skeleton,
which leaves running heads, hyphens and footnotes where the text layer
has them, so every one of the eight starts at words and lasts to
markdown.
"""

from dataclasses import replace
from pathlib import Path

import pytest

from galley.book_folder import BookFolder
from galley_eval.align import State, Subkind
from galley_eval.books import read_books
from galley_eval.evaluate import Difference, evaluate
from galley_eval.scores import Part
from galley_eval.stages import StageOutput

_FIXTURES = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "evaluation"

type _Checked = tuple[
    int, tuple[str, ...], tuple[str, ...], State, Subkind | None, StageOutput, Part
]


def _checked(difference: Difference) -> _Checked:
    return (
        difference.page_index if difference.page_index is not None else -1,
        difference.reference,
        difference.galley,
        difference.state,
        difference.subkind,
        difference.stage,
        difference.part,
    )


@pytest.fixture(scope="module")
def differences() -> frozenset[_Checked]:
    book = read_books(_FIXTURES / "haskins_eval.toml")[0]
    evaluation = evaluate(
        book, BookFolder(_FIXTURES / "haskins_eval"), _FIXTURES / "haskins_eval.html"
    )
    return frozenset(_checked(difference) for difference in evaluation.differences)


def test_reference_that_ends_before_the_index_page_scores_no_index() -> None:
    # The excerpt's index page, printed page 251, is a div with the id
    # toclink_251 in the HTML; reference_ends_at leaves it out of the
    # comparison, and the body before it is still scored.
    book = replace(
        read_books(_FIXTURES / "haskins_eval.toml")[0], reference_ends_at="toclink_251"
    )
    evaluation = evaluate(
        book, BookFolder(_FIXTURES / "haskins_eval"), _FIXTURES / "haskins_eval.html"
    )
    words = evaluation.scorecard.outputs[0]
    assert words.output is StageOutput.WORDS
    assert words.text[Part.INDEX].reference_tokens == 0
    assert words.text[Part.BODY].reference_tokens > 0


def _extra_words(page_index: int, galley: tuple[str, ...]) -> tuple[_Checked, ...]:
    # A running head is one difference per token.
    return tuple(
        (page_index, (), (word,), State.EXTRA, None, StageOutput.WORDS, Part.BODY)
        for word in galley
    )


def test_running_head_of_a_right_hand_page_is_extra_from_words(
    differences: frozenset[_Checked],
) -> None:
    # Printed page 117: "NORMANDY AND FRANCE", then the page number.
    expected = _extra_words(1, ("NORMANDY", "AND", "FRANCE", "117"))
    assert set(expected) <= differences


def test_running_head_of_a_left_hand_page_is_extra_from_words(
    differences: frozenset[_Checked],
) -> None:
    # Printed page 122: the page number, then "NORMANS IN EUROPEAN HISTORY".
    expected = _extra_words(6, ("122", "NORMANS", "IN", "EUROPEAN", "HISTORY"))
    assert set(expected) <= differences


def test_hyphen_at_a_line_end_is_left_split_from_words(
    differences: frozenset[_Checked],
) -> None:
    # Printed page 116: "val-" ends a line.
    expected = (
        0,
        ("valley",),
        ("val-", "ley"),
        State.SPLIT,
        None,
        StageOutput.WORDS,
        Part.BODY,
    )
    assert expected in differences


def test_hyphenated_word_broken_at_its_hyphen_is_left_split_from_words(
    differences: frozenset[_Checked],
) -> None:
    # Printed page 118: "proto-journalist," carries note 1, read as "^".
    expected = (
        2,
        ("proto-journalist,",),
        ("proto-", "journalist,^"),
        State.SPLIT,
        None,
        StageOutput.WORDS,
        Part.BODY,
    )
    assert expected in differences


def test_footnote_left_in_the_body_is_a_difference_of_the_notes(
    differences: frozenset[_Checked],
) -> None:
    # Printed page 117: note 1's "VIII," is printed in capitals, a roman
    # numeral; the text layer reads it lower case.
    expected = (
        1,
        ("VIII,",),
        ("viii,",),
        State.CHANGED,
        Subkind.CASE,
        StageOutput.WORDS,
        Part.NOTES,
    )
    assert expected in differences


def test_misread_ligature_is_changed_letters_from_words(
    differences: frozenset[_Checked],
) -> None:
    # Printed page 117: the ligature of "Æschylus" read as "yE".
    expected = (
        1,
        ("Æschylus",),
        ("yEschylus",),
        State.CHANGED,
        Subkind.LETTERS,
        StageOutput.WORDS,
        Part.BODY,
    )
    assert expected in differences


def test_chapter_first_word_in_capitals_is_changed_case_from_words(
    differences: frozenset[_Checked],
) -> None:
    # Printed page 116: the chapter's first word is printed "IN", a drop
    # capital and a small capital, so galley's "IN" is right. Gutenberg
    # writes "In": the difference is real in the tool's terms, and the
    # error is the transcription's convention, not galley's.
    expected = (
        0,
        ("In",),
        ("IN",),
        State.CHANGED,
        Subkind.CASE,
        StageOutput.WORDS,
        Part.BODY,
    )
    assert expected in differences


def test_index_entry_with_italic_f_is_changed_punctuation_from_words(
    differences: frozenset[_Checked],
) -> None:
    # Printed page 251: the index starts "Abacus, 106 f.", the italic "f."
    # read as "/." glued to the number.
    expected = (
        9,
        ("106",),
        ("106/.",),
        State.CHANGED,
        Subkind.PUNCTUATION,
        StageOutput.WORDS,
        Part.INDEX,
    )
    assert expected in differences
