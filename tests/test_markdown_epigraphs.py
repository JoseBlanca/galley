"""Tests of markdown's epigraphs, note group headings and no-break spaces
(structure spec section 25), on blocks written in the test."""

import hashlib
import json
import shutil
import subprocess
import zipfile
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

import pytest

from galley import epub, markdown
from galley.book_folder import BookFolder
from galley.config import BookConfig, Language
from galley.errors import FidelityBoundary, InputFileError
from galley.fidelity import check_stage, read_markdown
from galley.markdown import render_markdown
from galley.model import (
    Block,
    BlockKind,
    BlocksFile,
    Box,
    Emphasis,
    Note,
    NoteKind,
    Origin,
    PageInfo,
    PageKind,
    PagesFile,
    Span,
    TextSource,
    write_blocks,
    write_pages,
)

_PDF_BYTES = b"%PDF-1.4 a stand-in: markdown reads only its hash"
SOURCE_PDF_SHA256 = hashlib.sha256(_PDF_BYTES).hexdigest()

CONFIG = BookConfig(
    pdf=Path("/books/turney.pdf"),
    title="A Book",
    authors=("A. Author",),
    language=Language.EN,
)

HEADER = """\
---
title: "A Book"
author:
- "A\\\\. Author"
lang: en
---
"""

NO_BREAK_SPACE = " "


def _block(
    block_id: str,
    kind: BlockKind,
    text: str,
    page_index: int,
    *,
    level: int | None = None,
    source: str | None = None,
) -> Block:
    return Block(
        id=block_id,
        kind=kind,
        level=level,
        label=None,
        source=source,
        spans=(Span(text, Emphasis.NONE, None),),
        figure=None,
        origin=(Origin(page_index, Box(10.0, 20.0, 300.0, 400.0)),),
    )


def _endnote(note_id: str, text: str, *, group: str | None = None) -> Note:
    page_index = int(note_id[3:7])
    return Note(
        id=note_id,
        kind=NoteKind.ENDNOTE,
        marker="1",
        # Its block's number is the note's plus 100, apart from the body's.
        blocks=(
            _block(
                f"b-p{page_index:04d}-{int(note_id[-3:]) + 100:03d}",
                BlockKind.PARAGRAPH,
                text,
                page_index,
            ),
        ),
        origin=(Origin(page_index, Box(10.0, 500.0, 300.0, 520.0)),),
        referenced=False,
        group=group,
    )


def _blocks_file(blocks: tuple[Block, ...], notes: tuple[Note, ...] = ()) -> BlocksFile:
    return BlocksFile(
        source_pdf_sha256=SOURCE_PDF_SHA256,
        blocks=blocks,
        notes=notes,
        removals=(),
        word_changes=(),
        page_numbers=(),
    )


def _check_fidelity(blocks: BlocksFile) -> None:
    check_stage(
        FidelityBoundary.MARKDOWN,
        blocks,
        read_markdown(render_markdown(blocks, CONFIG)),
    )


CHAPTER = _block("b-p0000-001", BlockKind.HEADING, "The Start", 0, level=1)

PROSE_EPIGRAPH = _blocks_file(
    (
        CHAPTER,
        _block(
            "b-p0000-002",
            BlockKind.EPIGRAPH,
            "The life of man, solitary, poor, nasty, brutish, and short.",
            0,
            source="Thomas Hobbes, 1651",
        ),
        _block("b-p0000-003", BlockKind.PARAGRAPH, "It began.", 0),
    )
)


@pytest.mark.pandoc
def test_a_prose_epigraph_is_a_div_with_its_quotation_and_its_source_div() -> None:
    assert render_markdown(PROSE_EPIGRAPH, CONFIG) == (
        HEADER
        + """
# The Start {#b-p0000-001}

:::: {#b-p0000-002 .epigraph}
The life of man\\, solitary\\, poor\\, nasty\\, brutish\\, and short\\.

::: {.epigraph-source}
— Thomas Hobbes\\, 1651
:::
::::

::: {#b-p0000-003}
It began\\.
:::
"""
    )
    _check_fidelity(PROSE_EPIGRAPH)


VERSE_EPIGRAPH = _blocks_file(
    (
        CHAPTER,
        _block(
            "b-p0000-002",
            BlockKind.EPIGRAPH,
            "Tyger Tyger, burning bright,\nIn the forests of the night;",
            0,
            source="William Blake",
        ),
    )
)


