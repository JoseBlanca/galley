"""Tests of structure's epigraph rule (docs/specs/structure.md, section 22;
the epigraphs bullet of section 26's unit tests).

Every page's body stream is written by hand: a word is 5 pt wide per
character and 10 pt high (a source in smaller type 8 pt), with one
character's width between words, and lines lie 15 pt apart. The body
column runs from 50 to 400 pt; a quotation is indented 30 pt, as Haynes'
are, or 44 pt, as Turney's.
"""

from collections.abc import Callable
from dataclasses import replace

import pytest

from galley.book_folder import BookFolder
from galley.errors import FidelityBoundary, FidelityError
from galley.fidelity import check_stage
from galley.model import (
    BlockKind,
    BlocksFile,
    Box,
    ChangeReason,
    Line,
    LinesFile,
    PageLayout,
    Region,
    RemovalReason,
    Word,
    WordChange,
    block_text,
    read_blocks,
)
from galley.structure import make_blocks
from galley.structure._epigraphs import (
    QuotationForm,
    epigraph_column,
    epigraphs_after_heading,
    page_epigraph,
    page_epigraphs,
)
from galley.structure._lines import PlacedLine
from galley.structure._markers import MarkerForm
from galley.structure._measures import Edges
from galley.structure._paragraphs import PageParts, body_entries
from galley.structure._runs import BodyRun

_PAGE = 22
_CHAR_PT = 5.0
_HEIGHT_PT = 10.0
_SOURCE_HEIGHT_PT = 8.0
_PITCH_PT = 15.0
_COLUMN = Edges(50.0, 400.0)
_HAYNES_LEFT = 80.0
_TURNEY_LEFT = 94.0
# 70 characters, 350 pt: a line of the body, from edge to edge.
_BODY = "the text of the chapter runs on here from the left edge to the right ."


def _line(text: str, x0: float, row: float, height: float = _HEIGHT_PT) -> PlacedLine:
    """A line of `text` starting at `x0`, on the row `row` of the page."""
    top = 100.0 + row * _PITCH_PT
    words = []
    left = x0
    for part in text.split(" "):
        right = left + _CHAR_PT * len(part)
        words.append(Word(part, Box(left, top, right, top + height), None))
        left = right + _CHAR_PT
    box = Box(words[0].box.x0, top, words[-1].box.x1, top + height)
    return PlacedLine(_PAGE, Line(box, tuple(words)), _COLUMN, _COLUMN)


def _heading(row: int) -> PlacedLine:
    return _line("THE CHAPTER TITLE", _COLUMN.left, row, 20.0)


def _flush_right(text: str, right: float, row: int) -> PlacedLine:
    """A line of `text` whose right side lies at `right`."""
    width = _CHAR_PT * len(text)
    return _line(text, right - width, row)


# A prose quotation of Haynes' kind: its lines run on (the second starts in
# lower case) and end near the column's right edge.
_PROSE = (
    "it was the best of times and the worst of times , the age",
    "of wisdom and the age of foolishness and the epoch of faith",
)


def _haynes_page(*source: str) -> tuple[PlacedLine, ...]:
    return (
        _heading(0),
        _line(_PROSE[0], _HAYNES_LEFT, 2),
        _line(_PROSE[1], _HAYNES_LEFT, 3),
        _line(" ".join(source), _HAYNES_LEFT, 4, _SOURCE_HEIGHT_PT),
        _line(_BODY, _COLUMN.left, 6),
        _line(_BODY, _COLUMN.left, 7),
    )


def test_dashed_source_in_smaller_type_ends_an_epigraph() -> None:
    lines = _haynes_page("—Dickens,", "A", "Tale")
    (epigraph,) = epigraphs_after_heading(lines, 1, len(lines), _COLUMN)
    assert (epigraph.start, epigraph.quotation, epigraph.source_lines) == (
        1,
        (1, 2),
        (3,),
    )
    assert epigraph.end == 4
    assert epigraph.stray_marks == ()
    assert epigraph.form is QuotationForm.PROSE
    assert epigraph.source == "Dickens, A Tale"
    assert epigraph.source_dash == WordChange(
        page_index=_PAGE,
        before=("—Dickens,",),
        after=("Dickens,",),
        reason=ChangeReason.SOURCE_DASH,
    )


def test_dash_word_of_its_own_is_removed_with_the_word_after() -> None:
    lines = _haynes_page("—-", "Dickens,", "1859")
    (epigraph,) = epigraphs_after_heading(lines, 1, len(lines), _COLUMN)
    assert epigraph.source == "Dickens, 1859"
    assert epigraph.source_dash == WordChange(
        page_index=_PAGE,
        before=("—-", "Dickens,"),
        after=("Dickens,",),
        reason=ChangeReason.SOURCE_DASH,
    )


def test_dash_inside_the_source_stays() -> None:
    lines = _haynes_page("—Dickens,", "1859—1860")
    (epigraph,) = epigraphs_after_heading(lines, 1, len(lines), _COLUMN)
    assert epigraph.source == "Dickens, 1859—1860"


def test_dashed_line_in_the_body_s_type_is_no_source() -> None:
    lines = (
        _heading(0),
        _line(_PROSE[0], _HAYNES_LEFT, 2),
        _line("—Dickens, A Tale", _HAYNES_LEFT, 3),
        _line(_BODY, _COLUMN.left, 5),
    )
    assert epigraphs_after_heading(lines, 1, len(lines), _COLUMN) == ()


