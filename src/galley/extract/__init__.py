"""extract: the words of every page, written to words.json (walking
skeleton spec section 6, plates spec section 3).

extract reads the words of each text page, and of each plate page that
has a text layer, from the PDF's text layer with pdfplumber, one document
per worker thread. The words of an excluded page, of a front-matter page
(front-matter spec section 3), and those whose centre falls in a region
the config excludes, become removals, so that no word is dropped without
a record. A plate page is rendered whole at 300 dpi
into `images/plate-<page index, 4 digits>.png`, and the page gets one
figure, the whole page. The cover is rendered as `images/cover.png`.
"""

import logging
from collections.abc import Callable
from contextlib import closing
from pathlib import Path
from typing import Final, assert_never

import pdfplumber
from PIL import Image

from galley import pdfium
from galley.book_folder import BookFolder, Stage, delete_stage_outputs
from galley.config import BookConfig
from galley.errors import InputFileError
from galley.model import (
    Box,
    Figure,
    PageInfo,
    PageKind,
    PageWords,
    Removal,
    RemovalReason,
    RenderedPage,
    TextSource,
    Word,
    WordsFile,
    read_checked_pages,
    write_words,
)
from galley.parallel import DEFAULT_WORKERS, map_pages_with_source
from galley.text_layer import layer_words, open_pdf

__all__ = ["page_words", "plate_image", "run"]

_logger = logging.getLogger(__name__)

# Architecture section 9: pages are rendered at 300 dpi; spec section 6
# gives 2118 x 3034 pixels for the Kadesh cover. The same for plates (plates
# spec section 3).
_COVER_DPI: Final[int] = 300
_PLATE_DPI: Final[int] = 300


def run(
    folder: BookFolder, config: BookConfig, *, workers: int = DEFAULT_WORKERS
) -> None:
    """Writes `folder.words_json`, the words of every page of `config.pdf`
    as `folder.pages_json` describes them, the image of each plate page in
    `images/`, and `images/cover.png` when the config has a `cover_page`.

    Deletes words.json, images/ and every later stage's file first
    (lines.json, blocks.json, book.md, book.epub), then always creates
    images/, empty without a cover or a plate. Raises InputFileError when
    pages.json is missing, malformed, made from another PDF, or holds a
    page read by OCR, which extract cannot read yet. `workers` is the
    number of threads that read the pages and write the plates' images;
    the renders are made in the one PDFium thread.
    """
    delete_stage_outputs(folder, Stage.EXTRACT)
    pages_file = read_checked_pages(folder.pages_json, config.pdf)
    unreadable = tuple(
        page.index for page in pages_file.pages if page.text_source is TextSource.OCR
    )
    if unreadable:
        message = (
            f"{folder.pages_json}: page indices "
            f"{', '.join(str(index) for index in unreadable)} are read by OCR, "
            "which extract cannot read yet; run `galley2epub analyze` again"
        )
        raise InputFileError(message)
    folder.images_dir.mkdir()
    results = map_pages_with_source(
        lambda: open_pdf(config.pdf),
        _page_reader(config.pdf, folder.root),
        pages_file.pages,
        workers,
    )
    if config.cover_page is not None:
        _save_cover(config.pdf, config.cover_page, folder.cover_png)
    write_words(
        folder.words_json,
        WordsFile(
            source_pdf_sha256=pages_file.source_pdf_sha256,
            pages=tuple(page for page, _ in results),
            removals=tuple(removal for _, removals in results for removal in removals),
        ),
    )
    _logger.info(
        "extract: %d words and %d removals from %d pages of %s",
        sum(len(page.words) for page, _ in results),
        sum(len(removals) for _, removals in results),
        len(results),
        config.pdf,
    )


def _page_reader(
    pdf_path: Path, book_root: Path
) -> Callable[[pdfplumber.PDF, PageInfo], tuple[PageWords, tuple[Removal, ...]]]:
    """The function a worker thread runs on each page: it reads the page's
    text layer with the worker's pdfplumber document and, on a plate page,
    has the PDFium thread render it and saves the image from the worker."""

    def read_page(
        pdf: pdfplumber.PDF, page: PageInfo
    ) -> tuple[PageWords, tuple[Removal, ...]]:
        # A blank page, and a plate without a text layer, are not read: their
        # layer has no word, as analyze found.
        unread = page.kind is PageKind.BLANK or (
            page.kind is PageKind.PLATE and page.text_source is TextSource.NONE
        )
        page_layer_words = () if unread else _layer_words(pdf, page.index)
        if page.kind is PageKind.PLATE:
            _save_png(
                pdfium.render(pdf_path, page.index, _PLATE_DPI),
                book_root / plate_image(page.index),
            )
        return page_words(page, page_layer_words)

    return read_page


