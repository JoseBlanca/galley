"""What structure removes from a page (spec sections 3 and 4): the running
head, its page number and the stray marks above it; the page number at the
foot, the signature line and the printer's signature mark."""

import bisect
import re
from dataclasses import dataclass

from galley.model import (
    Line,
    PageLayout,
    PageNumber,
    PageNumberPosition,
    Removal,
    RemovalReason,
)
from galley.structure._foot import (
    LinePlace,
    body_column,
    is_foot_page_number,
    line_at,
    line_below_head,
    lowest_line,
    running_head_lines,
    signature_page_number,
)
from galley.structure._measures import (
    Edges,
    arabic_value,
    line_has_letter_or_digit,
    middle,
    words_removal,
    words_text,
)
from galley.structure._regions import RegionKind, head_line
from galley.structure._survey import BookSurvey, head_page_number


@dataclass(frozen=True, slots=True)
class LineRemovals:
    """What was removed from a page's lines: the records, the page numbers,
    and the removed lines, as (region number, line number) on the page."""

    removals: tuple[Removal, ...]
    page_numbers: tuple[PageNumber, ...]
    lines: frozenset[LinePlace]


_NOTHING_REMOVED = LineRemovals((), (), frozenset())

# Spec section 4: a printer's signature mark has at most 3 words and 6
# letters and digits, and its middle at least 0.3 of the column's width
# right of the column's left edge (the research's lie from 0.42 to 0.83 of
# the page width; a note's last line starts at the left edge).
_SIGNATURE_MARK_MAX_WORDS = 3
_SIGNATURE_MARK_MAX_CHARACTERS = 6
_SIGNATURE_MARK_FROM_LEFT_SHARE = 0.3
# Spec section 4: digits around a dash or a space, "4—2", "12 2".
_DIGITS_AROUND_A_DASH_OR_SPACE = re.compile(r"[0-9]+ ?[-–—] ?[0-9]+|[0-9]+ [0-9]+")
# Spec section 4: a signature mark without a digit, "M. c", is two words,
# the first a capital and a full stop, the second starting at least half
# the column's width right of the first's left side. Half is chosen, not
# measured: the one gap measured, in Gierke's introduction signed with
# letters, is 256 pt in a column of 297, 0.86 of it, on page index 38,
# where the OCR boxed "M." 128 pt wide.
_SIGNATURE_INITIAL = re.compile(r"[A-Z]\.")
_SIGNATURE_SPREAD_WORDS = 2
_SIGNATURE_GAP_SHARE = 0.5
# Spec section 4: a signature mark beside the lowest line lies less than a
# pitch above it and 2 pitches or more below its region's line before it.
# The 2 pitches are chosen, not measured, between the two gaps measured on
# 19 November 2026: on Domesday's page index 428, "26—2" lies 2.9 pitches
# below "Norfolk" (and 5.2 pt above the table's "[0", which the text layer
# boxes at the foot); the last lines of an index's other column, on
# Stubbs' page index 315 and Haskins' 268, lie 0.7 pitch below the lines
# before them and are not set apart.
_SET_APART_PITCHES = 2.0


def _running_head_removals(
    page_index: int, line: Line, survey: BookSurvey
) -> tuple[tuple[Removal, ...], tuple[PageNumber, ...]]:
    """A running head's line removed: its page number as `page_number`, the
    rest as `running_head`, in the order of the line."""
    words = line.words
    number = head_page_number(
        page_index, line, survey.first_arabic_page, survey.head_page_offset
    )
    if number is None:
        return (words_removal(page_index, words, RemovalReason.RUNNING_HEAD),), ()
    number_words = words[number.first : number.last + 1]
    rest = words[: number.first] + words[number.last + 1 :]
    number_removal = words_removal(page_index, number_words, RemovalReason.PAGE_NUMBER)
    rest_removals = (
        (words_removal(page_index, rest, RemovalReason.RUNNING_HEAD),) if rest else ()
    )
    in_line_order = (
        (number_removal, *rest_removals)
        if number.first == 0
        else (*rest_removals, number_removal)
    )
    return in_line_order, (
        PageNumber(page_index, number.text, PageNumberPosition.HEAD),
    )


