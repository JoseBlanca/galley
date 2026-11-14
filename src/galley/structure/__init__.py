"""structure: the book as ordered blocks and notes, and what was removed.

The walking skeleton's rule (spec section 7): each region of a page becomes
one paragraph, its words joined by single spaces, line after line. Nothing
is removed, no note is found and no hyphen is joined, so running heads,
page numbers and footnotes stay in the text.
"""

import logging

from galley.book_folder import BookFolder
from galley.config import BookConfig
from galley.errors import FidelityBoundary
from galley.fidelity import check_stage
from galley.model import (
    Block,
    BlockKind,
    BlocksFile,
    Emphasis,
    LinesFile,
    Origin,
    PageLayout,
    Region,
    Span,
    check_source_pdf,
    pdf_sha256,
    read_lines,
    read_pages,
    write_blocks,
)
from galley.parallel import DEFAULT_WORKERS

_log = logging.getLogger(__name__)


def _paragraph(page_index: int, number: int, region: Region) -> Block:
    """The paragraph of `region`, the `number`-th (from 1) of its page."""
    text = " ".join(word.text for line in region.lines for word in line.words)
    return Block(
        id=f"b-p{page_index:04d}-{number:03d}",
        kind=BlockKind.PARAGRAPH,
        level=None,
        spans=(Span(text, Emphasis.NONE, None),),
        figure=None,
        origin=(Origin(page_index, region.box),),
    )


def page_blocks(page: PageLayout) -> tuple[Block, ...]:
    """One paragraph block for each region of `page`, in the order of its
    regions: the region's words, line after line, joined by single spaces,
    in one span without emphasis or note reference. The n-th region gets
    the id `b-p<page index, 4 digits>-<n, 3 digits>`, n from 1. A page
    without regions gives no block."""
    return tuple(
        _paragraph(page.index, number, region)
        for number, region in enumerate(page.regions, start=1)
    )


def make_blocks(lines: LinesFile) -> BlocksFile:
    """The blocks of every page of `lines`, in page order, with no note,
    removal, word change or page number, and the PDF hash of `lines`."""
    return BlocksFile(
        source_pdf_sha256=lines.source_pdf_sha256,
        blocks=tuple(block for page in lines.pages for block in page_blocks(page)),
        notes=(),
        removals=(),
        word_changes=(),
        page_numbers=(),
    )


def run(
    folder: BookFolder, config: BookConfig, *, workers: int = DEFAULT_WORKERS
) -> None:
    """Reads pages.json and lines.json from `folder` and writes blocks.json.

    blocks.json is deleted first. pages.json must have been made from
    `config.pdf` and lines.json from the same PDF, or InputFileError names
    the stage to run again. When the words of blocks.json are not those of
    lines.json, FidelityError is raised and nothing is written. structure
    runs in one thread; `workers` is taken as every stage takes it.
    """
    del workers  # one pass over the book, in this thread (spec section 10)
    folder.blocks_json.unlink(missing_ok=True)
    pages = read_pages(folder.pages_json)
    check_source_pdf(folder.pages_json, pages.source_pdf_sha256, pdf_sha256(config.pdf))
    lines = read_lines(folder.lines_json)
    check_source_pdf(
        folder.lines_json, lines.source_pdf_sha256, pages.source_pdf_sha256
    )
    blocks = make_blocks(lines)
    check_stage(FidelityBoundary.STRUCTURE, lines, blocks)
    write_blocks(folder.blocks_json, blocks)
    _log.info(
        "structure: %d blocks written to %s", len(blocks.blocks), folder.blocks_json
    )
