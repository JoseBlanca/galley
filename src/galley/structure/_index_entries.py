"""The entries of a printed index (spec section 17, rules 3 to 5), across
its columns and pages, and their place among the body's blocks (spec
section 2, step 3.4)."""

from collections.abc import Sequence
from dataclasses import dataclass, replace

from galley.model import BlockKind, Word
from galley.structure._lines import Piece, PlacedLine, with_words
from galley.structure._paragraphs import BodyBlock, Entry, PageParts


@dataclass(frozen=True, slots=True)
class _IndexRun:
    """The pages of one printed index, given by the positions in the book's
    pages of its first and last page with index lines."""

    first: int
    last: int


def _has_text(page: PageParts) -> bool:
    return bool(page.body or page.band_regions or page.margin_notes or page.index_lines)


def _index_runs(pages: Sequence[PageParts]) -> tuple[_IndexRun, ...]:
    """The runs of pages with index lines, a page without text between two
    of them not ending a run."""
    runs: list[_IndexRun] = []
    current: _IndexRun | None = None
    for position, page in enumerate(pages):
        if page.index_lines:
            current = (
                _IndexRun(position, position)
                if current is None
                else replace(current, last=position)
            )
        elif _has_text(page) and current is not None:
            runs.append(current)
            current = None
    if current is not None:
        runs.append(current)
    return tuple(runs)


def with_index_breaks(pages: Sequence[PageParts]) -> tuple[PageParts, ...]:
    """The pages with the first body line of each index page, and the first
    body line after each index, starting a block, so that no paragraph runs
    on into, over or out of an index (spec section 17)."""
    starts = {position for position, page in enumerate(pages) if page.index_lines}
    for run in _index_runs(pages):
        after = next(
            (
                position
                for position in range(run.last + 1, len(pages))
                if pages[position].body
            ),
            None,
        )
        if after is not None:
            starts.add(after)
    return tuple(
        replace(page, block_starts=page.block_starts | {0})
        if position in starts and page.body
        else page
        for position, page in enumerate(pages)
    )


def _entries(pages: Sequence[PageParts]) -> tuple[BodyBlock, ...]:
    """The index entries of `pages`, one index: the lines of each page's
    columns as one stream, an entry from a line that starts one to the line
    before the next (spec section 17, rules 3 and 4); a stream that starts
    with a line that starts none still starts an entry."""
    entries: list[list[PlacedLine]] = []
    for page in pages:
        for position, line in enumerate(page.index_lines):
            if not entries or position in page.index_starts:
                entries.append([])
            entries[-1].append(line)
    return tuple(
        BodyBlock(
            piece=Piece(part),
            kind=BlockKind.INDEX_ENTRY,
            level=_ENTRY_DEPTH if number == 0 else _SUB_ENTRY_DEPTH,
        )
        for lines in entries
        for number, part in enumerate(_printed_parts(lines))
    )


# Spec section 17, rule 5: an entry's depth is 1, a sub-entry's 2.
_ENTRY_DEPTH = 1
_SUB_ENTRY_DEPTH = 2


def _printed_parts(lines: Sequence[PlacedLine]) -> tuple[tuple[PlacedLine, ...], ...]:
    """The lines of an entry cut after each word that ends with ";", inside
    a line when the word is (spec section 17, rule 5): the entry, then each
    sub-entry; none of them empty."""
    parts: list[list[PlacedLine]] = [[]]
    for line in lines:
        words: list[Word] = []
        for word in line.line.words:
            words.append(word)
            if word.text.endswith(";"):
                parts[-1].append(with_words(line, tuple(words)))
                parts.append([])
                words = []
        if words:
            parts[-1].append(with_words(line, tuple(words)))
    return tuple(tuple(part) for part in parts if part)


def with_index_entries(
    entries: Sequence[Entry], pages: Sequence[PageParts]
) -> tuple[Entry, ...]:
    """`entries`, the body's, with the entries of each printed index of
    `pages` among them by page (spec section 2, step 3.4): each before the
    first entry of the body that starts on a later page than it does."""
    index_entries = tuple(
        entry
        for run in _index_runs(pages)
        for entry in _entries(pages[run.first : run.last + 1])
    )
    placed: list[Entry] = []
    waiting = 0
    for entry in entries:
        page_index = entry.piece.lines[0].page_index
        while (
            waiting < len(index_entries)
            and index_entries[waiting].piece.lines[0].page_index < page_index
        ):
            placed.append(index_entries[waiting])
            waiting += 1
        placed.append(entry)
    placed.extend(index_entries[waiting:])
    return tuple(placed)
