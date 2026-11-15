"""structure: the book as ordered blocks and notes, and what was removed.

structure surveys the whole book (`survey_book`), then removes from each
page its running head, with the page number and the stray marks above it,
and the page number, signature line or printer's signature mark at its
foot, each kept as a removal with its reason (`docs/specs/structure.md`). Each
region's remaining lines become one paragraph, as in the walking skeleton.
"""

import logging
from dataclasses import dataclass

from galley.book_folder import BookFolder, Stage, delete_stage_outputs
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
    PageNumber,
    Removal,
    Span,
    read_checked_input,
    read_lines,
    write_blocks,
)
from galley.parallel import DEFAULT_WORKERS, map_pages
from galley.structure._measures import box_of, words_text
from galley.structure._regions import region_kinds
from galley.structure._removals import foot_removals, head_removals
from galley.structure._survey import BookSurvey, survey_book

__all__ = ["BookSurvey", "make_blocks", "run", "survey_book"]

_logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class _PageResult:
    blocks: tuple[Block, ...]
    removals: tuple[Removal, ...]
    page_numbers: tuple[PageNumber, ...]


def _page_result(page: PageLayout, survey: BookSurvey) -> _PageResult:
    kinds = region_kinds(page, survey.body_word_height, survey.running_heads)
    head = head_removals(page, kinds, survey)
    foot = foot_removals(page, kinds, survey)
    removed_lines = head.lines | foot.lines
    kept_regions = tuple(
        lines
        for region_number, region in enumerate(page.regions)
        if (
            lines := tuple(
                line
                for line_number, line in enumerate(region.lines)
                if (region_number, line_number) not in removed_lines
            )
        )
    )
    blocks = tuple(
        Block(
            id=f"b-p{page.index:04d}-{number:03d}",
            kind=BlockKind.PARAGRAPH,
            level=None,
            spans=(
                Span(
                    words_text(word for line in lines for word in line.words),
                    Emphasis.NONE,
                    None,
                ),
            ),
            figure=None,
            origin=(Origin(page.index, box_of(tuple(line.box for line in lines))),),
        )
        for number, lines in enumerate(kept_regions, start=1)
    )
    return _PageResult(
        blocks,
        head.removals + foot.removals,
        head.page_numbers + foot.page_numbers,
    )


def make_blocks(lines: LinesFile, *, workers: int = DEFAULT_WORKERS) -> BlocksFile:
    """The blocks of the book, what was removed and the page numbers, in a
    pool of `workers` threads; the result does not depend on `workers`."""
    survey = survey_book(lines, workers=workers)
    pages = map_pages(lambda page: _page_result(page, survey), lines.pages, workers)
    return BlocksFile(
        source_pdf_sha256=lines.source_pdf_sha256,
        blocks=tuple(block for page in pages for block in page.blocks),
        notes=(),
        removals=tuple(removal for page in pages for removal in page.removals),
        word_changes=(),
        page_numbers=tuple(number for page in pages for number in page.page_numbers),
    )


def run(
    folder: BookFolder, config: BookConfig, *, workers: int = DEFAULT_WORKERS
) -> None:
    """Reads pages.json and lines.json from `folder` and writes blocks.json.

    blocks.json and every later stage's file (book.md, book.epub) are
    deleted first. pages.json must have been made from `config.pdf` and
    lines.json from the same PDF, or InputFileError names the stage to run
    again. When the words of blocks.json are not those of lines.json less
    the removals, FidelityError is raised and nothing is written. The pages
    are worked on in a pool of `workers` threads.
    """
    delete_stage_outputs(folder, Stage.STRUCTURE)
    _, lines = read_checked_input(
        folder.pages_json, config.pdf, folder.lines_json, read_lines
    )
    blocks = make_blocks(lines, workers=workers)
    check_stage(FidelityBoundary.STRUCTURE, lines, blocks)
    write_blocks(folder.blocks_json, blocks)
    _logger.info(
        "structure: %d blocks written to %s", len(blocks.blocks), folder.blocks_json
    )
