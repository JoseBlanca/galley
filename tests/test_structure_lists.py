"""Tests of the list rules of galley.structure (docs/specs/structure.md,
sections 29 and 32).

The unit tests write their lines by hand, in the geometry section 29's
table gives for Haynes' and Domesday's lists; no text of the owner's books
is used beyond a dash and a capital.
"""

import json
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from galley.book_folder import BookFolder
from galley.errors import FidelityBoundary
from galley.fidelity import check_stage
from galley.list_markers import ListMarker, MarkerKind, marker_readings
from galley.model import (
    BlockKind,
    BlocksFile,
    Box,
    ChangeReason,
    Line,
    LinesFile,
    PageLayout,
    Region,
    Word,
    block_text,
    read_blocks,
)
from galley.structure import make_blocks
from galley.structure._assemble import _line_roles
from galley.structure._lines import PlacedLine
from galley.structure._lists import ItemLine, StreamPage, list_items
from galley.structure._measures import Edges
from galley.structure._paragraphs import PageParts
from galley.structure._runs import BodyRun

_CHAR_PT = 5.0
_WORD_HEIGHT_PT = 10.0
_PITCH_PT = 14.0
_EDGES = Edges(37.9, 340.0)


def _placed(
    text: str,
    x0: float,
    top: float,
    page_index: int = 0,
    x1: float | None = None,
    text_edge: float | None = None,
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
    return PlacedLine(page_index, Line(box, tuple(words)), _EDGES, _EDGES, text_edge)


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
    first = [_placed("grouped around six recurrent stereotypes:", _MARKER_PT, 100)]
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


def test_in_page_figure_between_two_items_does_not_end_the_list() -> None:
    # Spec section 29, rule 5: the gap is not tested across an in-page
    # figure, whose lines are out of the body stream.
    first = _numbered((("1. First", "goes on"),))
    after = _placed("2. Second", 40.0, 100 + 2 * _PITCH_PT + 120, 0)
    figure = Box(40.0, 100 + 2 * _PITCH_PT, 300.0, 100 + 2 * _PITCH_PT + 110)
    with_figure = StreamPage((*first.lines, after), figures=(figure,))
    without = StreamPage((*first.lines, after))
    assert _starts(list_items((with_figure,), _PITCH_PT)) == ("1.", "2.")
    assert list_items((without,), _PITCH_PT) == frozendict()


def _over_a_break(
    second: tuple[PlacedLine, ...],
) -> tuple[frozendict[tuple[int, int], ItemLine], int]:
    """Items "1." and "2." at 40 pt with their hang at 54 pt on page 0, then
    page 1's lines `second`; the found lines and how many of page 1's."""
    first = _numbered((("1. First", "goes on"), ("2. Second", "goes on")))
    found = list_items((first, StreamPage(second)), _PITCH_PT)
    return found, sum(1 for page_index, _ in found if page_index == 1)


def test_page_with_no_marker_line_and_no_text_edge_ends_the_list() -> None:
    # Spec section 29, rule 6: without a marker line to find the column by,
    # the text edge of the page's first body region; without one, the list
    # ends at the page break.
    lines = tuple(
        _placed("goes on still", 54.0, 60 + n * _PITCH_PT, 1) for n in range(2)
    )
    assert _over_a_break(lines)[1] == 0


def test_page_with_a_text_edge_continues_the_item_at_the_hang() -> None:
    lines = tuple(
        _placed("goes on still", 64.0, 60 + n * _PITCH_PT, 1, text_edge=50.0)
        for n in range(2)
    )
    assert _over_a_break(lines)[1] == 2


def test_lines_before_the_marker_line_at_two_left_sides_take_the_text_edge() -> None:
    # Rule 6: the lines before the page's first marker line lie at 72 and
    # 80 pt, not within 3 pt of one left side, so the marker column is the
    # text edge, which the page lacks: the list ends.
    lines = (
        _placed("goes on still", 72.0, 60, 1),
        _placed("and still", 80.0, 74, 1),
        _placed("3. Third", 59.5, 88, 1),
    )
    assert _over_a_break(lines)[1] == 0


def test_line_after_a_hyphen_goes_on_with_the_item_wherever_it_lies() -> None:
    # Rule 2: inside a list, the hyphen rule holds.
    page = StreamPage(
        (
            _placed("1. First item cut by a hy-", 40.0, 100),
            _placed("phen at the column's edge", 40.0, 114),
            _placed("2. Second", 40.0, 128),
            _placed("goes on", 54.0, 142),
        )
    )
    found = list_items((page,), _PITCH_PT)
    assert _starts(found) == ("1.", "2.")
    assert found[0, 1] == ItemLine(None)


def test_closed_line_at_the_hang_ends_the_list() -> None:
    # A verse run's line, closed, at the hang of the item before.
    page = _numbered((("1. First", "goes on"), ("2. Second", "goes on")))
    verse = _placed("A verse line at the hang", 54.0, 156)
    found = list_items((StreamPage((*page.lines, verse), frozenset({4})),), _PITCH_PT)
    assert (0, 4) not in found


def test_marker_line_with_no_word_after_its_marker_starts_no_list() -> None:
    page = _numbered((("1.", "goes on"), ("2. Second", "goes on")))
    assert list_items((page,), _PITCH_PT) == frozendict()


def test_next_marker_of_another_form_is_no_next_item() -> None:
    page = _numbered((("1. First", "goes on"), ("2) Second", "goes on")))
    assert list_items((page,), _PITCH_PT) == frozendict()


def test_next_marker_more_than_3_pt_left_of_the_column_is_no_next_item() -> None:
    page = StreamPage(
        (
            _placed("1. First", 40.0, 100),
            _placed("goes on", 54.0, 114),
            _placed("2. Second", 30.0, 128),
            _placed("goes on", 44.0, 142),
        )
    )
    assert list_items((page,), _PITCH_PT) == frozendict()


def test_closed_page_between_two_items_ends_the_list() -> None:
    first = _numbered((("1. First", "goes on"),))
    contents = StreamPage((_placed("A contents line", 40.0, 100, 1),), frozenset({0}))
    second = StreamPage((_placed("2. Second", 40.0, 100, 2),))
    assert list_items((first, contents, second), _PITCH_PT) == frozendict()


# The blocks (spec section 29, "Blocks"), through make_blocks on lines.json
# values written here.

_NO_WORDS: frozenset[str] = frozenset()
_RIGHT_PT = 300.0


def _line(text: str, x0: float, top: float, x1: float | None = None) -> Line:
    """A line of `text` from `x0`, its words 5 pt a character, spread to
    end at `x1` when given."""
    parts = text.split(" ")
    natural = _CHAR_PT * (sum(len(part) for part in parts) + len(parts) - 1)
    gap = _CHAR_PT
    if x1 is not None and len(parts) > 1:
        gap += (x1 - x0 - natural) / (len(parts) - 1)
    words = []
    left = x0
    for part in parts:
        right = left + _CHAR_PT * len(part)
        words.append(Word(part, Box(left, top, right, top + _WORD_HEIGHT_PT), None))
        left = right + gap
    return Line(Box(x0, top, words[-1].box.x1, top + _WORD_HEIGHT_PT), tuple(words))


def _page(index: int, *lines: Line) -> PageLayout:
    box = Box(
        min(line.box.x0 for line in lines),
        min(line.box.top for line in lines),
        max(line.box.x1 for line in lines),
        max(line.box.bottom for line in lines),
    )
    return PageLayout(index, (Region(box, lines),), ())


def _haynes_lines() -> LinesFile:
    """Spec section 32's first unit test as lines.json: a lead-in paragraph
    ending "…stereotypes:", 2 pitches above six dash items, the fifth over
    the page break, and a paragraph flush at 59.3 pt 2 pitches below."""
    lead = (
        _line("The figures of the scientist in the stories are", 37.9, 60, _RIGHT_PT),
        _line("many, and they come back again and again, and", 37.9, 74, _RIGHT_PT),
        _line("are grouped around six recurrent stereotypes:", 37.9, 88, 260),
    )
    items: list[Line] = []
    top = 88 + 2 * _PITCH_PT
    for number in range(5):
        items.append(_line(f"—The item {number} starts here and", 37.9, top, _RIGHT_PT))
        items.append(_line("it goes on here to the end", 50.4, top + _PITCH_PT, 250))
        top += 2 * _PITCH_PT
    first = _page(0, *lead, *items)
    second = _page(
        1,
        *(
            _line(f"the fifth item goes on {n} on the", 72.0, 60 + n * _PITCH_PT, 322)
            for n in range(5)
        ),
        _line("—The last item starts here and", 59.5, 60 + 5 * _PITCH_PT, 322),
        _line("ends here.", 72.0, 60 + 6 * _PITCH_PT),
        *(
            _line(f"The paragraph after it {n} goes on", 59.3, 60 + n * _PITCH_PT, 322)
            for n in range(8, 12)
        ),
    )
    return LinesFile(source_pdf_sha256="0" * 64, rereads=(), pages=(first, second))


def _blocks(lines: LinesFile) -> BlocksFile:
    return make_blocks(lines, _NO_WORDS, workers=1)


def test_dash_list_in_haynes_geometry_gives_six_list_item_blocks() -> None:
    lines = _haynes_lines()
    blocks = _blocks(lines)
    assert tuple((block.kind, block.label) for block in blocks.blocks) == (
        (BlockKind.PARAGRAPH, None),
        *((BlockKind.LIST_ITEM, "—"),) * 6,
        (BlockKind.PARAGRAPH, None),
    )
    assert block_text(blocks.blocks[1]).startswith("The item 0 starts here")
    assert tuple(len(block.origin) for block in blocks.blocks[1:7]) == (
        1,
        1,
        1,
        1,
        2,
        1,
    )
    markers = tuple(
        change
        for change in blocks.word_changes
        if change.reason is ChangeReason.LIST_MARKER
    )
    assert len(markers) == 6
    assert (markers[0].before, markers[0].after) == (("—The",), ("—", "The"))
    check_stage(FidelityBoundary.STRUCTURE, lines, blocks)


def test_numbered_list_items_take_their_marker_as_label() -> None:
    body = (
        _line("A paragraph that leads in to the list of", 40, 60, _RIGHT_PT),
        _line("the five things it names here:", 40, 74, 200),
        _line("1. First thing of the list", 40, 88),
        _line("goes on here", 54, 102),
        _line("2. Second thing", 40, 116),
        _line("3. Third thing", 40, 130),
        _line("4. Fourth thing", 40, 144),
        _line("5. Fifth thing of the list", 40, 158),
        _line("goes on here.", 54, 172),
    )
    lines = LinesFile(source_pdf_sha256="0" * 64, rereads=(), pages=(_page(0, *body),))
    blocks = _blocks(lines)
    assert tuple(
        (block.label, block_text(block))
        for block in blocks.blocks
        if block.kind is BlockKind.LIST_ITEM
    ) == (
        ("1.", "First thing of the list goes on here"),
        ("2.", "Second thing"),
        ("3.", "Third thing"),
        ("4.", "Fourth thing"),
        ("5.", "Fifth thing of the list goes on here."),
    )
    check_stage(FidelityBoundary.STRUCTURE, lines, blocks)


# The excerpts (spec section 32, "Excerpt tests").

_EXPECTED = Path(__file__).parent / "fixtures" / "expected" / "lists_figures"


def _expected(name: str) -> dict[str, Any]:
    return json.loads((_EXPECTED / name).read_text(encoding="utf-8"))


def _lists_on(blocks: BlocksFile, page: int) -> list[list[dict[str, str | None]]]:
    """The list items that start on excerpt page `page`, a list from each
    item whose label is "1.", as the expected files write them."""
    lists: list[list[dict[str, str | None]]] = []
    for block in blocks.blocks:
        if block.kind is not BlockKind.LIST_ITEM or block.origin[0].page_index != page:
            continue
        if block.label == "1." or not lists:
            lists.append([])
        lists[-1].append({"label": block.label, "text": block_text(block)})
    return lists


@pytest.mark.parametrize("page", [5, 6, 7])
def test_domesday_lists_table_rows_are_the_numbered_lists_read_on_the_page(
    excerpt_books: frozendict[str, BookFolder], page: int
) -> None:
    blocks = read_blocks(excerpt_books["domesday_lists"].blocks_json)
    expected = _expected(f"domesday_lists_page{page}.json")["expected"]
    assert _lists_on(blocks, page) == expected["lists"]


def test_domesday_lists_enumerations_of_page_141_stay_blocks_of_their_own(
    excerpt_books: frozendict[str, BookFolder],
) -> None:
    blocks = read_blocks(excerpt_books["domesday_lists"].blocks_json)
    expected = _expected("domesday_lists_page1.json")["expected"]
    assert not any(block.kind is BlockKind.LIST_ITEM for block in blocks.blocks[:20])
    starting = tuple(
        (block.kind.value, " ".join(block_text(block).split(" ")[:3]))
        for block in blocks.blocks
        if block.origin[0].page_index == 1 and block_text(block).startswith("(")
    )
    assert starting == tuple(
        (expected["blocks_kind"], start) for start in expected["blocks_starting"]
    )


def test_kadesh_numbered_paragraphs_stay_paragraphs(
    excerpt_books: frozendict[str, BookFolder],
) -> None:
    # Excerpt pages 3 and 4 are the book's pages 11 and 12.
    blocks = read_blocks(excerpt_books["kadesh_8-17"].blocks_json)
    assert tuple(
        (block.kind.value, block_text(block)[:6])
        for block in blocks.blocks
        if block.origin[0].page_index in {3, 4}
    ) == (
        ("paragraph", "1. Of "),
        ("paragraph", "2. The"),
        ("paragraph", "3. The"),
    )


# The whole books (spec section 32, "Whole-book tests"): list items in
# Domesday's tables, at least 36 (the prototype found 40), and none in the
# five other public-domain books.
_LIST_ITEMS_AT_LEAST = {"domesdaybook00maituoft": 36}
_NO_LISTS = (
    "normansineuropea00hask",
    "earlyplantagenet01stub",
    "politicaltheorie00gieruoft",
    "catherinedemedic00mariuoft",
    "battleofkadeshst00breauoft",
)


@pytest.mark.whole_book
@pytest.mark.timeout(900)
@pytest.mark.parametrize("book", [*_LIST_ITEMS_AT_LEAST, *_NO_LISTS])
def test_whole_book_list_items(
    whole_book_run: Callable[[str], BookFolder], book: str
) -> None:
    blocks = read_blocks(whole_book_run(book).blocks_json)
    items = sum(block.kind is BlockKind.LIST_ITEM for block in blocks.blocks)
    if book in _LIST_ITEMS_AT_LEAST:
        assert items >= _LIST_ITEMS_AT_LEAST[book]
    else:
        assert items == 0


# Spec section 29, "The rules": the pages and runs whose lines the list
# rules take none of, in step 3.1.


def _parts_of(page_index: int, **fields: object) -> PageParts:
    """Page `page_index` holding two numbered items in its body stream."""
    lines = tuple(
        replace(line, page_index=page_index)
        for line in _numbered((("1. First", "goes on"), ("2. Second", "goes on"))).lines
    )
    return replace(
        PageParts(
            index=page_index,
            removals=(),
            page_numbers=(),
            body=lines,
            margin_notes=(),
            band_regions=(),
            band_blocks=(),
        ),
        **fields,
    )


def _list_pages(page: PageParts, section_pages: range = range(0)) -> frozenset[int]:
    roles = _line_roles((page,), (), frozenset(), section_pages, _PITCH_PT)
    return frozenset(page_index for page_index, _ in roles)


def test_list_on_an_index_page_the_endnote_section_or_in_a_run_is_none() -> None:
    plain = _parts_of(0)
    index = _parts_of(1, index_lines=plain.body[:1])
    run = _parts_of(2, runs=(BodyRun(start=0, end=4, kind=BlockKind.VERSE),))
    assert _list_pages(plain) == {0}
    assert _list_pages(index) == frozenset()
    assert _list_pages(_parts_of(3), range(3, 4)) == frozenset()
    assert _list_pages(run) == frozenset()
