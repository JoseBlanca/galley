"""Epigraphs (spec section 22): the quotations set under a chapter's
heading, each ending at its source line, and a page that holds only one.

The rule is found per page on its body stream, after the heading lines
(spec section 2, step 2.3). It gives, for each epigraph, the positions of
its lines in the stream, whether its quotation is verse, its source
without the leading dash, and the record of that dash's removal.
"""

import statistics
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import assert_never

from galley.body_measures import median_word_height
from galley.model import BlockKind, ChangeReason, WordChange
from galley.structure._lines import PlacedLine
from galley.structure._measures import Edges, line_has_letter_or_digit
from galley.structure._runs import (
    CHAPTER_LEVEL,
    BodyRun,
    EpigraphParts,
    QuotationForm,
)

# Spec section 22, rule 2: every line of an epigraph run starts at least
# 20 pt right of the body column's left edge (Turney's quotations 32 to
# 46 pt, Haynes' 26.6 to 31).
_RUN_INDENT_MIN_PT = 20.0
# Spec section 22, rule 2: the next run's first line starts within 3 pt of
# the left side of the run before.
_NEXT_RUN_LEFT_PT = 3.0
# Spec section 22, rule 3: the dashes that may start a source line, alone
# or several ("—-" in Haynes' OCR).
_SOURCE_DASHES = "—–-"
# Spec section 22, rule 3: a dashed source line's height is at most 0.92 of
# the quotation's median line height (Haynes: 0.73 to 0.90, on all 21).
_DASHED_SOURCE_HEIGHT_SHARE = 0.92
# Spec section 22, rule 3: a source set flush right starts at least 60 pt
# right of the quotation's leftmost left side (Turney: 100.3 to 244.6; a
# verse turnover line lies 32 pt right in Haynes' page 87) and ends no
# more than 5 pt left of its rightmost right side (Turney's page 229: 4.5).
_FLUSH_RIGHT_SOURCE_LEFT_PT = 60.0
_FLUSH_RIGHT_SOURCE_RIGHT_PT = 5.0
# Spec section 22, rule 3, "A source over several lines": a flush-right
# source's first lines may start only 10 pt right of the quotation's
# leftmost left side (Turney's page 56: 12.5 and 49.2 pt).
_SOURCE_FIRST_LINES_LEFT_PT = 10.0
# Spec section 22, rule 5: a page of its own holds at most 10 lines with a
# letter or digit (a preface's last page signed at the right has more;
# Turney's has 6).
_PAGE_OF_ITS_OWN_MAX_LINES = 10
# Spec section 22, "Verse": a turnover line lies at least 15 pt right of
# the quotation's leftmost left side; verse lines end at least 80 pt short
# of the body column's right edge (Haynes 94 to 186, prose 0 to 67).
_TURNOVER_PT = 15.0
_VERSE_SHORT_PT = 80.0
_VERSE_MIN_LINES = 2
# Spec section 22, "Verse": passed over at a line's start before its
# first letter is looked at: quotation marks, full stops, ellipses, spaces.
_VERSE_START_PASSED = "\"'‘’“”«»„.… "


@dataclass(frozen=True, slots=True, kw_only=True)
class Epigraph:
    """One epigraph of a page's body stream, by the positions of its lines
    in the stream: `start`, its first line, which is a stray mark when one
    comes before the quotation; `quotation`, the quotation's lines;
    `stray_marks`, the lines with no letter or digit passed over in it, to
    be removed as stray marks; `source_lines`, the source's lines, which
    end it. `source` is the source lines' words joined by single spaces,
    without the leading dash, and `source_dash` the record of that dash's
    removal, None when the source starts with none."""

    start: int
    quotation: tuple[int, ...]
    stray_marks: tuple[int, ...]
    source_lines: tuple[int, ...]
    form: QuotationForm
    source: str
    source_dash: WordChange | None

    @property
    def end(self) -> int:
        """The position of the line after the last source line."""
        return self.source_lines[-1] + 1


def _line_height(line: PlacedLine) -> float:
    """The line height (spec section 1): the median height of its words."""
    return median_word_height(line.line.words)


def _starts_with_dash(line: PlacedLine) -> bool:
    """Whether the first word of `line` starts with a dash, "—", "–" or
    "-" (spec section 22, rule 3)."""
    return bool(line.line.words) and line.line.words[0].text[:1] in _SOURCE_DASHES


class _SourceShape(StrEnum):
    """How a source line shows it is one (spec section 22, rule 3)."""

    DASHED = "dashed"
    FLUSH_RIGHT = "flush_right"


