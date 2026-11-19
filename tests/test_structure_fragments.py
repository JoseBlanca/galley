"""Tests of Stubbs' letter fragments (docs/specs/structure.md, section 35):
the pieces of a letter that the text layer gives as words of their own,
removed as `letter_fragment` in a book where they are common.

The unit tests' words are literals, the boxes of the first two copied from
the runs of the plan stray-text (Stubbs' page 24, Gierke's page 225). The
excerpt tests list each fragment of the four Stubbs excerpts as the task
4.1 session saw it on the page rendered at 250 dpi on 19 November 2026,
with the words around it as printed.
"""

from collections.abc import Callable

import pytest

from galley.book_folder import BookFolder
from galley.model import (
    BlocksFile,
    Box,
    Line,
    PageLayout,
    Region,
    RemovalReason,
    Word,
    block_text,
    read_blocks,
)
from galley.structure._fragments import (
    LetterFragments,
    fragment_numbers,
    letter_fragments,
    without_fragments,
)


def _word(
    text: str,
    x0: float,
    top: float,
    x1: float,
    bottom: float,
    confidence: float | None = None,
) -> Word:
    return Word(text, Box(x0, top, x1, bottom), confidence)


def _line(*words: Word) -> Line:
    return Line(
        Box(
            min(word.box.x0 for word in words),
            min(word.box.top for word in words),
            max(word.box.x1 for word in words),
            max(word.box.bottom for word in words),
        ),
        words,
    )


def _page(index: int, *lines: Line) -> PageLayout:
    return PageLayout(index, (Region(Box(0.0, 0.0, 400.0, 600.0), lines),), ())


# Stubbs' page 24: "Swabia, . and", the "." the dot of the "i" of "Swabia".
_SWABIA_LINE = _line(
    _word("nations,", 29.8302, 408.7682, 65.9542, 416.2940),
    _word("Saxony,", 74.2161, 407.5847, 111.0550, 416.3559),
    _word("Franconia,", 119.5005, 407.5121, 169.9926, 415.9275),
    _word("Swabia,", 176.6451, 407.0383, 212.5858, 415.5956),
    _word(".", 202.3422, 405.9557, 203.6005, 408.0528),
    _word("and", 220.8513, 405.9505, 238.2826, 415.6345),
)

# Gierke's page 225: the layer boxes two rows 3.7 pt apart as one line; "a"
# of the lower row lies inside "pluralitas" of the upper, and shares its
# top and bottom with "for" and "pars" of its own row.
_GIERKE_LINE = _line(
    _word("possible", 262.224, 268.877, 290.697, 277.877),
    _word("is", 265.104, 272.573, 271.215, 281.573),
    _word("good", 275.184, 272.573, 292.252, 281.573),
    _word("for", 299.232, 272.573, 309.057, 281.573),
    _word("pluralitas", 303.408, 268.877, 336.873, 277.877),
    _word("a", 314.208, 272.573, 317.147, 281.573),
    _word("pars", 321.120, 272.573, 336.929, 281.573),
)


def test_dot_inside_swabia_is_a_letter_fragment() -> None:
    assert fragment_numbers(_SWABIA_LINE) == (4,)


def test_word_of_a_row_boxed_over_a_word_of_another_row_is_not_a_fragment() -> None:
    assert fragment_numbers(_GIERKE_LINE) == ()


def test_word_read_by_tesseract_is_not_a_fragment() -> None:
    line = _line(
        _word("examined", 100.0, 200.0, 140.0, 210.0, 91.0),
        _word(".", 110.0, 200.5, 111.5, 202.5, 40.0),
    )

    assert fragment_numbers(line) == ()


@pytest.mark.parametrize(
    ("piece", "taken"),
    [
        # Three characters, or two letters: a word, not a piece of one.
        (_word("...", 110.0, 200.0, 113.0, 203.0), False),
        (_word("ri", 110.0, 200.0, 113.0, 203.0), False),
        (_word("r'", 110.0, 200.0, 113.0, 203.0), True),
        # Less than half of its width inside "upon".
        (_word("x", 128.0, 205.0, 134.0, 209.0), False),
        (_word("x", 128.0, 205.0, 132.0, 209.0), True),
        # Below the word, touching nothing of it.
        (_word("x", 110.0, 210.0, 113.0, 214.0), False),
        # 1.15 times as tall as "upon" and no more.
        (_word("J", 110.0, 199.0, 113.0, 210.5), True),
        (_word("J", 110.0, 199.0, 113.0, 210.6), False),
    ],
)
def test_piece_is_a_fragment_by_its_size_and_place_in_the_word(
    piece: Word, taken: bool
) -> None:
    # "upon" is 10 pt tall and spans x 100 to 130.
    line = _line(_word("upon", 100.0, 200.0, 130.0, 210.0), piece)

    assert (fragment_numbers(line) == (1,)) is taken


