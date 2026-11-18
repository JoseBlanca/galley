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
  `margin-note`, its text on one line; an index entry's div also has the
  class of its depth, `depth-1` for an entry and `depth-2` for a
  sub-entry, which the style sheet sets in. A margin note stands where it is in
  blocks.json, before the paragraph it was printed beside; the style sheet
  sets it as a small bold line.
- `verse`: a fenced div of class `verse`, each line of the text a line of
  the Markdown ended by a hard line break (a backslash), and an empty line
  of the text, the end of a stanza, a new paragraph in the div. Lines
  empty or of spaces only are not written.
- `epigraph`: a fenced div of class `epigraph` holding its quotation,
  written as a verse block's text is (a prose quotation has no line feed,
  so it is one line), then, when it has a `source`, a fenced div of class
  `epigraph-source` holding an em dash, a no-break space and the source
  (structure spec, section 25). The dash is written as text, not drawn by
  the style sheet, because generated content was not tried on a Kindle;
  the no-break space keeps it on the source's line. The style sheet sets
  the epigraph in and its source to the right.
- `figure`: a fenced div of class `figure` holding its image alone in a
  paragraph with its caption as the image's text,
  `![PLATE I\\. The battle\\.](images/plate-0016.png)`, which Pandoc
  makes a figure with that caption, or `![](images/plate-0016.png)` when
  the caption is empty. The path is the block's `figure`, relative to the
  book folder; one that is not, or holds a character other than ASCII
  letters, digits, "_", ".", "-" and "/", is refused, and so is a note
  reference in the caption, which Pandoc would copy into the image's alt
  text. A figure without an image is its caption as text.
- `list_item`: an item of a Pandoc list (structure spec, section 31). A
  list is a run of list items whose markers follow each other (structure
  spec, section 29, rule 3): a dash or bullet list is a bullet list, whose
  items are written after "-", and an ordered list's items after their
  label as printed, "1.", "(iv)", which Pandoc reads as an ordered list of
  that style and start. The printed marker is not written otherwise: the
  reader shows its own bullet or Pandoc's numbers. Each item holds the
  block's fenced div, with its id and the class `list-item`, indented by
  the width of its marker and a space, at least 4 characters, so that
  "A." is followed by two spaces, without which Pandoc reads a
  paragraph. A block or a note written between two items ends the list,
  and two lists with nothing between them are kept apart by an empty
  fenced div of class `list-break`, since Pandoc reads two lists apart
  only by a blank line as one. The footnotes of a list's items are
  defined after the whole list. Pandoc 3.14 reads a list that starts at
  "v." or "x." as letters, whose numbers it shows as printed, and a
  roman item after one as the start of another list: the reader shows
  the same markers.
- `contents_entry`: a run of contents entries is a fenced div of class
  `contents` holding a bullet list, each item the block's fenced div, with
  its id and the class `contents-entry`, holding its label as a span of
  class `label`, as a heading's, then its title, a link to `#<heading_ref>`
  when it has one, which Pandoc points into its heading's chapter file.
  An entry deeper than the one before is in a bullet list inside the item
  before it, its depth its level, or one more than the entry before's
  when its level is deeper still. Its page number is not written; the
  style sheet sets the lists without bullets.

Notes (structure spec, section 19; architecture sections 9 and 13):

- A footnote with `referenced` true is a Pandoc footnote at its
  reference, `Greece\\,[^n-p0012-001]`, which the Kindle shows as a
  pop-up. Its definition follows the block, or the note or list of
  endnotes, that refers to it, and holds its blocks' divs, indented, its
  margin notes among them; its marker is not written, since Pandoc
  numbers its notes. Pandoc cannot put a footnote in a footnote, so a
  reference to one inside one is refused.
- A footnote with `referenced` false is a fenced div with its id and the
  class `note` around its blocks' divs.
- An endnote, referenced or not, is a fenced div with its id and the
  class `endnote` around its blocks' divs, and the endnotes that follow
  each other are one list, a div of class `endnotes` around theirs. A
  reference to one is a link to it with the reference as printed, marked
  as a note reference, `Law[1](#n-p0190-001){epub:type="noteref"}`,
  which Pandoc points into the chapter file of the endnote and a Kindle
  can show as a pop-up.
