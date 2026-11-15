"""What structure removes from a page (spec sections 3 and 4): the running
head, its page number and the stray marks above it; the page number at the
foot, the signature line and the printer's signature mark."""

import re
from dataclasses import dataclass

from galley.model import (
    Line,
    PageLayout,
    PageNumber,
    PageNumberPosition,
    Removal,
    RemovalReason,
    Word,
)
from galley.structure._foot import (
    LinePlace,
    body_column,
    is_foot_page_number,
    line_at,
    lowest_line,
    running_head_lines,
    signature_page_number,
)
from galley.structure._measures import (
    Edges,
    arabic_value,
    is_roman_form,
    middle,
    words_box,
    words_text,
)
from galley.structure._regions import RegionKind
from galley.structure._survey import BookSurvey


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


def _removal(
    page_index: int, words: tuple[Word, ...], reason: RemovalReason
) -> Removal:
    """One removal of `words`, of one line, joined by one space, with the
    smallest box that holds them."""
    return Removal(
        page_index=page_index,
        box=words_box(words),
        text=words_text(words),
        reason=reason,
    )


def _head_page_number(
    words: tuple[Word, ...], page_index: int, survey: BookSurvey
) -> int | None:
    """The position in `words` of the running head's page number, or None
    (spec section 3): its first or last word, when a page-number form, a
    roman one only before the first page with an arabic head number; of
    two, the one the offset gives, else the first."""
    roman_allowed = (
        survey.first_arabic_page is None or page_index < survey.first_arabic_page
    )
    ends = (0,) if len(words) == 1 else (0, len(words) - 1)
    numbers = tuple(
        position
        for position in ends
        if arabic_value(words[position].text) is not None
        or (roman_allowed and is_roman_form(words[position].text))
    )
    if not numbers:
        return None
    offset = survey.head_page_offset
    if offset is not None:
        for position in numbers:
            value = arabic_value(words[position].text)
            if value is not None and value + offset == page_index:
                return position
    return numbers[0]


def head_removals(
    page: PageLayout, kinds: tuple[RegionKind, ...], survey: BookSurvey
) -> LineRemovals:
    """The removals of a running head (spec section 3): a line of marks
    above it as `stray_mark`, its page number as `page_number` with a
    `head` page number, and the rest of its line as `running_head`. A page
    whose head line is not a running head loses nothing. `kinds` are those
    of the page's regions, in their order."""
    if RegionKind.RUNNING_HEAD not in kinds:
        return _NOTHING_REMOVED
    head = page.regions[0]
    *marks, text_line = head.lines
    strays = tuple(
        _removal(page.index, mark.words, RemovalReason.STRAY_MARK) for mark in marks
    )
    removals, page_numbers = _running_head_removals(page.index, text_line, survey)
    return LineRemovals(
        strays + removals,
        page_numbers,
        frozenset((0, number) for number in range(len(head.lines))),
    )


def _running_head_removals(
    page_index: int, line: Line, survey: BookSurvey
) -> tuple[tuple[Removal, ...], tuple[PageNumber, ...]]:
    words = line.words
    position = _head_page_number(words, page_index, survey)
    if position is None:
        return (_removal(page_index, words, RemovalReason.RUNNING_HEAD),), ()
    number = words[position]
    rest = words[:position] + words[position + 1 :]
    number_removal = _removal(page_index, (number,), RemovalReason.PAGE_NUMBER)
    rest_removals = (
        (_removal(page_index, rest, RemovalReason.RUNNING_HEAD),) if rest else ()
    )
    in_line_order = (
        (number_removal, *rest_removals)
        if position == 0
        else (*rest_removals, number_removal)
    )
    return in_line_order, (
        PageNumber(page_index, number.text, PageNumberPosition.HEAD),
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
        and has_digit
        and not is_foot_page_number(line, column)
        # Letters and digits, or digits around a dash or a space: so not a
        # number alone, "1900.".
        and (has_letter or _DIGITS_AROUND_A_DASH_OR_SPACE.fullmatch(text) is not None)
        and middle(line.box)
        >= column.left + _SIGNATURE_MARK_FROM_LEFT_SHARE * column.width
    )


def _signature_mark_removals(
    page: PageLayout, place: LinePlace | None, column: Edges
) -> LineRemovals:
    """The line at `place` removed as a signature mark when it is one."""
    if place is None or not _is_signature_mark(line_at(page, place), column):
        return _NOTHING_REMOVED
    removal = _removal(
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
        _removal(page.index, (number,), RemovalReason.PAGE_NUMBER),
        _removal(
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


def foot_removals(
    page: PageLayout,
    kinds: tuple[RegionKind, ...],
    survey: BookSurvey,
) -> LineRemovals:
    """The removals at the foot of a page (spec section 4), on its lowest
    line once the running head is removed: a page number, a signature line
    (on the pages of `survey.signature_lines`), or a printer's signature
    mark, which may also be the line above a page number. `kinds` are
    those of the page's regions, in their order."""
    column = body_column(page, kinds)
    head = running_head_lines(page, kinds)
    place = lowest_line(page, head)
    if column is None or place is None:
        return _NOTHING_REMOVED
    line = line_at(page, place)
    if is_foot_page_number(line, column):
        text = "".join(word.text for word in line.words)
        above = _signature_mark_removals(
            page, lowest_line(page, head | {place}), column
        )
        return LineRemovals(
            (
                *above.removals,
                _removal(page.index, line.words, RemovalReason.PAGE_NUMBER),
            ),
            (PageNumber(page.index, text, PageNumberPosition.FOOT),),
            above.lines | {place},
        )
    position = signature_page_number(line, column)
    if page.index in survey.signature_lines and position is not None:
        return _signature_line_removals(page, place, position)
    return _signature_mark_removals(page, place, column)
