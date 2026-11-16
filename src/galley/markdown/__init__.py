"""The markdown stage: blocks.json to book.md, the Pandoc Markdown the epub
stage reads and the owner proofreads.

book.md is a metadata header, then the blocks in the order of blocks.json,
one after the other with a blank line between. Every ASCII punctuation
character of the book's text is escaped, so that Pandoc reads it back as
written (walking-skeleton spec, section 8).

How each kind is written
------------------------

A kind says what a text is; this stage and the epub stage's style sheet,
`galley/epub/style.css`, decide how it looks (owner, 15 November 2026).
Every block keeps its id, so that an edit or a link can name it, and
every kind but the paragraph has a class of its own, its name with "-"
for "_", which the style sheet styles:

- `heading`: a Pandoc heading of its level with its id,
  `## [CHAPTER III\\.]{.label} THE EARLY YEARS {#b-p0040-001}`. The
  label, when the heading has one, is a span of class `label` before the
  title, which the style sheet sets on a line of its own; in the table of
  contents it stays before the title. The heading is not a div, because
  Pandoc starts a chapter file at each level-1 heading and a div around
  it would leave its id in the file before.
- `paragraph`: a fenced div with its id and no class, `::: {#b-p0012-003}`,
  its text on one line.
- `quote`, `chapter_summary`, `index_entry`, `margin_note`: a fenced div
  with its id and the class `quote`, `chapter-summary`, `index-entry` or
  `margin-note`, its text on one line. A margin note stands where it is in
  blocks.json, before the paragraph it was printed beside; the style sheet
  sets it as a small bold line.
- `verse`: a fenced div of class `verse`, each line of the text a line of
  the Markdown ended by a hard line break (a backslash), and an empty line
  of the text, the end of a stanza, a new paragraph in the div. Lines
  empty or of spaces only are not written.
- `figure`: a fenced div of class `figure` with its caption as text. Its
  image is not written: the fidelity check reads no Pandoc image, so a
  figure block with an image is refused.
- A note with `referenced` false is a fenced div with its id and the class
  `note` around its blocks' divs, its marker first, after the last block,
  in the order of blocks.json, whose first origin is on the note's first
  page or an earlier one, or first of all (structure spec, sections 6 and
  10, option b).

Note references and referenced notes are refused, and so are edits, since
none can exist before `galley2epub edits-from` is built.
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


# The kinds of block written in the body and inside a note.
_BODY_KINDS = frozenset(BlockKind)
_NOTE_KINDS = frozenset({BlockKind.PARAGRAPH})
# The levels a Pandoc heading can have.
_HEADING_LEVELS = range(1, 7)


def _block_problems(block: Block, kinds: frozenset[BlockKind]) -> tuple[str, ...]:
    """Why a block cannot be written; empty when it can."""
    kind = (
        (f"block {block.id} is a {block.kind.value}",)
        if block.kind not in kinds
        else ()
    )
    image = (
        (
            (
                f"block {block.id} is a figure with the image {block.figure}, and the "
                "fidelity check reads no image"
            ),
        )
        if block.kind is BlockKind.FIGURE and block.figure is not None
        else ()
    )
    reference = (
        (f"block {block.id} holds a note reference",)
        if any(span.note_ref is not None for span in block.spans)
        else ()
    )
    label = (
        _character_problems(f"the label of block {block.id}", block.label)
        if block.label is not None
        else ()
    )
    return (
        kind
        + image
        + reference
        + _character_problems(f"block {block.id}", block_text(block))
        + label
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
    blocks (each becomes the id of a div in book.md and the EPUB), a note
    without blocks or without origin, which cannot be placed, or a heading
    without a level Pandoc has (1 to 6)."""
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
    levelless = tuple(
        f"heading {block.id} has the level {block.level}"
        for block in blocks.blocks
        if block.kind is BlockKind.HEADING and block.level not in _HEADING_LEVELS
    )
    problems = repeated + empty + placeless + levelless
    if problems:
        message = f"blocks.json is malformed: {'; '.join(problems)}"
        raise InputFileError(message)


