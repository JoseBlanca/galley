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
import statistics
from collections.abc import Callable
from contextlib import closing
from dataclasses import replace
from pathlib import Path
from typing import Final, NamedTuple, assert_never

import pdfplumber
from PIL import Image

from galley import ocr, pdfium, text_layer
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

__all__ = [
    "are_over_each_other",
    "figure_crop_px",
    "figure_image",
    "page_words",
    "plate_image",
    "run",
    "with_layer_heights",
    "with_layer_references",
    "with_missed_layer_words",
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
# Extract spec section 9, "Layer words Tesseract missed", measured on the
# whole Kadesh book: a Tesseract word covers a layer word when they overlap
# by a quarter of the lower height (half took many words Tesseract read);
# a layer word is no copy of an unclaimed Tesseract word with its letters
# within 16 pt (the layer misplaces some boxes by 14 pt); the page's offset
# is taken over pairs of 3 or more letters whose middles are less than 12
# pt apart.
_COVER_HEIGHT_SHARE: Final[float] = 0.25
# Extract spec section 9, "Caption numbers from the layer": the words that
# open a caption and the numeral after them, as figures spec section 1
# gives them (structure's own test is not imported: no stage imports
# another).
_CAPTION_WORDS = frozenset(("figure", "fig.", "fig", "plate", "map"))
_NUMERAL_CHARACTERS = frozenset("0123456789ivxlcIVXLC")
_NUMERAL_ENDINGS = (".", ",")
_NUMERAL_MAX_CHARACTERS = 6
_COPY_DISTANCE_PT: Final[float] = 16.0
_OFFSET_PAIR_MIN_CHARACTERS: Final[int] = 3
_OFFSET_PAIR_DISTANCE_PT: Final[float] = 12.0


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
        lambda: text_layer.open_pdf(config.pdf),
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
        "by Tesseract took the layer's note reference or caption number, and "
        "%d words of the "
        "layer that Tesseract missed were kept",
        sum(len(result.page.words) for result in results),
        sum(len(result.removals) for result in results),
        len(results),
        config.pdf,
        sum(result.layer_references for result in results),
        sum(result.layer_words_kept for result in results),
    )


class _PageRead(NamedTuple):
    """What a worker gives for a page: its words, its removals, how many of
    Tesseract's words took the layer's note reference or caption number,
    and how many words
    of the layer Tesseract missed were kept (extract spec section 9)."""

    page: PageWords
    removals: tuple[Removal, ...]
    layer_references: int
    layer_words_kept: int


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
        # On a page read by Tesseract, its words keep their confidence and
        # their order; the layer's words kept among them have none.
        read_by_tesseract = page_read.text_source is TextSource.OCR
        taken = tuple(
            (tesseract_word, taken_word)
            for tesseract_word, taken_word in zip(
                tesseract_words,
                (word for word in words if word.ocr_confidence is not None),
                strict=False,
            )
            if read_by_tesseract and tesseract_word.text != taken_word.text
        )
        for tesseract_word, taken_word in taken:
            _logger.info(
                "extract: page index %d: %r, read by Tesseract, takes the "
                "layer's note reference or caption number: %r",
                page.index,
                tesseract_word.text,
                taken_word.text,
            )
        kept = tuple(
            word.text
            for word in words
            if read_by_tesseract and word.ocr_confidence is None
        )
        if kept:
            _logger.info(
                "extract: page index %d: %d words of the layer that Tesseract "
                "missed are kept: %s",
                page.index,
                len(kept),
                " ".join(kept),
            )
        return _PageRead(*page_words(page_read, words), len(taken), len(kept))

    return read_page


