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

from galley.model import Word
from galley.structure._lines import (
    INDENT_MAX_PT,
    INDENT_MIN_PT,
    PlacedLine,
    first_word,
    hyphen_between,
    is_indented,
    is_short,
    with_words,
)
from galley.structure._markers import (
    NoteMarker,
    glued_sign_marker,
    note_marker,
    read_number,
)
from galley.structure._references import are_confused
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
# Spec section 11, "Two notes on one line", the cuts of 23 November 2026:
# a marker that reads the next note's value is cut after a gap of 8 pt
# (Domesday's page 134 sets "5" 9.9 pt and "6" 9.3 pt after the note
# before); a word of one character that reads a number, after 20 pt,
# whatever follows (page 114, 41.9 pt; the other gaps of note lines reach
# 14.0 pt at the 99th percentile). Guessed between those, not varied.
_NEXT_MARKER_GAP_PT = 8.0
# Spec section 11, "Two notes on one line": also the gap between the
# columns of a row of notes, 23 to 37 pt before the markers that top
# Kadesh's columns on its pages 32 and 66.
_WIDE_GAP_PT = 20.0
_ENDS_BEFORE_A_NOTE = (".", "'", "’", ":", ";", ")")
# Spec section 11, "Two notes on one line": the end of a quotation, a full
# stop, "?" or "!" and a closing quotation mark ("Rege.'"), after which a
# marker that reads the next value starts a note whatever the gap.
_QUOTATION_ENDS = tuple(
    stop + quote for stop in ".?!" for quote in ("'", "’", '"', "”")
)
# Spec section 11, "Two notes on one line": a word that stands for a
# marker the OCR misread ("«", "-", "&", ":<", "B"), of at most 2
# characters, none a digit.
_STAND_IN_MAX_CHARACTERS = 2
# Spec section 11, "Its value": the scores of a page's numbering. A
# marker that reads its note's value scores 1, one a confused digit away
# 0.5; each number skipped costs 0.5, at most 2 on a page, and each note
# left out 0.25, or 0.1 for a note with no marker. Chosen on 23 November
# 2026 with galley-eval on the whole Domesday: 1,488 notes whose reference
# is right, against 1,487 with costs of 0.4 and 0.2, which lost 6 notes
# right before. The 0.1 lets the 13 unmarked rows of a table on page 418
# be left out before notes 1 to 3 (3 notes gained, none lost); guessed,
# below 3 matches over 13 rows, not varied further.
_MATCH_SCORE = 1.0
_CONFUSED_SCORE = 0.5
_JUMP_COST = 0.5
_MAX_JUMPS = 2
_SKIP_COST = 0.25
_UNMARKED_SKIP_COST = 0.1
# Spec section 11, rule 5: the marker and the word after it.
_MARKER_AND_A_WORD = 2


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
    marker, None when it has none; its value, the number of spec section
    11, "Its value", or None; and whether its page's numbering counts it,
    false for a note the numbering leaves out, which takes no reference."""

    lines: tuple[PlacedLine, ...]
    marker: NoteMarker | None
    value: int | None
    counted: bool


class _LinePlace(StrEnum):
    """Where a note line is in its band region."""

    TOP = "the region's first line"
    BELOW_THE_TOP = "a later line"


class _ValueSource(StrEnum):
    """Where the value of the note a line's first words belong to comes
    from: what its marker reads, or its place after a note whose marker
    reads one."""

    MARKER = "its marker"
    PLACE = "its place"


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


def _line_marker(
    before: str,
    word: str,
    after: str,
    gap: float,
    next_value: int | None,
    place: _LinePlace,
) -> NoteMarker | None:
    """The marker of a second note that starts at `word` inside a note
    line, between the words `before` and `after`, `gap` points after
    `before`, where the next note's value would be `next_value`; None when
    no note starts there (spec section 11, "Two notes on one line"). On
    the first line of a band region, `place` `TOP`, a number after a
    column's gap starts a note whatever `before` ends with."""
    marker = note_marker(word)
    if (
        place is _LinePlace.TOP
        and gap >= _WIDE_GAP_PT
        and marker is not None
        and marker.value is not None
        and marker.marker.rstrip(".").isdigit()
        and after[:1].isupper()
    ):
        return marker
    lone_letter = len(word) == 1 and word.isalpha() and word.islower()
    if not before.endswith(_ENDS_BEFORE_A_NOTE) or not after:
        return None
    reads_next = (
        marker is not None
        and marker.marker.rstrip(".").isdigit()
        and next_value is not None
        and marker.value == next_value
    )
    if reads_next and before.endswith(_QUOTATION_ENDS) and after[:1].isupper():
        return marker
    if reads_next and gap >= _NEXT_MARKER_GAP_PT and not after[:1].islower():
        return marker
    if (
        len(word) == 1
        and gap >= _WIDE_GAP_PT
        and (reading := read_number(word)) is not None
    ):
        return marker if marker is not None else NoteMarker(word, "", reading)
    if (
        (marker is None and not lone_letter)
        or len(word) > _LINE_MARKER_MAX_CHARACTERS
        or not (after[:1].isupper() or after[:1].isdigit())
    ):
        return None
    reads_next = (
        marker is not None and next_value is not None and marker.value == next_value
    )
    if gap < (_NEXT_MARKER_GAP_PT if reads_next else _LINE_MARKER_GAP_PT):
        return None
    return marker if marker is not None else NoteMarker(word, "", read_number(word))


