"""analyze: what each page of the PDF is, written to pages.json (walking
skeleton spec section 6, plates spec section 2).

analyze measures every page with pdfplumber, its size in points and the
words of its text layer, and renders every page that is neither excluded
nor the cover at 36 dpi to test whether it is a plate (`is_plate`). A page
is `excluded` when the config excludes it, a `plate` when the config's
`plate_pages` names it or the plate rule takes it, `text` when its layer
has a word, and `blank` otherwise. It has no OCR, so a blank page stops
the run: the owner checks it and adds it to `exclude_pages`. Each page the
plate rule takes is logged at WARNING, so that the owner sees the covers
and endpapers it takes too.
"""

import logging
from collections.abc import Callable
from contextlib import closing
from dataclasses import dataclass
from enum import StrEnum
from typing import assert_never

import pdfplumber

from galley import pdfium, wordlist
from galley.analyze._plates import (
    PLATE_RENDER_DPI,
    PictureArea,
    is_plate,
    is_plate_by_area,
    picture_area,
)
from galley.book_folder import BookFolder, Stage, delete_stage_outputs
from galley.config import BookConfig, OcrMode
from galley.errors import ConfigError, PdfError
from galley.model import (
    Box,
    PageInfo,
    PageKind,
    PagesFile,
    RenderedPage,
    TextSource,
    pdf_sha256,
    write_pages,
)
from galley.parallel import DEFAULT_WORKERS, map_pages_with_source
from galley.text_layer import layer_words, open_pdf

__all__ = [
    "PictureArea",
    "PlateRule",
    "check_config_pages",
    "classify_page",
    "is_plate",
    "picture_area",
    "require_text_layer",
    "run",
]

_logger = logging.getLogger(__name__)


class PlateRule(StrEnum):
    """What the plate rule of plates spec section 2 found on a page: a
    plate, or not one (also for a page it does not test, an excluded page
    or the cover)."""

    PLATE = "plate"
    NOT_PLATE = "not_plate"


@dataclass(frozen=True, slots=True)
class _PlateTest:
    """What the plate rule measured on a page it tested: its picture area,
    the known words of its text layer (0 without one), whether it has a
    layer, and the rule's finding."""

    area: PictureArea
    known_words: int
    has_layer: bool
    rule: PlateRule


@dataclass(frozen=True, slots=True)
class _Measurement:
    """What analyze measures of one page: its size in points from
    pdfplumber, the number of words of its text layer, and the plate
    rule's test, None for a page it does not test."""

    width_pt: float
    height_pt: float
    layer_word_count: int
    plate_test: _PlateTest | None


def run(
    folder: BookFolder, config: BookConfig, *, workers: int = DEFAULT_WORKERS
) -> None:
    """Writes `folder.pages_json`, what each page of `config.pdf` is.

    Deletes pages.json and every later stage's file first (words.json,
    images/, lines.json, blocks.json, book.md, book.epub), so that a failed
    run leaves none and no later file outlives the pages.json it came from.
    Takes the word list of the book's language from its cache folder,
    extracting it with Tesseract's tools the first time. Raises
    ConfigError when the config asks for OCR or names a page past the end
    of the PDF, and PdfError when a page that the config does not exclude
    has no text layer and is not a plate. `workers` is the number of
    threads that measure the pages; the renders are made in the one PDFium
    thread.
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
    pages = tuple(
        classify_page(
            index,
            measurement.width_pt,
            measurement.height_pt,
            measurement.layer_word_count,
            config,
            plate_rule=PlateRule.NOT_PLATE
            if measurement.plate_test is None
            else measurement.plate_test.rule,
        )
        for index, measurement in enumerate(measurements)
    )
    for index, measurement in enumerate(measurements):
        _log_plate_taken(index, measurement.plate_test)
    require_text_layer(pages)
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
    in the worker."""

    def measure(pdf: pdfplumber.PDF, page_index: int) -> _Measurement:
        with closing(pdf.pages[page_index]) as page:
            width_pt = float(page.width)
            height_pt = float(page.height)
            # Extract spec section 5: the words extract writes.
            page_layer_words = tuple(
                (layer_word.text, layer_word.box) for layer_word in layer_words(page)
            )
        plate_test = (
            _test_plate(
                pdfium.render(config.pdf, page_index, PLATE_RENDER_DPI),
                page_layer_words,
                lower_case_words,
            )
            if _plate_rule_tests(page_index, config)
            else None
        )
        return _Measurement(
            width_pt=width_pt,
            height_pt=height_pt,
            layer_word_count=len(page_layer_words),
            plate_test=plate_test,
        )

    return measure


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
) -> _PlateTest:
    """The plate rule on a page rendered as `rendered` whose text layer
    holds `layer_words`, each its text and box in points (none without a
    layer): its picture area, its words found in `lower_case_words`, and
    whether the rule takes it as a plate (plates spec, section 2)."""
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
    return _PlateTest(
        area=area, known_words=known_words, has_layer=bool(layer_words), rule=rule
    )


