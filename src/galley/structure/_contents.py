"""The printed table of contents (spec section 30, rules 1 to 8): the
title of a contents run, and the run's body stream cut into entries, each
with its label, title, page number, leader dots and depth.

Positions are PDF points, origin at the top left of the page."""

import re
from collections.abc import Sequence
from dataclasses import dataclass

from galley.model import Removal, RemovalReason, Word
from galley.structure._heads import starts_with_chapter_label_word
from galley.structure._lines import PlacedLine, is_centred, starts_paragraph, with_words
from galley.structure._measures import (
    has_letter_or_digit,
    is_page_number_form,
    line_has_letter_or_digit,
    words_removal,
)
from galley.structure._summaries import dash_count

# Spec section 30, rule 4: an entry runs on to its next line only when that
# line lies at least 5 pt right of the left side of the entry's first line
# (the indent of section 6, rule 1, and of the index).
_RUN_ON_MIN_PT = 5.0
# Spec section 30, rule 3: an analytical summary has at least 2 lines and
# 2 inline page references, and at least one for every two of its lines
# (guessed; it changes nothing on the eight books).
_SUMMARY_MIN_LINES = 2
_SUMMARY_MIN_REFERENCES = 2
_SUMMARY_LINES_PER_REFERENCE = 2
# Spec section 30, rule 8: a topics entry of at least 2 lines holds at
# least 2 dashes (the test of a chapter summary, section 15, rule 4).
_TOPICS_MIN_LINES = 2
_TOPICS_MIN_DASHES = 2
# Spec section 30, rule 8: a chapter's depth, and that of a centred entry
# under a chapter's.
_CHAPTER_DEPTH = 1
_SECTION_DEPTH = 2

# Spec section 30, "Terms": an inline page reference, 1 to 3 digits with
# any of "(", ")", "." and "," around them.
_INLINE_REFERENCE = re.compile(r"[(),.]*[0-9]{1,3}[(),.]*")
# A range of two page-number forms joined by a dash, in one word ("26—36.")
# or in three ("107" "—" "128.").
_RANGE_DASHES = frozenset("-–—")
_RANGE_WORD = re.compile(
    r"(?P<first>[0-9]{1,3}|[ivxlcdm]+)[-–—](?P<second>[0-9]{1,3}[.,]?|[ivxlcdm]+[.,]?)"
)
_PAGES_WORDS = frozenset({"pp.", "p."})
# Leader dots are words made only of these.
_LEADER_CHARACTERS = frozenset(".•·…")
# Spec section 14: a roman numeral alone as the OCR reads one; rule 7 of
# section 30 asks for its ".".
_OCR_ROMAN = re.compile(r"[IVXLCl1]{1,5}\.?")
_OCR_ROMAN_WITH_DOT = re.compile(r"[IVXLCl1]{1,5}\.")
# Spec section 30, rule 7: a number of 1 or 2 digits with ".", and the
# English number words.
_NUMBER_LABEL = re.compile(r"[0-9]{1,2}\.")
_NUMBER_WORDS = frozenset(
    {
        "one",
        "two",
        "three",
        "four",
        "five",
        "six",
        "seven",
        "eight",
        "nine",
        "ten",
        "eleven",
        "twelve",
        "thirteen",
        "fourteen",
        "fifteen",
        "sixteen",
        "seventeen",
        "eighteen",
        "nineteen",
        "twenty",
    }
)
_SECTION_SIGN = "§"


def _texts(line: PlacedLine) -> tuple[str, ...]:
    return tuple(word.text for word in line.line.words)


def is_lone_label(line: PlacedLine) -> bool:
    """Spec section 30, "Terms": the line's first word is a chapter label
    word and it has at most one more word ("CHAPTER II.", "ESSAY I."), or
    it is a roman numeral alone as the OCR reads one."""
    texts = _texts(line)
    if starts_with_chapter_label_word(texts):
        return len(texts) <= _LONE_LABEL_MAX_WORDS
    return len(texts) == 1 and _OCR_ROMAN.fullmatch(texts[0]) is not None


_LONE_LABEL_MAX_WORDS = 2


def page_number_length(texts: Sequence[str]) -> int:
    """How many of the last words of `texts` are a page number (spec
    section 30, "Terms"): a page-number form, a range of two in one word
    or in three, with "pp." or "p." before it; 0 when the last word is
    none."""
    if not texts:
        return 0
    if (
        len(texts) >= _RANGE_WORDS
        and texts[-2] in _RANGE_DASHES
        and is_page_number_form(texts[-3])
        and is_page_number_form(texts[-1])
    ):
        length = _RANGE_WORDS
    elif is_page_number_form(texts[-1]) or _RANGE_WORD.fullmatch(texts[-1]):
        length = 1
    else:
        return 0
    if len(texts) > length and texts[-length - 1] in _PAGES_WORDS:
        length += 1
    return length


