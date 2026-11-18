"""Headings (spec section 14): which lines of a page's body stream are
heading lines, how they group into heading blocks, each block's chapter
label and level.

Positions are PDF points, origin at the top left of the page; gaps are in
body line pitches."""

import re
import statistics
from collections.abc import Sequence
from collections.abc import Set as AbstractSet
from enum import StrEnum

from galley.body_measures import median_word_height
from galley.model import BlockKind, Line
from galley.structure._heads import starts_with_chapter_label_word
from galley.structure._lines import PlacedLine, is_centred
from galley.structure._measures import Edges
from galley.structure._runs import CHAPTER_LEVEL, SECTION_LEVEL, BodyRun, LabelLine

# Spec section 14, rule 4: a line in capitals has at least 0.7 of its
# letters upper case (every value from 0.5 to 0.9 gives the same blocks on
# the four books' body ranges); a line not in capitals needs a gap of at
# least 2.0 pitches above (1.5 adds a false block in Domesday, 2.5 loses
# one of its section headings) and 1.3 below (1.6 loses one).
_CAPITALS_SHARE_MIN = 0.7
_GAP_ABOVE_MIN_PITCHES = 2.0
_GAP_BELOW_MIN_PITCHES = 1.3
# Spec section 14, rule 2: one word of a heading line has at least 4
# letters, and at least half of its characters other than spaces are letters.
_WORD_MIN_LETTERS = 4
_LETTERS_SHARE_MIN = 0.5
# Spec section 14, rule 1: a page whose body regions hold fewer than 5
# lines may centre a heading between its body and band lines (Haskins'
# page 129).
_FEW_BODY_LINES = 5
# Spec section 14, rule 1, a flush-left line: its left side within 4 pt of
# the left edge (Haynes' labels lie 2.9 pt left to 2.3 pt right of their
# region's commonest edge, its bibliography's title 3.4 pt), its right side
# a quarter of the width short of the right edge; set apart by the gaps of
# rule 4, its last word does not end with a sign (Turney's flush-left lines
# that introduce a block quote, pages 93, 99, 100 and 160).
_FLUSH_LEFT_PT = 4.0
_FLUSH_LEFT_SHORT_SHARE = 0.25
_FLUSH_LEFT_GAP_ENDS = (".", ",", ";", ":", "?", "!")
# Spec section 14, a tall line: its line height at least 1.2 times the
# median of the page's body stream (Turney's labels are 1.2 to 1.4 times
# the body's, its titles 2.2 to 2.6; no line of its running text that tall
# but one, 0.77 pitch below the line before), and a gap above of at least
# 1.3 pitches.
_TALL_LINE_SHARE = 1.2
_TALL_GAP_ABOVE_MIN_PITCHES = 1.3
# Spec section 14: a page with more than 6 lines that tall has none, its
# median being that of smaller type (Domesday's pages 136 and 419 and
# Gierke's 50 have 13 to 18; pages with headings in the eight books at
# most 4; any limit from 4 to 10 gives the same, 17 November 2026).
_TALL_LINES_MAX = 6
# Spec section 14, "a continuation": at most 2.6 pitches below the heading
# line before it; when not centred, at least 0.9 of its letters upper case
# and a gap below of at least 1.5 pitches (Mariéjol's title that fills the
# column).
_CONTINUATION_MAX_PITCHES = 2.6
_CONTINUATION_CAPITALS_MIN = 0.9
_CONTINUATION_GAP_BELOW_MIN_PITCHES = 1.5
# Spec section 14, "Heading blocks": two heading lines are one block when
# the second is at most 2.6 pitches below the first (2.0 leaves a title
# apart from its label in Stubbs and Mariéjol; 3.5 joins Haskins' half-title
# to chapter I), or 4.0 after a chapter label alone (Domesday's stand 3.0
# to 3.4 above their titles).
_JOIN_MAX_PITCHES = 2.6
_JOIN_AFTER_LABEL_MAX_PITCHES = 4.0

# Spec section 14: a roman numeral alone as the OCR reads one, 1 to 5 of
# "IVXLCl1" with an optional ".", ("II", "Ill" for III).
_OCR_ROMAN_LABEL = re.compile(r"[IVXLCl1]{1,5}\.?")
# Spec section 14, rule 2: a word whose letters are a well-formed roman
# numeral, in any case ("(VIII)"), is not the long word a heading needs.
_ROMAN_NUMERAL = re.compile(
    r"(?=[ivxlcdm])m{0,3}(cm|cd|d?c{0,3})(xc|xl|l?x{0,3})(ix|iv|v?i{0,3})"
)
# Spec section 14, rule 3: a number or a range of numbers ("26.", "9—26").
_NUMBER_OR_RANGE = re.compile(r"[0-9]+(?:[-–—][0-9]+)?")