def test_source_set_flush_right_ends_an_epigraph_without_a_dash() -> None:
    # Turney's kind: the source starts far right of the quotation and ends
    # within 5 pt of its right side (4.5 pt short on Turney's page 229).
    quotation_right = _TURNEY_LEFT + _CHAR_PT * max(map(len, _PROSE))
    lines = (
        _heading(0),
        _line(_PROSE[0], _TURNEY_LEFT, 2),
        _line(_PROSE[1], _TURNEY_LEFT, 3),
        _flush_right("Charles Dickens", quotation_right - 4.5, 4),
        _line(_BODY, _COLUMN.left, 6),
    )
    (epigraph,) = epigraphs_after_heading(lines, 1, len(lines), _COLUMN)
    assert (epigraph.quotation, epigraph.source_lines) == ((1, 2), (3,))
    assert epigraph.source == "Charles Dickens"
    assert epigraph.source_dash is None


def test_line_ending_more_than_5_pt_short_is_no_flush_right_source() -> None:
    quotation_right = _TURNEY_LEFT + _CHAR_PT * max(map(len, _PROSE))
    lines = (
        _heading(0),
        _line(_PROSE[0], _TURNEY_LEFT, 2),
        _line(_PROSE[1], _TURNEY_LEFT, 3),
        _flush_right("Charles Dickens", quotation_right - 6.0, 4),
        _line(_BODY, _COLUMN.left, 6),
    )
    assert epigraphs_after_heading(lines, 1, len(lines), _COLUMN) == ()


# Turney's page 56: a quotation in justified lines, its last short, and a
# source over four lines set flush right, the first two starting 12.5 and
# 49 pt right of the quotation.
_JUSTIFIED = " ".join(["word"] * 12)
_JUSTIFIED_RIGHT = _TURNEY_LEFT + _CHAR_PT * len(_JUSTIFIED)


def _turney_56(
    third_source_right: float, last_source_right: float
) -> tuple[PlacedLine, ...]:
    return (
        _heading(0),
        _line(_JUSTIFIED, _TURNEY_LEFT, 2),
        _line(_JUSTIFIED, _TURNEY_LEFT, 3),
        _line("the end of it", _TURNEY_LEFT, 4),
        _line(
            "Sir Henry Acland , testimony to the Royal Commission on a",
            _TURNEY_LEFT + 12.5,
            5,
        ),
        _line(
            "Practice of the Subjecting of Live Animals to it ,", _TURNEY_LEFT + 49.0, 6
        ),
        _flush_right("Purposes , 1876", third_source_right, 7),
        _flush_right("Quoted in French", last_source_right, 8),
        _line(_BODY, _COLUMN.left, 10),
    )


def test_source_over_several_lines_set_flush_right_is_one_source() -> None:
    lines = _turney_56(_JUSTIFIED_RIGHT, _JUSTIFIED_RIGHT - 1.0)
    (epigraph,) = epigraphs_after_heading(lines, 1, len(lines), _COLUMN)
    assert epigraph.quotation == (1, 2, 3)
    assert epigraph.source_lines == (4, 5, 6, 7)
    assert epigraph.source == (
        "Sir Henry Acland , testimony to the Royal Commission on a Practice of the Subjecting of Live Animals to it ,"
        " Purposes , 1876 Quoted in French"
    )


def test_line_ending_short_of_the_source_line_does_not_continue_it() -> None:
    # Turney's back cover: a line at the right that ends under the
    # quotation's right side but 20 pt short of the source line above it.
    lines = _turney_56(_JUSTIFIED_RIGHT + 20.0, _JUSTIFIED_RIGHT)
    (epigraph,) = epigraphs_after_heading(lines, 1, len(lines), _COLUMN)
    assert epigraph.source_lines == (4, 5, 6)


def test_dashed_source_continues_on_a_smaller_line_after_it() -> None:
    lines = (
        _heading(0),
        _line(_PROSE[0], _HAYNES_LEFT, 2),
        _line("\u2014Dickens, A Tale of", _HAYNES_LEFT, 3, _SOURCE_HEIGHT_PT),
        _line("Two Cities", _HAYNES_LEFT + 10.0, 4, _SOURCE_HEIGHT_PT),
        _line(_BODY, _COLUMN.left, 6),
    )
    (epigraph,) = epigraphs_after_heading(lines, 1, len(lines), _COLUMN)
    assert epigraph.source_lines == (2, 3)
    assert epigraph.source == "Dickens, A Tale of Two Cities"


def test_column_starts_at_the_leftmost_line_that_is_no_heading_line() -> None:
    # Turney's page 229: the title hangs left, the epigraphs' lines are the
    # most, and the text starts 43 pt left of them.
    lines = (
        _line("Chapter Ten", 110.0, 0),
        _line("Conclusion", 30.0, 1, 20.0),
        _line(_PROSE[0], 110.0, 3),
        _line("/", 20.0, 4),
        _line(_PROSE[1], 67.0, 6),
    )
    column = epigraph_column(lines, frozenset({0, 1}), Edges(110.0, 440.0))
    assert column == Edges(67.0, 440.0)
    assert epigraph_column(lines[:2], frozenset({0, 1}), _COLUMN) is None


