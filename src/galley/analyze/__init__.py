"""analyze: what each page of the PDF is, written to pages.json (analyze
spec, plates spec sections 2 and 2b, figures spec section 3).

analyze measures every page with pdfplumber, its size in points and the
words of its text layer, and renders every page that is neither excluded
nor the cover at 36 dpi to test whether it is a plate (`is_plate`). A page
is `excluded` when the config excludes it, a `plate` when the config's
`plate_pages` names it or the plate rule takes it, and `text` when its
layer has a word. A page without a text layer that the plate rule tests
is also audited (analyze spec sections 2 to 4): rendered at 300 dpi, read
with Tesseract and measured for ink (`audit_verdict`). With 40 text words or
more it is text even where the plate rule takes it; else the plate rule
decides; else with a text word it is text, with ink a plate, and
otherwise `blank`, recorded as checked by OCR. A page the audit makes
text has the text source `ocr`, and extract reads it with Tesseract.
The config's `cover_page` is not audited: without a layer it is `blank`.
The audit runs under every value of `ocr`. Under
`ocr = "redo"` the pages are classified from the layer all the same, and
every text page is then read by OCR: its text source is `ocr`, and
extract reads it with Tesseract (architecture section 7b). Each page the
plate rule makes a plate is logged at WARNING, so that the owner sees the
covers and endpapers it takes too. On each text page, the same render is
searched for the figures printed among its lines (`figure_boxes`), whose
boxes go into pages.json; each page with figures is logged at INFO. The
same render also tells an inkless page (`is_inkless`): at least half of
the words of its layer have no ink under them, and fewer than a third of
those are known words, words the scanner's OCR invented where nothing is
printed. It is `inkless`, also when the plate rule takes it, and each one
is logged at WARNING.
"""

import logging
import statistics
import unicodedata
from collections.abc import Callable
from contextlib import closing
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Final, assert_never

import pdfplumber
from PIL import Image

from galley import ocr, pdfium, wordlist
from galley.analyze._audit import (
    AuditVerdict,
    audit_verdict,
    image_ink_share,
    ink_share,
    is_text_word,
)
from galley.analyze._figures import PictureGroup, figure_boxes, figure_groups
from galley.analyze._inkless import InkRule, InkTest, is_inkless, measure_ink
from galley.analyze._plates import (
    PLATE_RENDER_DPI,
    PictureArea,
    is_plate,
    is_plate_by_area,
    picture_area,
)
from galley.body_measures import group_rows
from galley.book_folder import BookFolder, Stage, delete_stage_outputs
from galley.config import BookConfig, OcrMode, tesseract_language
from galley.errors import ConfigError
from galley.model import (
    Box,
    PageInfo,
    PageKind,
    PagesFile,
    RenderedPage,
    TextSource,
    Word,
    box_holds_middle,
    pdf_sha256,
    write_pages,
)
from galley.parallel import DEFAULT_WORKERS, map_pages_with_source
from galley.text_layer import layer_words, open_pdf

__all__ = [
    "AuditVerdict",
    "InkRule",
    "PageStart",
    "PictureArea",
    "PlateRule",
    "audit_verdict",
    "check_config_pages",
    "classify_page",
    "figure_boxes",
    "front_matter_end",
    "ink_share",
    "is_inkless",
    "is_plate",
    "picture_area",
    "run",
]

_logger = logging.getLogger(__name__)

# Front-matter spec section 1, "Preface page": the names of a preface in the
# five languages of the config, reduced to their letters in lower case
# without accents, and the most words of a topmost row that names one.
_PREFACE_NAMES: Final[frozenset[str]] = frozenset(
    {
        "preface",
        "prefatory",
        "foreword",
        "avantpropos",
        "vorwort",
        "prefazione",
        "prologo",
        "prefacio",
    }
)
_PREFACE_ROW_MOST_WORDS: Final[int] = 6
# Front-matter spec section 1, "The search window": the first tenth of the
# PDF's pages, rounded down, and at least its first 10.
_SEARCH_WINDOW_SHARE: Final[int] = 10
_SEARCH_WINDOW_LEAST_PAGES: Final[int] = 10
# Front-matter spec section 2: a page of running text has at least half the
# median word count of the book's text pages. A guess, measured on Kadesh
# alone: its median is 545 words, its front pages have at most 47.
_RUNNING_TEXT_SHARE_OF_MEDIAN: Final[float] = 0.5
# Analyze spec sections 3 and 4: half the ink share from which a page is a
# picture; a blank page with this much ink is logged at WARNING, as a page
# whose lone word Tesseract may have missed (Haskins 4 with a pasted "end":
# 0.047%).
_BLANK_LOOK_LEAST_INK_SHARE: Final[float] = 0.0004
# Analyze spec section 4: how many of a text page's words the WARNING quotes.
_LOGGED_WORDS: Final[int] = 10


