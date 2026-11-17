"""Quotes (spec section 16, rules 1 to 3): body paragraphs set in smaller
type, across the column or inset, and the short blocks between them.

Positions and widths are PDF points; a height ratio is over the body word
height, a density over the book's (spec section 1)."""

import statistics
from collections.abc import Sequence
from dataclasses import replace

from galley.body_measures import median_word_height
from galley.model import BlockKind
from galley.structure._lines import PlacedLine, first_word
from galley.structure._markers import MarkerForm, marker_form
from galley.structure._paragraphs import BodyBlock, Entry

# Spec section 1: a wide line has at least 5 words and is at least 150 pt
# wide; a full line, measured for the book's density, has at least 5 words
# and its sides within 3 pt of its region's edges.
_WIDE_MIN_WORDS = 5
_WIDE_MIN_PT = 150.0
_FULL_SIDE_PT = 3.0
# Spec section 16: a quote's median height ratio is at most 0.95 (quote
# blocks' 90th percentile 0.94 to 0.97, paragraphs' 10th 0.99 to 1.00); by
# rule 1 its wide lines' median density is at least 1.04 and it has at
# least 2 wide lines; by rule 2 it has at least 2 lines, each at least 16
# pt right of its region's left edge.
_HEIGHT_RATIO_MAX = 0.95
_DENSITY_MIN = 1.04
_QUOTE_MIN_WIDE_LINES = 2
_INSET_MIN_LINES = 2
_INSET_LEFT_PT = 16.0


def _characters(line: PlacedLine) -> int:
    return sum(len(word.text) for word in line.line.words)


def _width(line: PlacedLine) -> float:
    return line.line.box.x1 - line.line.box.x0


def _raw_density(line: PlacedLine) -> float:
    """The line's characters, spaces left out, per point of its width."""
    return _characters(line) / _width(line) if _width(line) > 0 else 0.0


def _is_full(line: PlacedLine) -> bool:
    box, edges = line.line.box, line.edges
    return (
        len(line.line.words) >= _WIDE_MIN_WORDS
        and abs(box.x0 - edges.left) <= _FULL_SIDE_PT
        and abs(edges.right - box.x1) <= _FULL_SIDE_PT
    )


def book_density(lines: Sequence[PlacedLine]) -> float:
    """The book's median character density of full lines (spec section 1),
    over `lines`, the body stream's lines of every page; 0 without one."""
    densities = tuple(_raw_density(line) for line in lines if _is_full(line))
    return statistics.median(densities) if densities else 0.0


def _is_wide(line: PlacedLine) -> bool:
    return len(line.line.words) >= _WIDE_MIN_WORDS and _width(line) >= _WIDE_MIN_PT


def _height_ratio(lines: Sequence[PlacedLine], body_word_height: float) -> float:
    """The median height of the words of `lines` over the body word height."""
    return (
        median_word_height(word for line in lines for word in line.line.words)
        / body_word_height
    )


def _by_rule_1_or_2(
    lines: Sequence[PlacedLine], body_word_height: float, density: float
) -> bool:
    """Spec section 16, rules 1 and 2: smaller type across the column, or
    inset on the left."""
    if _height_ratio(lines, body_word_height) > _HEIGHT_RATIO_MAX:
        return False
    wide = tuple(line for line in lines if _is_wide(line))
    smaller_type = (
        len(wide) >= _QUOTE_MIN_WIDE_LINES
        and density > 0
        and statistics.median(_raw_density(line) for line in wide) / density
        >= _DENSITY_MIN
    )
    inset = len(lines) >= _INSET_MIN_LINES and all(
        line.line.box.x0 - line.edges.left >= _INSET_LEFT_PT for line in lines
    )
    return smaller_type or inset


def _is_short_and_small(lines: Sequence[PlacedLine], body_word_height: float) -> bool:
    """Spec section 16, rule 3: fewer than 2 wide lines, a median height
    ratio of at most 0.95."""
    return (
        sum(_is_wide(line) for line in lines) < _QUOTE_MIN_WIDE_LINES
        and _height_ratio(lines, body_word_height) <= _HEIGHT_RATIO_MAX
    )


def with_quotes(
    entries: Sequence[Entry],
    judged: frozenset[int],
    form: MarkerForm | None,
    body_word_height: float,
    density: float,
) -> tuple[Entry, ...]:
    """The entries with each body paragraph that rules 1 to 3 of spec
    section 16 take made a quote. Only the paragraphs at the positions
    `judged` are looked at (not those of the endnote section or of a
    bibliographical note); a paragraph whose first word has the book's
    marker form `form` never is. Rule 3 takes a short block of small type
    next to a block that rules 1 or 2 took, among the body's blocks.
    `body_word_height` is in points; `density` is the book's."""
    if body_word_height <= 0:
        return tuple(entries)
    candidates = frozenset(
        position
        for position in judged
        if isinstance(entry := entries[position], BodyBlock)
        and entry.kind is BlockKind.PARAGRAPH
        and not (
            form is not None and marker_form(first_word(entry.piece.lines[0])) is form
        )
    )
    by_rules = frozenset(
        position
        for position in candidates
        if _by_rule_1_or_2(entries[position].piece.lines, body_word_height, density)
    )
    body = tuple(
        position
        for position, entry in enumerate(entries)
        if isinstance(entry, BodyBlock)
    )
    neighbours = {
        position: (
            body[number - 1] if number > 0 else None,
            body[number + 1] if number + 1 < len(body) else None,
        )
        for number, position in enumerate(body)
    }
    by_rule_3 = frozenset(
        position
        for position in candidates - by_rules
        if any(neighbour in by_rules for neighbour in neighbours[position])
        and _is_short_and_small(entries[position].piece.lines, body_word_height)
    )
    quotes = by_rules | by_rule_3
    return tuple(
        replace(entry, kind=BlockKind.QUOTE) if position in quotes else entry
        for position, entry in enumerate(entries)
    )
