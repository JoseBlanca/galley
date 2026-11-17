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
from galley.structure._heads import EndNumber, arabic_number, is_confirmed
from galley.structure._measures import (
    Edges,
    line_has_letter_or_digit,
    middle,
    words_removal,
    words_text,
)
from galley.structure._regions import RegionKind, head_line
from galley.structure._survey import BookSurvey, number_candidates


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


def _head_page_number(
    line: Line, page_index: int, survey: BookSurvey
) -> EndNumber | None:
    """The running head's page number, or None (spec section 3): a
    page-number form at its start or end, a run of digit words joined, a
    roman one only before the first arabic head number; of two, the one
    the offset puts within 2 of the page index, else the first."""
    candidates = number_candidates(page_index, line, survey.first_arabic_page)
    if not candidates:
        return None
    return next(
        (
            candidate
            for candidate in candidates
            if is_confirmed(
                page_index, arabic_number(candidate), survey.head_page_offset
            )
        ),
        candidates[0],
    )


def _running_head_removals(
    page_index: int, line: Line, survey: BookSurvey
) -> tuple[tuple[Removal, ...], tuple[PageNumber, ...]]:
    """A running head's line removed: its page number as `page_number`, the
    rest as `running_head`, in the order of the line."""
    words = line.words
    number = _head_page_number(line, page_index, survey)
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


def running_head_place(page: PageLayout, survey: BookSurvey) -> LinePlace | None:
    """The place of the line that section 3 makes the page's running head:
    the text line of its head line, or the line below a speck; None when
    the page has none."""
    if page.index in survey.running_heads and (head := head_line(page)) is not None:
        return (0, len(head.lines) - 1)
    if page.index in survey.heads_below_specks:
        below = line_below_head(page)
        assert below is not None, "the survey found a line below the speck"
        return below
    return None


def head_removals(page: PageLayout, survey: BookSurvey) -> LineRemovals:
    """The removals of a running head (spec section 3): a line of marks
    above it as `stray_mark`, its page number as `page_number` with a
    `head` page number, and the rest of its line as `running_head`. When
    the head line is a speck and the line below it the running head, that
    line is removed so, and the speck stays. A page with no running head
    loses nothing."""
    head_place = running_head_place(page, survey)
    if head_place is None:
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
    removals, page_numbers = _running_head_removals(
        page.index, line_at(page, head_place), survey
    )
    return LineRemovals(
        strays + removals, page_numbers, frozenset((*mark_places, head_place))
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
                words_removal(page.index, line.words, RemovalReason.PAGE_NUMBER),
            ),
            (PageNumber(page.index, text, PageNumberPosition.FOOT),),
            above.lines | {place},
        )
    position = signature_page_number(line, column)
    if page.index in survey.signature_lines and position is not None:
        return _signature_line_removals(page, place, position)
    return _signature_mark_removals(page, place, column)
