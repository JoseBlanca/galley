"""Paragraphs and side text (spec section 6).

The per-page part, `page_parts`, runs on one page: what each region is,
what is removed, the body stream, and the side text cut into blocks.
`body_entries` runs once in page order: it finds the paragraphs of the
book's body stream, which run over page breaks, and puts each page's
margin notes after the paragraph in which its body ends.
"""

from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import assert_never

from galley.model import (
    BlockKind,
    Box,
    FigureKind,
    Line,
    PageLayout,
    PageNumber,
    Region,
    Removal,
    RemovalReason,
)
from galley.structure._contents import ContentsEntry, contents_title
from galley.structure._epigraphs import epigraph_run, page_epigraphs
from galley.structure._foot import body_column
from galley.structure._headings import PageHead, heading_runs
from galley.structure._index import IndexPage, index_page
from galley.structure._lines import (
    Piece,
    PlacedLine,
    ends_paragraph_at_page_break,
    first_word,
    misread_marker_lines,
    starts_paragraph,
    text_edge,
)
from galley.structure._lists import ItemLine
from galley.structure._markers import MarkerForm, marker_form
from galley.structure._measures import (
    Edges,
    is_short,
    letters,
    region_edges,
    words_removal,
    words_text,
)
from galley.structure._regions import RegionKind, head_line, region_kinds
from galley.structure._removals import foot_removals, head_removals
from galley.structure._runs import CHAPTER_LEVEL, BodyRun, EpigraphParts, LabelLine
from galley.structure._summaries import summary_run
from galley.structure._survey import (
    BookSurvey,
    in_head_band,
    like_a_running_head,
)
from galley.structure._verse import verse_runs


@dataclass(frozen=True, slots=True)
class PageFigure:
    """A plate page's figure (spec section 18): the path of its image, its
    box on the page, and its caption lines from the top down, none when it
    has no caption."""

    image: str
    box: Box
    caption: Piece


@dataclass(frozen=True, slots=True)
class PageParts:
    """What the per-page work gives for one page: its index, the removals and page
    numbers, the body stream, the margin notes, the lines of each band
    region and the band blocks they make by rules 1 and 2, each of one
    page, a plate page's figure (spec section 18), the runs of the body
    stream that are blocks of their own (spec section 2, step 2.3), the
    positions of other lines of the body stream that start a block (a
    bibliographical note's band blocks, spec section 16), and the lines
    taken from the foot of the body stream as notes (spec section 11, "Notes left
    in the body"), none until they are taken. On an index page,
    `index_lines` are the lines of its columns, left then right, and
    `index_starts` the positions of those that start an entry (spec
    section 17). `in_page_figures` are the boxes of the page's in-page
    figures (`docs/specs/figures.md` §5)."""

    index: int
    removals: tuple[Removal, ...]
    page_numbers: tuple[PageNumber, ...]
    body: tuple[PlacedLine, ...]
    margin_notes: tuple[Piece, ...]
    band_regions: tuple[tuple[PlacedLine, ...], ...]
    band_blocks: tuple[Piece, ...]
    figure: PageFigure | None = None
    runs: tuple[BodyRun, ...] = ()
    block_starts: frozenset[int] = frozenset()
    body_notes: tuple[PlacedLine, ...] = ()
    index_lines: tuple[PlacedLine, ...] = ()
    index_starts: frozenset[int] = frozenset()
    in_page_figures: tuple[Box, ...] = ()


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


@dataclass(frozen=True, slots=True)
class _PageRuns:
    """The runs of a page's body stream that are blocks of their own, by
    their positions in the stream without `stray_marks`, the positions of
    the lines with no letter or digit an epigraph passed over, which are
    removed (spec section 22, rule 2)."""

    runs: tuple[BodyRun, ...]
    stray_marks: tuple[int, ...]


