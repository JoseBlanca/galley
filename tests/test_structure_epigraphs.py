"""Tests of structure's epigraph rule (docs/specs/structure.md, section 22;
the epigraphs bullet of section 26's unit tests).

Every page's body stream is written by hand: a word is 5 pt wide per
character and 10 pt high (a source in smaller type 8 pt), with one
character's width between words, and lines lie 15 pt apart. The body
column runs from 50 to 400 pt; a quotation is indented 30 pt, as Haynes'
are, or 44 pt, as Turney's.
"""

from galley.model import Box, ChangeReason, Line, Word, WordChange
from galley.structure._epigraphs import (
    QuotationForm,
    epigraph_column,
    epigraphs_after_heading,
    page_epigraph,
)
from galley.structure._lines import PlacedLine
from galley.structure._measures import Edges

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


def _line(text: str, x0: float, row: int, height: float = _HEIGHT_PT) -> PlacedLine:
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
