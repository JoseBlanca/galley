"""Tests of galley.body_measures: the rows of a page, the commonest edge and
the body word height and body line pitch that layout and structure both
take (architecture section 12; layout spec sections 1 and 3).

The rows are written by hand, one word each unless a test needs more, in
PDF points with the origin at the top left of the page.
"""

import pytest

from galley.body_measures import (
    BodyMeasures,
    body_measures,
    commonest,
    edge_counts,
    group_rows,
    measured_pages,
    median_word_height,
)
from galley.model import Box, Line, Word


def _word(text: str, x0: float, top: float, x1: float, bottom: float) -> Word:
    return Word(text, Box(x0, top, x1, bottom), None)


def _texts(rows: tuple[Line, ...]) -> tuple[tuple[str, ...], ...]:
    return tuple(tuple(word.text for word in row.words) for row in rows)


def _rows(count: int, *, height: float, pitch: float) -> tuple[Line, ...]:
    """`count` rows of one word `height` tall, their tops `pitch` apart."""
    return tuple(
        Line(
            Box(50, index * pitch, 300, index * pitch + height),
            (_word(f"row-{index}", 50, index * pitch, 300, index * pitch + height),),
        )
        for index in range(count)
    )


# group_rows


def test_two_rows_given_shuffled_come_out_as_two_rows_left_to_right() -> None:
    words = (
        _word("four", 70, 30, 90, 40),
        _word("two", 40, 10, 60, 20),
        _word("three", 10, 30, 30, 40),
        _word("one", 10, 10, 30, 20),
    )
    rows = group_rows(words)
    assert _texts(rows) == (("one", "two"), ("three", "four"))
    assert tuple(row.box for row in rows) == (Box(10, 10, 60, 20), Box(10, 30, 90, 40))


def test_word_whose_centre_is_on_the_anchors_bottom_joins_its_row() -> None:
    # Centre (10 + 30) / 2 = 20.0, the anchor's bottom: edges are included.
    words = (_word("anchor", 10, 10, 30, 20), _word("edge", 40, 10, 60, 30))
    assert _texts(group_rows(words)) == (("anchor", "edge"),)


def test_word_whose_centre_is_below_the_anchors_bottom_starts_a_row() -> None:
    words = (_word("anchor", 10, 10, 30, 20), _word("below", 40, 10.02, 60, 30))
    assert _texts(group_rows(words)) == (("anchor",), ("below",))


def test_word_two_points_below_with_its_centre_in_the_band_joins_the_row() -> None:
    words = (_word("anchor", 10, 10, 30, 20), _word("low", 40, 12, 60, 22))
    rows = group_rows(words)
    assert _texts(rows) == (("anchor", "low"),)
    assert rows[0].box == Box(10, 10, 60, 22)


def test_two_columns_of_two_rows_give_two_rows_across_both_columns() -> None:
    # The rule knows no columns: a row runs across both, and layout cuts
    # the body into columns before it groups rows.
    words = (
        _word("left-1", 10, 10, 100, 20),
        _word("left-2", 10, 30, 100, 40),
        _word("right-1", 200, 10, 300, 20),
        _word("right-2", 200, 30, 300, 40),
    )
    assert _texts(group_rows(words)) == (
        ("left-1", "right-1"),
        ("left-2", "right-2"),
    )


def test_words_with_the_same_top_and_x0_keep_their_given_order() -> None:
    words = (_word("first", 10, 10, 30, 20), _word("second", 10, 10, 30, 20))
    assert _texts(group_rows(words)) == (("first", "second"),)


def test_words_of_a_row_are_sorted_by_x0() -> None:
    # "right" comes first by top and anchors the band 10-20; "left" has its
    # centre at 16, joins, and goes before "right" by x0.
    words = (_word("right", 50, 10, 70, 20), _word("left", 10, 11, 30, 21))
    rows = group_rows(words)
    assert _texts(rows) == (("left", "right"),)
    assert rows[0].box == Box(10, 10, 70, 21)


def test_a_row_keeps_the_band_of_its_first_word() -> None:
    # Each word 4 pt lower than the one before: "b" (centre 9) is in the
    # band of "a" (0-10), "c" (centre 13) is not, though it is in b's.
    words = (
        _word("a", 10, 0, 20, 10),
        _word("b", 30, 4, 40, 14),
        _word("c", 50, 8, 60, 18),
    )
    rows = group_rows(words)
    assert _texts(rows) == (("a", "b"), ("c",))
    assert tuple(row.box for row in rows) == (Box(10, 0, 40, 14), Box(50, 8, 60, 18))


def test_words_with_the_same_top_are_taken_by_x0() -> None:
    # "short" goes first by x0 and anchors the band 10-14; the centre of
    # "tall", 20, is outside it. Taken in the given order, "tall" would
    # anchor the band 10-30 and "short" (centre 12) would join it.
    words = (_word("tall", 50, 10, 60, 30), _word("short", 10, 10, 20, 14))
    rows = group_rows(words)
    assert _texts(rows) == (("short",), ("tall",))
    assert tuple(row.box for row in rows) == (
        Box(10, 10, 20, 14),
        Box(50, 10, 60, 30),
    )


