"""Tests of galley.text_layer: opening a PDF (walking skeleton spec
sections 4 and 6), and reading a page's words (extract spec sections 3 to
5). The characters of the split_glued tests are copied from the text layers
of the whole books, page indices from 0, their boxes rounded to 0.01 pt.

The race test replaces pdfminer's table of keywords, which every thread
shares, so it is marked thread_unsafe: `pytest --parallel-threads=8` runs
it once.
"""

import threading
from collections import Counter
from collections.abc import Callable, Iterator
from contextlib import closing
from pathlib import Path
from typing import Final, override

import pdfplumber
import pytest
from pdfminer import psparser
from pdfplumber.utils.exceptions import PdfminerException
from pdfplumber.utils.text import LIGATURES

from galley.errors import PdfError
from galley.model import Box, Word
from galley.parallel import DEFAULT_WORKERS, map_pages_with_source
from galley.text_layer import Character, _word, layer_words, open_pdf, split_glued

KADESH = "kadesh_8-17"
THREADS_AT_ONCE: Final[int] = 4
TRAILER: Final[bytes] = b"trailer"
# How long a thread waits for the others in the table below. Without the
# lock they all arrive within milliseconds; with it, each wait runs out.
WAIT_FOR_OTHERS_S: Final[float] = 0.2


type _Name = str | bytes


class _TrailerRaceTable(dict[_Name, psparser.PSKeyword]):
    """pdfminer's keyword table without `trailer`, in which the race of
    PSSymbolTable.intern (check, then store) happens every time it can.

    A thread that does not find `trailer` waits until every thread has not
    found it, and a thread that stores it waits until every thread has
    stored its own, so that each thread's later lookup finds the keyword
    stored last. Each wait ends after WAIT_FOR_OTHERS_S, as it does when
    the threads open one after the other.
    """

    def __init__(
        self, entries: dict[_Name, psparser.PSKeyword], thread_count: int
    ) -> None:
        super().__init__(
            (name, keyword) for name, keyword in entries.items() if name != TRAILER
        )
        self._count_lock = threading.Lock()
        self._thread_count = thread_count
        self._misses = 0
        self._stores = 0
        self._all_missed = threading.Event()
        self._all_stored = threading.Event()

    @override
    def __contains__(self, name: object) -> bool:
        found = super().__contains__(name)
        if name == TRAILER and not found:
            self._count(self._all_missed, stores=False)
        return found

    @override
    def __setitem__(self, name: _Name, keyword: psparser.PSKeyword) -> None:
        super().__setitem__(name, keyword)
        if name == TRAILER:
            self._count(self._all_stored, stores=True)

    def _count(self, everyone: threading.Event, *, stores: bool) -> None:
        with self._count_lock:
            if stores:
                self._stores += 1
                arrived = self._stores
            else:
                self._misses += 1
                arrived = self._misses
            if arrived == self._thread_count:
                everyone.set()
        everyone.wait(WAIT_FOR_OTHERS_S)


@pytest.fixture
def trailer_race() -> Iterator[None]:
    """pdfminer's keyword table replaced by a _TrailerRaceTable for the
    test, and the original put back after it, whatever its outcome."""
    original = psparser.PSKeywordTable.dict
    psparser.PSKeywordTable.dict = _TrailerRaceTable(original, THREADS_AT_ONCE)
    yield
    psparser.PSKeywordTable.dict = original


def _open_at_once(
    open_document: Callable[[Path], pdfplumber.PDF], pdf: Path
) -> tuple[str, ...]:
    """The errors of THREADS_AT_ONCE threads each opening and closing its own
    document of `pdf` with `open_document`, as `type: message`."""
    errors: list[str] = []
    errors_lock = threading.Lock()

    def open_and_close() -> None:
        # The exception is recorded so that the test can count them; a
        # thread's own exception would only reach threading.excepthook.
        try:
            with open_document(pdf):
                pass
        except (PdfminerException, PdfError) as err:
            with errors_lock:
                errors.append(f"{type(err).__name__}: {err}")

    threads = tuple(
        threading.Thread(target=open_and_close) for _ in range(THREADS_AT_ONCE)
    )
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return tuple(errors)