def test_line_set_in_too_little_is_no_flush_right_source() -> None:
    # A verse turnover line, 25 pt right of the quotation (32 on Haynes
    # page 87), and ending with it: under the 60 pt of rule 3.
    quotation_right = _HAYNES_LEFT + _CHAR_PT * len(_PROSE[0])
    lines = (
        _heading(0),
        _line(_PROSE[0], _HAYNES_LEFT, 2),
        _flush_right(
            "and the age of wisdom and the age of foolishness too", quotation_right, 3
        ),
        _line(_BODY, _COLUMN.left, 5),
    )
    assert epigraphs_after_heading(lines, 1, len(lines), _COLUMN) == ()


def test_two_epigraphs_on_a_page_are_two_runs() -> None:
    lines = (
        _heading(0),
        _line(_PROSE[0], _HAYNES_LEFT, 2),
        _line("—Dickens", _HAYNES_LEFT, 3, _SOURCE_HEIGHT_PT),
        _line(_PROSE[1], _HAYNES_LEFT + 2.0, 5),
        _line("—Hobbes", _HAYNES_LEFT, 6, _SOURCE_HEIGHT_PT),
        _line(_BODY, _COLUMN.left, 8),
    )
    first, second = epigraphs_after_heading(lines, 1, len(lines), _COLUMN)
    assert (first.quotation, first.source, first.end) == ((1,), "Dickens", 3)
    assert (second.start, second.quotation, second.source) == (3, (3,), "Hobbes")


def test_next_run_further_in_than_3_pt_ends_the_epigraphs() -> None:
    lines = (
        _heading(0),
        _line(_PROSE[0], _HAYNES_LEFT, 2),
        _line("—Dickens", _HAYNES_LEFT, 3, _SOURCE_HEIGHT_PT),
        _line(_PROSE[1], _HAYNES_LEFT + 10.0, 5),
        _line("—Hobbes", _HAYNES_LEFT, 6, _SOURCE_HEIGHT_PT),
    )
    (epigraph,) = epigraphs_after_heading(lines, 1, len(lines), _COLUMN)
    assert epigraph.source == "Dickens"


def test_speck_before_the_quotation_is_a_stray_mark_of_the_epigraph() -> None:
    # Turney's pages 14, 26 and 148: a "/" between the title and the
    # epigraph.
    lines = (
        _heading(0),
        _line("/", _TURNEY_LEFT + 100.0, 1),
        *_haynes_page("—Dickens")[1:],
    )
    (epigraph,) = epigraphs_after_heading(lines, 1, len(lines), _COLUMN)
    assert (epigraph.start, epigraph.stray_marks) == (1, (1,))
    assert epigraph.quotation == (2, 3)


def test_indented_paragraph_without_a_source_is_no_epigraph() -> None:
    # Haynes' introduction: its text opens with an indented line.
    lines = (
        _heading(0),
        _line(_PROSE[0], _HAYNES_LEFT, 2),
        _line(_BODY, _COLUMN.left, 3),
        _line(_BODY, _COLUMN.left, 4),
    )
    assert epigraphs_after_heading(lines, 1, len(lines), _COLUMN) == ()


def test_heading_line_between_quotation_and_source_ends_the_run() -> None:
    lines = _haynes_page("—Dickens")
    assert epigraphs_after_heading(lines, 1, 3, _COLUMN) == ()


def test_run_that_reaches_the_end_without_a_source_is_no_epigraph() -> None:
    lines = (_heading(0), _line(_PROSE[0], _HAYNES_LEFT, 2))
    assert epigraphs_after_heading(lines, 1, len(lines), _COLUMN) == ()


_VERSE = (
    "Tyger Tyger , burning bright ,",
    "In the forests of the night ;",
    "“What immortal hand or eye ,",
    "... Could frame thy fearful symmetry ?",
)


def test_short_lines_starting_with_capitals_are_verse() -> None:
    lines = (
        _heading(0),
        *(_line(text, _HAYNES_LEFT, 2 + row) for row, text in enumerate(_VERSE)),
        _line("—Blake", _HAYNES_LEFT, 6, _SOURCE_HEIGHT_PT),
        _line(_BODY, _COLUMN.left, 8),
    )
    (epigraph,) = epigraphs_after_heading(lines, 1, len(lines), _COLUMN)
    assert epigraph.quotation == (1, 2, 3, 4)
    assert epigraph.form is QuotationForm.VERSE


def test_long_lines_starting_with_capitals_are_prose() -> None:
    # Haynes' page 156, the second: a second line that starts a sentence.
    lines = (
        _heading(0),
        _line(_PROSE[0], _HAYNES_LEFT, 2),
        _line("The age of foolishness and the epoch of belief and doubts", 80, 3),
        _line("—Dickens", _HAYNES_LEFT, 4, _SOURCE_HEIGHT_PT),
    )
    (epigraph,) = epigraphs_after_heading(lines, 1, len(lines), _COLUMN)
    assert epigraph.form is QuotationForm.PROSE


def test_long_verse_lines_with_a_turnover_line_are_verse() -> None:
    # Haynes' page 87: long lines, the end of one set further in.
    lines = (
        _heading(0),
        _line(_PROSE[0], _HAYNES_LEFT, 2),
        _line("of foolishness and belief", _HAYNES_LEFT + 32.0, 3),
        _line("The epoch of belief and the epoch of incredulity and so", 80, 4),
        _line("—Dickens", _HAYNES_LEFT, 5, _SOURCE_HEIGHT_PT),
    )
    (epigraph,) = epigraphs_after_heading(lines, 1, len(lines), _COLUMN)
    assert epigraph.form is QuotationForm.VERSE