- A note group's heading, `Note.group`, is a fenced div of class
  `note-group` just before the div of its endnote, in the list of
  endnotes. It is not a Pandoc heading, so it stays out of the EPUB's
  table of contents (structure spec, sections 25 and 27). Only an endnote
  may have one: the fidelity check reads a group's div only before an
  endnote's.
- A note written where it was printed, an unreferenced footnote or an
  endnote, follows the last block, in the order of blocks.json, whose
  first origin is on the note's first page or an earlier one, or comes
  first of all (structure spec, sections 6 and 10, option b). Its marker
  is first in the text of its first block that is not a margin note, so
  that a margin note printed beside it stays a line of its own before it.

A no-break space, U+00A0, which structure puts before a spaced sign in a
French book (structure spec, section 23), is written as the character,
which Pandoc keeps inside its word.

Edits are refused, since none can exist before `galley2epub edits-from`
is built.
"""

import itertools
import json
import logging
import re
import string
import textwrap
from collections import Counter
from typing import assert_never

from galley.book_folder import BookFolder, Stage, delete_stage_outputs
from galley.config import BookConfig
from galley.errors import EditError, FidelityBoundary, InputFileError
from galley.fidelity import check_stage, read_markdown
from galley.list_markers import ListMarker, follows, is_bulleted, marker_readings
from galley.model import (
    Block,
    BlockKind,
    BlocksFile,
    Note,
    NoteKind,
    Span,
    block_text,
    has_entry_depth,
    note_places,
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


# The kinds of block written inside a note (architecture section 8): its
# text, and the margin notes printed beside it.
_NOTE_KINDS = frozenset(
    {BlockKind.PARAGRAPH, BlockKind.QUOTE, BlockKind.VERSE, BlockKind.MARGIN_NOTE}
)
# The levels a Pandoc heading can have.
_HEADING_LEVELS = range(1, 7)


def _references(block: Block) -> tuple[str, ...]:
    """The ids of the notes a block's reference spans name, in order."""
    return tuple(span.note_ref for span in block.spans if span.note_ref is not None)


def _is_footnote_at_its_reference(note: Note) -> bool:
    """Whether a note is written as a Pandoc footnote at its reference: a
    footnote with `referenced` true. Every other note is written where it
    was printed."""
    return note.kind is NoteKind.FOOTNOTE and note.referenced


# An image path as extract writes it, "images/plate-0016.png", relative to
# the book folder: one Pandoc reads as a link target as it is, with no
# escaping, which a space or a bracket would need.
_IMAGE_PATH = re.compile(r"[A-Za-z0-9_.-]+(/[A-Za-z0-9_.-]+)*")


def _image_problems(block: Block) -> tuple[str, ...]:
    """Why a figure's image cannot be written: a path that is not relative
    or holds a character other than ASCII letters, digits, "_", ".", "-"
    and "/"; or a note reference in its caption, which Pandoc would copy
    into the image's alt text."""
    if block.kind is not BlockKind.FIGURE or block.figure is None:
        return ()
    path = (
        ()
        if _IMAGE_PATH.fullmatch(block.figure)
        else (
            (
                f"figure {block.id} has the image path {block.figure!r}, which is "
                "not relative or holds a character other than ASCII letters, "
                "digits, '_', '.', '-' and '/'"
            ),
        )
    )
    reference = (
        (f"figure {block.id} has a note reference in its caption",)
        if _references(block)
        else ()
    )
    return path + reference


def _first_marker(label: str) -> ListMarker:
    """The marker of a list's first item: a roman numeral when the label
    reads as one (structure spec section 29, "Terms")."""
    return marker_readings(label)[0]


def _next_marker(before: ListMarker, label: str) -> ListMarker | None:
    """The reading of `label` that follows the marker `before` (structure
    spec section 29, rule 3); None when none does."""
    return next(
        (reading for reading in marker_readings(label) if follows(reading, before)),
        None,
    )


def _list_problems(block: Block) -> tuple[str, ...]:
    """Why a list item or a contents entry cannot be written: a list item
    whose label is not a list marker, or a contents entry linked to its
    heading with a note reference in its title, which would put a link in
    the link."""
    if (
        block.kind is BlockKind.LIST_ITEM
        and block.label is not None
        and not marker_readings(block.label)
    ):
        return (
            (
                f"list item {block.id} has the label {block.label!r}, which is "
                "not a list marker (structure spec section 29)"
            ),
        )
    if (
        block.kind is BlockKind.CONTENTS_ENTRY
        and block.heading_ref is not None
        and _references(block)
    ):
        return (
            (
                f"contents entry {block.id} links to its heading and has a note "
                "reference in its title, which would be a link inside the link"
            ),
        )
    return ()