@pytest.mark.thread_unsafe
@pytest.mark.usefixtures("trailer_race")
def test_pdfplumber_open_from_threads_at_once_raises_trailer_error(
    excerpt_pdf: frozendict[str, Path],
) -> None:
    # The race the lock prevents: every thread but the one that stored the
    # keyword last fails.
    errors = _open_at_once(pdfplumber.open, excerpt_pdf[KADESH])
    assert errors == ("PdfminerException: /b'trailer'",) * (THREADS_AT_ONCE - 1)


@pytest.mark.thread_unsafe
@pytest.mark.usefixtures("trailer_race")
def test_open_pdf_from_threads_at_once_raises_nothing(
    excerpt_pdf: frozendict[str, Path],
) -> None:
    assert _open_at_once(open_pdf, excerpt_pdf[KADESH]) == ()


def test_open_pdf_gives_the_pages_of_the_excerpt(
    excerpt_pdf: frozendict[str, Path],
) -> None:
    with open_pdf(excerpt_pdf[KADESH]) as pdf:
        assert len(pdf.pages) == 10


def test_open_pdf_of_a_truncated_pdf_raises_pdf_error_naming_it(
    excerpt_pdf: frozendict[str, Path], tmp_path: Path
) -> None:
    whole = excerpt_pdf[KADESH].read_bytes()
    truncated = tmp_path / "truncated.pdf"
    truncated.write_bytes(whole[: len(whole) // 2])
    with pytest.raises(PdfError, match="truncated.pdf") as caught:
        open_pdf(truncated)
    assert isinstance(caught.value.__cause__, PdfminerException)


def test_open_pdf_of_a_text_file_raises_pdf_error_naming_it(tmp_path: Path) -> None:
    text_file = tmp_path / "not_a.pdf"
    text_file.write_text("This is a text file, not a PDF.\n", encoding="utf-8")
    with pytest.raises(PdfError, match="not_a.pdf") as caught:
        open_pdf(text_file)
    assert isinstance(caught.value.__cause__, PdfminerException)


def _words(parts: tuple[tuple[Character, ...], ...]) -> tuple[str, ...]:
    return tuple("".join(character.text for character in part) for part in parts)


def _glyphs(
    text: str, boxes: tuple[tuple[float, float, float, float], ...]
) -> tuple[Character, ...]:
    """The characters of `text`, one per box, in order."""
    assert len(text) == len(boxes)
    return tuple(
        Character(glyph, Box(*box)) for glyph, box in zip(text, boxes, strict=True)
    )


# Haskins' page 12, "This book rests partly upon": four gaps of 2.5 to 2.9
# pt, with characters 4.4 to 5.9 pt wide.
THIS_BOOK_RESTS = _glyphs(
    "Thisbookrestspartlyupon",
    (
        (31.50, 453.85, 36.90, 462.85),
        (36.90, 453.85, 42.30, 462.85),
        (42.30, 453.85, 47.70, 462.85),
        (47.70, 453.85, 53.10, 462.85),
        (55.62, 453.42, 61.47, 463.17),
        (61.47, 453.42, 67.32, 463.17),
        (67.32, 453.42, 73.17, 463.17),
        (73.17, 453.42, 79.02, 463.17),
        (81.72, 455.43, 86.08, 462.69),
        (86.08, 455.43, 90.43, 462.69),
        (90.43, 455.43, 94.79, 462.69),
        (94.79, 455.43, 99.14, 462.69),
        (99.14, 455.43, 103.50, 462.69),
        (106.38, 454.75, 111.24, 462.85),
        (111.24, 454.75, 116.10, 462.85),
        (116.10, 454.75, 120.96, 462.85),
        (120.96, 454.75, 125.82, 462.85),
        (125.82, 454.75, 130.68, 462.85),
        (130.68, 454.75, 135.54, 462.85),
        (138.42, 453.36, 144.31, 463.19),
        (144.31, 453.36, 150.21, 463.19),
        (150.21, 453.36, 156.10, 463.19),
        (156.10, 453.36, 162.00, 463.19),
    ),
)


def test_split_glued_cuts_a_glued_line_at_its_word_gaps() -> None:
    parts = split_glued(THIS_BOOK_RESTS)
    assert _words(parts) == ("This", "book", "rests", "partly", "upon")
    assert parts[1] == THIS_BOOK_RESTS[4:8]


def test_split_glued_does_not_cut_a_number_at_a_wide_gap() -> None:
    # Haskins' page 157, "13|15,": a gap of 1.8 pt, characters 4.0 to 4.7
    # pt wide.
    number = _glyphs(
        "1315,",
        (
            (244.68, 140.13, 249.35, 147.91),
            (249.35, 140.13, 254.02, 147.91),
            (255.82, 141.55, 259.83, 148.24),
            (259.83, 141.55, 263.85, 148.24),
            (263.85, 141.55, 267.86, 148.24),
        ),
    )
    assert split_glued(number) == (number,)


def test_split_glued_cuts_after_a_closing_mark_but_not_inside_a_compound() -> None:
    # Haskins' page 206, "Henry Adams, Mont-Saint-Michel": gaps of 2.0 and
    # 2.9 pt between the words, and of 0.55 pt after the second hyphen.
    glued = _glyphs(
        "HenryAdams,Mont-Saint-Michel",
        (
            (158.81, 122.24, 163.63, 130.27),
            (163.63, 122.24, 168.44, 130.27),
            (168.44, 122.24, 173.26, 130.27),
            (173.26, 122.24, 178.07, 130.27),
            (178.07, 122.24, 182.89, 130.27),
            (184.86, 122.32, 189.62, 130.25),
            (189.62, 122.32, 194.38, 130.25),
            (194.38, 122.32, 199.14, 130.25),
            (199.14, 122.32, 203.90, 130.25),
            (203.90, 122.32, 208.67, 130.25),
            (208.67, 122.32, 213.43, 130.25),
            (216.30, 123.14, 220.45, 130.05),
            (220.45, 123.14, 224.59, 130.05),
            (224.59, 123.14, 228.74, 130.05),
            (228.74, 123.14, 232.89, 130.05),
            (232.89, 123.14, 237.04, 130.05),
            (237.04, 123.14, 241.19, 130.05),
            (241.19, 123.14, 245.33, 130.05),
            (245.33, 123.14, 249.48, 130.05),
            (249.48, 123.14, 253.63, 130.05),
            (253.63, 123.14, 257.78, 130.05),
            (257.78, 123.14, 261.92, 130.05),
            (262.47, 123.40, 266.69, 130.44),
            (266.69, 123.40, 270.91, 130.44),
            (270.91, 123.40, 275.14, 130.44),
            (275.14, 123.40, 279.36, 130.44),
            (279.36, 123.40, 283.58, 130.44),
            (283.58, 123.40, 287.80, 130.44),
        ),
    )
    assert _words(split_glued(glued)) == ("Henry", "Adams,", "Mont-Saint-Michel")


def test_split_glued_does_not_cut_at_a_dash() -> None:
    # Stubbs' page 45, "first—came": a gap of 1.6 pt after the dash, more
    # than a third of the characters' median width, 4.6 pt.
    dashed = _glyphs(
        "first—came",
        (
            (232.71, 263.16, 237.26, 270.75),
            (237.26, 263.16, 241.82, 270.75),
            (241.82, 263.16, 246.37, 270.75),
            (246.37, 263.16, 250.92, 270.75),
            (250.92, 263.16, 255.47, 270.75),
            (255.47, 263.16, 260.02, 270.75),
            (261.64, 261.01, 267.80, 271.27),
            (267.80, 261.01, 273.95, 271.27),
            (273.95, 261.01, 280.11, 271.27),
            (280.11, 261.01, 286.26, 271.27),
        ),
    )
    assert split_glued(dashed) == (dashed,)


def test_split_glued_does_not_cut_before_a_digit_after_a_letter() -> None:
    # Stubbs' page 15, "Page58": a gap of 2.7 pt before the "5", as before a
    # note reference glued to its word ("land3.").
    page_number = _glyphs(
        "Page58",
        (
            (267.21, 115.34, 272.11, 123.51),
            (272.11, 115.34, 277.01, 123.51),
            (277.01, 115.34, 281.91, 123.51),
            (281.91, 115.34, 286.80, 123.51),
            (289.50, 116.91, 293.63, 123.80),
            (293.63, 116.91, 297.76, 123.80),
        ),
    )
    assert split_glued(page_number) == (page_number,)


def test_split_glued_does_not_cut_before_a_straight_quote_that_closes() -> None:
    # Stubbs' page 325, `told."`: a gap of 1.8 pt before the quote.
    quoted = _glyphs(
        'told."',
        (
            (87.69, 394.49, 91.47, 400.78),
            (91.47, 394.49, 95.24, 400.78),
            (95.24, 394.49, 99.01, 400.78),
            (99.01, 394.49, 102.79, 400.78),
            (102.79, 394.49, 106.56, 400.78),
            (108.36, 392.57, 112.49, 399.46),
        ),
    )
    assert split_glued(quoted) == (quoted,)


def test_split_glued_does_not_cut_between_two_marks() -> None:
    # Stubbs' page 318, "II.'s": a gap of 1.3 pt between the full stop and
    # the apostrophe, characters 2.6 to 2.9 pt wide.
    possessive = _glyphs(
        "II.'s",
        (
            (256.07, 183.47, 258.95, 188.26),
            (258.95, 183.47, 261.82, 188.26),
            (261.82, 183.47, 264.70, 188.26),
            (265.96, 184.19, 268.56, 188.54),
            (268.56, 184.19, 271.17, 188.54),
        ),
    )
    assert split_glued(possessive) == (possessive,)


def test_split_glued_cuts_before_an_opening_mark() -> None:
    # Haskins' page 99, "siecle (Paris,": a gap of 2.15 pt before the
    # parenthesis, characters 3.1 to 3.4 pt wide.
    glued = _glyphs(
        "siecle(Paris,",
        (
            (249.17, 157.45, 252.32, 162.69),
            (252.32, 157.45, 255.46, 162.69),
            (255.46, 157.45, 258.61, 162.69),
            (258.61, 157.45, 261.75, 162.69),
            (261.75, 157.45, 264.90, 162.69),
            (264.90, 157.45, 268.04, 162.69),
            (270.19, 157.05, 273.63, 162.78),
            (273.63, 157.05, 277.07, 162.78),
            (277.07, 157.05, 280.51, 162.78),
            (280.51, 157.05, 283.95, 162.78),
            (283.95, 157.05, 287.39, 162.78),
            (287.39, 157.05, 290.82, 162.78),
            (290.82, 157.05, 294.26, 162.78),
        ),
    )
    assert _words(split_glued(glued)) == ("siecle", "(Paris,")


def test_split_glued_does_not_cut_a_gap_under_a_third_of_a_character() -> None:
    # The first four characters of THIS_BOOK_RESTS with the "b" moved to a
    # gap of 1.7 pt, under a third of the median width, 5.4 pt.
    narrow = (*THIS_BOOK_RESTS[:4], Character("b", Box(54.80, 453.42, 60.65, 463.17)))
    assert split_glued(narrow) == (narrow,)


def test_split_glued_measures_an_even_word_by_the_larger_middle_width() -> None:
    # Stubbs' page 207, "A.d." for "A.D.": a gap of 1.44 pt before the "d".
    # The middle widths are 4.13 and 4.49 pt: a third of the larger is 1.50
    # pt, and the word stays whole; a third of their mean, 1.44 pt, would
    # cut it.
    initials = _glyphs(
        "A.d.",
        (
            (275.84, 37.66, 279.97, 44.55),
            (279.97, 37.66, 284.10, 44.55),
            (285.54, 37.36, 290.04, 44.85),
            (290.04, 37.36, 294.53, 44.85),
        ),
    )
    assert split_glued(initials) == (initials,)


def test_split_glued_gives_a_word_of_one_character_whole() -> None:
    single = (Character("a", Box(10.0, 20.0, 15.0, 29.0)),)
    assert split_glued(single) == (single,)


def test_split_glued_does_not_cut_after_a_hyphen_at_a_wide_gap() -> None:
    # Stubbs' page 218, "church-revenue,": a gap of 1.8 pt after the hyphen,
    # more than a third of the characters' median width, 5.0 pt.
    compound = _glyphs(
        "church-revenue,",
        (
            (92.01, 80.39, 97.24, 89.11),
            (97.24, 80.39, 102.48, 89.11),
            (102.48, 80.39, 107.72, 89.11),
            (107.72, 80.39, 112.95, 89.11),
            (112.95, 80.39, 118.19, 89.11),
            (118.19, 80.39, 123.43, 89.11),
            (123.43, 80.39, 128.66, 89.11),
            (130.46, 80.18, 135.45, 88.49),
            (135.45, 80.18, 140.44, 88.49),
            (140.44, 80.18, 145.42, 88.49),
            (145.42, 80.18, 150.41, 88.49),
            (150.41, 80.18, 155.40, 88.49),
            (155.40, 80.18, 160.38, 88.49),
            (160.38, 80.18, 165.37, 88.49),
            (165.37, 80.18, 170.36, 88.49),
        ),
    )
    assert split_glued(compound) == (compound,)


def test_split_glued_does_not_cut_after_a_digit_before_a_letter() -> None:
    # Haskins' page 58, "263ff." read as "263Jf.": a gap of 2.2 pt after the
    # "3", more than a third of the median width, 4.0 pt.
    page_reference = _glyphs(
        "263Jf.",
        (
            (85.87, 473.46, 89.88, 480.15),
            (89.88, 473.46, 93.90, 480.15),
            (93.90, 473.46, 97.91, 480.15),
            (100.07, 475.87, 102.82, 480.46),
            (102.82, 475.87, 105.58, 480.46),
            (105.58, 475.87, 108.33, 480.46),
        ),
    )
    assert split_glued(page_reference) == (page_reference,)


# No page of the six books has a wide gap at the marks below, nor a ligature
# glyph, so their characters are made up: 4 pt wide, with a gap of 2 pt, half
# a character, before the character at `gap_before`.
GLYPH_WIDTH_PT: Final[float] = 4.0
WIDE_GAP_PT: Final[float] = 2.0


def _spaced(
    text: str, gap_before: int, width_pt: float = GLYPH_WIDTH_PT
) -> tuple[Character, ...]:
    """The characters of `text` side by side, `width_pt` wide, with a gap of
    WIDE_GAP_PT before the one at index `gap_before`."""
    return tuple(
        Character(
            glyph,
            Box(
                index * width_pt + (WIDE_GAP_PT if index >= gap_before else 0.0),
                20.0,
                (index + 1) * width_pt + (WIDE_GAP_PT if index >= gap_before else 0.0),
                29.0,
            ),
        )
        for index, glyph in enumerate(text)
    )


@pytest.mark.parametrize("mark", tuple(",.;:!?)]'\"’”"))
def test_split_glued_cuts_after_each_closing_mark_before_a_letter(mark: str) -> None:
    glued = _spaced(f"ab{mark}cd", 3)
    assert _words(split_glued(glued)) == (f"ab{mark}", "cd")


@pytest.mark.parametrize("mark", tuple("([‘“"))
def test_split_glued_cuts_before_each_opening_mark_after_a_letter(mark: str) -> None:
    glued = _spaced(f"ab{mark}cd", 2)
    assert _words(split_glued(glued)) == ("ab", f"{mark}cd")


def test_split_glued_does_not_cut_between_a_closing_and_an_opening_mark() -> None:
    marks = _spaced("ab,(cd", 3)
    assert split_glued(marks) == (marks,)


def test_split_glued_cuts_a_gap_of_exactly_a_third_of_a_character() -> None:
    # Characters 6 pt wide: the gap of 2 pt is exactly a third of them.
    glued = _spaced("abcd", 2, width_pt=3 * WIDE_GAP_PT)
    assert _words(split_glued(glued)) == ("ab", "cd")


def test_layer_word_writes_a_ligature_as_its_letters() -> None:
    assert _word(_spaced("ﬁne", 3)).text == "fine"


def test_layer_words_of_haskins_page_12_gives_its_glued_line_split(
    excerpt_pdf: frozendict[str, Path],
) -> None:
    # Excerpt page 5 of haskins_front is Haskins' page 12.
    with open_pdf(excerpt_pdf["haskins_front"]) as pdf:
        words = layer_words(pdf.pages[5])
    texts = tuple(word.text for word in words)
    start = next(
        index
        for index, text in enumerate(texts)
        if texts[index : index + 2] == ("This", "book")
    )
    assert texts[start : start + 5] == ("This", "book", "rests", "partly", "upon")
    assert words[start] == Word("This", Box(31.5, 453.846, 53.1, 462.846), None)


def test_layer_words_takes_the_characters_in_the_pdfs_order(
    excerpt_pdf: frozendict[str, Path],
) -> None:
    # Excerpt page 7 of domesday_front_flow is Domesday's page 23, where
    # sorting by position cut ", some" into "s" and "ome".
    with open_pdf(excerpt_pdf["domesday_front_flow"]) as pdf:
        texts = tuple(word.text for word in layer_words(pdf.pages[7]))
    assert "some" in texts
    assert "s" not in texts
    assert "ome" not in texts


# The whole books (extract spec section 7, "Whole books")

# Extract spec section 4, the table of what the split changes: each book's
# words after both rules, measured on 17 November 2026 with pdfplumber
# 0.11.10.
WORDS_AFTER_BOTH_RULES = frozendict(
    {
        "normansineuropea00hask": 69_028,
        "earlyplantagenet01stub": 104_429,
        "domesdaybook00maituoft": 251_053,
        "politicaltheorie00gieruoft": 112_270,
        "battleofkadeshst00breauoft": 24_188,
    }
)


def _page_count(pdf_path: Path) -> int:
    with open_pdf(pdf_path) as pdf:
        return len(pdf.pages)


def _words_and_lost_characters(
    pdf: pdfplumber.PDF, page_index: int
) -> tuple[int, Counter[str]]:
    """The number of words layer_words gives on the page, and the difference
    between the page's non-space characters and the characters of those
    words, both ways (empty when each character is in exactly one word)."""
    with closing(pdf.pages[page_index]) as page:
        words = layer_words(page)
        characters = Counter(
            "".join(
                LIGATURES.get(str(character["text"]), str(character["text"]))
                for character in page.chars
                if not str(character["text"]).isspace()
            )
        )
    in_words = Counter("".join(word.text for word in words))
    return len(words), (characters - in_words) + (in_words - characters)


@pytest.fixture(scope="module")
def whole_book_layers(
    books_dir: Path,
) -> frozendict[str, tuple[int, tuple[int, ...]]]:
    """For each whole book, by Internet Archive identifier, its words as
    layer_words reads them, and the indices of its pages where a non-space
    character is in no word or in more than one."""
    layers = {}
    for book in WORDS_AFTER_BOTH_RULES:
        pdf_path = books_dir / f"{book}.pdf"
        pages = map_pages_with_source(
            lambda pdf_path=pdf_path: open_pdf(pdf_path),
            _words_and_lost_characters,
            range(_page_count(pdf_path)),
            DEFAULT_WORKERS,
        )
        layers[book] = (
            sum(word_count for word_count, _ in pages),
            tuple(index for index, (_, lost) in enumerate(pages) if lost),
        )
    return frozendict(layers)


@pytest.mark.whole_book
@pytest.mark.parametrize("book", sorted(WORDS_AFTER_BOTH_RULES))
def test_layer_words_of_a_whole_book_are_those_of_the_spec_table(
    whole_book_layers: frozendict[str, tuple[int, tuple[int, ...]]], book: str
) -> None:
    word_count, _ = whole_book_layers[book]
    assert word_count == WORDS_AFTER_BOTH_RULES[book]


@pytest.mark.whole_book
@pytest.mark.parametrize("book", sorted(WORDS_AFTER_BOTH_RULES))
def test_layer_words_of_a_whole_book_hold_each_non_space_character_once(
    whole_book_layers: frozendict[str, tuple[int, tuple[int, ...]]], book: str
) -> None:
    _, pages_with_lost_characters = whole_book_layers[book]
    assert pages_with_lost_characters == ()
