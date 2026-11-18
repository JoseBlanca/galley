"""The endnote section (spec section 12): a run of body paragraphs that
start with endnote markers ("1." to "345." in Gierke, or bare numbers
from 1, as Turney marks its notes) in rising order, which become notes of
kind endnote."""

from collections.abc import Sequence
from dataclasses import dataclass

from galley.model import BlockKind
from galley.structure._lines import first_word, is_bare_number
from galley.structure._markers import NoteMarker, endnote_marker
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


def _runs(
    entries: Sequence[Entry], contents_pages: frozenset[int]
) -> tuple[tuple[tuple[int, NoteMarker], ...], ...]:
    """The runs of paragraphs with endnote markers whose values rise, any
    paragraphs without such a marker between them; a marker that does not
    rise starts a new run, except a bare number that does not read 1,
    which is no marker. Each run is the positions of its marked paragraphs
    with their markers."""
    runs: list[list[tuple[int, NoteMarker]]] = []
    last_value: int | None = None
    for position, entry in enumerate(entries):
        found = _marker_of(entry, contents_pages)
        if found is None:
            continue
        marker, bare = found
        value = marker.value
        if value is None:
            continue
        if last_value is None or value <= last_value:
            if bare and value != 1:
                continue
            runs.append([])
        runs[-1].append((position, marker))
        last_value = value
    return tuple(tuple(run) for run in runs)


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
    first = entry.piece.lines[0]
    before = next(
        (
            earlier.piece.lines[-1]
            for earlier in reversed(entries[:position])
            if isinstance(earlier, BodyBlock)
        ),
        None,
    )
    if before is None or before.page_index != first.page_index:
        return True
    gap = first.line.box.top - before.line.box.top
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
    long_runs = tuple(run for run in runs if len(run) >= _SECTION_MIN_MARKERS)
    if not long_runs:
        return None
    first, last = long_runs[0][0][0], long_runs[-1][-1][0]
    marked = tuple(item for run in runs for item in run)
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