@dataclass(frozen=True, slots=True, kw_only=True)
class PageStart:
    """What the front-matter rule needs of one page: its index, the kind
    classify_page gives it before the front matter is known, the words
    of its topmost row (empty without words) and its number of words."""

    index: int
    kind: PageKind
    first_row: tuple[str, ...]
    word_count: int


class _FrontMatterStep(StrEnum):
    """The step of the front-matter rule (front-matter spec section 2) that
    gave the front-matter end, as analyze logs it."""

    CONFIG = "the config's `front_matter_end`"
    PREFACE = "the first preface page"
    CONTENTS = "the first page of `contents_pages`"
    RUNNING_TEXT = "the first page of running text"
    NOTHING_FOUND = "no preface, contents or running text in the search window"


class PlateRule(StrEnum):
    """What the plate rule of plates spec section 2 found on a page: a
    plate, or not one (also for a page it does not test, an excluded page
    or the cover)."""

    PLATE = "plate"
    NOT_PLATE = "not_plate"


@dataclass(frozen=True, slots=True)
class _Audit:
    """What the audit found on a page without a text layer: every word
    Tesseract read on its 300 dpi render, its ink share from 0 to 1, and
    the verdict of the two (analyze spec section 3)."""

    words: tuple[Word, ...]
    ink: float
    verdict: AuditVerdict


@dataclass(frozen=True, slots=True)
class _PlateTest:
    """What analyze measured on a page the plate rule tested: its picture
    area, the known words of its text layer (0 without one), the rule's
    finding, and the audit of a page without a text layer (None for a page
    with one)."""

    area: PictureArea
    known_words: int
    rule: PlateRule
    audit: _Audit | None


@dataclass(frozen=True, slots=True)
class _Measurement:
    """What analyze measures of one page.

    Its size in points is pdfplumber's. `layer_word_count` counts the
    words of its text layer, and `first_row` holds those of the layer's
    topmost row, empty without words. `plate_test` is the plate rule's
    test with the page's audit, None for a page the rule does not test;
    `ink_test` is the inkless rule's, None likewise. `figures` are the
    in-page figures found on a page the plate rule tests that is not a
    plate and has a text layer or text the audit read.
    """

    width_pt: float
    height_pt: float
    layer_word_count: int
    first_row: tuple[str, ...]
    plate_test: _PlateTest | None
    ink_test: InkTest | None
    figures: tuple[PictureGroup, ...]


def _audit_of(measurement: _Measurement) -> _Audit | None:
    """The audit of the measured page, None for a page it did not read."""
    return None if measurement.plate_test is None else measurement.plate_test.audit


