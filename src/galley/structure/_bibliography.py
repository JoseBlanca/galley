"""Haskins' bibliographical notes (spec section 16, "Haskins'
bibliographical notes"): the section after a level-2 heading
"BIBLIOGRAPHICAL NOTE", up to the next heading, is paragraphs, its band
blocks among them."""

from collections.abc import Sequence
from dataclasses import dataclass, replace

from galley.model import BlockKind
from galley.structure._lines import PlacedLine, first_word
from galley.structure._markers import MarkerForm, marker_form
from galley.structure._paragraphs import BodyBlock, Entry, PageParts
from galley.structure._runs import SECTION_LEVEL, BodyRun

_TITLE = "bibliographical note"


def _text(lines: Sequence[PlacedLine]) -> str:
    return " ".join(word.text for line in lines for word in line.line.words)


def _is_bibliographical_note(text: str, level: int | None) -> bool:
    """Whether a heading of `text` and `level` heads a bibliographical note:
    level 2, its text "BIBLIOGRAPHICAL NOTE" in any case."""
    return level == SECTION_LEVEL and text.casefold() == _TITLE


def _heading_text(page: PageParts, run: BodyRun) -> str:
    return _text(page.body[run.start : run.end])


@dataclass(frozen=True, slots=True)
class Bibliography:
    """The page indices whose band lies in a bibliographical note, and among
    them those that print a bibliographical note's heading."""

    pages: frozenset[int]
    heading_pages: frozenset[int]


def bibliography(pages: Sequence[PageParts]) -> Bibliography:
    """The pages whose band lies in a bibliographical note: those on which
    the last heading so far, at the end of the page's body, is a
    bibliographical note's."""
    inside = False
    found: set[int] = set()
    headed: set[int] = set()
    for page in pages:
        for run in page.runs:
            if run.kind is BlockKind.HEADING:
                inside = _is_bibliographical_note(_heading_text(page, run), run.level)
                if inside:
                    headed.add(page.index)
        if inside:
            found.add(page.index)
    return Bibliography(frozenset(found), frozenset(headed))


def _kept_as_notes(
    page: PageParts, found: Bibliography, form: MarkerForm | None
) -> int:
    """How many of the page's band blocks become paragraphs: all, except on
    a heading's page those from the first led by a word of the book's
    marker form `form` on, a footnote of the text above (spec section 16)."""
    if page.index not in found.heading_pages or form is None:
        return len(page.band_blocks)
    return next(
        (
            number
            for number, piece in enumerate(page.band_blocks)
            if marker_form(first_word(piece.lines[0])) is form
        ),
        len(page.band_blocks),
    )


def _without_first_lines(
    regions: Sequence[tuple[PlacedLine, ...]], count: int
) -> tuple[tuple[PlacedLine, ...], ...]:
    """`regions` without their first `count` lines, in order, and without
    the regions left empty: the band blocks are cut from them in order."""
    kept: list[tuple[PlacedLine, ...]] = []
    for region in regions:
        dropped = min(count, len(region))
        count -= dropped
        if region[dropped:]:
            kept.append(region[dropped:])
    return tuple(kept)


def with_band_as_body(
    page: PageParts, found: Bibliography, form: MarkerForm | None
) -> PageParts:
    """`page`, when it is one of `found`'s pages, with its band blocks after
    its body stream, so that they become body paragraphs (spec section 16),
    each starting a block of its own; on a heading's page the blocks from
    the first led by a word of the book's marker form `form` stay its
    band."""
    if page.index not in found.pages:
        return page
    moved = page.band_blocks[: _kept_as_notes(page, found, form)]
    kept = page.band_blocks[len(moved) :]
    starts = []
    lines = list(page.body)
    for piece in moved:
        starts.append(len(lines))
        lines.extend(piece.lines)
    return replace(
        page,
        body=tuple(lines),
        band_regions=_without_first_lines(
            page.band_regions, sum(len(piece.lines) for piece in moved)
        ),
        band_blocks=kept,
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
            inside = _is_bibliographical_note(_text(entry.piece.lines), entry.level)
        elif inside:
            found.add(position)
    return frozenset(found)
