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
    WordChange,
    read_checked_input,
    read_lines,
    write_blocks,
)
from galley.parallel import DEFAULT_WORKERS, map_pages
from galley.structure._hyphens import (
    HyphenJoin,
    PageLine,
    join_hyphen,
    join_lines,
)
from galley.structure._measures import box_of
from galley.structure._regions import region_kinds
from galley.structure._removals import foot_removals, head_removals
from galley.structure._survey import BookSurvey, survey_book
from galley.wordlist import word_list

__all__ = [
    "BookSurvey",
    "HyphenJoin",
    "join_hyphen",
    "make_blocks",
    "run",
    "survey_book",
]

_logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class _PageResult:
    blocks: tuple[Block, ...]
    removals: tuple[Removal, ...]
    word_changes: tuple[WordChange, ...]
    page_numbers: tuple[PageNumber, ...]


def _page_result(
    page: PageLayout, survey: BookSurvey, word_list: frozenset[str]
) -> _PageResult:
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
    joined = tuple(
        join_lines(
            tuple(
                PageLine(page.index, tuple(word.text for word in line.words))
                for line in lines
            ),
            survey.book_words,
            word_list,
        )
        for lines in kept_regions
    )
    blocks = tuple(
        Block(
            id=f"b-p{page.index:04d}-{number:03d}",
            kind=BlockKind.PARAGRAPH,
            level=None,
            spans=(Span(" ".join(words.words), Emphasis.NONE, None),),
            figure=None,
            origin=(Origin(page.index, box_of(tuple(line.box for line in lines))),),
        )
        for number, (lines, words) in enumerate(
            zip(kept_regions, joined, strict=True), start=1
        )
    )
    return _PageResult(
        blocks,
        head.removals + foot.removals,
        tuple(change for words in joined for change in words.changes),
        head.page_numbers + foot.page_numbers,
    )


def make_blocks(
    lines: LinesFile, word_list: frozenset[str], *, workers: int = DEFAULT_WORKERS
) -> BlocksFile:
    """The blocks of the book, what was removed, the words changed and the
    page numbers, in a pool of `workers` threads; the result does not
    depend on `workers`. `word_list` is the word list of the book's
    language as `wordlist.word_list` gives it, in any case."""
    survey = survey_book(lines, workers=workers)
    lower_word_list = frozenset(word.lower() for word in word_list)
    pages = map_pages(
        lambda page: _page_result(page, survey, lower_word_list), lines.pages, workers
    )
    return BlocksFile(
        source_pdf_sha256=lines.source_pdf_sha256,
        blocks=tuple(block for page in pages for block in page.blocks),
        notes=(),
        removals=tuple(removal for page in pages for removal in page.removals),
        word_changes=tuple(change for page in pages for change in page.word_changes),
        page_numbers=tuple(number for page in pages for number in page.page_numbers),
    )


def run(
    folder: BookFolder, config: BookConfig, *, workers: int = DEFAULT_WORKERS
) -> None:
    """Reads pages.json and lines.json from `folder` and writes blocks.json.

    blocks.json and every later stage's file (book.md, book.epub) are
    deleted first. pages.json must have been made from `config.pdf` and
    lines.json from the same PDF, or InputFileError names the stage to run
    again. The word list of `config.language` is taken from Tesseract's
    data, which needs Tesseract the first time a language is used. When the words of blocks.json are not those of lines.json less
    the removals, FidelityError is raised and nothing is written. The pages
    are worked on in a pool of `workers` threads.
    """
    delete_stage_outputs(folder, Stage.STRUCTURE)
    _, lines = read_checked_input(
        folder.pages_json, config.pdf, folder.lines_json, read_lines
    )
    blocks = make_blocks(lines, word_list(config.language), workers=workers)
    check_stage(FidelityBoundary.STRUCTURE, lines, blocks)
    write_blocks(folder.blocks_json, blocks)
    _logger.info(
        "structure: %d blocks written to %s", len(blocks.blocks), folder.blocks_json
    )