def run(
    folder: BookFolder, config: BookConfig, *, workers: int = DEFAULT_WORKERS
) -> None:
    """Writes `folder.pages_json`, what each page of `config.pdf` is.

    Deletes pages.json and every later stage's file first (words.json,
    images/, lines.json, blocks.json, book.md, book.epub), so that a failed
    run leaves none and no later file outlives the pages.json it came from.
    Takes the word list of the book's language from its cache folder,
    extracting it with Tesseract's tools the first time. The text pages
    before the front-matter end (`front_matter_end`) are `front_matter`. A
    page the inkless rule takes (`is_inkless`) is `inkless`, or
    `front_matter` before the front-matter end. Each page without a text
    layer that is not excluded, in `plate_pages` or the cover is read with
    Tesseract and made text, a plate or blank (analyze spec sections 2 to
    4), under every value of `ocr`. Under `ocr = "redo"` every
    text page has the text source `ocr`. Raises ConfigError when the
    config names a page past the end of the PDF or a contents
    page before its `front_matter_end`, and ExternalProgramError when
    Tesseract is needed and missing or fails, before pages.json is
    written. `workers` is the number of threads that measure the pages
    and run Tesseract; the renders are made in the one PDFium thread.
    """
    delete_stage_outputs(folder, Stage.ANALYZE)
    page_count = pdfium.page_count(config.pdf)
    check_config_pages(config, page_count)
    lower_case_words = wordlist.lower_case_word_list(
        config.language, wordlist.DEFAULT_CACHE_DIR
    )
    measure = _measurer(config, lower_case_words)
    measurements = map_pages_with_source(
        lambda: open_pdf(config.pdf), measure, range(page_count), workers
    )

    def classify(end: int) -> tuple[PageInfo, ...]:
        return tuple(
            _with_figures(
                classify_page(
                    index,
                    measurement.width_pt,
                    measurement.height_pt,
                    measurement.layer_word_count,
                    config,
                    plate_rule=PlateRule.NOT_PLATE
                    if measurement.plate_test is None
                    else measurement.plate_test.rule,
                    ink_rule=InkRule.NOT_INKLESS
                    if measurement.ink_test is None
                    else measurement.ink_test.rule,
                    audit=_verdict(_audit_of(measurement)),
                    front_matter_end=end,
                ),
                measurement.figures,
            )
            for index, measurement in enumerate(measurements)
        )

    starts = tuple(
        _page_start(page, measurement)
        for page, measurement in zip(classify(0), measurements, strict=True)
    )
    end, step = _front_matter_end_and_step(starts, config)
    pages = classify(end)
    for page, measurement in zip(pages, measurements, strict=True):
        if measurement.plate_test is not None:
            _log_plate_taken(page, measurement.plate_test)
            _log_audited(page, measurement.plate_test)
    _log_front_matter(end, step, pages, config)
    for page, measurement in zip(pages, measurements, strict=True):
        if page.kind is PageKind.INKLESS and measurement.ink_test is not None:
            _log_inkless(page.index, measurement.ink_test)
    for page, measurement in zip(pages, measurements, strict=True):
        if page.figure_boxes:
            _log_figures(page.index, measurement.figures)
    _log_audit_counts(pages, measurements)
    write_pages(
        folder.pages_json,
        PagesFile(
            source_pdf_sha256=pdf_sha256(config.pdf), pages=pages, ocr_audit=None
        ),
    )
    _logger.info(
        "analyze: %d pages of %s, %d excluded",
        page_count,
        config.pdf,
        sum(1 for page in pages if page.kind is PageKind.EXCLUDED),
    )


def _measurer(
    config: BookConfig, lower_case_words: frozenset[str]
) -> Callable[[pdfplumber.PDF, int], _Measurement]:
    """The function a worker thread runs on each page: it reads the page's
    text layer with the worker's pdfplumber document and, on a page the
    plate rule tests, has the PDFium thread render it and tests the render
    in the worker, for a plate and for an inkless page; on such a page
    without a text layer, it has the page rendered at 300 dpi too and
    audits it in the worker."""
    language = tesseract_language(config.language)

    def measure(pdf: pdfplumber.PDF, page_index: int) -> _Measurement:
        with closing(pdf.pages[page_index]) as page:
            width_pt = float(page.width)
            height_pt = float(page.height)
            # Extract spec section 5: the words extract writes.
            words = layer_words(page)
        page_layer_words = tuple((word.text, word.box) for word in words)
        rows = group_rows(words)
        region_boxes = tuple(
            region.box
            for region in config.exclude_regions
            if region.page_index == page_index
        )
        rendered = (
            pdfium.render(config.pdf, page_index, PLATE_RENDER_DPI)
            if _plate_rule_tests(page_index, config)
            else None
        )
        plate_test = (
            None
            if rendered is None
            else _test_plate(
                rendered,
                page_layer_words,
                lower_case_words,
                None if page_layer_words else _audit(config, page_index, language),
            )
        )
        # Figures spec section 3: a page that may end as a text page is
        # searched for figures on the same render; classify_page decides.
        # A page without a layer that the audit reads as text is searched
        # with its text words in place of the layer's (analyze spec
        # section 4).
        figures = (
            ()
            if rendered is None or plate_test is None
            else _figures(
                rendered, plate_test, page_layer_words, region_boxes, lower_case_words
            )
        )
        ink_test = (
            None
            if rendered is None
            else measure_ink(
                rendered,
                tuple(
                    (text, box)
                    for text, box in page_layer_words
                    if not any(box_holds_middle(region, box) for region in region_boxes)
                ),
                lower_case_words,
            )
        )
        return _Measurement(
            width_pt=width_pt,
            height_pt=height_pt,
            layer_word_count=len(page_layer_words),
            first_row=tuple(word.text for word in rows[0].words) if rows else (),
            plate_test=plate_test,
            ink_test=ink_test,
            figures=figures,
        )

    return measure


