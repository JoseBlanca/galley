"""Letter fragments: the pieces of a letter, a descender or the dot of an
"i", that Stubbs' text layer gives as words of their own, inside the word
they were cut from (spec section 35)."""

from collections.abc import Sequence
from dataclasses import dataclass, replace
from enum import StrEnum

from galley.model import Line, PageLayout, Removal, RemovalReason, Word
from galley.structure._measures import letters, words_removal

# Condition 1: a fragment has at most 2 characters, at most 1 of them a
# letter (spec section 35).
_FRAGMENT_MOST_CHARACTERS = 2
_FRAGMENT_MOST_LETTERS = 1
# Condition 2: the word it lies in has at least 3 letters, covers at least
# half of the fragment's width, and the fragment is at most 1.15 times as
# tall as that word (spec section 35, measured on Stubbs on 19 November
# 2026).
_HOST_LEAST_LETTERS = 3
_HOST_LEAST_SHARE_OF_WIDTH = 0.5
_FRAGMENT_MOST_TIMES_HOST_HEIGHT = 1.15
# Condition 3: fewer than 2 other words of the line share the fragment's
# top and bottom, each within 0.2 pt (spec section 35).
_ROW_TOLERANCE_PT = 0.2
_ROW_MOST_OTHER_WORDS = 1
# A line of fragments (spec section 35): each of its words lies by a word of
# the nearest line of text above or below, overlapping it in height or at
# most 1.5 pt from it; Stubbs' page 29 "." lies 1.0 pt above "English". On
# Stubbs, 149 such words at 0 pt, 168 at 1 pt, 172 at 1.5 pt, 176 at 2 pt
# (19 November 2026), all 172 pieces of letters or specks; 116 of them on
# lines whose every word lies so, which the rule removes.
_LINE_OF_FRAGMENTS_GAP_PT = 1.5
# A book has letter fragments when at least 0.15 of its pages of 5 lines or
# more have one: Stubbs 0.410, the seven other books 0.030 at most (spec
# section 35, measured on 19 November 2026).
_LEAST_LINES_OF_A_COUNTED_PAGE = 5
_LEAST_SHARE_OF_PAGES = 0.15


class LetterFragments(StrEnum):
    """Whether a book has letter fragments, and so whether the rule runs
    (spec section 35)."""

    PRESENT = "present"
    ABSENT = "absent"


def _may_be_a_fragment(word: Word) -> bool:
    return (
        word.ocr_confidence is None
        and len(word.text) <= _FRAGMENT_MOST_CHARACTERS
        and len(letters(word.text)) <= _FRAGMENT_MOST_LETTERS
    )


def _lies_inside(fragment: Word, host: Word) -> bool:
    """Condition 2: `host` has 3 letters or more, covers half of
    `fragment`'s width, overlaps it in height and is at least 1/1.15 of its
    height."""
    if host is fragment or len(letters(host.text)) < _HOST_LEAST_LETTERS:
        return False
    box, host_box = fragment.box, host.box
    width = box.x1 - box.x0
    covered = min(box.x1, host_box.x1) - max(box.x0, host_box.x0)
    return (
        covered > 0
        and covered >= _HOST_LEAST_SHARE_OF_WIDTH * width
        and box.top < host_box.bottom
        and box.bottom > host_box.top
        and box.bottom - box.top
        <= (host_box.bottom - host_box.top) * _FRAGMENT_MOST_TIMES_HOST_HEIGHT
    )


def _lies_by(fragment: Word, host: Word) -> bool:
    """For a line of fragments: `host` has 3 letters or more, covers half
    of `fragment`'s width, overlaps it in height or lies at most
    `_LINE_OF_FRAGMENTS_GAP_PT` above or below it, and is at least 1/1.15
    of its height."""
    if len(letters(host.text)) < _HOST_LEAST_LETTERS:
        return False
    box, host_box = fragment.box, host.box
    width = box.x1 - box.x0
    covered = min(box.x1, host_box.x1) - max(box.x0, host_box.x0)
    gap = max(host_box.top - box.bottom, box.top - host_box.bottom)
    return (
        covered > 0
        and covered >= _HOST_LEAST_SHARE_OF_WIDTH * width
        and gap <= _LINE_OF_FRAGMENTS_GAP_PT
        and box.bottom - box.top
        <= (host_box.bottom - host_box.top) * _FRAGMENT_MOST_TIMES_HOST_HEIGHT
    )


def _only_candidates(line: Line) -> bool:
    """Whether `line` holds words and each meets condition 1."""
    return bool(line.words) and all(_may_be_a_fragment(word) for word in line.words)


