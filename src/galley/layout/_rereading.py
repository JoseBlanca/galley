"""The re-reading of a page's small print with Tesseract inside layout
(docs/specs/reocr.md, sections 3 and 4): rendering the page, reading each
region found by `_reread`, choosing the readings and laying the page out
again with the words kept (`layout_page_with_rereads`), and what `run`
needs for it (`rereading`).
"""

from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Protocol

from PIL import Image

from galley import pdfium, wordlist
from galley.body_measures import (
    group_rows,
)
from galley.config import BookConfig, OcrMode, tesseract_language
from galley.errors import ExternalProgramError
from galley.layout._column import (
    BookMeasures,
    ColumnSplit,
    Side,
    running_head_row_count,
    split_at_column,
)
from galley.layout._page import (
    PageParts,
    column_regions_with_drop_capitals,
    drop_capital_indices,
    layout_page,
    page_parts,
    page_regions,
    regions_of_parts,
    words_of,
)
from galley.layout._reread import (
    NOTE_PSM,
    SMALL_PRINT_PSM,
    RegionReading,
    cut_in_crops,
    cut_in_reading,
    footnote_band_crop,
    footnote_band_reading,
    is_small_print_page,
    margin_note_reading,
    margin_note_sides,
    margin_strip,
    note_bands,
    page_rereads,
    pixel_box,
    small_print_crop,
    small_print_reading,
)
from galley.model import (
    Box,
    FigureKind,
    PageLayout,
    PageWords,
    Reread,
    RereadKind,
    TextSource,
    Word,
    WordsFile,
    box_holds_middle,
    take_out_once,
    words_after_rereads,
)
from galley.ocr import OCR_DPI, point_box, read_image_lines
from galley.parallel import map_pages

# Re-reading small print (docs/specs/reocr.md, sections 3 and 4).


class ReadLines(Protocol):
    """Tesseract run on an image: its words grouped by its lines, with
    boxes in points on the page, as `ocr.read_image_lines` gives them."""

    def __call__(
        self, image: Image.Image, *, origin: tuple[float, float], psm: int
    ) -> tuple[tuple[Word, ...], ...]:
        """The words of `image`, a crop of a page rendered at `OCR_DPI`
        whose top left lies at `origin`, (left, top) in points on the page,
        read with page segmentation mode `psm`."""
        ...


@dataclass(frozen=True, slots=True, kw_only=True)
class Rereading:
    """What layout needs to re-read a page's small print with Tesseract
    (reocr spec, sections 3, 4 and 6).

    `pdf` is the book's PDF, which an error names; `render` gives the page
    of a page index rendered whole at `OCR_DPI`, a
    grayscale Pillow image; `read_lines` runs Tesseract on a crop of it.
    `lower_case_words` is the word list of the book's language in lower
    case, for the reading scores. `margin_note_sides` are the sides of the
    book whose outer margins hold notes (`margin_note_sides` of the book's
    pages), and `footnote_bands` whether each page's footnote band is read
    too (the config's `reread_footnotes`).
    """

    pdf: Path
    render: Callable[[int], Image.Image]
    read_lines: ReadLines
    lower_case_words: frozenset[str]
    margin_note_sides: frozenset[Side]
    footnote_bands: bool


def _words_of_lines(lines: tuple[tuple[Word, ...], ...]) -> tuple[Word, ...]:
    return tuple(word for line in lines for word in line)


def _read_crop(
    image: Image.Image, pixels: tuple[int, int, int, int], psm: int, read: ReadLines
) -> tuple[tuple[Word, ...], ...]:
    """Tesseract's lines of the crop `pixels` of `image`, a page rendered at
    `OCR_DPI`, cut to the image's edges; no line when nothing is left of
    the crop."""
    clamped = _inside_image(pixels, image)
    if clamped is None:
        return ()
    origin = point_box(clamped, origin=(0.0, 0.0), dpi=OCR_DPI)
    return read(image.crop(clamped), origin=(origin.x0, origin.top), psm=psm)


def _inside_image(
    pixels: tuple[int, int, int, int], image: Image.Image
) -> tuple[int, int, int, int] | None:
    """The crop box `pixels` cut to the edges of `image`; None when nothing
    of it is left."""
    width, height = image.size
    left, top = max(0, pixels[0]), max(0, pixels[1])
    right, bottom = min(width, pixels[2]), min(height, pixels[3])
    if right <= left or bottom <= top:
        return None
    return left, top, right, bottom