def _audit(config: BookConfig, page_index: int, language: str) -> _Audit:
    """The audit of page `page_index` of `config.pdf`, which has no text
    layer: rendered at 300 dpi in the PDFium thread, read with Tesseract in
    page segmentation mode 3 and the language `language` (Tesseract's
    code), and measured for ink, in the calling thread (analyze spec
    sections 2 and 3)."""
    rendered = pdfium.render(config.pdf, page_index, ocr.OCR_DPI)
    image = Image.frombytes(
        "L", (rendered.width_px, rendered.height_px), rendered.pixels
    )
    words = ocr.read_image(
        image,
        origin=(0.0, 0.0),
        dpi=rendered.dpi,
        psm=ocr.WHOLE_PAGE_SEGMENTATION,
        language=language,
    )
    ink = image_ink_share(image)
    return _Audit(words=words, ink=ink, verdict=audit_verdict(words, ink))


def _verdict(audit: _Audit | None) -> AuditVerdict:
    """The audit's verdict, NOT_AUDITED for a page it did not read."""
    return AuditVerdict.NOT_AUDITED if audit is None else audit.verdict


def _figures(
    rendered: RenderedPage,
    plate_test: _PlateTest,
    page_layer_words: tuple[tuple[str, Box], ...],
    region_boxes: tuple[Box, ...],
    lower_case_words: frozenset[str],
) -> tuple[PictureGroup, ...]:
    """The in-page figures of a page the plate rule tested, on its 36 dpi
    render (figures spec section 3): searched among the words of its text
    layer, or on a page without one that the audit reads as text, among
    its text words (analyze spec section 4); none on a page that ends as a
    plate or has no such words."""
    audit = plate_test.audit
    words = page_layer_words if audit is None else _audited_text_words(audit)
    if not words or (
        plate_test.rule is PlateRule.PLATE
        and _verdict(audit) is not AuditVerdict.MUCH_TEXT
    ):
        return ()
    return figure_groups(rendered, words, region_boxes, lower_case_words)


def _audited_text_words(audit: _Audit) -> tuple[tuple[str, Box], ...]:
    """The text words of a page the audit reads as text, each its text and
    box, for the figure search; none for any other page."""
    if audit.verdict not in {
        AuditVerdict.MUCH_TEXT,
        AuditVerdict.TEXT,
    }:
        return ()
    return tuple((word.text, word.box) for word in audit.words if is_text_word(word))


def _page_start(page: PageInfo, measurement: _Measurement) -> PageStart:
    """What the front-matter rule needs of `page`, as classify_page makes it
    before the front matter is known. A text page without a text layer has
    the words Tesseract read on it, its topmost row the first row they
    make (analyze spec section 4); any other page has its layer's."""
    audit = _audit_of(measurement)
    if page.kind is PageKind.TEXT and audit is not None:
        rows = group_rows(audit.words)
        return PageStart(
            index=page.index,
            kind=page.kind,
            first_row=tuple(word.text for word in rows[0].words) if rows else (),
            word_count=len(audit.words),
        )
    return PageStart(
        index=page.index,
        kind=page.kind,
        first_row=measurement.first_row,
        word_count=measurement.layer_word_count,
    )


def _highest_confidence(words: tuple[Word, ...]) -> str:
    """The highest confidence of `words` with one decimal, "none" without
    words."""
    confidences = tuple(
        word.ocr_confidence for word in words if word.ocr_confidence is not None
    )
    return f"{max(confidences):.1f}" if confidences else "none"


def _text_words(audit: _Audit) -> tuple[Word, ...]:
    """The text words of the audited page, in Tesseract's order."""
    return tuple(word for word in audit.words if is_text_word(word))


def _text_words_read(audit: _Audit) -> str:
    """The number of text words of the audited page and, when it has any,
    the first ten of them, for its WARNING: "2 text words, the first ten
    or fewer: TO MY"."""
    text_words = _text_words(audit)
    if not text_words:
        return "0 text words"
    return f"{len(text_words)} text words, the first ten or fewer: " + " ".join(
        word.text for word in text_words[:_LOGGED_WORDS]
    )