def _block_problems(block: Block) -> tuple[str, ...]:
    """Why a block cannot be written: a list item or contents entry
    _list_problems refuses, a figure's image _image_problems refuses, or a
    character XML 1.0 does not allow, in its text, label or source; empty
    when it can."""
    kind = _list_problems(block)
    image = _image_problems(block)
    label = (
        _character_problems(f"the label of block {block.id}", block.label)
        if block.label is not None
        else ()
    )
    source = (
        _character_problems(f"the source of block {block.id}", block.source)
        if block.source is not None
        else ()
    )
    return (
        kind
        + image
        + _character_problems(f"block {block.id}", block_text(block))
        + label
        + source
    )


def _note_block_problems(
    note: Note, block: Block, footnote_ids: frozenset[str]
) -> tuple[str, ...]:
    """Why a block of `note` cannot be written: a kind a note does not
    hold, a reference to a footnote inside a footnote, which Pandoc cannot
    nest, or what _block_problems finds."""
    kind = (
        (f"block {block.id} of note {note.id} is a {block.kind.value}",)
        if block.kind not in _NOTE_KINDS
        else ()
    )
    nested = (
        tuple(
            f"block {block.id} of footnote {note.id} refers to footnote {note_id}, "
            "and Pandoc cannot put a footnote in a footnote"
            for note_id in _references(block)
            if note_id in footnote_ids
        )
        if _is_footnote_at_its_reference(note)
        else ()
    )
    return kind + nested + _block_problems(block)


def _group_problems(note: Note) -> tuple[str, ...]:
    """Why a note's group heading cannot be written: a group on a note that
    is not an endnote, whose div would not stand in a list of endnotes,
    where the fidelity check reads it, or a character XML 1.0 does not
    allow."""
    if note.group is None:
        return ()
    misplaced = (
        f"note {note.id} is a {note.kind.value} and has the group heading "
        f"{note.group!r}; only an endnote has one"
    )
    kind = (misplaced,) if note.kind is not NoteKind.ENDNOTE else ()
    return kind + _character_problems(
        f"the group heading of note {note.id}", note.group
    )


def _note_problems(note: Note, footnote_ids: frozenset[str]) -> tuple[str, ...]:
    """Why a note cannot be written; empty when it can."""
    marker = _character_problems(f"the marker of note {note.id}", note.marker)
    blocks = tuple(
        problem
        for block in note.blocks
        for problem in _note_block_problems(note, block, footnote_ids)
    )
    return marker + _group_problems(note) + blocks


def _reference_problems(blocks: BlocksFile) -> tuple[str, ...]:
    """The references that do not agree with the notes: one that names no
    note, a note with `referenced` true and no reference or false and one,
    and a footnote referenced more than once, which Pandoc would print at
    each reference."""
    notes = {note.id: note for note in blocks.notes}
    referring = tuple(
        (block.id, note_id)
        for block in _every_block(blocks)
        for note_id in _references(block)
    )
    counts = Counter(note_id for _, note_id in referring)
    nowhere = tuple(
        f"block {block_id} refers to {note_id}, which is no note"
        for block_id, note_id in referring
        if note_id not in notes
    )
    unreferenced = tuple(
        f"note {note.id} is referenced and no block refers to it"
        for note in blocks.notes
        if note.referenced and not counts[note.id]
    )
    referenced = tuple(
        f"note {note.id} is not referenced and a block refers to it"
        for note in blocks.notes
        if not note.referenced and counts[note.id]
    )
    repeated = tuple(
        f"footnote {note.id} is referenced {counts[note.id]} times"
        for note in blocks.notes
        if note.kind is NoteKind.FOOTNOTE and counts[note.id] > 1
    )
    return nowhere + unreferenced + referenced + repeated


def _every_block(blocks: BlocksFile) -> tuple[Block, ...]:
    """The blocks of the body, then those of every note."""
    return blocks.blocks + tuple(
        block for note in blocks.notes for block in note.blocks
    )


