"""What each region of a page is (spec section 2): the head line, body,
margin or band. lines.json does not say; structure decides from where each
region lies and the height of its words."""

from dataclasses import dataclass
from enum import StrEnum

from galley.body_measures import median_word_height
from galley.model import Line, PageLayout, Region
from galley.structure._measures import (
    line_has_letter_or_digit,
    region_words,
    words_box,
)

# Spec section 2: a margin region is narrower than a quarter of the widest.
_MARGIN_WIDTH_SHARE = 0.25
# Spec section 2, from layout section 3, step 4: a band's words are at most
# 0.85 of the body word height (measured, layout section 2).
_SMALL_WORD_SHARE = 0.85
# Spec section 3, "A short region beside the head": one line of at most 5
# characters (a roman number up to "lxxiv", or a speck) whose top lies
# within 4 pt of the head's (Turney's numbers 0 to 0.8 pt, Gierke's 0 to
# 3.9 pt, measured on 17 November 2026).
_BESIDE_MAX_CHARACTERS = 5
# Spec section 2: the head line lies above every other region, which may
# reach 2 pt into it; Stubbs' "MAPS." (page 17), boxed 18 pt tall, reaches
# 1 pt into the region below it.
_HEAD_OVERLAP_PT = 2.0
_BESIDE_TOP_PT = 4.0


class RegionKind(StrEnum):
    """What a region of a page is. A head line is a running head, or else
    the first body region (section 3)."""

    RUNNING_HEAD = "running_head"
    BODY = "body"
    MARGIN = "margin"
    BAND = "band"


@dataclass(frozen=True, slots=True)
class HeadLine:
    """A page's head line (spec section 2): its first region, the numbers
    of the regions beside it, and `line`, the words of the first region's
    last line and of the regions beside it, left to right, as one line."""

    region: Region
    beside: tuple[int, ...]
    line: Line

    @property
    def region_numbers(self) -> frozenset[int]:
        """The numbers of the regions that make the head line: 0 and those
        beside it."""
        return frozenset({0, *self.beside})


def _is_beside(region: Region, first: Region) -> bool:
    """Whether `region` lies beside the head line of `first`, the page's
    first region (spec section 3, "A short region beside the head"): one
    line of at most 5 characters, spaces left out, whose top lies within 4
    pt of the top of `first`'s last line, wholly left or right of `first`."""
    if len(region.lines) != 1:
        return False
    (line,) = region.lines
    characters = sum(len(word.text) for word in line.words)
    return (
        characters <= _BESIDE_MAX_CHARACTERS
        and abs(line.box.top - first.lines[-1].box.top) <= _BESIDE_TOP_PT
        and (region.box.x1 <= first.box.x0 or region.box.x0 >= first.box.x1)
    )


def head_line(page: PageLayout) -> HeadLine | None:
    """The page's head line: its first region, with the regions beside it,
    when together they lie wholly above every other region and the first
    holds one line with a letter or a digit, with only lines of marks above
    it; None otherwise."""
    if not page.regions:
        return None
    first = page.regions[0]
    with_text = tuple(
        number
        for number, line in enumerate(first.lines)
        if line_has_letter_or_digit(line)
    )
    if with_text != (len(first.lines) - 1,):
        return None
    beside = tuple(
        number
        for number, region in enumerate(page.regions[1:], start=1)
        if _is_beside(region, first)
    )
    head_bottom = max(page.regions[number].box.bottom for number in (0, *beside))
    if any(
        region.box.top < head_bottom - _HEAD_OVERLAP_PT
        for number, region in enumerate(page.regions)
        if number != 0 and number not in beside
    ):
        return None
    words = sorted(
        (
            *first.lines[-1].words,
            *(
                word
                for number in beside
                for word in page.regions[number].lines[0].words
            ),
        ),
        key=lambda word: word.box.x0,
    )
    return HeadLine(first, beside, Line(words_box(words), tuple(words)))


def _width(region: Region) -> float:
    return region.box.x1 - region.box.x0


def _overlap_vertically(region: Region, other: Region) -> bool:
    return region.box.top < other.box.bottom and other.box.top < region.box.bottom


def _is_margin(region: Region, widest: Region, others: tuple[Region, ...]) -> bool:
    if _width(region) >= _MARGIN_WIDTH_SHARE * _width(widest):
        return False
    beside = region.box.x1 <= widest.box.x0 or region.box.x0 >= widest.box.x1
    return beside or any(
        _width(other) > _width(region) and _overlap_vertically(region, other)
        for other in others
        if other is not region
    )


def region_kinds(
    page: PageLayout, body_word_height: float, running_heads: frozenset[int]
) -> tuple[RegionKind, ...]:
    """The kind of each region of `page`, in the order of its regions
    (spec section 2). `body_word_height` is the book's, in points;
    `running_heads` the pages whose head line is a running head."""
    head = head_line(page)
    running = head is not None and page.index in running_heads
    # The head line's regions are left out of the rules below: all of them
    # when it is a running head, else its first region, a body region.
    head_numbers = (
        frozenset()
        if head is None
        else head.region_numbers
        if running
        else frozenset({0})
    )
    head_kind = RegionKind.RUNNING_HEAD if running else RegionKind.BODY
    numbered = tuple(
        (number, region)
        for number, region in enumerate(page.regions)
        if number not in head_numbers
    )
    others = tuple(region for _, region in numbered)
    if not others:
        return tuple(head_kind for _ in page.regions)
    widest = max(others, key=_width)
    margins = tuple(_is_margin(region, widest, others) for region in others)
    small_limit = _SMALL_WORD_SHARE * body_word_height
    heights = tuple(median_word_height(region_words(region)) for region in others)
    large_bottoms = tuple(
        region.box.bottom
        for region, margin, height in zip(others, margins, heights, strict=True)
        if not margin and height > small_limit
    )
    other_kinds = {
        number: RegionKind.MARGIN
        if margin
        else RegionKind.BAND
        if height <= small_limit
        and any(region.box.top >= bottom for bottom in large_bottoms)
        else RegionKind.BODY
        for (number, region), margin, height in zip(
            numbered, margins, heights, strict=True
        )
    }
    return tuple(
        other_kinds.get(number, head_kind) for number in range(len(page.regions))
    )