def _log_audited(page: PageInfo, plate_test: _PlateTest) -> None:
    """Logs what the audit made of `page`, when it read it (analyze spec
    section 4). A page made text or front matter is logged at WARNING with
    its numbers of words and of text words and its first ten text words.
    A plate the plate rule did not take is logged at WARNING with its ink
    share and its words' number and highest confidence; one the rule took
    is logged by `_log_plate_taken`. A blank page is logged with the same
    measures, at INFO, or at WARNING when its ink share is 0.04% or more."""
    audit = plate_test.audit
    if audit is None:
        return
    match page.kind:
        case PageKind.TEXT | PageKind.FRONT_MATTER:
            _logger.warning(
                "analyze: page index %d, without a text layer, is read by "
                "Tesseract as %s: %d words, %s; add it to `exclude_pages` if it "
                "is not the book's",
                page.index,
                "text" if page.kind is PageKind.TEXT else "front matter",
                len(audit.words),
                _text_words_read(audit),
            )
        case PageKind.PLATE if plate_test.rule is PlateRule.NOT_PLATE:
            _logger.warning(
                "analyze: page index %d, without a text layer, taken for a "
                "plate: ink covers %.3f%% of it, Tesseract reads %d words, the "
                "highest of confidence %s; add it to `exclude_pages` if it is "
                "not one",
                page.index,
                audit.ink * 100,
                len(audit.words),
                _highest_confidence(audit.words),
            )
        case PageKind.BLANK if audit.ink >= _BLANK_LOOK_LEAST_INK_SHARE:
            _logger.warning(
                "analyze: page index %d, without a text layer, is blank: "
                "Tesseract reads %d words, the highest of confidence %s, and ink "
                "covers %.3f%% of it; check that it holds no print",
                page.index,
                len(audit.words),
                _highest_confidence(audit.words),
                audit.ink * 100,
            )
        case PageKind.BLANK:
            _logger.info(
                "analyze: page index %d, without a text layer, is blank: "
                "Tesseract reads %d words, the highest of confidence %s, and ink "
                "covers %.3f%% of it",
                page.index,
                len(audit.words),
                _highest_confidence(audit.words),
                audit.ink * 100,
            )
        case PageKind.PLATE | PageKind.EXCLUDED | PageKind.INKLESS:
            return
        case _:
            assert_never(page.kind)


def _log_audit_counts(
    pages: tuple[PageInfo, ...], measurements: tuple[_Measurement, ...]
) -> None:
    """Logs at INFO the number of pages the audit read and what they
    became: text (front matter included), a picture, blank, or a plate the
    plate rule took (analyze spec section 4)."""
    audited = tuple(
        (page.kind, measurement.plate_test.rule)
        for page, measurement in zip(pages, measurements, strict=True)
        if measurement.plate_test is not None
        and measurement.plate_test.audit is not None
    )
    text = sum(
        1 for kind, _ in audited if kind in {PageKind.TEXT, PageKind.FRONT_MATTER}
    )
    picture = sum(
        1
        for kind, rule in audited
        if kind is PageKind.PLATE and rule is PlateRule.NOT_PLATE
    )
    blank = sum(1 for kind, _ in audited if kind is PageKind.BLANK)
    taken = sum(
        1
        for kind, rule in audited
        if kind is PageKind.PLATE and rule is PlateRule.PLATE
    )
    _logger.info(
        "analyze: Tesseract read %d pages without a text layer: %d text, %d "
        "picture, %d blank, %d taken by the plate rule",
        len(audited),
        text,
        picture,
        blank,
        taken,
    )


def _plate_rule_tests(page_index: int, config: BookConfig) -> bool:
    """Whether the plate rule tests the page: not an excluded page, not the
    cover, and not a page that `plate_pages` makes a plate anyway."""
    return (
        page_index not in config.exclude_pages
        and page_index != config.cover_page
        and page_index not in config.plate_pages
    )


def _test_plate(
    rendered: RenderedPage,
    layer_words: tuple[tuple[str, Box], ...],
    lower_case_words: frozenset[str],
    audit: _Audit | None,
) -> _PlateTest:
    """The plate rule on a page rendered as `rendered` whose text layer
    holds `layer_words`, each its text and box in points (none without a
    layer): its picture area, its words found in `lower_case_words`, and
    whether the rule takes it as a plate (plates spec, section 2); with
    `audit`, the audit of a page without a text layer, None with one."""
    word_boxes = tuple(box for _, box in layer_words) if layer_words else None
    known_words = sum(
        1 for text, _ in layer_words if wordlist.is_known_word(text, lower_case_words)
    )
    area = picture_area(rendered, word_boxes)
    rule = (
        PlateRule.PLATE
        if is_plate_by_area(area, word_boxes, known_words)
        else PlateRule.NOT_PLATE
    )
    return _PlateTest(area=area, known_words=known_words, rule=rule, audit=audit)


def _log_inkless(page_index: int, ink_test: InkTest) -> None:
    """Logs at WARNING a page made `inkless`, with its share of words without
    ink and how many of those are known words of 2 letters or more, so that
    the owner sees a page taken wrongly (plates spec, section 2b)."""
    _logger.warning(
        "analyze: page index %d is inkless, its words removed: %.2f of its words "
        "have no ink under them, %d of those are known words of 2 letters or "
        "more",
        page_index,
        ink_test.share_without_ink,
        ink_test.known_words,
    )


