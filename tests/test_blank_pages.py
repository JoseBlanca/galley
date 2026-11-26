"""Tests of analyze's audit of the pages without a text layer
(docs/specs/analyze.md, section 11): the verdict of Tesseract's words and
the ink share, the ink share itself, how classify_page takes the verdict
under each `ocr`, and the excerpt `kadesh_blank`, whose ten pages have no
text layer.

The unit tests build their words, renders and configs by hand. The
excerpt tests read the session's run of `kadesh_blank` (`excerpt_books`);
a test that runs analyze on a folder of its own calls PDFium and
Tesseract and is marked thread_unsafe, so that the 8-thread run does it
once.
"""

import json
import logging
import logging.handlers
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Final

import pytest
from PIL import Image

from galley import analyze, extract, pdfium
from galley.analyze import (
    AuditVerdict,
    InkRule,
    PlateRule,
    audit_verdict,
    classify_page,
    ink_share,
    is_plate,
)
from galley.analyze._plates import PLATE_RENDER_DPI
from galley.book_folder import BookFolder
from galley.config import BookConfig, Language, OcrMode, read_config
from galley.model import (
    Box,
    FigureKind,
    PageKind,
    RenderedPage,
    TextSource,
    Word,
    read_pages,
    read_words,
)

EXCERPT = "kadesh_blank"
EXPECTED = (
    Path(__file__).parent
    / "fixtures"
    / "expected"
    / "blank_pages"
    / "kadesh_blank_page0.json"
)

# audit_verdict

BOX = Box(100.0, 100.0, 120.0, 112.0)


def word(text: str, confidence: float) -> Word:
    return Word(text, BOX, confidence)


# Kadesh 73, a blank leaf, excerpt page 8: the 26 words Tesseract 5.5.4 reads
# on its 300 dpi render, the highest "7" at 51.7 (read on 26 November 2026).
KADESH_73_WORDS = tuple(
    word(text, confidence)
    for text, confidence in (
        ("AP", 3.0),
        ("Ps", 30.8),
        ("»*", 38.9),
        ("a", 29.6),
        ("~", 9.2),
        ("<", 0.0),
        ("ane", 27.7),
        ("*", 0.0),
        ("7", 51.7),
        ("oe,", 28.7),
        ("et", 17.5),
        (";", 19.5),
        ("a", 23.7),
        (".", 0.0),
        ("a", 48.5),
        ("Ee", 33.4),
        ("a+", 23.8),
        ("rca", 39.4),
        ("n", 0.0),
        ("raed", 19.1),
        (":", 0.0),
        ("~", 2.9),
        ("a", 26.0),
        ("aa", 0.0),
        ("Go", 11.5),
        ("o-", 5.5),
    )
)


def test_kadesh_73_blank_leaf_with_26_stray_marks_and_little_ink_is_blank() -> None:
    assert len(KADESH_73_WORDS) == 26
    assert audit_verdict(KADESH_73_WORDS, 0.00003) is AuditVerdict.BLANK


@pytest.mark.parametrize(
    ("ink", "verdict"),
    [(0.0008, AuditVerdict.PICTURE), (0.00079, AuditVerdict.BLANK)],
)
def test_page_without_text_words_is_a_picture_from_ink_of_0_0008_and_blank_below(
    ink: float, verdict: AuditVerdict
) -> None:
    assert audit_verdict(KADESH_73_WORDS, ink) is verdict


@pytest.mark.parametrize("ink", [0.0, 0.5])
def test_one_text_word_makes_text_whatever_the_ink_not_blank(ink: float) -> None:
    assert audit_verdict((word("TO", 96.0),), ink) is AuditVerdict.TEXT


def test_a_lone_numeral_read_at_86_9_is_text_not_blank() -> None:
    # Domesday 0's library label, the page read with the lowest best word.
    assert audit_verdict((word("2", 86.9),), 0.0) is AuditVerdict.TEXT


def test_a_sign_without_letter_or_digit_at_86_leaves_the_page_blank() -> None:
    assert audit_verdict((word("=", 86.0),), 0.0) is AuditVerdict.BLANK


@pytest.mark.parametrize(
    ("confidence", "verdict"), [(70.0, AuditVerdict.TEXT), (69.9, AuditVerdict.BLANK)]
)
def test_a_word_is_text_from_confidence_70_and_the_page_blank_below(
    confidence: float, verdict: AuditVerdict
) -> None:
    assert audit_verdict((word("E", confidence),), 0.0) is verdict