def _words_read(
    page: PageInfo,
    tesseract_words: tuple[Word, ...],
    page_layer_words: tuple[Word, ...],
) -> tuple[PageInfo, tuple[Word, ...]]:
    """The page as extract reads it and its words, given Tesseract's words
    of the page (empty unless its source is `ocr`) and its layer's: a page
    read by OCR has Tesseract's words, with the layer's note references put
    back and the layer words Tesseract missed kept, but when Tesseract found
    none it keeps its layer's, with the source `text_layer`, so that no
    printed word is lost (extract spec section 9); any other page has its
    layer's."""
    if page.text_source is not TextSource.OCR:
        return page, page_layer_words
    if tesseract_words or not page_layer_words:
        return page, with_layer_heights(
            with_missed_layer_words(
                _with_caption_numbers(
                    with_layer_references(tesseract_words, page_layer_words),
                    page_layer_words,
                ),
                tuple(
                    layer_word
                    for layer_word in page_layer_words
                    if not any(
                        _overlap(box.x0, box.x1, layer_word.box.x0, layer_word.box.x1)
                        > 0
                        and _overlap(
                            box.top,
                            box.bottom,
                            layer_word.box.top,
                            layer_word.box.bottom,
                        )
                        > 0
                        for box in page.figure_boxes
                    )
                ),
            ),
            page_layer_words,
        )
    return replace(page, text_source=TextSource.TEXT_LAYER), page_layer_words


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


def _with_caption_numbers(
    ocr_words: tuple[Word, ...], layer_words: tuple[Word, ...]
) -> tuple[Word, ...]:
    """`ocr_words`, each that follows a caption word on its line taking the
    numeral of the layer word over it (extract spec section 9, "Caption
    numbers from the layer")."""
    over = tuple(
        tuple(layer_word for layer_word in layer_words if _over(ocr_word, layer_word))
        for ocr_word in ocr_words
    )
    return tuple(
        replace(ocr_word, text=layer_over[0].text)
        if position > 0
        and ocr_words[position - 1].text.lower() in _CAPTION_WORDS
        and _overlap(
            ocr_words[position - 1].box.top,
            ocr_words[position - 1].box.bottom,
            ocr_word.box.top,
            ocr_word.box.bottom,
        )
        > 0
        and not any(character.isdigit() for character in ocr_word.text)
        and len(layer_over) == 1
        and sum(_over(other, layer_over[0]) for other in ocr_words) == 1
        and _is_numeral(layer_over[0].text)
        else ocr_word
        for position, (ocr_word, layer_over) in enumerate(
            zip(ocr_words, over, strict=True)
        )
    )


def _is_numeral(text: str) -> bool:
    """Whether `text` is a numeral by figures spec section 1: 1 to 6
    characters, each a digit or one of i, v, x, l, c in either case, with
    or without a "." or "," after them."""
    bare = text[:-1] if text.endswith(_NUMERAL_ENDINGS) else text
    return 0 < len(bare) <= _NUMERAL_MAX_CHARACTERS and all(
        character in _NUMERAL_CHARACTERS for character in bare
    )


def _letter_count(text: str) -> int:
    return sum(character.isalpha() for character in text)


def with_missed_layer_words(
    ocr_words: tuple[Word, ...], layer_words: tuple[Word, ...]
) -> tuple[Word, ...]:
    """`ocr_words`, a page's words as Tesseract read them, with the layer
    words Tesseract missed (extract spec section 9) put among them, each
    with its box moved by the page's offset. Each goes before the first
    word of `ocr_words` whose top is lower than its own, in the order of
    `layer_words`."""
    offset = _layer_offset(ocr_words, layer_words)
    moved = tuple(_moved_up(layer_word, offset) for layer_word in layer_words)
    unclaimed = tuple(
        ocr_word
        for ocr_word in ocr_words
        if not any(
            _letters_and_digits(layer_word.text) == _letters_and_digits(ocr_word.text)
            and _covers(ocr_word.box, layer_word.box)
            for layer_word in moved
        )
    )
    missed = tuple(
        layer_word
        for layer_word in moved
        if _letters_and_digits(layer_word.text)
        and not any(_covers(ocr_word.box, layer_word.box) for ocr_word in ocr_words)
        and not any(
            _letters_and_digits(ocr_word.text) == _letters_and_digits(layer_word.text)
            and _gap(
                ocr_word.box.top,
                ocr_word.box.bottom,
                layer_word.box.top,
                layer_word.box.bottom,
            )
            <= _COPY_DISTANCE_PT
            and _gap(
                ocr_word.box.x0, ocr_word.box.x1, layer_word.box.x0, layer_word.box.x1
            )
            <= _COPY_DISTANCE_PT
            for ocr_word in unclaimed
        )
    )
    places = tuple(_place(ocr_words, layer_word) for layer_word in missed)
    words: list[Word] = []
    for position, ocr_word in enumerate(ocr_words):
        words.extend(
            layer_word
            for layer_word, place in zip(missed, places, strict=True)
            if place == position
        )
        words.append(ocr_word)
    words.extend(
        layer_word
        for layer_word, place in zip(missed, places, strict=True)
        if place == len(ocr_words)
    )
    return tuple(words)


