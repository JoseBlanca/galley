"""The hyphens that end a line of print in the OCR's text, which layout,
structure and the fidelity check all recognise (structure spec section 5).
"""

from typing import Final

# The ASCII hyphen-minus and the not sign "¬" (U+00AC), with which the OCR
# of two of the owner's books marks every line-end hyphen.
LINE_END_HYPHENS: Final[frozenset[str]] = frozenset({"-", "\N{NOT SIGN}"})
