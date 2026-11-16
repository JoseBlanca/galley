"""Paragraphs and side text (spec section 6).

The per-page part, `page_parts`, runs on one page: what each region is,
what is removed, the body stream, and the side text cut into blocks.
`body_entries` runs once in page order: it finds the paragraphs of the
book's body stream, which run over page breaks, and puts each page's
margin notes after the paragraph in which its body ends.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from galley.model import (
    PageLayout,
    PageNumber,
    Region,
    Removal,
)
from galley.structure._foot import body_column
from galley.structure._lines import (
    Piece,
    PlacedLine,
    first_word,
    hyphen_between,
    starts_paragraph,
)
from galley.structure._markers import MarkerForm, marker_form
from galley.structure._measures import Edges, is_short, region_edges
from galley.structure._regions import RegionKind, region_kinds
from galley.structure._removals import foot_removals, head_removals
from galley.structure._survey import BookSurvey


@dataclass(frozen=True, slots=True)
class PageParts:
    """What the per-page work gives for one page: the removals and page
    numbers, the body stream, the margin notes, the lines of each band
    region and the band blocks they make by rules 1 and 2, each of one
    page, whether the page has a figure, and the lines taken from the foot
    of the body stream as notes (spec section 11, "Notes left in the
    body"), none until they are taken."""

    removals: tuple[Removal, ...]
    page_numbers: tuple[PageNumber, ...]
    body: tuple[PlacedLine, ...]
    margin_notes: tuple[Piece, ...]
    band_regions: tuple[tuple[PlacedLine, ...], ...]
    band_blocks: tuple[Piece, ...]
    has_figure: bool
    body_notes: tuple[PlacedLine, ...] = ()


def _pieces(lines: tuple[PlacedLine, ...]) -> tuple[Piece, ...]:
    """The lines of one band region cut into blocks by rules 1 and 2."""
    pieces: list[list[PlacedLine]] = []
    before: PlacedLine | None = None
    for line in lines:
        if not pieces or starts_paragraph(line, before):
            pieces.append([])
        pieces[-1].append(line)
        before = line
    return tuple(Piece(tuple(piece)) for piece in pieces)


def _edges(region: Region, kind: RegionKind) -> Edges:
    """A region's edges for rules 1 and 2: a band's are its box's sides, so
    that its short last lines do not set its right edge (spec section 6,
    "Side text"); any other region's are `region_edges`."""
    if kind is RegionKind.BAND:
        return Edges(region.box.x0, region.box.x1)
    return region_edges(region)


def page_parts(page: PageLayout, survey: BookSurvey) -> PageParts:
    """The per-page work on `page` (spec section 2, step 2)."""
    kinds = region_kinds(page, survey.body_word_height, survey.running_heads)
    head = head_removals(page, kinds, survey)
    foot = foot_removals(page, kinds, survey)
    removed = head.lines | foot.lines
    column = body_column(page, kinds)

    def centring_edges(region: Region, kind: RegionKind, edges: Edges) -> Edges:
        if kind is RegionKind.BODY and is_short(region) and column is not None:
            return column
        return edges

    regions = tuple(
        (
            kind,
            tuple(
                PlacedLine(page.index, line, edges, centring_edges(region, kind, edges))
                for line_number, line in enumerate(region.lines)
                if (region_number, line_number) not in removed
            ),
        )
        for region_number, (region, kind, edges) in enumerate(
            zip(
                page.regions,
                kinds,
                (
                    _edges(region, kind)
                    for region, kind in zip(page.regions, kinds, strict=True)
                ),
                strict=True,
            )
        )
    )
    band_regions = tuple(
        lines for kind, lines in regions if kind is RegionKind.BAND and lines
    )
    return PageParts(
        removals=head.removals + foot.removals,
        page_numbers=head.page_numbers + foot.page_numbers,
        body=tuple(
            line for kind, lines in regions if kind is RegionKind.BODY for line in lines
        ),
        margin_notes=tuple(
            Piece(lines)
            for kind, lines in regions
            if kind is RegionKind.MARGIN and lines
        ),
        band_regions=band_regions,
        band_blocks=tuple(piece for lines in band_regions for piece in _pieces(lines)),
        has_figure=bool(page.figures),
    )


# Across pages


@dataclass(frozen=True, slots=True)
class Paragraph:
    """A paragraph of the body stream, as a piece."""

    piece: Piece


@dataclass(frozen=True, slots=True)
class MarginNote:
    piece: Piece


type Entry = Paragraph | MarginNote


def _marker_led(lines: Sequence[PlacedLine], form: MarkerForm | None) -> bool:
    """Whether a paragraph of `lines` starts with a word of the book's
    marker form `form`: a note that section 11 did not take, which never
    runs on into the next page (spec section 16)."""
    return (
        form is not None and bool(lines) and marker_form(first_word(lines[0])) is form
    )


def body_entries(
    pages: Sequence[PageParts], form: MarkerForm | None = None
) -> tuple[Entry, ...]:
    """The paragraphs of the book's body stream in order, each followed by
    the margin notes of the pages whose body ends in it; the margin notes
    of a page with no body stream after the last block so far. A paragraph
    whose first word has the book's marker form `form` does not run on
    into the next page."""
    entries: list[Entry] = []
    current: list[PlacedLine] = []
    pending: list[MarginNote] = []
    before: PlacedLine | None = None
    page_before_has_figure = False
    for page in pages:
        for number, line in enumerate(page.body):
            # The hyphen rule comes before the plate break (spec section 6).
            plate_break = (
                number == 0
                and (page.has_figure or page_before_has_figure)
                and not (before is not None and hyphen_between(before, line))
            )
            note_break = number == 0 and _marker_led(current, form)
            if plate_break or note_break or starts_paragraph(line, before):
                if current:
                    entries.append(Paragraph(Piece(tuple(current))))
                    entries.extend(pending)
                    pending = []
                current = []
            current.append(line)
            before = line
        if page.body:
            page_before_has_figure = page.has_figure
        notes = tuple(MarginNote(piece) for piece in page.margin_notes)
        if current:
            pending.extend(notes)
        else:
            entries.extend(notes)
    if current:
        entries.append(Paragraph(Piece(tuple(current))))
    entries.extend(pending)
    return tuple(entries)
