"""A line placed on its page, and the rules of spec section 6 that say
whether a line starts a paragraph: the indent after a short line, the
centred line, the hanging number, and the hyphen that joins a line to the
one before."""

import re
from collections.abc import Sequence
from dataclasses import dataclass

from galley.body_measures import commonest
from galley.model import Line, Word
from galley.structure._measures import (
    Edges,
    is_hyphen_first_part,
    is_number_before_word,
    words_box,
)

# Spec section 6, rule 1: an indented line starts 5 to 40 pt right of its
# region's left edge (Stubbs' cut-in notes push lines 60 pt in), after a
# line that ends more than 3 pt short of its region's right edge.
INDENT_MIN_PT = 5.0
INDENT_MAX_PT = 40.0
_SHORT_LINE_PT = 3.0
# Spec section 6, rule 2: a centred line is at least 15 pt in from both
# edges, the two insets differing by at most 10 pt.
_CENTRED_INSET_MIN_PT = 15.0
_CENTRED_INSET_DIFFERENCE_PT = 10.0
# Spec section 6, rule 3: a hanging number is 1 to 3 digits, hung 5 to 20
# pt left of its region's text edge (Turney's notes hang theirs 8.8 to
# 18.8 pt), which is the commonest left side of at least 3 lines that do
# not start with such a number.
_HANGING_NUMBER = re.compile(r"[0-9]{1,3}")
_HANG_MIN_PT = 5.0
_HANG_MAX_PT = 20.0
_TEXT_EDGE_MIN_LINES = 3
# Spec section 6, rule 3, and section 12: a misread marker is followed by
# lines hung with 2, 3 and 4.
_MISREAD_FOLLOWERS = 3


@dataclass(frozen=True, slots=True)
class PlacedLine:
    """A line of a page with its page index, its region's edges, the
    edges its centring is measured against: the region's, or the page's
    body column for a line of a short body region, and, for a line of a
    body region, the region's text edge in points from the left of the
    page, None when it has none or the line is side text (spec section 6,
    rule 3)."""

    page_index: int
    line: Line
    edges: Edges
    centring_edges: Edges
    text_edge: float | None = None


@dataclass(frozen=True, slots=True)
class Piece:
    """A block's lines, all on one page or over several, in order, and the
    positions of those lines that a hyphen never joins to the line before:
    the first line of each region but the first of a margin note printed
    in several regions, where a line between them went unread (spec
    section 13, rule 1)."""

    lines: tuple[PlacedLine, ...]
    unjoined: frozenset[int] = frozenset()


def first_word(line: PlacedLine) -> str:
    """The text of the line's first word, "" when it has none."""
    return line.line.words[0].text if line.line.words else ""


def with_words(line: PlacedLine, words: tuple[Word, ...]) -> PlacedLine:
    """The part of `line` that holds `words`, some of its words in order,
    which are not none."""
    return PlacedLine(
        line.page_index,
        Line(words_box(words), words),
        line.edges,
        line.centring_edges,
        line.text_edge,
    )


def is_bare_number(word: str) -> bool:
    """Whether `word` is 1 to 3 digits with nothing after them, "8" or
    "145" (spec section 6, rule 3; section 12)."""
    return _HANGING_NUMBER.fullmatch(word) is not None


def text_edge(lines: Sequence[Line]) -> float | None:
    """The text edge of a region of `lines` (spec section 6, rule 3): the
    commonest left side of its lines whose first word is not a bare
    number, in points; None when fewer than 3 lines are such."""
    lefts = tuple(
        line.box.x0
        for line in lines
        if line.words and not is_bare_number(line.words[0].text)
    )
    return commonest(lefts) if len(lefts) >= _TEXT_EDGE_MIN_LINES else None


def has_hanging_number(line: PlacedLine) -> bool:
    """Spec section 6, rule 3: the line's first word is a bare number, it
    has a second word, and its left side lies 5 to 20 pt left of its
    region's text edge."""
    return _is_hung(line) and is_bare_number(line.line.words[0].text)


def is_misread_marker(word: str) -> bool:
    """Whether `word` may be a note's "1" the OCR misread: one character
    that is not a digit, Turney's "x" (spec section 12, the misread
    marker)."""
    return len(word) == 1 and not word.isdigit()


def _is_hung(line: PlacedLine) -> bool:
    return (
        line.text_edge is not None
        and len(line.line.words) > 1
        and _HANG_MIN_PT <= line.text_edge - line.line.box.x0 <= _HANG_MAX_PT
    )


def misread_marker_lines(lines: Sequence[PlacedLine]) -> frozenset[int]:
    """The positions in `lines`, a page's body stream, of the lines that
    start a paragraph with a misread marker (spec section 6, rule 3): the
    first word one character that is not a digit, a second word, hung 5 to
    20 pt left of the text edge, and the next three lines that start with
    a hanging number reading 2, 3 and 4."""
    return frozenset(
        number
        for number, line in enumerate(lines)
        if _is_hung(line)
        and is_misread_marker(line.line.words[0].text)
        and tuple(
            later.line.words[0].text
            for later in lines[number + 1 :]
            if has_hanging_number(later)
        )[:_MISREAD_FOLLOWERS]
        == ("2", "3", "4")
    )


def is_indented(line: PlacedLine, before: PlacedLine) -> bool:
    """Spec section 6, rule 1: `line` starts 5 to 40 pt right of its
    region's left edge, and `before` ends more than 3 pt short of its
    region's right edge."""
    indent = line.line.box.x0 - line.edges.left
    return (
        INDENT_MIN_PT <= indent <= INDENT_MAX_PT
        and before.line.box.x1 < before.edges.right - _SHORT_LINE_PT
    )


def is_centred(line: PlacedLine) -> bool:
    """Spec section 6, rule 2: both insets of the line from its centring
    edges are at least 15 pt and differ by at most 10 pt."""
    left_inset = line.line.box.x0 - line.centring_edges.left
    right_inset = line.centring_edges.right - line.line.box.x1
    return (
        left_inset >= _CENTRED_INSET_MIN_PT
        and right_inset >= _CENTRED_INSET_MIN_PT
        and abs(left_inset - right_inset) <= _CENTRED_INSET_DIFFERENCE_PT
    )


def hyphen_between(before: PlacedLine, line: PlacedLine) -> bool:
    """Whether `before` ends with a hyphen that may join it to `line`: the
    first part of a join, unless a number before a word (spec section 6)."""
    if not before.line.words:
        return False
    last = before.line.words[-1].text
    return is_hyphen_first_part(last) and not (
        bool(line.line.words) and is_number_before_word(last, line.line.words[0].text)
    )


def starts_paragraph(line: PlacedLine, before: PlacedLine | None) -> bool:
    """Whether `line` starts a paragraph after `before`, the line before it
    (spec section 6): never after a hyphen; else when it is indented after
    a short line, it or the line before is centred, or it starts with a
    hanging number."""
    if before is None:
        return True
    if hyphen_between(before, line):
        return False
    return (
        is_indented(line, before)
        or is_centred(line)
        or is_centred(before)
        or has_hanging_number(line)
    )
