"""The endnote section (spec section 12): a run of body paragraphs that
start with endnote markers ("1." to "345." in Gierke, or bare numbers
from 1, as Turney marks its notes) in rising order, which become notes of
kind endnote."""

from collections.abc import Sequence
from dataclasses import dataclass
from difflib import SequenceMatcher

from galley.model import BlockKind
from galley.structure._heads import starts_with_chapter_label_word
from galley.structure._lines import (
    MISREAD_FOLLOWERS,
    Piece,
    PlacedLine,
    first_word,
    is_bare_number,
    is_hung,
    is_misread_marker,
)
from galley.structure._markers import NoteMarker, endnote_marker
from galley.structure._measures import letters
from galley.structure._paragraphs import BodyBlock, Entry

# Spec section 12: a run of at least 8 rising endnote markers makes the
# section; the six books hold one run of 6 outside it (Kadesh, pages 20 to
# 40), and the Gierke excerpt 12 endnotes, 291 to 302.
_SECTION_MIN_MARKERS = 8
# Spec section 12, "Note groups": a group heading holds at most 3 lines and
# lies at least 1.5 body line pitches below the line before it; the survey
# measured Haynes' at 2.1 pitches and Turney's at 1.8 to 1.9, the lines of
# a note 0.8 pitch apart.
_GROUP_HEADING_MAX_LINES = 3
_GROUP_HEADING_GAP_PITCHES = 1.5
# Spec section 12, "The chapter of a group": a group heading's title is
# alike to its chapter's heading by at least this ratio of difflib. On the
# 26 group headings of Turney and Haynes, 18 November 2026: 0.94 to 1.00 to
# their own chapter's, at most 0.76 to another's.
_CHAPTER_ALIKE_RATIO = 0.85


@dataclass(frozen=True, slots=True)
class EndnoteSection:
    """The endnote section: the positions in the body's entries of its
    paragraphs, in order, its first page index, whose first line starts a
    paragraph, and the marker of each of its paragraphs that starts with
    an endnote marker, by position."""

    paragraphs: tuple[int, ...]
    first_page: int
    markers: frozendict[int, NoteMarker]


def _first_page(entry: Entry) -> int:
    return entry.piece.lines[0].page_index


def _marker_of(
    entry: Entry, contents_pages: frozenset[int]
) -> tuple[NoteMarker, bool] | None:
    """The endnote marker the first word of a paragraph has, and whether it
    is a bare number (spec section 12): a bare number counts only outside
    `contents_pages`. None for a paragraph without one and for a margin
    note."""
    match entry:
        case BodyBlock(piece=piece):
            word = first_word(piece.lines[0])
            marker = endnote_marker(word)
            if marker is not None:
                return marker, False
            if is_bare_number(word) and _first_page(entry) not in contents_pages:
                return NoteMarker(word, "", int(word)), True
            return None
        case _:
            return None


def _misread_markers(
    entries: Sequence[Entry], contents_pages: frozenset[int]
) -> dict[int, tuple[NoteMarker, bool]]:
    """The misread markers among the entries (spec section 12), by position:
    a paragraph whose first word is one character that is not a digit,
    with a word after it, whose first line is hung (`is_hung`), when the
    next three paragraphs that start with a bare number read 2, 3 and 4
    and the nearest before it does not read 1. Its marker is that
    character, its value 1, a bare number's."""
    bare = tuple(
        (position, found[0].value)
        for position, entry in enumerate(entries)
        if (found := _marker_of(entry, contents_pages)) is not None and found[1]
    )
    found_misread: dict[int, tuple[NoteMarker, bool]] = {}
    for position, entry in enumerate(entries):
        if not isinstance(entry, BodyBlock):
            continue
        line = entry.piece.lines[0]
        words = line.line.words
        if not is_hung(line) or not is_misread_marker(words[0].text):
            continue
        following = tuple(value for later, value in bare if later > position)
        preceding = tuple(value for earlier, value in bare if earlier < position)
        if following[: len(MISREAD_FOLLOWERS)] == MISREAD_FOLLOWERS and preceding[
            -1:
        ] != (1,):
            found_misread[position] = (NoteMarker(words[0].text, "", 1), True)
    return found_misread