def _log_plate_taken(page_index: int, plate_test: _PlateTest | None) -> None:
    """Logs at WARNING a page the plate rule takes, with what it measured."""
    if plate_test is None or plate_test.rule is PlateRule.NOT_PLATE:
        return
    if plate_test.has_layer:
        _logger.warning(
            "analyze: page index %d taken for a plate: a picture of %d squares, "
            "%d known words; add it to `exclude_pages` if it is not one",
            page_index,
            plate_test.area.largest_group,
            plate_test.known_words,
        )
    else:
        _logger.warning(
            "analyze: page index %d, without a text layer, taken for a plate: a "
            "picture of %d of its %d squares; add it to `exclude_pages` if it "
            "is not one",
            page_index,
            plate_test.area.largest_group,
            plate_test.area.squares,
        )


def classify_page(
    index: int,
    width_pt: float,
    height_pt: float,
    layer_word_count: int,
    config: BookConfig,
    *,
    plate_rule: PlateRule,
) -> PageInfo:
    """What page `index` (from 0) is, given its size in points, the number
    of words of its text layer and what the plate rule found on it.

    A page in the config's `exclude_pages` is `excluded`; else a page in
    `plate_pages`, or one the plate rule takes that is not the
    `cover_page`, is a `plate`, read from its layer when it has a word;
    else a page with a layer word is `text`, read from the layer; else it
    is `blank`. `exclude_regions` holds the boxes of the config's regions
    on this page, in the config's order. No page is checked by OCR and
    none has a score.
    """
    match plate_rule:
        case PlateRule.PLATE:
            taken_by_rule = index != config.cover_page
        case PlateRule.NOT_PLATE:
            taken_by_rule = False
        case _:
            assert_never(plate_rule)
    layer_source = TextSource.TEXT_LAYER if layer_word_count > 0 else TextSource.NONE
    if index in config.exclude_pages:
        kind, text_source = PageKind.EXCLUDED, TextSource.NONE
    elif index in config.plate_pages or taken_by_rule:
        kind, text_source = PageKind.PLATE, layer_source
    elif layer_word_count > 0:
        kind, text_source = PageKind.TEXT, TextSource.TEXT_LAYER
    else:
        kind, text_source = PageKind.BLANK, TextSource.NONE
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
        blank_checked_by_ocr=False,
    )


def check_config_pages(config: BookConfig, page_count: int) -> None:
    """Raises ConfigError when the config's `ocr` is `redo`, which needs OCR,
    or when a page index of `exclude_pages`, `exclude_regions`,
    `cover_page`, `plate_pages` or `contents_pages` is not below
    `page_count`, naming the key, the index and the count."""
    if config.ocr is OcrMode.REDO:
        message = (
            "ocr = redo needs OCR, which the walking skeleton does not have; "
            "use verify or trust"
        )
        raise ConfigError(message)
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
    )
    for key, index in indices:
        if index >= page_count:
            message = (
                f"key `{key}`: page index {index} is not below the page count "
                f"of {config.pdf}, {page_count}"
            )
            raise ConfigError(message)


def require_text_layer(pages: tuple[PageInfo, ...]) -> None:
    """Raises PdfError listing every blank page: a page without a text layer
    that the config does not exclude and that is not a plate, which the
    walking skeleton cannot read, having no OCR."""
    blank = tuple(page.index for page in pages if page.kind is PageKind.BLANK)
    if blank:
        message = (
            f"page indices {', '.join(str(index) for index in blank)}: these "
            "pages have no text layer, and the walking skeleton has no OCR; add "
            "them to `exclude_pages` once you have checked that they hold no text"
        )
        raise PdfError(message)