@pytest.mark.parametrize(
    ("count", "verdict"), [(40, AuditVerdict.MUCH_TEXT), (39, AuditVerdict.TEXT)]
)
def test_40_text_words_are_much_text_and_39_text_not_blank(
    count: int, verdict: AuditVerdict
) -> None:
    words = (*(word("the", 90.0) for _ in range(count)), *KADESH_73_WORDS)
    assert audit_verdict(words, 0.0) is verdict


def test_a_word_of_a_text_layer_given_to_the_blank_page_rule_is_an_error() -> None:
    with pytest.raises(ValueError, match="'the' has no confidence"):
        audit_verdict((Word("the", BOX, None),), 0.0)


# ink_share, on renders of 2000 by 3000 pixels at 300 dpi

WIDTH_PX: Final[int] = 2000
HEIGHT_PX: Final[int] = 3000
WHITE: Final[int] = 255
BLACK: Final[int] = 0
# Ten black lines, 2 pixels high, 40 pixels apart, across the middle.
LINE_ROWS: Final[tuple[int, ...]] = tuple(1400 + 40 * line for line in range(10))


def gray_page(gray: Callable[[int, int], int], dpi: int = 300) -> RenderedPage:
    """A page whose pixel at (`across`, `down`) is `gray(across, down)`."""
    image = Image.new("L", (WIDTH_PX, HEIGHT_PX))
    image.putdata(
        [gray(across, down) for down in range(HEIGHT_PX) for across in range(WIDTH_PX)]
    )
    return RenderedPage(
        page_index=0,
        dpi=dpi,
        width_px=WIDTH_PX,
        height_px=HEIGHT_PX,
        pixels=image.tobytes(),
    )


def lines_page(left_px: int, right_px: int) -> RenderedPage:
    """A white page with the black lines of LINE_ROWS from `left_px` to
    `right_px`."""
    image = Image.new("L", (WIDTH_PX, HEIGHT_PX), WHITE)
    for top in LINE_ROWS:
        image.paste(BLACK, (left_px, top, right_px, top + 2))
    return RenderedPage(
        page_index=0,
        dpi=300,
        width_px=WIDTH_PX,
        height_px=HEIGHT_PX,
        pixels=image.tobytes(),
    )


def test_a_white_page_has_no_ink_and_is_blank() -> None:
    page = lines_page(0, 0)
    assert ink_share(page) == 0.0


def test_a_page_darkening_smoothly_from_255_to_200_has_no_ink_and_is_blank() -> None:
    image = Image.linear_gradient("L").resize((WIDTH_PX, HEIGHT_PX))
    # 0 at the top to 255 at the foot, made 255 to 200.
    image = image.point(lambda level: 255 - round(level * 55 / 255))
    page = RenderedPage(
        page_index=0,
        dpi=300,
        width_px=WIDTH_PX,
        height_px=HEIGHT_PX,
        pixels=image.tobytes(),
    )
    assert ink_share(page) == 0.0


def test_black_lines_across_a_blank_page_are_ink_their_share_after_halving() -> None:
    # Halved, the page is 1000 by 1500 pixels, each line 1 pixel high; the
    # bands leave 840 by 1320 pixels, of which each line covers 840.
    expected = len(LINE_ROWS) * 840 / (840 * 1320)
    assert ink_share(lines_page(0, WIDTH_PX)) == pytest.approx(expected, rel=0.03)


def test_black_lines_inside_the_left_band_of_8_percent_are_no_ink_of_a_blank_page() -> (
    None
):
    # The band is 80 pixels of the halved page, 160 of the render.
    assert ink_share(lines_page(0, 150)) == 0.0


def test_the_ink_share_of_a_blank_page_is_refused_at_other_than_300_dpi() -> None:
    page = replace(lines_page(0, 0), dpi=150)
    with pytest.raises(ValueError, match="measured at 300 dpi, not at 150"):
        ink_share(page)


# classify_page with the audit's verdict (docs/specs/analyze.md, section 4)

CONFIG = BookConfig(
    pdf=Path("/books/book.pdf"),
    title="A Book",
    authors=("An Author",),
    language=Language.EN,
)


@dataclass(frozen=True, slots=True)
class Classified:
    kind: PageKind
    text_source: TextSource
    blank_checked_by_ocr: bool