def _runs(
    entries: Sequence[Entry], contents_pages: frozenset[int]
) -> tuple[tuple[bool, tuple[tuple[int, NoteMarker], ...]], ...]:
    """The runs of paragraphs with endnote markers of one form whose values
    rise, any paragraphs without such a marker between them, in the order
    of their first paragraphs, each with whether its markers are bare
    numbers: a marker that does not rise above the last of its form starts
    a new run, except a bare number that does not read 1, which is no
    marker. The two forms make runs of their own (spec section 12): a bare
    number does not go on with, or end, a run of "N." markers. Each run is
    the positions of its marked paragraphs with their markers."""
    runs: list[tuple[bool, list[tuple[int, NoteMarker]]]] = []
    current: dict[bool, list[tuple[int, NoteMarker]]] = {}
    last_value: dict[bool, int] = {}
    misread = _misread_markers(entries, contents_pages)
    for position, entry in enumerate(entries):
        found = misread.get(position) or _marker_of(entry, contents_pages)
        if found is None:
            continue
        marker, bare = found
        value = marker.value
        if value is None:
            continue
        if bare not in last_value or value <= last_value[bare]:
            if bare and value != 1:
                continue
            current[bare] = []
            runs.append((bare, current[bare]))
        current[bare].append((position, marker))
        last_value[bare] = value
    return tuple((bare, tuple(run)) for bare, run in runs)


def is_group_heading(
    entries: Sequence[Entry], position: int, body_line_pitch: float
) -> bool:
    """Whether the block at `position` has the look of a group heading (spec
    section 12, "Note groups"): a body block of at most 3 lines whose first
    line lies at least 1.5 body line pitches (`body_line_pitch`, in points)
    below the last line of the body block before it, or is the first line
    of its region: the first of the body blocks, on a later page than the
    line before, or above it, at the top of a column."""
    entry = entries[position]
    if (
        not isinstance(entry, BodyBlock)
        or len(entry.piece.lines) > _GROUP_HEADING_MAX_LINES
    ):
        return False
    before = next(
        (
            line
            for earlier in reversed(entries[:position])
            if isinstance(earlier, BodyBlock)
            for line in reversed(earlier.piece.lines)
            if _has_letter_or_digit(line)
        ),
        None,
    )
    return before is None or _set_apart(entry.piece.lines[0], before, body_line_pitch)


def _has_letter_or_digit(line: PlacedLine) -> bool:
    """Whether a word of `line` holds a letter or a digit: a line without
    one, a speck the OCR read as "/", is passed over (spec section 12)."""
    return any(
        character.isalnum() for word in line.line.words for character in word.text
    )


def _piece_has_letter_or_digit(piece: Piece) -> bool:
    return any(_has_letter_or_digit(line) for line in piece.lines)


def _set_apart(line: PlacedLine, before: PlacedLine, body_line_pitch: float) -> bool:
    """Whether `line` is set apart from `before`, the line before it in the
    body stream, as a group heading is: at least 1.5 body line pitches
    below it, or the first line of its region, on a later page or above
    it, at the top of a column (spec section 12, "Note groups")."""
    if before.page_index != line.page_index:
        return True
    gap = line.line.box.top - before.line.box.top
    return gap < 0 or gap >= _GROUP_HEADING_GAP_PITCHES * body_line_pitch