def _check_well_formed(blocks: BlocksFile) -> None:
    """Raise InputFileError, naming blocks.json, when it is malformed: an
    id given more than once among the blocks, the notes and the notes'
    blocks (each becomes the id of a div in book.md and the EPUB), a note
    without blocks or without origin, which cannot be placed, a heading
    without a level Pandoc has (1 to 6), an index entry or a contents
    entry without a depth from 1, a list item without a label, a contents
    entry whose heading reference names no heading block, or references
    that do not agree with the notes (_reference_problems)."""
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
    depthless = tuple(
        f"index entry {block.id} has the depth {block.level}"
        for block in _every_block(blocks)
        if block.kind is BlockKind.INDEX_ENTRY and not has_entry_depth(block)
    )
    contents_depthless = tuple(
        f"contents entry {block.id} has the depth {block.level}"
        for block in _every_block(blocks)
        if block.kind is BlockKind.CONTENTS_ENTRY and not has_entry_depth(block)
    )
    labelless = tuple(
        f"list item {block.id} has no label, its marker"
        for block in _every_block(blocks)
        if block.kind is BlockKind.LIST_ITEM and block.label is None
    )
    headings = frozenset(
        block.id for block in _every_block(blocks) if block.kind is BlockKind.HEADING
    )
    unlinked = tuple(
        f"contents entry {block.id} refers to {block.heading_ref}, which is no heading"
        for block in _every_block(blocks)
        if block.heading_ref is not None and block.heading_ref not in headings
    )
    problems = (
        repeated
        + empty
        + placeless
        + levelless
        + depthless
        + contents_depthless
        + labelless
        + unlinked
        + _reference_problems(blocks)
    )
    if problems:
        message = f"blocks.json is malformed: {'; '.join(problems)}"
        raise InputFileError(message)


def _check_writable(blocks: BlocksFile) -> None:
    """Raise InputFileError, naming blocks.json, at what markdown does not
    write, rather than write it wrongly: a list item whose label is not a
    list marker, a contents entry linked to its heading with a note
    reference in its title, a figure's image _image_problems refuses, a
    note
    block that is not a paragraph, quote, verse or margin note, a reference
    to a footnote inside a referenced footnote, a group heading on a note
    that is not an endnote, or a character XML 1.0 does not allow."""
    footnote_ids = frozenset(
        note.id for note in blocks.notes if _is_footnote_at_its_reference(note)
    )
    problems = tuple(
        problem for block in blocks.blocks for problem in _block_problems(block)
    ) + tuple(
        problem
        for note in blocks.notes
        for problem in _note_problems(note, footnote_ids)
    )
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
            | BlockKind.EPIGRAPH
            | BlockKind.FIGURE
            | BlockKind.MARGIN_NOTE
            | BlockKind.INDEX_ENTRY
            | BlockKind.LIST_ITEM
            | BlockKind.CONTENTS_ENTRY
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


def _span_markdown(
    span: Span, notes: frozendict[str, Note], white_space: frozendict[int, str]
) -> str:
    """A span in Markdown: its text with the white space of `white_space`
    made a space and every ASCII punctuation escaped; a reference to a
    footnote written at its reference, Pandoc's `[^n-p0012-001]`; a
    reference to any other note a link to it with its text, marked as a
    note reference, `[1](#n-p0190-001){epub:type="noteref"}`."""
    if span.note_ref is None:
        return span.text.translate(white_space).translate(_ESCAPED)
    note = notes[span.note_ref]
    if _is_footnote_at_its_reference(note):
        return f"[^{note.id}]"
    return f'[{escape_markdown(span.text)}](#{note.id}){{epub:type="noteref"}}'


def _verse_markdown(block: Block, notes: frozendict[str, Note]) -> str:
    """A verse block's text with each line ended by a hard line break, and
    a blank line where the text has an empty line or one of spaces only,
    the end of a stanza; the spaces at the start and end of each line
    dropped."""
    text = "".join(
        _span_markdown(span, notes, _PLAIN_WHITE_SPACE_BUT_LINE_FEED)
        for span in block.spans
    )
    lines = (line.strip(" ") for line in text.split("\n"))
    stanzas = tuple(
        tuple(stanza)
        for is_line, stanza in itertools.groupby(lines, key=bool)
        if is_line
    )
    return "\n\n".join(_HARD_LINE_BREAK.join(stanza) for stanza in stanzas)


