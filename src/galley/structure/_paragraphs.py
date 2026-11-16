"""Paragraphs, side text and the order of the blocks (spec section 6).

The per-page part, `page_parts`, runs on one page: what each region is,
what is removed, the body stream, and the side text cut into blocks. The
part across pages, `assemble`, runs once in page order: it finds the
paragraphs of the book's body stream, which run over page breaks, joins
the hyphens of every block, body and side text, puts each page's side
text after the paragraph in which its body ends, and numbers the blocks
and notes.
"""

import bisect
import itertools
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from typing import assert_never

from galley.model import (
    Block,
    BlockKind,
    Emphasis,
    Line,
    Note,
    NoteKind,
    Origin,
    PageLayout,
    PageNumber,
    Region,
    Removal,
    Span,
    WordChange,
)
from galley.structure._foot import body_column
from galley.structure._hyphens import PageLine, join_lines
from galley.structure._measures import (
    Edges,
    box_of,
    is_hyphen_first_part,
    is_number_before_word,
    is_short,
    region_edges,
)
from galley.structure._regions import RegionKind, region_kinds
from galley.structure._removals import foot_removals, head_removals
from galley.structure._survey import BookSurvey

# Spec section 6, rule 1: an indented line starts 5 to 40 pt right of its
# region's left edge (Stubbs' cut-in notes push lines 60 pt in), after a
# line that ends more than 3 pt short of its region's right edge.
_INDENT_MIN_PT = 5.0
_INDENT_MAX_PT = 40.0
_SHORT_LINE_PT = 3.0
# Spec section 6, rule 2: a centred line is at least 15 pt in from both
# edges, the two insets differing by at most 10 pt.
_CENTRED_INSET_MIN_PT = 15.0
_CENTRED_INSET_DIFFERENCE_PT = 10.0


@dataclass(frozen=True, slots=True)
class PlacedLine:
    """A line of a page with its page index, its region's edges, and the
    edges its centring is measured against: the region's, or the page's
    body column for a line of a short body region (spec section 6)."""

    page_index: int
    line: Line
    edges: Edges
    centring_edges: Edges


@dataclass(frozen=True, slots=True)
class Piece:
    """A block's lines, all on one page or over several, in order."""

    lines: tuple[PlacedLine, ...]


@dataclass(frozen=True, slots=True)
class PageParts:
    """What the per-page work gives for one page: the removals and page
    numbers, the body stream, the margin notes and the band blocks, each
    of one page, and whether the page has a figure."""

    removals: tuple[Removal, ...]
    page_numbers: tuple[PageNumber, ...]
    body: tuple[PlacedLine, ...]
    margin_notes: tuple[Piece, ...]
    band_blocks: tuple[Piece, ...]
    has_figure: bool


def _is_indented(line: PlacedLine, before: PlacedLine) -> bool:
    indent = line.line.box.x0 - line.edges.left
    return (
        _INDENT_MIN_PT <= indent <= _INDENT_MAX_PT
        and before.line.box.x1 < before.edges.right - _SHORT_LINE_PT
    )


def _is_centred(line: PlacedLine) -> bool:
    left_inset = line.line.box.x0 - line.centring_edges.left
    right_inset = line.centring_edges.right - line.line.box.x1
    return (
        left_inset >= _CENTRED_INSET_MIN_PT
        and right_inset >= _CENTRED_INSET_MIN_PT
        and abs(left_inset - right_inset) <= _CENTRED_INSET_DIFFERENCE_PT
    )


def _hyphen_between(before: PlacedLine, line: PlacedLine) -> bool:
    """Whether `before` ends with a hyphen that may join it to `line`: the
    first part of a join, unless a number before a word (spec section 6)."""
    if not before.line.words:
        return False
    last = before.line.words[-1].text
    return is_hyphen_first_part(last) and not (
        bool(line.line.words) and is_number_before_word(last, line.line.words[0].text)
    )


