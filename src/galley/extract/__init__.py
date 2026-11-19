"""extract: the words of every page, written to words.json (walking
skeleton spec section 6, plates spec section 3, figures spec section 4,
extract spec section 9).

extract reads the words of each text page, and of each plate page that
has a text layer, from the PDF's text layer with pdfplumber, one document
per worker thread. A page whose text source is `ocr`, every text page
under `ocr = "redo"`, is rendered at 300 dpi in the PDFium thread and read
with Tesseract in the worker; when Tesseract finds no word on it, the
page keeps the layer's words. The words of an excluded page, of a front-matter page
(front-matter spec section 3), and those whose centre falls in a region
the config excludes, become removals, so that no word is dropped without
a record. A plate page is rendered whole at 300 dpi
into `images/plate-<page index, 4 digits>.png`, and the page gets one
figure, the whole page. A text page with figure boxes in pages.json is
rendered at 300 dpi and each box cut into
`images/figure-<page index, 4 digits>-<n>.png`, one in-page figure each.
The cover is rendered as `images/cover.png`.
"""

import logging
import math
from collections.abc import Callable
from contextlib import closing
from dataclasses import replace
from pathlib import Path
from typing import Final, NamedTuple, assert_never

import pdfplumber
from PIL import Image

from galley import ocr, pdfium
from galley.book_folder import BookFolder, Stage, delete_stage_outputs
from galley.config import BookConfig, tesseract_language
from galley.model import (
    Box,
    Figure,
    FigureKind,
    PageInfo,
    PageKind,
    PageWords,
    Removal,
    RemovalReason,
    RenderedPage,
    TextSource,
    Word,
    WordsFile,
    box_holds_middle,
    read_checked_pages,
    write_words,
)
from galley.note_references import after_last_letter, glued_reference
from galley.parallel import DEFAULT_WORKERS, map_pages_with_source
from galley.text_layer import layer_words, open_pdf

__all__ = [
    "are_over_each_other",
    "figure_crop_px",
    "figure_image",
    "page_words",
    "plate_image",
    "run",
    "with_layer_references",
]

_logger = logging.getLogger(__name__)

# Architecture section 9: pages are rendered at 300 dpi; spec section 6
# gives 2118 x 3034 pixels for the Kadesh cover. The same for plates (plates
# spec section 3).
_COVER_DPI: Final[int] = 300
_PLATE_DPI: Final[int] = 300
# Figures spec section 4: an in-page figure is cut from a render at 300 dpi.
_FIGURE_DPI: Final[int] = 300
# Extract spec section 9: Tesseract finds the blocks of the whole page.
_OCR_PAGE_SEGMENTATION: Final[int] = 3
# Extract spec section 9: a Tesseract word and a layer word are over each
# other when they overlap by half the lower height and half the narrower
# width; a third of the height took 4 wrong references on Kadesh.
_OVER_EACH_OTHER_SHARE: Final[float] = 0.5


def run(
    folder: BookFolder, config: BookConfig, *, workers: int = DEFAULT_WORKERS
) -> None:
    """Writes `folder.words_json`, the words of every page of `config.pdf`
    as `folder.pages_json` describes them, the image of each plate page and
    of each in-page figure in `images/`, and `images/cover.png` when the
    config has a `cover_page`.

    A page whose text source is `ocr` is read with Tesseract (extract spec
    section 9); one where Tesseract finds no word keeps its layer's words,
    with the source `text_layer`, and is logged at WARNING.

    Deletes words.json, images/ and every later stage's file first
    (lines.json, blocks.json, book.md, book.epub), then always creates
    images/, empty without a cover, a plate or a figure. Raises
    InputFileError when pages.json is missing, malformed or made from
    another PDF, and ExternalProgramError when Tesseract fails on a page.
    `workers` is the number of threads that read the pages, run Tesseract
    and write the figures' images; the renders are made in the one PDFium
    thread.
    """
    delete_stage_outputs(folder, Stage.EXTRACT)
    pages_file = read_checked_pages(folder.pages_json, config.pdf)
    folder.images_dir.mkdir()
    results = map_pages_with_source(
        lambda: open_pdf(config.pdf),
        _page_reader(config, folder.root),
        pages_file.pages,
        workers,
    )
    if config.cover_page is not None:
        _save_cover(config.pdf, config.cover_page, folder.cover_png)
    write_words(
        folder.words_json,
        WordsFile(
            source_pdf_sha256=pages_file.source_pdf_sha256,
            pages=tuple(result.page for result in results),
            removals=tuple(
                removal for result in results for removal in result.removals
            ),
        ),
    )
    _logger.info(
        "extract: %d words and %d removals from %d pages of %s; %d words read "
        "by Tesseract took the layer's note reference",
        sum(len(result.page.words) for result in results),
        sum(len(result.removals) for result in results),
        len(results),
        config.pdf,
        sum(result.layer_references for result in results),
    )