def _is_smaller(line: PlacedLine, quotation: Sequence[PlacedLine]) -> bool:
    """Whether `line`'s height is at most 0.92 of the median line height of
    `quotation`."""
    quotation_height = statistics.median(_line_height(other) for other in quotation)
    return _line_height(line) <= _DASHED_SOURCE_HEIGHT_SHARE * quotation_height


def _ends_flush_right(line: PlacedLine, quotation: Sequence[PlacedLine]) -> bool:
    """Whether `line` ends no more than 5 pt left of the rightmost right side
    of `quotation`."""
    rightmost = max(other.line.box.x1 for other in quotation)
    return line.line.box.x1 >= rightmost - _FLUSH_RIGHT_SOURCE_RIGHT_PT


def _starts_right_of(
    line: PlacedLine, quotation: Sequence[PlacedLine], distance: float
) -> bool:
    """Whether `line` starts at least `distance` right of the leftmost left
    side of `quotation`."""
    leftmost = min(other.line.box.x0 for other in quotation)
    return line.line.box.x0 >= leftmost + distance


def _source_shape(
    line: PlacedLine, quotation: Sequence[PlacedLine]
) -> _SourceShape | None:
    """Spec section 22, rule 3: `line`, after the lines `quotation` of its
    run, is a source line when it starts with a dash and is set in smaller
    type, or is set flush right under them; None when it is neither."""
    if not quotation:
        return None
    if _starts_with_dash(line) and _is_smaller(line, quotation):
        return _SourceShape.DASHED
    if _starts_right_of(
        line, quotation, _FLUSH_RIGHT_SOURCE_LEFT_PT
    ) and _ends_flush_right(line, quotation):
        return _SourceShape.FLUSH_RIGHT
    return None


def _continues_source(
    line: PlacedLine,
    first: PlacedLine,
    shape: _SourceShape,
    quotation: Sequence[PlacedLine],
) -> bool:
    """Spec section 22, rule 3, "A source over several lines": `line`, after
    a source line, keeps the shape of the source, whose first line is
    `first`: a dashed source's next line is in smaller type, starts with no
    dash and no more than 3 pt left of `first`; a flush-right source's is
    set flush right under the quotation and under `first`, at least 60 pt
    right of the quotation."""
    match shape:
        case _SourceShape.DASHED:
            return (
                not _starts_with_dash(line)
                and _is_smaller(line, quotation)
                and line.line.box.x0 >= first.line.box.x0 - _NEXT_RUN_LEFT_PT
            )
        case _SourceShape.FLUSH_RIGHT:
            return (
                _starts_right_of(line, quotation, _FLUSH_RIGHT_SOURCE_LEFT_PT)
                and _ends_flush_right(line, quotation)
                and _ends_flush_right(line, (first,))
            )
        case _:
            assert_never(shape)


def _source_first_lines(lines: Sequence[PlacedLine], quotation: tuple[int, ...]) -> int:
    """How many of the last lines of `quotation`, before a flush-right
    source line, are the source's first lines (spec section 22, rule 3, "A
    source over several lines"): each set flush right under the lines
    before it and starting at least 10 pt right of them, leaving at least
    one line of quotation."""
    count = 0
    while count < len(quotation) - 1:
        line = lines[quotation[-1 - count]]
        before = tuple(lines[number] for number in quotation[: -1 - count])
        if not (
            _ends_flush_right(line, before)
            and _starts_right_of(line, before, _SOURCE_FIRST_LINES_LEFT_PT)
        ):
            break
        count += 1
    return count


def _text_past_opening_marks(line: PlacedLine) -> str:
    """The line's text from its first character that is not passed over by
    the verse test: a quotation mark, a full stop, an ellipsis or a space."""
    text = " ".join(word.text for word in line.line.words)
    return text.lstrip(_VERSE_START_PASSED)


def _form(quotation: Sequence[PlacedLine], column: Edges) -> QuotationForm:
    """Spec section 22, "Verse": a quotation of at least 2 lines is verse
    when every line after its first starts with a capital or is a turnover
    line, and every line ends at least 80 pt short of the column's right
    edge or one of them is a turnover line."""
    if len(quotation) < _VERSE_MIN_LINES:
        return QuotationForm.PROSE
    leftmost = min(line.line.box.x0 for line in quotation)
    turnovers = tuple(
        line.line.box.x0 >= leftmost + _TURNOVER_PT for line in quotation[1:]
    )
    starts = all(
        _text_past_opening_marks(line)[:1].isupper() or turnover
        for line, turnover in zip(quotation[1:], turnovers, strict=True)
    )
    short = all(
        line.line.box.x1 <= column.right - _VERSE_SHORT_PT for line in quotation
    )
    return (
        QuotationForm.VERSE
        if starts and (short or any(turnovers))
        else QuotationForm.PROSE
    )