def _reading_in_line(words: Sequence[Word], start: int) -> int | None:
    """What the first marker of a note inside a line reads, among `words`
    from position `start` on: a word of 1 to 3 digits after a word that
    ends as before a note and a gap of at least 8 pt, before a word that
    starts with a capital; None when there is none."""
    for position in range(max(start, 1), len(words) - 1):
        marker = note_marker(words[position].text)
        if (
            marker is not None
            and marker.value is not None
            and marker.marker.rstrip(".").isdigit()
            and words[position - 1].text.endswith(_ENDS_BEFORE_A_NOTE)
            and words[position].box.x0 - words[position - 1].box.x1
            >= _NEXT_MARKER_GAP_PT
            and words[position + 1].text[:1].isupper()
        ):
            return marker.value
    return None


def _reads_after_next(following: int | None, next_value: int) -> bool:
    """Whether `following`, what a later marker reads, is the number after
    `next_value`, or more than `next_value` and one confused digit away
    from that number (a 5 read 6 after a 4): the number between is a
    marker the OCR misread (spec section 11, rule 5 and "Two notes on one
    line")."""
    return following is not None and (
        following == next_value + 1
        or (following > next_value and are_confused(following, next_value + 1))
    )


def _is_stand_in(word: str) -> bool:
    """Whether `word` may stand for a marker the OCR misread: 1 or 2
    characters, no digit, reading no number, and of 2 characters only
    when neither is a letter ("«", "&", ":<", "B")."""
    return (
        0 < len(word) <= _STAND_IN_MAX_CHARACTERS
        and not any(character.isdigit() for character in word)
        and read_number(word) is None
        and (len(word) == 1 or not any(character.isalpha() for character in word))
    )


def _stand_in_marker(
    before: str,
    word: str,
    after: str,
    gap: float,
    next_value: int,
    following: int | None,
    source: _ValueSource,
) -> NoteMarker | None:
    """The marker of a second note that starts at `word`, a word that
    stands for a misread marker, inside a note line between `before` and
    `after`, `gap` points after `before`, where the next note's value would
    be `next_value` and `following` is what the next marker of the page
    after `word` reads, None when none reads a number; None when no note
    starts there (spec section 11, "Two notes on one line"). `source` says
    whether the value of the note the line's words so far belong to is its
    marker's reading."""
    if (
        not _is_stand_in(word)
        or word in _ONE_LETTER_WORDS
        or not before.endswith(_ENDS_BEFORE_A_NOTE)
        or gap < _LINE_MARKER_GAP_PT
        or note_marker(after) is not None
    ):
        return None
    between = _reads_after_next(following, next_value)
    last = (
        following is None
        and gap >= _WIDE_GAP_PT
        and source is _ValueSource.MARKER
        and after[:1].isupper()
        and not word.islower()
    )
    return NoteMarker(word, "", None) if between or last else None


def _cut_line(
    line: PlacedLine,
    value: int | None,
    place: _LinePlace,
    source: _ValueSource,
    following: int | None,
) -> tuple[tuple[PlacedLine, NoteMarker | None], ...]:
    """The parts of a note line, each with the marker of the note it starts,
    the first part's None: one part when no second note starts in it.
    `value` is that of the note the first part belongs to, None when not
    known, and `source` where it comes from; `place` says whether the line
    is the first of its region; `following` is what the first marker of the
    page's later note lines reads, None when none reads a number."""
    words = line.line.words
    parts: list[tuple[int, NoteMarker | None]] = [(0, None)]
    for position in range(1, len(words) - 1):
        next_value = value + 1 if value is not None else None
        gap = words[position].box.x0 - words[position - 1].box.x1
        marker = _line_marker(
            words[position - 1].text,
            words[position].text,
            words[position + 1].text,
            gap,
            next_value,
            place,
        )
        if marker is None and next_value is not None:
            in_line = _reading_in_line(words, position + 1)
            marker = _stand_in_marker(
                words[position - 1].text,
                words[position].text,
                words[position + 1].text,
                gap,
                next_value,
                in_line if in_line is not None else following,
                source,
            )
        if marker is not None:
            parts.append((position, marker))
            value = marker.value if marker.value is not None else next_value
            source = (
                _ValueSource.MARKER if marker.value is not None else _ValueSource.PLACE
            )
    ends = (*(start for start, _ in parts[1:]), len(words))
    return tuple(
        (with_words(line, words[start:end]), marker)
        for (start, marker), end in zip(parts, ends, strict=True)
    )


