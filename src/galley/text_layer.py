"""Reading the text layer of a PDF with pdfplumber: opening the PDF, and
the words of a page (extract spec sections 3 to 5).

Every pdfplumber document galley reads is opened by `open_pdf`, which
opens one document at a time in the whole process. Reading the pages of
the documents it opened stays parallel, one document per worker thread.

The lock is there because pdfminer.six 20260107, which pdfplumber reads
PDFs with, is not safe to open from two threads at once. It keeps every
keyword it meets, such as `trailer`, in one dictionary that all threads
share, and adds a new one by checking for it and then storing it
(`PSSymbolTable.intern` in psparser.py), with no lock. Two threads that
meet `trailer` for the first time can each store a keyword object of
their own, the second replacing the first. Opening a PDF then checks that
the keyword it read is the stored one by identity (`assert kwd is
KWD(b"trailer")` in `PDFXRef.load_trailer`, pdfdocument.py), and that
fails in the thread whose object was replaced: `pdfplumber.open` raises
`PdfminerException: /b'trailer'`. Measured on 14 November 2026 on an M5
Pro: 3 of 450 fresh processes running analyze and extract on the whole
Kadesh book with 6, 12 and 24 workers failed so, and 0 of 150 with 1
worker. It can happen only while a process first meets the keyword, which
is while documents open, so the lock is held only then.
"""

import statistics
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import pdfplumber
from pdfplumber.page import Page
from pdfplumber.utils.exceptions import PdfminerException
from pdfplumber.utils.text import LIGATURES

from galley.errors import PdfError
from galley.model import Box, Word

__all__ = ["Character", "layer_words", "open_pdf", "split_glued"]

_OPEN_LOCK = threading.Lock()

# Extract spec section 4: a gap inside a word of the text flow is a space
# between two glued words when it is at least this fraction of the median
# width of the word's characters. Chosen on every such gap of Haskins and
# Stubbs judged by the word list: from a third up, 5,570 cuts were right
# and 26 wrong; from 0.25 to a third, 45 right and 13 wrong.
_GLUED_GAP_IN_CHARACTER_WIDTHS: Final[float] = 1 / 3
# Extract spec section 4: the marks a glued word may start with after a
# letter, and those it may end with before a letter. A straight quote is
# only a closing mark: inside a word something always comes before it.
_OPENING_MARKS: Final[frozenset[str]] = frozenset("([‘“")
_CLOSING_MARKS: Final[frozenset[str]] = frozenset(",.;:!?)]'\"’”")


def open_pdf(pdf: Path) -> pdfplumber.PDF:
    """`pdf` opened with pdfplumber, to be closed by the caller (it is a
    context manager). Only one thread of the process opens a document at a
    time; the document is then used by the thread that opened it alone.

    A file pdfplumber cannot read as a PDF, such as a truncated one, is a
    PdfError naming it, whose cause is pdfplumber's PdfminerException.
    """
    with _OPEN_LOCK:
        try:
            return pdfplumber.open(pdf)
        except PdfminerException as err:
            message = f"{pdf}: pdfplumber cannot read it as a PDF: {err}"
            raise PdfError(message) from err


@dataclass(frozen=True, slots=True)
class Character:
    """One glyph of the text layer: `text`, one character, and `box`, in
    points."""

    text: str
    box: Box


def split_glued(characters: tuple[Character, ...]) -> tuple[tuple[Character, ...], ...]:
    """The characters of one word of pdfplumber's text flow, in order, cut
    into the words that the OCR left glued (extract spec section 4).

    A word is cut between two characters when the gap from the right side
    of the first to the left side of the second is at least a third of the
    median width of the word's characters, and the first is a letter and
    the second a letter or an opening mark, or the first a closing mark and
    the second a letter. So a word is never cut at a digit, a hyphen or a
    dash, nor between two marks. The parts keep their order; a word with
    no such gap comes back as one part, and no part comes back empty.
    """
    if not characters:
        return ()
    median_width_pt = statistics.median(
        character.box.x1 - character.box.x0 for character in characters
    )
    least_gap_pt = median_width_pt * _GLUED_GAP_IN_CHARACTER_WIDTHS
    cuts = tuple(
        index
        for index in range(1, len(characters))
        if _glued_at(characters[index - 1], characters[index], least_gap_pt)
    )
    starts = (0, *cuts)
    ends = (*cuts, len(characters))
    return tuple(characters[start:end] for start, end in zip(starts, ends, strict=True))


def _glued_at(before: Character, after: Character, least_gap_pt: float) -> bool:
    """Whether a glued word ends at `before` and the next starts at `after`."""
    if after.box.x0 - before.box.x1 < least_gap_pt:
        return False
    if before.text.isalpha():
        return after.text.isalpha() or after.text in _OPENING_MARKS
    return before.text in _CLOSING_MARKS and after.text.isalpha()


def layer_words(page: Page) -> tuple[Word, ...]:
    """The words of `page`'s text layer, in the PDF's order: those of
    pdfplumber's `extract_words(use_text_flow=True)`, each cut by
    `split_glued` (extract spec sections 3 and 4). A word's box is the
    smallest that holds its characters, and its `ocr_confidence` is None.
    A ligature, such as "ﬁ", is written as its letters, as pdfplumber
    writes it.
    """
    return tuple(
        _word(part)
        for layer_word in page.extract_words(use_text_flow=True, return_chars=True)
        for part in split_glued(
            tuple(
                Character(
                    str(character["text"]),
                    Box(
                        float(character["x0"]),
                        float(character["top"]),
                        float(character["x1"]),
                        float(character["bottom"]),
                    ),
                )
                for character in layer_word["chars"]
            )
        )
    )


def _word(characters: tuple[Character, ...]) -> Word:
    """The word made of `characters`, with the box that holds them all."""
    return Word(
        "".join(
            LIGATURES.get(character.text, character.text) for character in characters
        ),
        Box(
            min(character.box.x0 for character in characters),
            min(character.box.top for character in characters),
            max(character.box.x1 for character in characters),
            max(character.box.bottom for character in characters),
        ),
        None,
    )
