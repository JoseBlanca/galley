"""Tesseract, the OCR program, run on an image of part of a page.

`read_image` writes the image as a PNG to Tesseract's standard input and
reads back its tsv output, Tesseract's table of what it read: one row per
word, with the word's box in pixels of the image, its confidence from 0
to 100, and the numbers of its block, paragraph and line. `words_of_tsv`
and `lines_of_tsv` are the pure part: they turn that table into galley's
`Word`s, with boxes in PDF points on the page (docs/specs/reocr.md,
sections 4 to 6).

Adapted from `tesseract_words` in the owner's ocr_lab
(`~/devel/tomato_history_web_site/tools/ocr_lab/lib/common.py`), without
its cache. Layout calls it now; analyze's audit and extract's OCR pages
will (architecture section 7b).
"""

import io
import itertools
import os
import shutil
import subprocess
from collections.abc import Callable
from typing import Final

from PIL import Image

from galley.errors import ExternalProgramError
from galley.model import Box, Word
from galley.pdfium import POINTS_PER_INCH

__all__ = [
    "OCR_DPI",
    "lines_of_tsv",
    "point_box",
    "read_image",
    "read_image_lines",
    "words_of_tsv",
]

# The resolution galley renders a page at for Tesseract (reocr spec,
# section 3): the measurements of that spec were taken at it.
OCR_DPI: Final[int] = 300

# Guessed (reocr spec, section 5): 100 times the slowest whole page
# measured, 0.88 s, with room for a slow machine.
_TIMEOUT_S: Final[float] = 120.0

_TSV_HEADER: Final[str] = "level\t"
_WORD_LEVEL: Final[str] = "5"
_TSV_FIELDS: Final[int] = 12
# How much of Tesseract's output or error output an error message quotes.
_QUOTED_CHARACTERS: Final[int] = 300


def point_box(
    box: tuple[int, int, int, int], *, origin: tuple[float, float], dpi: int
) -> Box:
    """The box in points on the page of `box`, a Pillow crop box in pixels
    (left, top, right, bottom) of an image rendered at `dpi` whose top left
    lies at `origin`, (left, top) in points."""
    scale = POINTS_PER_INCH / dpi
    left, top = origin
    return Box(
        left + box[0] * scale,
        top + box[1] * scale,
        left + box[2] * scale,
        top + box[3] * scale,
    )


def _field_number(row: str, field: str, convert: Callable[[str], float]) -> float:
    """`field` of the tsv `row` as a number; ExternalProgramError when it is
    not one."""
    try:
        return convert(field)
    except ValueError as err:
        msg = (
            f"Tesseract's tsv row {row!r} has {field!r} where a number is, not a number"
        )
        raise ExternalProgramError(msg) from err


def _word_rows(tsv: str) -> tuple[tuple[str, tuple[str, ...]], ...]:
    """The rows of `tsv` that are words, each as the row and its fields:
    level 5, with text that is not blank. ExternalProgramError when `tsv`
    does not start with the tsv header or a word's row is short."""
    if not tsv.startswith(_TSV_HEADER):
        msg = (
            "Tesseract's output does not start with the tsv header "
            f"{_TSV_HEADER!r}: {tsv[:_QUOTED_CHARACTERS]!r}"
        )
        raise ExternalProgramError(msg)
    rows = []
    for row in tsv.splitlines()[1:]:
        fields = tuple(row.split("\t"))
        if fields[0] != _WORD_LEVEL:
            continue
        if len(fields) < _TSV_FIELDS:
            msg = f"Tesseract's tsv row {row!r} has fewer than {_TSV_FIELDS} fields"
            raise ExternalProgramError(msg)
        if fields[11].strip():
            rows.append((row, fields))
    return tuple(rows)


