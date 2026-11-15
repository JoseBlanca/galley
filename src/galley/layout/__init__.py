"""layout: each page's words grouped into regions and lines, in reading order.

The rules are those of docs/specs/layout.md. `measure_book` takes the
book's measures over all its pages: the width of the body column, the
height of a body word, the distance between rows, and the usual left edge
of the column. `group_lines` groups words into lines by the walking
skeleton's rule: a word joins the line of the word that started it, its
anchor, when the word's vertical centre lies within the anchor's top and
bottom. `layout_page` still puts all the words of a page in one region.
"""

import logging
from bisect import bisect_left, bisect_right
from collections.abc import Iterable
from dataclasses import dataclass
from itertools import pairwise
from statistics import median
from typing import Final

from galley.book_folder import BookFolder, Stage, delete_stage_outputs
from galley.config import BookConfig
from galley.errors import FidelityBoundary
from galley.fidelity import check_stage
from galley.model import (
    Box,
    Line,
    LinesFile,
    PageLayout,
    PageWords,
    Region,
    Word,
    WordsFile,
    read_checked_input,
    read_words,
    write_lines,
)
from galley.parallel import DEFAULT_WORKERS, map_pages

__all__ = ["BookMeasures", "group_lines", "layout_page", "measure_book", "run"]

_logger = logging.getLogger(__name__)


def _enclosing_box(boxes: tuple[Box, ...]) -> Box:
    """The smallest box that holds every box of `boxes`, which is not empty."""
    return Box(
        min(box.x0 for box in boxes),
        min(box.top for box in boxes),
        max(box.x1 for box in boxes),
        max(box.bottom for box in boxes),
    )


def _line(words: tuple[Word, ...]) -> Line:
    """The line of `words`, sorted left to right by x0; equal x0 keep their order."""
    left_to_right = tuple(sorted(words, key=lambda word: word.box.x0))
    return Line(_enclosing_box(tuple(word.box for word in words)), left_to_right)


def group_lines(words: tuple[Word, ...]) -> tuple[Line, ...]:
    """The lines of `words`, top to bottom, each one's words left to right.

    The words are taken by (top, x0), equal keys in their given order. The
    first word starts a line and is its anchor; a later word joins the
    current line when its vertical centre, (top + bottom) / 2 in points,
    lies within the anchor's top and bottom, edges included, and otherwise
    starts the next line as its anchor. A line's box is the smallest box
    that holds its words. No words give no lines.
    """
    rows: list[list[Word]] = []
    anchor: Word | None = None
    for word in sorted(words, key=lambda word: (word.box.top, word.box.x0)):
        centre = (word.box.top + word.box.bottom) / 2
        if anchor is not None and anchor.box.top <= centre <= anchor.box.bottom:
            rows[-1].append(word)
        else:
            rows.append([word])
            anchor = word
    return tuple(_line(tuple(row)) for row in rows)


def layout_page(page: PageWords) -> PageLayout:
    """The layout of one page: one region holding the lines of all its
    words, whose box is the smallest that holds them, or no region when the
    page has no words. The figures are those of `page`."""
    lines = group_lines(page.words)
    regions = (
        (Region(_enclosing_box(tuple(line.box for line in lines)), lines),)
        if lines
        else ()
    )
    return PageLayout(page.index, regions, page.figures)


# The book's measures (layout spec section 3, "The book's measures").

# Guessed: enough rows on a page for a commonest edge.
_MEASURED_PAGE_ROWS: Final[int] = 15
# A book with no page of 15 rows is measured on its pages of 3 rows.
_MEASURED_PAGE_ROWS_FALLBACK: Final[int] = 3
# Measured: body lines start within 2.2 pt of the edge on 99% of Haskins'
# lines.
_COMMONEST_EDGE_PT: Final[float] = 2.0
# Guessed: a full line is the column width.
_WIDE_ROW_SHARE: Final[float] = 0.8


@dataclass(frozen=True, slots=True, kw_only=True)
class BookMeasures:
    """The numbers measured over a whole book that lay out each of its
    pages, in points (layout spec section 3).

    `column_width` is the width of the body column; `body_word_height` the
    median height of a body line's words; `body_line_pitch` the median
    distance from the top of one row to the top of the next.
    `usual_left_edge` is the left edge of the body column on a page that
    has no row wide enough to place it, by the parity of the page index:
    0 for even pages, 1 for odd.
    """

    column_width: float
    body_word_height: float
    body_line_pitch: float
    usual_left_edge: frozendict[int, float]


def _commonest(edges: Iterable[float]) -> float | None:
    """The commonest value of `edges`, in points: each edge rounded to the
    point, the value with the most edges within 2 pt of it, the smallest on
    a tie. None for no edges."""
    rounded = sorted(float(round(edge)) for edge in edges)
    if not rounded:
        return None
    return min(
        dict.fromkeys(rounded),
        key=lambda value: (
            -(
                bisect_right(rounded, value + _COMMONEST_EDGE_PT)
                - bisect_left(rounded, value - _COMMONEST_EDGE_PT)
            ),
            value,
        ),
    )