def _with_figures(page: PageInfo, figures: tuple[PictureGroup, ...]) -> PageInfo:
    """`page` with the boxes of `figures` when it is a text page; a page of
    any other kind has none (figures spec section 3)."""
    if page.kind is not PageKind.TEXT:
        return page
    return replace(page, figure_boxes=tuple(figure.box for figure in figures))


def _log_figures(page_index: int, figures: tuple[PictureGroup, ...]) -> None:
    """Logs at INFO the in-page figures of a page, each box with its squares
    and known words (figures spec section 3)."""
    _logger.info(
        "analyze: page index %d has %d in-page figures: %s",
        page_index,
        len(figures),
        "; ".join(
            f"box ({figure.box.x0:.1f}, {figure.box.top:.1f}, {figure.box.x1:.1f}, "
            f"{figure.box.bottom:.1f}) pt, {figure.squares} squares, "
            f"{figure.known_words} known words"
            for figure in figures
        ),
    )


def _log_front_matter(
    end: int, step: _FrontMatterStep, pages: tuple[PageInfo, ...], config: BookConfig
) -> None:
    """Logs at INFO the front-matter end, the step of the rule that gave it
    and the pages made `front_matter`; and at WARNING an end at the first
    page of running text that makes a page `front_matter` when the config
    has no `contents_pages`, so that the owner adds them (front-matter spec
    section 2)."""
    dropped = tuple(page.index for page in pages if page.kind is PageKind.FRONT_MATTER)
    _logger.info(
        "analyze: the front matter ends at page index %d, by %s; %s",
        end,
        step,
        f"page indices {', '.join(str(index) for index in dropped)} are front "
        "matter, their words dropped"
        if dropped
        else "no page is front matter",
    )
    if step is _FrontMatterStep.RUNNING_TEXT and dropped and not config.contents_pages:
        _logger.warning(
            "analyze: the front matter ends at the first page of running text, "
            "page index %d, and the config has no `contents_pages`; add the pages "
            "of the printed table of contents, or set `front_matter_end`",
            end,
        )


def _log_plate_taken(page: PageInfo, plate_test: _PlateTest) -> None:
    """Logs at WARNING a page the plate rule takes, with what it measured,
    when its kind is `plate`: not an inkless page the rule also takes, which
    is `inkless` or `front_matter` (plates spec section 2b). A page without
    a text layer is logged with the text words the audit read on it
    (analyze spec section 4)."""
    if plate_test.rule is PlateRule.NOT_PLATE or page.kind is not PageKind.PLATE:
        return
    if plate_test.audit is None:
        _logger.warning(
            "analyze: page index %d taken for a plate: a picture of %d squares, "
            "%d known words; add it to `exclude_pages` if it is not one",
            page.index,
            plate_test.area.largest_group,
            plate_test.known_words,
        )
    else:
        _logger.warning(
            "analyze: page index %d, without a text layer, taken for a plate: a "
            "picture of %d of its %d squares, Tesseract reads %s; add it to "
            "`exclude_pages` if it is not one",
            page.index,
            plate_test.area.largest_group,
            plate_test.area.squares,
            _text_words_read(plate_test.audit),
        )