def test_no_words_give_no_rows() -> None:
    assert group_rows(()) == ()


# commonest


def test_commonest_is_the_value_with_the_most_edges_within_2_pt() -> None:
    # Rounded: 100, 102, 103, 104, 140, 140. Within 2 pt of 102 are four
    # edges, of 103 and 104 three, of 100 and 140 two. Within 1 pt, 103
    # would win with three.
    assert commonest((100.4, 101.6, 103.0, 104.0, 140.0, 140.2)) == 102.0


def test_edge_counts_give_each_rounded_edge_the_edges_within_2_pt() -> None:
    assert edge_counts((100.4, 101.6, 103.0, 104.0, 140.0, 140.2)) == frozendict(
        {100.0: 2, 102.0: 4, 103.0: 3, 104.0: 3, 140.0: 2}
    )


def test_edge_counts_of_no_edges_are_empty() -> None:
    assert edge_counts(()) == frozendict()


def test_commonest_on_a_tie_is_the_smaller_value() -> None:
    assert commonest((80.0, 20.0)) == 20.0


def test_commonest_of_no_edges_is_an_error() -> None:
    with pytest.raises(ValueError, match="no edges"):
        commonest(())


# median_word_height


def test_median_word_height_is_the_median_of_the_words_heights() -> None:
    # 8, 9 and 14 pt: the median is 9 pt, the mean 10.33 pt.
    words = (
        _word("short", 0, 0, 10, 8),
        _word("tall", 0, 0, 10, 14),
        _word("middle", 0, 0, 10, 9),
    )
    assert median_word_height(words) == 9.0


def test_median_word_height_of_no_words_is_0() -> None:
    assert median_word_height(()) == 0.0


# measured_pages


def test_measured_pages_are_those_of_at_least_15_rows() -> None:
    fifteen = _rows(15, height=10, pitch=12)
    pages = (_rows(14, height=10, pitch=12), fifteen, _rows(3, height=10, pitch=12))
    assert measured_pages(pages) == (fifteen,)


def test_measured_pages_are_those_of_3_rows_when_none_has_15() -> None:
    fourteen = _rows(14, height=10, pitch=12)
    three = _rows(3, height=10, pitch=12)
    pages = (fourteen, _rows(2, height=10, pitch=12), three)
    assert measured_pages(pages) == (fourteen, three)


def test_no_page_is_measured_when_none_has_3_rows() -> None:
    assert measured_pages((_rows(2, height=10, pitch=12), ())) == ()


# body_measures


def test_body_measures_leave_out_pages_of_fewer_than_15_rows() -> None:
    pages = (_rows(15, height=10, pitch=12), _rows(2, height=20, pitch=50))
    assert body_measures(pages) == BodyMeasures(
        body_word_height=10.0, body_line_pitch=12.0
    )


def test_body_word_height_is_the_median_over_the_rows_of_all_pages_pooled() -> None:
    # 15 rows of 8 pt and 16 of 10 pt: the median of the 31 rows is 10 pt,
    # where the median of the two pages' medians would be 9 pt.
    pages = (_rows(15, height=8, pitch=12), _rows(16, height=10, pitch=12))
    measures = body_measures(pages)
    assert measures is not None
    assert measures.body_word_height == 10.0


def test_body_line_pitch_takes_no_distance_from_one_page_to_the_next() -> None:
    # 14 pitches of 12 pt and 15 of 14 pt give a median of 14 pt; a
    # distance from the last row of a page to the first of the next, -168
    # pt here, would make it 13 pt.
    pages = (_rows(15, height=10, pitch=12), _rows(16, height=10, pitch=14))
    measures = body_measures(pages)
    assert measures is not None
    assert measures.body_line_pitch == 14.0


def test_body_line_pitch_is_measured_from_the_top_of_one_row_to_the_next() -> None:
    # Each row holds a word 3 pt lower than its anchor, 0.25 pt taller on
    # each row: the rows' tops, the anchors', are 12 pt apart, their bottoms
    # 12.25 pt. The body word height is the median of the rows' medians,
    # 10 + 7 * 0.125 pt.
    rows = tuple(
        group_rows(
            (
                _word("anchor", 50, index * 12, 100, index * 12 + 10),
                _word(
                    "lower",
                    110,
                    index * 12 + 3,
                    160,
                    index * 12 + 13 + index * 0.25,
                ),
            )
        )[0]
        for index in range(15)
    )
    assert len(rows[14].words) == 2
    assert body_measures((rows,)) == BodyMeasures(
        body_word_height=10.875, body_line_pitch=12.0
    )


def test_body_measures_are_none_when_no_page_has_3_rows() -> None:
    assert body_measures((_rows(2, height=10, pitch=12), ())) is None