def _texts(line: PlacedLine) -> tuple[str, ...]:
    return tuple(word.text for word in line.line.words)


def _capitals_share(line: PlacedLine) -> float:
    """The share of the line's letters (`str.isalpha`) that are upper case;
    0 for a line without a letter."""
    letters = [c for text in _texts(line) for c in text if c.isalpha()]
    if not letters:
        return 0.0
    return sum(c.isupper() for c in letters) / len(letters)


def _is_chapter_label(line: PlacedLine) -> bool:
    """Whether the line is a chapter label (spec section 14): it starts with
    CHAPTER, CHAPITRE, ESSAY, PART, PARTIE, BOOK or LIVRE in any case, or
    it is one word, a roman numeral as the OCR reads one ("V", "Ill.")."""
    texts = _texts(line)
    if not texts:
        return False
    if _starts_with_label_word(line):
        return True
    return len(texts) == 1 and _OCR_ROMAN_LABEL.fullmatch(texts[0]) is not None


def _starts_with_label_word(line: PlacedLine) -> bool:
    """Whether the line's first word is a chapter label word (spec section
    3)."""
    return starts_with_chapter_label_word(_texts(line))


def _has_long_word(texts: Sequence[str]) -> bool:
    """Spec section 14, rule 2: a word of at least 4 letters that is not a
    roman numeral."""
    for text in texts:
        word_letters = "".join(c for c in text.lower() if c.isalpha())
        if (
            len(word_letters) >= _WORD_MIN_LETTERS
            and _ROMAN_NUMERAL.fullmatch(word_letters) is None
        ):
            return True
    return False


def _mostly_letters(texts: Sequence[str]) -> bool:
    characters = "".join(texts)
    return bool(characters) and (
        sum(c.isalpha() for c in characters) >= _LETTERS_SHARE_MIN * len(characters)
    )


def _ends_with_number(texts: Sequence[str]) -> bool:
    """Spec section 14, rule 3: a line of more than one word whose last word,
    without the punctuation around it, is a number or a range of numbers."""
    if len(texts) <= 1:
        return False
    last = texts[-1].strip(".,;:()[]")
    return _NUMBER_OR_RANGE.fullmatch(last) is not None


def _letter_count(line: PlacedLine) -> int:
    return sum(c.isalpha() for text in _texts(line) for c in text)


def _top(line: PlacedLine) -> float:
    return line.line.box.top


def _pitches(upper: PlacedLine, lower: PlacedLine, pitch: float) -> float | None:
    """How far the top of `lower` is below the top of `upper`, in pitches;
    None when the book has no pitch (0 pt)."""
    if pitch <= 0:
        return None
    return (_top(lower) - _top(upper)) / pitch


def _centred_between(line: PlacedLine, edges: Edges) -> bool:
    """Whether the line is centred, by section 6's rule 2, between `edges`."""
    return is_centred(PlacedLine(line.page_index, line.line, line.edges, edges))


def _gap_branch(lines: Sequence[PlacedLine], number: int, pitch: float) -> bool:
    """Spec section 14, rule 4, second branch: a gap of at least 2.0 pitches
    above (or the page's first line) and 1.3 below (or its last line). A
    book without a pitch measures no gap."""
    if number > 0:
        above = _pitches(lines[number - 1], lines[number], pitch)
        if above is None or above < _GAP_ABOVE_MIN_PITCHES:
            return False
    if number + 1 < len(lines):
        below = _pitches(lines[number], lines[number + 1], pitch)
        if below is None or below < _GAP_BELOW_MIN_PITCHES:
            return False
    return True


def _is_flush_left(line: PlacedLine) -> bool:
    """Spec section 14, rule 1: the line's left side lies within 4 pt of the
    left edge of its centring edges, and its right side a quarter of their
    width or more short of the right edge."""
    edges = line.centring_edges
    return (
        abs(line.line.box.x0 - edges.left) <= _FLUSH_LEFT_PT
        and edges.right - line.line.box.x1 >= _FLUSH_LEFT_SHORT_SHARE * edges.width
    )


