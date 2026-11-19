"""structure: the book as ordered blocks and notes, and what was removed.

structure turns the regions and lines of lines.json into blocks.json
(`docs/specs/structure.md`). It surveys the whole book (`survey_book`);
removes from each page its running head, with the page number and the
stray marks above it, and the page number, signature line or printer's
signature mark at its foot, each kept as a removal with its reason; finds
the paragraphs of the body, which run over page breaks; joins the hyphens
at line ends (`join_hyphen`), each join kept as a word change; keeps the
text of the footnote band as notes, after the paragraph in which their
page's body ends; and puts each margin note before the paragraph, or
inside the note, beside whose line it was printed. A plate page's lines
are its running head, its caption, kept as the text of a figure block
placed after the paragraph that runs over the plate, and its stray words,
removed.
"""

import logging

from galley import wordlist
from galley.book_folder import BookFolder, Stage, delete_stage_outputs
from galley.config import BookConfig, Language
from galley.errors import FidelityBoundary
from galley.fidelity import check_stage
from galley.model import (
    BlocksFile,
    FigureKind,
    LinesFile,
    read_checked_input,
    read_lines,
    write_blocks,
)
from galley.parallel import DEFAULT_WORKERS, map_pages
from galley.structure._assemble import assemble
from galley.structure._case_split import split_at_case
from galley.structure._figures import is_caption_label
from galley.structure._hyphens import (
    HyphenJoin,
    join_hyphen,
    join_lost_hyphen,
    sign_removals,
)
from galley.structure._markers import (
    NoteMarker,
    Reference,
    ReferenceForm,
    note_marker,
    reference_candidate,
)
from galley.structure._paragraphs import page_parts
from galley.structure._plates import plate_parts, plate_survey
from galley.structure._spaced import attach_spaced_sign
from galley.structure._survey import BookSurvey, survey_book

__all__ = [
    "BookSurvey",
    "HyphenJoin",
    "NoteMarker",
    "Reference",
    "ReferenceForm",
    "attach_spaced_sign",
    "is_caption_label",
    "join_hyphen",
    "join_lost_hyphen",
    "make_blocks",
    "note_marker",
    "reference_candidate",
    "run",
    "split_at_case",
    "survey_book",
]

_logger = logging.getLogger(__name__)


def make_blocks(
    lines: LinesFile,
    lower_case_words: frozenset[str],
    *,
    language: Language = Language.EN,
    contents_pages: frozenset[int] = frozenset(),
    workers: int = DEFAULT_WORKERS,
) -> BlocksFile:
    """The blocks of the book, what was removed, the words changed and the
    page numbers, in a pool of `workers` threads; the result does not
    depend on `workers`. `lower_case_words` is the word list of the book's
    language in lower case, as `wordlist.lower_case_word_list` gives it;
    `language` the config's, by which a spaced sign is attached to its word
    or, in French, takes a no-break space (spec section 23);
    `contents_pages` the page indices of the printed table of contents
    (the config's), whose lines are its title and its entries (spec
    section 30) and after the last of which the references to endnotes
    are taken (spec section 12)."""
    survey = survey_book(lines, workers=workers)
    plates = plate_survey(lines, survey)
    pages = map_pages(
        lambda page: (
            plate_parts(page, survey, plates, lower_case_words)
            # Figures spec section 5: the plate rules on a plate's page only;
            # a page with in-page figures is laid out as a text page, its
            # figures not yet placed as blocks.
            if any(figure.kind is FigureKind.PLATE for figure in page.figures)
            else page_parts(page, survey, contents_pages)
        ),
        lines.pages,
        workers,
    )
    assembled = assemble(
        pages,
        survey.book_words,
        lower_case_words,
        survey.common_inner_words,
        survey.body_word_height,
        survey.body_line_pitch,
        contents_pages,
        language,
    )
    return BlocksFile(
        source_pdf_sha256=lines.source_pdf_sha256,
        blocks=assembled.blocks,
        notes=assembled.notes,
        # The leader dots removed across pages go after their page's
        # removals; the sort is stable.
        removals=tuple(
            sorted(
                (
                    *(removal for page in pages for removal in page.removals),
                    *assembled.removals,
                    *sign_removals(assembled.word_changes, lines),
                ),
                key=lambda removal: removal.page_index,
            )
        ),
        word_changes=assembled.word_changes,
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
    data, which needs Tesseract the first time a language is used. When
    the words of blocks.json are not those of lines.json less the
    removals, FidelityError is raised and nothing is written. The pages
    are worked on in a pool of `workers` threads.
    """
    delete_stage_outputs(folder, Stage.STRUCTURE)
    _, lines = read_checked_input(
        folder.pages_json, config.pdf, folder.lines_json, read_lines
    )
    # The cache folder is read here, as the command's check reads it.
    words = wordlist.lower_case_word_list(config.language, wordlist.DEFAULT_CACHE_DIR)
    blocks = make_blocks(
        lines,
        words,
        language=config.language,
        contents_pages=frozenset(config.contents_pages),
        workers=workers,
    )
    check_stage(FidelityBoundary.STRUCTURE, lines, blocks)
    write_blocks(folder.blocks_json, blocks)
    _logger.info(
        "structure: %d blocks written to %s", len(blocks.blocks), folder.blocks_json
    )