def _runs(
    page_index: int,
    body: Sequence[PlacedLine],
    band_regions: Sequence[Sequence[PlacedLine]],
    head: PageHead,
    kept_head: int | None,
    survey: BookSurvey,
    contents_pages: frozenset[int],
    column: Edges | None,
) -> _PageRuns:
    """The runs of the body stream that are blocks of their own (spec
    section 2, step 2.3), in order: the headings, the chapter summary under
    a heading, the epigraphs under a level-1 heading or the page's one
    epigraph, and the verse; on a page of the printed table of contents,
    only the title of a contents run on the run's first page, a heading of
    level 1, with the stray marks above it (spec section 30, rule 1).
    `kept_head` is the position in `body` of the page's head line
    that section 3 left in the text near the book's head lines
    (`_kept_head_line`), or None; `column` the page's body column."""
    if page_index in contents_pages:
        if page_index - 1 in contents_pages:
            return _PageRuns((), ())
        title = contents_title(body)
        start = None if title.title is None else title.title - len(title.stray_marks)
        return _PageRuns(
            ()
            if start is None
            else (
                BodyRun(
                    start=start,
                    end=start + 1,
                    kind=BlockKind.HEADING,
                    level=CHAPTER_LEVEL,
                ),
            ),
            title.stray_marks,
        )
    band_lines = tuple(line for region in band_regions for line in region)
    headings = heading_runs(
        body,
        band_lines,
        survey.body_line_pitch,
        head,
        kept_head,
        _like_running_heads(body, survey),
    )
    # Each heading's summary ends at the next heading at the latest.
    limits = (*(run.start for run in headings[1:]), len(body))
    summaries = tuple(
        summary
        for number, heading in enumerate(headings)
        if (summary := summary_run(body, heading.end, limits[number])) is not None
    )
    epigraphs = page_epigraphs(body, headings, summaries, column)
    stray_marks = tuple(
        number for epigraph in epigraphs for number in epigraph.stray_marks
    )

    def shift(number: int) -> int:
        return number - sum(1 for stray in stray_marks if stray < number)

    taken = frozenset(
        number for run in headings + summaries for number in range(run.start, run.end)
    ) | frozenset(
        number
        for epigraph in epigraphs
        for number in range(epigraph.start, epigraph.end)
    )
    shifted = tuple(
        replace(run, start=shift(run.start), end=shift(run.end))
        for run in headings + summaries + verse_runs(body, taken)
    ) + tuple(epigraph_run(epigraph, shift) for epigraph in epigraphs)
    return _PageRuns(tuple(sorted(shifted, key=lambda run: run.start)), stray_marks)


def _kept_head_line(page: PageLayout, survey: BookSurvey) -> Line | None:
    """The text line of the page's head line when section 3 left it in the
    text and it lies in the band where running heads are looked for, at
    most 2 pitches below the median top of the book's head lines or
    anywhere above it (`in_head_band`): never a flush-left heading line
    unless it starts with a chapter label word (spec section 14, rule 1).
    None otherwise."""
    head = head_line(page)
    if (
        head is None
        or page.index in survey.running_heads
        or survey.median_head_top is None
    ):
        return None
    line = head.region.lines[-1]
    within = in_head_band(line.box.top, survey.median_head_top, survey.body_line_pitch)
    return line if within else None


def _like_running_heads(
    body: Sequence[PlacedLine], survey: BookSurvey
) -> frozenset[int]:
    """The positions in `body`, a page's body stream, of the lines that are
    never headings (spec section 14): those whose top lies at most 2
    pitches below the median top of the book's head lines, or above it,
    and whose letters are at least 0.6 alike to a running head's."""
    if survey.median_head_top is None:
        return frozenset()
    median_head_top = survey.median_head_top
    return frozenset(
        number
        for number, line in enumerate(body)
        if in_head_band(line.line.box.top, median_head_top, survey.body_line_pitch)
        and like_a_running_head(
            letters(words_text(line.line.words)), survey.running_head_letters
        )
    )