_RANGE_WORDS = 3


def _is_leader_dots(text: str) -> bool:
    return bool(text) and all(character in _LEADER_CHARACTERS for character in text)


def _is_inline_reference(text: str) -> bool:
    return _INLINE_REFERENCE.fullmatch(text) is not None


@dataclass(frozen=True, slots=True)
class ContentsTitle:
    """The start of a contents run (spec section 30, rule 1): the positions
    of the lines before its first line with a letter or a digit, removed as
    stray marks, and the position of its title, None when the first such
    line ends with a page number or is a lone label, or there is none."""

    stray_marks: tuple[int, ...]
    title: int | None


def contents_title(lines: Sequence[PlacedLine]) -> ContentsTitle:
    """The stray marks and the title of a contents run whose body stream
    starts with `lines`, the first page's (spec section 30, rule 1)."""
    first = next(
        (
            number
            for number, line in enumerate(lines)
            if line_has_letter_or_digit(line.line)
        ),
        None,
    )
    if first is None:
        return ContentsTitle(tuple(range(len(lines))), None)
    line = lines[first]
    title = None if page_number_length(_texts(line)) or is_lone_label(line) else first
    return ContentsTitle(tuple(range(first)), title)


@dataclass(frozen=True, slots=True, kw_only=True)
class ContentsEntry:
    """One entry of a printed contents (spec section 30): `lines` all its
    lines, for its origin; `title` the lines of its title, each with only
    its title's words, none when the title is empty; `label` its number as
    printed before the title, its words joined by single spaces, None when
    it has none; `page_number` likewise; `level` its depth, from 1; and
    `leader_dots` the removals of the leader dots before its page number,
    one per line."""

    lines: tuple[PlacedLine, ...]
    title: tuple[PlacedLine, ...]
    label: str | None
    page_number: str | None
    level: int
    leader_dots: tuple[Removal, ...]


def _pieces(lines: Sequence[PlacedLine]) -> tuple[tuple[PlacedLine, ...], ...]:
    """The lines cut into pieces where section 6's rule 1 or 2 starts a
    paragraph and before each lone label (spec section 30, rule 2); rule 3
    has no text edge on a contents page."""
    pieces: list[list[PlacedLine]] = []
    before: PlacedLine | None = None
    for line in lines:
        if not pieces or starts_paragraph(line, before) or is_lone_label(line):
            pieces.append([])
        pieces[-1].append(line)
        before = line
    return tuple(tuple(piece) for piece in pieces)


def is_analytical_summary(piece: Sequence[PlacedLine]) -> bool:
    """Spec section 30, rule 3: at least 2 lines, at least 2 inline page
    references, and at least one for every two lines. An inline page
    reference is neither the first nor the last word of its line."""
    references = sum(
        1
        for line in piece
        for word in line.line.words[1:-1]
        if _is_inline_reference(word.text)
    )
    return (
        len(piece) >= _SUMMARY_MIN_LINES
        and references >= _SUMMARY_MIN_REFERENCES
        and references * _SUMMARY_LINES_PER_REFERENCE >= len(piece)
    )


@dataclass(frozen=True, slots=True)
class _Raw:
    """An entry before its parts are taken: the lines of its lone label
    (none or one), its other lines, and whether it is an analytical
    summary."""

    label_lines: tuple[PlacedLine, ...]
    lines: tuple[PlacedLine, ...]
    summary: bool


def _raw_entries(lines: Sequence[PlacedLine]) -> tuple[_Raw, ...]:
    """The run's lines cut into entries (spec section 30, rules 2 to 5),
    each lone label joined to the entry after it; a lone label at the end
    of the run is an entry of its own with no other line."""
    raws: list[_Raw] = []
    label: tuple[PlacedLine, ...] = ()
    for piece in _pieces(lines):
        if is_lone_label(piece[0]):
            if label:
                raws.append(_Raw(label, (), summary=False))
            label = (piece[0],)
            piece = piece[1:]
            if not piece:
                continue
        if is_analytical_summary(piece):
            raws.append(_Raw(label, piece, summary=True))
            label = ()
            continue
        current: list[PlacedLine] = []
        for position, line in enumerate(piece):
            if not line_has_letter_or_digit(line.line) and not current and raws:
                # A line with no letter or digit joins the entry before it.
                last = raws[-1]
                raws[-1] = _Raw(last.label_lines, (*last.lines, line), last.summary)
                continue
            current.append(line)
            after = piece[position + 1] if position + 1 < len(piece) else None
            if (
                after is None
                or page_number_length(_texts(line)) > 0
                or (
                    after.line.box.x0 - current[0].line.box.x0 < _RUN_ON_MIN_PT
                    and line_has_letter_or_digit(after.line)
                )
            ):
                raws.append(_Raw(label, tuple(current), summary=False))
                label = ()
                current = []
    if label:
        raws.append(_Raw(label, (), summary=False))
    return tuple(raws)