def _page_size(image: Image.Image) -> Box:
    """The page of `image`, rendered whole at `OCR_DPI`, in points."""
    width, height = image.size
    return point_box((0, 0, width, height), origin=(0.0, 0.0), dpi=OCR_DPI)


def _head_words(column: tuple[Word, ...], measures: BookMeasures) -> tuple[Word, ...]:
    """The words of the running-head region of a column of `column`'s words
    (step 3)."""
    rows = group_rows(column)
    head_count = running_head_row_count(rows, measures.body_line_pitch)
    return words_of(rows[:head_count])


def _layer_band_words(parts: PageParts, measures: BookMeasures) -> tuple[Word, ...]:
    """The words of the footnote band that step 4 finds among the column's
    words of `parts`, in the order of its rows."""
    _, band = column_regions_with_drop_capitals(
        parts.column,
        drop_capital_indices(parts, measures),
        parts.left,
        measures,
        None,
    )
    return tuple(word for region in band for word in words_of(region.lines))


def _margin_readings(
    page: PageWords,
    parts: PageParts,
    image: Image.Image,
    rereading: Rereading,
) -> tuple[RegionReading, ...]:
    """The note bands of the outer margins of `page` on the book's sides
    with margin notes, each read (reocr spec, section 3, kind 2)."""
    column = (*parts.column, *parts.left_cut_in, *parts.right_cut_in)
    if not column:
        return ()
    page_width = _page_size(image).x1
    readings = []
    for side in sorted(rereading.margin_note_sides):
        strip = margin_strip(
            side,
            left=parts.left,
            right=parts.right,
            column_top=min(word.box.top for word in column),
            lowest=max(word.box.bottom for word in page.words),
            page_width=page_width,
        )
        clamped = _inside_image(pixel_box(strip, OCR_DPI), image)
        if clamped is None:
            continue
        strip_left, strip_top = clamped[0], clamped[1]
        strip_image = image.crop(clamped)
        for band in note_bands(strip_image, dpi=OCR_DPI):
            band_pixels = (
                strip_left + band[0],
                strip_top + band[1],
                strip_left + band[2],
                strip_top + band[3],
            )
            readings.append(
                margin_note_reading(
                    side,
                    point_box(band_pixels, origin=(0.0, 0.0), dpi=OCR_DPI),
                    _words_of_lines(
                        _read_crop(image, band_pixels, NOTE_PSM, rereading.read_lines)
                    ),
                    page_words=page.words,
                    edge=parts.left if side is Side.LEFT else parts.right,
                )
            )
    return tuple(readings)


def _cut_in_readings(
    parts: PageParts,
    measures: BookMeasures,
    image: Image.Image,
    rereading: Rereading,
    head_bottom: float | None,
) -> tuple[RegionReading, ...]:
    """The crops of the notes cut into the column of a page placed as
    `parts`, each read (reocr spec, section 3, kind 3)."""
    readings = []
    for side, zones, edge, inset, cut_in_words in (
        (
            Side.LEFT,
            parts.left_zones,
            parts.left,
            measures.cut_in_inset_left,
            parts.left_cut_in,
        ),
        (
            Side.RIGHT,
            parts.right_zones,
            parts.right,
            measures.cut_in_inset_right,
            parts.right_cut_in,
        ),
    ):
        if inset is None or not zones:
            continue
        for crop in cut_in_crops(
            zones,
            side,
            edge=edge,
            inset=inset,
            pitch=measures.body_line_pitch,
            head_bottom=head_bottom,
        ):
            readings.append(
                cut_in_reading(
                    side,
                    crop,
                    _read_crop(
                        image,
                        pixel_box(crop.box, OCR_DPI),
                        NOTE_PSM,
                        rereading.read_lines,
                    ),
                    edge=edge,
                    inset=inset,
                    cut_in_words=cut_in_words,
                    column_words=parts.column,
                )
            )
    return tuple(readings)


def _page_readings(
    page: PageWords,
    parts: PageParts,
    measures: BookMeasures,
    rereading: Rereading,
) -> tuple[RegionReading, ...]:
    """The regions of `page` read with Tesseract, as `_read_regions` gives
    them, each without the words whose middle lies inside one of the
    page's in-page figures, Tesseract's and the layer's it may replace
    (figures spec section 5): a crop may run across a figure, whose words
    are its region's and never read again. A failure of Tesseract is an
    ExternalProgramError that names the page and the PDF."""
    try:
        readings = _read_regions(page, parts, measures, rereading)
    except ExternalProgramError as err:
        msg = f"re-reading page {page.index} of {rereading.pdf}: {err}"
        raise ExternalProgramError(msg) from err
    boxes = tuple(
        figure.box for figure in page.figures if figure.kind is FigureKind.IN_PAGE
    )
    if not boxes:
        return readings
    return tuple(_outside_figures(reading, boxes) for reading in readings)