def test_piece_with_one_other_word_of_its_row_is_a_fragment_and_with_two_is_not() -> (
    None
):
    host = _word("great", 100.0, 200.0, 125.0, 210.0)
    piece = _word("°", 104.0, 207.0, 107.0, 211.0)
    neighbour = _word("pomp", 140.0, 207.05, 160.0, 211.15)
    other = _word("to", 170.0, 206.9, 180.0, 210.9)

    assert fragment_numbers(_line(host, piece, neighbour)) == (1,)
    assert fragment_numbers(_line(host, piece, neighbour, other)) == ()


def test_fragments_are_removed_on_a_page_of_a_book_that_has_them() -> None:
    page = _page(24, _SWABIA_LINE)

    result = without_fragments(page, frozenset(), LetterFragments.PRESENT, frozenset())

    assert [word.text for word in result.page.regions[0].lines[0].words] == [
        "nations,",
        "Saxony,",
        "Franconia,",
        "Swabia,",
        "and",
    ]
    assert result.page.regions[0].lines[0].box == _SWABIA_LINE.box
    assert [(r.page_index, r.text, r.reason, r.box) for r in result.removals] == [
        (
            24,
            ".",
            RemovalReason.LETTER_FRAGMENT,
            Box(202.3422, 405.9557, 203.6005, 408.0528),
        )
    ]


@pytest.mark.parametrize(
    ("fragments", "index_pages", "removed"),
    [
        # A book without letter fragments.
        (LetterFragments.ABSENT, frozenset(), frozenset()),
        # An index page, whose page numbers the scan's skew sets inside an
        # entry's word.
        (LetterFragments.PRESENT, frozenset({24}), frozenset()),
        # A line another rule removed keeps its words for that removal.
        (LetterFragments.PRESENT, frozenset(), frozenset({(0, 0)})),
    ],
)
def test_fragment_is_kept_without_fragments_in_the_book_on_an_index_page_or_a_removed_line(
    fragments: LetterFragments,
    index_pages: frozenset[int],
    removed: frozenset[tuple[int, int]],
) -> None:
    page = _page(24, _SWABIA_LINE)

    result = without_fragments(page, removed, fragments, index_pages)

    assert result.page == page
    assert result.removals == ()


def _plain_line(top: float) -> Line:
    return _line(
        _word("Stephen", 100.0, top, 140.0, top + 10.0),
        _word("and", 145.0, top, 160.0, top + 10.0),
    )


def _book_page(index: int, *, lines: int = 5, fragment: bool = False) -> PageLayout:
    plain = tuple(_plain_line(100.0 + 14.0 * number) for number in range(lines))
    return _page(index, *((_SWABIA_LINE, *plain[1:]) if fragment else plain))


@pytest.mark.parametrize(
    ("with_a_fragment", "found"),
    [(3, LetterFragments.PRESENT), (2, LetterFragments.ABSENT)],
)
def test_book_has_letter_fragments_when_at_least_0_15_of_its_pages_have_one(
    with_a_fragment: int, found: LetterFragments
) -> None:
    pages = tuple(
        _book_page(index, fragment=index < with_a_fragment) for index in range(20)
    )

    assert letter_fragments(pages, frozenset()) is found


def test_share_leaves_out_index_pages_and_pages_of_fewer_than_5_lines() -> None:
    # 2 of 10 counted pages have a fragment, 0.2; counted with the 4 short
    # pages and the 6 index pages, it would be 2 of 20, 0.1.
    pages = (
        *(_book_page(index, fragment=index < 2) for index in range(10)),
        *(_book_page(index, lines=4) for index in range(10, 14)),
        *(_book_page(index) for index in range(14, 20)),
    )

    assert letter_fragments(pages, frozenset(range(14, 20))) is LetterFragments.PRESENT
    assert letter_fragments(pages, frozenset()) is LetterFragments.ABSENT


def test_book_without_a_page_of_5_lines_has_no_letter_fragments() -> None:
    pages = (_book_page(0, lines=2, fragment=True),)

    assert letter_fragments(pages, frozenset()) is LetterFragments.ABSENT


