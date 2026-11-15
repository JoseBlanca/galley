"""galley's side of the comparison: the tokens of its four stage outputs
(spec section 5, "galley's tokens").

Each output becomes a tuple of GalleyToken, a word with its page index,
its stream, whether it sits on the first or last line of its page, and its
block's id:

- words: every word of `words.json`, page by page, in the file's order;
- lines: every word of `lines.json`, page by page, region by region, line
  by line;
- blocks: the tokens of each block of `blocks.json`, split as the
  fidelity check splits them at the markdown boundary: a note reference
  span is a space, not a token, and so is the marker of a referenced
  note; the marker of an unreferenced note is a word of the book, the
  first tokens of the note's first block. The body blocks come in order, with the margin notes in their place, then
  the notes' blocks;
- markdown: the words of `book.md` as `galley.fidelity.read_markdown`
  reads them, each in the block its id names.

A word's text is split on white space, as the fidelity check splits it.

How the spec is read here, where it leaves a choice:

- `edge_of_page` flags, in `lines.json`'s order of a page's lines, the
  first and the last line that hold a token with a non-empty alignment
  key, and the lines of marks only before the first and after the last
  (spec section 5). In words.json, a word is flagged when the same word,
  text and box, is on such a line.
- A block token's page is found by aligning the block's tokens with the
  words of the pages in its `origin`, in `lines.json`'s order, with
  `difflib.SequenceMatcher(autojunk=False)` over their texts. In a
  replaced stretch the k-th token takes the page of the k-th word of the
  stretch, or of its last when the stretch has fewer words: "replicate"
  against "repli-" "cate" takes the page of "repli-". A token with no
  word against it takes the page of the word before, else after, else
  the first page of the block's origin.
- A markdown word's page is found the same way, by aligning the words of
  each block in `book.md` with that block's tokens at blocks.
- A margin note inside a note is in the notes stream, as the alignment
  takes it.
- At markdown, a note reference is placed before the token of its block
  that it precedes at blocks, counted from the block's start, since
  Pandoc's words carry no place for a note.
"""

from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import assert_never

from galley.book_folder import BookFolder
from galley.fidelity import MarkdownWords, read_markdown
from galley.model import (
    Block,
    BlockKind,
    BlocksFile,
    Line,
    LinesFile,
    Note,
    PageLayout,
    Word,
    WordsFile,
    read_blocks,
    read_lines,
    read_words,
)
from galley_eval.align import GalleyStream, GalleyToken, alignment_key
from galley_eval.errors import GalleyFilesError

__all__ = [
    "GalleyBlock",
    "GalleyNoteReference",
    "GalleySide",
    "blocks_tokens",
    "galley_blocks",
    "lines_tokens",
    "markdown_tokens",
    "note_references",
    "read_galley_side",
    "words_tokens",
]


@dataclass(frozen=True, slots=True, kw_only=True)
class GalleyBlock:
    """A block of `blocks.json`: its kind, its stream, and the id of the
    note it is in, None in the body."""

    kind: BlockKind
    stream: GalleyStream
    note_id: str | None


@dataclass(frozen=True, slots=True, kw_only=True)
class GalleyNoteReference:
    """A note reference of `blocks.json`: the note it points to, the block
    it is in, and the number of that block's tokens before it."""

    note_id: str
    block_id: str
    tokens_before: int


@dataclass(frozen=True, slots=True, kw_only=True)
class GalleySide:
    """galley's files of one book, as the comparison uses them: the tokens
    of each stage output, the blocks by id, the note references, and
    `words.json` itself, for the page table."""

    words: tuple[GalleyToken, ...]
    lines: tuple[GalleyToken, ...]
    blocks: tuple[GalleyToken, ...]
    markdown: tuple[GalleyToken, ...]
    galley_blocks: frozendict[str, GalleyBlock]
    note_references: tuple[GalleyNoteReference, ...]
    words_file: WordsFile