@pytest.mark.pandoc
def test_a_verse_epigraph_keeps_each_line_with_a_hard_line_break() -> None:
    assert render_markdown(VERSE_EPIGRAPH, CONFIG) == (
        HEADER
        + """
# The Start {#b-p0000-001}

:::: {#b-p0000-002 .epigraph}
Tyger Tyger\\, burning bright\\,\\
In the forests of the night\\;

::: {.epigraph-source}
— William Blake
:::
::::
"""
    )
    _check_fidelity(VERSE_EPIGRAPH)


@pytest.mark.pandoc
def test_the_source_div_starts_with_a_dash_and_a_no_break_space_that_pandoc_keeps() -> (
    None
):
    words = read_markdown(render_markdown(PROSE_EPIGRAPH, CONFIG)).words

    # The dash, which blocks.json does not hold, is not among the words read.
    assert tuple(word.text for word in words if word.block_id == "b-p0000-002") == (
        *("The", "life", "of", "man,", "solitary,", "poor,", "nasty,"),
        *("brutish,", "and", "short.", "Thomas", "Hobbes,", "1651"),
    )
    # A no-break space read as an ordinary space would let the dash end a
    # line of its own; Pandoc keeps the character.
    document = _pandoc_json(render_markdown(PROSE_EPIGRAPH, CONFIG))
    assert {"t": "Str", "c": f"—{NO_BREAK_SPACE}Thomas"} in _elements(document)


def test_an_epigraph_without_a_source_is_its_quotation_alone() -> None:
    blocks = _blocks_file(
        (_block("b-p0000-002", BlockKind.EPIGRAPH, "Alone.", 0, source=None),)
    )

    assert render_markdown(blocks, CONFIG) == (
        HEADER
        + """
:::: {#b-p0000-002 .epigraph}
Alone\\.
::::
"""
    )


GROUPED_NOTES = _blocks_file(
    (
        CHAPTER,
        _block("b-p0000-002", BlockKind.PARAGRAPH, "Text.", 0),
        _block("b-p0001-001", BlockKind.HEADING, "Notes", 1, level=1),
    ),
    (
        _endnote("n-p0001-001", "See the rolls.", group="Chapter 1. The Start"),
        _endnote("n-p0001-002", "Ibid."),
        _endnote("n-p0001-003", "Again.", group="Chapter 2. The End"),
    ),
)


def _pandoc_json(document: str) -> object:
    pandoc = shutil.which("pandoc")
    assert pandoc is not None
    result = subprocess.run(
        [pandoc, "--from", "markdown-smart", "--to", "json"],
        input=document,
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )
    return json.loads(result.stdout)


def _elements(value: object) -> list[object]:
    """Every dict of a Pandoc JSON document, depth first."""
    match value:
        case dict():
            return [value, *(e for item in value.values() for e in _elements(item))]
        case list():
            return [e for item in value for e in _elements(item)]
        case _:
            return []


@pytest.mark.pandoc
def test_a_group_heading_is_a_div_before_its_note_and_not_a_pandoc_heading() -> None:
    document = render_markdown(GROUPED_NOTES, CONFIG)

    assert document.endswith(
        """
# Notes {#b-p0001-001}

::::: {.endnotes}
::: {.note-group}
Chapter 1\\. The Start
:::

:::: {#n-p0001-001 .endnote}
::: {#b-p0001-101}
1 See the rolls\\.
:::
::::

:::: {#n-p0001-002 .endnote}
::: {#b-p0001-102}
1 Ibid\\.
:::
::::

::: {.note-group}
Chapter 2\\. The End
:::

:::: {#n-p0001-003 .endnote}
::: {#b-p0001-103}
1 Again\\.
:::
::::
:::::
"""
    )
    headers = [
        element
        for element in _elements(_pandoc_json(document))
        if isinstance(element, dict) and element.get("t") == "Header"
    ]
    assert len(headers) == 2  # the chapter's and the notes', no group's
    _check_fidelity(GROUPED_NOTES)


FRENCH_SPACES = _blocks_file(
    (
        _block(
            "b-p0000-001",
            BlockKind.PARAGRAPH,
            f"Est-elle complète{NO_BREAK_SPACE}; et pourquoi{NO_BREAK_SPACE}?",
            0,
        ),
        _block(
            "b-p0000-002",
            BlockKind.EPIGRAPH,
            f"Qui vive{NO_BREAK_SPACE}!",
            0,
            source=f"Hugo{NO_BREAK_SPACE}:",
        ),
    ),
    (_endnote("n-p0001-001", "Voir.", group=f"Chapitre{NO_BREAK_SPACE}:"),),
)