def _text_markdown(block: Block, notes: frozendict[str, Note], marker: str) -> str:
    """A block's text in Markdown, its spans as _span_markdown writes them:
    on one line, without the spaces at its start and end, or, for verse,
    line by line, as are an epigraph's; a note's `marker`, when given, first, escaped, with one
    space after it. An empty marker adds nothing."""
    match block.kind:
        # Structure spec section 25: an epigraph's quotation keeps its line
        # feeds, as verse; a prose one has none.
        case BlockKind.VERSE | BlockKind.EPIGRAPH:
            text = _verse_markdown(block, notes)
        case (
            BlockKind.HEADING
            | BlockKind.PARAGRAPH
            | BlockKind.QUOTE
            | BlockKind.CHAPTER_SUMMARY
            | BlockKind.FIGURE
            | BlockKind.MARGIN_NOTE
            | BlockKind.INDEX_ENTRY
            | BlockKind.LIST_ITEM
            | BlockKind.CONTENTS_ENTRY
        ):
            text = "".join(
                _span_markdown(span, notes, _PLAIN_WHITE_SPACE) for span in block.spans
            ).strip(" ")
        case _:
            assert_never(block.kind)
    return " ".join(part for part in (escape_markdown(marker), text) if part)


def _labelled(block: Block, text: str) -> str:
    """`text` after the block's label as a span of class `label`, when it
    has one, `[CHAPTER III\\.]{.label} THE EARLY YEARS`."""
    label = (
        f"[{escape_markdown(block.label)}]{{.label}}" if block.label is not None else ""
    )
    return " ".join(part for part in (label, text) if part)


def _heading(block: Block, notes: frozendict[str, Note]) -> str:
    """A heading of its level with its id, its label first as a span of
    class `label`."""
    assert block.level is not None, "_check_well_formed refuses a heading without one"
    words = _labelled(block, _text_markdown(block, notes, ""))
    return f"{'#' * block.level} {words} {{#{block.id}}}\n"


def _contents_entry_text(block: Block, notes: frozendict[str, Note]) -> str:
    """A contents entry's label as a span of class `label`, then its title,
    a link to its heading when it has one; not its page number."""
    title = _text_markdown(block, notes, "")
    linked = (
        f"[{title}](#{block.heading_ref})" if block.heading_ref is not None else title
    )
    return _labelled(block, linked)


# Structure spec section 25: written before an epigraph's source, an em
# dash and a no-break space, which keeps the dash on the source's line. The
# fidelity check takes this word out, since blocks.json does not hold it.
_SOURCE_DASH = "\u2014\u00a0"


def _epigraph(block: Block, notes: frozendict[str, Note]) -> str:
    """An epigraph's fenced div with its id and the class `epigraph`,
    holding its quotation and, when it has a source, the div of class
    `epigraph-source` with the dash and the source."""
    source = (
        f"\n::: {{.epigraph-source}}\n{_SOURCE_DASH}{escape_markdown(block.source)}\n:::\n"
        if block.source is not None
        else ""
    )
    return (
        f":::: {{#{block.id} .epigraph}}\n"
        f"{_text_markdown(block, notes, '')}\n{source}::::\n"
    )


def _div(block: Block, notes: frozendict[str, Note], marker: str = "") -> str:
    """A block's fenced div with its id and its class, or for a heading a
    Pandoc heading, or for an epigraph the div _epigraph writes; `marker`
    as _text_markdown takes it."""
    if block.kind is BlockKind.HEADING:
        return _heading(block, notes)
    if block.kind is BlockKind.EPIGRAPH:
        return _epigraph(block, notes)
    class_name = _class_name(block.kind)
    attributes = f"#{block.id}" + (f" .{class_name}" if class_name is not None else "")
    if block.kind is BlockKind.INDEX_ENTRY:
        # Structure spec section 19: the entry's depth, which the style
        # sheet indents; _check_well_formed refuses one without a depth.
        attributes += f" .depth-{block.level}"
    text = _text_markdown(block, notes, marker)
    if block.kind is BlockKind.FIGURE and block.figure is not None:
        text = f"![{text}]({block.figure})"
    if block.kind is BlockKind.CONTENTS_ENTRY:
        text = _contents_entry_text(block, notes)
    return f"::: {{{attributes}}}\n{text}\n:::\n"