def with_layer_heights(
    ocr_words: tuple[Word, ...], layer_words: tuple[Word, ...]
) -> tuple[Word, ...]:
    """`ocr_words` with each word that carries a confidence and that a
    layer word covers given that layer word's top and bottom, moved by
    the page's offset (extract spec section 9)."""
    tesseract_words = tuple(
        word for word in ocr_words if word.ocr_confidence is not None
    )
    offset = _layer_offset(tesseract_words, layer_words)
    moved = tuple(_moved_up(layer_word, offset).box for layer_word in layer_words)
    return tuple(
        word
        if word.ocr_confidence is None
        else _with_height_of(
            word, tuple(box for box in moved if _covers(word.box, box))
        )
        for word in ocr_words
    )


def _with_height_of(ocr_word: Word, covering: tuple[Box, ...]) -> Word:
    """`ocr_word` with the height of the box of `covering`, the moved boxes
    of the layer words that cover it, that overlaps it most, about its own
    middle; as it is when none does."""
    if not covering:
        return ocr_word
    box = ocr_word.box
    largest = max(
        covering,
        key=lambda layer_box: (
            _overlap(box.x0, box.x1, layer_box.x0, layer_box.x1)
            * _overlap(box.top, box.bottom, layer_box.top, layer_box.bottom)
        ),
    )
    half_height = (largest.bottom - largest.top) / 2
    middle = _middle(box)
    return replace(
        ocr_word, box=Box(box.x0, middle - half_height, box.x1, middle + half_height)
    )


def _place(ocr_words: tuple[Word, ...], layer_word: Word) -> int:
    """The position in `ocr_words` before which `layer_word` goes: that of
    the first word whose top is lower than its own, or the end."""
    return next(
        (
            position
            for position, ocr_word in enumerate(ocr_words)
            if ocr_word.box.top > layer_word.box.top
        ),
        len(ocr_words),
    )


def _layer_offset(ocr_words: tuple[Word, ...], layer_words: tuple[Word, ...]) -> float:
    """How far the layer's boxes sit below Tesseract's on a page: the median,
    over the pairs of a layer word and a Tesseract word with the same 3 or
    more letters and digits, overlapping in width, with middles less than
    12 pt apart up or down, of the layer word's middle less the Tesseract
    word's; 0 without a pair (extract spec section 9)."""
    differences = tuple(
        _middle(layer_word.box) - _middle(ocr_word.box)
        for layer_word in layer_words
        if len(_letters_and_digits(layer_word.text)) >= _OFFSET_PAIR_MIN_CHARACTERS
        for ocr_word in ocr_words
        if _letters_and_digits(ocr_word.text) == _letters_and_digits(layer_word.text)
        and _overlap(
            ocr_word.box.x0, ocr_word.box.x1, layer_word.box.x0, layer_word.box.x1
        )
        > 0
        and abs(_middle(layer_word.box) - _middle(ocr_word.box))
        < _OFFSET_PAIR_DISTANCE_PT
    )
    return statistics.median(differences) if differences else 0.0