def classified(
    audit: AuditVerdict,
    *,
    ocr: OcrMode,
    plate_rule: PlateRule = PlateRule.NOT_PLATE,
    front_matter_end: int = 0,
    config: BookConfig = CONFIG,
) -> Classified:
    """What classify_page makes of page index 5, without a text layer."""
    page = classify_page(
        5,
        400.0,
        600.0,
        0,
        replace(config, ocr=ocr),
        plate_rule=plate_rule,
        ink_rule=InkRule.NOT_INKLESS,
        audit=audit,
        front_matter_end=front_matter_end,
    )
    return Classified(page.kind, page.text_source, page.blank_checked_by_ocr)


OCR_MODES = pytest.mark.parametrize("ocr", list(OcrMode))


@OCR_MODES
def test_text_at_or_past_the_front_matter_end_is_a_text_page_read_by_ocr_not_blank(
    ocr: OcrMode,
) -> None:
    expected = Classified(PageKind.TEXT, TextSource.OCR, blank_checked_by_ocr=False)
    assert classified(AuditVerdict.TEXT, ocr=ocr, front_matter_end=5) == expected
    assert classified(AuditVerdict.TEXT, ocr=ocr, front_matter_end=0) == expected


@OCR_MODES
def test_text_before_the_front_matter_end_is_front_matter_read_by_ocr_not_blank(
    ocr: OcrMode,
) -> None:
    assert classified(AuditVerdict.TEXT, ocr=ocr, front_matter_end=6) == Classified(
        PageKind.FRONT_MATTER, TextSource.OCR, blank_checked_by_ocr=False
    )


@OCR_MODES
def test_much_text_is_text_where_the_plate_rule_takes_the_page_not_blank(
    ocr: OcrMode,
) -> None:
    assert classified(
        AuditVerdict.MUCH_TEXT, ocr=ocr, plate_rule=PlateRule.PLATE
    ) == Classified(PageKind.TEXT, TextSource.OCR, blank_checked_by_ocr=False)


@OCR_MODES
@pytest.mark.parametrize("audit", [AuditVerdict.TEXT, AuditVerdict.BLANK])
def test_text_or_blank_on_a_page_the_plate_rule_takes_is_a_plate(
    ocr: OcrMode, audit: AuditVerdict
) -> None:
    assert classified(audit, ocr=ocr, plate_rule=PlateRule.PLATE) == Classified(
        PageKind.PLATE, TextSource.NONE, blank_checked_by_ocr=False
    )


@OCR_MODES
def test_picture_is_a_plate_without_text_source_not_blank(ocr: OcrMode) -> None:
    assert classified(AuditVerdict.PICTURE, ocr=ocr) == Classified(
        PageKind.PLATE, TextSource.NONE, blank_checked_by_ocr=False
    )


@OCR_MODES
def test_blank_is_blank_checked_by_ocr(ocr: OcrMode) -> None:
    assert classified(AuditVerdict.BLANK, ocr=ocr) == Classified(
        PageKind.BLANK, TextSource.NONE, blank_checked_by_ocr=True
    )


@OCR_MODES
def test_the_cover_without_a_layer_not_audited_is_blank_not_checked_by_ocr(
    ocr: OcrMode,
) -> None:
    assert classified(
        AuditVerdict.NOT_AUDITED, ocr=ocr, config=replace(CONFIG, cover_page=5)
    ) == Classified(PageKind.BLANK, TextSource.NONE, blank_checked_by_ocr=False)


@OCR_MODES
@pytest.mark.parametrize("audit", list(AuditVerdict))
def test_a_page_in_exclude_pages_stays_excluded_whatever_the_blank_page_audit_finds(
    ocr: OcrMode, audit: AuditVerdict
) -> None:
    assert classified(
        audit, ocr=ocr, config=replace(CONFIG, exclude_pages=(5,))
    ) == Classified(PageKind.EXCLUDED, TextSource.NONE, blank_checked_by_ocr=False)


def test_a_blank_page_verdict_on_a_page_with_a_text_layer_is_an_error() -> None:
    with pytest.raises(ValueError, match="page index 5 has 12 words in its text layer"):
        classify_page(
            5,
            400.0,
            600.0,
            12,
            CONFIG,
            plate_rule=PlateRule.NOT_PLATE,
            ink_rule=InkRule.NOT_INKLESS,
            audit=AuditVerdict.BLANK,
            front_matter_end=0,
        )


# The excerpt kadesh_blank, from the session's run (docs/specs/analyze.md,
# section 11): its config has only pdf, title, authors and language, and
# its front-matter end is 0, so that no page is front matter.