def test_quotation_of_one_line_is_prose() -> None:
    lines = (
        _heading(0),
        _line("Tyger Tyger , burning bright ,", _HAYNES_LEFT, 2),
        _line("—Blake", _HAYNES_LEFT, 3, _SOURCE_HEIGHT_PT),
    )
    (epigraph,) = epigraphs_after_heading(lines, 1, len(lines), _COLUMN)
    assert epigraph.form is QuotationForm.PROSE


def _page_of_its_own(quotation_lines: int) -> tuple[PlacedLine, ...]:
    """Turney's page 13: the quotation set in the page's own measure, the
    source far right of it and ending with it."""
    quotation = tuple(_line(_BODY, _COLUMN.left, row) for row in range(quotation_lines))
    return (*quotation, _flush_right("Charles Dickens", _COLUMN.right, quotation_lines))


def test_page_holding_only_a_quotation_and_its_source_is_an_epigraph() -> None:
    epigraph = page_epigraph(_page_of_its_own(5), _COLUMN)
    assert epigraph is not None
    assert (epigraph.start, epigraph.quotation, epigraph.source_lines) == (
        0,
        (0, 1, 2, 3, 4),
        (5,),
    )
    assert epigraph.source == "Charles Dickens"


def test_page_of_more_than_10_lines_signed_at_the_right_is_no_epigraph() -> None:
    # A preface's last page, signed at the right.
    assert page_epigraph(_page_of_its_own(10), _COLUMN) is None


def test_page_of_10_lines_and_a_speck_is_an_epigraph() -> None:
    lines = (_line("/", 200.0, 0), *_page_of_its_own(9))
    epigraph = page_epigraph(lines, _COLUMN)
    assert epigraph is not None
    assert epigraph.stray_marks == (0,)


def test_page_with_lines_after_the_source_is_no_epigraph() -> None:
    lines = (*_page_of_its_own(3), _line(_BODY, _COLUMN.left, 5))
    assert page_epigraph(lines, _COLUMN) is None


# The rule wired into structure (spec section 2, step 2.3; section 22, "The
# block" and "The dash is look, not text"), through make_blocks. A chapter
# opens as in tests/test_structure_heads.py: a label 1.3 times the body's
# height indented 45 pt, a title 2.4 times, flush left, 1.5 pitches below
# it, and a region of the epigraph and the text 2 pitches under the title.

_NO_WORDS: frozenset[str] = frozenset()
_HASH = "a" * 64


def _region(*lines: PlacedLine) -> Region:
    boxes = tuple(line.line.box for line in lines)
    box = Box(
        min(box.x0 for box in boxes),
        min(box.top for box in boxes),
        max(box.x1 for box in boxes),
        max(box.bottom for box in boxes),
    )
    return Region(box, tuple(line.line for line in lines))


def _chapter_page(index: int, *epigraph: PlacedLine) -> PageLayout:
    """A chapter's first page: its label and title on rows -6 and -4.5, and
    `epigraph`, lines placed from row 0, before 8 lines of text set flush
    left two rows under the last of them."""
    label = _line("Chapter Twelve", _COLUMN.left + 45, -6, 1.3 * _HEIGHT_PT)
    title = _line("The Long Title", _COLUMN.left, -4.5, 2.4 * _HEIGHT_PT)
    first_text_row = int(max(line.line.box.top for line in epigraph) - 100) // 15 + 2
    text = tuple(_line(_BODY, _COLUMN.left, first_text_row + row) for row in range(8))
    return PageLayout(
        index, (_region(label), _region(title), _region(*epigraph, *text)), ()
    )


def _blocks(*pages: PageLayout) -> BlocksFile:
    lines = LinesFile(source_pdf_sha256=_HASH, pages=pages, rereads=())
    blocks = make_blocks(lines, _NO_WORDS, workers=1)
    check_stage(FidelityBoundary.STRUCTURE, lines, blocks)
    return blocks


def _kinds(blocks: BlocksFile) -> tuple[BlockKind, ...]:
    return tuple(block.kind for block in blocks.blocks)


_HAYNES_EPIGRAPH = (
    _line(_PROSE[0], _HAYNES_LEFT, 0),
    _line(_PROSE[1], _HAYNES_LEFT, 1),
    _line("it was the season of light", _HAYNES_LEFT, 2),
    _line("—Hobbes", _HAYNES_LEFT, 3, _SOURCE_HEIGHT_PT),
)


def test_dashed_source_under_a_chapter_heading_makes_an_epigraph_block() -> None:
    blocks = _blocks(_chapter_page(30, *_HAYNES_EPIGRAPH))
    assert _kinds(blocks) == (
        BlockKind.HEADING,
        BlockKind.EPIGRAPH,
        BlockKind.PARAGRAPH,
    )
    epigraph = blocks.blocks[1]
    assert block_text(epigraph) == " ".join((*_PROSE, "it was the season of light"))
    assert epigraph.source == "Hobbes"
    assert tuple(origin.page_index for origin in epigraph.origin) == (30,)
    assert epigraph.origin[0].box.bottom == _HAYNES_EPIGRAPH[3].line.box.bottom
    assert blocks.word_changes == (
        WordChange(
            page_index=30,
            before=("—Hobbes",),
            after=("Hobbes",),
            reason=ChangeReason.SOURCE_DASH,
        ),
    )


