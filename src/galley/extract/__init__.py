"""extract: the words of every page, written to words.json (spec section 6).

The walking skeleton's extract reads the words of each text page from the
PDF's text layer with pdfplumber, one document per worker thread. The
words of an excluded page, and those whose centre falls in a region the
config excludes, become removals, so that no word is dropped without a
record. It cuts no figure, and renders only the cover.
"""

import logging
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
    PageInfo,
    PageKind,
    PageWords,
    Removal,
    RemovalReason,
    TextSource,
    Word,
    WordsFile,
    read_checked_pages,
    write_words,
)
from galley.parallel import DEFAULT_WORKERS, map_pages_with_source

__all__ = ["page_words", "run"]

_logger = logging.getLogger(__name__)

# Architecture section 9: pages are rendered at 300 dpi; spec section 6
# gives 2118 x 3034 pixels for the Kadesh cover.
_COVER_DPI: Final[int] = 300


def run(
    folder: BookFolder, config: BookConfig, *, workers: int = DEFAULT_WORKERS
) -> None:
    """Writes `folder.words_json`, the words of every page of `config.pdf`
    as `folder.pages_json` describes them, and `images/cover.png` when the
    config has a `cover_page`.

    Deletes words.json, images/ and every later stage's file first
    (lines.json, blocks.json, book.md, book.epub), then always creates
    images/, empty without a cover. Raises InputFileError when pages.json
    is missing, malformed, made from another PDF, or holds a page the
    walking skeleton cannot read (a plate, or a page read by OCR).
    `workers` is the number of threads that read the pages.
    """
    delete_stage_outputs(folder, Stage.EXTRACT)
    pages_file = read_checked_pages(folder.pages_json, config.pdf)
    unreadable = tuple(page.index for page in pages_file.pages if _unreadable(page))
    if unreadable:
        message = (
            f"{folder.pages_json}: page indices "
            f"{', '.join(str(index) for index in unreadable)} are plates or read "
            "by OCR, which the walking skeleton cannot read; run `galley2epub "
            "analyze` again"
        )
        raise InputFileError(message)
    results = map_pages_with_source(
        lambda: pdfplumber.open(config.pdf), _read_page, pages_file.pages, workers
    )
    folder.images_dir.mkdir()
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


def _unreadable(page: PageInfo) -> bool:
    """Whether the walking skeleton cannot read the page: it cuts no figure
    from a plate and has no OCR."""
    return page.kind is PageKind.PLATE or page.text_source is TextSource.OCR


def _read_page(
    pdf: pdfplumber.PDF, page: PageInfo
) -> tuple[PageWords, tuple[Removal, ...]]:
    # A blank page is not read: its layer has no word, as analyze found.
    layer_words = () if page.kind is PageKind.BLANK else _layer_words(pdf, page.index)
    return page_words(page, layer_words)


def _layer_words(pdf: pdfplumber.PDF, page_index: int) -> tuple[Word, ...]:
    """The words of the page's text layer, as extract_words() gives them
    with its default options, in its order."""
    with closing(pdf.pages[page_index]) as pdf_page:
        return tuple(
            Word(
                layer_word["text"],
                Box(
                    float(layer_word["x0"]),
                    float(layer_word["top"]),
                    float(layer_word["x1"]),
                    float(layer_word["bottom"]),
                ),
                None,
            )
            for layer_word in pdf_page.extract_words()
        )


def _save_cover(pdf: Path, cover_page: int, cover_png: Path) -> None:
    # analyze checked cover_page against the page count; pdfium.render
    # raises PdfError if the PDF has fewer pages now.
    rendered = pdfium.render(pdf, cover_page, _COVER_DPI)
    Image.frombytes("L", (rendered.width_px, rendered.height_px), rendered.pixels).save(
        cover_png, format="PNG"
    )


def page_words(
    page: PageInfo, layer_words: tuple[Word, ...]
) -> tuple[PageWords, tuple[Removal, ...]]:
    """The words of `page` and its removals, given the words pdfplumber read
    from its text layer, in that order (empty for a blank page).

    A text page keeps every word but those whose centre is inside one of
    its `exclude_regions`, edges included, which are removals with the
    reason `excluded_region`. Every word of an excluded page is a removal
    with the reason `excluded_page`. A blank page has neither. The page
    has no figure. Raises ValueError for a page the walking skeleton cannot
    read, a plate or a page read by OCR, and for a blank page given words,
    which would be lost.
    """
    if page.text_source is TextSource.OCR:
        message = (
            f"page {page.index} is read by OCR, which the walking skeleton has not"
        )
        raise ValueError(message)
    match page.kind:
        case PageKind.TEXT:
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
        case PageKind.EXCLUDED:
            kept = ()
            removals = tuple(
                _removal(page, layer_word, RemovalReason.EXCLUDED_PAGE)
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
        case PageKind.PLATE:
            message = (
                f"page {page.index} is a plate, from which the walking skeleton "
                "cuts no figure"
            )
            raise ValueError(message)
        case _:
            assert_never(page.kind)
    return (
        PageWords(
            index=page.index, text_source=page.text_source, words=kept, figures=()
        ),
        removals,
    )


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