@dataclass(frozen=True, slots=True)
class _RunningHead:
    """The line section 3 makes a page's running head, and the places of
    the lines it is made of: the text line of the head line and the lines
    of the regions beside it, or the line below a speck."""

    line: Line
    places: frozenset[LinePlace]


def _running_head(page: PageLayout, survey: BookSurvey) -> _RunningHead | None:
    """The page's running head, None when it has none."""
    head = head_line(page)
    if page.index in survey.running_heads and head is not None:
        return _RunningHead(
            head.line,
            frozenset(
                {
                    (0, len(head.region.lines) - 1),
                    *((number, 0) for number in head.beside),
                }
            ),
        )
    if page.index in survey.heads_below_specks:
        assert head is not None, "the survey found a speck as the head line"
        below = line_below_head(page, head.region_numbers)
        assert below is not None, "the survey found a line below the speck"
        return _RunningHead(line_at(page, below), frozenset({below}))
    return None


def running_head_line(page: PageLayout, survey: BookSurvey) -> Line | None:
    """The line that section 3 makes the page's running head: the words of
    its head line, or the line below a speck; None when the page has
    none."""
    head = _running_head(page, survey)
    return None if head is None else head.line


def head_removals(page: PageLayout, survey: BookSurvey) -> LineRemovals:
    """The removals of a running head (spec section 3): a line of marks
    above it as `stray_mark`, its page number as `page_number` with a
    `head` page number, and the rest of its line as `running_head`. When
    the head line is a speck and the line below it the running head, that
    line is removed so, and the speck stays. A page with no running head
    loses nothing."""
    head = _running_head(page, survey)
    if head is None:
        return _NOTHING_REMOVED
    mark_places = tuple(
        (0, number)
        for number, line in enumerate(page.regions[0].lines)
        if not line_has_letter_or_digit(line)
    )
    strays = tuple(
        words_removal(page.index, line_at(page, place).words, RemovalReason.STRAY_MARK)
        for place in mark_places
    )
    removals, page_numbers = _running_head_removals(page.index, head.line, survey)
    return LineRemovals(
        strays + removals, page_numbers, frozenset(mark_places) | head.places
    )


def _is_spread_signature(line: Line, column: Edges) -> bool:
    """Whether a line is two words, the first a capital and a full stop
    ("M."), the second starting at least half of `column`'s width right of
    the first's left side (spec section 4)."""
    words = sorted(line.words, key=lambda word: word.box.x0)
    return (
        len(words) == _SIGNATURE_SPREAD_WORDS
        and _SIGNATURE_INITIAL.fullmatch(words[0].text) is not None
        and words[1].box.x0 - words[0].box.x0 >= _SIGNATURE_GAP_SHARE * column.width
    )


def _is_signature_mark(line: Line, column: Edges) -> bool:
    """Whether a line is a printer's signature mark (spec section 4)."""
    text = words_text(line.words)
    characters = tuple(character for character in text if character.isalnum())
    has_digit = any(character.isdigit() for character in characters)
    has_letter = any(character.isalpha() for character in characters)
    return (
        len(line.words) <= _SIGNATURE_MARK_MAX_WORDS
        and len(characters) <= _SIGNATURE_MARK_MAX_CHARACTERS
        and (
            (
                has_digit
                # Letters and digits, or digits around a dash or a space:
                # so not a number alone, "1900.".
                and (
                    has_letter
                    or _DIGITS_AROUND_A_DASH_OR_SPACE.fullmatch(text) is not None
                )
            )
            or _is_spread_signature(line, column)
        )
        and middle(line.box)
        >= column.left + _SIGNATURE_MARK_FROM_LEFT_SHARE * column.width
    )


def _signature_mark_removals(
    page: PageLayout, place: LinePlace | None, column: Edges
) -> LineRemovals:
    """The line at `place` removed as a signature mark when it is one."""
    if place is None or not _is_signature_mark(line_at(page, place), column):
        return _NOTHING_REMOVED
    return _removed_as_signature_mark(page, place)


def _removed_as_signature_mark(page: PageLayout, place: LinePlace) -> LineRemovals:
    """The line at `place`, known to be a signature mark, removed as one."""
    removal = words_removal(
        page.index, line_at(page, place).words, RemovalReason.SIGNATURE_MARK
    )
    return LineRemovals((removal,), (), frozenset({place}))


