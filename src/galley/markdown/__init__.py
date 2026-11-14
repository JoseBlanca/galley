"""The markdown stage: blocks.json to book.md, the Pandoc Markdown the epub
stage reads and the owner proofreads.

In the walking skeleton (spec section 8) book.md is a metadata header and
one fenced div per paragraph block, `::: {#b-p0012-003}`, whose text has
every ASCII punctuation character escaped. Edits are refused, since none
can exist before `galley2epub edits-from` is built.
"""

import json
import logging
import string

from galley.book_folder import BookFolder
from galley.config import BookConfig
from galley.errors import EditError, FidelityBoundary, GalleyError
from galley.fidelity import check_stage, read_markdown
from galley.model import (
    Block,
    BlockKind,
    BlocksFile,
    block_text,
    check_source_pdf,
    read_blocks,
    read_edits,
    read_pages,
)
from galley.parallel import DEFAULT_WORKERS

__all__ = ["escape_markdown", "render_markdown", "run"]

_logger = logging.getLogger(__name__)

# Spec section 8: Pandoc's Markdown reads any escaped ASCII punctuation as
# itself, so none of it can start a list, emphasis or a fence.
_ESCAPED = frozendict(
    {ord(character): "\\" + character for character in string.punctuation}
)
# Spec section 8: the white space Pandoc's Markdown reads as layout. Pandoc
# 3.14 drops a carriage return inside a word and reads a tab or four spaces
# at the start of a line as a code block; str.split(), which the fidelity
# check splits words with, splits at all four, so no word changes.
_LAYOUT_WHITE_SPACE = " \t\n\r"
_PLAIN_WHITE_SPACE = frozendict({ord(character): " " for character in "\t\n\r"})


def escape_markdown(text: str) -> str:
    """The text of a block as one line of Pandoc Markdown that Pandoc reads
    back with the same words: a backslash before every ASCII punctuation
    character, each tab, line feed and carriage return made a space, and
    those and spaces dropped at the start and end. Every other character is
    kept as it is."""
    plain = text.strip(_LAYOUT_WHITE_SPACE).translate(_PLAIN_WHITE_SPACE)
    return plain.translate(_ESCAPED)


def _unwritable_block(block: Block) -> str | None:
    """Why the skeleton cannot write a block, or None when it can."""
    if block.kind is not BlockKind.PARAGRAPH:
        return f"block {block.id} is a {block.kind.value}"
    if any(span.note_ref is not None for span in block.spans):
        return f"block {block.id} holds a note reference"
    return None


def _check_writable(blocks: BlocksFile) -> None:
    """Raise GalleyError at a block the skeleton does not write, a heading,
    figure or other kind than a paragraph, a note reference, or a note,
    rather than write it wrongly."""
    problems = tuple(
        problem
        for problem in (_unwritable_block(block) for block in blocks.blocks)
        if problem is not None
    ) + tuple(f"note {note.id}" for note in blocks.notes)
    if problems:
        message = (
            "the walking skeleton's markdown writes only paragraphs without "
            f"notes; blocks.json has: {'; '.join(problems)}"
        )
        raise GalleyError(message)


def _header(config: BookConfig) -> str:
    """The metadata header, its values as JSON strings, which YAML reads as
    double-quoted strings."""
    authors = "".join(
        f"- {json.dumps(author, ensure_ascii=False)}\n" for author in config.authors
    )
    return (
        "---\n"
        f"title: {json.dumps(config.title, ensure_ascii=False)}\n"
        "author:\n"
        f"{authors}"
        f"lang: {config.language.value}\n"
        "---\n"
    )


def _div(block: Block) -> str:
    return f"::: {{#{block.id}}}\n{escape_markdown(block_text(block))}\n:::\n"


def render_markdown(blocks: BlocksFile, config: BookConfig) -> str:
    """book.md: the metadata header from the config (title, authors,
    language), then one fenced div per block with the block's id, in the
    order of blocks.json, its text escaped by escape_markdown on one line,
    a blank line between each.

    Raises GalleyError, naming the block or note, for a block that is not
    a paragraph, a note reference, or a note: the skeleton does not write
    them.
    """
    _check_writable(blocks)
    return "\n".join((_header(config), *(_div(block) for block in blocks.blocks)))


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
            f"{', '.join(str(path) for path in with_edits)} hold edits; the walking "
            "skeleton does not apply edits, which are applied from the markdown "
            "spec on"
        )
        raise EditError(message)


def run(
    folder: BookFolder, config: BookConfig, *, workers: int = DEFAULT_WORKERS
) -> None:
    """Write book.md from blocks.json, after checking that no word is lost
    or invented between the two as Pandoc reads book.md.

    Deletes book.md first. Reads pages.json and blocks.json, and raises
    InputFileError when blocks.json was made from another PDF; raises
    EditError when an edits file holds an edit; raises FidelityError when
    the words differ, and ExternalProgramError when Pandoc is missing or
    fails. markdown runs once, so `workers` is not used.
    """
    del workers  # every stage's run takes it; markdown is not per page
    folder.book_md.unlink(missing_ok=True)
    pages = read_pages(folder.pages_json)
    blocks = read_blocks(folder.blocks_json)
    check_source_pdf(
        folder.blocks_json,
        blocks.source_pdf_sha256,
        expected_pdf_sha256=pages.source_pdf_sha256,
    )
    _check_no_edits(folder)
    book_markdown = render_markdown(blocks, config)
    check_stage(FidelityBoundary.MARKDOWN, blocks, read_markdown(book_markdown))
    folder.book_md.write_text(book_markdown, encoding="utf-8", newline="\n")
    _logger.info("wrote %s: %d blocks", folder.book_md, len(blocks.blocks))