def plate_image(page_index: int) -> str:
    """The path of the image of the plate on page `page_index`, relative to
    the book folder: `images/plate-0016.png` for page 16 (plates spec
    section 3)."""
    return f"images/plate-{page_index:04d}.png"


def _layer_words(pdf: pdfplumber.PDF, page_index: int) -> tuple[Word, ...]:
    """The words of the page's text layer, as `text_layer.layer_words`
    reads them (extract spec section 5)."""
    with closing(pdf.pages[page_index]) as pdf_page:
        return layer_words(pdf_page)


def _save_cover(pdf: Path, cover_page: int, cover_png: Path) -> None:
    # analyze checked cover_page against the page count; pdfium.render
    # raises PdfError if the PDF has fewer pages now.
    _save_png(pdfium.render(pdf, cover_page, _COVER_DPI), cover_png)


def _save_png(rendered: RenderedPage, path: Path) -> None:
    """Saves `rendered` as an 8-bit grayscale PNG at `path`."""
    Image.frombytes("L", (rendered.width_px, rendered.height_px), rendered.pixels).save(
        path, format="PNG"
    )


def page_words(
    page: PageInfo, layer_words: tuple[Word, ...]
) -> tuple[PageWords, tuple[Removal, ...]]:
    """The words of `page` and its removals, given the words pdfplumber read
    from its text layer, in that order (empty for a blank page and a plate
    without a text layer).

    A text page, and a plate page with a text layer, keep every word but
    those whose centre is inside one of its `exclude_regions`, edges
    included, which are removals with the reason `excluded_region`. Every
    word of an excluded page is a removal with the reason `excluded_page`,
    and of a front-matter page one with the reason `front_matter`.
    A blank page has neither. A plate page has one figure, the whole page,
    at 300 dpi, whose image is `plate_image(page.index)`; no other page
    has one. Raises ValueError for a page read by OCR, which extract
    cannot read yet, and for a blank page or a plate without a text layer
    given words, which would be lost.
    """
    if page.text_source is TextSource.OCR:
        message = f"page {page.index} is read by OCR, which extract cannot read yet"
        raise ValueError(message)
    figures: tuple[Figure, ...] = ()
    match page.kind:
        case PageKind.TEXT:
            kept, removals = _kept_and_region_removals(page, layer_words)
        case PageKind.PLATE:
            if page.text_source is TextSource.NONE and layer_words:
                message = (
                    f"page {page.index} is a plate without a text layer, but "
                    f"{len(layer_words)} words were given for it"
                )
                raise ValueError(message)
            kept, removals = _kept_and_region_removals(page, layer_words)
            figures = (
                Figure(
                    box=Box(0.0, 0.0, page.width_pt, page.height_pt),
                    image=plate_image(page.index),
                    dpi=_PLATE_DPI,
                ),
            )
        case PageKind.EXCLUDED:
            kept = ()
            removals = tuple(
                _removal(page, layer_word, RemovalReason.EXCLUDED_PAGE)
                for layer_word in layer_words
            )
        case PageKind.FRONT_MATTER:
            # Front-matter spec, section 3: every word a removal, as on an
            # excluded page.
            kept = ()
            removals = tuple(
                _removal(page, layer_word, RemovalReason.FRONT_MATTER)
                for layer_word in layer_words
            )
        case PageKind.BLANK:
            if layer_words:
                message = (
                    f"page {page.index} is blank, with no text layer, but "
                    f"{len(layer_words)} words were given for it"
                )
                raise ValueError(message)
            kept, removals = (), ()
        case _:
            assert_never(page.kind)
    return (
        PageWords(
            index=page.index, text_source=page.text_source, words=kept, figures=figures
        ),
        removals,
    )


def _kept_and_region_removals(
    page: PageInfo, layer_words: tuple[Word, ...]
) -> tuple[tuple[Word, ...], tuple[Removal, ...]]:
    """The words of `page` outside its `exclude_regions`, and those inside
    as removals with the reason `excluded_region`."""
    kept = tuple(
        layer_word
        for layer_word in layer_words
        if not _in_a_region(layer_word.box, page.exclude_regions)
    )
    removals = tuple(
        _removal(page, layer_word, RemovalReason.EXCLUDED_REGION)
        for layer_word in layer_words
        if _in_a_region(layer_word.box, page.exclude_regions)
    )
    return kept, removals


def _removal(page: PageInfo, layer_word: Word, reason: RemovalReason) -> Removal:
    return Removal(
        page_index=page.index, box=layer_word.box, text=layer_word.text, reason=reason
    )


def _in_a_region(box: Box, regions: tuple[Box, ...]) -> bool:
    """Whether the centre of `box` is inside one of `regions`, edges included."""
    centre_x = (box.x0 + box.x1) / 2
    centre_y = (box.top + box.bottom) / 2
    return any(
        region.x0 <= centre_x <= region.x1 and region.top <= centre_y <= region.bottom
        for region in regions
    )