def _under_a_short_line(
    region: Sequence[PlacedLine],
    number: int,
    marker: NoteMarker | None,
    expected: int | None,
) -> bool:
    """Whether line `number` of `region`, whose first word's marker is
    `marker`, starts a note by spec section 11's rule 5: a marker of one
    character before a capital, under a line that ends short and no hyphen;
    a sign only when the next line's marker reads `expected`, the value
    the note before should have, plus 2."""
    line = region[number]
    words = line.line.words
    if (
        marker is None
        or len(marker.marker) != 1
        or marker.rest
        or number == 0
        or len(words) < _MARKER_AND_A_WORD
        or not words[1].text[:1].isupper()
    ):
        return False
    before = region[number - 1]
    if not is_short(before) or hyphen_between(before, line):
        return False
    if marker.value is not None:
        return True
    in_line = _reading_in_line(words, 2)
    next_line = (
        note_marker(first_word(region[number + 1]))
        if number + 1 < len(region)
        else None
    )
    following = (
        in_line
        if in_line is not None
        else (next_line.value if next_line is not None else None)
    )
    return expected is not None and _reads_after_next(following, expected + 1)


def page_notes(
    regions: Sequence[Sequence[PlacedLine]], lower_case_words: frozenset[str]
) -> tuple[PageNote, ...]:
    """The notes of one page's note lines, `regions` being the lines of each
    band region in reading order (spec section 11, "Where a note starts");
    `lower_case_words` is the word list in lower case, which tells the
    word "A" from a marker.

    A line starts a note when section 6's indent rule starts a block there;
    when its first word has a note marker's form and it is indented 5 to 40
    pt from the band's left edge; when its first word has a marker's form
    that reads one more than the note before's, or, of one character, one
    more than the last number the page's markers read plus the notes
    after it; or when its first word is a marker of one character under a
    short line (rule 5, `_under_a_short_line`). A word inside a line
    can start a note too ("Two notes on one line"), on a region's first
    line a number after the gap between columns whatever comes before it.
    The page's first note, when its first line is a row of notes, takes
    signs glued to its first word as its marker ("The marker of a note"),
    and so continues no note of the page before. Any other line, the
    first of a later region too, is part of the note before. The page's
    first line always starts a note, and so does the first line of a later
    region indented 5 to 40 pt against its column (rule 4)."""
    page_lines = tuple(line for region in regions for line in region)
    readings = tuple(
        marker.value if (marker := note_marker(first_word(line))) else None
        for line in page_lines
    )
    notes: list[PageNote] = []
    line_count = 0
    for region in regions:
        parts_before = 1
        for number, line in enumerate(region):
            line_count += 1
            following = next(
                (reading for reading in readings[line_count:] if reading is not None),
                None,
            )
            word = first_word(line)
            marker = note_marker(word)
            indent = _indent(line, page_lines)
            indented = INDENT_MIN_PT <= indent <= INDENT_MAX_PT
            before = region[number - 1] if number > 0 else None
            by_indent = before is not None and (
                is_indented(line, before) and not hyphen_between(before, line)
            )
            last_value = notes[-1].marker.value if notes and notes[-1].marker else None
            expected = _expected_value(notes)
            starts = (
                not notes
                or by_indent
                or (marker is not None and indented)
                or (number == 0 and indented)
                or _under_a_short_line(region, number, marker, expected)
                or _under_a_row(line, marker, parts_before)
                or (
                    marker is not None
                    and marker.value is not None
                    and (
                        (last_value is not None and marker.value == last_value + 1)
                        or (
                            expected is not None
                            and len(marker.marker) == 1
                            and marker.value == expected + 1
                        )
                    )
                )
            )
            if starts and marker is not None and marker.value is not None:
                value, source = marker.value, _ValueSource.MARKER
            elif starts:
                value = expected + 1 if expected is not None else None
                source = _ValueSource.PLACE
            else:
                value = expected
                source = (
                    _ValueSource.MARKER
                    if notes and notes[-1].marker and notes[-1].marker.value is not None
                    else _ValueSource.PLACE
                )
            parts = _cut_line(
                line,
                value,
                _LinePlace.TOP if number == 0 else _LinePlace.BELOW_THE_TOP,
                source,
                following,
            )
            parts_before = len(parts)
            first_part, _ = parts[0]
            if starts:
                if marker is None and (by_indent or indented):
                    marker = _indent_marker(line, lower_case_words)
                if marker is None and not notes and len(parts) > 1:
                    marker = glued_sign_marker(word)
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