# Each excerpt page's kind, text source and blank_checked_by_ocr: the
# Internet Archive's notice; two blank endpapers; a faint relief; the
# photograph under blurred text that the plate rule takes; three boards
# of the back cover, the board between them a blank leaf with the next
# page showing through, then a blank leaf with 26 stray marks.
KADESH_BLANK_PAGES = (
    (PageKind.TEXT, TextSource.OCR, False),
    (PageKind.BLANK, TextSource.NONE, True),
    (PageKind.BLANK, TextSource.NONE, True),
    (PageKind.PLATE, TextSource.NONE, False),
    (PageKind.PLATE, TextSource.NONE, False),
    (PageKind.BLANK, TextSource.NONE, True),
    (PageKind.BLANK, TextSource.NONE, True),
    (PageKind.BLANK, TextSource.NONE, True),
    (PageKind.BLANK, TextSource.NONE, True),
    (PageKind.BLANK, TextSource.NONE, True),
)


def test_kadesh_blank_pages_are_text_blank_or_plates_as_the_spec_gives(
    excerpt_books: frozendict[str, BookFolder],
) -> None:
    pages = read_pages(excerpt_books[EXCERPT].pages_json)

    assert (
        tuple(
            (page.kind, page.text_source, page.blank_checked_by_ocr)
            for page in pages.pages
        )
        == KADESH_BLANK_PAGES
    )
    assert all(page.text_layer_score is None for page in pages.pages)
    assert pages.ocr_audit is None


def test_kadesh_blank_has_the_notice_read_by_tesseract_and_no_word_on_blank_pages(
    excerpt_books: frozendict[str, BookFolder],
) -> None:
    expected = json.loads(EXPECTED.read_text(encoding="utf-8"))
    words = read_words(excerpt_books[EXCERPT].words_json)
    notice = words.pages[0]

    assert notice.text_source is TextSource.OCR
    assert len(notice.words) == expected["expected_word_count"]
    assert [
        read.text for read in notice.words[: len(expected["expected_words"])]
    ] == expected["expected_words"]
    assert all(read.ocr_confidence is not None for read in notice.words)
    assert [len(page.words) for page in words.pages[1:]] == [0] * 9
    assert words.removals == ()


def test_kadesh_blank_plates_have_one_figure_each_the_whole_page_and_blank_pages_none(
    excerpt_books: frozendict[str, BookFolder],
) -> None:
    words = read_words(excerpt_books[EXCERPT].words_json)

    assert [
        [(figure.kind, figure.box.x0, figure.box.top) for figure in page.figures]
        for page in words.pages
    ] == [
        [],
        [],
        [],
        [(FigureKind.PLATE, 0.0, 0.0)],
        [(FigureKind.PLATE, 0.0, 0.0)],
        [],
        [],
        [],
        [],
        [],
    ]


# analyze on kadesh_blank in a folder of its own, with 1 worker, its log
# kept: once for the tests that read it.


@dataclass(frozen=True, slots=True)
class AnalyzeRun:
    pages_json: bytes
    records: tuple[tuple[int, str], ...]


# More records than any run of analyze on the excerpt logs.
_KEPT_RECORDS: Final[int] = 1000


def kadesh_blank_folder(root: Path, pdf: Path, settings: str = "") -> BookFolder:
    folder = BookFolder(root)
    folder.book_toml.write_text(
        f"pdf = '{pdf}'\n"
        'title = "The Battle of Kadesh"\n'
        'authors = ["J. H. Breasted"]\n'
        'language = "en"\n'
        f"{settings}",
        encoding="utf-8",
    )
    return folder


@pytest.fixture(scope="module")
def one_worker_run(
    tmp_path_factory: pytest.TempPathFactory, excerpt_pdf: frozendict[str, Path]
) -> AnalyzeRun:
    folder = kadesh_blank_folder(tmp_path_factory.mktemp(EXCERPT), excerpt_pdf[EXCERPT])
    logger = logging.getLogger("galley.analyze")
    kept = logging.handlers.BufferingHandler(_KEPT_RECORDS)
    level = logger.level
    logger.addHandler(kept)
    logger.setLevel(logging.INFO)
    try:
        analyze.run(folder, read_config(folder.book_toml), workers=1)
    finally:
        logger.removeHandler(kept)
        logger.setLevel(level)
    return AnalyzeRun(
        folder.pages_json.read_bytes(),
        tuple((record.levelno, record.getMessage()) for record in kept.buffer),
    )