def _signature_line_removals(
    page: PageLayout, place: LinePlace, position: int
) -> LineRemovals:
    """A signature line removed: the page number at `position` as
    `page_number` with a `foot` page number, every other word as
    `signature_mark`, in the order of their left sides."""
    words = line_at(page, place).words
    number = words[position]
    removals = (
        words_removal(page.index, (number,), RemovalReason.PAGE_NUMBER),
        words_removal(
            page.index,
            words[:position] + words[position + 1 :],
            RemovalReason.SIGNATURE_MARK,
        ),
    )
    return LineRemovals(
        tuple(sorted(removals, key=lambda removal: removal.box.x0)),
        (PageNumber(page.index, number.text, PageNumberPosition.FOOT),),
        frozenset({place}),
    )


def _local_offset(page_index: int, head_numbers: frozendict[int, int]) -> int | None:
    """The local offset of a page (spec section 4): page index minus printed
    number of the nearest page, before or after it, before on a tie, whose
    running head has an arabic page number in `head_numbers`; None when
    no page has one."""
    pages = sorted(head_numbers)
    after = bisect.bisect_left(pages, page_index)
    near = tuple(pages[max(0, after - 1) : after + 1])
    if not near:
        return None
    nearest = min(near, key=lambda page: (abs(page - page_index), page))
    return nearest - head_numbers[nearest]


def _is_foot_number_by_value(
    line: Line, page_index: int, head_numbers: frozendict[int, int]
) -> bool:
    """Whether a lowest line is a page number at the foot by its value
    (spec section 4): one word of the arabic page-number form whose value
    plus the page's local offset is the page index, wherever it lies."""
    if len(line.words) != 1:
        return False
    value = arabic_value(line.words[0].text)
    offset = _local_offset(page_index, head_numbers)
    return value is not None and offset is not None and value + offset == page_index


def _is_set_apart_beside(
    page: PageLayout, place: LinePlace, lowest: Line, pitch: float
) -> bool:
    """Whether the line at `place` lies beside `lowest`, the page's lowest
    line, in height: its bottom less than `pitch` above `lowest`'s bottom,
    wherever it lies across the page; and set apart below its region's
    line before it, its top `_SET_APART_PITCHES` times `pitch` or more
    below that line's top. A line first in its region is not set apart
    (spec section 4). `pitch` is in points."""
    region_number, line_number = place
    if line_number == 0:
        return False
    line = line_at(page, place)
    before = page.regions[region_number].lines[line_number - 1]
    return (
        lowest.box.bottom - line.box.bottom < pitch
        and line.box.top - before.box.top >= _SET_APART_PITCHES * pitch
    )


def foot_removals(
    page: PageLayout,
    kinds: tuple[RegionKind, ...],
    survey: BookSurvey,
) -> LineRemovals:
    """The removals at the foot of a page (spec section 4), on its lowest
    line once the running head is removed: a page number, a signature line
    (on the pages of `survey.signature_lines`), or a printer's signature
    mark, which may also be the line above a page number, or the line
    beside a lowest line that is none of these (`_is_set_apart_beside`).
    `kinds` are those of the page's regions, in their order."""
    column = body_column(page, kinds)
    head = running_head_lines(page, kinds)
    place = lowest_line(page, head)
    if column is None or place is None:
        return _NOTHING_REMOVED
    line = line_at(page, place)
    if is_foot_page_number(line, column) or _is_foot_number_by_value(
        line, page.index, survey.head_numbers
    ):
        text = "".join(word.text for word in line.words)
        above = _signature_mark_removals(
            page, lowest_line(page, head | {place}), column
        )
        return LineRemovals(
            (
                *above.removals,
                words_removal(page.index, line.words, RemovalReason.PAGE_NUMBER),
            ),
            (PageNumber(page.index, text, PageNumberPosition.FOOT),),
            above.lines | {place},
        )
    position = signature_page_number(line, column)
    if page.index in survey.signature_lines and position is not None:
        return _signature_line_removals(page, place, position)
    if _is_signature_mark(line, column):
        return _removed_as_signature_mark(page, place)
    above = lowest_line(page, head | {place})
    if above is None or not _is_set_apart_beside(
        page, above, line, survey.body_line_pitch
    ):
        return _NOTHING_REMOVED
    return _signature_mark_removals(page, above, column)