def classify_page(
    index: int,
    width_pt: float,
    height_pt: float,
    layer_word_count: int,
    config: BookConfig,
    *,
    plate_rule: PlateRule,
    ink_rule: InkRule,
    audit: AuditVerdict,
    front_matter_end: int,
) -> PageInfo:
    """What page `index` (from 0) is, given its size in points, the number
    of words of its text layer and what the plate rule, the inkless rule
    and the audit found on it, by the order of analyze spec section 2 and
    the table of its section 4.

    A page in the config's `exclude_pages` is `excluded`; else a page in
    `plate_pages` is a `plate`; else a page the inkless rule takes is
    `front_matter` when its index is below `front_matter_end` and
    `inkless` otherwise, both with no text source, also when the plate
    rule takes it; else a page the audit finds MUCH_TEXT on, not the
    `cover_page`, is read by OCR, `front_matter` below `front_matter_end`
    and `text` otherwise; else a page the plate rule takes that is not the
    `cover_page` is a `plate`; a plate is read from its layer when it has
    a word; else a page with a layer word is `front_matter`, with no text
    source, when its index is below `front_matter_end`, and `text`
    otherwise, read from the layer, or by OCR when the config's `ocr` is
    `redo` (architecture section 7b). A page without a layer word takes
    the audit's verdict: TEXT is read by OCR, `front_matter` or `text` as
    MUCH_TEXT; PICTURE is a `plate` with no text source; BLANK is `blank`
    with `blank_checked_by_ocr`; NOT_AUDITED, and the cover whatever the
    verdict, is `blank` without it. `exclude_regions` holds the boxes of
    the config's regions on this page, in the config's order. No page has
    a score. ValueError for a verdict other than NOT_AUDITED on a page
    with a layer word, which the audit does not read.
    """
    if audit is not AuditVerdict.NOT_AUDITED and layer_word_count > 0:
        message = (
            f"page index {index} has {layer_word_count} words in its text layer "
            f"and the audit's verdict {audit}, but the audit reads only pages "
            "without a text layer"
        )
        raise ValueError(message)
    taken_by_rule = _takes_plate(plate_rule) and index != config.cover_page
    inkless = _takes_inkless(ink_rule) and layer_word_count > 0
    layer_source = TextSource.TEXT_LAYER if layer_word_count > 0 else TextSource.NONE
    is_cover = index == config.cover_page
    read_as_text = (
        PageKind.FRONT_MATTER if index < front_matter_end else PageKind.TEXT,
        TextSource.OCR,
    )
    checked_blank = False
    if index in config.exclude_pages:
        kind, text_source = PageKind.EXCLUDED, TextSource.NONE
    elif index in config.plate_pages:
        kind, text_source = PageKind.PLATE, layer_source
    elif inkless and index < front_matter_end:
        kind, text_source = PageKind.FRONT_MATTER, TextSource.NONE
    elif inkless:
        kind, text_source = PageKind.INKLESS, TextSource.NONE
    elif audit is AuditVerdict.MUCH_TEXT and not is_cover:
        kind, text_source = read_as_text
    elif taken_by_rule:
        kind, text_source = PageKind.PLATE, layer_source
    elif layer_word_count > 0 and index < front_matter_end:
        kind, text_source = PageKind.FRONT_MATTER, TextSource.NONE
    elif layer_word_count > 0:
        kind, text_source = PageKind.TEXT, _text_page_source(config.ocr)
    elif is_cover:
        kind, text_source = PageKind.BLANK, TextSource.NONE
    else:
        kind, text_source, checked_blank = _audited_page(audit, read_as_text)
    return PageInfo(
        index=index,
        width_pt=width_pt,
        height_pt=height_pt,
        kind=kind,
        text_source=text_source,
        text_layer_score=None,
        exclude_regions=tuple(
            region.box
            for region in config.exclude_regions
            if region.page_index == index
        ),
        # analyze adds the boxes of a text page (figures spec section 3).
        figure_boxes=(),
        blank_checked_by_ocr=checked_blank,
    )


def _takes_plate(plate_rule: PlateRule) -> bool:
    """Whether the plate rule took the page."""
    match plate_rule:
        case PlateRule.PLATE:
            return True
        case PlateRule.NOT_PLATE:
            return False
        case _:
            assert_never(plate_rule)


def _takes_inkless(ink_rule: InkRule) -> bool:
    """Whether the inkless rule took the page."""
    match ink_rule:
        case InkRule.INKLESS:
            return True
        case InkRule.NOT_INKLESS:
            return False
        case _:
            assert_never(ink_rule)


def _audited_page(
    audit: AuditVerdict, read_as_text: tuple[PageKind, TextSource]
) -> tuple[PageKind, TextSource, bool]:
    """The kind, the text source and `blank_checked_by_ocr` of a page
    without a text layer that no earlier rule took, by the audit's verdict
    (analyze spec section 4); `read_as_text` is the kind and source of a
    page the audit reads text on."""
    match audit:
        case AuditVerdict.MUCH_TEXT | AuditVerdict.TEXT:
            return (*read_as_text, False)
        case AuditVerdict.PICTURE:
            return PageKind.PLATE, TextSource.NONE, False
        case AuditVerdict.BLANK:
            return PageKind.BLANK, TextSource.NONE, True
        case AuditVerdict.NOT_AUDITED:
            return PageKind.BLANK, TextSource.NONE, False
        case _:
            assert_never(audit)


def _text_page_source(ocr: OcrMode) -> TextSource:
    """The text source of a text page: `ocr` under `redo`, which reads every
    text page with Tesseract, the layer otherwise (architecture section
    7b)."""
    match ocr:
        case OcrMode.REDO:
            return TextSource.OCR
        case OcrMode.VERIFY | OcrMode.TRUST:
            return TextSource.TEXT_LAYER
        case _:
            assert_never(ocr)


