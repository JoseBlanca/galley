"""Tests of the list rules of galley.structure (docs/specs/structure.md,
sections 29 and 32).

The unit tests write their lines by hand, in the geometry section 29's
table gives for Haynes' and Domesday's lists; no text of the owner's books
is used beyond a dash and a capital.
"""

import pytest

from galley.model import Box, Line, Word
from galley.structure._lines import PlacedLine
from galley.structure._lists import (
    ItemLine,
    ListMarker,
    MarkerKind,
    StreamPage,
    list_items,
    marker_readings,
)
from galley.structure._measures import Edges

_CHAR_PT = 5.0
_WORD_HEIGHT_PT = 10.0
_PITCH_PT = 14.0
_EDGES = Edges(37.9, 340.0)


def _placed(
    text: str, x0: float, top: float, page_index: int = 0, x1: float | None = None
) -> PlacedLine:
    """A line of `text` whose left side is `x0` and top `top`, its words
    5 pt a character with one character between them; it ends at `x1`
    when given, the words spread to reach it."""
    words = []
    left = x0
    for part in text.split(" "):
        right = left + _CHAR_PT * len(part)
        words.append(Word(part, Box(left, top, right, top + _WORD_HEIGHT_PT), None))
        left = right + _CHAR_PT
    if x1 is not None and len(words) > 1:
        last = words[-1]
        width = last.box.x1 - last.box.x0
        words[-1] = Word(last.text, Box(x1 - width, top, x1, last.box.bottom), None)
    box = Box(x0, top, words[-1].box.x1, top + _WORD_HEIGHT_PT)
    return PlacedLine(page_index, Line(box, tuple(words)), _EDGES, _EDGES)


def _starts(found: frozendict[tuple[int, int], ItemLine]) -> tuple[str, ...]:
    """The markers of the items found, in order."""
    return tuple(
        item.marker.text for _, item in sorted(found.items()) if item.marker is not None
    )


# Marker readings (spec section 29, "Terms").


@pytest.mark.parametrize(
    ("word", "expected"),
    [
        ("—The", (ListMarker("—", MarkerKind.DASH, "—", None),)),
        ("–", (ListMarker("–", MarkerKind.DASH, "–", None),)),
        ("•", (ListMarker("•", MarkerKind.BULLET, "•", None),)),
        ("1.", (ListMarker("1.", MarkerKind.NUMBER, "1.", 1),)),
        ("12)", (ListMarker("12)", MarkerKind.NUMBER, "1)", 12),)),
        ("(3)", (ListMarker("(3)", MarkerKind.NUMBER, "(1)", 3),)),
        ("a.", (ListMarker("a.", MarkerKind.LETTER, "a.", 1),)),
        ("(B)", (ListMarker("(B)", MarkerKind.LETTER, "(A)", 2),)),
        ("iv.", (ListMarker("iv.", MarkerKind.ROMAN, "i.", 4),)),
        ("(xiv)", (ListMarker("(xiv)", MarkerKind.ROMAN, "(i)", 14),)),
        (
            "I.",
            (
                ListMarker("I.", MarkerKind.ROMAN, "I.", 1),
                ListMarker("I.", MarkerKind.LETTER, "A.", 9),
            ),
        ),
    ],
)
def test_list_marker_reads_its_kind_form_and_value(
    word: str, expected: tuple[ListMarker, ...]
) -> None:
    assert marker_readings(word) == expected


@pytest.mark.parametrize(
    "word", ["(3.", "3", "123.", "Mr.", "xvi.", "ib.", "-The", "—1", "the", "•The"]
)
def test_word_that_is_no_list_marker_has_no_reading(word: str) -> None:
    assert marker_readings(word) == ()


# The rules (spec section 29, rules 1 to 6), on lines written here.

_MARKER_PT = 37.9
_HANG_PT = 50.4


def _haynes_pages() -> tuple[StreamPage, StreamPage]:
    """Six dash items in Haynes' geometry (spec section 32, the first
    unit test): a lead-in line, then on page 0 items 1 to 5, each a marker
    line at 37.9 pt and continuation lines at 50.4 pt, 2 pitches below the
    lead-in; on page 1 item 5's last five lines at 72.0 pt, item 6's marker
    line at 59.5 pt and its continuation, then a line flush at 59.3 pt 2
    pitches lower."""
    first = [_placed("sorted into six common types:", _MARKER_PT, 100)]
    top = 100 + 2 * _PITCH_PT
    for _ in range(5):
        first.append(_placed("—The item starts here", _MARKER_PT, top))
        first.append(_placed("and goes on here", _HANG_PT, top + _PITCH_PT))
        top += 2 * _PITCH_PT
    second = [_placed("and goes on", 72.0, 60 + n * _PITCH_PT, 1) for n in range(5)]
    second.append(_placed("—The last item", 59.5, 60 + 5 * _PITCH_PT, 1))
    second.append(_placed("ends here.", 72.0, 60 + 6 * _PITCH_PT, 1))
    second.append(_placed("The paragraph after", 59.3, 60 + 8 * _PITCH_PT, 1))
    return StreamPage(tuple(first)), StreamPage(tuple(second))


def test_dash_list_over_a_page_break_gives_six_items_in_haynes_geometry() -> None:
    found = list_items(_haynes_pages(), _PITCH_PT)
    assert _starts(found) == ("—",) * 6
    # The lead-in and the paragraph after are no item; item 5 runs on to
    # page 1, whose marker column is found again at 59.5 pt.
    assert (0, 0) not in found
    assert (1, 7) not in found
    assert all((1, number) in found for number in range(7))
    assert found[1, 5].marker is not None
    assert found[1, 0].marker is None


