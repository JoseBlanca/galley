"""Chapter summaries (spec section 15): the lines under a heading that list
the chapter's topics between dashes, with a hanging indent."""

from collections.abc import Sequence

from galley.model import BlockKind
from galley.structure._lines import INDENT_MIN_PT, PlacedLine
from galley.structure._runs import BodyRun

# Spec section 15, rule 4: a summary holds at least 2 dashes, which keeps
# out the two lines beside a drop capital (Haskins page 163, Domesday 12,
# Mariéjol 105, 182, 222, 299).
_SUMMARY_MIN_DASHES = 2
_DASH_CHARACTERS = frozenset("—–")
# Spec section 15, rules 1 and 2: a summary has a first line and an indented
# second one.
_SUMMARY_MIN_LINES = 2
_SPACED_HYPHEN = "-"


def _indent(line: PlacedLine) -> float:
    return line.line.box.x0 - line.edges.left


def dash_count(texts: Sequence[str]) -> int:
    """The dashes of the words `texts` (spec section 15, rule 4): each "—"
    or "–", and each " - ", a word that is a hyphen alone."""
    return sum(
        1 if text == _SPACED_HYPHEN else sum(c in _DASH_CHARACTERS for c in text)
        for text in texts
    )


def _dashes(lines: Sequence[PlacedLine]) -> int:
    """The dashes of `lines` (`dash_count`)."""
    return dash_count(tuple(word.text for line in lines for word in line.line.words))


def summary_run(lines: Sequence[PlacedLine], start: int, end: int) -> BodyRun | None:
    """The chapter summary that starts at `start` in `lines`, a page's body
    stream, right after a heading block, and ends at `end` at the latest
    (the next run of the page or its end); None when there is none (spec
    section 15): its first line is at the left edge (indented less than
    5 pt), its second indented at least 5 pt, it holds them and every line
    after them indented at least 5 pt, and its text at least 2 dashes."""
    if end - start < _SUMMARY_MIN_LINES or _indent(lines[start]) >= INDENT_MIN_PT:
        return None
    last = start + 1
    while last < end and _indent(lines[last]) >= INDENT_MIN_PT:
        last += 1
    if last == start + 1 or _dashes(lines[start:last]) < _SUMMARY_MIN_DASHES:
        return None
    return BodyRun(start=start, end=last, kind=BlockKind.CHAPTER_SUMMARY)