def test_source_set_flush_right_under_a_chapter_heading_has_no_change() -> None:
    source = "Hobbes, Leviathan"
    lines = (
        _line(_PROSE[0], _TURNEY_LEFT, 0),
        _line(_PROSE[1], _TURNEY_LEFT, 1),
        _flush_right(source, _line(_PROSE[1], _TURNEY_LEFT, 1).line.box.x1, 2),
    )
    assert lines[2].line.box.x0 - _TURNEY_LEFT >= 150
    blocks = _blocks(_chapter_page(30, *lines))
    assert _kinds(blocks) == (
        BlockKind.HEADING,
        BlockKind.EPIGRAPH,
        BlockKind.PARAGRAPH,
    )
    assert blocks.blocks[1].source == source
    assert blocks.word_changes == ()


def test_two_epigraphs_under_a_chapter_heading_are_two_blocks() -> None:
    lines = (
        _line(_PROSE[0], _HAYNES_LEFT, 0),
        _line("—Hobbes", _HAYNES_LEFT, 1, _SOURCE_HEIGHT_PT),
        _line(_PROSE[1], _HAYNES_LEFT, 3),
        _line("—Locke", _HAYNES_LEFT, 4, _SOURCE_HEIGHT_PT),
    )
    blocks = _blocks(_chapter_page(30, *lines))
    assert _kinds(blocks) == (
        BlockKind.HEADING,
        BlockKind.EPIGRAPH,
        BlockKind.EPIGRAPH,
        BlockKind.PARAGRAPH,
    )
    assert (blocks.blocks[1].source, blocks.blocks[2].source) == ("Hobbes", "Locke")


def test_indented_lines_without_a_source_under_a_chapter_heading_stay_text() -> None:
    lines = (
        _line(_PROSE[0], _HAYNES_LEFT, 0),
        _line(_PROSE[1], _HAYNES_LEFT, 1),
    )
    blocks = _blocks(_chapter_page(30, *lines))
    assert BlockKind.EPIGRAPH not in _kinds(blocks)
    assert all(block.source is None for block in blocks.blocks)


def test_speck_between_title_and_epigraph_is_removed_as_a_stray_mark() -> None:
    speck = _line("/", 200.0, 0)
    lines = tuple(
        _line(
            " ".join(word.text for word in line.line.words),
            line.line.box.x0,
            row + 1,
            line.line.box.bottom - line.line.box.top,
        )
        for row, line in enumerate(_HAYNES_EPIGRAPH)
    )
    blocks = _blocks(_chapter_page(30, speck, *lines))
    assert _kinds(blocks) == (
        BlockKind.HEADING,
        BlockKind.EPIGRAPH,
        BlockKind.PARAGRAPH,
    )
    assert block_text(blocks.blocks[1]).split()[0] == "it"
    assert tuple(
        (removal.reason, removal.text)
        for removal in blocks.removals
        if removal.page_index == 30
    ) == ((RemovalReason.STRAY_MARK, "/"),)


_TYGER = (
    "Tyger Tyger burning bright",
    "In the forests of the night",
    "What immortal hand or eye",
)


def test_verse_epigraph_keeps_its_line_breaks() -> None:
    lines = (
        *(_line(text, _HAYNES_LEFT, row) for row, text in enumerate(_TYGER)),
        _line("—Blake", _HAYNES_LEFT, 3, _SOURCE_HEIGHT_PT),
    )
    blocks = _blocks(_chapter_page(30, *lines))
    assert block_text(blocks.blocks[1]) == "\n".join(_TYGER)
    assert blocks.blocks[1].source == "Blake"


def test_prose_epigraph_joins_its_lines() -> None:
    blocks = _blocks(_chapter_page(30, *_HAYNES_EPIGRAPH))
    assert "\n" not in block_text(blocks.blocks[1])


def test_page_holding_only_an_epigraph_is_an_epigraph_block() -> None:
    quotation = (
        _line(_PROSE[0], _COLUMN.left, 0),
        _line(_PROSE[1], _COLUMN.left, 1),
    )
    source = _flush_right("Hobbes", quotation[1].line.box.x1, 2)
    page = PageLayout(13, (_region(*quotation, source),), ())
    blocks = _blocks(page)
    assert _kinds(blocks) == (BlockKind.EPIGRAPH,)
    assert blocks.blocks[0].source == "Hobbes"


# A short last line at a page break (spec section 6). Each page is one
# region of 6 lines, its right edge at 400 pt, the edge of its full lines.


def _text_page(index: int, *lines: PlacedLine) -> PageLayout:
    return PageLayout(index, (_region(*lines),), ())


def _page_ending_with(index: int, last: str) -> PageLayout:
    full = tuple(_line(_BODY, _COLUMN.left, row) for row in range(5))
    return _text_page(index, *full, _line(last, _COLUMN.left, 5))


# The body line above with a capital to start it.
_SENTENCE_START = "The" + _BODY.removeprefix("the")


def _flush_left_page(index: int, first: str = _SENTENCE_START) -> PageLayout:
    """A page of 6 full lines, flush left, the first `first`."""
    return _text_page(
        index,
        _line(first, _COLUMN.left, 0),
        *(_line(_BODY, _COLUMN.left, row) for row in range(1, 6)),
    )


