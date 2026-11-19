"""Caption labels (figures spec section 1): the words that open a caption,
"figure", "plate" or "map", and the numeral after them.

structure finds a figure's caption by its label (figures spec section 5),
and extract, under `ocr = "redo"`, puts back the layer's numeral after such
a word where Tesseract misread it (extract spec section 9), so the two read
a label alike. Moved from `structure/_figures.py` on 19 November 2026.
"""

import re
from typing import Final

__all__ = [
    "LABEL_NAMES",
    "is_numeral",
    "is_well_formed_numeral",
]

# Figures spec section 1: the words that name a caption's label, in lower
# case, and a numeral's characters: digits and the letters of a roman
# numeral the OCR also reads for 1 ("li." for 11, "2i." for 21).
LABEL_NAMES: Final[frozenset[str]] = frozenset(
    {"figure", "fig.", "fig", "plate", "map"}
)
_NUMERAL_CHARACTERS = frozenset("0123456789ivxlcIVXLC")
_NUMERAL_ENDINGS = (".", ",")
_NUMERAL_MAX_CHARACTERS = 6
# Extract spec section 9, "Caption numbers from the layer": a numeral as
# printed, 1 to 3 digits or a roman numeral of upper-case letters, I to
# XXXIX, as Kadesh's maps III to VIII.
_WELL_FORMED = re.compile(r"[0-9]{1,3}|X{0,3}(?:IX|IV|V?I{0,3})")


def _bare(text: str) -> str:
    return text[:-1] if text.endswith(_NUMERAL_ENDINGS) else text


def is_numeral(text: str) -> bool:
    """Whether `text` is a numeral as the OCR reads one (figures spec
    section 1): 1 to 6 digits or letters i, v, x, l, c in either case, with
    or without a "." or "," after them ("111." and "li." are)."""
    bare = _bare(text)
    return 0 < len(bare) <= _NUMERAL_MAX_CHARACTERS and all(
        character in _NUMERAL_CHARACTERS for character in bare
    )


def is_well_formed_numeral(text: str) -> bool:
    """Whether `text` is a numeral as printed (extract spec section 9): 1 to
    3 digits, or a well-formed roman numeral in capitals, with or without a
    "." or "," after it ("VI.", "12"; not "ILL.", "VIIL" or "vi.")."""
    bare = _bare(text)
    return bool(bare) and _WELL_FORMED.fullmatch(bare) is not None