def _source(lines: Sequence[PlacedLine]) -> tuple[str, WordChange | None]:
    """The source lines' words joined by single spaces without the leading
    dashes, and the record of their removal (spec section 22, "The dash is
    look, not text"): the first word, or a word of dashes alone and the
    word after it, become the one word without its leading dashes."""
    texts = tuple(word.text for line in lines for word in line.line.words)
    if not texts or texts[0][:1] not in _SOURCE_DASHES:
        return " ".join(texts), None
    count = 2 if not texts[0].strip(_SOURCE_DASHES) and len(texts) > 1 else 1
    before = texts[:count]
    after = "".join(before).lstrip(_SOURCE_DASHES)
    change = WordChange(
        page_index=lines[0].page_index,
        before=before,
        after=(after,),
        reason=ChangeReason.SOURCE_DASH,
    )
    return " ".join((after, *texts[count:])), change


@dataclass(frozen=True, slots=True)
class _Run:
    """The positions of a run's quotation, stray marks and source lines."""

    quotation: tuple[int, ...]
    stray_marks: tuple[int, ...]
    source_lines: tuple[int, ...]


def _source_run(
    lines: Sequence[PlacedLine],
    quotation: tuple[int, ...],
    stray_marks: tuple[int, ...],
    source_line: int,
    end: int,
    shape: _SourceShape,
    left_min: float | None,
) -> _Run:
    """The run whose first source line, of `shape`, is at `source_line`
    after the lines `quotation`: a flush-right source takes the last lines
    of the quotation that are its first lines, and either takes the lines
    after it before `end`, none left of `left_min`, that keep its shape."""
    first_lines = (
        _source_first_lines(lines, quotation)
        if shape is _SourceShape.FLUSH_RIGHT
        else 0
    )
    kept = quotation[: len(quotation) - first_lines]
    kept_lines = tuple(lines[number] for number in kept)
    source = [*quotation[len(kept) :], source_line]
    number = source_line + 1
    while (
        number < end
        and (left_min is None or lines[number].line.box.x0 >= left_min)
        and _continues_source(lines[number], lines[source_line], shape, kept_lines)
    ):
        source.append(number)
        number += 1
    return _Run(kept, stray_marks, tuple(source))


def _run(
    lines: Sequence[PlacedLine],
    start: int,
    end: int,
    left_min: float | None,
) -> _Run | None:
    """The run of `lines` from `start` that ends at its source before `end`
    (spec section 22, rules 2 and 3), passing over lines with no letter or
    digit; None when a line before its source starts left of `left_min`
    (None for no bound, rule 5) or `end` comes first."""
    quotation: list[int] = []
    stray_marks: list[int] = []
    for number in range(start, end):
        line = lines[number]
        if not line_has_letter_or_digit(line.line):
            stray_marks.append(number)
            continue
        if left_min is not None and line.line.box.x0 < left_min:
            return None
        shape = _source_shape(line, tuple(lines[other] for other in quotation))
        if shape is not None:
            return _source_run(
                lines,
                tuple(quotation),
                tuple(stray_marks),
                number,
                end,
                shape,
                left_min,
            )
        quotation.append(number)
    return None


def _epigraph(
    lines: Sequence[PlacedLine], start: int, run: _Run, column: Edges
) -> Epigraph:
    """The epigraph of `run`, whose lines are among `lines` and whose first
    line, a stray mark or the quotation's, is at `start`: its source
    without the leading dash and that dash's removal, and its quotation's
    form against `column`, the edges the rule measures against."""
    source, source_dash = _source(tuple(lines[number] for number in run.source_lines))
    return Epigraph(
        start=start,
        quotation=run.quotation,
        stray_marks=run.stray_marks,
        source_lines=run.source_lines,
        form=_form(tuple(lines[number] for number in run.quotation), column),
        source=source,
        source_dash=source_dash,
    )


def _first_line(lines: Sequence[PlacedLine], start: int, end: int) -> int | None:
    """The position of the first line from `start` before `end` with a
    letter or digit, None when there is none."""
    return next(
        (
            number
            for number in range(start, end)
            if line_has_letter_or_digit(lines[number].line)
        ),
        None,
    )