def _blank(index: int, words: int, highest: str, ink: str) -> tuple[int, str]:
    return (
        logging.INFO,
        (
            f"analyze: page index {index}, without a text layer, is blank: "
            f"Tesseract reads {words} words, the highest of confidence {highest}, "
            f"and ink covers {ink}% of it"
        ),
    )


@pytest.mark.thread_unsafe
@pytest.mark.tesseract
def test_kadesh_blank_logs_a_warning_for_text_and_plates_and_info_for_blank_pages(
    one_worker_run: AnalyzeRun,
) -> None:
    audited = tuple(
        record
        for record in one_worker_run.records
        if "without a text layer" in record[1]
    )

    assert audited == (
        (
            logging.WARNING,
            (
                "analyze: page index 0, without a text layer, is read by Tesseract as "
                "text: 13 words, the first ten or fewer: Digitized by the Internet "
                "Archive in 2007 with funding from; add it to `exclude_pages` if it is "
                "not the book's"
            ),
        ),
        _blank(1, 0, "none", "0.031"),
        _blank(2, 0, "none", "0.010"),
        (
            logging.WARNING,
            (
                "analyze: page index 3, without a text layer, taken for a plate: ink "
                "covers 1.441% of it, Tesseract reads 0 words, the highest of "
                "confidence none; add it to `exclude_pages` if it is not one"
            ),
        ),
        (
            logging.WARNING,
            (
                "analyze: page index 4, without a text layer, taken for a plate: a "
                "picture of 169 of its 476 squares; add it to `exclude_pages` if it "
                "is not one"
            ),
        ),
        _blank(5, 0, "none", "0.001"),
        _blank(6, 0, "none", "0.039"),
        _blank(7, 0, "none", "0.013"),
        _blank(8, 26, "51.7", "0.003"),
        _blank(9, 0, "none", "0.050"),
        (
            logging.INFO,
            (
                "analyze: Tesseract read 10 pages without a text layer: 0 much_text, "
                "1 text, 2 picture, 7 blank"
            ),
        ),
    )


@pytest.mark.thread_unsafe
@pytest.mark.tesseract
def test_kadesh_blank_audit_with_1_worker_writes_the_bytes_of_the_run_with_6(
    one_worker_run: AnalyzeRun, excerpt_books: frozendict[str, BookFolder]
) -> None:
    # The session's run uses DEFAULT_WORKERS, 6 on a machine of 6 cores or
    # more.
    assert one_worker_run.pages_json == excerpt_books[EXCERPT].pages_json.read_bytes()


@pytest.mark.thread_unsafe
@pytest.mark.tesseract
@pytest.mark.parametrize("ocr", ["trust", "redo"])
def test_kadesh_blank_pages_are_audited_alike_under_ocr_trust_and_redo(
    ocr: str,
    tmp_path: Path,
    excerpt_pdf: frozendict[str, Path],
    excerpt_books: frozendict[str, BookFolder],
) -> None:
    # docs/specs/analyze.md, section 6: the same rule and verdicts under every
    # `ocr`, so pages.json is the one of `verify`, the default.
    folder = kadesh_blank_folder(tmp_path, excerpt_pdf[EXCERPT], f'ocr = "{ocr}"\n')

    analyze.run(folder, read_config(folder.book_toml))

    assert folder.pages_json.read_bytes() == (
        excerpt_books[EXCERPT].pages_json.read_bytes()
    )


# A page of running text without a text layer (docs/specs/analyze.md,
# section 11): Kadesh 9, excerpt page 1 of kadesh_8-17, rendered at 300 dpi
# and saved as a one-page PDF, which has no text layer.


@pytest.mark.thread_unsafe
@pytest.mark.tesseract
def test_running_text_without_a_layer_is_text_read_by_ocr_though_the_plate_rule_takes_it_not_blank(
    tmp_path: Path, excerpt_pdf: frozendict[str, Path]
) -> None:
    rendered = pdfium.render(excerpt_pdf["kadesh_8-17"], 1, 300)
    pdf = tmp_path / "kadesh_9.pdf"
    Image.frombytes("L", (rendered.width_px, rendered.height_px), rendered.pixels).save(
        pdf, format="PDF", resolution=300.0
    )
    (tmp_path / "book").mkdir()
    folder = kadesh_blank_folder(tmp_path / "book", pdf)
    config = read_config(folder.book_toml)

    analyze.run(folder, config)
    extract.run(folder, config)

    assert is_plate(pdfium.render(pdf, 0, PLATE_RENDER_DPI), None, 0)
    (page,) = read_pages(folder.pages_json).pages
    assert (page.kind, page.text_source) == (PageKind.TEXT, TextSource.OCR)
    (page_words,) = read_words(folder.words_json).pages
    assert page_words.text_source is TextSource.OCR
    texts = [read.text for read in page_words.words]
    # The first line of the page's text, read by eye on the render: "Megiddo
    # and Kadesh. At Megiddo, already in the sixteenth century before Christ,".
    first = texts.index("Megiddo")
    assert texts[first : first + 7] == [
        "Megiddo",
        "and",
        "Kadesh.",
        "At",
        "Megiddo,",
        "already",
        "in",
    ]


