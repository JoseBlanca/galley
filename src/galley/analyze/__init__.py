"""analyze: what each page of the PDF is, written to pages.json (spec section 6).

The walking skeleton's analyze measures every page with pdfplumber, its
size in points and how many words its text layer holds, and calls a page
`text` when the layer has a word, `excluded` when the config excludes it,
and `blank` otherwise. It has no OCR, so a blank page stops the run: the
owner checks it and adds it to `exclude_pages`.
"""

import logging
import shutil
from contextlib import closing
from dataclasses import dataclass

import pdfplumber

from galley import pdfium
from galley.book_folder import BookFolder
from galley.config import BookConfig, OcrMode
from galley.errors import ConfigError, PdfError
from galley.model import (
    PageInfo,
    PageKind,
    PagesFile,
    TextSource,
    pdf_sha256,
    write_pages,
)
from galley.parallel import DEFAULT_WORKERS, map_pages_with_source

__all__ = ["check_config_pages", "classify_page", "require_text_layer", "run"]

_logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class _Measurement:
    """What pdfplumber gives of one page: its size in points and the number
    of words of its text layer."""

    width_pt: float
    height_pt: float
    layer_word_count: int


def run(
    folder: BookFolder, config: BookConfig, *, workers: int = DEFAULT_WORKERS
) -> None:
    """Writes `folder.pages_json`, what each page of `config.pdf` is.

    Deletes pages.json and every later stage's file first (words.json,
    images/, lines.json, blocks.json, book.md, book.epub), so that a failed
    run leaves none and no later file outlives the pages.json it came from.
    Raises ConfigError when the config asks for OCR or names a page past
    the end of the PDF, and PdfError when a page that the config does not
    exclude has no text layer. `workers` is the number of threads that
    measure the pages.
    """
    for generated in (
        folder.pages_json,
        folder.words_json,
        folder.lines_json,
        folder.blocks_json,
        folder.book_md,
        folder.book_epub,
    ):
        generated.unlink(missing_ok=True)
    if folder.images_dir.exists():
        shutil.rmtree(folder.images_dir)
    page_count = pdfium.page_count(config.pdf)
    check_config_pages(config, page_count)
    measurements = map_pages_with_source(
        lambda: pdfplumber.open(config.pdf), _measure, range(page_count), workers
    )
    pages = tuple(
        classify_page(
            index,
            measurement.width_pt,
            measurement.height_pt,
            measurement.layer_word_count,
            config,
        )
        for index, measurement in enumerate(measurements)
    )
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


def _measure(pdf: pdfplumber.PDF, page_index: int) -> _Measurement:
    with closing(pdf.pages[page_index]) as page:
        return _Measurement(
            width_pt=float(page.width),
            height_pt=float(page.height),
            layer_word_count=len(page.extract_words()),
        )


def classify_page(
    index: int,
    width_pt: float,
    height_pt: float,
    layer_word_count: int,
    config: BookConfig,
) -> PageInfo:
    """What page `index` (from 0) is, given its size in points and the number
    of words of its text layer.

    A page in the config's `exclude_pages` is `excluded`; else a page with a
    layer word is `text`, read from the layer; else it is `blank`.
    `exclude_regions` holds the boxes of the config's regions on this page,
    in the config's order. No page is checked by OCR and none has a score.
    """
    if index in config.exclude_pages:
        kind, text_source = PageKind.EXCLUDED, TextSource.NONE
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
    or when a page index of `exclude_pages`, `exclude_regions` or
    `cover_page` is not below `page_count`, naming the key, the index and
    the count."""
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
    that the config does not exclude, which the walking skeleton cannot
    read, having no OCR."""
    blank = tuple(page.index for page in pages if page.kind is PageKind.BLANK)
    if blank:
        message = (
            f"page indices {', '.join(str(index) for index in blank)}: these "
            "pages have no text layer, and the walking skeleton has no OCR; add "
            "them to `exclude_pages` once you have checked that they hold no text"
        )
        raise PdfError(message)