def _outside_figures(reading: RegionReading, boxes: tuple[Box, ...]) -> RegionReading:
    """`reading` without its words, Tesseract's and the layer's, whose
    middle lies inside one of `boxes`, edges included."""

    def outside(words: tuple[Word, ...]) -> tuple[Word, ...]:
        return tuple(
            word
            for word in words
            if not any(box_holds_middle(box, word.box) for box in boxes)
        )

    return replace(
        reading,
        ocr_words=outside(reading.ocr_words),
        layer_words=outside(reading.layer_words),
    )


def _read_regions(
    page: PageWords,
    parts: PageParts,
    measures: BookMeasures,
    rereading: Rereading,
) -> tuple[RegionReading, ...]:
    """The regions of `page` read with Tesseract (reocr spec, sections 3
    and 4): the whole page below its running head when it is a small-print
    page, and then no other region; else the note bands of its outer
    margins, the crops of its cut-in notes and, when `rereading` asks, its
    footnote band. The page is rendered once, and only when it has a
    region to read."""
    head = _head_words(parts.column, measures)
    head_bottom = max((word.box.bottom for word in head), default=None)
    small_print = is_small_print_page(page, measures)
    band = (
        _layer_band_words(parts, measures)
        if rereading.footnote_bands and not small_print
        else ()
    )
    if not (
        small_print
        or rereading.margin_note_sides
        or parts.left_zones
        or parts.right_zones
        or band
    ):
        return ()
    image = rereading.render(page.index)
    if small_print:
        page_size = _page_size(image)
        crop = small_print_crop(
            page_width=page_size.x1,
            page_height=page_size.bottom,
            head_bottom=head_bottom,
        )
        return (
            small_print_reading(
                crop,
                _words_of_lines(
                    _read_crop(
                        image,
                        pixel_box(crop, OCR_DPI),
                        SMALL_PRINT_PSM,
                        rereading.read_lines,
                    )
                ),
                page_words=page.words,
                head_words=head,
            ),
        )
    footnote = ()
    if band:
        crop = footnote_band_crop(band, left=parts.left, right=parts.right)
        footnote = (
            footnote_band_reading(
                crop,
                _words_of_lines(
                    _read_crop(
                        image, pixel_box(crop, OCR_DPI), NOTE_PSM, rereading.read_lines
                    )
                ),
                band_words=band,
            ),
        )
    return (
        *_margin_readings(page, parts, image, rereading),
        *_cut_in_readings(parts, measures, image, rereading, head_bottom),
        *footnote,
    )


def _side_of(record: Reread, parts: PageParts) -> Side:
    """The side of the column a margin note band or a cut-in crop lies at:
    that of its crop's middle."""
    middle = (record.box.x0 + record.box.x1) / 2
    return Side.LEFT if middle < (parts.left + parts.right) / 2 else Side.RIGHT


def _ocr_words_of(
    kept: tuple[Reread, ...], kind: RereadKind, side: Side | None, parts: PageParts
) -> tuple[Word, ...]:
    return tuple(
        word
        for record in kept
        if record.kind is kind and (side is None or _side_of(record, parts) is side)
        for word in record.ocr_words
    )