def _covers(ocr_box: Box, layer_box: Box) -> bool:
    """Whether a Tesseract word's box covers a layer word's, already moved
    by the offset: they overlap in width, and in height by a quarter of the
    lower height (extract spec section 9)."""
    height_overlap = _overlap(
        ocr_box.top, ocr_box.bottom, layer_box.top, layer_box.bottom
    )
    return (
        _overlap(ocr_box.x0, ocr_box.x1, layer_box.x0, layer_box.x1) > 0
        and height_overlap > 0
        and height_overlap
        >= _COVER_HEIGHT_SHARE
        * min(ocr_box.bottom - ocr_box.top, layer_box.bottom - layer_box.top)
    )


def _moved_up(layer_word: Word, offset: float) -> Word:
    box = layer_word.box
    return replace(
        layer_word, box=Box(box.x0, box.top - offset, box.x1, box.bottom - offset)
    )


def _middle(box: Box) -> float:
    return (box.top + box.bottom) / 2


def _overlap(start: float, end: float, other_start: float, other_end: float) -> float:
    """The length two intervals share, 0 when they do not meet."""
    return max(0.0, min(end, other_end) - max(start, other_start))


def _gap(start: float, end: float, other_start: float, other_end: float) -> float:
    """The distance between two intervals, 0 when they meet."""
    return max(0.0, max(start, other_start) - min(end, other_end))


def _letters_and_digits(text: str) -> str:
    return "".join(character.lower() for character in text if character.isalnum())


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
        return text_layer.layer_words(pdf_page)


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
    page: PageInfo, read_words: tuple[Word, ...]
) -> tuple[PageWords, tuple[Removal, ...]]:
    """The words of `page` and its removals, given `read_words`, the words pdfplumber read
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
            kept, removals = _kept_and_region_removals(page, read_words)
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
            if page.text_source is TextSource.NONE and read_words:
                message = (
                    f"page {page.index} is a plate without a text layer, but "
                    f"{len(read_words)} words were given for it"
                )
                raise ValueError(message)
            kept, removals = _kept_and_region_removals(page, read_words)
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
                _removal(page, read_word, RemovalReason.EXCLUDED_PAGE)
                for read_word in read_words
            )
        case PageKind.FRONT_MATTER:
            # Front-matter spec, section 3: every word a removal, as on an
            # excluded page.
            kept = ()
            removals = tuple(
                _removal(page, read_word, RemovalReason.FRONT_MATTER)
                for read_word in read_words
            )
        case PageKind.INKLESS:
            # Plates spec, section 2b: every word a removal, as on an
            # excluded page, but a word in an excluded region, which keeps
            # the reason of any page.
            kept = ()
            removals = tuple(
                _removal(
                    page,
                    read_word,
                    RemovalReason.EXCLUDED_REGION
                    if _in_a_region(read_word.box, page.exclude_regions)
                    else RemovalReason.INKLESS_PAGE,
                )
                for read_word in read_words
            )
        case PageKind.BLANK:
            if read_words:
                message = (
                    f"page {page.index} is blank, with no text layer, but "
                    f"{len(read_words)} words were given for it"
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
    page: PageInfo, read_words: tuple[Word, ...]
) -> tuple[tuple[Word, ...], tuple[Removal, ...]]:
    """The words of `page` outside its `exclude_regions`, and those inside
    as removals with the reason `excluded_region`."""
    kept = tuple(
        read_word
        for read_word in read_words
        if not _in_a_region(read_word.box, page.exclude_regions)
    )
    removals = tuple(
        _removal(page, read_word, RemovalReason.EXCLUDED_REGION)
        for read_word in read_words
        if _in_a_region(read_word.box, page.exclude_regions)
    )
    return kept, removals


def _removal(page: PageInfo, read_word: Word, reason: RemovalReason) -> Removal:
    return Removal(
        page_index=page.index, box=read_word.box, text=read_word.text, reason=reason
    )


def _in_a_region(box: Box, regions: tuple[Box, ...]) -> bool:
    """Whether the middle of `box` is inside one of `regions`, edges included."""
    return any(box_holds_middle(region, box) for region in regions)
