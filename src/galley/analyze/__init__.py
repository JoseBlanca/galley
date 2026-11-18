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
import statistics
import unicodedata
from collections.abc import Callable
from contextlib import closing
from dataclasses import dataclass
from enum import StrEnum
from typing import Final, assert_never

import pdfplumber

from galley import pdfium, wordlist
from galley.analyze._plates import (
    PLATE_RENDER_DPI,
    PictureArea,
    is_plate,
    is_plate_by_area,
    picture_area,
)
from galley.body_measures import group_rows
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
    "PageStart",
    "PictureArea",
    "PlateRule",
    "check_config_pages",
    "classify_page",
    "front_matter_end",
    "is_plate",
    "picture_area",
    "require_text_layer",
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
    pdfplumber, the number of words of its text layer, the words of the
    layer's topmost row (empty without words), and the plate rule's test,
    None for a page it does not test."""

    width_pt: float
    height_pt: float
    layer_word_count: int
    first_row: tuple[str, ...]
    plate_test: _PlateTest | None


def run(
    folder: BookFolder, config: BookConfig, *, workers: int = DEFAULT_WORKERS
) -> None:
    """Writes `folder.pages_json`, what each page of `config.pdf` is.

    Deletes pages.json and every later stage's file first (words.json,
    images/, lines.json, blocks.json, book.md, book.epub), so that a failed
    run leaves none and no later file outlives the pages.json it came from.
    Takes the word list of the book's language from its cache folder,
    extracting it with Tesseract's tools the first time. The text pages
    before the front-matter end (`front_matter_end`) are `front_matter`.
    Raises ConfigError when the config asks for OCR, names a page past the
    end of the PDF or a contents page before its `front_matter_end`, and
    PdfError when a page that the config does not exclude
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

    def classify(end: int) -> tuple[PageInfo, ...]:
        return tuple(
            classify_page(
                index,
                measurement.width_pt,
                measurement.height_pt,
                measurement.layer_word_count,
                config,
                plate_rule=PlateRule.NOT_PLATE
                if measurement.plate_test is None
                else measurement.plate_test.rule,
                front_matter_end=end,
            )
            for index, measurement in enumerate(measurements)
        )

    starts = tuple(
        PageStart(
            index=page.index,
            kind=page.kind,
            first_row=measurement.first_row,
            word_count=measurement.layer_word_count,
        )
        for page, measurement in zip(classify(0), measurements, strict=True)
    )
    end, step = _front_matter_end_and_step(starts, config)
    pages = classify(end)
    for index, measurement in enumerate(measurements):
        _log_plate_taken(index, measurement.plate_test)
    _log_front_matter(end, step, pages, config)
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
            words = layer_words(page)
        page_layer_words = tuple((word.text, word.box) for word in words)
        rows = group_rows(words)
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
            first_row=tuple(word.text for word in rows[0].words) if rows else (),
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
    front_matter_end: int,
) -> PageInfo:
    """What page `index` (from 0) is, given its size in points, the number
    of words of its text layer and what the plate rule found on it.

    A page in the config's `exclude_pages` is `excluded`; else a page in
    `plate_pages`, or one the plate rule takes that is not the
    `cover_page`, is a `plate`, read from its layer when it has a word;
    else a page with a layer word is `front_matter`, with no text source,
    when its index is below `front_matter_end`, and `text`, read from the
    layer, otherwise; else it is `blank`. `exclude_regions` holds the boxes of the config's regions
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
    elif layer_word_count > 0 and index < front_matter_end:
        kind, text_source = PageKind.FRONT_MATTER, TextSource.NONE
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
        # The rule of docs/specs/figures.md, section 3, is not written yet.
        figure_boxes=(),
        blank_checked_by_ocr=False,
    )


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
    """Raises ConfigError when the config's `ocr` is `redo`, which needs OCR,
    or when a page index of `exclude_pages`, `exclude_regions`,
    `cover_page`, `plate_pages`, `contents_pages` or `front_matter_end` is
    not below `page_count`, naming the key, the index and the count; and
    when a page of `contents_pages` lies before `front_matter_end`, naming
    both keys (front-matter spec section 2)."""
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
