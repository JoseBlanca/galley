"""Tests of galley.contents_labels: the number labels and the runs of a
printed contents, and rule 12's inferred labels (docs/specs/structure.md,
section 30, rule 12, and section 31)."""

import pytest

from galley.contents_labels import (
    LabelStyle,
    NumberLabel,
    contents_runs,
    inferred_labels,
    number_label,
)


@pytest.mark.parametrize(
    ("label", "number"),
    [
        ("7.", NumberLabel(LabelStyle.DIGITS, 7)),
        ("16.", NumberLabel(LabelStyle.DIGITS, 16)),
        ("IV.", NumberLabel(LabelStyle.ROMAN, 4)),
        ("XIV.", NumberLabel(LabelStyle.ROMAN, 14)),
        (None, None),
        ("0.", None),
        ("00.", None),
        (".", None),
        ("IIII.", None),
        ("iv.", None),
        ("l.", None),
        ("100.", None),
        ("7", None),
        ("One", None),
    ],
)
def test_number_label_is_one_or_two_digits_or_a_roman_numeral_with_a_period(
    label: str | None, number: NumberLabel | None
) -> None:
    assert number_label(label) == number


def test_contents_runs_are_the_consecutive_contents_pages() -> None:
    assert contents_runs((52, 10, 54, 53, 67)) == ((10,), (52, 53, 54), (67,))
    assert contents_runs(()) == ()


@pytest.mark.parametrize(
    ("labels", "levels", "inferred"),
    [
        # Between two labels in sequence, the count fitting.
        (("2.", None, "4."), (1, 1, 1), {1: "3."}),
        # Before the run's first number label.
        (
            (None, None, None, "IV.", None),
            (1, 1, 1, 1, 1),
            {0: "I.", 1: "II.", 2: "III."},
        ),
        # Only the N−1 entries just before "2." get a label.
        ((None, None, None, "2."), (1, 1, 1, 1), {2: "1."}),
        # The count does not fit, or the styles differ.
        (("2.", None, "5."), (1, 1, 1), {}),
        (("IV.", None, "6."), (1, 1, 1), {}),
        ((None, None, "4."), (1, 1, 1), {}),
        # An entry with a label of another kind keeps it, and none is
        # inferred across it.
        (("1.", "Chapter Two", "3."), (1, 1, 1), {}),
        ((None, "Chapter Two", "3."), (1, 1, 1), {}),
        # The depths: sections between two chapters take no number.
        (("I.", None, None, "IV."), (1, 2, 2, 1), {}),
        (("I.", None, None, "IV."), (1, 1, 1, 2), {}),
        ((None, None, "III."), (2, 1, 1), {}),
        ((None, None, "III."), (2, 2, 2), {0: "I.", 1: "II."}),
    ],
)
def test_labels_are_inferred_where_count_and_depth_fit(
    labels: tuple[str | None, ...],
    levels: tuple[int, ...],
    inferred: dict[int, str],
) -> None:
    assert dict(inferred_labels(labels, levels)) == inferred
