"""The markdown stage: blocks.json to book.md, the Pandoc Markdown the epub
stage reads and the owner proofreads.

book.md is a metadata header and one fenced div per block, `::: {#b-p0012-003}`,
whose text has every ASCII punctuation character escaped (walking-skeleton
spec, section 8). A paragraph's div has no class; a margin note's has the
class `margin-note` and stands where the block is in blocks.json; a note
with `referenced` false is a div with its id and the class `note` around
its blocks' divs, its marker first, after the last block, in the order
of blocks.json, whose first origin is on the note's first page or an
earlier one, or first of all (structure spec, sections 6 and 10, option
b). Headings, quotes, verse, chapter summaries, figures, index entries,
note references and referenced notes are refused, and so are edits,
since none can exist before `galley2epub edits-from` is built.
"""

import bisect
import itertools
import json
import logging
import re
import string
from collections import Counter
from typing import assert_never

from galley.book_folder import BookFolder, Stage, delete_stage_outputs
from galley.config import BookConfig
from galley.errors import EditError, FidelityBoundary, InputFileError
from galley.fidelity import check_stage, read_markdown
from galley.model import (
    Block,
    BlockKind,
    BlocksFile,
    Note,
    block_text,
    read_blocks,
    read_checked_input,
    read_edits,
)
from galley.parallel import DEFAULT_WORKERS

__all__ = ["escape_markdown", "render_markdown", "run"]

_logger = logging.getLogger(__name__)

# Spec section 8: Pandoc's Markdown reads any escaped ASCII punctuation as
# itself, so none of it can start a list, emphasis or a fence.
_ESCAPED = frozendict(
    {ord(character): "\\" + character for character in string.punctuation}
)
# Spec section 8: white space made a space. Pandoc 3.14 drops a carriage
# return inside a word and reads a tab or four spaces at the start of a line
# as a code block; XML 1.0 does not allow the vertical tab, the form feed
# and U+001C to U+001F. str.split(), which the fidelity check splits words
# with, splits at all of them, so no word changes.
_PLAIN_WHITE_SPACE = frozendict(
    {ord(character): " " for character in "\t\n\r\x0b\x0c\x1c\x1d\x1e\x1f"}
)


def escape_markdown(text: str) -> str:
    """The text of a block as one line of Pandoc Markdown that Pandoc reads
    back with the same words: a backslash before every ASCII punctuation
    character; each tab, line feed, carriage return, vertical tab, form feed
    and U+001C to U+001F made a space, then the spaces at the start and end
    dropped. Every other character is kept as it is."""
    plain = text.translate(_PLAIN_WHITE_SPACE).strip(" ")
    return plain.translate(_ESCAPED)


# Spec section 8: the characters XML 1.0 does not allow, which Pandoc
# copies into the EPUB's XHTML, leaving it not well-formed: C0 controls but
# tab, line feed and carriage return, U+FFFE, U+FFFF and lone surrogates.
# It is matched on the escaped text, where the white space among them is
# already a space.
# C1 controls and the other noncharacters were checked to pass epubcheck.
_NOT_IN_XML = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\ufffe\uffff\ud800-\udfff]")


def _character_problems(where: str, text: str) -> tuple[str, ...]:
    """The characters XML 1.0 does not allow in `text` as it is written,
    each named with `where` it is: "block b-p0003-002"."""
    return tuple(
        f"{where} holds U+{ord(character):04X}, which XML 1.0 does not allow"
        for character in dict.fromkeys(_NOT_IN_XML.findall(escape_markdown(text)))
    )


# The kinds of block written now: in the body, and inside a note.
_BODY_KINDS = frozenset({BlockKind.PARAGRAPH, BlockKind.MARGIN_NOTE})
_NOTE_KINDS = frozenset({BlockKind.PARAGRAPH})


def _block_problems(block: Block, kinds: frozenset[BlockKind]) -> tuple[str, ...]:
    """Why a block cannot be written; empty when it can."""
    kind = (
        (f"block {block.id} is a {block.kind.value}",)
        if block.kind not in kinds
        else ()
    )
    reference = (
        (f"block {block.id} holds a note reference",)
        if any(span.note_ref is not None for span in block.spans)
        else ()
    )
    return (
        kind + reference + _character_problems(f"block {block.id}", block_text(block))
    )


