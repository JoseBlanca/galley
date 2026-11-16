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
    BlockKind,
    PageLayout,
    PageNumber,
    Region,
    Removal,
    RemovalReason,
)
from galley.structure._foot import body_column
from galley.structure._headings import PageHead, heading_runs
from galley.structure._index import IndexPage, index_page
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
from galley.structure._runs import BodyRun, LabelLine
from galley.structure._summaries import summary_run
from galley.structure._survey import BookSurvey
from galley.structure._verse import verse_runs


@dataclass(frozen=True, slots=True)
class PageParts:
    """What the per-page work gives for one page: its index, the removals and page
    numbers, the body stream, the margin notes, the lines of each band
    region and the band blocks they make by rules 1 and 2, each of one
    page, whether the page has a figure, the runs of the body stream that
    are blocks of their own (spec section 2, step 2.3), the positions of
    other lines of the body stream that start a block (a bibliographical
    note's band blocks, spec section 16), and the lines taken
    from the foot of the body stream as notes (spec section 11, "Notes left
    in the body"), none until they are taken. On an index page,
    `index_lines` are the lines of its columns, left then right, and
    `index_starts` the positions of those that start an entry (spec
    section 17)."""

    index: int
    removals: tuple[Removal, ...]
    page_numbers: tuple[PageNumber, ...]
    body: tuple[PlacedLine, ...]
    margin_notes: tuple[Piece, ...]
    band_regions: tuple[tuple[PlacedLine, ...], ...]
    band_blocks: tuple[Piece, ...]
    has_figure: bool
    runs: tuple[BodyRun, ...] = ()
    block_starts: frozenset[int] = frozenset()
    body_notes: tuple[PlacedLine, ...] = ()
    index_lines: tuple[PlacedLine, ...] = ()
    index_starts: frozenset[int] = frozenset()


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


def _runs(
    page_index: int,
    body: Sequence[PlacedLine],
    band_regions: Sequence[Sequence[PlacedLine]],
    head: PageHead,
    survey: BookSurvey,
    contents_pages: frozenset[int],
) -> tuple[BodyRun, ...]:
    """The runs of the body stream that are blocks of their own (spec
    section 2, step 2.3), in order: the headings, the chapter summary under
    a heading, and the verse; none on a page of the printed table of
    contents."""
    if page_index in contents_pages:
        return ()
    band_lines = tuple(line for region in band_regions for line in region)
    headings = heading_runs(body, band_lines, survey.body_line_pitch, head)
    # Each heading's summary ends at the next heading at the latest.
    limits = (*(run.start for run in headings[1:]), len(body))
    summaries = tuple(
        summary
        for number, heading in enumerate(headings)
        if (summary := summary_run(body, heading.end, limits[number])) is not None
    )
    taken = frozenset(
        number for run in headings + summaries for number in range(run.start, run.end)
    )
    return tuple(
        sorted(
            headings + summaries + verse_runs(body, taken), key=lambda run: run.start
        )
    )


def page_parts(
    page: PageLayout, survey: BookSurvey, contents_pages: frozenset[int] = frozenset()
) -> PageParts:
    """The per-page work on `page` (spec section 2, step 2). `contents_pages`
    are the page indices of the printed table of contents, on which no
    heading is found."""
    kinds = region_kinds(page, survey.body_word_height, survey.running_heads)
    head = head_removals(page, kinds, survey)
    foot = foot_removals(page, kinds, survey)
    removed = head.lines | foot.lines
    index = (
        index_page(page, kinds, removed) if page.index in survey.index_pages else None
    )
    taken = index.taken if index is not None else frozenset()
    if index is not None:
        removed |= index.removed_lines
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
                and region_number not in taken
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
    body = tuple(
        line for kind, lines in regions if kind is RegionKind.BODY for line in lines
    )
    index_lines = _index_lines(page.index, index)
    page_head = (
        PageHead.RUNNING_HEAD
        if any(
            removal.reason is RemovalReason.RUNNING_HEAD for removal in head.removals
        )
        else PageHead.NO_RUNNING_HEAD
    )
    return PageParts(
        index=page.index,
        removals=head.removals
        + (index.removals if index is not None else ())
        + foot.removals,
        page_numbers=head.page_numbers + foot.page_numbers,
        body=body,
        margin_notes=tuple(
            Piece(lines)
            for kind, lines in regions
            if kind is RegionKind.MARGIN and lines
        ),
        band_regions=band_regions,
        band_blocks=tuple(piece for lines in band_regions for piece in _pieces(lines)),
        has_figure=bool(page.figures),
        # Spec section 17, rule 4: the index columns are the page's body or
        # band lines for the title's centring (section 14, rule 1).
        runs=_runs(
            page.index,
            body,
            (*band_regions, index_lines),
            page_head,
            survey,
            contents_pages,
        ),
        index_lines=index_lines,
        index_starts=index.starts if index is not None else frozenset(),
    )