def _under_a_row(
    line: PlacedLine, marker: NoteMarker | None, parts_before: int
) -> bool:
    """Whether `line`, whose first word's marker is `marker`, starts a note
    under a row of notes, the line before it in its region having been cut
    into `parts_before` notes (spec section 11, rule 6): a marker of one
    character before a capital, under a line of two notes or more."""
    words = line.line.words
    return (
        parts_before > 1
        and marker is not None
        and len(marker.marker) == 1
        and not marker.rest
        and len(words) >= _MARKER_AND_A_WORD
        and words[1].text[:1].isupper()
    )


def _expected_value(notes: Sequence[PageNote]) -> int | None:
    """The value the last of `notes` should have: what the last marker that
    reads a number reads, plus the notes after it; None when no marker
    reads one."""
    for back, note in enumerate(reversed(notes)):
        if note.marker is not None and note.marker.value is not None:
            return note.marker.value + back
    return None


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
    the notes that start on a page take the values of `page_values`, a
    first note that may continue and does not being left uncounted;
    otherwise a note's value is what its marker reads."""
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
    """The footnotes that start on one page, with their values: in a book
    numbered per page, those of `page_values`, a note it leaves out not
    counted; otherwise what their markers read. A first note that may
    continue one of the page before and does not, the end of a note that
    started elsewhere, is not counted and has no value."""
    leftover = notes[0].may_continue
    counted = notes[1:] if leftover else notes
    readings = tuple(
        note.marker.value if note.marker is not None else None for note in counted
    )
    values = (
        page_values(readings, tuple(note.marker is None for note in counted))
        if numbering is Numbering.PER_PAGE
        else readings
    )
    return (
        (Footnote(notes[0].lines, notes[0].marker, None, counted=True),)
        if leftover
        else ()
    ) + tuple(
        Footnote(
            lines=note.lines,
            marker=note.marker,
            value=value,
            counted=value is not None or numbering is not Numbering.PER_PAGE,
        )
        for note, value in zip(counted, values, strict=True)
    )


def _reading_score(reading: int | None, value: int) -> float:
    """The score of a note whose marker reads `reading` given `value`."""
    if reading is None:
        return 0.0
    if reading == value:
        return _MATCH_SCORE
    return _CONFUSED_SCORE if are_confused(reading, value) else 0.0


# A numbering of a page's notes so far: its score, minus the numbers it
# skipped and the notes it left out, and the values, None for a note left
# out.
type _Numbering = tuple[float, int, tuple[int | None, ...]]


def page_values(
    readings: Sequence[int | None], unmarked: Sequence[bool]
) -> tuple[int | None, ...]:
    """The values of a page's notes in a book numbered per page, whose
    markers read `readings`, None for one that reads no number, and of
    which those `unmarked` have no marker at all (spec
    section 11, "Its value"): of the numberings in which each note's value
    is one more than the last value before it or more, at most 2 numbers
    skipped on the page, or the note is left out with no value, the one of
    the highest score, then of the fewest numbers skipped and notes left
    out. "1 3 4 s" gives 1, 3, 4, 5; "1 2 8" gives 1, 2, 3."""
    # The best numbering of the notes so far for each last value and number
    # of values skipped.
    states: dict[tuple[int, int], _Numbering] = {(0, 0): (0.0, 0, ())}
    for reading, no_marker in zip(readings, unmarked, strict=True):
        skip_cost = _UNMARKED_SKIP_COST if no_marker else _SKIP_COST
        following: dict[tuple[int, int], _Numbering] = {}
        for (last, skipped), (score, changes, values) in states.items():
            left_out: _Numbering = (score - skip_cost, changes - 1, (*values, None))
            options: list[tuple[tuple[int, int], _Numbering]] = [
                (
                    (last + 1 + more, skipped + more),
                    (
                        score
                        + _reading_score(reading, last + 1 + more)
                        - _JUMP_COST * more,
                        changes - more,
                        (*values, last + 1 + more),
                    ),
                )
                for more in range(_MAX_JUMPS - skipped + 1)
            ]
            options.append(((last, skipped), left_out))
            for key, numbering in options:
                if key not in following or numbering[:2] > following[key][:2]:
                    following[key] = numbering
        states = following
    return max(states.values(), key=lambda numbering: numbering[:2])[2]