def _row_word_height(row: Line) -> float:
    """The median height of the words of `row`, in points."""
    return median(word.box.bottom - word.box.top for word in row.words)


def _wide_rows_left_edge(rows: tuple[Line, ...], column_width: float) -> float | None:
    """The left edge of the body column on a page of `rows` (layout spec
    section 3, step 1): the commonest left side of the rows at least 0.8 of
    `column_width` wide. None when no row is that wide."""
    return _commonest(
        row.box.x0
        for row in rows
        if row.box.x1 - row.box.x0 >= _WIDE_ROW_SHARE * column_width
    )


def _commonest_left_edge(rows: tuple[Line, ...]) -> float:
    """The commonest left side of `rows`, which are not empty."""
    edge = _commonest(row.box.x0 for row in rows)
    assert edge is not None, "rows is not empty"
    return edge


def _column_width_of_page(rows: tuple[Line, ...]) -> float:
    """The commonest right side of `rows` minus their commonest left side;
    `rows` is not empty."""
    right = _commonest(row.box.x1 for row in rows)
    assert right is not None, "rows is not empty"
    return right - _commonest_left_edge(rows)


def _usual_left_edges(
    pages: tuple[PageWords, ...],
    rows_by_page: tuple[tuple[Line, ...], ...],
    measured: tuple[tuple[Line, ...], ...],
    column_width: float,
) -> frozendict[int, float]:
    """The usual left edge for even (0) and odd (1) page indices: the median
    of the left edges step 1 finds on the pages of that parity, else the
    other parity's, else the median of the commonest left edges of the
    `measured` pages."""
    found = tuple(
        (page.index % 2, edge)
        for page, rows in zip(pages, rows_by_page, strict=True)
        if (edge := _wide_rows_left_edge(rows, column_width)) is not None
    )
    either_parity = (
        median(edge for _, edge in found)
        if found
        else median(_commonest_left_edge(rows) for rows in measured)
    )

    def of_parity(parity: int) -> float:
        edges = tuple(edge for edge_parity, edge in found if edge_parity == parity)
        return median(edges) if edges else either_parity

    return frozendict({0: of_parity(0), 1: of_parity(1)})


def measure_book(
    words: WordsFile, *, workers: int = DEFAULT_WORKERS
) -> BookMeasures | None:
    """The measures of the book of `words` (layout spec section 3), taken
    from the rows of its pages of at least 15 rows, or of 3 rows when it
    has none of 15. None when no page has 3 rows: its pages are then laid
    out as one region each. The rows of each page are grouped in `workers`
    threads; the result does not depend on their number."""

    def page_rows(page: PageWords) -> tuple[Line, ...]:
        return group_lines(page.words)

    rows_by_page = map_pages(page_rows, words.pages, workers)
    measured = tuple(
        rows for rows in rows_by_page if len(rows) >= _MEASURED_PAGE_ROWS
    ) or tuple(
        rows for rows in rows_by_page if len(rows) >= _MEASURED_PAGE_ROWS_FALLBACK
    )
    if not measured:
        return None
    column_width = median(_column_width_of_page(rows) for rows in measured)
    return BookMeasures(
        column_width=column_width,
        body_word_height=median(
            _row_word_height(row) for rows in measured for row in rows
        ),
        body_line_pitch=median(
            below.box.top - above.box.top
            for rows in measured
            for above, below in pairwise(rows)
        ),
        usual_left_edge=_usual_left_edges(
            words.pages, rows_by_page, measured, column_width
        ),
    )


def run(
    folder: BookFolder, config: BookConfig, *, workers: int = DEFAULT_WORKERS
) -> None:
    """Reads pages.json and words.json from `folder`, lays out every page in
    `workers` threads, and writes lines.json.

    lines.json and every later stage's file (blocks.json, book.md,
    book.epub) are deleted first. pages.json must have been made from
    `config.pdf` and words.json from the same PDF, or InputFileError names
    the stage to run again. When the words of lines.json are not those of
    words.json, FidelityError is raised and nothing is written.
    """
    delete_stage_outputs(folder, Stage.LAYOUT)
    _, words = read_checked_input(
        folder.pages_json, config.pdf, folder.words_json, read_words
    )
    lines = LinesFile(
        source_pdf_sha256=words.source_pdf_sha256,
        pages=map_pages(layout_page, words.pages, workers),
    )
    check_stage(FidelityBoundary.LAYOUT, words, lines)
    write_lines(folder.lines_json, lines)
    _logger.info(
        "layout: %d pages, %d lines written to %s",
        len(lines.pages),
        sum(len(region.lines) for page in lines.pages for region in page.regions),
        folder.lines_json,
    )