def _is_heading_line(
    lines: Sequence[PlacedLine],
    number: int,
    pitch: float,
    side_edges: Edges | None,
    kept_head: Line | None,
) -> bool:
    """Spec section 14, rules 1 to 4, for the line at `number` of a page's
    body stream `lines`. `side_edges` are the sides of the page's body and
    band lines when its body holds fewer than 5 lines, else None;
    `kept_head` is the page's head line when section 3 left it in the text
    within 2 pitches of the median head top, which is not flush left
    unless it starts with a chapter label word."""
    line = lines[number]
    texts = _texts(line)
    centred = is_centred(line) or (
        side_edges is not None and _centred_between(line, side_edges)
    )
    flush_left = (
        not centred
        and _is_flush_left(line)
        and (line.line is not kept_head or _starts_with_label_word(line))
    )
    return (
        (centred or flush_left)
        and _mostly_letters(texts)
        and _has_long_word(texts)
        and not _ends_with_number(texts)
        and (
            _capitals_share(line) >= _CAPITALS_SHARE_MIN
            or (
                _gap_branch(lines, number, pitch)
                and not (flush_left and texts[-1].endswith(_FLUSH_LEFT_GAP_ENDS))
            )
        )
    )


def _line_height(line: PlacedLine) -> float:
    """The line height (spec section 1): the median height of its words, in
    points."""
    return median_word_height(line.line.words)


def _is_tall_line(
    lines: Sequence[PlacedLine],
    number: int,
    pitch: float,
    median_height: float,
    heading_lines: AbstractSet[int],
) -> bool:
    """Spec section 14, a tall line: the line at `number` of a page's body
    stream `lines` is at least 1.2 times `median_height`, the median line
    height of the stream, has at least 4 letters, passes rules 2 and 3, and
    lies at least 1.3 pitches below the line before, or is the page's first
    line, or follows a heading line, one of the positions
    `heading_lines`; a line with no letter or digit counts as no line."""
    line = lines[number]
    texts = _texts(line)
    if not (
        _line_height(line) >= _TALL_LINE_SHARE * median_height
        and _letter_count(line) >= _WORD_MIN_LETTERS
        and _mostly_letters(texts)
        and _has_long_word(texts)
        and not _ends_with_number(texts)
    ):
        return False
    # A line of marks, a speck, is passed over.
    before = next(
        (
            other
            for other in range(number - 1, -1, -1)
            if any(c.isalnum() for c in "".join(_texts(lines[other])))
        ),
        None,
    )
    if before is None or before in heading_lines:
        return True
    above = _pitches(lines[before], line, pitch)
    return above is not None and above >= _TALL_GAP_ABOVE_MIN_PITCHES


def _is_continuation(lines: Sequence[PlacedLine], number: int, pitch: float) -> bool:
    """Spec section 14, "a continuation": the line at `number` follows a
    heading line, has at least 4 letters, lies at most 2.6 pitches below
    it (4.0 below a chapter label), and is centred, or is in capitals (0.9)
    with a gap below of at least 1.5 pitches."""
    line = lines[number]
    below_heading = _pitches(lines[number - 1], line, pitch)
    reach = (
        _JOIN_AFTER_LABEL_MAX_PITCHES
        if _is_chapter_label(lines[number - 1])
        else _CONTINUATION_MAX_PITCHES
    )
    if (
        _letter_count(line) < _WORD_MIN_LETTERS
        or below_heading is None
        or below_heading > reach
    ):
        return False
    if is_centred(line):
        return True
    if number + 1 >= len(lines):
        return False
    below = _pitches(line, lines[number + 1], pitch)
    return (
        _capitals_share(line) >= _CONTINUATION_CAPITALS_MIN
        and below is not None
        and below >= _CONTINUATION_GAP_BELOW_MIN_PITCHES
    )