def _starts_paragraph(line: PlacedLine, before: PlacedLine | None) -> bool:
    """Whether `line` starts a paragraph after `before`, the line before it
    (spec section 6): never after a hyphen; else when it is indented after
    a short line, or it or the line before is centred."""
    if before is None:
        return True
    if _hyphen_between(before, line):
        return False
    return _is_indented(line, before) or _is_centred(line) or _is_centred(before)


def _pieces(lines: tuple[PlacedLine, ...]) -> tuple[Piece, ...]:
    """The lines of one band region cut into blocks by rules 1 and 2."""
    pieces: list[list[PlacedLine]] = []
    before: PlacedLine | None = None
    for line in lines:
        if not pieces or _starts_paragraph(line, before):
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
        band_blocks=tuple(
            piece
            for kind, lines in regions
            if kind is RegionKind.BAND
            for piece in _pieces(lines)
        ),
        has_figure=bool(page.figures),
    )


# Across pages


@dataclass(frozen=True, slots=True)
class _Paragraph:
    """A paragraph of the body stream, as a piece."""

    piece: Piece


@dataclass(frozen=True, slots=True)
class _MarginNote:
    piece: Piece


type _Entry = _Paragraph | _MarginNote


def _body_entries(pages: Sequence[PageParts]) -> tuple[_Entry, ...]:
    """The paragraphs of the book's body stream in order, each followed by
    the margin notes of the pages whose body ends in it; the margin notes
    of a page with no body stream after the last block so far."""
    entries: list[_Entry] = []
    current: list[PlacedLine] = []
    pending: list[_MarginNote] = []
    before: PlacedLine | None = None
    page_before_has_figure = False
    for page in pages:
        for number, line in enumerate(page.body):
            # The hyphen rule comes before the plate break (spec section 6).
            plate_break = (
                number == 0
                and (page.has_figure or page_before_has_figure)
                and not (before is not None and _hyphen_between(before, line))
            )
            if plate_break or _starts_paragraph(line, before):
                if current:
                    entries.append(_Paragraph(Piece(tuple(current))))
                    entries.extend(pending)
                    pending = []
                current = []
            current.append(line)
            before = line
        if page.body:
            page_before_has_figure = page.has_figure
        notes = tuple(_MarginNote(piece) for piece in page.margin_notes)
        if current:
            pending.extend(notes)
        else:
            entries.extend(notes)
    if current:
        entries.append(_Paragraph(Piece(tuple(current))))
    entries.extend(pending)
    return tuple(entries)


def _origin(piece: Piece) -> tuple[Origin, ...]:
    """One origin per page the piece has lines on, with the box of those
    lines."""
    return tuple(
        Origin(page_index, box_of(tuple(line.line.box for line in lines)))
        for page_index, lines in itertools.groupby(
            piece.lines, key=lambda line: line.page_index
        )
    )


@dataclass(frozen=True, slots=True)
class _Unnumbered:
    """A block before it has its id: its kind, text and origin."""

    kind: BlockKind
    text: str
    origin: tuple[Origin, ...]


def _joined(
    piece: Piece,
    kind: BlockKind,
    book_words: frozenset[str],
    word_list: frozenset[str],
) -> tuple[_Unnumbered, tuple[WordChange, ...]]:
    joined = join_lines(
        tuple(
            PageLine(line.page_index, tuple(word.text for word in line.line.words))
            for line in piece.lines
        ),
        book_words,
        word_list,
    )
    return _Unnumbered(kind, " ".join(joined.words), _origin(piece)), joined.changes


def _block(block_id: str, unnumbered: _Unnumbered) -> Block:
    return Block(
        id=block_id,
        kind=unnumbered.kind,
        level=None,
        label=None,
        spans=(Span(unnumbered.text, Emphasis.NONE, None),),
        figure=None,
        origin=unnumbered.origin,
    )


def _first_page(unnumbered: _Unnumbered) -> int:
    return unnumbered.origin[0].page_index


