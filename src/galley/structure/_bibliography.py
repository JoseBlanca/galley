"""Haskins' bibliographical notes (spec section 16, "Haskins'
bibliographical notes"): the section after a level-2 heading
"BIBLIOGRAPHICAL NOTE", up to the next heading, is paragraphs, its band
blocks among them."""

from collections.abc import Sequence
from dataclasses import replace

from galley.model import BlockKind
from galley.structure._lines import PlacedLine
from galley.structure._paragraphs import BodyBlock, Entry, PageParts
from galley.structure._runs import BodyRun

_TITLE = "bibliographical note"
# Spec section 14, "Levels": a section's heading.
_SECTION_LEVEL = 2


def _text(lines: Sequence[PlacedLine]) -> str:
    return " ".join(word.text for line in lines for word in line.line.words)


def is_bibliographical_note(text: str, level: int | None) -> bool:
    """Whether a heading of `text` and `level` heads a bibliographical note:
    level 2, its text "BIBLIOGRAPHICAL NOTE" in any case."""
    return level == _SECTION_LEVEL and text.casefold() == _TITLE


def _heading_text(page: PageParts, run: BodyRun) -> str:
    return _text(page.body[run.start : run.end])


def bibliographical_pages(pages: Sequence[PageParts]) -> frozenset[int]:
    """The page indices whose band lies in a bibliographical note: those on
    which the last heading so far, at the end of the page's body, is a
    bibliographical note's."""
    inside = False
    found: set[int] = set()
    for page in pages:
        for run in page.runs:
            if run.kind is BlockKind.HEADING:
                inside = is_bibliographical_note(_heading_text(page, run), run.level)
        if inside:
            found.add(page.index)
    return frozenset(found)


def with_band_as_body(page: PageParts) -> PageParts:
    """`page` with its band regions' lines after its body stream, so that
    they become body paragraphs (spec section 16), each band block starting
    a block of its own, and no band left."""
    starts = []
    lines = list(page.body)
    for piece in page.band_blocks:
        starts.append(len(lines))
        lines.extend(piece.lines)
    return replace(
        page,
        body=tuple(lines),
        band_regions=(),
        band_blocks=(),
        block_starts=page.block_starts | frozenset(starts),
    )


def in_bibliographical_notes(entries: Sequence[Entry]) -> frozenset[int]:
    """The positions of the body blocks that follow a bibliographical note's
    heading, up to the next heading."""
    inside = False
    found: set[int] = set()
    for position, entry in enumerate(entries):
        if not isinstance(entry, BodyBlock):
            continue
        if entry.kind is BlockKind.HEADING:
            inside = is_bibliographical_note(_text(entry.piece.lines), entry.level)
        elif inside:
            found.add(position)
    return frozenset(found)
