"""Tests of the caption labels' numerals (figures spec section 1, extract
spec section 9), with the words Kadesh's maps and Turney's figures give."""

import pytest

from galley.caption_labels import is_numeral, is_well_formed_numeral


@pytest.mark.parametrize(
    ("text", "numeral"),
    [
        ("111.", True),
        ("li.", True),
        ("VIIL", True),
        ("123456", True),
        ("1234567", False),
        ("Y.", False),
        ("", False),
        (".", False),
    ],
)
def test_numeral_as_the_ocr_reads_one(text: str, numeral: bool) -> None:
    assert is_numeral(text) is numeral


@pytest.mark.parametrize(
    ("text", "well_formed"),
    [
        ("VI.", True),
        ("VIII.", True),
        ("IV", True),
        ("XXXIX,", True),
        ("12", True),
        ("ILL.", False),
        ("VIIL", False),
        ("vi.", False),
        ("111.", True),
        ("1234", False),
        ("", False),
        (".", False),
    ],
)
def test_numeral_as_printed(text: str, well_formed: bool) -> None:
    assert is_well_formed_numeral(text) is well_formed