class _PageRead(NamedTuple):
    """What a worker gives for a page: its words, its removals, and how many
    of Tesseract's words took the layer's note reference (extract spec
    section 9)."""

    page: PageWords
    removals: tuple[Removal, ...]
    layer_references: int


def _page_reader(
    config: BookConfig, book_root: Path
) -> Callable[[pdfplumber.PDF, PageInfo], _PageRead]:
    """The function a worker thread runs on each page: it reads the page's
    text layer with the worker's pdfplumber document; on a page read by
    OCR, has the PDFium thread render it and runs Tesseract on the render;
    and on a plate page or a page with figures, has it rendered and saves
    the images from the worker."""
    pdf_path = config.pdf
    language = tesseract_language(config.language)

    def read_page(pdf: pdfplumber.PDF, page: PageInfo) -> _PageRead:
        # A blank page, and a plate without a text layer, are not read: their
        # layer has no word, as analyze found.
        unread = page.kind is PageKind.BLANK or (
            page.kind is PageKind.PLATE and page.text_source is TextSource.NONE
        )
        page_layer_words = () if unread else _layer_words(pdf, page.index)
        ocr_render = (
            pdfium.render(pdf_path, page.index, ocr.OCR_DPI)
            if page.text_source is TextSource.OCR
            else None
        )
        tesseract_words = (
            ()
            if ocr_render is None
            else ocr.read_image(
                _image(ocr_render),
                origin=(0.0, 0.0),
                dpi=ocr_render.dpi,
                psm=_OCR_PAGE_SEGMENTATION,
                language=language,
            )
        )
        if page.kind is PageKind.PLATE:
            _save_png(
                pdfium.render(pdf_path, page.index, _PLATE_DPI),
                book_root / plate_image(page.index),
            )
        if page.kind is PageKind.TEXT and page.figure_boxes:
            _save_figures(
                ocr_render
                if ocr_render is not None and ocr_render.dpi == _FIGURE_DPI
                else pdfium.render(pdf_path, page.index, _FIGURE_DPI),
                page,
                book_root,
            )
        page_read, words = _words_read(page, tesseract_words, page_layer_words)
        if page_read.text_source is not page.text_source:
            _logger.warning(
                "extract: page index %d: Tesseract found no word on it; it keeps "
                "the %d words of its text layer",
                page.index,
                len(words),
            )
        taken = tuple(
            (tesseract_word, taken_word)
            for tesseract_word, taken_word in zip(tesseract_words, words, strict=False)
            if page_read.text_source is TextSource.OCR
            and tesseract_word.text != taken_word.text
        )
        for tesseract_word, taken_word in taken:
            _logger.info(
                "extract: page index %d: %r, read by Tesseract, takes the "
                "layer's note reference: %r",
                page.index,
                tesseract_word.text,
                taken_word.text,
            )
        return _PageRead(*page_words(page_read, words), len(taken))

    return read_page


