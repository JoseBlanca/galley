"""Where a margin note stands (spec section 13): the line of the page it is
beside (rule 2), and the note that holds that line, inside which it goes
(rule 5)."""

from collections.abc import Sequence
from dataclasses import dataclass

from galley.structure._lines import PlacedLine

# Spec section 13, rule 2: a paragraph's first line whose top lies within
# 0.5 pitch of the margin note's top is the line beside, before any other
# (519 of Domesday's 613 margin notes have one, 379 of Gierke's 658).
_FIRST_LINE_PITCHES = 0.5


@dataclass(frozen=True, slots=True)
class BesideLine:
    """A line of a page that a margin note may stand beside: the line,
    whether it is the first line of its block, and, for a line of a note,
    the note's position among the notes and its block's among the note's
    blocks; None for a line of the body."""

    line: PlacedLine
    first: bool
    note_block: tuple[int, int] | None


def line_beside(
    top: float, lines: Sequence[BesideLine], pitch: float
) -> BesideLine | None:
    """The line beside a margin note whose first line's top is `top`, among
    the `lines` of its page (spec section 13, rule 2): a block's first line
    whose top is within 0.5 `pitch` of it, the nearest; otherwise the line
    whose top is nearest; the first in the order of `lines` on a tie. None
    when the page has no line. `top` and `pitch`, the body line pitch, are
    in points."""

    def distance(beside: BesideLine) -> float:
        return abs(beside.line.line.box.top - top)

    firsts = tuple(
        beside
        for beside in lines
        if beside.first and distance(beside) <= _FIRST_LINE_PITCHES * pitch
    )
    candidates = firsts or tuple(lines)
    return min(candidates, key=distance, default=None)