def _note_problems(note: Note) -> tuple[str, ...]:
    """Why a note cannot be written; empty when it can."""
    referenced = (f"note {note.id} is referenced",) if note.referenced else ()
    marker = _character_problems(f"the marker of note {note.id}", note.marker)
    blocks = tuple(
        problem
        for block in note.blocks
        for problem in _block_problems(block, _NOTE_KINDS)
    )
    return referenced + marker + blocks


def _check_well_formed(blocks: BlocksFile) -> None:
    """Raise InputFileError, naming blocks.json, when it is malformed: an
    id given more than once among the blocks, the notes and the notes'
    blocks (each becomes the id of a div in book.md and the EPUB), or a
    note without blocks or without origin, which cannot be placed."""
    id_counts = Counter(
        (
            *(block.id for block in blocks.blocks),
            *(note.id for note in blocks.notes),
            *(block.id for note in blocks.notes for block in note.blocks),
        )
    )
    repeated = tuple(
        f"id {given_id} is given {count} times"
        for given_id, count in id_counts.items()
        if count > 1
    )
    empty = tuple(
        f"note {note.id} has no blocks" for note in blocks.notes if not note.blocks
    )
    placeless = tuple(
        f"note {note.id} has no origin" for note in blocks.notes if not note.origin
    )
    problems = repeated + empty + placeless
    if problems:
        message = f"blocks.json is malformed: {'; '.join(problems)}"
        raise InputFileError(message)


def _check_writable(blocks: BlocksFile) -> None:
    """Raise InputFileError, naming blocks.json, at what markdown does not
    write yet, rather than write it wrongly: a block that is not a paragraph
    or a margin note, a note reference, a referenced note, a note block that
    is not a paragraph, or a character XML 1.0 does not allow."""
    problems = tuple(
        problem
        for block in blocks.blocks
        for problem in _block_problems(block, _BODY_KINDS)
    ) + tuple(problem for note in blocks.notes for problem in _note_problems(note))
    if problems:
        message = (
            f"blocks.json holds what markdown does not write yet: {'; '.join(problems)}"
        )
        raise InputFileError(message)


def _metadata_value(value: str) -> str:
    """A metadata value as a JSON string, which YAML reads as a
    double-quoted string, of the value escaped by escape_markdown, since
    Pandoc reads metadata values as Markdown."""
    return json.dumps(escape_markdown(value), ensure_ascii=False)


def _header(config: BookConfig) -> str:
    """The metadata header: title, authors and language."""
    authors = "".join(f"- {_metadata_value(author)}\n" for author in config.authors)
    return (
        "---\n"
        f"title: {_metadata_value(config.title)}\n"
        "author:\n"
        f"{authors}"
        f"lang: {config.language.value}\n"
        "---\n"
    )


def _div_attributes(block: Block) -> str:
    """The id of a block's div, and its class when it has one."""
    match block.kind:
        case BlockKind.MARGIN_NOTE:
            return f"#{block.id} .margin-note"
        case (
            BlockKind.PARAGRAPH
            | BlockKind.HEADING
            | BlockKind.QUOTE
            | BlockKind.VERSE
            | BlockKind.CHAPTER_SUMMARY
            | BlockKind.FIGURE
            | BlockKind.INDEX_ENTRY
        ):
            return f"#{block.id}"
        case _:
            assert_never(block.kind)


def _div(block: Block, marker: str = "") -> str:
    """A block's fenced div, with its text on one line, escaped by
    escape_markdown; a note's `marker`, when given, is joined before the
    text with one space and escaped with it. An empty marker adds
    nothing."""
    text = escape_markdown(f"{marker} {block_text(block)}")
    return f"::: {{{_div_attributes(block)}}}\n{text}\n:::\n"


def _note_div(note: Note) -> str:
    """A note's fenced div, with its id and the class `note`, around its
    blocks' divs, the marker at the start of the first."""
    first, *rest = note.blocks
    inner = "\n".join((_div(first, note.marker), *(_div(block) for block in rest)))
    return f":::: {{#{note.id} .note}}\n{inner}::::\n"