def _index_lines(page_index: int, index: IndexPage | None) -> tuple[PlacedLine, ...]:
    """The lines of an index page's columns, each with its column's edges."""
    if index is None:
        return ()
    return tuple(
        PlacedLine(page_index, line, Edges(*edges), Edges(*edges))
        for line, edges in zip(index.lines, index.column_edges, strict=True)
    )


# Across pages


@dataclass(frozen=True, slots=True, kw_only=True)
class BodyBlock:
    """A block of the body stream, as a piece: a paragraph, or a run of
    section 2, step 2.3, with its kind, a heading's level and whether its
    first line is its chapter label."""

    piece: Piece
    kind: BlockKind = BlockKind.PARAGRAPH
    level: int | None = None
    label_line: LabelLine = LabelLine.NONE


@dataclass(frozen=True, slots=True)
class MarginNote:
    """A margin region of a page, as a piece of one page (spec section 6,
    "Side text")."""

    piece: Piece


type Entry = BodyBlock | MarginNote


def _marker_led(lines: Sequence[PlacedLine], form: MarkerForm | None) -> bool:
    """Whether a paragraph of `lines` starts with a word of the book's
    marker form `form`: a note that section 11 did not take, which never
    runs on into the next page (spec section 16)."""
    return (
        form is not None and bool(lines) and marker_form(first_word(lines[0])) is form
    )


def _crosses_section_edge(
    before: PlacedLine | None, line: PlacedLine, section_pages: range
) -> bool:
    """Whether a paragraph running on from `before` into `line`, the first
    line of a page, would run into or out of the endnote section."""
    return (
        before is not None
        and bool(section_pages)
        and (before.page_index in section_pages) != (line.page_index in section_pages)
    )


def _run_at(runs: Sequence[BodyRun], number: int) -> BodyRun | None:
    """The run that holds the line at `number`, None when no run does."""
    return next((run for run in runs if run.start <= number < run.end), None)


def _continues_verse(
    current_run: BodyRun | None, run: BodyRun | None, number: int
) -> bool:
    """Whether the line at `number` of a page's body stream, in `run`,
    continues the verse block `current_run` that ended the page before:
    it is the page's first line and starts a verse run (spec section 16,
    rule 4)."""
    return (
        number == 0
        and run is not None
        and run.kind is BlockKind.VERSE
        and current_run is not None
        and current_run.kind is BlockKind.VERSE
    )


def _block(lines: Sequence[PlacedLine], run: BodyRun | None) -> BodyBlock:
    piece = Piece(tuple(lines))
    if run is None:
        return BodyBlock(piece=piece)
    return BodyBlock(
        piece=piece, kind=run.kind, level=run.level, label_line=run.label_line
    )


def body_entries(
    pages: Sequence[PageParts],
    form: MarkerForm | None = None,
    section_pages: range = range(0),
) -> tuple[Entry, ...]:
    """The blocks of the book's body stream in order, each followed by the
    margin notes of the pages whose body ends in it; the margin notes of a
    page with no body stream after the last block so far. Each run of a
    page (`PageParts.runs`) is a block of its own, and the line after it
    starts a block; a verse block that ends a page's body stream goes on
    into a verse run that starts the next. A paragraph whose first word has
    the book's marker form `form` does not run on into the next page, and
    no paragraph runs on into or out of `section_pages`, the pages of the
    endnote section (spec section 12): the first line of its first page,
    and the first body line after its last page, start a paragraph."""
    entries: list[Entry] = []
    current: list[PlacedLine] = []
    current_run: BodyRun | None = None
    pending: list[MarginNote] = []
    before: PlacedLine | None = None
    page_before_has_figure = False
    for page in pages:
        for number, line in enumerate(page.body):
            run = _run_at(page.runs, number)
            if _continues_verse(current_run, run, number):
                starts = False
            elif run is not None or current_run is not None:
                # A run is a block of its own, and so is what follows it.
                starts = run is None or run.start == number or number == 0
            else:
                # The hyphen rule comes before the plate break (spec section 6).
                plate_break = (
                    number == 0
                    and (page.has_figure or page_before_has_figure)
                    and not (before is not None and hyphen_between(before, line))
                )
                note_break = number == 0 and (
                    _marker_led(current, form)
                    or _crosses_section_edge(before, line, section_pages)
                )
                starts = (
                    number in page.block_starts
                    or plate_break
                    or note_break
                    or starts_paragraph(line, before)
                )
            if starts:
                if current:
                    entries.append(_block(current, current_run))
                    entries.extend(pending)
                    pending = []
                current = []
                current_run = run
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
        entries.append(_block(current, current_run))
    entries.extend(pending)
    return tuple(entries)