def endnote_section(
    entries: Sequence[Entry],
    contents_pages: frozenset[int],
    body_line_pitch: float,
) -> EndnoteSection | None:
    """The endnote section among the body's entries (spec section 12), or
    None: from the first to the last paragraph of the runs of at least 8
    rising endnote markers. It takes in the paragraphs before its first
    marker on that page, back to the first heading block that is not a
    group heading (the heading "NOTES."), and ends with the last paragraph
    that starts on the page of its last marker. `contents_pages` are the
    pages of the printed table of contents, where a bare number is no
    marker; `body_line_pitch` is in points."""
    runs = _runs(entries, contents_pages)
    long_runs = tuple(
        (bare, run) for bare, run in runs if len(run) >= _SECTION_MIN_MARKERS
    )
    if not long_runs:
        return None
    first = min(run[0][0] for _, run in long_runs)
    last = max(run[-1][0] for _, run in long_runs)
    # Spec section 12: the section's markers are those of the forms of its
    # long runs, so that a margin note's "1" in Gierke's "N." notes is none.
    forms = frozenset(bare for bare, _ in long_runs)
    marked = tuple(sorted(item for bare, run in runs if bare in forms for item in run))
    # Spec section 12, "Note groups": a section with a marker reading 1
    # after its first is cut into groups, and only then has group headings.
    grouped = any(
        marker.value == 1 for position, marker in marked if first < position <= last
    )
    first_page, last_page = _first_page(entries[first]), _first_page(entries[last])
    start = first
    while start > 0:
        before = entries[start - 1]
        if not isinstance(before, BodyBlock) or _first_page(before) != first_page:
            break
        if before.kind is BlockKind.HEADING and not (
            grouped
            and start == first
            and is_group_heading(entries, start - 1, body_line_pitch)
        ):
            break
        start -= 1
    end = last
    while end + 1 < len(entries) and _first_page(entries[end + 1]) == last_page:
        end += 1
    return EndnoteSection(
        tuple(
            position
            for position in range(start, end + 1)
            if isinstance(entries[position], BodyBlock)
        ),
        first_page,
        frozendict(
            (position, marker)
            for position, marker in marked
            if start <= position <= end
        ),
    )


@dataclass(frozen=True, slots=True)
class EndnoteParagraphs:
    """The paragraphs of one endnote, by their positions in the entries, and
    its marker, None for the endnote before the section's first marker."""

    marker: NoteMarker | None
    paragraphs: tuple[int, ...]


def endnote_paragraphs(section: EndnoteSection) -> tuple[EndnoteParagraphs, ...]:
    """The section's paragraphs grouped into endnotes: each paragraph with
    an endnote marker starts one, the paragraphs after it without one are
    its later blocks, and those before the first marker are an endnote
    without a marker."""
    endnotes: list[EndnoteParagraphs] = []
    for position in section.paragraphs:
        marker = section.markers.get(position)
        if marker is not None or not endnotes:
            endnotes.append(EndnoteParagraphs(marker, (position,)))
        else:
            last = endnotes[-1]
            endnotes[-1] = EndnoteParagraphs(last.marker, (*last.paragraphs, position))
    return tuple(endnotes)


@dataclass(frozen=True, slots=True)
class NoteGroup:
    """A note group (spec section 12, "Note groups"): the position in the
    entries of its group heading, None when it has none, and its
    endnotes."""

    heading: int | None
    endnotes: tuple[EndnoteParagraphs, ...]


def _reads_1(endnote: EndnoteParagraphs) -> bool:
    return endnote.marker is not None and endnote.marker.value == 1


