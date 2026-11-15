"""The stage output a difference belongs to (spec section 5, "The stage a
difference belongs to").

A reference token has a state at each of the four stage outputs, words,
lines, blocks and markdown, in that order. Not matched at markdown, it is
a difference of the book, attributed to the first output of its last run
of states other than matched. Matched at markdown after a state other
than matched, it was repaired by the output where its last run of
matches starts. Matched means the state `matched`: a pair that differs
only by convention is a difference too, which the scores count apart.

An extra galley token has no reference token to follow, so the extras of
each output are taken as a multiset of (page index, text), and an extra
at markdown is attributed to the first output from which it is in that
multiset at every later output. When the same (page index, text) is extra
several times at markdown, its first copy is followed through the first
copies of the other outputs, its second through the second, and so on.
"""

from dataclasses import dataclass
from enum import StrEnum

from galley_eval.align import GalleyToken, State

__all__ = [
    "PerOutput",
    "StageOutput",
    "TokenFate",
    "TracedExtra",
    "token_fate",
    "trace_extras",
]


class StageOutput(StrEnum):
    """The four texts compared with the reference, in the order galley
    makes them: `words.json`, `lines.json`, `blocks.json` and `book.md`."""

    WORDS = "words"
    LINES = "lines"
    BLOCKS = "blocks"
    MARKDOWN = "markdown"


_OUTPUTS = tuple(StageOutput)

type PerOutput[T] = tuple[T, T, T, T]
"""One value for each stage output, in the order of StageOutput."""


@dataclass(frozen=True, slots=True, kw_only=True)
class TokenFate:
    """What the four outputs did to a reference token. `difference_stage`
    is the output its difference is attributed to, None when it is
    matched at markdown; `repaired_by` is the output that repaired it,
    None when it is matched at every output or not at markdown."""

    difference_stage: StageOutput | None
    repaired_by: StageOutput | None


@dataclass(frozen=True, slots=True, kw_only=True)
class TracedExtra:
    """An extra token of markdown, the output its difference is
    attributed to, and the extra token with the same page index and text
    at that output: at words or lines, it carries `edge_of_page`."""

    token: GalleyToken
    stage: StageOutput
    origin: GalleyToken


def token_fate(states: PerOutput[State]) -> TokenFate:
    """The stage of a reference token's difference, or the stage that
    repaired it, from its state at words, lines, blocks and markdown."""
    final = states[-1] is State.MATCHED
    start = len(states) - 1
    while start > 0 and (states[start - 1] is State.MATCHED) == final:
        start -= 1
    if not final:
        return TokenFate(difference_stage=_OUTPUTS[start], repaired_by=None)
    if start == 0:
        return TokenFate(difference_stage=None, repaired_by=None)
    return TokenFate(difference_stage=None, repaired_by=_OUTPUTS[start])


def trace_extras(extras: PerOutput[tuple[GalleyToken, ...]]) -> tuple[TracedExtra, ...]:
    """Each extra token of markdown, the last of `extras`, with the output
    it is attributed to. `extras` holds the extra tokens of each output in
    the order of StageOutput, each in its output's order."""
    copies = tuple(_copies(output) for output in extras)
    seen: dict[tuple[int, str], int] = {}
    traced: list[TracedExtra] = []
    for token in extras[-1]:
        item = (token.page_index, token.text)
        copy = seen.get(item, 0)
        seen[item] = copy + 1
        start = len(extras) - 1
        while start > 0 and len(copies[start - 1].get(item, ())) > copy:
            start -= 1
        traced.append(
            TracedExtra(
                token=token, stage=_OUTPUTS[start], origin=copies[start][item][copy]
            )
        )
    return tuple(traced)


def _copies(
    tokens: tuple[GalleyToken, ...],
) -> frozendict[tuple[int, str], tuple[GalleyToken, ...]]:
    grouped: dict[tuple[int, str], list[GalleyToken]] = {}
    for token in tokens:
        grouped.setdefault((token.page_index, token.text), []).append(token)
    return frozendict({item: tuple(found) for item, found in grouped.items()})