def epigraph_column(
    lines: Sequence[PlacedLine], heading_lines: frozenset[int], column: Edges
) -> Edges | None:
    """The edges the epigraph rule measures against on a page whose body
    stream is `lines` (spec section 22, "The rule"): the left side of its
    leftmost line with a letter or digit that is not a heading line, one
    of the positions `heading_lines`, and the right edge of `column`, the
    page's body column; None when every line is a heading line."""
    lefts = tuple(
        line.line.box.x0
        for number, line in enumerate(lines)
        if number not in heading_lines and line_has_letter_or_digit(line.line)
    )
    return Edges(min(lefts), column.right) if lefts else None


def epigraphs_after_heading(
    lines: Sequence[PlacedLine], start: int, end: int, column: Edges
) -> tuple[Epigraph, ...]:
    """The epigraphs of `lines`, a page's body stream, from `start`, the
    position right after a level-1 heading block (and its chapter
    summary), to `end` at the latest, the position of the next heading line
    or the stream's end (spec section 22, rules 1 to 4). `column` is what
    `epigraph_column` gives. Each run of lines at least 20 pt right of the
    column's left edge that ends at a source is an epigraph; the next run
    starts within 3 pt of the left side of the one before; the first line
    that starts no run ends them, and a run without a source is none."""
    epigraphs: list[Epigraph] = []
    left_min = column.left + _RUN_INDENT_MIN_PT
    run_start = start
    while (first := _first_line(lines, run_start, end)) is not None:
        if epigraphs:
            before_left = min(
                lines[number].line.box.x0 for number in epigraphs[-1].quotation
            )
            if abs(lines[first].line.box.x0 - before_left) > _NEXT_RUN_LEFT_PT:
                break
        run = _run(lines, run_start, end, left_min)
        if run is None:
            break
        epigraphs.append(_epigraph(lines, run_start, run, column))
        run_start = run.source_lines[-1] + 1
    return tuple(epigraphs)


def page_epigraph(lines: Sequence[PlacedLine], column: Edges) -> Epigraph | None:
    """The epigraph that is the whole of `lines`, the body stream of a page
    with no heading line, or None (spec section 22, rule 5): one run of at
    most 10 lines with a letter or digit, a quotation of at least 1 line
    and its source last, at any indent. `column` is the page's body
    column."""
    run = _run(lines, 0, len(lines), None)
    if (
        run is None
        or run.source_lines[-1] != len(lines) - 1
        or len(run.quotation) + len(run.source_lines) > _PAGE_OF_ITS_OWN_MAX_LINES
    ):
        return None
    return _epigraph(lines, 0, run, column)


def epigraph_run(epigraph: Epigraph, shift: Callable[[int], int]) -> BodyRun:
    """The run of `epigraph`'s quotation and source lines, which are
    consecutive once its stray marks are taken out of the body stream:
    `shift` gives a line's position in the stream without them."""
    return BodyRun(
        start=shift(epigraph.quotation[0]),
        end=shift(epigraph.end),
        kind=BlockKind.EPIGRAPH,
        epigraph=EpigraphParts(
            quotation_lines=len(epigraph.quotation),
            form=epigraph.form,
            source=epigraph.source,
            source_dash=epigraph.source_dash,
        ),
    )


def page_epigraphs(
    lines: Sequence[PlacedLine],
    headings: Sequence[BodyRun],
    summaries: Sequence[BodyRun],
    column: Edges | None,
) -> tuple[Epigraph, ...]:
    """The epigraphs of `lines`, a page's body stream whose heading blocks
    are `headings` and chapter summaries `summaries` (spec section 22):
    those after each level-1 heading and its summary, up to the next
    heading; on a page with no heading line, the whole stream when it is
    one epigraph (rule 5). `column` is the page's body column, None when
    it has no body region."""
    if column is None:
        return ()
    if not headings:
        found = page_epigraph(lines, column)
        return () if found is None else (found,)
    heading_lines = frozenset(
        number for run in headings for number in range(run.start, run.end)
    )
    edges = epigraph_column(lines, heading_lines, column)
    if edges is None:
        return ()
    summary_ends = {run.start: run.end for run in summaries}
    limits = (*(run.start for run in headings[1:]), len(lines))
    return tuple(
        epigraph
        for heading, limit in zip(headings, limits, strict=True)
        if heading.level == CHAPTER_LEVEL
        for epigraph in epigraphs_after_heading(
            lines, summary_ends.get(heading.end, heading.end), limit, edges
        )
    )