def read_galley_side(folder: BookFolder) -> GalleySide:
    """galley's files in `folder` read into a GalleySide. Raises galley's
    InputFileError for a file that is missing or malformed,
    ExternalProgramError when Pandoc cannot read `book.md`, and
    GalleyFilesError when the files do not fit together."""
    words = read_words(folder.words_json)
    lines = read_lines(folder.lines_json)
    blocks = read_blocks(folder.blocks_json)
    try:
        markdown_text = folder.book_md.read_text(encoding="utf-8")
    except FileNotFoundError as err:
        message = (
            f"{folder.book_md} does not exist; run `galley2epub markdown` to write it"
        )
        raise GalleyFilesError(message) from err
    markdown = read_markdown(markdown_text)
    blocks_side = blocks_tokens(blocks, lines)
    return GalleySide(
        words=words_tokens(words, lines),
        lines=lines_tokens(lines),
        blocks=blocks_side,
        markdown=markdown_tokens(markdown, blocks, blocks_side),
        galley_blocks=galley_blocks(blocks),
        note_references=note_references(blocks),
        words_file=words,
    )


# words and lines


def _edge_flags(page_lines: tuple[Line, ...]) -> tuple[bool, ...]:
    """For each line of a page, whether it is on the edge: the first and
    the last line that hold a token with a non-empty alignment key, and
    the lines of marks only before the first and after the last. A page
    of marks only is all on the edge."""
    keyed = tuple(
        position
        for position, line in enumerate(page_lines)
        if any(alignment_key(word.text) for word in line.words)
    )
    if not keyed:
        return tuple(True for _ in page_lines)
    first, last = keyed[0], keyed[-1]
    return tuple(
        position <= first or position >= last for position in range(len(page_lines))
    )


def _page_lines(page: PageLayout) -> tuple[Line, ...]:
    return tuple(line for region in page.regions for line in region.lines)


def _edge_lines(lines: LinesFile) -> frozendict[int, tuple[Word, ...]]:
    """For each page, the words of its lines on the edge."""
    edges: dict[int, tuple[Word, ...]] = {}
    for page in lines.pages:
        page_lines = _page_lines(page)
        edges[page.index] = tuple(
            word
            for line, edge in zip(page_lines, _edge_flags(page_lines), strict=True)
            if edge
            for word in line.words
        )
    return frozendict(edges)


def words_tokens(words: WordsFile, lines: LinesFile) -> tuple[GalleyToken, ...]:
    """The tokens of `words.json`, page by page in the file's order, each
    flagged `edge_of_page` when the same word, text and box, is on a line
    of its page on the edge in `lines` (_edge_flags)."""
    edges = _edge_lines(lines)
    tokens: list[GalleyToken] = []
    for page in words.pages:
        on_edge = list(edges.get(page.index, ()))
        for word in page.words:
            edge = word in on_edge
            if edge:
                on_edge.remove(word)
            tokens.extend(_split(word.text, page.index, edge_of_page=edge))
    return tuple(tokens)


def lines_tokens(lines: LinesFile) -> tuple[GalleyToken, ...]:
    """The tokens of `lines.json`, page by page, region by region, line by
    line, those of a page's lines on the edge (_edge_flags) flagged
    `edge_of_page`."""
    tokens: list[GalleyToken] = []
    for page in lines.pages:
        page_lines = _page_lines(page)
        for line, edge in zip(page_lines, _edge_flags(page_lines), strict=True):
            for word in line.words:
                tokens.extend(_split(word.text, page.index, edge_of_page=edge))
    return tuple(tokens)


def _split(
    text: str, page_index: int, *, edge_of_page: bool
) -> tuple[GalleyToken, ...]:
    return tuple(
        GalleyToken(
            text=part,
            page_index=page_index,
            stream=GalleyStream.BODY,
            edge_of_page=edge_of_page,
            block_id=None,
        )
        for part in text.split()
    )


