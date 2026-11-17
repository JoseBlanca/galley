"""Tests of galley.ocr (docs/specs/reocr.md, sections 5, 6 and 9).

The unit tests parse Tesseract's tsv output written by hand and need no
Tesseract. The tests marked `tesseract` run it on an image drawn here.
"""

import pytest
from PIL import Image, ImageDraw, ImageFont

from galley.errors import ExternalProgramError
from galley.model import Box, Word
from galley.ocr import OCR_DPI, lines_of_tsv, read_image, words_of_tsv

_HEADER = (
    "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num"
    "\tleft\ttop\twidth\theight\tconf\ttext"
)


def _row(level: int, numbers: str, box: str, conf: str, text: str) -> str:
    return f"{level}\t1\t{numbers}\t{box}\t{conf}\t{text}"


# Two lines of three words, the second with a word of blank text; the rows
# of levels 1 to 4 (page, block, paragraph, line) carry no word.
_TSV = "\n".join(
    (
        _HEADER,
        _row(1, "0\t0\t0\t0", "0\t0\t600\t150", "-1", ""),
        _row(2, "1\t0\t0\t0", "0\t0\t600\t150", "-1", ""),
        _row(3, "1\t1\t0\t0", "0\t0\t600\t150", "-1", ""),
        _row(4, "1\t1\t1\t0", "0\t0\t390\t50", "-1", ""),
        _row(5, "1\t1\t1\t1", "0\t0\t120\t50", "96.5", "Stephen"),
        _row(5, "1\t1\t1\t2", "150\t0\t60\t50", "91", "of"),
        _row(5, "1\t1\t1\t3", "240\t0\t150\t50", "88.25", "Blois."),
        _row(4, "1\t1\t2\t0", "0\t100\t600\t50", "-1", ""),
        _row(5, "1\t1\t2\t1", "0\t100\t90\t50", "95", "King"),
        _row(5, "1\t1\t2\t2", "100\t100\t30\t50", "95", " "),
        _row(5, "1\t1\t2\t3", "150\t100\t60\t50", "40", "of"),
        _row(5, "1\t1\t2\t4", "240\t100\t360\t50", "93", "England"),
        "",
    )
)


def _expected(text: str, box: tuple[float, float, float, float], conf: float) -> Word:
    return Word(text, Box(*box), conf)


# At 300 dpi a pixel is 0.24 pt; the crop's top left lies at (100, 200) pt.
_EXPECTED_FIRST_LINE = (
    _expected("Stephen", (100, 200, 128.8, 212), 96.5),
    _expected("of", (136, 200, 150.4, 212), 91),
    _expected("Blois.", (157.6, 200, 193.6, 212), 88.25),
)
_EXPECTED_SECOND_LINE = (
    _expected("King", (100, 224, 121.6, 236), 95),
    _expected("of", (136, 224, 150.4, 236), 40),
    _expected("England", (157.6, 224, 244, 236), 93),
)


def _numbers(words: tuple[Word, ...]) -> tuple[float | None, ...]:
    """The four sides of each word's box and its confidence, in a row."""
    return tuple(
        number
        for word in words
        for number in (
            word.box.x0,
            word.box.top,
            word.box.x1,
            word.box.bottom,
            word.ocr_confidence,
        )
    )


def _assert_words(words: tuple[Word, ...], expected: tuple[Word, ...]) -> None:
    """`words` are `expected`, their numbers to a millionth."""
    assert [word.text for word in words] == [word.text for word in expected]
    assert _numbers(words) == pytest.approx(_numbers(expected))


def test_ocr_dpi_is_300() -> None:
    assert OCR_DPI == 300


def test_words_of_tsv_gives_boxes_in_points_confidences_and_tesseract_order() -> None:
    words = words_of_tsv(_TSV, origin=(100, 200), dpi=300)
    _assert_words(words, _EXPECTED_FIRST_LINE + _EXPECTED_SECOND_LINE)


def test_words_of_tsv_skips_a_word_of_blank_text() -> None:
    words = words_of_tsv(_TSV, origin=(0, 0), dpi=300)
    assert [word.text for word in words] == [
        "Stephen",
        "of",
        "Blois.",
        "King",
        "of",
        "England",
    ]


def test_words_of_tsv_strips_spaces_around_a_word() -> None:
    tsv = "\n".join(
        (_HEADER, _row(5, "1\t1\t1\t1", "0\t0\t30\t10", "90", " word "), "")
    )
    assert [word.text for word in words_of_tsv(tsv, origin=(0, 0), dpi=72)] == ["word"]


def test_lines_of_tsv_groups_words_by_block_paragraph_and_line() -> None:
    lines = lines_of_tsv(_TSV, origin=(100, 200), dpi=300)
    assert len(lines) == 2
    _assert_words(lines[0], _EXPECTED_FIRST_LINE)
    _assert_words(lines[1], _EXPECTED_SECOND_LINE)


def test_words_of_tsv_without_the_level_header_raises() -> None:
    plain_text = "Stephen of Blois.\nKing of England\n"
    with pytest.raises(ExternalProgramError, match="tsv header"):
        words_of_tsv(plain_text, origin=(0, 0), dpi=300)


def test_words_of_tsv_with_a_short_word_row_raises() -> None:
    tsv = f"{_HEADER}\n5\t1\t1\t1\t1\t1\t0\t0\t30\n"
    with pytest.raises(ExternalProgramError, match="12 fields"):
        words_of_tsv(tsv, origin=(0, 0), dpi=300)


def test_words_of_tsv_with_a_box_that_is_not_a_number_raises() -> None:
    tsv = "\n".join((_HEADER, _row(5, "1\t1\t1\t1", "0\tx\t30\t10", "90", "a"), ""))
    with pytest.raises(ExternalProgramError, match="not a number"):
        words_of_tsv(tsv, origin=(0, 0), dpi=300)


# read_image, with Tesseract


def _drawn_words(text: str) -> Image.Image:
    """A white image with `text` drawn in black, 60 px high, at (40, 40)."""
    image = Image.new("L", (900, 160), 255)
    font = ImageFont.load_default(size=60)
    ImageDraw.Draw(image).text((40, 40), text, fill=0, font=font)
    return image


@pytest.mark.tesseract
def test_read_image_reads_drawn_words_with_boxes_on_the_page() -> None:
    image = _drawn_words("Stephen of Blois")
    words = read_image(image, origin=(100, 200), dpi=300, psm=6, language="eng")
    assert [word.text for word in words] == ["Stephen", "of", "Blois"]
    # The image is 900 by 160 px, 216 by 38.4 pt at 300 dpi, from (100, 200).
    for word in words:
        assert 100 < word.box.x0 < word.box.x1 < 316
        assert 200 < word.box.top < word.box.bottom < 238.4
        assert word.ocr_confidence is not None


@pytest.mark.tesseract
def test_read_image_with_a_language_tesseract_lacks_raises_naming_it() -> None:
    image = _drawn_words("Stephen")
    with pytest.raises(ExternalProgramError, match="xxq"):
        read_image(image, origin=(0, 0), dpi=300, psm=6, language="xxq")
