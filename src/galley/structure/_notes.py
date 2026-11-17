"""Footnotes (spec section 11): where a note starts in a page's note lines,
two notes on one line, the marker of each note and its value, and a note
that runs over a page break.

`page_notes` cuts one page's note lines into notes; `footnotes` joins a
note that runs over a page break and gives each note its value, over the
whole book in page order.
"""

from collections.abc import Sequence
from dataclasses import dataclass, replace
from enum import StrEnum

from galley.structure._lines import (
    INDENT_MAX_PT,
    INDENT_MIN_PT,
    PlacedLine,
    first_word,
    hyphen_between,
    is_indented,
    with_words,
)
from galley.structure._markers import (
    NoteMarker,
    glued_sign_marker,
    note_marker,
    read_number,
)
from galley.wordlist import is_known_word

# Spec section 11, rule 2: a note's first line is indented from the band's
# left edge, the smallest left side among the page's note lines within 60
# pt of this line, so that each column of notes has its own.
_COLUMN_PT = 60.0
# Spec section 11, "Two notes on one line": a word of at most 2
# characters, after a gap of at least 10 pt (Domesday: 3 wrong cuts for 21
# more right ones than at 15 pt), after a word ending with one of these
# and before a word starting with a capital or a digit.
_LINE_MARKER_MAX_CHARACTERS = 2
# Spec section 11, "The marker of a note": one-letter words, which are no
# marker before a known word ("A Treatise", "I have"). A lower-case "a"
# before a capital is a marker: a note's text starts a sentence.
_ONE_LETTER_WORDS = frozenset({"A", "I"})
_LINE_MARKER_GAP_PT = 10.0
_ENDS_BEFORE_A_NOTE = (".", "'", "’", ":", ";", ")")


@dataclass(frozen=True, slots=True)
class PageNote:
    """A note cut from one page's note lines: its lines, the last possibly
    cut before a second note on the same line; its marker, the first word's
    or None; and whether it may continue the last note of the page before
    (the page's first note, without a marker and not indented)."""

    lines: tuple[PlacedLine, ...]
    marker: NoteMarker | None
    may_continue: bool


@dataclass(frozen=True, slots=True)
class Footnote:
    """A note of the book: its lines, over one page or two, in order; its
    marker, None when it has none; and its value, the number of spec
    section 11, "Its value", or None."""

    lines: tuple[PlacedLine, ...]
    marker: NoteMarker | None
    value: int | None


def _column_left(line: PlacedLine, lines: Sequence[PlacedLine]) -> float:
    """The band's left edge for `line` (spec section 11, rule 2)."""
    return min(
        other.line.box.x0
        for other in lines
        if abs(other.line.box.x0 - line.line.box.x0) <= _COLUMN_PT
    )


def _indent(line: PlacedLine, lines: Sequence[PlacedLine]) -> float:
    return line.line.box.x0 - _column_left(line, lines)


def _indent_marker(
    line: PlacedLine, lower_case_words: frozenset[str]
) -> NoteMarker | None:
    """The marker of a note started by its indent whose first word has no
    marker's form: the word, when it is one character and the next word
    starts with a capital ("«", "z"), unless it is the word "A" or "I"
    and the next word is known in `lower_case_words` ("A Treatise");
    the signs, when the word is 1 or 2 signs glued to a word that starts
    with a capital ("'There"); None otherwise (spec section 11, "The
    marker of a note")."""
    words = line.line.words
    if not words:
        return None
    glued = glued_sign_marker(words[0].text)
    if glued is not None:
        return glued
    if len(words) <= 1 or len(words[0].text) != 1 or not words[1].text[:1].isupper():
        return None
    if words[0].text in _ONE_LETTER_WORDS and is_known_word(
        words[1].text, lower_case_words
    ):
        return None
    return NoteMarker(words[0].text, "", read_number(words[0].text))


def _line_marker(before: str, word: str, after: str, gap: float) -> NoteMarker | None:
    """The marker of a second note that starts at `word` inside a note
    line, between the words `before` and `after`, `gap` points after
    `before`; None when no note starts there (spec section 11, "Two notes
    on one line")."""
    marker = note_marker(word)
    lone_letter = len(word) == 1 and word.isalpha() and word.islower()
    if (
        (marker is None and not lone_letter)
        or len(word) > _LINE_MARKER_MAX_CHARACTERS
        or gap < _LINE_MARKER_GAP_PT
        or not before.endswith(_ENDS_BEFORE_A_NOTE)
        or not (after[:1].isupper() or after[:1].isdigit())
    ):
        return None
    return marker if marker is not None else NoteMarker(word, "", read_number(word))


def _cut_line(line: PlacedLine) -> tuple[tuple[PlacedLine, NoteMarker | None], ...]:
    """The parts of a note line, each with the marker of the note it starts,
    the first part's None: one part when no second note starts in it."""
    words = line.line.words
    parts: list[tuple[int, NoteMarker | None]] = [(0, None)]
    for position in range(1, len(words) - 1):
        marker = _line_marker(
            words[position - 1].text,
            words[position].text,
            words[position + 1].text,
            words[position].box.x0 - words[position - 1].box.x1,
        )
        if marker is not None:
            parts.append((position, marker))
    ends = (*(start for start, _ in parts[1:]), len(words))
    return tuple(
        (with_words(line, words[start:end]), marker)
        for (start, marker), end in zip(parts, ends, strict=True)
    )