# Structure spec section 31: the marker of a bullet list's items, and the
# least indent of an item's div, under which Pandoc reads the next item as
# code or a capital letter's item as a paragraph.
_BULLET_MARKER = "-"
_LEAST_ITEM_INDENT = 4
# The empty div between two lists with nothing between them, which Pandoc
# would otherwise read as one.
_LIST_BREAK = "::: {.list-break}\n:::\n"


def _list_item(marker: str, div: str) -> str:
    """A list item of `marker` holding `div`, indented by the marker's
    width and a space, at least _LEAST_ITEM_INDENT characters."""
    width = max(_LEAST_ITEM_INDENT, len(marker) + 1)
    first, rest = div.split("\n", 1)
    return marker.ljust(width) + first + "\n" + textwrap.indent(rest, " " * width)


def _list(items: tuple[Block, ...], notes: frozendict[str, Note]) -> str:
    """A list of list items: a bullet list when the first marker is a dash
    or a bullet, otherwise an ordered list with each label as its marker;
    a blank line between the items."""
    assert items[0].label is not None, "_check_well_formed refuses an item without one"
    bulleted = is_bulleted(_first_marker(items[0].label))
    return "\n".join(
        _list_item(
            _BULLET_MARKER if bulleted or item.label is None else item.label,
            _div(item, notes),
        )
        for item in items
    )


def _contents_depths(entries: tuple[Block, ...]) -> tuple[int, ...]:
    """The depth of each entry in the Markdown: its level, or one more than
    the entry before's when its level is deeper still."""
    depths: list[int] = []
    for entry in entries:
        assert entry.level is not None, "_check_well_formed refuses one without"
        depths.append(min(entry.level, (depths[-1] if depths else 0) + 1))
    return tuple(depths)


def _contents(entries: tuple[Block, ...], notes: frozendict[str, Note]) -> str:
    """A contents: a fenced div of class `contents` holding a bullet list of
    the entries' divs, an entry deeper than the one before in a bullet
    list inside the item before it."""
    items = "\n".join(
        textwrap.indent(
            _list_item(_BULLET_MARKER, _div(entry, notes)),
            " " * (_LEAST_ITEM_INDENT * (depth - 1)),
        )
        for entry, depth in zip(entries, _contents_depths(entries), strict=True)
    )
    return f"::: contents\n{items}:::\n"


def _runs(
    blocks: tuple[Block, ...], ended_after: frozenset[int]
) -> tuple[tuple[Block, ...], ...]:
    """The blocks in runs, each written as one: a list, the list items each
    of whose markers follows the one before (structure spec section 29,
    rule 3); a contents, the contents entries that follow each other; and
    every other block alone. A run ends after the block of each index of
    `ended_after`, after which a note is written."""
    runs: list[list[Block]] = []
    marker: ListMarker | None = None
    for index, block in enumerate(blocks):
        before = blocks[index - 1] if runs and index - 1 not in ended_after else None
        following = (
            _next_marker(marker, block.label)
            if before is not None
            and before.kind is BlockKind.LIST_ITEM
            and block.kind is BlockKind.LIST_ITEM
            and marker is not None
            and block.label is not None
            else None
        )
        joins = following is not None or (
            before is not None
            and before.kind is BlockKind.CONTENTS_ENTRY
            and block.kind is BlockKind.CONTENTS_ENTRY
        )
        if block.kind is BlockKind.LIST_ITEM and block.label is not None:
            marker = following if following is not None else _first_marker(block.label)
        if joins:
            runs[-1].append(block)
        else:
            runs.append([block])
    return tuple(tuple(run) for run in runs)


def _run_markdown(run: tuple[Block, ...], notes: frozendict[str, Note]) -> str:
    """A run of _runs: a list, a contents, or the one block's div."""
    match run[0].kind:
        case BlockKind.LIST_ITEM:
            return _list(run, notes)
        case BlockKind.CONTENTS_ENTRY:
            return _contents(run, notes)
        case _:
            return _div(run[0], notes)


