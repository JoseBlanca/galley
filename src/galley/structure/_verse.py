"""Verse (spec section 16, rule 4): runs of short lines inset from both
sides of the column, found per page before the paragraphs are made."""

import statistics
from collections.abc import Sequence

from galley.model import BlockKind
from galley.structure._lines import PlacedLine, hyphen_between
from galley.structure._runs import BodyRun

# Spec section 16, rule 4: a verse line has at least 3 words and is inset at
# least 30 pt from both edges (15 pt adds 3 Domesday table runs and 8
# Mariéjol runs of broken lines, and no verse); a run has at least 2 lines,
# more than half of them starting within 12 pt of its median left side.
_VERSE_MIN_WORDS = 3
_VERSE_INSET_PT = 30.0
_VERSE_MIN_LINES = 2
_VERSE_LEFT_WINDOW_PT = 12.0


def _is_verse_line(line: PlacedLine) -> bool:
    """At least 3 words, and inset at least 30 pt from both of the edges its
    centring is measured against (its region's, or the page's body column
    for a line of a short body region, spec section 6)."""
    box, edges = line.line.box, line.centring_edges
    return (
        len(line.line.words) >= _VERSE_MIN_WORDS
        and box.x0 - edges.left >= _VERSE_INSET_PT
        and edges.right - box.x1 >= _VERSE_INSET_PT
    )


def _aligned(lines: Sequence[PlacedLine]) -> bool:
    """More than half of `lines` start within 12 pt of their median left."""
    lefts = tuple(line.line.box.x0 for line in lines)
    median = statistics.median(lefts)
    near = sum(abs(left - median) <= _VERSE_LEFT_WINDOW_PT for left in lefts)
    return 2 * near > len(lefts)


def verse_runs(
    lines: Sequence[PlacedLine], taken: frozenset[int]
) -> tuple[BodyRun, ...]:
    """The verse blocks of `lines`, a page's body stream (spec section 16,
    rule 4): each longest run of at least 2 consecutive verse lines, none of
    them at the positions `taken` (a heading's or a summary's), the first
    not right after a line ending with a hyphen, more than half of them
    starting within 12 pt of the run's median left side."""
    runs: list[BodyRun] = []
    start: int | None = None
    for number in range(len(lines) + 1):
        is_verse = (
            number < len(lines)
            and number not in taken
            and _is_verse_line(lines[number])
            # A run never starts right after a hyphen (spec section 6).
            and not (
                start is None
                and number > 0
                and hyphen_between(lines[number - 1], lines[number])
            )
        )
        if is_verse and start is None:
            start = number
        elif not is_verse and start is not None:
            if number - start >= _VERSE_MIN_LINES and _aligned(lines[start:number]):
                runs.append(BodyRun(start=start, end=number, kind=BlockKind.VERSE))
            start = None
    return tuple(runs)