def page_notes(
    regions: Sequence[Sequence[PlacedLine]], lower_case_words: frozenset[str]
) -> tuple[PageNote, ...]:
    """The notes of one page's note lines, `regions` being the lines of each
    band region in reading order (spec section 11, "Where a note starts");
    `lower_case_words` is the word list in lower case, which tells the
    word "A" from a marker.

    A line starts a note when section 6's indent rule starts a block there;
    when its first word has a note marker's form and it is indented 5 to 40
    pt from the band's left edge; or when its first word has a marker's
    form that reads one more than the note before's. A word inside a line
    can start a note too ("Two notes on one line"). Any other line, the
    first of a later region too, is part of the note before. The page's
    first line always starts a note, and so does the first line of a later
    region indented 5 to 40 pt against its column (rule 4)."""
    page_lines = tuple(line for region in regions for line in region)
    notes: list[PageNote] = []
    for region in regions:
        for number, line in enumerate(region):
            word = first_word(line)
            marker = note_marker(word)
            indent = _indent(line, page_lines)
            indented = INDENT_MIN_PT <= indent <= INDENT_MAX_PT
            before = region[number - 1] if number > 0 else None
            by_indent = before is not None and (
                is_indented(line, before) and not hyphen_between(before, line)
            )
            last_value = notes[-1].marker.value if notes and notes[-1].marker else None
            starts = (
                not notes
                or by_indent
                or (marker is not None and indented)
                or (number == 0 and indented)
                or (
                    marker is not None
                    and marker.value is not None
                    and last_value is not None
                    and marker.value == last_value + 1
                )
            )
            parts = _cut_line(line)
            first_part, _ = parts[0]
            if starts:
                if marker is None and (by_indent or indented):
                    marker = _indent_marker(line, lower_case_words)
                notes.append(
                    PageNote(
                        (first_part,),
                        marker,
                        may_continue=not notes
                        and marker is None
                        and indent < INDENT_MIN_PT,
                    )
                )
            else:
                notes[-1] = replace(notes[-1], lines=(*notes[-1].lines, first_part))
            notes.extend(
                PageNote((part,), part_marker, may_continue=False)
                for part, part_marker in parts[1:]
            )
    return tuple(notes)


class Numbering(StrEnum):
    """How a book numbers its notes (spec section 11, "Its value")."""

    PER_PAGE = "per_page"
    BY_MARKER = "by_marker"


def book_numbering(pages: Sequence[Sequence[PageNote]]) -> Numbering:
    """How the book numbers its notes (spec section 11, "Its value"), from
    the notes of each of its pages: per page when, on at least half of the
    pages with a note whose marker reads as a number, the first such
    marker reads 1; by marker otherwise."""
    firsts = tuple(
        value
        for notes in pages
        if (
            value := next(
                (
                    note.marker.value
                    for note in notes
                    if note.marker is not None and note.marker.value is not None
                ),
                None,
            )
        )
        is not None
    )
    per_page = bool(firsts) and 2 * sum(value == 1 for value in firsts) >= len(firsts)
    return Numbering.PER_PAGE if per_page else Numbering.BY_MARKER


def footnotes(
    pages: Sequence[Sequence[PageNote]],
    has_body: Sequence[bool],
    numbering: Numbering,
) -> tuple[Footnote, ...]:
    """The book's footnotes, from the notes of each page in page order, with
    `has_body` saying for each page whether it has a body stream (spec
    section 11, "A note that runs over a page break" and "Its value").

    The first note of a page continues the last note of the page before
    when it may (`PageNote.may_continue`) and the last page before it with
    notes is the page before, pages with neither notes nor a body stream
    (blank, plate and excluded pages) aside. In a book numbered per page,
    the k-th note that starts on a page has the value k, a first note that
    may continue and does not being left uncounted; otherwise its value is
    what its marker reads."""
    joined: list[list[PageNote]] = []
    last_page_with_notes: int | None = None
    for page_number, notes in enumerate(pages):
        if not notes:
            continue
        starts = list(notes)
        if (
            starts[0].may_continue
            and last_page_with_notes is not None
            and not any(has_body[last_page_with_notes + 1 : page_number])
            and joined
        ):
            last = joined[-1][-1]
            joined[-1][-1] = replace(last, lines=last.lines + starts[0].lines)
            starts = starts[1:]
        if starts:
            joined.append(starts)
        last_page_with_notes = page_number
    return tuple(footnote for notes in joined for footnote in _valued(notes, numbering))


def _valued(notes: Sequence[PageNote], numbering: Numbering) -> tuple[Footnote, ...]:
    """The footnotes that start on one page, with their values. A first
    note that may continue one of the page before and does not, the end of
    a note that started elsewhere, is not counted and has no value."""
    leftover = notes[0].may_continue
    counted = notes[1:] if leftover else notes
    return (
        (Footnote(notes[0].lines, notes[0].marker, None),) if leftover else ()
    ) + tuple(
        Footnote(
            lines=note.lines,
            marker=note.marker,
            value=place
            if numbering is Numbering.PER_PAGE
            else (note.marker.value if note.marker is not None else None),
        )
        for place, note in enumerate(counted, start=1)
    )