def _note_places(
    blocks: tuple[_Unnumbered, ...], notes: tuple[_Unnumbered, ...]
) -> tuple[int, ...]:
    """For each note, the position in `blocks` of the block markdown writes
    it after, -1 for first of all (spec section 6, "Order"): the last block
    whose first origin is on the note's first page or an earlier one."""
    first_pages = tuple(_first_page(block) for block in blocks)
    last_by_page: dict[int, int] = {}
    for position, page_index in enumerate(first_pages):
        last_by_page[page_index] = position
    pages = sorted(last_by_page)
    last_up_to = tuple(
        itertools.accumulate((last_by_page[page] for page in pages), max)
    )

    def place(note: _Unnumbered) -> int:
        up_to = bisect.bisect_right(pages, _first_page(note))
        return last_up_to[up_to - 1] if up_to > 0 else -1

    return tuple(place(note) for note in notes)


@dataclass(frozen=True, slots=True)
class Assembled:
    """The book's blocks and notes in order, with their ids, and the word
    changes of their hyphen joins in reading order."""

    blocks: tuple[Block, ...]
    notes: tuple[Note, ...]
    word_changes: tuple[WordChange, ...]


def _numbered(
    blocks: tuple[_Unnumbered, ...], notes: tuple[_Unnumbered, ...]
) -> tuple[tuple[Block, ...], tuple[Note, ...]]:
    """Block and note ids (spec section 6): a block's counts the blocks that
    start on its page in reading order, each note's block where markdown
    writes the note; a note's counts the notes that start on its page."""
    places = _note_places(blocks, notes)
    notes_after: dict[int, list[int]] = {}
    for note_number, position in enumerate(places):
        notes_after.setdefault(position, []).append(note_number)
    block_counts: Counter[int] = Counter()

    def next_id(unnumbered: _Unnumbered) -> str:
        page_index = _first_page(unnumbered)
        block_counts[page_index] += 1
        return f"b-p{page_index:04d}-{block_counts[page_index]:03d}"

    note_block_ids: dict[int, str] = {}
    body: list[Block] = []
    for position in range(-1, len(blocks)):
        if position >= 0:
            body.append(_block(next_id(blocks[position]), blocks[position]))
        for note_number in notes_after.get(position, []):
            note_block_ids[note_number] = next_id(notes[note_number])
    note_counts: Counter[int] = Counter()
    numbered_notes: list[Note] = []
    for note_number, note in enumerate(notes):
        page_index = _first_page(note)
        note_counts[page_index] += 1
        numbered_notes.append(
            Note(
                id=f"n-p{page_index:04d}-{note_counts[page_index]:03d}",
                kind=NoteKind.FOOTNOTE,
                marker="",
                blocks=(_block(note_block_ids[note_number], note),),
                origin=note.origin,
                referenced=False,
            )
        )
    return tuple(body), tuple(numbered_notes)


def assemble(
    pages: Sequence[PageParts], book_words: frozenset[str], word_list: frozenset[str]
) -> Assembled:
    """The work across pages (spec section 2, step 3), in page order: the
    paragraphs of the body stream with their hyphens joined, the margin
    notes after the paragraph in which their page's body ends, the band
    blocks as notes, and the ids. `word_list` is in lower case."""
    joined_blocks: list[_Unnumbered] = []
    body_changes: list[WordChange] = []
    for entry in _body_entries(pages):
        match entry:
            case _Paragraph(piece):
                kind = BlockKind.PARAGRAPH
            case _MarginNote(piece):
                kind = BlockKind.MARGIN_NOTE
            case _:
                assert_never(entry)
        block, changes = _joined(piece, kind, book_words, word_list)
        joined_blocks.append(block)
        body_changes.extend(changes)
    joined_notes: list[_Unnumbered] = []
    side_changes: list[WordChange] = []
    for page in pages:
        for piece in page.band_blocks:
            note, changes = _joined(piece, BlockKind.PARAGRAPH, book_words, word_list)
            joined_notes.append(note)
            side_changes.extend(changes)
    blocks, notes = _numbered(tuple(joined_blocks), tuple(joined_notes))
    return Assembled(
        blocks=blocks,
        notes=notes,
        word_changes=tuple(
            sorted(body_changes + side_changes, key=lambda change: change.page_index)
        ),
    )