def _note_positions(
    blocks: tuple[Block, ...], notes: tuple[Note, ...]
) -> tuple[int, ...]:
    """For each note, how many blocks of `blocks` are written before it: all
    up to the last block, in the order of `blocks`, whose first origin is on
    the note's first page or an earlier one; none when there is no such
    block (structure spec, sections 6 and 10)."""
    # Each block's first page and its position from 1, in page order, and
    # for each the highest position of a block on that page or before.
    by_first_page = sorted(
        (block.origin[0].page_index, position)
        for position, block in enumerate(blocks, start=1)
        if block.origin
    )
    first_pages = tuple(page_index for page_index, _ in by_first_page)
    last_positions = tuple(
        itertools.accumulate((position for _, position in by_first_page), max)
    )

    def position_of(note: Note) -> int:
        on_or_before = bisect.bisect_right(first_pages, note.origin[0].page_index)
        return last_positions[on_or_before - 1] if on_or_before else 0

    return tuple(position_of(note) for note in notes)


def render_markdown(blocks: BlocksFile, config: BookConfig) -> str:
    """book.md: the metadata header from the config (title, authors,
    language), then one fenced div per block with the block's id, in the
    order of blocks.json, its text escaped by escape_markdown on one line,
    a blank line between each. A margin note's div also has the class
    `margin-note`. Each note, all with `referenced` false, is a div with its
    id and the class `note` around its blocks' divs, the marker first in the
    first one's text; it follows the last block, in the order of
    blocks.json, whose first origin is on the note's first page or an
    earlier one, or comes first of all when there is none. Notes written at
    the same place keep the order of blocks.json.

    The title and each author are escaped by escape_markdown too. Raises
    InputFileError, naming blocks.json, when it is malformed: an id given
    twice, or a note without blocks or origin. Raises InputFileError, naming
    blocks.json and the block or note, for what markdown does not write
    yet: a heading, quote, figure or index entry, a note reference, a
    referenced note, a note block that is not a paragraph, or a character
    XML 1.0 does not allow (named as U+FFFE).
    """
    _check_well_formed(blocks)
    _check_writable(blocks)
    positions = _note_positions(blocks.blocks, blocks.notes)
    note_divs: dict[int, list[str]] = {}
    for note, position in zip(blocks.notes, positions, strict=True):
        note_divs.setdefault(position, []).append(_note_div(note))

    def notes_at(position: int) -> tuple[str, ...]:
        return tuple(note_divs.get(position, ()))

    body = tuple(
        div
        for position, block in enumerate(blocks.blocks, start=1)
        for div in (_div(block), *notes_at(position))
    )
    return "\n".join((_header(config), *notes_at(0), *body))


def _check_no_edits(folder: BookFolder) -> None:
    """Raise EditError when any edits file holds an edit, or one is
    malformed (read_edits). A missing edits folder, or empty files, is no
    edits."""
    if not folder.edits_dir.exists():
        return
    if not folder.edits_dir.is_dir():
        message = f"{folder.edits_dir} is not a folder; it should hold the edits files"
        raise EditError(message)
    with_edits = tuple(
        path for path in sorted(folder.edits_dir.glob("*.jsonl")) if read_edits(path)
    )
    if with_edits:
        message = (
            f"{', '.join(str(path) for path in with_edits)} hold edits; markdown "
            "does not apply edits yet: that comes with the markdown spec, not "
            "written yet, and with `galley2epub edits-from`, not built yet"
        )
        raise EditError(message)


def run(
    folder: BookFolder, config: BookConfig, *, workers: int = DEFAULT_WORKERS
) -> None:
    """Write book.md from blocks.json, after checking that no word is lost
    or invented between the two as Pandoc reads book.md.

    Deletes book.md and book.epub, the file of the stage after it, first.
    Reads pages.json and blocks.json, and raises InputFileError when
    pages.json was not made from `config.pdf` or
    blocks.json was made from another PDF than pages.json; raises
    EditError when an edits file holds an edit; raises FidelityError when
    the words differ, and ExternalProgramError when Pandoc is missing or
    fails. markdown runs once, so `workers` is not used.
    """
    del workers  # every stage's run takes it; markdown is not per page
    delete_stage_outputs(folder, Stage.MARKDOWN)
    _, blocks = read_checked_input(
        folder.pages_json, config.pdf, folder.blocks_json, read_blocks
    )
    _check_no_edits(folder)
    book_markdown = render_markdown(blocks, config)
    check_stage(FidelityBoundary.MARKDOWN, blocks, read_markdown(book_markdown))
    folder.book_md.write_text(book_markdown, encoding="utf-8", newline="\n")
    _logger.info(
        "wrote %s: %d blocks, %d notes",
        folder.book_md,
        len(blocks.blocks),
        len(blocks.notes),
    )