# The fragments of the Stubbs excerpts, by excerpt: the page in the
# excerpt, the fragment's text, and the words around it as printed, which
# a block of the excerpt holds once the fragment is gone.
STUBBS_FRAGMENTS = {
    "stubbs_51_56-64": (
        (0, ".", "of Simon de Montfort,"),  # the dot of the "i"
        (0, ",", "scarcely named"),  # a piece of the "d"
        (1, "r", "chaplains, and a"),  # the tail of the "p"
        (2, "x", "acted upon this shameless"),
        (3, "1", "man created for the"),  # the stem of the "d"
        (4, ",", "far-seeing king who recognized"),
        (8, "r", "his powerful kinsman,"),
        (8, "'", "kinsman, who,"),  # the tail of the comma
        (8, "\\", "now busily employed in"),
        (9, "°", "and setting at work"),
    ),
    "stubbs_cut_in": (
        (0, "v", "epoch which in"),
        (0, "i", "of Stephen to the"),  # the stem of the "h"
        (2, "J", "the treasury he next"),
        (3, ",", "William the Good, as"),
    ),
    "stubbs_heads": (
        (1, "°", "country during this epoch"),
        (1, ",", "men and great causes"),
        (2, ",", "six months, save that"),
        (4, "J", "held, early in"),
        (9, "'", "issued one, but had"),
    ),
    "stubbs_summaries_index": ((1, "J", "that they were one"),),
}


def _texts(blocks: BlocksFile) -> tuple[str, ...]:
    return (
        *(block_text(block) for block in blocks.blocks),
        *(block_text(block) for note in blocks.notes for block in note.blocks),
    )


@pytest.mark.pandoc
@pytest.mark.tesseract
@pytest.mark.parametrize("excerpt", sorted(STUBBS_FRAGMENTS))
def test_stubbs_excerpt_letter_fragments_are_removed_and_their_words_read_whole(
    excerpt_books: frozendict[str, BookFolder], excerpt: str
) -> None:
    blocks = read_blocks(excerpt_books[excerpt].blocks_json)
    expected = STUBBS_FRAGMENTS[excerpt]

    removed = [
        (removal.page_index, removal.text)
        for removal in blocks.removals
        if removal.reason is RemovalReason.LETTER_FRAGMENT
    ]

    assert removed == [(page, text) for page, text, _ in expected]
    texts = _texts(blocks)
    assert [
        words for _, _, words in expected if not any(words in t for t in texts)
    ] == []


@pytest.mark.pandoc
@pytest.mark.tesseract
def test_no_letter_fragment_is_removed_in_an_excerpt_of_another_book(
    excerpt_books: frozendict[str, BookFolder],
) -> None:
    removed = {
        name: sum(
            1
            for removal in read_blocks(folder.blocks_json).removals
            if removal.reason is RemovalReason.LETTER_FRAGMENT
        )
        for name, folder in excerpt_books.items()
        if not name.startswith("stubbs")
    }

    assert {name: count for name, count in removed.items() if count} == {}


# Whole books (spec section 35, "How it is verified"): Stubbs' fragments
# removed, at least 240 of the 251 the rule took on the runs of the plan
# stray-text, and none in the other books.
_STUBBS_FRAGMENTS_AT_LEAST = 240


@pytest.mark.whole_book
@pytest.mark.thread_unsafe
@pytest.mark.timeout(900)
def test_whole_book_stubbs_letter_fragments_are_removed(
    whole_book_run: Callable[[str], BookFolder],
) -> None:
    blocks = read_blocks(whole_book_run("earlyplantagenet01stub").blocks_json)

    removed = sum(
        1
        for removal in blocks.removals
        if removal.reason is RemovalReason.LETTER_FRAGMENT
    )

    assert removed >= _STUBBS_FRAGMENTS_AT_LEAST


@pytest.mark.whole_book
@pytest.mark.thread_unsafe
@pytest.mark.timeout(900)
@pytest.mark.parametrize(
    "book",
    [
        "normansineuropea00hask",
        "domesdaybook00maituoft",
        "battleofkadeshst00breauoft",
        "politicaltheorie00gieruoft",
    ],
)
def test_whole_book_other_than_stubbs_has_no_letter_fragment_removed(
    whole_book_run: Callable[[str], BookFolder], book: str
) -> None:
    blocks = read_blocks(whole_book_run(book).blocks_json)

    assert not any(
        removal.reason is RemovalReason.LETTER_FRAGMENT for removal in blocks.removals
    )


@pytest.mark.whole_book
@pytest.mark.thread_unsafe
@pytest.mark.timeout(900)
@pytest.mark.parametrize("book", ["turney", "haynes"])
def test_whole_book_owner_book_has_no_letter_fragment_removed(
    owner_book_run: Callable[[str], BlocksFile], book: str
) -> None:
    # The owner's books are copyrighted: the test counts and quotes nothing.
    blocks = owner_book_run(book)

    assert not any(
        removal.reason is RemovalReason.LETTER_FRAGMENT for removal in blocks.removals
    )