def _ending(text: str, short_pt: float) -> str:
    """A line of words that ends with `text`, `short_pt` short of 400 pt."""
    characters = round((_COLUMN.right - _COLUMN.left - short_pt) / _CHAR_PT)
    filler = "x" * (characters - len(text) - 1)
    return f"{filler} {text}"


@pytest.mark.parametrize("end", ["it.", "it?", "it!", "it:", "it.”", "it.)", "it.43"])
def test_page_break_after_a_short_last_line_ending_a_sentence_starts_a_paragraph(
    end: str,
) -> None:
    blocks = _blocks(_page_ending_with(20, _ending(end, 30.0)), _flush_left_page(21))
    assert _kinds(blocks) == (BlockKind.PARAGRAPH, BlockKind.PARAGRAPH)
    assert blocks.blocks[1].origin[0].page_index == 21


@pytest.mark.parametrize(
    ("end", "short_pt"), [("it,", 30.0), ("it.", 15.0), ("it.4321", 30.0)]
)
def test_page_break_after_a_comma_or_a_line_15_pt_short_continues_the_paragraph(
    end: str, short_pt: float
) -> None:
    blocks = _blocks(
        _page_ending_with(20, _ending(end, short_pt)), _flush_left_page(21)
    )
    assert _kinds(blocks) == (BlockKind.PARAGRAPH,)


@pytest.mark.parametrize("first", [_BODY, "‘" + _BODY[1:], "“" + _BODY[1:]])
def test_page_break_before_a_line_starting_in_lower_case_continues_the_paragraph(
    first: str,
) -> None:
    # A note left in the body ends the page short with a full stop; the
    # sentence it interrupts runs on at the next page (spec section 6).
    blocks = _blocks(
        _page_ending_with(20, _ending("1 D. B. i. 141.", 30.0)),
        _flush_left_page(21, first),
    )
    assert _kinds(blocks) == (BlockKind.PARAGRAPH,)


@pytest.mark.parametrize(
    ("last", "kinds"),
    [("8 Companies Act , sec. 4.", 1), ("Companies Act , sec. 4.", 2), ("8.", 2)],
)
def test_page_break_after_a_line_led_by_a_note_marker_continues_the_paragraph(
    last: str, kinds: int
) -> None:
    # A footnote left in the body ends the page with its first line; the
    # sentence it interrupts runs on with a capital (spec section 6).
    blocks = _blocks(_page_ending_with(20, last), _flush_left_page(21))
    assert len(_kinds(blocks)) == kinds


def test_page_break_inside_a_verse_block_keeps_it_one_block() -> None:
    # Verse lines inset at least 30 pt from both edges (spec section 16,
    # rule 4), the last of page 20 ending a sentence.
    verse_left = _COLUMN.left + 60
    page_20 = _text_page(
        20,
        *(_line(_BODY, _COLUMN.left, row) for row in range(5)),
        _line(_TYGER[0], verse_left, 6),
        _line(_TYGER[1] + ".", verse_left, 7),
    )
    page_21 = _text_page(
        21,
        _line(_TYGER[2], verse_left, 0),
        _line("Could frame thy fearful symmetry", verse_left, 1),
        *(_line(_BODY, _COLUMN.left, row) for row in range(3, 8)),
    )
    blocks = _blocks(page_20, page_21)
    assert _kinds(blocks) == (
        BlockKind.PARAGRAPH,
        BlockKind.VERSE,
        BlockKind.PARAGRAPH,
    )
    assert tuple(origin.page_index for origin in blocks.blocks[1].origin) == (20, 21)


# Rules that only a test of their own shows (review of work package 4).


def test_lines_set_less_than_20_pt_in_are_no_epigraph_run() -> None:
    # Spec section 22, rule 2: two lines of text flush left and a line
    # signed flush right under them make no epigraph.
    signature = _flush_right("Hobbes", _COLUMN.right, 4)
    lines = (
        _heading(0),
        _line(_BODY, _COLUMN.left, 2),
        _line(_BODY, _COLUMN.left, 3),
        signature,
        _line(_BODY, _COLUMN.left, 6),
    )
    assert epigraphs_after_heading(lines, 1, len(lines), _COLUMN) == ()


@pytest.mark.parametrize(("level", "found"), [(1, 1), (2, 0)])
def test_epigraphs_are_looked_for_under_a_level_1_heading_only(
    level: int, found: int
) -> None:
    lines = _haynes_page("—Dickens")
    heading = BodyRun(start=0, end=1, kind=BlockKind.HEADING, level=level)
    assert len(page_epigraphs(lines, (heading,), (), _COLUMN)) == found


def test_epigraph_is_looked_for_after_the_chapter_summary() -> None:
    # Spec section 22, rule 1: a summary's first line lies at the left
    # edge, so a run looked for at the heading's end would find none.
    lines = (
        _heading(0),
        _line("Topics of the chapter — the first — the second", _COLUMN.left, 1),
        _line("— the third — the fourth", _COLUMN.left + 10, 2),
        *(
            _line(
                " ".join(word.text for word in line.line.words),
                line.line.box.x0,
                row + 4,
                line.line.box.bottom - line.line.box.top,
            )
            for row, line in enumerate(_haynes_page("—Dickens")[1:])
        ),
    )
    heading = BodyRun(start=0, end=1, kind=BlockKind.HEADING, level=1)
    summary = BodyRun(start=1, end=3, kind=BlockKind.CHAPTER_SUMMARY)
    (epigraph,) = page_epigraphs(lines, (heading,), (summary,), _COLUMN)
    assert (epigraph.quotation, epigraph.source_lines) == ((3, 4), (5,))