def _parts_after_rereads(
    parts: PageParts, kept: tuple[Reread, ...], measures: BookMeasures
) -> PageParts:
    """The parts of a page with the kept records `kept` of its regions read
    again (reocr spec, section 4): each record's layer words taken out of
    the part that holds them, and its Tesseract words put into the part of
    its kind, the side's margin words, the side's cut-in words or the
    band, which the later steps lay out as they lay out the layer's."""
    band_read = _ocr_words_of(kept, RereadKind.FOOTNOTE_BAND, None, parts)
    layer_band = (
        _layer_band_words(parts, measures)
        if any(record.kind is RereadKind.FOOTNOTE_BAND for record in kept)
        else ()
    )
    (column,) = take_out_once((parts.column,), layer_band)
    left_margin, right_margin, left_cut_in, right_cut_in, column, band = take_out_once(
        (
            parts.left_margin,
            parts.right_margin,
            parts.left_cut_in,
            parts.right_cut_in,
            column,
            layer_band,
        ),
        (word for record in kept for word in record.layer_words),
    )
    return replace(
        parts,
        left_margin=(
            *left_margin,
            *_ocr_words_of(kept, RereadKind.MARGIN_NOTE, Side.LEFT, parts),
        ),
        right_margin=(
            *right_margin,
            *_ocr_words_of(kept, RereadKind.MARGIN_NOTE, Side.RIGHT, parts),
        ),
        left_cut_in=(
            *left_cut_in,
            *_ocr_words_of(kept, RereadKind.CUT_IN_NOTE, Side.LEFT, parts),
        ),
        right_cut_in=(
            *right_cut_in,
            *_ocr_words_of(kept, RereadKind.CUT_IN_NOTE, Side.RIGHT, parts),
        ),
        column=column,
        band=(*band, *band_read) if layer_band else None,
    )


def layout_page_with_rereads(
    page: PageWords, measures: BookMeasures | None, rereading: Rereading | None
) -> tuple[PageLayout, tuple[Reread, ...]]:
    """The layout of one page, as `layout_page` gives it, with its small
    print re-read with Tesseract (reocr spec, sections 3 and 4), and the
    records of the regions read, in their order.

    Nothing is read, and the layout is `layout_page`'s, when `rereading`
    or `measures` is None, or the page's words are not the text layer's.
    Each region is found on the layer's words, read, and kept or not by
    `page_rereads`. A small-print page whose reading is kept is laid out
    from its words after the record (`model.words_after_rereads`), by
    steps 1 to 7; on another page, each kept region's Tesseract words go
    into the part the replaced words were in, and the later steps lay
    them out.
    """
    if (
        rereading is None
        or measures is None
        or not page.words
        or page.text_source is not TextSource.TEXT_LAYER
    ):
        return layout_page(page, measures), ()
    parts = page_parts(page.words, page.index, measures)
    records = page_rereads(
        page.index,
        _page_readings(page, parts, measures, rereading),
        rereading.lower_case_words,
        page_words=page.words,
    )
    kept = tuple(record for record in records if record.kept)
    if not kept:
        return layout_page(page, measures), records
    if kept[0].kind is RereadKind.SMALL_PRINT_PAGE:
        regions = page_regions(
            words_after_rereads(page.words, kept), page.index, measures
        )
    else:
        regions = regions_of_parts(
            _parts_after_rereads(parts, kept, measures), measures
        )
    return PageLayout(page.index, regions, page.figures), records


def _rendered_image(pdf: Path, page_index: int) -> Image.Image:
    """Page `page_index` of `pdf` rendered at `OCR_DPI` by the PDFium
    thread, as a grayscale Pillow image."""
    rendered = pdfium.render(pdf, page_index, OCR_DPI)
    return Image.frombytes(
        "L", (rendered.width_px, rendered.height_px), rendered.pixels
    )


def rereading_of_book(
    config: BookConfig,
    words: WordsFile,
    measures: BookMeasures | None,
    workers: int,
) -> Rereading | None:
    """What layout needs to re-read the small print of the book of `words`;
    None when the config's `ocr` is not `verify` (reocr spec, section 3) or
    the book has no measures."""
    if config.ocr is not OcrMode.VERIFY or measures is None:
        return None
    lower_case_words = wordlist.lower_case_word_list(
        config.language, wordlist.DEFAULT_CACHE_DIR
    )
    language = tesseract_language(config.language)

    def split(page: PageWords) -> tuple[int, ColumnSplit]:
        return len(page.words), split_at_column(page.words, page.index, measures)

    def render(page_index: int) -> Image.Image:
        return _rendered_image(config.pdf, page_index)

    def read_lines(
        image: Image.Image, *, origin: tuple[float, float], psm: int
    ) -> tuple[tuple[Word, ...], ...]:
        return read_image_lines(
            image, origin=origin, dpi=OCR_DPI, psm=psm, language=language
        )

    return Rereading(
        pdf=config.pdf,
        render=render,
        read_lines=read_lines,
        lower_case_words=lower_case_words,
        margin_note_sides=margin_note_sides(
            map_pages(
                split, tuple(page for page in words.pages if page.words), workers
            ),
            lower_case_words,
        ),
        footnote_bands=config.reread_footnotes,
    )