def _check_writable(blocks: BlocksFile) -> None:
    """Raise InputFileError, naming blocks.json, at what markdown does not
    write, rather than write it wrongly: a figure with an image, a note
    reference, a referenced note, a note block that is not a paragraph, or
    a character XML 1.0 does not allow."""
    problems = tuple(
        problem
        for block in blocks.blocks
        for problem in _block_problems(block, _BODY_KINDS)
    ) + tuple(problem for note in blocks.notes for problem in _note_problems(note))
    if problems:
        message = (
            f"blocks.json holds what markdown does not write: {'; '.join(problems)}"
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


def _class_name(kind: BlockKind) -> str | None:
    """The class of a block's div, which the style sheet styles; None for
    a paragraph."""
    match kind:
        case BlockKind.PARAGRAPH:
            return None
        case (
            BlockKind.HEADING
            | BlockKind.QUOTE
            | BlockKind.VERSE
            | BlockKind.CHAPTER_SUMMARY
            | BlockKind.FIGURE
            | BlockKind.MARGIN_NOTE
            | BlockKind.INDEX_ENTRY
        ):
            return kind.value.replace("_", "-")
        case _:
            assert_never(kind)


# White space made a space, as escape_markdown does, but the line feed,
# which a verse block keeps.
_PLAIN_WHITE_SPACE_BUT_LINE_FEED = frozendict(
    {key: value for key, value in _PLAIN_WHITE_SPACE.items() if key != ord("\n")}
)
# Pandoc's hard line break: a backslash at the end of a line.
_HARD_LINE_BREAK = "\\\n"


def _verse_markdown(text: str) -> str:
    """A verse block's text with each line ended by a hard line break,
    escaped by escape_markdown line by line, and a blank line where the
    text has an empty line or one of spaces only, the end of a stanza."""
    lines = (
        escape_markdown(line)
        for line in text.translate(_PLAIN_WHITE_SPACE_BUT_LINE_FEED).split("\n")
    )
    stanzas = tuple(
        tuple(stanza)
        for is_line, stanza in itertools.groupby(lines, key=bool)
        if is_line
    )
    return "\n\n".join(_HARD_LINE_BREAK.join(stanza) for stanza in stanzas)


def _text_markdown(block: Block, marker: str) -> str:
    """A block's text in Markdown: on one line, escaped by escape_markdown,
    or, for verse, line by line; a note's `marker`, when given, first, with
    one space after it. An empty marker adds nothing."""
    match block.kind:
        case BlockKind.VERSE:
            text = _verse_markdown(block_text(block))
            return f"{escape_markdown(marker)} {text}" if marker else text
        case (
            BlockKind.HEADING
            | BlockKind.PARAGRAPH
            | BlockKind.QUOTE
            | BlockKind.CHAPTER_SUMMARY
            | BlockKind.FIGURE
            | BlockKind.MARGIN_NOTE
            | BlockKind.INDEX_ENTRY
        ):
            return escape_markdown(f"{marker} {block_text(block)}")
        case _:
            assert_never(block.kind)


def _heading(block: Block) -> str:
    """A heading of its level with its id, its label first as a span of
    class `label`."""
    label = (
        (f"[{escape_markdown(block.label)}]{{.label}}",)
        if block.label is not None
        else ()
    )
    if block.level is None:
        message = f"blocks.json is malformed: heading {block.id} has no level"
        raise InputFileError(message)
    title = _text_markdown(block, "")
    words = " ".join((*label, *((title,) if title else ())))
    return f"{'#' * block.level} {words} {{#{block.id}}}\n"


def _div(block: Block, marker: str = "") -> str:
    """A block's fenced div with its id and its class, or for a heading a
    Pandoc heading; `marker` as _text_markdown takes it."""
    if block.kind is BlockKind.HEADING:
        return _heading(block)
    class_name = _class_name(block.kind)
    attributes = f"#{block.id}" + (f" .{class_name}" if class_name is not None else "")
    return f"::: {{{attributes}}}\n{_text_markdown(block, marker)}\n:::\n"


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
    language), then each block in the order of blocks.json, a blank line
    between each, as the module's docstring says for each kind: a heading
    as a Pandoc heading of its level with its id and its label as a span of
    class `label`; every other block as a fenced div with its id and the
    class of its kind but a paragraph's, its text escaped by
    escape_markdown on one line, or, for verse, line by line with hard
    line breaks. Each note, all with `referenced` false, is a div with its
    id and the class `note` around its blocks' divs, the marker first in
    the first one's text; it follows the last block, in the order of
    blocks.json, whose first origin is on the note's first page or an
    earlier one, or comes first of all when there is none. Notes written
    at the same place keep the order of blocks.json.

    The title and each author are escaped by escape_markdown too. Raises
    InputFileError, naming blocks.json, when it is malformed: an id given
    twice, a note without blocks or origin, or a heading without a level
    from 1 to 6. Raises InputFileError, naming blocks.json and the block or
    note, for what markdown does not write: a figure with an image, a note
    reference, a referenced note, a note block that is not a paragraph, or
    a character XML 1.0 does not allow (named as U+FFFE).
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
