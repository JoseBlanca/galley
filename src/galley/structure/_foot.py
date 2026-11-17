"""The foot of a page (spec section 4): its lowest line, the body column it
is measured against, and the forms of a page number at the foot."""

from galley.model import Line, PageLayout, Word
from galley.structure._measures import (
    Edges,
    is_page_number_form,
    letters,
    middle,
    region_edges,
)
from galley.structure._regions import RegionKind

# Spec section 4: a page number at the foot, and the page number of a
# signature line, lie within 0.15 of the column's width of its middle.
_CENTRED_SHARE = 0.15
# Spec section 4: "(49)", and Mariéjol's OCR forms "U9)", "{2)", "(31J".
_OPENING_BRACKETS = ("(", "[", "{", "U")
_CLOSING_BRACKETS = (")", "]", "}", "J")
_BRACKETED_MAX_CHARACTERS = 4
_FOOT_NUMBER_MAX_WORDS = 2

type LinePlace = tuple[int, int]
"""A line of a page, as (region number, line number), both from 0."""


def body_column(page: PageLayout, kinds: tuple[RegionKind, ...]) -> Edges | None:
    """The page's body column (spec section 1): from the leftmost left edge
    to the rightmost right edge of its body regions, whose `kinds` are
    given in the order of the regions; None when the page has none."""
    body_edges = tuple(
        region_edges(region)
        for region, kind in zip(page.regions, kinds, strict=True)
        if kind is RegionKind.BODY
    )
    if not body_edges:
        return None
    return Edges(
        min(edges.left for edges in body_edges),
        max(edges.right for edges in body_edges),
    )


def lowest_line(page: PageLayout, removed: frozenset[LinePlace]) -> LinePlace | None:
    """The line of any region whose bottom is lowest, the first in the
    page's order on a tie, leaving out the lines `removed`; None when no
    line is left."""
    lowest: LinePlace | None = None
    lowest_bottom = 0.0
    for region_number, region in enumerate(page.regions):
        for line_number, line in enumerate(region.lines):
            place = (region_number, line_number)
            if place in removed:
                continue
            if lowest is None or line.box.bottom > lowest_bottom:
                lowest, lowest_bottom = place, line.box.bottom
    return lowest


def line_at(page: PageLayout, place: LinePlace) -> Line:
    region_number, line_number = place
    return page.regions[region_number].lines[line_number]


def is_bracketed_number(text: str) -> bool:
    """Whether `text` is a page number in brackets (spec section 4): an
    opening "(", "[", "{" or "U", 1 to 4 letters and digits with at least
    one digit, and a closing ")", "]", "}" or "J", at most one of the two
    brackets missing."""
    for opening in ("", *_OPENING_BRACKETS):
        for closing in ("", *_CLOSING_BRACKETS):
            if not opening and not closing:
                continue
            if not (text.startswith(opening) and text.endswith(closing)):
                continue
            inner = text[len(opening) : len(text) - len(closing)]
            if (
                1 <= len(inner) <= _BRACKETED_MAX_CHARACTERS
                and all(character.isalnum() for character in inner)
                and any(character.isdigit() for character in inner)
            ):
                return True
    return False


def is_centred(box_middle: float, column: Edges) -> bool:
    return abs(box_middle - column.middle) <= _CENTRED_SHARE * column.width


def is_foot_page_number(line: Line, column: Edges) -> bool:
    """Whether a lowest line is a page number at the foot (spec section 4):
    one or two words, centred on the column, whose text joined without the
    space is a page-number form or a page number in brackets."""
    if not 1 <= len(line.words) <= _FOOT_NUMBER_MAX_WORDS:
        return False
    text = "".join(word.text for word in line.words)
    return is_centred(middle(line.box), column) and (
        is_page_number_form(text) or is_bracketed_number(text)
    )


def signature_page_number(line: Line, column: Edges) -> int | None:
    """The position, in a lowest line of more than two words, of its first
    word that is a page number in brackets centred on the column; None
    when it has none (spec section 4)."""
    if len(line.words) <= _FOOT_NUMBER_MAX_WORDS:
        return None
    return next(
        (
            position
            for position, word in enumerate(line.words)
            if is_bracketed_number(word.text) and is_centred(middle(word.box), column)
        ),
        None,
    )


def signature_letters(words: tuple[Word, ...], position: int) -> str:
    """The letters of the words left of the page number at `position`."""
    return letters("".join(word.text for word in words[:position]))


def running_head_lines(
    page: PageLayout, kinds: tuple[RegionKind, ...]
) -> frozenset[LinePlace]:
    """The lines of the page's running head, with the marks above it."""
    return frozenset(
        (region_number, line_number)
        for region_number, (region, kind) in enumerate(
            zip(page.regions, kinds, strict=True)
        )
        if kind is RegionKind.RUNNING_HEAD
        for line_number in range(len(region.lines))
    )


def signature_candidate(page: PageLayout, kinds: tuple[RegionKind, ...]) -> str | None:
    """The letters left of the page number of the page's lowest line, once
    the running head is removed, when that line could be a signature line
    (more than two words, one a centred page number in brackets); None
    otherwise. `kinds` are those of the page's regions, in their order."""
    column = body_column(page, kinds)
    if column is None:
        return None
    place = lowest_line(page, running_head_lines(page, kinds))
    if place is None:
        return None
    line = line_at(page, place)
    position = signature_page_number(line, column)
    if position is None:
        return None
    return signature_letters(line.words, position)


def line_below_head(page: PageLayout, head: frozenset[int]) -> LinePlace | None:
    """The topmost line of the page's regions but those of `head`, the
    region numbers of its head line, the first in their order on a tie:
    the line below a head line (spec section 3); None when there is
    none."""
    below: LinePlace | None = None
    below_top = 0.0
    for region_number, region in enumerate(page.regions):
        if region_number in head:
            continue
        for line_number, line in enumerate(region.lines):
            if below is None or line.box.top < below_top:
                below, below_top = (region_number, line_number), line.box.top
    return below