def test_dashed_line_after_a_dashed_source_does_not_continue_it() -> None:
    lines = (
        _heading(0),
        _line(_PROSE[0], _HAYNES_LEFT, 2),
        _line(_PROSE[1], _HAYNES_LEFT, 3),
        _line("—Dickens,", _HAYNES_LEFT, 4, _SOURCE_HEIGHT_PT),
        _line("—Locke", _HAYNES_LEFT, 5, _SOURCE_HEIGHT_PT),
        _line(_BODY, _COLUMN.left, 7),
    )
    (epigraph,) = epigraphs_after_heading(lines, 1, len(lines), _COLUMN)
    assert (epigraph.source_lines, epigraph.source) == ((3,), "Dickens,")


def test_smaller_line_4_pt_left_of_a_dashed_source_does_not_continue_it() -> None:
    lines = (
        _heading(0),
        _line(_PROSE[0], _HAYNES_LEFT, 2),
        _line(_PROSE[1], _HAYNES_LEFT, 3),
        _line("—Dickens,", _HAYNES_LEFT, 4, _SOURCE_HEIGHT_PT),
        _line("A Tale", _HAYNES_LEFT - 4.0, 5, _SOURCE_HEIGHT_PT),
        _line(_BODY, _COLUMN.left, 7),
    )
    (epigraph,) = epigraphs_after_heading(lines, 1, len(lines), _COLUMN)
    assert (epigraph.source_lines, epigraph.source) == ((3,), "Dickens,")


def test_source_line_starting_left_of_the_run_s_bound_does_not_continue_it() -> None:
    # The run's lines start exactly 20 pt in; a smaller line 2 pt left of
    # the source keeps its shape but lies left of the bound of rule 2.
    left = _COLUMN.left + 20.0
    lines = (
        _heading(0),
        _line(_BODY, _COLUMN.left, 1),
        _line(_PROSE[0], left, 2),
        _line(_PROSE[1], left, 3),
        _line("—Dickens,", left, 4, _SOURCE_HEIGHT_PT),
        _line("A Tale", left - 2.0, 5, _SOURCE_HEIGHT_PT),
    )
    (epigraph,) = epigraphs_after_heading(lines, 2, len(lines), _COLUMN)
    assert (epigraph.source_lines, epigraph.source) == ((4,), "Dickens,")


def test_last_quotation_line_set_in_but_ending_short_stays_in_the_quotation() -> None:
    # Spec section 22, rule 3: a source's first lines are set flush right;
    # a quotation's last line set 26 pt in but ending 50 pt short is not.
    lines = (
        _heading(0),
        _line(_JUSTIFIED, _TURNEY_LEFT, 2),
        _line(_JUSTIFIED, _TURNEY_LEFT, 3),
        _line("the end of it all", _TURNEY_LEFT + 26.0, 4),
        _flush_right("Quoted in French", _JUSTIFIED_RIGHT, 5),
        _line(_BODY, _COLUMN.left, 7),
    )
    (epigraph,) = epigraphs_after_heading(lines, 1, len(lines), _COLUMN)
    assert (epigraph.quotation, epigraph.source_lines) == ((1, 2, 3), (4,))


def test_short_lines_one_starting_in_lower_case_are_prose() -> None:
    lines = (
        _heading(0),
        _line(_VERSE[0], _HAYNES_LEFT, 2),
        _line("in the forests of the night ;", _HAYNES_LEFT, 3),
        _line("—Blake", _HAYNES_LEFT, 4, _SOURCE_HEIGHT_PT),
        _line(_BODY, _COLUMN.left, 6),
    )
    (epigraph,) = epigraphs_after_heading(lines, 1, len(lines), _COLUMN)
    assert epigraph.form is QuotationForm.PROSE


def _on_page(index: int, *lines: PlacedLine) -> tuple[PlacedLine, ...]:
    return tuple(replace(line, page_index=index) for line in lines)


def _parts(index: int, body: tuple[PlacedLine, ...], *, index_page: bool) -> PageParts:
    return PageParts(
        index=index,
        removals=(),
        page_numbers=(),
        body=body,
        margin_notes=(),
        band_regions=(),
        band_blocks=(),
        index_lines=body[:1] if index_page else (),
    )


@pytest.mark.parametrize("index_page", [20, 21])
def test_page_break_on_an_index_page_keeps_the_paragraph(index_page: int) -> None:
    # Spec section 6: the rule does not apply on the index pages
    # (section 17), on either side of the break.
    page_20 = _on_page(
        20,
        *(_line(_BODY, _COLUMN.left, row) for row in range(5)),
        _line(_ending("it.", 30.0), _COLUMN.left, 5),
    )
    page_21 = _on_page(
        21, *(_line(_SENTENCE_START, _COLUMN.left, row) for row in range(6))
    )
    entries = body_entries(
        (
            _parts(20, page_20, index_page=index_page == 20),
            _parts(21, page_21, index_page=index_page == 21),
        ),
        body_word_height=_HEIGHT_PT,
    )
    assert len(entries) == 1