# blocks


def _block_stream(block: Block, *, in_note: bool) -> GalleyStream:
    if in_note:
        return GalleyStream.NOTES
    if block.kind is BlockKind.MARGIN_NOTE:
        return GalleyStream.MARGIN_NOTES
    return GalleyStream.BODY


def galley_blocks(blocks: BlocksFile) -> frozendict[str, GalleyBlock]:
    """Every block of `blocks`, the body's and the notes', by its id."""
    body = {
        block.id: GalleyBlock(
            kind=block.kind,
            stream=_block_stream(block, in_note=False),
            note_id=None,
        )
        for block in blocks.blocks
    }
    notes = {
        block.id: GalleyBlock(
            kind=block.kind, stream=GalleyStream.NOTES, note_id=note.id
        )
        for note in blocks.notes
        for block in note.blocks
    }
    return frozendict(body | notes)


def _block_texts(block: Block, marker: str) -> tuple[str, ...]:
    """The tokens of a block as the fidelity check splits them at the
    markdown boundary: a note reference span is a space; `marker`, the
    marker of an unreferenced note before its first block, else "", comes
    first."""
    text = "".join(
        " " if span.note_ref is not None else span.text for span in block.spans
    )
    return tuple(marker.split()) + tuple(text.split())


def _blocks_with_markers(blocks: BlocksFile) -> tuple[tuple[Block, str, bool], ...]:
    """Every block, the body's then the notes', with the marker its text
    starts with and whether it is in a note. Raises GalleyFilesError for
    an unreferenced note with no block to hold its marker."""
    found: list[tuple[Block, str, bool]] = [
        (block, "", False) for block in blocks.blocks
    ]
    for note in blocks.notes:
        if not note.blocks:
            message = f"note {note.id} of blocks.json has no block"
            raise GalleyFilesError(message)
        found.extend(
            (block, _marker(note) if position == 0 else "", True)
            for position, block in enumerate(note.blocks)
        )
    return tuple(found)


def _marker(note: Note) -> str:
    return "" if note.referenced else note.marker


def note_references(blocks: BlocksFile) -> tuple[GalleyNoteReference, ...]:
    """The note references of every block, the body's then the notes', in
    order, each with the number of its block's tokens before it."""
    found: list[GalleyNoteReference] = []
    for block, marker, _ in _blocks_with_markers(blocks):
        before = marker + " "
        for span in block.spans:
            if span.note_ref is not None:
                found.append(
                    GalleyNoteReference(
                        note_id=span.note_ref,
                        block_id=block.id,
                        tokens_before=len(before.split()),
                    )
                )
                before += " "
            else:
                before += span.text
    return tuple(found)


def blocks_tokens(blocks: BlocksFile, lines: LinesFile) -> tuple[GalleyToken, ...]:
    """The tokens of `blocks`: the body's blocks in order, margin notes in
    their place, then the notes' blocks. Each token has the page of the
    same word in `lines`, found by aligning its block with the words of
    the pages in the block's origin. Raises GalleyFilesError for a block
    with no origin or with a page of its origin that `lines` lacks."""
    page_words = {
        page.index: tuple(
            word
            for region in page.regions
            for line in region.lines
            for item in line.words
            for word in item.text.split()
        )
        for page in lines.pages
    }
    return tuple(
        token
        for block, marker, in_note in _blocks_with_markers(blocks)
        for token in _tokens_of_block(block, marker, page_words, in_note=in_note)
    )