@pytest.mark.pandoc
def test_a_no_break_space_is_written_as_the_character_and_pandoc_keeps_it() -> None:
    document = render_markdown(FRENCH_SPACES, CONFIG)

    assert f"Est\\-elle complète{NO_BREAK_SPACE}\\; et pourquoi{NO_BREAK_SPACE}\\?" in (
        document
    )
    assert f"Qui vive{NO_BREAK_SPACE}\\!" in document
    assert f"—{NO_BREAK_SPACE}Hugo{NO_BREAK_SPACE}\\:" in document
    assert f"Chapitre{NO_BREAK_SPACE}\\:" in document
    strs = {
        element["c"]
        for element in _elements(_pandoc_json(document))
        if isinstance(element, dict) and element.get("t") == "Str"
    }
    assert f"complète{NO_BREAK_SPACE};" in strs
    _check_fidelity(FRENCH_SPACES)


@pytest.mark.parametrize(
    ("note", "refused"),
    [
        (
            replace(_endnote("n-p0001-001", "A."), kind=NoteKind.FOOTNOTE, group="G"),
            r"note n-p0001-001 is a footnote and has the group heading 'G'",
        ),
        (
            _endnote("n-p0001-001", "A.", group="￾"),
            r"the group heading of note n-p0001-001 holds U\+FFFE",
        ),
    ],
    ids=["a group on a footnote", "a group with a character XML does not allow"],
)
def test_render_markdown_refuses_a_group_it_cannot_write(
    note: Note, refused: str
) -> None:
    with pytest.raises(InputFileError, match=rf"blocks.json.*{refused}"):
        render_markdown(_blocks_file((CHAPTER,), (note,)), CONFIG)


def test_render_markdown_refuses_a_source_with_a_character_xml_does_not_allow() -> None:
    blocks = _blocks_file(
        (_block("b-p0000-002", BlockKind.EPIGRAPH, "A.", 0, source="B￾"),)
    )

    with pytest.raises(
        InputFileError, match=r"blocks.json.*the source of block b-p0000-002.*U\+FFFE"
    ):
        render_markdown(blocks, CONFIG)


def _book(root: Path, blocks: BlocksFile) -> tuple[BookFolder, BookConfig]:
    """A book folder with book.pdf, pages.json of two pages made from it,
    and `blocks`, and CONFIG with book.pdf as its PDF."""
    pdf = root / "book.pdf"
    pdf.write_bytes(_PDF_BYTES)
    folder = BookFolder(root)
    write_pages(
        folder.pages_json,
        PagesFile(
            source_pdf_sha256=SOURCE_PDF_SHA256,
            pages=tuple(
                PageInfo(
                    index=index,
                    width_pt=432.0,
                    height_pt=648.0,
                    kind=PageKind.TEXT,
                    text_source=TextSource.TEXT_LAYER,
                    text_layer_score=None,
                    exclude_regions=(),
                    figure_boxes=(),
                    blank_checked_by_ocr=False,
                )
                for index in range(2)
            ),
            ocr_audit=None,
        ),
    )
    write_blocks(folder.blocks_json, blocks)
    return folder, replace(CONFIG, pdf=pdf)


EPUB_BOOK = _blocks_file(
    (
        *VERSE_EPIGRAPH.blocks,
        _block("b-p0000-003", BlockKind.PARAGRAPH, "It began.", 0),
        _block("b-p0001-001", BlockKind.HEADING, "Notes", 1, level=1),
    ),
    GROUPED_NOTES.notes,
)


# Java starts in about a second; the 8-thread run would start it 8 times.
@pytest.mark.thread_unsafe
@pytest.mark.pandoc
@pytest.mark.epubcheck
def test_the_epub_of_an_epigraph_and_note_groups_passes_epubcheck(
    tmp_path: Path, check_epubs: Callable[..., None]
) -> None:
    folder, config = _book(tmp_path, EPUB_BOOK)

    markdown.run(folder, config)
    epub.run(folder, config)

    check_epubs(folder.book_epub)
    with zipfile.ZipFile(folder.book_epub) as book:
        names = book.namelist()
        navigation = book.read(next(n for n in names if n.endswith("nav.xhtml")))
        style_sheet = b"".join(
            book.read(name) for name in names if name.endswith(".css")
        )
        chapters = b"".join(
            book.read(name) for name in names if name.endswith(".xhtml")
        )
    assert b"Chapter 1. The Start" not in navigation
    assert b".epigraph .epigraph-source p" in style_sheet
    assert b".note-group p" in style_sheet
    assert "— William Blake".encode() in chapters
    assert b'class="note-group"' in chapters
