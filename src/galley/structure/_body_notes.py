"""Notes left in the body (spec section 11, "Notes left in the body";
section 2, step 2.5): the lines at the foot of a page's body stream that
are notes set in smaller type, which layout did not put in the band."""

import itertools
from collections.abc import Sequence
from dataclasses import replace

from galley.body_measures import median_word_height
from galley.structure._lines import PlacedLine, first_word
from galley.structure._markers import MarkerForm, marker_form, note_marker
from galley.structure._notes import PageNote
from galley.structure._paragraphs import PageParts

# Spec section 11, "Notes left in the body", conditions 2 and 3: the notes'
# lines have a height ratio of at most 0.95, and the lines above one at
# least 0.05 higher (Mariéjol's note lines are 9 pt high against 10).
_NOTE_HEIGHT_RATIO_MAX = 0.95
_HEIGHT_RATIO_STEP = 0.05


def _height_ratio(lines: Sequence[PlacedLine], body_word_height: float) -> float:
    """The median height of the words of `lines` over the body word height;
    0 for no line, so that notes with no line above them fail condition 3."""
    return (
        median_word_height(word for line in lines for word in line.line.words)
        / body_word_height
    )


def _marker_value(line: PlacedLine, form: MarkerForm) -> int | None:
    """What the first word of `line` reads, when it has the book's marker
    form; None otherwise or when it reads no number."""
    word = first_word(line)
    if marker_form(word) is not form:
        return None
    marker = note_marker(word)
    return marker.value if marker is not None else None


def _never_decrease(values: Sequence[int | None]) -> bool:
    readable = tuple(value for value in values if value is not None)
    return all(before <= after for before, after in itertools.pairwise(readable))


def note_lines_start(
    body: Sequence[PlacedLine],
    band_notes: Sequence[PageNote],
    form: MarkerForm,
    body_word_height: float,
) -> int | None:
    """The position in `body`, a page's body stream, of its first marker
    line when the lines from it to the end are notes left in the body, or
    None (spec section 11, "Notes left in the body", conditions 1 to 5).
    `band_notes` are the page's notes of its band, `form` the book's
    marker form and `body_word_height` the book's, in points."""
    if body_word_height <= 0:
        return None
    if band_notes and band_notes[0].marker and band_notes[0].marker.value == 1:
        return None
    start = next(
        (
            position
            for position, line in enumerate(body)
            if _marker_value(line, form) == 1
        ),
        None,
    )
    if start is None:
        return None
    notes, above = body[start:], body[:start]
    notes_ratio = _height_ratio(notes, body_word_height)
    if (
        notes_ratio > _NOTE_HEIGHT_RATIO_MAX
        or _height_ratio(above, body_word_height) < notes_ratio + _HEIGHT_RATIO_STEP
    ):
        return None
    if not _never_decrease(tuple(_marker_value(line, form) for line in notes)):
        return None
    return start


def take_body_notes(
    page: PageParts,
    band_notes: Sequence[PageNote],
    form: MarkerForm | None,
    body_word_height: float,
) -> PageParts:
    """`page` with the notes left at the foot of its body stream taken out
    of it into `body_notes`, when there are such notes; `page` as it is
    otherwise, and in a book without a marker form. `body_word_height` is
    in points."""
    if form is None:
        return page
    start = note_lines_start(page.body, band_notes, form, body_word_height)
    if start is None:
        return page
    return replace(
        page,
        body=page.body[:start],
        runs=tuple(
            replace(run, end=min(run.end, start))
            for run in page.runs
            if run.start < start
        ),
        block_starts=frozenset(n for n in page.block_starts if n < start),
        body_notes=page.body[start:],
    )