def _tokens_of_block(
    block: Block, marker: str, page_words: dict[int, tuple[str, ...]], *, in_note: bool
) -> tuple[GalleyToken, ...]:
    pages = tuple(dict.fromkeys(origin.page_index for origin in block.origin))
    if not pages:
        message = f"block {block.id} of blocks.json has no origin, so no page"
        raise GalleyFilesError(message)
    missing = tuple(page for page in pages if page not in page_words)
    if missing:
        message = (
            f"block {block.id} of blocks.json was printed on page {missing[0]}, "
            "which lines.json does not have"
        )
        raise GalleyFilesError(message)
    source = tuple((word, page) for page in pages for word in page_words[page])
    texts = _block_texts(block, marker)
    stream = _block_stream(block, in_note=in_note)
    return tuple(
        GalleyToken(
            text=text,
            page_index=page,
            stream=stream,
            edge_of_page=False,
            block_id=block.id,
        )
        for text, page in zip(
            texts, _pages_through(texts, source, pages[0]), strict=True
        )
    )


def _pages_through(
    texts: tuple[str, ...], source: tuple[tuple[str, int], ...], fallback: int
) -> tuple[int, ...]:
    """The page of each of `texts`, from the (text, page) pairs of
    `source` they align with; `fallback` when `source` is empty."""
    if not source:
        return tuple(fallback for _ in texts)
    pages: list[int] = [fallback] * len(texts)
    matcher = SequenceMatcher(
        None, tuple(text for text, _ in source), texts, autojunk=False
    )
    for tag, source_start, source_end, start, end in matcher.get_opcodes():
        match tag:
            case "equal" | "replace":
                for offset in range(end - start):
                    at = min(source_start + offset, source_end - 1)
                    pages[start + offset] = source[at][1]
            case "insert":
                at = source_start - 1 if source_start > 0 else source_start
                for offset in range(end - start):
                    pages[start + offset] = source[min(at, len(source) - 1)][1]
            case "delete":
                pass  # words of the source that the texts lack give no page
            case _:
                message = f"difflib gave an unknown operation {tag!r}"
                raise AssertionError(message)
    return tuple(pages)


# markdown


def markdown_tokens(
    markdown: MarkdownWords, blocks: BlocksFile, blocks_side: tuple[GalleyToken, ...]
) -> tuple[GalleyToken, ...]:
    """The words of `book.md`, in its order, each with the stream of the
    block its id names and the page of the same word in that block at
    blocks, `blocks_side`. Raises GalleyFilesError for a word in no block
    or in a block that `blocks` does not have."""
    known = galley_blocks(blocks)
    by_block: dict[str, list[tuple[str, int]]] = {}
    for token in blocks_side:
        assert token.block_id is not None  # every token of blocks has a block
        by_block.setdefault(token.block_id, []).append((token.text, token.page_index))
    first_page = {
        block.id: block.origin[0].page_index
        for block in blocks.blocks
        + tuple(block for note in blocks.notes for block in note.blocks)
        if block.origin
    }
    grouped: dict[str, list[int]] = {}
    for position, word in enumerate(markdown.words):
        match word.block_id:
            case None:
                message = f"word {word.text!r} of book.md is in no block with an id"
                raise GalleyFilesError(message)
            case str() as block_id if block_id not in known:
                message = (
                    f"word {word.text!r} of book.md is in block {block_id}, "
                    "which blocks.json does not have"
                )
                raise GalleyFilesError(message)
            case str() as block_id:
                grouped.setdefault(block_id, []).append(position)
            case _:
                assert_never(word.block_id)
    pages: dict[int, int] = {}
    for block_id, positions in grouped.items():
        if block_id not in first_page:
            message = f"block {block_id} of blocks.json has no origin, so no page"
            raise GalleyFilesError(message)
        texts = tuple(markdown.words[position].text for position in positions)
        found = _pages_through(
            texts, tuple(by_block.get(block_id, ())), first_page[block_id]
        )
        pages.update(zip(positions, found, strict=True))
    return tuple(
        GalleyToken(
            text=word.text,
            page_index=pages[position],
            stream=known[block_id].stream,
            edge_of_page=False,
            block_id=block_id,
        )
        for position, word in enumerate(markdown.words)
        if (block_id := word.block_id) is not None
    )
