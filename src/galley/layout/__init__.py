"""layout: each page's words grouped into regions and lines, in reading order.

The walking skeleton's rule (spec section 7): all the words of a page go in
one region, and a word joins the line of the word that started it, its
anchor, when the word's vertical centre lies within the anchor's top and
bottom. A row of the page becomes one line across every column it crosses,
so footnote columns and margin headings are read row by row; no word is
lost, and the real layout spec fixes the order.
"""

import logging

from galley.book_folder import BookFolder
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
    read_checked_input,
    read_words,
    write_lines,
)
from galley.parallel import DEFAULT_WORKERS, map_pages

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


def run(
    folder: BookFolder, config: BookConfig, *, workers: int = DEFAULT_WORKERS
) -> None:
    """Reads pages.json and words.json from `folder`, lays out every page in
    `workers` threads, and writes lines.json.

    lines.json is deleted first. pages.json must have been made from
    `config.pdf` and words.json from the same PDF, or InputFileError names
    the stage to run again. When the words of lines.json are not those of
    words.json, FidelityError is raised and nothing is written.
    """
    folder.lines_json.unlink(missing_ok=True)
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