def note_groups(
    entries: Sequence[Entry], section: EndnoteSection, body_line_pitch: float
) -> tuple[NoteGroup, ...]:
    """The section's endnotes cut into note groups (spec section 12): a
    group from each endnote whose marker reads 1 up to the next, the
    endnotes before the first such one in the first group; one group when
    no marker reads 1 after the first endnote with a marker. The block
    right before a group's first endnote is its group heading when it has
    the look of one (`is_group_heading`); it is then no block of the
    endnote before, and an endnote of that block alone is no endnote,
    so that a heading that starts with a bare 1 starts no group. Groups
    are looked at from the last, so that such a heading is taken before
    it could be a group's first endnote. `body_line_pitch` is in
    points."""
    endnotes = list(endnote_paragraphs(section))
    first_marked = next(
        (number for number, endnote in enumerate(endnotes) if endnote.marker), 0
    )
    if not any(_reads_1(endnote) for endnote in endnotes[first_marked + 1 :]):
        return (NoteGroup(None, tuple(endnotes)),)
    starts = tuple(
        number for number, endnote in enumerate(endnotes) if _reads_1(endnote)
    )
    headings: dict[int, int] = {}
    dropped: set[int] = set()
    for number in reversed(starts):
        if number in dropped or number == 0:
            continue
        before = endnotes[number - 1]
        # A block with no letter or digit, a speck, is passed over.
        place = next(
            (
                place
                for place in range(len(before.paragraphs) - 1, -1, -1)
                if _piece_has_letter_or_digit(entries[before.paragraphs[place]].piece)
            ),
            None,
        )
        rest = (
            before.paragraphs[:place] + before.paragraphs[place + 1 :]
            if place is not None
            else ()
        )
        # An endnote whose marker reads another number is no heading.
        numbered = before.marker is not None and before.marker.value != 1
        if (
            place is None
            or (place == 0 and (rest or numbered))
            or not is_group_heading(entries, before.paragraphs[place], body_line_pitch)
        ):
            continue
        headings[number] = before.paragraphs[place]
        if not rest:
            dropped.add(number - 1)
        else:
            endnotes[number - 1] = EndnoteParagraphs(before.marker, rest)
    kept_starts = tuple(number for number in starts if number not in dropped)
    groups: list[NoteGroup] = []
    for number, endnote in enumerate(endnotes):
        if number in dropped:
            continue
        if not groups or (number in kept_starts and number != kept_starts[0]):
            groups.append(NoteGroup(headings.get(number), ()))
        last = groups[-1]
        groups[-1] = NoteGroup(last.heading, (*last.endnotes, endnote))
    if kept_starts and kept_starts[0] in headings:
        groups[0] = NoteGroup(headings[kept_starts[0]], groups[0].endnotes)
    return tuple(groups)


def _title_letters(group_heading: str) -> str:
    """The letters of a group heading in lower case once a first word that
    is a chapter label word is dropped ("Chapter" of "Chapter 1."); its
    number falls out with the other characters that are not letters
    (spec section 12, "The chapter of a group")."""
    words = group_heading.split(" ")
    if starts_with_chapter_label_word(words[:1]):
        words = words[1:]
    return letters(" ".join(words))


def _chapter_by_heading(
    group_heading: str | None, chapters: Sequence[tuple[int, str]]
) -> int | None:
    """The index in `chapters`, the positions and letters of the body's
    level-1 headings in order, of the one most alike to `group_heading`,
    at least 0.85 alike; None for a group without a heading or alike to
    none (spec section 12, "The chapter of a group")."""
    if group_heading is None:
        return None
    title = _title_letters(group_heading)
    ratios = tuple(
        SequenceMatcher(None, title, chapter_letters).ratio()
        for _, chapter_letters in chapters
    )
    if not ratios or max(ratios) < _CHAPTER_ALIKE_RATIO:
        return None
    return ratios.index(max(ratios))


def _counted_chapter(
    group: int, by_heading: Sequence[int | None], chapter_count: int
) -> int | None:
    """The index among the chapters of a group not found by its heading
    (spec section 12): counted on from the nearest group before it found
    by its heading, or, when there is none or the count would not lie
    before the chapter of the nearest such group after it, back from that
    one; from the first chapter, the first group's, when no group was
    found by its heading. None when the count falls outside."""
    before = next(
        (other for other in range(group - 1, -1, -1) if by_heading[other] is not None),
        None,
    )
    after = next(
        (
            other
            for other in range(group + 1, len(by_heading))
            if by_heading[other] is not None
        ),
        None,
    )
    after_index = by_heading[after] if after is not None else None
    before_index = by_heading[before] if before is not None else None
    if before_index is not None:
        counted = before_index + group - (before or 0)
        if counted < chapter_count and (after_index is None or counted < after_index):
            return counted
    if after_index is not None:
        counted = after_index - ((after or 0) - group)
        if counted >= 0 and (before_index is None or counted > before_index):
            return counted
        return None
    if before_index is None and group < chapter_count:
        return group
    return None