def _words_read(
    page: PageInfo, tesseract_words: tuple[Word, ...], layer_words: tuple[Word, ...]
) -> tuple[PageInfo, tuple[Word, ...]]:
    """The page as extract reads it and its words, given Tesseract's words
    of the page (empty unless its source is `ocr`) and its layer's: a page
    read by OCR has Tesseract's words, but when Tesseract found none it
    keeps its layer's, with the source `text_layer`, so that no printed word
    is lost (extract spec section 9); any other page has its layer's."""
    if page.text_source is not TextSource.OCR:
        return page, layer_words
    if tesseract_words or not layer_words:
        return page, with_layer_references(tesseract_words, layer_words)
    return replace(page, text_source=TextSource.TEXT_LAYER), layer_words


def with_layer_references(
    ocr_words: tuple[Word, ...], layer_words: tuple[Word, ...]
) -> tuple[Word, ...]:
    """`ocr_words`, a page's words as Tesseract read them, each that
    takes the layer's note reference (extract spec section 9) with its
    text changed, in the same order."""
    over = tuple(
        tuple(layer_word for layer_word in layer_words if _over(ocr_word, layer_word))
        for ocr_word in ocr_words
    )
    return tuple(
        _with_layer_reference(ocr_word, layer_over[0])
        if len(layer_over) == 1
        and sum(_over(other, layer_over[0]) for other in ocr_words) == 1
        else ocr_word
        for ocr_word, layer_over in zip(ocr_words, over, strict=True)
    )


def _over(ocr_word: Word, layer_word: Word) -> bool:
    return are_over_each_other(ocr_word.box, layer_word.box)


def _with_layer_reference(ocr_word: Word, layer_word: Word) -> Word:
    """`ocr_word` with the reference glued to `layer_word`, the one layer
    word over it, when the two words meet conditions 1, 3 and 4 of extract
    spec section 9; else `ocr_word` as it is."""
    if (
        glued_reference(layer_word.text) is None
        or any(character.isdigit() for character in ocr_word.text)
        or _letter_count(ocr_word.text) == 0
        or _letter_count(ocr_word.text) != _letter_count(layer_word.text)
    ):
        return ocr_word
    text = ocr_word.text[
        : len(ocr_word.text) - len(after_last_letter(ocr_word.text))
    ] + after_last_letter(layer_word.text)
    return replace(ocr_word, text=text)


def _letter_count(text: str) -> int:
    return sum(character.isalpha() for character in text)


def are_over_each_other(one: Box, other: Box) -> bool:
    """Whether two word boxes overlap by half the lower height and half
    the narrower width (extract spec section 9)."""
    height_overlap = max(0.0, min(one.bottom, other.bottom) - max(one.top, other.top))
    width_overlap = max(0.0, min(one.x1, other.x1) - max(one.x0, other.x0))
    return (
        height_overlap > 0
        and width_overlap > 0
        and height_overlap
        >= _OVER_EACH_OTHER_SHARE * min(one.bottom - one.top, other.bottom - other.top)
        and width_overlap
        >= _OVER_EACH_OTHER_SHARE * min(one.x1 - one.x0, other.x1 - other.x0)
    )


def plate_image(page_index: int) -> str:
    """The path of the image of the plate on page `page_index`, relative to
    the book folder: `images/plate-0016.png` for page 16 (plates spec
    section 3)."""
    return f"images/plate-{page_index:04d}.png"


def figure_image(page_index: int, number: int) -> str:
    """The path of the image of the in-page figure `number`, from 1 in the
    order of pages.json, on page `page_index`, relative to the book folder:
    `images/figure-0025-1.png` for the first on page index 25 (figures spec
    section 4)."""
    return f"images/figure-{page_index:04d}-{number}.png"


def figure_crop_px(box: Box, dpi: int) -> tuple[int, int, int, int]:
    """The pixels of a render at `dpi` that `box`, in points, covers, as
    (left, top, right, bottom), right and bottom excluded: each side
    rounded outwards to a whole pixel (figures spec section 4)."""
    scale = dpi / pdfium.POINTS_PER_INCH
    return (
        math.floor(box.x0 * scale),
        math.floor(box.top * scale),
        math.ceil(box.x1 * scale),
        math.ceil(box.bottom * scale),
    )