def test_page_break_off_the_index_pages_ends_the_paragraph() -> None:
    page_20 = _on_page(
        20,
        *(_line(_BODY, _COLUMN.left, row) for row in range(5)),
        _line(_ending("it.", 30.0), _COLUMN.left, 5),
    )
    page_21 = _on_page(
        21, *(_line(_SENTENCE_START, _COLUMN.left, row) for row in range(6))
    )
    entries = body_entries(
        (_parts(20, page_20, index_page=False), _parts(21, page_21, index_page=False)),
        body_word_height=_HEIGHT_PT,
    )
    assert len(entries) == 2


# A numbered paragraph at a page break (spec section 16, "A numbered
# paragraph runs on"): a block led by a word of the book's marker form,
# "1.", runs on when it is set in the body's type and its page's last line
# ends no sentence, as Kadesh's "1. Of the three…" on page 11.


def _numbered_page(last: str, height: float) -> tuple[PlacedLine, ...]:
    return _on_page(
        20,
        _line("1. " + _BODY.removesuffix(" ."), _COLUMN.left, 0, height),
        *(_line(_BODY.removesuffix(" ."), _COLUMN.left, row, height) for row in (1, 2)),
        _line(_ending(last, 0.0), _COLUMN.left, 3, height),
    )


def _numbered_entries(last: str, height: float) -> int:
    page_21 = _on_page(21, *(_line(_BODY, _COLUMN.left, row) for row in range(4)))
    return len(
        body_entries(
            (
                _parts(20, _numbered_page(last, height), index_page=False),
                _parts(21, page_21, index_page=False),
            ),
            MarkerForm.DIGITS,
            body_word_height=_HEIGHT_PT,
        )
    )


def test_numbered_paragraph_in_body_type_runs_on_over_the_page_break() -> None:
    assert _numbered_entries("with the", _HEIGHT_PT) == 1


def test_numbered_block_in_smaller_type_is_a_note_and_does_not_run_on() -> None:
    # Height ratio 0.9: a note left in the body (section 11).
    assert _numbered_entries("with the", 9.0) == 2


@pytest.mark.parametrize("last", ["it.", "follows:", "it.”"])
def test_numbered_paragraph_ending_a_sentence_does_not_run_on(last: str) -> None:
    assert _numbered_entries(last, _HEIGHT_PT) == 2


# A source's dash and the fidelity check (spec section 22, "The dash is
# look, not text").


def test_line_of_dashes_alone_is_no_source_line() -> None:
    lines = _haynes_page("—")
    assert epigraphs_after_heading(lines, 1, len(lines), _COLUMN) == ()


def test_dash_removal_leaving_no_word_is_refused_by_the_fidelity_check() -> None:
    page = _chapter_page(30, *_HAYNES_EPIGRAPH)
    lines = LinesFile(source_pdf_sha256=_HASH, pages=(page,), rereads=())
    blocks = make_blocks(lines, _NO_WORDS, workers=1)
    emptied = replace(
        blocks,
        word_changes=(
            WordChange(
                page_index=30,
                before=("—",),
                after=("",),
                reason=ChangeReason.SOURCE_DASH,
            ),
        ),
    )
    with pytest.raises(FidelityError, match="is not a source_dash"):
        check_stage(FidelityBoundary.STRUCTURE, lines, emptied)


def test_source_dash_comes_after_the_quotation_s_hyphen_join() -> None:
    # The dash's removal is placed after the quotation's last word, so
    # that blocks.json lists the block's changes in the order of its words.
    lines = (
        _line(
            "it was the best of times and the worst of times , the fool-",
            _HAYNES_LEFT,
            0,
        ),
        _line("ishness of the age of wisdom and the epoch of belief", _HAYNES_LEFT, 1),
        _line("—Dickens", _HAYNES_LEFT, 2, _SOURCE_HEIGHT_PT),
    )
    blocks = _blocks(_chapter_page(30, *lines))
    assert blocks.blocks[1].kind is BlockKind.EPIGRAPH
    assert tuple(change.reason for change in blocks.word_changes) == (
        ChangeReason.HYPHEN_JOIN_GUESSED,
        ChangeReason.SOURCE_DASH,
    )


# Structure spec section 26, "Whole-book tests": none of the six
# public-domain books prints an epigraph; the margin of 2 is for a motto
# the rule takes.
_PUBLIC_DOMAIN_BOOKS = (
    "normansineuropea00hask",
    "earlyplantagenet01stub",
    "domesdaybook00maituoft",
    "battleofkadeshst00breauoft",
    "politicaltheorie00gieruoft",
)
_PUBLIC_DOMAIN_EPIGRAPHS_MAX = 2


@pytest.mark.whole_book
@pytest.mark.thread_unsafe
@pytest.mark.timeout(900)
@pytest.mark.parametrize("book", _PUBLIC_DOMAIN_BOOKS)
def test_whole_book_public_domain_book_has_at_most_2_epigraph_blocks(
    whole_book_run: Callable[[str], BookFolder], book: str
) -> None:
    blocks = read_blocks(whole_book_run(book).blocks_json)
    epigraphs = sum(block.kind is BlockKind.EPIGRAPH for block in blocks.blocks)
    assert epigraphs <= _PUBLIC_DOMAIN_EPIGRAPHS_MAX