def _note_blocks(note: Note, notes: frozendict[str, Note], marker: str) -> str:
    """The divs of a note's blocks, a blank line between each, `marker` at
    the start of the first that is not a margin note, or of the first when
    all are."""
    marked = next(
        (
            position
            for position, block in enumerate(note.blocks)
            if block.kind is not BlockKind.MARGIN_NOTE
        ),
        0,
    )
    return "\n".join(
        _div(block, notes, marker if position == marked else "")
        for position, block in enumerate(note.blocks)
    )


def _note_div(note: Note, notes: frozendict[str, Note]) -> str:
    """A note written where it was printed: a fenced div with its id and
    the class `note` (a footnote) or `endnote`, around its blocks' divs,
    its marker first; before it, when it has a group heading, a fenced div
    of class `note-group` holding the heading."""
    class_name = "endnote" if note.kind is NoteKind.ENDNOTE else "note"
    group = (
        f"::: {{.note-group}}\n{escape_markdown(note.group)}\n:::\n\n"
        if note.group is not None
        else ""
    )
    return (
        f"{group}:::: {{#{note.id} .{class_name}}}\n"
        f"{_note_blocks(note, notes, note.marker)}::::\n"
    )


# The indent of a footnote's blocks under its definition.
_FOOTNOTE_INDENT = "    "


def _footnote_definition(note: Note, notes: frozendict[str, Note]) -> str:
    """A referenced footnote as a Pandoc footnote definition, its blocks'
    divs indented under it, without its marker, which Pandoc replaces with
    its own number."""
    blocks = textwrap.indent(_note_blocks(note, notes, ""), _FOOTNOTE_INDENT)
    return f"[^{note.id}]:\n{blocks}"


def _with_footnotes(
    written: str, written_blocks: tuple[Block, ...], notes: frozendict[str, Note]
) -> tuple[str, ...]:
    """`written`, then the definitions of the footnotes its blocks refer
    to, in the order of their references."""
    return (
        written,
        *(
            _footnote_definition(notes[note_id], notes)
            for block in written_blocks
            for note_id in _references(block)
            if _is_footnote_at_its_reference(notes[note_id])
        ),
    )


def _printed_notes(group: tuple[Note, ...], notes: frozendict[str, Note]) -> str:
    """Notes written where they were printed, each a div; a run of
    endnotes is one list, a div of class `endnotes` around theirs."""
    if group[0].kind is NoteKind.ENDNOTE:
        inner = "\n".join(_note_div(note, notes) for note in group)
        return f"::::: {{.endnotes}}\n{inner}:::::\n"
    return "\n".join(_note_div(note, notes) for note in group)