def _heading_line_numbers(
    lines: Sequence[PlacedLine],
    pitch: float,
    side_edges: Edges | None,
    kept_head: Line | None,
    never: frozenset[int],
) -> frozenset[int]:
    """The positions in `lines`, a page's body stream, of its heading lines
    (spec section 14, "The rule"): the lines rules 1 to 4 take, the tall
    lines, none on a page with more than `_TALL_LINES_MAX` lines that tall,
    each centred chapter label whose next line they take, and each
    continuation of a line they take. `pitch` is the body line pitch;
    `side_edges` the sides of the page's body and band lines when its body
    holds fewer than 5 lines, else None; `kept_head` the head line section
    3 left in the text near the head top, or None; `never` the positions of
    lines that are never heading lines."""
    by_rule = {
        number
        for number in range(len(lines))
        if number not in never
        and _is_heading_line(lines, number, pitch, side_edges, kept_head)
    }
    median_height = (
        statistics.median(_line_height(line) for line in lines) if lines else 0.0
    )
    tall_lines = sum(
        _line_height(line) >= _TALL_LINE_SHARE * median_height for line in lines
    )
    if lines and tall_lines <= _TALL_LINES_MAX:
        # In order, so that a tall line below a tall heading line follows a
        # heading line.
        for number in range(len(lines)):
            if number not in by_rule | never and _is_tall_line(
                lines, number, pitch, median_height, by_rule
            ):
                by_rule.add(number)
    labels = frozenset(
        number
        for number in range(len(lines) - 1)
        if number + 1 in by_rule
        and _is_chapter_label(lines[number])
        and is_centred(lines[number])
    )
    taken = frozenset(by_rule) | labels
    continuations = frozenset(
        number + 1
        for number in taken
        if number + 1 < len(lines)
        and number + 1 not in taken
        and _is_continuation(lines, number + 1, pitch)
    )
    return (taken | continuations) - never


class PageHead(StrEnum):
    """Whether a page's head line was removed as a running head, which
    decides the level of a heading on its first line."""

    RUNNING_HEAD = "running_head"
    NO_RUNNING_HEAD = "no_running_head"


def _joins(upper: PlacedLine, lower: PlacedLine, pitch: float) -> bool:
    """Spec section 14, "Heading blocks": two consecutive heading lines are
    one block when the second is at most 2.6 pitches below the first, or
    4.0 when the first is a chapter label alone."""
    below = _pitches(upper, lower, pitch)
    limit = (
        _JOIN_AFTER_LABEL_MAX_PITCHES if _is_chapter_label(upper) else _JOIN_MAX_PITCHES
    )
    return below is not None and below <= limit


def _side_edges(body: Sequence[PlacedLine], band: Sequence[PlacedLine]) -> Edges | None:
    """The sides of a page's body and band lines when its body holds fewer
    than 5 lines, between which a heading may be centred (spec section 14,
    rule 1); None otherwise."""
    if not body or len(body) >= _FEW_BODY_LINES:
        return None
    lines = (*body, *band)
    return Edges(
        min(line.line.box.x0 for line in lines),
        max(line.line.box.x1 for line in lines),
    )


def heading_runs(
    lines: Sequence[PlacedLine],
    band: Sequence[PlacedLine],
    pitch: float,
    head: PageHead,
    kept_head: Line | None,
    never: frozenset[int],
) -> tuple[BodyRun, ...]:
    """The heading blocks of `lines`, a page's body stream, in order (spec
    section 14). A block is level 1 when its first line is a chapter label
    (which a line starting with a label word is) or the first line of a page without a
    running head (`head`); level 2 otherwise. `band` are the lines of the
    page's band regions; `pitch` is the body line pitch, in points;
    `kept_head` the page's head line when section 3 left it in the text
    within 2 pitches of the book's median head top, else None; `never` the
    positions of the lines that are never heading lines, those of the head
    band alike to a running head."""
    numbers = sorted(
        _heading_line_numbers(lines, pitch, _side_edges(lines, band), kept_head, never)
    )
    groups: list[list[int]] = []
    for number in numbers:
        if (
            groups
            and groups[-1][-1] == number - 1
            and _joins(lines[number - 1], lines[number], pitch)
        ):
            groups[-1].append(number)
        else:
            groups.append([number])
    runs: list[BodyRun] = []
    for group in groups:
        first = lines[group[0]]
        # A line that starts with a label word is a chapter label.
        level_1 = _is_chapter_label(first) or (
            group[0] == 0 and head is PageHead.NO_RUNNING_HEAD
        )
        runs.append(
            BodyRun(
                start=group[0],
                end=group[-1] + 1,
                kind=BlockKind.HEADING,
                level=CHAPTER_LEVEL if level_1 else SECTION_LEVEL,
                label_line=(
                    LabelLine.FIRST
                    if _is_chapter_label(first) and len(group) > 1
                    else LabelLine.NONE
                ),
            )
        )
    return tuple(runs)
