"""layout: each page's words grouped into regions and lines, in reading order.

The rules are those of docs/specs/layout.md. `measure_book` takes the
book's measures over all its pages: the width of the body column, the
height of a body word, the distance between rows, the usual left edge of
the column, and the cut-in insets, how far inside the column the body
lines beside a margin note set into the column start or end (of the six
sample books, only Stubbs has them); the height and the distance are taken
by `galley.body_measures`, which structure shares, and so are the rows:
`body_measures.group_rows` groups words into lines by the walking
skeleton's rule, a word joining the line of the word that started it, its
anchor, when the word's vertical centre lies within the anchor's top and
bottom. `layout_page` places the body column on the page, takes the words
outside it, and the words of the notes set into it beside its shortened
lines, as margin regions, the first row set apart at the top as the
running-head region and the small rows at the foot as the footnote band,
cuts the body and the band into two columns where a gutter runs down them,
and puts a drop capital first in the line beside it.
`layout_page_with_rereads` does the same and re-reads the page's small
print with Tesseract where it reads better than the text layer
(docs/specs/reocr.md): a page printed wholly in small type, the note
bands of the outer margins, the crops of the cut-in notes and, when the
config asks, the footnote band. The laying out of a page is in `_page`,
the steps it shares with the re-reading in `_column`, the re-reading's
crops and choices in `_reread`, and its rendering, reading and laying out
again in `_rereading`. `run` measures the
book, then lays out its pages in parallel, re-reading unless the config's
`ocr` is `trust` or `redo`. On a page with in-page figures, the words
inside each figure's box are first set apart as its region
(`figure_regions`, docs/specs/figures.md section 5), never re-read.
"""

import bisect
import logging
from dataclasses import replace
from statistics import median
from typing import Final

from galley.body_measures import (
    body_measures,
    commonest,
    group_rows,
    measured_page_positions,
    measured_pages,
)
from galley.book_folder import BookFolder, Stage, delete_stage_outputs
from galley.config import BookConfig
from galley.errors import FidelityBoundary
from galley.fidelity import check_stage
from galley.layout._column import (
    BookMeasures,
    ColumnSplit,
    Side,
    split_at_column,
    wide_rows_edges,
)
from galley.layout._figures import figure_regions, layout_page_with_figures
from galley.layout._page import layout_page
from galley.layout._reread import (
    is_small_print_page,
    note_bands,
    reading_score,
)
from galley.layout._rereading import (
    ReadLines,
    Rereading,
    layout_page_with_rereads,
    rereading_of_book,
)
from galley.model import (
    Line,
    LinesFile,
    PageKind,
    PageLayout,
    PageWords,
    Reread,
    TextSource,
    WordsFile,
    read_checked_input,
    read_words,
    write_lines,
)
from galley.parallel import DEFAULT_WORKERS, map_pages

__all__ = [
    "BookMeasures",
    "ReadLines",
    "Rereading",
    "Side",
    "figure_regions",
    "is_small_print_page",
    "layout_page",
    "layout_page_with_figures",
    "layout_page_with_rereads",
    "measure_book",
    "note_bands",
    "reading_score",
    "run",
]

_logger = logging.getLogger(__name__)


def _commonest_left_edge(rows: tuple[Line, ...]) -> float:
    """The commonest left side of `rows`, which are not empty."""
    return commonest(row.box.x0 for row in rows)


def _column_width_of_page(rows: tuple[Line, ...]) -> float:
    """The commonest right side of `rows` minus their commonest left side;
    `rows` is not empty."""
    return commonest(row.box.x1 for row in rows) - _commonest_left_edge(rows)


def _usual_left_edges(
    pages: tuple[PageWords, ...],
    rows_by_page: tuple[tuple[Line, ...], ...],
    measured: tuple[tuple[Line, ...], ...],
    column_width: float,
) -> frozendict[int, float]:
    """The usual left edge for even (0) and odd (1) page indices: the median
    of the left edges step 1 finds on the pages of that parity that place
    their column themselves, else the
    other parity's, else the median of the commonest left edges of the
    `measured` pages."""
    found = tuple(
        (page.index % 2, edges[0])
        for page, rows in zip(pages, rows_by_page, strict=True)
        if (edges := wide_rows_edges(rows, column_width)) is not None
    )
    either_parity = (
        median(edge for _, edge in found)
        if found
        else median(_commonest_left_edge(rows) for rows in measured)
    )

    def of_parity(parity: int) -> float:
        lefts = tuple(edge for edge_parity, edge in found if edge_parity == parity)
        return median(lefts) if lefts else either_parity

    return frozendict({0: of_parity(0), 1: of_parity(1)})