def page_parts(
    page: PageLayout, survey: BookSurvey, contents_pages: frozenset[int] = frozenset()
) -> PageParts:
    """The per-page work on `page` (spec section 2, step 2). `contents_pages`
    are the page indices of the printed table of contents, on which the
    only heading is a contents run's title (spec section 30, rule 1)."""
    kinds = region_kinds(page, survey.body_word_height, survey.running_heads)
    head = head_removals(page, survey)
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

    # Spec section 6, rule 3: a hanging number starts a paragraph only in
    # the body stream, and not on a page of the printed contents.
    text_edges = tuple(
        text_edge(region.lines)
        if kind is RegionKind.BODY and page.index not in contents_pages
        else None
        for region, kind in zip(page.regions, kinds, strict=True)
    )
    regions = tuple(
        (
            kind,
            tuple(
                PlacedLine(
                    page.index,
                    line,
                    edges,
                    centring_edges(region, kind, edges),
                    text_edges[region_number],
                )
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
    # The head line, the first region's last line, is then the last of
    # that region's lines that open the body stream.
    head_line_kept = (
        _kept_head_line(page, survey) is not None
        and regions
        and regions[0][0] is RegionKind.BODY
        and regions[0][1]
        and regions[0][1][-1].line == page.regions[0].lines[-1]
    )
    kept_head = len(regions[0][1]) - 1 if head_line_kept else None
    index_lines = _index_lines(page.index, index)
    page_head = (
        PageHead.RUNNING_HEAD
        if any(
            removal.reason is RemovalReason.RUNNING_HEAD for removal in head.removals
        )
        else PageHead.NO_RUNNING_HEAD
    )
    # Spec section 17, rule 4: the index columns are the page's body or
    # band lines for the title's centring (section 14, rule 1).
    page_runs = _runs(
        page.index,
        body,
        (*band_regions, index_lines),
        page_head,
        kept_head,
        survey,
        contents_pages,
        column,
    )
    # Spec section 22, rule 2: the specks an epigraph passed over.
    strays = frozenset(page_runs.stray_marks)
    stray_removals = tuple(
        words_removal(page.index, body[number].line.words, RemovalReason.STRAY_MARK)
        for number in page_runs.stray_marks
    )
    body = tuple(line for number, line in enumerate(body) if number not in strays)
    return PageParts(
        index=page.index,
        removals=head.removals
        + (index.removals if index is not None else ())
        + foot.removals
        + stray_removals,
        page_numbers=head.page_numbers
        + (index.page_numbers if index is not None else ())
        + foot.page_numbers,
        body=body,
        # Spec section 6, rule 3: a note's "1" the OCR misread starts one.
        block_starts=misread_marker_lines(body),
        margin_notes=tuple(
            Piece(lines)
            for kind, lines in regions
            if kind is RegionKind.MARGIN and lines
        ),
        band_regions=band_regions,
        band_blocks=tuple(piece for lines in band_regions for piece in _pieces(lines)),
        runs=page_runs.runs,
        index_lines=index_lines,
        index_starts=index.starts if index is not None else frozenset(),
        in_page_figures=tuple(
            figure.box for figure in page.figures if figure.kind is FigureKind.IN_PAGE
        ),
    )


def _index_lines(page_index: int, index: IndexPage | None) -> tuple[PlacedLine, ...]:
    """The lines of an index page's columns, each with its column's edges."""
    if index is None:
        return ()
    return tuple(
        PlacedLine(page_index, line, edges, edges)
        for line, edges in zip(index.lines, index.column_edges, strict=True)
    )


# Across pages


@dataclass(frozen=True, slots=True, kw_only=True)
class BodyBlock:
    """A block of the body stream, as a piece: a paragraph, a run of
    section 2, step 2.3, a list item or a contents entry, with its kind, a
    heading's level and whether its first line is its chapter label, an
    epigraph's quotation and source, a list item's marker as printed
    (spec section 29), and a contents entry's parts (section 30)."""

    piece: Piece
    kind: BlockKind = BlockKind.PARAGRAPH
    level: int | None = None
    label_line: LabelLine = LabelLine.NONE
    epigraph: EpigraphParts | None = None
    marker: str | None = None
    contents: ContentsEntry | None = None


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


def _short_page_end(
    before: PlacedLine | None, before_page: PageParts | None, page: PageParts
) -> bool:
    """Whether `before`, the last body line of `before_page`, a page before
    `page`, ends the paragraph at the page break before the first body
    line of `page` (spec section 6, "A short last line at a page break"):
    not on an index page, either side (section 17)."""
    return (
        before is not None
        and before_page is not None
        and not before_page.index_lines
        and not page.index_lines
        and bool(page.body)
        and not _note_led(before)
        and ends_paragraph_at_page_break(before, page.body[0])
    )


def _note_led(line: PlacedLine) -> bool:
    """Whether `line` starts with a note's marker followed by text: the
    first line of a footnote left in the body (spec section 6, "A short
    last line at a page break")."""
    return len(line.line.words) > 1 and marker_form(first_word(line)) is not None


def _block(
    lines: Sequence[PlacedLine], run: BodyRun | None, role: LineRole | None
) -> BodyBlock:
    """The block of `lines`, made by `run` when it is one of section 2,
    step 2.3, else by `role`, the role of its first line, when it is a
    list item or a contents entry, else a paragraph."""
    piece = Piece(tuple(lines))
    match role:
        case ItemLine(marker=marker) if marker is not None:
            return BodyBlock(piece=piece, kind=BlockKind.LIST_ITEM, marker=marker.text)
        case ContentsLine(entry=entry) if entry is not None:
            return BodyBlock(
                piece=piece,
                kind=BlockKind.CONTENTS_ENTRY,
                level=entry.level,
                contents=entry,
            )
        case _:
            pass
    if run is None:
        return BodyBlock(piece=piece)
    return BodyBlock(
        piece=piece,
        kind=run.kind,
        level=run.level,
        label_line=run.label_line,
        epigraph=run.epigraph,
    )


@dataclass(frozen=True, slots=True)
class ContentsLine:
    """A line of a contents entry: `entry` is the entry on its first line,
    None on its other lines (spec section 30)."""

    entry: ContentsEntry | None


type LineRole = ItemLine | ContentsLine


def _starts_by_role(role: LineRole, current_role: LineRole | None) -> bool:
    """Whether a line of `role` starts a block after a line of
    `current_role`, None for a line of a paragraph or a run: an item's
    marker line and an entry's first line do, and so does any line after
    a paragraph or run (spec sections 29 and 30)."""
    match role:
        case ItemLine(marker=marker):
            return marker is not None or not isinstance(current_role, ItemLine)
        case ContentsLine(entry=entry):
            return entry is not None or not isinstance(current_role, ContentsLine)
        case _:
            assert_never(role)


def body_entries(
    pages: Sequence[PageParts],
    form: MarkerForm | None = None,
    section_pages: range = range(0),
    roles: frozendict[tuple[int, int], LineRole] = frozendict(),
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
    and the first body line after its last page, start a paragraph. A
    page's last line that ends short with a sentence's end ends its
    paragraph, but on an index page (spec section 6). `roles` gives the
    lines of the list items and contents entries by their page index and
    position in their page's body stream (spec sections 29 and 30): each
    item and entry is a block, whose lines the paragraph rules do not
    look at, and the line after the last starts a block."""
    entries: list[Entry] = []
    current: list[PlacedLine] = []
    current_run: BodyRun | None = None
    current_role: LineRole | None = None
    pending: list[MarginNote] = []
    before: PlacedLine | None = None
    before_page: PageParts | None = None
    for page in pages:
        for number, line in enumerate(page.body):
            run = _run_at(page.runs, number)
            role = roles.get((page.index, number))
            if role is not None:
                starts = _starts_by_role(role, current_role)
            elif current_role is not None:
                starts = True
            elif _continues_verse(current_run, run, number):
                starts = False
            elif run is not None or current_run is not None:
                # A run is a block of its own, and so is what follows it.
                starts = run is None or run.start == number or number == 0
            else:
                note_break = number == 0 and (
                    _marker_led(current, form)
                    or _crosses_section_edge(before, line, section_pages)
                    or _short_page_end(before, before_page, page)
                )
                starts = (
                    number in page.block_starts
                    or note_break
                    or starts_paragraph(line, before)
                )
            if starts:
                if current:
                    entries.append(_block(current, current_run, current_role))
                    entries.extend(pending)
                    pending = []
                current = []
                current_run = run
                current_role = role
            current.append(line)
            before = line
            before_page = page
        notes = tuple(MarginNote(piece) for piece in page.margin_notes)
        if current:
            pending.extend(notes)
        else:
            entries.extend(notes)
    if current:
        entries.append(_block(current, current_run, current_role))
    entries.extend(pending)
    return tuple(entries)