@dataclass(frozen=True, slots=True)
class _Placed:
    """A word of an entry with the line it is on, by the line's position in
    the entry."""

    line: int
    word: Word


def _label_length(texts: Sequence[str]) -> int:
    """How many of the first words of `texts` are an entry's label by rule
    7 of spec section 30, the words with no letter or digit before it
    among them; 0 when it has none or no word follows it."""
    marks = 0
    while marks < len(texts) and not has_letter_or_digit(texts[marks]):
        marks += 1
    rest = texts[marks:]
    if not rest:
        return 0
    first = rest[0]
    if (
        _NUMBER_LABEL.fullmatch(first)
        or _OCR_ROMAN_WITH_DOT.fullmatch(first)
        or first.rstrip(".").lower() in _NUMBER_WORDS
    ):
        length = 1
    elif starts_with_chapter_label_word(rest) or first == _SECTION_SIGN:
        length = 2
    else:
        return 0
    return marks + length if len(rest) > length else 0


def _topics(raw: _Raw, title: Sequence[str]) -> bool:
    """Spec section 30, rule 8: an analytical summary, or an entry of at
    least 2 lines whose title holds at least 2 dashes."""
    return raw.summary or (
        len(raw.lines) >= _TOPICS_MIN_LINES and dash_count(title) >= _TOPICS_MIN_DASHES
    )


def _parts(
    raw: _Raw,
) -> tuple[str | None, tuple[_Placed, ...], str | None, tuple[Removal, ...]]:
    """An entry's label, title words, page number and leader-dot removals
    (spec section 30, rules 5 to 7)."""
    placed = tuple(
        _Placed(number, word)
        for number, line in enumerate(raw.lines)
        for word in line.line.words
    )
    if raw.summary:
        label = _joined(raw.label_lines) if raw.label_lines else None
        return label, placed, None, ()
    texts = tuple(item.word.text for item in placed)
    number_length = page_number_length(texts)
    page_number = None
    dots: tuple[_Placed, ...] = ()
    words_before = len(placed) - number_length
    leading = words_before
    while leading > 0 and _is_leader_dots(texts[leading - 1]):
        leading -= 1
    if number_length and leading > 0:
        page_number = " ".join(texts[words_before:])
        dots = placed[leading:words_before]
        placed = placed[:leading]
    if raw.label_lines:
        label: str | None = _joined(raw.label_lines)
    else:
        length = _label_length(tuple(item.word.text for item in placed))
        label = " ".join(item.word.text for item in placed[:length]) or None
        placed = placed[length:]
    removals = tuple(
        words_removal(
            raw.lines[number].page_index,
            tuple(item.word for item in dots if item.line == number),
            RemovalReason.LEADER_DOTS,
        )
        for number in sorted({item.line for item in dots})
    )
    return label, placed, page_number, removals


def _joined(lines: Sequence[PlacedLine]) -> str:
    return " ".join(word.text for line in lines for word in line.line.words)


def contents_entries(lines: Sequence[PlacedLine]) -> tuple[ContentsEntry, ...]:
    """The entries of a contents run whose body stream, its pages' in page
    order, after its title and stray marks, is `lines` (spec section 30,
    rules 2 to 8)."""
    entries: list[ContentsEntry] = []
    # The depth of the nearest entry before that is not a topics entry, and
    # whether an entry of the run has a label that starts with a chapter
    # label word.
    nearest: int | None = None
    chapters_seen = False
    for raw in _raw_entries(lines):
        label, placed, page_number, removals = _parts(raw)
        title_texts = tuple(item.word.text for item in placed)
        chapter = label is not None and starts_with_chapter_label_word(
            tuple(label.split(" ")[_marks_before(label) :])
        )
        first = (raw.label_lines + raw.lines)[0]
        if _topics(raw, title_texts):
            level = nearest + 1 if nearest is not None else _CHAPTER_DEPTH
        elif chapter:
            level = _CHAPTER_DEPTH
        elif chapters_seen and is_centred(raw.lines[0] if raw.lines else first):
            level = _SECTION_DEPTH
        else:
            level = _CHAPTER_DEPTH
        if not _topics(raw, title_texts):
            nearest = level
        chapters_seen = chapters_seen or chapter
        entries.append(
            ContentsEntry(
                lines=raw.label_lines + raw.lines,
                title=tuple(
                    with_words(
                        raw.lines[number],
                        tuple(item.word for item in placed if item.line == number),
                    )
                    for number in sorted({item.line for item in placed})
                ),
                label=label,
                page_number=page_number,
                level=level,
                leader_dots=removals,
            )
        )
    return tuple(entries)


def _marks_before(label: str) -> int:
    """How many of the label's first words hold no letter or digit."""
    words = label.split(" ")
    marks = 0
    while marks < len(words) and not has_letter_or_digit(words[marks]):
        marks += 1
    return marks