def group_reaches(
    chapters: Sequence[tuple[int, str]],
    group_headings: Sequence[str | None],
    before_section: int,
) -> tuple[tuple[int, int], ...]:
    """For each note group, whose heading is in `group_headings` (None for a
    group without one), the body blocks whose references its endnotes are
    matched against, from the first position to before the second (spec
    section 12, "References" and "The chapter of a group"): with one
    group, the body before the section, the first `before_section`
    blocks; with several, from the group's chapter heading to the chapter
    heading of the next group after it that has one, or to the section.
    `chapters` are the positions and letters, in lower case, of the
    body's level-1 heading blocks after the contents pages and before the
    section, in order. A group whose chapter is not found reaches no
    block."""
    if len(group_headings) <= 1:
        return tuple((0, before_section) for _ in group_headings)
    by_heading = tuple(
        _chapter_by_heading(heading, chapters) for heading in group_headings
    )
    indices = tuple(
        found
        if (found := by_heading[group]) is not None
        else _counted_chapter(group, by_heading, len(chapters))
        for group in range(len(group_headings))
    )
    found = tuple(
        chapters[index][0] if index is not None else None for index in indices
    )
    # Each reach ends at the next group after it that has a chapter.
    next_starts = tuple(
        next((later for later in found[group + 1 :] if later is not None), None)
        for group in range(len(found))
    )
    return tuple(
        (start, end)
        if start is not None
        and (end := next_start if next_start is not None else before_section) > start
        else (0, 0)
        for start, next_start in zip(found, next_starts, strict=True)
    )


def _heading_lines_start(piece: Piece, body_line_pitch: float) -> int | None:
    """The position in `piece` of the line that starts a group heading left
    at its end (spec section 12, "Note groups"): the last of its last 3
    lines, but not its first, that is set apart from the line before it;
    None when there is none."""
    lines = piece.lines
    return next(
        (
            number
            for number in range(len(lines) - 1, 0, -1)
            if len(lines) - number <= _GROUP_HEADING_MAX_LINES
            and _has_letter_or_digit(lines[number])
            and (
                before := next(
                    (
                        line
                        for line in reversed(lines[:number])
                        if _has_letter_or_digit(line)
                    ),
                    None,
                )
            )
            is not None
            and _set_apart(lines[number], before, body_line_pitch)
        ),
        None,
    )


def _split(entry: BodyBlock, start: int) -> tuple[BodyBlock, BodyBlock]:
    """`entry` cut before its line at `start`: its lines before, which keep
    its kind, and a paragraph of the lines from there."""
    piece = entry.piece
    return (
        BodyBlock(
            piece=Piece(
                piece.lines[:start],
                frozenset(number for number in piece.unjoined if number < start),
            ),
            kind=entry.kind,
            level=entry.level,
            label_line=entry.label_line,
        ),
        BodyBlock(
            piece=Piece(
                piece.lines[start:],
                frozenset(
                    number - start for number in piece.unjoined if number > start
                ),
            )
        ),
    )


def with_group_headings_cut(
    entries: Sequence[Entry], section: EndnoteSection, body_line_pitch: float
) -> tuple[Entry, ...]:
    """`entries` with each group heading that ends the block right before a
    group's first endnote cut off that block into a paragraph of its own
    (spec section 12, "Note groups"): Haynes sets some flush left after
    the note before, where no paragraph rule starts them. The block is cut
    when it is no group heading as a whole and its last lines are set
    apart (`_heading_lines_start`); only in a section of several groups.
    `body_line_pitch` is in points."""
    marked = sorted(section.markers)
    if not any(section.markers[position].value == 1 for position in marked[1:]):
        return tuple(entries)
    paragraphs = section.paragraphs
    cuts: dict[int, int] = {}
    for number, position in enumerate(paragraphs[1:], start=1):
        marker = section.markers.get(position)
        before = next(
            (
                earlier
                for earlier in reversed(paragraphs[:number])
                if _piece_has_letter_or_digit(entries[earlier].piece)
            ),
            paragraphs[number - 1],
        )
        entry = entries[before]
        if (
            marker is None
            or marker.value != 1
            or not isinstance(entry, BodyBlock)
            or is_group_heading(entries, before, body_line_pitch)
        ):
            continue
        start = _heading_lines_start(entry.piece, body_line_pitch)
        if start is not None:
            cuts[before] = start
    return tuple(
        part
        for position, entry in enumerate(entries)
        for part in (
            _split(entry, cuts[position])
            if position in cuts and isinstance(entry, BodyBlock)
            else (entry,)
        )
    )
