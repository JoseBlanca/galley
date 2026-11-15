"""What structure removes from a page (spec sections 3 and 4): the running
head, its page number and the stray marks above it."""

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
from galley.structure._measures import (
    arabic_value,
    is_roman_form,
    words_box,
    words_text,
)
from galley.structure._survey import BookSurvey


@dataclass(frozen=True, slots=True)
class LineRemovals:
    """What was removed from a page's lines: the records, the page numbers,
    and the removed lines, as (region number, line number) on the page."""

    removals: tuple[Removal, ...]
    page_numbers: tuple[PageNumber, ...]
    lines: frozenset[tuple[int, int]]


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


def head_removals(page: PageLayout, survey: BookSurvey) -> LineRemovals:
    """The removals of a running head (spec section 3): a line of marks
    above it as `stray_mark`, its page number as `page_number` with a
    `head` page number, and the rest of its line as `running_head`. A page
    whose head line is not a running head loses nothing."""
    if page.index not in survey.running_heads:
        return LineRemovals((), (), frozenset())
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
