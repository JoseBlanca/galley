"""A line placed on its page, and the rules of spec section 6 that say
whether a line starts a paragraph: the indent after a short line, the
centred line, and the hyphen that joins a line to the one before."""

from dataclasses import dataclass

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


@dataclass(frozen=True, slots=True)
class PlacedLine:
    """A line of a page with its page index, its region's edges, and the
    edges its centring is measured against: the region's, or the page's
    body column for a line of a short body region (spec section 6)."""

    page_index: int
    line: Line
    edges: Edges
    centring_edges: Edges


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
        line.page_index, Line(words_box(words), words), line.edges, line.centring_edges
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
    a short line, or it or the line before is centred."""
    if before is None:
        return True
    if hyphen_between(before, line):
        return False
    return is_indented(line, before) or is_centred(line) or is_centred(before)
