"""Lining two sequences of comparison forms up by least edits
(docs/specs/correct.md, sections 5 and 7)."""

from collections.abc import Sequence
from dataclasses import dataclass
from enum import IntEnum


@dataclass(frozen=True, slots=True)
class Pair:
    """One step of an alignment: `first` and `second` are positions in the
    two sequences, either None when the other's token pairs with nothing."""

    first: int | None
    second: int | None


# Section 7: two unequal tokens cost 1 less this share of the letters they
# share, so that of two alignments that the measurement's unit costs make
# equal, the one that pairs alike words wins ("puem" with "poem", not with
# a note's number "15" beside it). Small, so that it decides ties and
# little else; guessed, not measured.
_LIKENESS_WEIGHT = 0.1


def _likeness(first: frozenset[str], second: frozenset[str]) -> float:
    """The share of letters two tokens have in common: those of both over
    those of the one with more, 0 to 1."""
    larger = max(len(first), len(second))
    return len(first & second) / larger if larger else 0.0


class _Step(IntEnum):
    PAIR = 0
    FIRST_ALONE = 1
    SECOND_ALONE = 2


def align(first: Sequence[str], second: Sequence[str]) -> tuple[Pair, ...]:
    """The alignment of `first` with `second` of least cost: a pair costs 0
    when equal, and when not 1 less a tenth of the share of letters the two
    have in common; a token left alone costs 1. On equal cost the backtrace
    takes a pair, then a token of `first` alone, then one of `second`
    alone: the measurement's common.align without its wildcard, but for
    that tenth."""
    return _align(first, second, free_first_tail=False)


def align_free_tail(first: Sequence[str], second: Sequence[str]) -> tuple[Pair, ...]:
    """As `align`, but the tokens of `first` after its last paired one cost
    nothing to leave out: how a block's tokens are lined up with the words
    printed on one of its pages (correct spec, section 5). Those tokens of
    `first` are not in the result."""
    return _align(first, second, free_first_tail=True)


def _align(
    first: Sequence[str], second: Sequence[str], *, free_first_tail: bool
) -> tuple[Pair, ...]:
    rows, columns = len(first), len(second)
    second_letters = [frozenset(token) for token in second]
    cost: list[list[float]] = [[0.0] * (columns + 1) for _ in range(rows + 1)]
    step = [[_Step.PAIR] * (columns + 1) for _ in range(rows + 1)]
    for column in range(1, columns + 1):
        cost[0][column] = column
        step[0][column] = _Step.SECOND_ALONE
    for row in range(1, rows + 1):
        cost[row][0] = cost[row - 1][0] + 1
        step[row][0] = _Step.FIRST_ALONE
        token = first[row - 1]
        letters = frozenset(token)
        above, here = cost[row - 1], cost[row]
        for column in range(1, columns + 1):
            other = second[column - 1]
            best = above[column - 1] + (
                0.0
                if token == other
                else 1.0
                - _LIKENESS_WEIGHT * _likeness(letters, second_letters[column - 1])
            )
            chosen = _Step.PAIR
            if above[column] + 1 < best:
                best, chosen = above[column] + 1, _Step.FIRST_ALONE
            if here[column - 1] + 1 < best:
                best, chosen = here[column - 1] + 1, _Step.SECOND_ALONE
            here[column] = best
            step[row][column] = chosen
    row = (
        min(range(rows + 1), key=lambda end: (cost[end][columns], -end))
        if free_first_tail
        else rows
    )
    column = columns
    pairs = []
    while row > 0 or column > 0:
        chosen = step[row][column] if row > 0 else _Step.SECOND_ALONE
        if row > 0 and column > 0 and chosen is _Step.PAIR:
            pairs.append(Pair(row - 1, column - 1))
            row, column = row - 1, column - 1
        elif row > 0 and (chosen is _Step.FIRST_ALONE or column == 0):
            pairs.append(Pair(row - 1, None))
            row -= 1
        else:
            pairs.append(Pair(None, column - 1))
            column -= 1
    return tuple(reversed(pairs))