def _numbered(
    texts: tuple[tuple[str, ...], ...], marker_pt: float = 40.0, hang_pt: float = 54.0
) -> StreamPage:
    """Items one after another, each a marker line at `marker_pt` and its
    other lines at `hang_pt`, a pitch apart."""
    lines = []
    top = 100.0
    for item in texts:
        for number, text in enumerate(item):
            lines.append(_placed(text, marker_pt if number == 0 else hang_pt, top))
            top += _PITCH_PT
    return StreamPage(tuple(lines))


def test_numbered_list_whose_middle_items_have_one_line_gives_five_items() -> None:
    page = _numbered(
        (
            ("1. First item", "goes on"),
            ("2. Second item", "goes on", "and on"),
            ("3. Third item",),
            ("4. Fourth item",),
            ("5. Fifth item", "goes on"),
        )
    )
    found = list_items((page,), _PITCH_PT)
    assert _starts(found) == ("1.", "2.", "3.", "4.", "5.")
    assert len(found) == len(page.lines)


def test_dash_inside_running_text_at_the_left_side_is_no_list() -> None:
    # Stubbs' page 21: a line starts with "—" inside a sentence, and the
    # next lies at the same left side.
    page = StreamPage(
        (
            _placed("of the reign", 40.0, 100),
            _placed("— the only period during which", 40.0, 114),
            _placed("the king was at home", 40.0, 128),
        )
    )
    assert list_items((page,), _PITCH_PT) == frozendict()


def test_one_marker_line_with_a_hang_and_no_second_item_is_no_list() -> None:
    page = _numbered((("1. Only item", "goes on", "and on"),))
    page = StreamPage((*page.lines, _placed("A paragraph after", 40.0, 142)))
    assert list_items((page,), _PITCH_PT) == frozendict()


def test_items_2_and_3_without_1_are_no_list() -> None:
    page = _numbered((("2. Second", "goes on"), ("3. Third", "goes on")))
    assert list_items((page,), _PITCH_PT) == frozendict()


def test_items_1_then_3_are_no_list() -> None:
    page = _numbered((("1. First", "goes on"), ("3. Third", "goes on")))
    assert list_items((page,), _PITCH_PT) == frozendict()


def test_numbered_paragraphs_indented_15_pt_are_no_list() -> None:
    # Kadesh's page 11: each first line indented 15 pt, the others at the
    # column's edge.
    lines = []
    top = 100.0
    for number in (1, 2, 3):
        lines.append(_placed(f"{number}. Of the three sources", 55.0, top))
        lines.append(_placed("the text goes on to the edge", 40.0, top + _PITCH_PT))
        lines.append(_placed("and ends.", 40.0, top + 2 * _PITCH_PT))
        top += 3 * _PITCH_PT
    assert list_items((StreamPage(tuple(lines)),), _PITCH_PT) == frozendict()


def test_marker_line_inside_a_verse_run_is_no_list() -> None:
    page = _numbered((("1. First", "goes on"), ("2. Second", "goes on")))
    closed = StreamPage(page.lines, frozenset(range(len(page.lines))))
    assert list_items((closed,), _PITCH_PT) == frozendict()


def test_marker_line_after_a_line_ending_with_a_hyphen_is_no_list() -> None:
    page = _numbered((("1. First", "goes on"), ("2. Second", "goes on")))
    page = StreamPage((_placed("a word cut by a hy-", 40.0, 86), *page.lines))
    assert list_items((page,), _PITCH_PT) == frozendict()


def test_line_2_pitches_below_the_last_item_and_indented_12_pt_is_kept_out() -> None:
    page = _numbered((("1. First", "goes on"), ("2. Second", "goes on")))
    after = _placed("A paragraph indented", 52.0, 100 + 5 * _PITCH_PT)
    found = list_items((StreamPage((*page.lines, after)),), _PITCH_PT)
    assert _starts(found) == ("1.", "2.")
    assert (0, 4) not in found


def test_list_of_one_item_gives_its_line_after_to_a_list_that_starts_there() -> None:
    # Domesday's page 156: "I. COMBERTON…" reads as a roman first value, and
    # "1. Seven sokemen…" lies 8.6 pt right of it, then rows 2 and 3.
    page = StreamPage(
        (
            _placed("I. COMBERTON. A vill of 6 hides.", 40.0, 100),
            _placed("1. Seven sokemen of the King", 48.6, 114),
            _placed("A sokeman, man of Earl Waltheof", 62.6, 128),
            _placed("2. A man of Earl Waltheof", 48.6, 142),
            _placed("3. A sokeman, man of the King", 48.6, 156),
        )
    )
    assert _starts(list_items((page,), _PITCH_PT)) == ("1.", "2.", "3.")


def test_i_after_h_is_a_letter_and_after_a_roman_numeral_a_numeral() -> None:
    letters = _numbered(
        tuple((f"{letter}. Item", "goes on") for letter in "abcdefghij")
    )
    numerals = _numbered((("i. Item", "goes on"), ("ii. Item", "goes on")))
    assert _starts(list_items((letters,), _PITCH_PT)) == tuple(
        f"{letter}." for letter in "abcdefghij"
    )
    assert _starts(list_items((numerals,), _PITCH_PT)) == ("i.", "ii.")


def test_closed_page_between_two_items_ends_the_list() -> None:
    first = _numbered((("1. First", "goes on"),))
    contents = StreamPage((_placed("A contents line", 40.0, 100, 1),), frozenset({0}))
    second = StreamPage((_placed("2. Second", 40.0, 100, 2),))
    assert list_items((first, contents, second), _PITCH_PT) == frozendict()