# The whole books (docs/specs/analyze.md, section 11), with the config of a
# bare PDF: the 68 pages without a text layer of the five books as section 5
# gives them. The text pages before the front-matter end are front matter.

WHOLE_BOOK_PAGES_WITHOUT_A_LAYER = frozendict(
    {
        "battleofkadeshst00breauoft": {
            PageKind.PLATE: (17, 23, 35, 43, 57, 69),
            PageKind.FRONT_MATTER: (1,),
            PageKind.BLANK: (2, 3, 70, 71, 72, 73, 75),
        },
        "domesdaybook00maituoft": {
            PageKind.PLATE: (6, 557),
            PageKind.FRONT_MATTER: (0,),
            PageKind.BLANK: (1, 2, 3, 5, 7, 38, 41, 554, 555),
        },
        "earlyplantagenet01stub": {
            PageKind.PLATE: (0, 9, 11, 52, 54),
            PageKind.TEXT: (343,),
            PageKind.BLANK: (2, 3, 4, 5, 8, 10, 53, 55, 338, 339, 340, 341, 342),
        },
        "normansineuropea00hask": {
            PageKind.PLATE: (0,),
            PageKind.BLANK: (3, 4, 5, 7, 11, 15, 265, 274, 276, 279),
        },
        "politicaltheorie00gieruoft": {
            PageKind.PLATE: (0, 287, 289),
            PageKind.FRONT_MATTER: (4,),
            PageKind.BLANK: (2, 3, 5, 51, 283, 284, 285, 286),
        },
    }
)


def test_the_whole_books_have_68_pages_without_a_layer_47_of_them_blank() -> None:
    kinds = tuple(
        kind
        for book in WHOLE_BOOK_PAGES_WITHOUT_A_LAYER.values()
        for kind, pages in book.items()
        for _ in pages
    )
    assert len(kinds) == 68
    assert kinds.count(PageKind.BLANK) == 47


def _bare_toml(books_dir: Path, configs: frozendict[str, str], book: str) -> str:
    """The config `galley2epub run` writes for the bare PDF of `book`: its
    pdf, title, authors and language."""
    kept = (
        line
        for line in configs[book].splitlines(keepends=True)
        if line.startswith(("title", "authors", "language"))
    )
    return f"pdf = {json.dumps(str(books_dir / f'{book}.pdf'))}\n" + "".join(kept)


@pytest.mark.whole_book
@pytest.mark.thread_unsafe
@pytest.mark.tesseract
@pytest.mark.timeout(600)
@pytest.mark.parametrize("book", sorted(WHOLE_BOOK_PAGES_WITHOUT_A_LAYER))
def test_analyze_of_a_whole_book_without_exclude_pages_reads_its_blank_pages(
    book: str,
    books_dir: Path,
    whole_book_configs: frozendict[str, str],
    tmp_path: Path,
) -> None:
    folder = BookFolder(tmp_path)
    folder.book_toml.write_text(
        _bare_toml(books_dir, whole_book_configs, book), encoding="utf-8"
    )

    analyze.run(folder, read_config(folder.book_toml))

    pages = read_pages(folder.pages_json).pages
    expected = WHOLE_BOOK_PAGES_WITHOUT_A_LAYER[book]
    for kind, indices in expected.items():
        assert {page.index: page.kind for page in pages if page.index in indices} == (
            dict.fromkeys(indices, kind)
        ), (book, kind)
    assert (
        tuple(page.index for page in pages if page.kind is PageKind.BLANK)
        == (expected[PageKind.BLANK])
    ), book
    assert all(
        page.blank_checked_by_ocr is (page.kind is PageKind.BLANK) for page in pages
    ), book
    assert all(
        page.text_source is TextSource.OCR
        for page in pages
        if page.index
        in (*expected.get(PageKind.TEXT, ()), *expected.get(PageKind.FRONT_MATTER, ()))
    ), book
