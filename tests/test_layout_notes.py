"""Tests of layout's column cut for notes printed in two columns at the
back (docs/specs/layout.md, section 3, step 5: a number hung before the
right column). Words are written by hand: rows 8 pt high, 12 pt apart, in
the column of 200 pt from 50 pt."""

from galley.layout import BookMeasures, layout_page
from galley.model import Box, PageWords, TextSource, Word

_ROW_HEIGHT = 8.0
_PITCH = 12.0
_MEASURES = BookMeasures(
    column_width=200.0,
    body_word_height=_ROW_HEIGHT,
    body_line_pitch=_PITCH,
    usual_left_edge=frozendict({0: 50.0, 1: 50.0}),
    cut_in_inset_left=None,
    cut_in_inset_right=None,
)


def _word(text: str, x0: float, x1: float, row: int) -> Word:
    top = 100.0 + row * _PITCH
    return Word(text, Box(x0, top, x1, top + _ROW_HEIGHT), None)


def _page(right_first: str) -> PageWords:
    """Ten rows: a left column ending at 126 pt, and a right column whose
    text starts at 155; rows 2, 5 and 8 open a note with a number at 140
    to 148, and on rows 8 and 9 the left column is empty, so that the
    gutter falls between the numbers and their text. `right_first` is
    the first word of the right column's noted rows."""
    words = []
    for row in range(10):
        if row < 8:
            words.append(_word(f"left{row}", 50, 126, row))
        if row in (2, 5, 8):
            words.append(_word(str(row), 140, 148, row))
            words.append(_word(right_first, 155, 250, row))
        else:
            words.append(_word(f"right{row}", 155, 250, row))
    return PageWords(
        index=0, text_source=TextSource.TEXT_LAYER, words=tuple(words), figures=()
    )


def _first_words(page: PageWords) -> tuple[tuple[str, ...], ...]:
    result = layout_page(page, _MEASURES)
    return tuple(
        tuple(line.words[0].text for line in region.lines) for region in result.regions
    )


def test_number_hung_before_the_right_column_goes_with_its_line() -> None:
    # The run ends at its last open row, 8; row 9 is a region of its own.
    assert _first_words(_page("Note")) == (
        tuple(f"left{row}" for row in range(8)),
        ("right0", "right1", "2", "right3", "right4", "5", "right6", "right7", "8"),
        ("right9",),
    )


def test_number_before_a_number_of_the_right_column_stays_left() -> None:
    # Gierke's contents: the right column's line starts with a number.
    regions = _first_words(_page("121"))
    assert regions[1][2] == "121"


def test_number_nearer_the_word_before_it_stays_in_the_left_column() -> None:
    # The number ends its left line 2 pt after the word before it and lies
    # 10 pt from the right column's text: it is the left line's, not hung.
    words = []
    for row in range(10):
        words.append(_word(f"left{row}", 50, 120, row))
        if row in (2, 5, 8):
            words.append(_word(str(row), 122, 130, row))
        words.append(_word(f"right{row}", 140, 250, row))
    page = PageWords(
        index=0, text_source=TextSource.TEXT_LAYER, words=tuple(words), figures=()
    )
    result = layout_page(page, _MEASURES)
    left = result.regions[0]
    assert tuple(word.text for word in left.lines[2].words) == ("left2", "2")
