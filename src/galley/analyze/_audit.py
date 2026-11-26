"""The audit of a page without a text layer (analyze spec sections 1 and 3).

analyze reads each page without a text layer that it audits with
Tesseract, on its 300 dpi render, and measures the share of the page
that is ink on the same render. `audit_verdict` turns the two into a
verdict: much text, text, a picture, or blank. A word of Tesseract counts
as text only when it is read at a confidence of 70 or more and holds a
letter or digit; the other words it reads on an empty page are its
readings of specks and stains. Ink is measured against the page's own
background, so that a stain, the shadow of the binding or another page
showing through is not ink, and a band at each edge of the page, where
the scan's rim lies, is left out.
"""

from enum import StrEnum
from typing import Final

from PIL import Image, ImageChops, ImageFilter

from galley.model import RenderedPage, Word
from galley.ocr import OCR_DPI

__all__ = [
    "AuditVerdict",
    "audit_verdict",
    "image_ink_share",
    "ink_share",
    "is_text_word",
]

# Analyze spec section 3: the stray marks of the 47 pages judged blank of
# the five books reach 51.7, the best word of the printed page read worst
# is 86.9 (measured on 26 November 2026).
_TEXT_WORD_LEAST_CONFIDENCE: Final[float] = 70.0
# Analyze spec section 2, rule 4: Tesseract reads 0 to 23 text words on the
# 21 plates of the five books, 26 or more on a page of text the plate rule
# takes (measured on 26 November 2026).
_MUCH_TEXT_LEAST_WORDS: Final[int] = 40
# Analyze spec section 3: 0.062% at most on the 47 pages judged blank,
# 0.114% at least on a page that holds print (measured on 26 November 2026).
_PICTURE_LEAST_INK_SHARE: Final[float] = 0.0008
# Analyze spec section 3, the four steps of the ink share, measured on the
# blank pages and 26 short pages with a text layer on 26 November 2026: the
# render halved to 150 dpi; a background of radius 20 pixels of the halved
# image; ink 15 levels or more below it; bands of 8% of the width and 6%
# of the height left out at the edges.
_HALVING: Final[int] = 2
_BACKGROUND_RADIUS_PX: Final[int] = 20
_INK_LEAST_LEVELS: Final[int] = 15
_SIDE_BAND_SHARE: Final[float] = 0.08
_TOP_AND_FOOT_BAND_SHARE: Final[float] = 0.06


class AuditVerdict(StrEnum):
    """What the audit found on a page it read (analyze spec section 3), or
    NOT_AUDITED for a page it does not read."""

    MUCH_TEXT = "much_text"
    TEXT = "text"
    PICTURE = "picture"
    BLANK = "blank"
    NOT_AUDITED = "not_audited"


def is_text_word(word: Word) -> bool:
    """Whether `word`, read by Tesseract, is a text word: read at a
    confidence of 70 or more, with at least one letter or digit (analyze
    spec section 1). ValueError for a word with no confidence, one of a
    text layer."""
    if word.ocr_confidence is None:
        message = f"the word {word.text!r} has no confidence: it is not Tesseract's"
        raise ValueError(message)
    return word.ocr_confidence >= _TEXT_WORD_LEAST_CONFIDENCE and any(
        character.isalnum() for character in word.text
    )


def audit_verdict(words: tuple[Word, ...], ink: float) -> AuditVerdict:
    """MUCH_TEXT when 40 or more of `words` are text words, else TEXT when
    one is, else PICTURE when `ink`, the page's ink share from 0 to 1, is
    0.0008 or more, else BLANK (analyze spec section 3). `words` are every
    word Tesseract read on the page. Whether the plate rule takes the page
    is for `classify_page` to weigh."""
    text_words = sum(1 for word in words if is_text_word(word))
    if text_words >= _MUCH_TEXT_LEAST_WORDS:
        return AuditVerdict.MUCH_TEXT
    if text_words > 0:
        return AuditVerdict.TEXT
    if ink >= _PICTURE_LEAST_INK_SHARE:
        return AuditVerdict.PICTURE
    return AuditVerdict.BLANK


def ink_share(page: RenderedPage) -> float:
    """The share, from 0 to 1, of the page that is ink (analyze spec
    section 3), `page` rendered at 300 dpi: halved to 150 dpi, a pixel is
    ink when it is 15 levels or more darker than the mean of the 41 by 41
    pixels around it, counted without a band of 8% of the width at each
    side and 6% of the height at the top and foot. ValueError for a render
    at another dpi, on which the measures would mean other sizes."""
    if page.dpi != OCR_DPI:
        message = (
            f"page index {page.page_index}: the ink share is measured at "
            f"{OCR_DPI} dpi, not at {page.dpi}"
        )
        raise ValueError(message)
    return image_ink_share(
        Image.frombytes("L", (page.width_px, page.height_px), page.pixels)
    )


def image_ink_share(image: Image.Image) -> float:
    """The ink share of `ink_share`, for `image`, an 8-bit gray render of a
    page at 300 dpi that the caller has already made, so that a page read
    by Tesseract is not turned into an image twice."""
    halved = image.reduce(_HALVING)
    background = halved.filter(ImageFilter.BoxBlur(_BACKGROUND_RADIUS_PX))
    darkness = ImageChops.subtract(background, halved)
    width_px, height_px = halved.size
    side_px = int(width_px * _SIDE_BAND_SHARE)
    top_px = int(height_px * _TOP_AND_FOOT_BAND_SHARE)
    histogram = darkness.crop(
        (side_px, top_px, width_px - side_px, height_px - top_px)
    ).histogram()
    return sum(histogram[_INK_LEAST_LEVELS:]) / sum(histogram)