def lines_of_tsv(
    tsv: str, *, origin: tuple[float, float], dpi: int
) -> tuple[tuple[Word, ...], ...]:
    """The words of Tesseract's tsv output `tsv`, grouped by Tesseract's
    lines (its block, paragraph and line numbers), in its order.

    The image Tesseract read was rendered at `dpi` and its top left lies at
    `origin`, (left, top) in points, on the page: a word's box is its pixel
    box divided by `dpi`/72 and moved by `origin`. A word's text is the
    tsv's, stripped of spaces; a row of blank text is not a word. Its
    `ocr_confidence` is the tsv's confidence. ExternalProgramError when
    `tsv` is not tsv output (Tesseract prints plain text when it lacks a
    setting, and exits with 0).
    """
    numbered = []
    for row, fields in _word_rows(tsv):
        x_px, y_px, width_px, height_px = (
            int(_field_number(row, field, int)) for field in fields[6:10]
        )
        box = point_box(
            (x_px, y_px, x_px + width_px, y_px + height_px), origin=origin, dpi=dpi
        )
        word = Word(fields[11].strip(), box, _field_number(row, fields[10], float))
        numbered.append((fields[1:5], word))
    return tuple(
        tuple(word for _, word in line)
        for _, line in itertools.groupby(numbered, key=lambda pair: pair[0])
    )


def words_of_tsv(
    tsv: str, *, origin: tuple[float, float], dpi: int
) -> tuple[Word, ...]:
    """The words of Tesseract's tsv output `tsv`, in its order (block,
    paragraph, line, word), as `lines_of_tsv` gives them."""
    return tuple(
        word for line in lines_of_tsv(tsv, origin=origin, dpi=dpi) for word in line
    )


def _tesseract_tsv(image: Image.Image, psm: int, language: str) -> str:
    """Tesseract's tsv output for `image`, read with page segmentation mode
    `psm` and the language data `language` (Tesseract's code, "eng")."""
    executable = shutil.which("tesseract")
    if executable is None:
        msg = "tesseract is not installed; install it with `brew install tesseract`"
        raise ExternalProgramError(msg)
    png = io.BytesIO()
    image.save(png, format="PNG")
    command = [
        executable,
        "stdin",
        "stdout",
        "--psm",
        str(psm),
        "-l",
        language,
        "tsv",
    ]
    # One Tesseract uses one core: the parallelism is galley's threads.
    environment = {**os.environ, "OMP_THREAD_LIMIT": "1"}
    try:
        completed = subprocess.run(
            command,
            input=png.getvalue(),
            capture_output=True,
            check=True,
            timeout=_TIMEOUT_S,
            env=environment,
        )
    except subprocess.CalledProcessError as err:
        error_output = err.stderr.decode("utf-8", errors="replace")
        msg = (
            f"tesseract failed with exit status {err.returncode} on the language "
            f"{language!r}: {error_output[:_QUOTED_CHARACTERS]}"
        )
        raise ExternalProgramError(msg) from err
    except subprocess.TimeoutExpired as err:
        msg = f"tesseract did not finish in {_TIMEOUT_S:.0f} s on the language {language!r}"
        raise ExternalProgramError(msg) from err
    output = completed.stdout.decode("utf-8")
    if not output.startswith(_TSV_HEADER):
        error_output = completed.stderr.decode("utf-8", errors="replace")
        msg = (
            f"tesseract printed no tsv output on the language {language!r}: "
            f"{error_output[:_QUOTED_CHARACTERS] or output[:_QUOTED_CHARACTERS]}"
        )
        raise ExternalProgramError(msg)
    return output


def read_image_lines(
    image: Image.Image,
    *,
    origin: tuple[float, float],
    dpi: int,
    psm: int,
    language: str,
) -> tuple[tuple[Word, ...], ...]:
    """Tesseract's words of `image`, grouped by its lines, as `lines_of_tsv`
    gives them; for a reading whose lines are filtered (reocr spec,
    section 3, kind 3). The arguments are those of `read_image`."""
    return lines_of_tsv(_tesseract_tsv(image, psm, language), origin=origin, dpi=dpi)


def read_image(
    image: Image.Image,
    *,
    origin: tuple[float, float],
    dpi: int,
    psm: int,
    language: str,
) -> tuple[Word, ...]:
    """Tesseract's words of `image`, a crop of a page rendered at `dpi`
    whose top left lies at `origin`, (left, top) in points, on the page,
    with boxes in points on the page and Tesseract's confidences.

    `psm` is Tesseract's page segmentation mode (3 finds blocks on a whole
    page, 6 reads one block of lines) and `language` Tesseract's code of
    the language data, `config.tesseract_language(config.language)`. One
    Tesseract runs per call, on one core. ExternalProgramError when
    Tesseract is missing, fails, lacks the language or prints no tsv.
    """
    return tuple(
        word
        for line in read_image_lines(
            image, origin=origin, dpi=dpi, psm=psm, language=language
        )
        for word in line
    )
