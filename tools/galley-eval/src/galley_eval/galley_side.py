"""galley's side of the comparison: the tokens of its four stage outputs
(spec section 5, "galley's tokens").

Each output becomes a tuple of GalleyToken, a word with its page index,
its stream, whether it sits on the first or last line of its page, and its
block's id:

- words: every word of `words.json`, page by page, in the file's order;
- lines: every word of `lines.json`, page by page, region by region, line
  by line;
- blocks: the tokens of each block of `blocks.json`, split as the
  fidelity check splits them at the markdown boundary: a heading's label
  first; a note reference span is a space, not a token, whether it points
  to a footnote or an endnote; the marker of a referenced footnote is not
  a token; the marker of an unreferenced footnote, and of every endnote,
  is a word of the book, the first tokens of the note's first block that
  is not a margin note. The body blocks come in order, with the margin
  notes in their place, then the notes' blocks;
- markdown: the words of `book.md` as `galley.fidelity.read_markdown`
  reads them, each in the block its id names, without the words of the
  links to endnotes.

At blocks and markdown, the words of an endnote that galley links from a
reference carry the page of its first reference, in galley's order, as
`near_page`: the page of the token before the reference in its block, or
of the block's first token when the reference opens it.

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
- At markdown, the words of a heading's label are its block's first
  words, as many as the label has, since markdown writes it first.
- At markdown, the words of a link to an endnote are found by aligning
  each block's words, with `difflib.SequenceMatcher(autojunk=False)` over
  their texts, with its tokens at blocks with the words of its references
  to endnotes put back in their places; a word on an equal or replaced
  stretch against a put-back word is dropped.
"""

import dataclasses
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
    NoteKind,
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
    "endnote_pages",
    "galley_blocks",
    "lines_tokens",
    "markdown_tokens",
    "note_references",
    "read_galley_side",
    "words_tokens",
]