def measure_book(
    words: WordsFile, *, workers: int = DEFAULT_WORKERS
) -> BookMeasures | None:
    """The measures of the book of `words` (layout spec section 3), taken
    from the rows of its pages of at least 15 rows, or of 3 rows when it
    has none of 15. None when no page has 3 rows: its pages are then laid
    out as one region each. The cut-in insets are measured once every
    measured page's column is placed. The pages are worked on in `workers`
    threads; the result does not depend on their number."""

    def page_rows(page: PageWords) -> tuple[Line, ...]:
        return group_rows(page.words)

    rows_by_page = map_pages(page_rows, words.pages, workers)
    measured = measured_pages(rows_by_page)
    # The measured pages are their own measured pages: body_measures takes
    # the same rows from them as from every page.
    body = body_measures(measured)
    if body is None:
        return None
    column_width = median(_column_width_of_page(rows) for rows in measured)
    without_insets = BookMeasures(
        column_width=column_width,
        body_word_height=body.body_word_height,
        body_line_pitch=body.body_line_pitch,
        usual_left_edge=_usual_left_edges(
            words.pages, rows_by_page, measured, column_width
        ),
        cut_in_inset_left=None,
        cut_in_inset_right=None,
    )
    measured_words = tuple(
        words.pages[position] for position in measured_page_positions(rows_by_page)
    )

    def page_insets(page: PageWords) -> tuple[tuple[int, ...], tuple[int, ...]]:
        return _row_insets(split_at_column(page.words, page.index, without_insets))

    insets = map_pages(page_insets, measured_words, workers)
    return replace(
        without_insets,
        cut_in_inset_left=_cut_in_inset(
            tuple(inset for left, _ in insets for inset in left)
        ),
        cut_in_inset_right=_cut_in_inset(
            tuple(inset for _, right in insets for inset in right)
        ),
    )


# Measured on the six whole books and the six excerpts on 16 November 2026
# (layout spec section 3, "The book's measures"): Stubbs' cut-in insets lie
# 60.4 and 59.0 pt inside its column, with 394 and 359 rows within 2 pt of
# them and at most 40 rows 6 to 12 pt to either side (this code, on the
# books of that day, measures 60.3 and 59.3 pt, 397 and 362 rows); no other
# book has a peak more than 1.3 times its neighbours'. The floor of 10 rows lets the
# Stubbs excerpt, 17 and 13 rows, pass; the other excerpts have at most 11
# rows at their peak, against 9 beside it.
_CUT_IN_INSET_TENTHS: Final[int] = 10
_CUT_IN_INSET_LEAST_TENTHS: Final[int] = 300
_CUT_IN_INSET_MOST_TENTHS: Final[int] = 1000
_CUT_IN_PEAK_TENTHS: Final[int] = 20
_CUT_IN_NEIGHBOURS_NEAR_TENTHS: Final[int] = 60
_CUT_IN_NEIGHBOURS_FAR_TENTHS: Final[int] = 120
_CUT_IN_PEAK_ROWS: Final[int] = 10
_CUT_IN_PEAK_TIMES_NEIGHBOURS: Final[int] = 4


def _row_insets(split: ColumnSplit) -> tuple[tuple[int, ...], tuple[int, ...]]:
    """The left and right insets of the rows of `split`'s column words, in
    tenths of a point: how far each row starts right of the left edge and
    ends left of the right edge."""
    rows = group_rows(split.column)
    return (
        tuple(_tenths(row.box.x0 - split.left) for row in rows),
        tuple(_tenths(split.right - row.box.x1) for row in rows),
    )


def _tenths(points: float) -> int:
    return round(points * _CUT_IN_INSET_TENTHS)