def front_matter_end(starts: tuple[PageStart, ...], config: BookConfig) -> int:
    """The index of the first page after the front matter, by the rule of
    the front-matter spec, section 2: the config's front_matter_end; else
    the first preface page or first contents page in the search window;
    else the first page of running text in it; else 0.

    `starts` are every page of the PDF, in index order.
    """
    return _front_matter_end_and_step(starts, config)[0]


def _front_matter_end_and_step(
    starts: tuple[PageStart, ...], config: BookConfig
) -> tuple[int, _FrontMatterStep]:
    """The front-matter end of `front_matter_end`, and the step of the rule
    that gave it."""
    if config.front_matter_end is not None:
        return config.front_matter_end, _FrontMatterStep.CONFIG
    window_pages = max(_SEARCH_WINDOW_LEAST_PAGES, len(starts) // _SEARCH_WINDOW_SHARE)
    window = tuple(page for page in starts if page.index < window_pages)
    found = tuple(
        (page.index, step)
        for page, step in (
            (
                next((page for page in window if _is_preface_page(page)), None),
                _FrontMatterStep.PREFACE,
            ),
            (
                next(
                    (page for page in window if page.index in config.contents_pages),
                    None,
                ),
                _FrontMatterStep.CONTENTS,
            ),
        )
        if page is not None
    )
    if found:
        return min(found, key=lambda index_and_step: index_and_step[0])
    text_word_counts = tuple(
        page.word_count for page in starts if page.kind is PageKind.TEXT
    )
    if text_word_counts:
        least_words = _RUNNING_TEXT_SHARE_OF_MEDIAN * statistics.median(
            text_word_counts
        )
        running_text = next(
            (page for page in window if page.word_count >= least_words), None
        )
        if running_text is not None:
            return running_text.index, _FrontMatterStep.RUNNING_TEXT
    return 0, _FrontMatterStep.NOTHING_FOUND


def _is_preface_page(page: PageStart) -> bool:
    """Whether the topmost row of `page` names a preface: at most 6 words,
    one of which, reduced to its letters in lower case without accents, is
    a preface name (front-matter spec section 1)."""
    return len(page.first_row) <= _PREFACE_ROW_MOST_WORDS and any(
        _letters_without_accents(word) in _PREFACE_NAMES for word in page.first_row
    )


def _letters_without_accents(word: str) -> str:
    """The letters of `word` in lower case without accents: "Préface." gives
    "preface", "AVANT-PROPOS" "avantpropos"."""
    return "".join(
        character
        for character in unicodedata.normalize("NFKD", word.lower())
        if character.isalpha() and not unicodedata.combining(character)
    )


def check_config_pages(config: BookConfig, page_count: int) -> None:
    """Raises ConfigError when a page index of `exclude_pages`, `exclude_regions`,
    `cover_page`, `plate_pages`, `contents_pages` or `front_matter_end` is
    not below `page_count`, naming the key, the index and the count; and
    when a page of `contents_pages` lies before `front_matter_end`, naming
    both keys (front-matter spec section 2)."""
    indices = (
        *(
            (f"exclude_pages[{position}]", index)
            for position, index in enumerate(config.exclude_pages)
        ),
        *(
            (f"exclude_regions[{position}].page", region.page_index)
            for position, region in enumerate(config.exclude_regions)
        ),
        *(() if config.cover_page is None else (("cover_page", config.cover_page),)),
        *(
            (f"plate_pages[{position}]", index)
            for position, index in enumerate(config.plate_pages)
        ),
        *(
            (f"contents_pages[{position}]", index)
            for position, index in enumerate(config.contents_pages)
        ),
        *(
            ()
            if config.front_matter_end is None
            else (("front_matter_end", config.front_matter_end),)
        ),
    )
    for key, index in indices:
        if index >= page_count:
            message = (
                f"key `{key}`: page index {index} is not below the page count "
                f"of {config.pdf}, {page_count}"
            )
            raise ConfigError(message)
    if config.front_matter_end is not None:
        dropped_contents = tuple(
            index for index in config.contents_pages if index < config.front_matter_end
        )
        if dropped_contents:
            message = (
                f"key `contents_pages`: page index {dropped_contents[0]} lies before "
                f"`front_matter_end`, {config.front_matter_end}, and would be "
                "dropped with the front matter; correct one of the two keys"
            )
            raise ConfigError(message)
