"""What each region of a page is (spec section 2): the head line, body,
margin or band. lines.json does not say; structure decides from where each
region lies and the height of its words."""

import statistics
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
# 0.85 of the body word height (measured, layout section 2), or at most 0.82
# of the page's median line height (layout's "Small against the page":
# Gierke's introduction notes, 8 pt against its 10 to 11 pt body and the
# book's 9.0 pt; at 0.85 the last rows of two printed contents were small).
_SMALL_WORD_SHARE = 0.85
_SMALL_PAGE_SHARE = 0.82
# Spec section 2, from layout section 3, step 4, "A page whose notes
# outnumber its text": the page's median line height is taken on its lines
# of at least 0.9 of the body word height when they are a quarter of its
# lines (Gierke's page 50, 13 lines of text above 25 of notes).
_FULL_SIZE_LINE_SHARE = 0.9
_FULL_SIZE_LINES_LEAST_SHARE = 0.25
# Spec section 2: a band region may reach 2 pt into the region above it;
# Domesday's note "1 See above, p. 359." (page 535) reaches 0.8 pt into the
# text above it, and was a margin region.
_BELOW_SLACK_PT = 2.0
# Spec section 2, from layout section 3, step 4, "A note of one line boxed
# as tall as the body": a one-line note region's first word.
_ONE_LINE_NOTE_MARKER = "1"
# Spec section 3, "A short region beside the head": one line of at most 5
# characters (a roman number up to "lxxiv", or a speck) whose top lies
# within 4 pt of the head's (Turney's numbers 0 to 0.8 pt, Gierke's 0 to
# 3.9 pt, measured on 17 November 2026).
_BESIDE_MAX_CHARACTERS = 5
_BESIDE_TOP_PT = 4.0
# Spec section 2: the head line lies above every other region, which may
# reach 2 pt into it; Stubbs' "MAPS." (page 17), boxed 18 pt tall, reaches
# 1 pt into the region below it.
_HEAD_OVERLAP_PT = 2.0


class Small(StrEnum):
    """Whether a region is set in small type: its median word height at
    most `_SMALL_WORD_SHARE` of the body word height, or at most
    `_SMALL_PAGE_SHARE` of the page's median line height."""

    SMALL = "small"
    NOT_SMALL = "not small"


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


def _lies_below(region: Region, other: Region) -> bool:
    """Whether `region`'s top lies at or below `other`'s bottom, or above
    it by at most `_BELOW_SLACK_PT` (spec section 2)."""
    return region.box.top >= other.box.bottom - _BELOW_SLACK_PT


def _is_margin(
    region: Region, widest: Region, others: tuple[Region, ...], *, small: Small
) -> bool:
    """Whether `region` is a margin region (spec section 2): narrower than
    a quarter of `widest`, and wholly left or right of it, or overlapping
    vertically a wider region of `others`, unless, in small type
    (`small`), it lies below that region."""
    if _width(region) >= _MARGIN_WIDTH_SHARE * _width(widest):
        return False
    beside = region.box.x1 <= widest.box.x0 or region.box.x0 >= widest.box.x1
    return beside or any(
        _width(other) > _width(region)
        and _overlap_vertically(region, other)
        and not (small is Small.SMALL and _lies_below(region, other))
        for other in others
        if other is not region
    )


def _page_line_height(
    regions: tuple[Region, ...], widest: Region, body_word_height: float
) -> float:
    """The page's median line height (spec section 2), in points: the median,
    over the lines of `regions` not narrower than a quarter of `widest`, of
    each line's median word height, taken over those of at least
    `_FULL_SIZE_LINE_SHARE` of `body_word_height` when they are
    `_FULL_SIZE_LINES_LEAST_SHARE` of the lines or more; 0 without such a
    line."""
    heights = tuple(
        median_word_height(line.words)
        for region in regions
        if _width(region) >= _MARGIN_WIDTH_SHARE * _width(widest)
        for line in region.lines
    )
    if not heights:
        return 0.0
    full_size = tuple(
        height
        for height in heights
        if height >= _FULL_SIZE_LINE_SHARE * body_word_height
    )
    if len(full_size) >= _FULL_SIZE_LINES_LEAST_SHARE * len(heights):
        return statistics.median(full_size)
    return statistics.median(heights)


def _is_one_line_note(
    number: int,
    page: PageLayout,
    numbered: tuple[tuple[int, Region], ...],
    margins: tuple[bool, ...],
) -> bool:
    """Whether region `number` of `page` is a one-line note region (spec
    section 2): the page's last region, one line whose first word is "1" and
    whose second starts with a capital, lying below every other region of
    `numbered` (the regions out of the head line) that is not a margin
    region, as `margins` says, and there is one."""
    region = page.regions[number]
    if number != len(page.regions) - 1 or len(region.lines) != 1:
        return False
    texts = tuple(word.text for word in region.lines[0].words)
    above = tuple(
        other
        for (other_number, other), margin in zip(numbered, margins, strict=True)
        if other_number != number and not margin
    )
    return (
        texts[:1] == (_ONE_LINE_NOTE_MARKER,)
        and texts[1:2] != ()
        and texts[1][:1].isupper()
        and bool(above)
        and all(_lies_below(region, other) for other in above)
    )


def _kind(
    *, one_line_note: bool, margin: bool, small: Small, below_large: bool
) -> RegionKind:
    """The kind of a region out of the head line (spec section 2), by the
    rules in this order: a one-line note region is a band region, whatever
    it is by the others; else a margin region is a margin region; else a
    region in small type whose top lies at or below the bottom of a region
    that is neither in small type nor a margin region nor a one-line note
    (2 pt slack), `below_large`, is a band region; else a body region."""
    if one_line_note:
        return RegionKind.BAND
    if margin:
        return RegionKind.MARGIN
    if small is Small.SMALL and below_large:
        return RegionKind.BAND
    return RegionKind.BODY


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
    small_limit = max(
        _SMALL_WORD_SHARE * body_word_height,
        _SMALL_PAGE_SHARE * _page_line_height(others, widest, body_word_height),
    )
    heights = tuple(median_word_height(region_words(region)) for region in others)
    margins = tuple(
        _is_margin(
            region,
            widest,
            others,
            small=Small.SMALL if height <= small_limit else Small.NOT_SMALL,
        )
        for region, height in zip(others, heights, strict=True)
    )
    one_line_note = tuple(
        _is_one_line_note(number, page, numbered, margins) for number, _ in numbered
    )
    large_bottoms = tuple(
        region.box.bottom
        for region, margin, height, note in zip(
            others, margins, heights, one_line_note, strict=True
        )
        if not margin and not note and height > small_limit
    )
    other_kinds = {
        number: _kind(
            one_line_note=note,
            margin=margin,
            small=Small.SMALL if height <= small_limit else Small.NOT_SMALL,
            below_large=any(
                region.box.top >= bottom - _BELOW_SLACK_PT for bottom in large_bottoms
            ),
        )
        for (number, region), margin, height, note in zip(
            numbered, margins, heights, one_line_note, strict=True
        )
    }
    return tuple(
        other_kinds.get(number, head_kind) for number in range(len(page.regions))
    )