def _cut_in_inset(insets: tuple[int, ...]) -> float | None:
    """The cut-in inset of one side of a book, in points, from the `insets`
    of the rows of its measured pages, in tenths of a point (layout spec
    section 3): of the insets from 30 to 100 pt, the one with the most rows
    within 2 pt of it, the smaller on a tie, when those rows are at least
    10 and 4 times the rows 6 to 12 pt smaller and 4 times those 6 to 12 pt
    larger. None otherwise."""
    ordered = sorted(insets)

    def rows_between(least: int, most: int) -> int:
        return bisect.bisect_right(ordered, most) - bisect.bisect_left(ordered, least)

    def rows_at(peak: int) -> int:
        return rows_between(peak - _CUT_IN_PEAK_TENTHS, peak + _CUT_IN_PEAK_TENTHS)

    candidates = sorted(
        {
            inset
            for inset in ordered
            if _CUT_IN_INSET_LEAST_TENTHS <= inset <= _CUT_IN_INSET_MOST_TENTHS
        }
    )
    if not candidates:
        return None
    # The candidates are in increasing order, and max keeps the first of a
    # tie.
    peak = max(candidates, key=rows_at)
    at_peak = rows_at(peak)
    smaller = rows_between(
        peak - _CUT_IN_NEIGHBOURS_FAR_TENTHS, peak - _CUT_IN_NEIGHBOURS_NEAR_TENTHS
    )
    larger = rows_between(
        peak + _CUT_IN_NEIGHBOURS_NEAR_TENTHS, peak + _CUT_IN_NEIGHBOURS_FAR_TENTHS
    )
    has_notes = (
        at_peak >= _CUT_IN_PEAK_ROWS
        and at_peak >= _CUT_IN_PEAK_TIMES_NEIGHBOURS * smaller
        and at_peak >= _CUT_IN_PEAK_TIMES_NEIGHBOURS * larger
    )
    return peak / _CUT_IN_INSET_TENTHS if has_notes else None


def run(
    folder: BookFolder, config: BookConfig, *, workers: int = DEFAULT_WORKERS
) -> None:
    """Reads pages.json and words.json from `folder`, measures the book,
    lays out every page in `workers` threads, re-reading its small print
    with Tesseract unless the config's `ocr` is `trust` or `redo`, and
    writes lines.json with the records of the regions read.

    Only text pages whose words are the text layer's are re-read (reocr
    spec, section 3), and never the words inside an in-page figure, which
    are the figure's region (`figure_regions`); a render is made in the one PDFium thread, and
    Tesseract runs in the worker threads. lines.json and every later
    stage's file (blocks.json, book.md, book.epub) are deleted first.
    pages.json must have been made from `config.pdf` and words.json from
    the same PDF, or InputFileError names the stage to run again. When the
    words of lines.json are not those of words.json after the kept
    records, FidelityError is raised and nothing is written.
    """
    delete_stage_outputs(folder, Stage.LAYOUT)
    pages, words = read_checked_input(
        folder.pages_json, config.pdf, folder.words_json, read_words
    )
    measures = measure_book(words, workers=workers)
    if measures is None:
        _logger.info(
            "layout: no page has enough rows to measure the book; "
            "every page is laid out as one region"
        )
    else:
        _logger.info("layout: the book's measures, in points: %s", measures)
    rereading = rereading_of_book(config, words, measures, workers)
    if rereading is not None:
        _logger.info(
            "layout: re-reading small print; outer margin notes on the sides %s",
            ", ".join(sorted(rereading.margin_note_sides)) or "none",
        )
    readable = frozenset(
        page.index
        for page in pages.pages
        if page.kind is PageKind.TEXT and page.text_source is TextSource.TEXT_LAYER
    )

    def lay_out(page: PageWords) -> tuple[PageLayout, tuple[Reread, ...]]:
        return layout_page_with_figures(
            page, measures, rereading if page.index in readable else None
        )

    laid_out = map_pages(lay_out, words.pages, workers)
    lines = LinesFile(
        source_pdf_sha256=words.source_pdf_sha256,
        pages=tuple(page for page, _ in laid_out),
        rereads=tuple(record for _, records in laid_out for record in records),
    )
    check_stage(FidelityBoundary.LAYOUT, words, lines)
    write_lines(folder.lines_json, lines)
    _logger.info(
        "layout: %d pages, %d regions, %d lines written to %s; "
        "%d regions re-read, %d of them kept",
        len(lines.pages),
        sum(len(page.regions) for page in lines.pages),
        sum(len(region.lines) for page in lines.pages for region in page.regions),
        folder.lines_json,
        len(lines.rereads),
        sum(record.kept for record in lines.rereads),
    )
