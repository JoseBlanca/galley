"""Whether a page is inkless, from the same small render as the plate rule
(plates spec section 2b).

An inkless page prints nothing, or only the next page showing through or
a patterned endpaper, while its text layer holds words the scanner's OCR
invented there. Under a real word there is ink and under these there is
none, so each word's ink is measured on the render: the largest gap in
gray between the paper around the word and any pixel near it, either way,
so that white print on a dark ground counts.
"""

import math
import statistics
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from galley.model import Box, RenderedPage
from galley.pdfium import POINTS_PER_INCH
from galley.wordlist import is_known_word

# Plates spec section 2b: measured on the words of the eight books, whose
# text-layer boxes sit a few points off the print: of the real words, 2,573
# have no ink with the box not grown, 972 grown by 1 pt and 339 by 3 pt.
_INK_BOX_GROWTH_PT: Final[float] = 3.0
# Plates spec section 2b: guessed, and kept because it absorbs the gradient
# of Haynes' page 9, which darkens from one side to the other.
_BACKGROUND_BOX_GROWTH_PT: Final[float] = 6.0
# Plates spec section 2b: measured, 40 of the 43 junk words of the eight
# books have less ink, and 339 of 1.1 million real ones.
_LEAST_INK_LEVELS: Final[int] = 20
# Plates spec section 2b: measured, the inkless pages have 0.88 to 1.00 of
# their words without ink, the highest page of print 0.10 (Domesday 481).
_INKLESS_SHARE: Final[float] = 0.5
# Plates spec section 2b: measured, the words without ink of the inkless
# pages are at most 0.17 known words (Haynes 9, 1 of 6), those of Gierke
# 1, a binder's label printed faintly, 0.50 (1 of 2).
_KNOWN_SHARE_OF_PRINT: Final[float] = 0.5


class InkRule(StrEnum):
    """What the inkless rule of plates spec section 2b found on a page: an
    inkless page, or not one (also for a page it does not test, one the
    plate rule does not test or one without words outside its excluded
    regions)."""

    INKLESS = "inkless"
    NOT_INKLESS = "not_inkless"


@dataclass(frozen=True, slots=True)
class InkTest:
    """What the inkless rule measured on a page it tested: the share of the
    words outside its excluded regions that have no ink, and the rule's
    finding."""

    share_without_ink: float
    rule: InkRule


def is_inkless(
    page: RenderedPage,
    layer_words: tuple[tuple[str, Box], ...],
    lower_case_words: frozenset[str],
) -> bool:
    """Whether the page is inkless by plates spec section 2b: at least half
    of `layer_words`, the page's text-layer words outside its excluded
    regions, each its text and box in points, have no ink on `page`, its
    36 dpi render, and fewer than half of those without ink are known
    words (`wordlist.is_known_word`) of `lower_case_words`, the word list
    as `wordlist.lower_case_word_list` gives it. False when `layer_words`
    is empty."""
    ink_test = measure_ink(page, layer_words, lower_case_words)
    return ink_test is not None and ink_test.rule is InkRule.INKLESS


def measure_ink(
    page: RenderedPage,
    layer_words: tuple[tuple[str, Box], ...],
    lower_case_words: frozenset[str],
) -> InkTest | None:
    """The inkless rule on `page` and `layer_words`, as `is_inkless` takes
    them: the share of `layer_words` without ink and the rule's finding;
    None when `layer_words` is empty, a page the rule does not test."""
    if not layer_words:
        return None
    without_ink = tuple(text for text, box in layer_words if not _has_ink(page, box))
    share = len(without_ink) / len(layer_words)
    known_share = (
        sum(1 for text in without_ink if is_known_word(text, lower_case_words))
        / len(without_ink)
        if without_ink
        else 0.0
    )
    inkless = share >= _INKLESS_SHARE and known_share < _KNOWN_SHARE_OF_PRINT
    return InkTest(
        share_without_ink=share,
        rule=InkRule.INKLESS if inkless else InkRule.NOT_INKLESS,
    )


def _has_ink(page: RenderedPage, box: Box) -> bool:
    """Whether the word whose box is `box`, in points, has ink on `page`: the
    local background, the median gray of the box grown by
    `_BACKGROUND_BOX_GROWTH_PT`, differs by at least `_LEAST_INK_LEVELS`
    gray levels from the darkest or the brightest pixel of the box grown by
    `_INK_BOX_GROWTH_PT`. A box with no pixel on the page has none."""
    background_pixels = _pixels(page, box, _BACKGROUND_BOX_GROWTH_PT)
    word_pixels = _pixels(page, box, _INK_BOX_GROWTH_PT)
    if not word_pixels:
        return False
    background = statistics.median_low(background_pixels)
    ink = max(background - min(word_pixels), max(word_pixels) - background)
    return ink >= _LEAST_INK_LEVELS


def _pixels(page: RenderedPage, box: Box, growth_pt: float) -> bytes:
    """The pixels of `page` under `box` grown by `growth_pt` on every side,
    its left and top rounded down and its right and bottom rounded up, cut
    to the page; empty when the grown box lies wholly off the page."""
    scale = page.dpi / POINTS_PER_INCH
    left = max(0, math.floor((box.x0 - growth_pt) * scale))
    top = max(0, math.floor((box.top - growth_pt) * scale))
    right = min(page.width_px, math.ceil((box.x1 + growth_pt) * scale))
    bottom = min(page.height_px, math.ceil((box.bottom + growth_pt) * scale))
    if right <= left or bottom <= top:
        return b""
    return b"".join(
        page.pixels[row * page.width_px + left : row * page.width_px + right]
        for row in range(top, bottom)
    )