@dataclass(frozen=True, slots=True, kw_only=True)
class GalleyBlock:
    """A block of `blocks.json`: its kind, its stream, the id of the note
    it is in, None in the body, and the kind of that note; whether it is a
    heading with a label; and the page index of its first origin, None
    for a block without one."""

    kind: BlockKind
    stream: GalleyStream
    note_id: str | None
    note_kind: NoteKind | None = None
    has_label: bool = False
    first_page: int | None = None


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
    references = note_references(blocks)
    return GalleySide(
        words=words_tokens(words, lines),
        lines=lines_tokens(lines),
        blocks=endnote_pages(blocks_side, blocks, references),
        markdown=endnote_pages(
            markdown_tokens(markdown, blocks, blocks_side), blocks, references
        ),
        galley_blocks=galley_blocks(blocks),
        note_references=references,
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


def _first_page(block: Block) -> int | None:
    return block.origin[0].page_index if block.origin else None


def galley_blocks(blocks: BlocksFile) -> frozendict[str, GalleyBlock]:
    """Every block of `blocks`, the body's and the notes', by its id."""
    body = {
        block.id: GalleyBlock(
            kind=block.kind,
            stream=_block_stream(block, in_note=False),
            note_id=None,
            has_label=block.label is not None,
            first_page=_first_page(block),
        )
        for block in blocks.blocks
    }
    notes = {
        block.id: GalleyBlock(
            kind=block.kind,
            stream=GalleyStream.NOTES,
            note_id=note.id,
            note_kind=note.kind,
            has_label=block.label is not None,
            first_page=_first_page(block),
        )
        for note in blocks.notes
        for block in note.blocks
    }
    return frozendict(body | notes)


def _prefix(block: Block, marker: str) -> tuple[str, ...]:
    """The tokens a block's text starts with before its spans': a
    heading's label, then `marker`, the marker its note prints before it,
    else ""."""
    label = block.label.split() if block.label is not None else []
    return (*label, *marker.split())


def _block_texts(block: Block, marker: str) -> tuple[str, ...]:
    """The tokens of a block as the fidelity check splits them at the
    markdown boundary: its _prefix, then its spans', a note reference
    span being a space."""
    text = "".join(
        " " if span.note_ref is not None else span.text for span in block.spans
    )
    return _prefix(block, marker) + tuple(text.split())


def _blocks_with_markers(blocks: BlocksFile) -> tuple[tuple[Block, str, bool], ...]:
    """Every block, the body's then the notes', with the marker its text
    starts with and whether it is in a note: a note's marker, when it is
    printed, goes before its first block that is not a margin note, else
    before its first block. Raises GalleyFilesError for a note with no
    block."""
    found: list[tuple[Block, str, bool]] = [
        (block, "", False) for block in blocks.blocks
    ]
    for note in blocks.notes:
        if not note.blocks:
            message = f"note {note.id} of blocks.json has no block"
            raise GalleyFilesError(message)
        marked = next(
            (
                position
                for position, block in enumerate(note.blocks)
                if block.kind is not BlockKind.MARGIN_NOTE
            ),
            0,
        )
        found.extend(
            (block, _marker(note) if position == marked else "", True)
            for position, block in enumerate(note.blocks)
        )
    return tuple(found)


def _marker(note: Note) -> str:
    """The marker as markdown prints it: that of an unreferenced footnote
    and of every endnote; a referenced footnote's is Pandoc's number."""
    if note.kind is NoteKind.ENDNOTE or not note.referenced:
        return note.marker
    return ""


def note_references(blocks: BlocksFile) -> tuple[GalleyNoteReference, ...]:
    """The note references of every block, the body's then the notes', in
    order, each with the number of its block's tokens before it."""
    found: list[GalleyNoteReference] = []
    for block, marker, _ in _blocks_with_markers(blocks):
        before = " ".join(_prefix(block, marker)) + " "
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


def endnote_pages(
    tokens: tuple[GalleyToken, ...],
    blocks: BlocksFile,
    references: tuple[GalleyNoteReference, ...],
) -> tuple[GalleyToken, ...]:
    """`tokens`, of blocks or markdown, with the words of each endnote
    that galley links from a reference given the page of its first
    reference as `near_page`: the page of the token before the reference
    in its block, or of the block's first token when the reference opens
    it. A reference in a block with no token at this output gives no
    page."""
    endnotes = frozendict(
        {
            block.id: note.id
            for note in blocks.notes
            if note.kind is NoteKind.ENDNOTE
            for block in note.blocks
        }
    )
    if not endnotes:
        return tokens
    linked = frozenset(endnotes.values())
    positions: dict[str, list[int]] = {}
    for index, token in enumerate(tokens):
        if token.block_id is not None:
            positions.setdefault(token.block_id, []).append(index)
    pages: dict[str, int] = {}
    for reference in references:
        if reference.note_id not in linked or reference.note_id in pages:
            continue
        found = positions.get(reference.block_id, [])
        if not found:
            continue  # no token of its block at this output
        at = found[max(min(reference.tokens_before, len(found)) - 1, 0)]
        pages[reference.note_id] = tokens[at].page_index
    return tuple(
        dataclasses.replace(token, near_page=pages[note_id])
        if token.block_id is not None
        and (note_id := endnotes.get(token.block_id)) is not None
        and note_id in pages
        else token
        for token in tokens
    )


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
    label = _label_length(block)
    return tuple(
        GalleyToken(
            text=text,
            page_index=page,
            stream=stream,
            edge_of_page=False,
            block_id=block.id,
            in_label=position < label,
        )
        for position, (text, page) in enumerate(
            zip(texts, _pages_through(texts, source, pages[0]), strict=True)
        )
    )


def _label_length(block: Block) -> int:
    """The number of words of a heading's label, 0 without one."""
    return len(block.label.split()) if block.label is not None else 0


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
    every_block = blocks.blocks + tuple(
        block for note in blocks.notes for block in note.blocks
    )
    first_page = {
        block.id: block.origin[0].page_index for block in every_block if block.origin
    }
    labels = {block.id: _label_length(block) for block in every_block}
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
    links = _endnote_link_words(blocks, by_block)
    pages: dict[int, int] = {}
    in_label: set[int] = set()
    dropped: set[int] = set()
    for block_id, positions in grouped.items():
        if block_id not in first_page:
            message = f"block {block_id} of blocks.json has no origin, so no page"
            raise GalleyFilesError(message)
        if block_id in links:
            kept = _without_link_words(markdown, positions, links[block_id])
            dropped.update(frozenset(positions) - frozenset(kept))
            positions = kept
        texts = tuple(markdown.words[position].text for position in positions)
        found = _pages_through(
            texts, tuple(by_block.get(block_id, ())), first_page[block_id]
        )
        pages.update(zip(positions, found, strict=True))
        in_label.update(positions[: labels[block_id]])
    return tuple(
        GalleyToken(
            text=word.text,
            page_index=pages[position],
            stream=known[block_id].stream,
            edge_of_page=False,
            block_id=block_id,
            in_label=position in in_label,
        )
        for position, word in enumerate(markdown.words)
        if (block_id := word.block_id) is not None and position not in dropped
    )


def _endnote_link_words(
    blocks: BlocksFile, by_block: dict[str, list[tuple[str, int]]]
) -> frozendict[str, tuple[tuple[str, bool], ...]]:
    """For each block with a reference to an endnote, its words as
    markdown writes them: its tokens at blocks, `by_block`, with the words
    of those references put back in their places, each with whether it is
    a put-back word."""
    endnotes = frozenset(
        note.id for note in blocks.notes if note.kind is NoteKind.ENDNOTE
    )
    found: dict[str, tuple[tuple[str, bool], ...]] = {}
    for block, marker, _ in _blocks_with_markers(blocks):
        if any(span.note_ref in endnotes for span in block.spans):
            tokens = [text for text, _ in by_block.get(block.id, ())]
            found[block.id] = _interleave(tokens, block, marker, endnotes)
    return frozendict(found)


def _interleave(
    tokens: list[str], block: Block, marker: str, endnotes: frozenset[str]
) -> tuple[tuple[str, bool], ...]:
    """The block's `tokens` at blocks with the words of its references to
    endnotes put back where they stand: before the token each precedes."""
    inserted: dict[int, list[str]] = {}
    before = " ".join(_prefix(block, marker)) + " "
    for span in block.spans:
        if span.note_ref is None:
            before += span.text
            continue
        if span.note_ref in endnotes:
            inserted.setdefault(len(before.split()), []).extend(span.text.split())
        before += " "
    words: list[tuple[str, bool]] = []
    for position in range(len(tokens) + 1):
        words.extend((text, True) for text in inserted.get(position, ()))
        if position < len(tokens):
            words.append((tokens[position], False))
    return tuple(words)


def _without_link_words(
    markdown: MarkdownWords,
    positions: list[int],
    expected: tuple[tuple[str, bool], ...],
) -> list[int]:
    """`positions`, the words of one block of `book.md`, without those that
    fall on a put-back word of `expected` when the two are aligned."""
    texts = tuple(markdown.words[position].text for position in positions)
    matcher = SequenceMatcher(
        None, texts, tuple(text for text, _ in expected), autojunk=False
    )
    dropped: set[int] = set()
    for tag, start, end, expected_start, expected_end in matcher.get_opcodes():
        match tag:
            case "equal" | "replace":
                for offset in range(min(end - start, expected_end - expected_start)):
                    if expected[expected_start + offset][1]:
                        dropped.add(start + offset)
            case "insert" | "delete":
                pass  # words on one side only fall on no put-back word
            case _:
                message = f"difflib gave an unknown operation {tag!r}"
                raise AssertionError(message)
    return [
        position for offset, position in enumerate(positions) if offset not in dropped
    ]