def is_line_of_fragments(line: Line, neighbours: tuple[Line, ...]) -> bool:
    """Whether `line` is a line of letter fragments (spec section 35, "A
    line of fragments"): each of its words meets condition 1 and lies by a
    word of one of `neighbours`, the nearest lines above and below it in
    its region that are not made only of such words."""
    return bool(line.words) and all(
        _may_be_a_fragment(word)
        and any(_lies_by(word, host) for other in neighbours for host in other.words)
        for word in line.words
    )


def _alone_in_its_row(fragment: Word, line: Line) -> bool:
    """Condition 3: fewer than 2 other words of `line` have a top and a
    bottom each within 0.2 pt of `fragment`'s."""
    return (
        sum(
            1
            for word in line.words
            if word is not fragment
            and abs(word.box.top - fragment.box.top) <= _ROW_TOLERANCE_PT
            and abs(word.box.bottom - fragment.box.bottom) <= _ROW_TOLERANCE_PT
        )
        <= _ROW_MOST_OTHER_WORDS
    )


def fragment_numbers(line: Line) -> tuple[int, ...]:
    """The positions in `line` of its letter fragments, by the three
    conditions of spec section 35, whether or not the book has them."""
    return tuple(
        number
        for number, word in enumerate(line.words)
        if _may_be_a_fragment(word)
        and any(_lies_inside(word, host) for host in line.words)
        and _alone_in_its_row(word, line)
    )


def _counted(page: PageLayout, index_pages: frozenset[int]) -> bool:
    """Whether `page` counts for the share: not an index page, and with 5
    lines or more in all its regions."""
    return (
        page.index not in index_pages
        and sum(len(region.lines) for region in page.regions)
        >= _LEAST_LINES_OF_A_COUNTED_PAGE
    )


def letter_fragments(
    pages: Sequence[PageLayout], index_pages: frozenset[int]
) -> LetterFragments:
    """Whether the book of `pages`, without their in-page figures' regions,
    has letter fragments: at least 0.15 of its pages of 5 lines or more,
    `index_pages` left out, have one (spec section 35)."""
    counted = tuple(page for page in pages if _counted(page, index_pages))
    with_one = sum(
        1
        for page in counted
        if any(
            fragment_numbers(line) for region in page.regions for line in region.lines
        )
    )
    return (
        LetterFragments.PRESENT
        if counted and with_one >= _LEAST_SHARE_OF_PAGES * len(counted)
        else LetterFragments.ABSENT
    )


@dataclass(frozen=True, slots=True)
class PageWithoutFragments:
    """A page with its letter fragments taken out of its lines, each line's
    box unchanged, and the removal of each fragment, in reading order."""

    page: PageLayout
    removals: tuple[Removal, ...]
    removed_lines: frozenset[tuple[int, int]]


def without_fragments(
    page: PageLayout,
    removed: frozenset[tuple[int, int]],
    fragments: LetterFragments,
    index_pages: frozenset[int],
) -> PageWithoutFragments:
    """`page` without the letter fragments of its lines, in a book whose
    survey found `fragments` present and on a page not among `index_pages`
    (spec section 35); else `page` as it is. The lines at the (region,
    line) places of `removed`, which another rule removed, keep their
    words. A line keeps the word a fragment lies in, so none is left
    empty; a line of fragments keeps its words and is given among
    `removed_lines`, its words each a removal."""
    if fragments is LetterFragments.ABSENT or page.index in index_pages:
        return PageWithoutFragments(page, (), frozenset())
    removals: list[Removal] = []
    removed_lines: set[tuple[int, int]] = set()

    def without(region_number: int, line_number: int, line: Line) -> Line:
        if (region_number, line_number) in removed:
            return line
        lines = page.regions[region_number].lines
        neighbours = tuple(
            nearest
            for numbers in (
                range(line_number - 1, -1, -1),
                range(line_number + 1, len(lines)),
            )
            if (
                nearest := next(
                    (lines[n] for n in numbers if not _only_candidates(lines[n])),
                    None,
                )
            )
            is not None
        )
        if is_line_of_fragments(line, neighbours):
            removed_lines.add((region_number, line_number))
            removals.extend(
                words_removal(page.index, (word,), RemovalReason.LETTER_FRAGMENT)
                for word in line.words
            )
            return line
        numbers = frozenset(fragment_numbers(line))
        if not numbers:
            return line
        removals.extend(
            words_removal(page.index, (word,), RemovalReason.LETTER_FRAGMENT)
            for number, word in enumerate(line.words)
            if number in numbers
        )
        return replace(
            line,
            words=tuple(
                word for number, word in enumerate(line.words) if number not in numbers
            ),
        )

    regions = tuple(
        replace(
            region,
            lines=tuple(
                without(region_number, line_number, line)
                for line_number, line in enumerate(region.lines)
            ),
        )
        for region_number, region in enumerate(page.regions)
    )
    return PageWithoutFragments(
        replace(page, regions=regions), tuple(removals), frozenset(removed_lines)
    )
