"""What each region of a page is (spec section 2): the head line, body,
margin or band. lines.json does not say; structure decides from where each
region lies and the height of its words."""

from enum import StrEnum

from galley.model import PageLayout, Region
from galley.structure._measures import (
    line_has_letter_or_digit,
    median_word_height,
    region_words,
)

# Spec section 2: a margin region is narrower than a quarter of the widest.
_MARGIN_WIDTH_SHARE = 0.25
# Spec section 2, from layout section 3, step 4: a band's words are at most
# 0.85 of the body word height (measured, layout section 2).
_SMALL_WORD_SHARE = 0.85


class RegionKind(StrEnum):
    """What a region of a page is. A head line is a running head, or else
    the first body region (section 3)."""

    RUNNING_HEAD = "running_head"
    BODY = "body"
    MARGIN = "margin"
    BAND = "band"


def head_line(page: PageLayout) -> Region | None:
    """The page's head line: its first region, when that lies wholly above
    every other region and holds one line with a letter or a digit, with
    only lines of marks above it; None otherwise."""
    if not page.regions:
        return None
    first, *others = page.regions
    if any(other.box.top < first.box.bottom for other in others):
        return None
    with_text = tuple(
        number
        for number, line in enumerate(first.lines)
        if line_has_letter_or_digit(line)
    )
    if with_text != (len(first.lines) - 1,):
        return None
    return first


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
    has_head_line = head_line(page) is not None
    head_kinds = (
        ()
        if not has_head_line
        else (RegionKind.RUNNING_HEAD,)
        if page.index in running_heads
        else (RegionKind.BODY,)
    )
    others = page.regions[1:] if has_head_line else page.regions
    if not others:
        return head_kinds
    widest = max(others, key=_width)
    margins = tuple(_is_margin(region, widest, others) for region in others)
    small_limit = _SMALL_WORD_SHARE * body_word_height
    heights = tuple(median_word_height(region_words(region)) for region in others)
    large_bottoms = tuple(
        region.box.bottom
        for region, margin, height in zip(others, margins, heights, strict=True)
        if not margin and height > small_limit
    )
    kinds = tuple(
        RegionKind.MARGIN
        if margin
        else RegionKind.BAND
        if height <= small_limit
        and any(region.box.top >= bottom for bottom in large_bottoms)
        else RegionKind.BODY
        for region, margin, height in zip(others, margins, heights, strict=True)
    )
    return head_kinds + kinds
