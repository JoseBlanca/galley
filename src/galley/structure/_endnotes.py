"""The endnote section (spec section 12): a run of body paragraphs that
start with endnote markers ("1." to "345." in Gierke) in rising order,
which become notes of kind endnote."""

from collections.abc import Sequence
from dataclasses import dataclass

from galley.structure._lines import first_word, is_centred
from galley.structure._markers import NoteMarker, endnote_marker
from galley.structure._paragraphs import Entry, Paragraph

# Spec section 12: a run of at least 8 rising endnote markers makes the
# section; the six books hold one run of 6 outside it (Kadesh, pages 20 to
# 40), and the Gierke excerpt 12 endnotes, 291 to 302.
_SECTION_MIN_MARKERS = 8


@dataclass(frozen=True, slots=True)
class EndnoteSection:
    """The endnote section: the positions in the body's entries of its
    paragraphs, in order, and its first page index, whose first line
    starts a paragraph."""

    paragraphs: tuple[int, ...]
    first_page: int


def _marked(entry: Entry) -> NoteMarker | None:
    match entry:
        case Paragraph(piece):
            return endnote_marker(first_word(piece.lines[0]))
        case _:
            return None


def _first_page(entry: Entry) -> int:
    return entry.piece.lines[0].page_index


def _runs(entries: Sequence[Entry]) -> tuple[tuple[int, ...], ...]:
    """The runs of paragraphs with endnote markers whose values rise, any
    paragraphs without such a marker between them; a marker that does not
    rise starts a new run. Each run is the positions of its marked
    paragraphs."""
    runs: list[list[int]] = []
    last_value: int | None = None
    for position, entry in enumerate(entries):
        marker = _marked(entry)
        if marker is None or marker.value is None:
            continue
        if not runs or last_value is None or marker.value <= last_value:
            runs.append([])
        runs[-1].append(position)
        last_value = marker.value
    return tuple(tuple(run) for run in runs)


def endnote_section(entries: Sequence[Entry]) -> EndnoteSection | None:
    """The endnote section among the body's entries (spec section 12), or
    None: from the first to the last paragraph of the runs of at least 8
    rising endnote markers. It takes in the paragraphs before its first
    marker on that page, back to a centred line (the heading "NOTES."),
    and ends with the last paragraph that starts on the page of its last
    marker."""
    long_runs = tuple(run for run in _runs(entries) if len(run) >= _SECTION_MIN_MARKERS)
    if not long_runs:
        return None
    first, last = long_runs[0][0], long_runs[-1][-1]
    first_page, last_page = _first_page(entries[first]), _first_page(entries[last])
    start = first
    while start > 0:
        before = entries[start - 1]
        if (
            not isinstance(before, Paragraph)
            or _first_page(before) != first_page
            or is_centred(before.piece.lines[0])
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
            if isinstance(entries[position], Paragraph)
        ),
        first_page,
    )


@dataclass(frozen=True, slots=True)
class EndnoteGroup:
    """The paragraphs of one endnote, by their positions in the entries, and
    its marker, None for the endnote before the section's first marker."""

    marker: NoteMarker | None
    paragraphs: tuple[int, ...]


def endnote_groups(
    entries: Sequence[Entry], section: EndnoteSection
) -> tuple[EndnoteGroup, ...]:
    """The section's paragraphs grouped into endnotes: each paragraph with
    an endnote marker starts one, the paragraphs after it without one are
    its later blocks, and those before the first marker are an endnote
    without a marker."""
    groups: list[EndnoteGroup] = []
    for position in section.paragraphs:
        marker = _marked(entries[position])
        if marker is not None or not groups:
            groups.append(EndnoteGroup(marker, (position,)))
        else:
            last = groups[-1]
            groups[-1] = EndnoteGroup(last.marker, (*last.paragraphs, position))
    return tuple(groups)