def render_markdown(blocks: BlocksFile, config: BookConfig) -> str:
    """book.md: the metadata header from the config (title, authors,
    language), then each block in the order of blocks.json, a blank line
    between each, as the module's docstring says for each kind: a heading
    as a Pandoc heading of its level with its id and its label as a span of
    class `label`; every other block as a fenced div with its id and the
    class of its kind but a paragraph's, its text escaped by
    escape_markdown on one line, or, for verse, line by line with hard
    line breaks; an epigraph holds its quotation, as verse is written,
    and a div of class `epigraph-source` with an em dash, a no-break space
    and its source; a figure with an image holds the image alone, its
    caption as the image's text. A no-break space is kept as the character.

    List items whose markers follow each other are a Pandoc list, a
    bullet list for a dash or a bullet and otherwise an ordered list with
    each label as its marker, each item holding the block's div; a block
    or a note between two items ends the list, and an empty div of class
    `list-break` keeps apart two lists with nothing between them. Contents
    entries that follow each other are a div of class `contents` holding a
    bullet list nested by depth, each item holding the entry's div, with
    its label as a span of class `label` and its title, a link to its
    heading when it has one; its page number is not written. The footnotes
    of a list or a contents are defined after it.

    A referenced footnote is a Pandoc footnote at its reference, its
    definition after the block or note that refers to it, holding its
    blocks' divs, margin notes among them, without its marker. Every other
    note, an unreferenced footnote or an endnote, is a div with its id and
    the class `note` or `endnote` around its blocks' divs, its marker first
    in the first that is not a margin note; it follows the last block, in
    the order of blocks.json, whose first origin is on the note's first
    page or an earlier one, or comes first of all when there is none. A
    note's group heading is a div of class `note-group` before its div.
    Notes written at the same place keep the order of blocks.json, and the
    endnotes among them that follow each other are one list, a div of class
    `endnotes`. A reference to an endnote is a link to it with the
    reference's text, marked `epub:type="noteref"`.

    The title and each author are escaped by escape_markdown too. Raises
    InputFileError, naming blocks.json, when it is malformed: an id given
    twice, a note without blocks or origin, a heading without a level from
    1 to 6, an index or contents entry without a depth from 1, a list item
    without a label, a heading reference that names no heading, a
    reference that names no note, a note whose `referenced`
    disagrees with whether a block refers to it, or a footnote referenced
    twice. Raises InputFileError, naming blocks.json and the block or note,
    for what markdown does not write: a list item whose label is not a list
    marker, a contents entry linked to its heading with a note reference
    in its title, a figure's image path that is not
    relative or holds other characters than ASCII letters, digits, "_",
    ".", "-" and "/", a note reference in a figure's caption, a note block
    that is not a paragraph, quote, verse or margin note, a reference to a
    footnote inside a referenced footnote, a group heading on a note that
    is not an endnote, or a character XML 1.0 does not allow, in a text,
    label, source, marker or group heading (named as U+FFFE).
    """
    _check_well_formed(blocks)
    _check_writable(blocks)
    notes = frozendict({note.id: note for note in blocks.notes})
    printed = tuple(
        note for note in blocks.notes if not _is_footnote_at_its_reference(note)
    )
    printed_at: dict[int, list[Note]] = {}
    for note, position in zip(
        printed,
        note_places(
            tuple(
                block.origin[0].page_index if block.origin else None
                for block in blocks.blocks
            ),
            tuple(note.origin[0].page_index for note in printed),
        ),
        strict=True,
    ):
        printed_at.setdefault(position, []).append(note)

    def notes_at(position: int) -> tuple[str, ...]:
        groups = (
            tuple(group)
            for _, group in itertools.groupby(
                printed_at.get(position, ()), key=lambda note: note.kind
            )
        )
        return tuple(
            part
            for group in groups
            for part in _with_footnotes(
                _printed_notes(group, notes),
                tuple(block for note in group for block in note.blocks),
                notes,
            )
        )

    runs = _runs(
        blocks.blocks,
        frozenset(position - 1 for position in printed_at if position > 0),
    )
    body: list[str] = []
    position = 0
    for run in runs:
        if (
            run[0].kind is BlockKind.LIST_ITEM
            and position > 0
            and blocks.blocks[position - 1].kind is BlockKind.LIST_ITEM
            and position not in printed_at
        ):
            body.append(_LIST_BREAK)
        position += len(run)
        body.extend(_with_footnotes(_run_markdown(run, notes), run, notes))
        body.extend(notes_at(position))
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


def _check_figure_images(folder: BookFolder, blocks: BlocksFile) -> None:
    """Raise InputFileError when the image of a figure of `blocks` is not a
    file inside `folder`, naming each such figure and its image, so that
    Pandoc does not fail on it later."""
    root = folder.root.resolve()
    missing = tuple(
        f"figure {block.id} has the image {block.figure}"
        for block in blocks.blocks
        if block.kind is BlockKind.FIGURE
        and block.figure is not None
        and not (
            (image := (folder.root / block.figure).resolve()).is_relative_to(root)
            and image.is_file()
        )
    )
    if missing:
        message = (
            f"{folder.blocks_json}: {'; '.join(missing)}, which is not a file in "
            f"{folder.root}; run `galley2epub extract` to cut the figures again"
        )
        raise InputFileError(message)


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
    fails. Raises InputFileError, naming each figure, when a figure's image
    is not a file in the book folder. markdown runs once, so `workers` is
    not used.
    """
    del workers  # every stage's run takes it; markdown is not per page
    delete_stage_outputs(folder, Stage.MARKDOWN)
    _, blocks = read_checked_input(
        folder.pages_json, config.pdf, folder.blocks_json, read_blocks
    )
    _check_no_edits(folder)
    _check_figure_images(folder, blocks)
    book_markdown = render_markdown(blocks, config)
    check_stage(FidelityBoundary.MARKDOWN, blocks, read_markdown(book_markdown))
    folder.book_md.write_text(book_markdown, encoding="utf-8", newline="\n")
    _logger.info(
        "wrote %s: %d blocks, %d notes",
        folder.book_md,
        len(blocks.blocks),
        len(blocks.notes),
    )