def _save_figures(rendered: RenderedPage, page: PageInfo, book_root: Path) -> None:
    """Saves the image of each in-page figure of `page`, cut from
    `rendered`, the page at 300 dpi, as an 8-bit grayscale PNG. A box that
    runs past the render is cut to it, with a warning that names the page:
    analyze's boxes lie on the page, so it is a box made from another
    render or a page of another size."""
    image = _image(rendered)
    for number, box in enumerate(page.figure_boxes, start=1):
        left, top, right, bottom = figure_crop_px(box, rendered.dpi)
        if (
            left < 0
            or top < 0
            or right > rendered.width_px
            or bottom > rendered.height_px
        ):
            _logger.warning(
                "extract: page index %d, figure %d: its box (%.1f, %.1f, %.1f, "
                "%.1f) pt runs past the page's render, %d by %d pixels at %d "
                "dpi; the image is cut to the render",
                page.index,
                number,
                box.x0,
                box.top,
                box.x1,
                box.bottom,
                rendered.width_px,
                rendered.height_px,
                rendered.dpi,
            )
        image.crop(
            (
                max(0, left),
                max(0, top),
                min(rendered.width_px, right),
                min(rendered.height_px, bottom),
            )
        ).save(book_root / figure_image(page.index, number), format="PNG")


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
    _image(rendered).save(path, format="PNG")


def _image(rendered: RenderedPage) -> Image.Image:
    """`rendered` as an 8-bit grayscale Pillow image."""
    return Image.frombytes(
        "L", (rendered.width_px, rendered.height_px), rendered.pixels
    )


def page_words(
    page: PageInfo, layer_words: tuple[Word, ...]
) -> tuple[PageWords, tuple[Removal, ...]]:
    """The words of `page` and its removals, given the words pdfplumber read
    from its text layer, in that order (empty for a blank page and a plate
    without a text layer), or for a page whose text source is `ocr` the
    words Tesseract read, in its order (extract spec section 9).

    A text page, and a plate page with a text layer, keep every word but
    those whose centre is inside one of its `exclude_regions`, edges
    included, which are removals with the reason `excluded_region`. Every
    word of an excluded page is a removal with the reason `excluded_page`,
    and of a front-matter page one with the reason `front_matter`; every
    word of an inkless page is a removal with the reason `inkless_page`, but
    one inside an excluded region, which is `excluded_region`. A blank
    page has neither. A plate page has one figure, the whole page, at 300
    dpi, whose image is `plate_image(page.index)`, of kind `plate`; a text
    page has one for each of its `figure_boxes`, in their order, with that
    box, at 300 dpi, whose image is `figure_image(page.index, n)`, n from 1,
    of kind `in_page`; no other page has one. Raises ValueError for a blank
    page or a plate without a text layer given words, which would be lost.
    """
    figures: tuple[Figure, ...] = ()
    match page.kind:
        case PageKind.TEXT:
            kept, removals = _kept_and_region_removals(page, layer_words)
            figures = tuple(
                Figure(
                    box=box,
                    image=figure_image(page.index, number),
                    dpi=_FIGURE_DPI,
                    kind=FigureKind.IN_PAGE,
                )
                for number, box in enumerate(page.figure_boxes, start=1)
            )
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
                    kind=FigureKind.PLATE,
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
        case PageKind.INKLESS:
            # Plates spec, section 2b: every word a removal, as on an
            # excluded page, but a word in an excluded region, which keeps
            # the reason of any page.
            kept = ()
            removals = tuple(
                _removal(
                    page,
                    layer_word,
                    RemovalReason.EXCLUDED_REGION
                    if _in_a_region(layer_word.box, page.exclude_regions)
                    else RemovalReason.INKLESS_PAGE,
                )
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
    """Whether the middle of `box` is inside one of `regions`, edges included."""
    return any(box_holds_middle(region, box) for region in regions)
