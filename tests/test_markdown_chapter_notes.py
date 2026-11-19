"""Tests of unlinked footnotes at the end of their chapter, under a heading
"Notes" (docs/specs/structure.md, section 36; the owner, 19 November
2026).

The literal blocks are small books of a few pages: a heading of level 1
or 2 starts a chapter, and each unlinked footnote is placed by the page it
was printed on.
"""

import re
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

import pytest

from galley.book_folder import BookFolder
from galley.config import BookConfig, Language, read_config
from galley.errors import ExternalProgramError, FidelityBoundary
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
    Span,
    block_text,
    read_blocks,
)

_HASH = "a" * 64

CONFIG = BookConfig(
    pdf=Path("/books/kadesh.pdf"),
    title="The Battle of Kadesh",
    authors=("James Henry Breasted",),
    language=Language.EN,
)

HEADER = """\
---
title: "The Battle of Kadesh"
author:
- "James Henry Breasted"
lang: en
---
"""


def _block(
    block_id: str,
    kind: BlockKind,
    text: str,
    *page_indices: int,
    level: int | None = None,
    note_ref: str | None = None,
) -> Block:
    """A block of the pages given, its text one span and, with `note_ref`,
    a reference span "1" to that note after it."""
    reference = (Span("1", Emphasis.NONE, note_ref),) if note_ref is not None else ()
    return Block(
        id=block_id,
        kind=kind,
        level=level,
        label=None,
        spans=(Span(text, Emphasis.NONE, None), *reference),
        figure=None,
        origin=tuple(
            Origin(page_index, Box(10.0, 20.0, 300.0, 400.0))
            for page_index in page_indices
        ),
    )


def _heading(block_id: str, text: str, page_index: int, level: int) -> Block:
    return _block(block_id, BlockKind.HEADING, text, page_index, level=level)


def _paragraph(
    block_id: str, text: str, *page_indices: int, note_ref: str | None = None
) -> Block:
    return _block(block_id, BlockKind.PARAGRAPH, text, *page_indices, note_ref=note_ref)


def _note(
    note_id: str,
    page_index: int,
    text: str,
    marker: str,
    *,
    kind: NoteKind = NoteKind.FOOTNOTE,
    referenced: bool = False,
) -> Note:
    page = note_id.split("-")[1]
    return Note(
        id=note_id,
        kind=kind,
        marker=marker,
        blocks=(_paragraph(f"b-{page}-9{note_id[-2:]}", text, page_index),),
        origin=(Origin(page_index, Box(10.0, 500.0, 300.0, 520.0)),),
        referenced=referenced,
    )


def _book(blocks: tuple[Block, ...], notes: tuple[Note, ...]) -> BlocksFile:
    return BlocksFile(
        source_pdf_sha256=_HASH,
        blocks=blocks,
        notes=notes,
        removals=(),
        word_changes=(),
        page_numbers=(),
    )


# Two chapters of level 1: page 0 and 1 the first, page 2 the second; an
# unlinked footnote on pages 0, 1 and 2.
TWO_CHAPTERS = _book(
    (
        _heading("b-p0000-001", "THE FIRST", 0, 1),
        _paragraph("b-p0000-002", "Text of page zero.", 0),
        _paragraph("b-p0001-001", "Text of page one.", 1),
        _heading("b-p0002-001", "THE SECOND", 2, 1),
        _paragraph("b-p0002-002", "Text of page two.", 2),
    ),
    (
        _note("n-p0000-001", 0, "Note of page zero.", "15"),
        _note("n-p0001-001", 1, "Note of page one.", "*"),
        _note("n-p0002-001", 2, "Note of page two.", "16"),
    ),
)

TWO_CHAPTERS_MARKDOWN = (
    HEADER
    + """
# THE FIRST {#b-p0000-001}

::: {#b-p0000-002}
Text of page zero\\.
:::

::: {#b-p0001-001}
Text of page one\\.
:::

## Notes {#notes-n-p0000-001 .unlisted .chapter-notes}

:::: {#n-p0000-001 .note}
::: {#b-p0000-901}
15 Note of page zero\\.
:::
::::

:::: {#n-p0001-001 .note}
::: {#b-p0001-901}
\\* Note of page one\\.
:::
::::

# THE SECOND {#b-p0002-001}

::: {#b-p0002-002}
Text of page two\\.
:::

## Notes {#notes-n-p0002-001 .unlisted .chapter-notes}

:::: {#n-p0002-001 .note}
::: {#b-p0002-901}
16 Note of page two\\.
:::
::::
"""
)


def test_unlinked_footnotes_go_to_the_end_of_their_chapter_under_notes() -> None:
    assert render_markdown(TWO_CHAPTERS, CONFIG) == TWO_CHAPTERS_MARKDOWN


def _notes_headings(markdown: str) -> tuple[str, ...]:
    return tuple(
        match.group()
        for match in re.finditer(r"^#+ Notes \{[^}]*\}$", markdown, flags=re.MULTILINE)
    )


def test_a_chapter_without_unlinked_footnotes_gets_no_notes_heading() -> None:
    book = replace(TWO_CHAPTERS, notes=TWO_CHAPTERS.notes[2:])

    markdown = render_markdown(book, CONFIG)

    assert _notes_headings(markdown) == (
        "## Notes {#notes-n-p0002-001 .unlisted .chapter-notes}",
    )


def test_a_book_without_unlinked_footnotes_gets_no_notes_heading() -> None:
    markdown = render_markdown(replace(TWO_CHAPTERS, notes=()), CONFIG)

    assert _notes_headings(markdown) == ()


def test_unlinked_footnotes_before_the_first_heading_go_just_before_it() -> None:
    book = _book(
        (
            _paragraph("b-p0000-001", "The end of a chapter the excerpt cut.", 0),
            _heading("b-p0001-001", "THE NEXT", 1, 1),
            _paragraph("b-p0001-002", "Text.", 1),
        ),
        (_note("n-p0000-001", 0, "Note of page zero.", "1"),),
    )

    markdown = render_markdown(book, CONFIG)

    heading = "## Notes {#notes-n-p0000-001 .unlisted .chapter-notes}"
    assert (
        markdown.index("{#b-p0000-001}")
        < markdown.index(heading)
        < markdown.index("{#n-p0000-001 .note}")
        < markdown.index("# THE NEXT")
    )


def test_unlinked_footnotes_of_a_book_without_headings_go_to_its_end() -> None:
    book = _book(
        (
            _paragraph("b-p0000-001", "Page zero.", 0),
            _paragraph("b-p0001-001", "Page one.", 1),
        ),
        (_note("n-p0000-001", 0, "Note of page zero.", "1"),),
    )

    markdown = render_markdown(book, CONFIG)

    assert markdown.endswith(
        "::: {#b-p0001-001}\nPage one\\.\n:::\n\n"
        "## Notes {#notes-n-p0000-001 .unlisted .chapter-notes}\n\n"
        ":::: {#n-p0000-001 .note}\n::: {#b-p0000-901}\n1 Note of page zero\\.\n"
        ":::\n::::\n"
    )


def test_notes_of_a_level_2_chapter_are_level_3_and_a_level_3_heading_ends_none() -> (
    None
):
    book = _book(
        (
            _heading("b-p0000-001", "BOOK ONE", 0, 1),
            _heading("b-p0001-001", "§ 1. Plan of the Survey.", 1, 2),
            _paragraph("b-p0001-002", "Text of page one.", 1),
            _heading("b-p0002-001", "A subsection", 2, 3),
            _paragraph("b-p0002-002", "Text of page two.", 2),
            _heading("b-p0003-001", "§ 2. Hides.", 3, 2),
            _paragraph("b-p0003-002", "Text of page three.", 3),
        ),
        (_note("n-p0001-001", 1, "Note of page one.", "1"),),
    )

    markdown = render_markdown(book, CONFIG)

    heading = "### Notes {#notes-n-p0001-001 .unlisted .chapter-notes}"
    assert _notes_headings(markdown) == (heading,)
    assert (
        markdown.index("{#b-p0002-002}")
        < markdown.index(heading)
        < markdown.index("{#n-p0001-001 .note}")
        < markdown.index("## § 2")
    )
    assert markdown.index("## § 1") < markdown.index("{#b-p0001-002}")


def test_a_heading_inside_a_page_takes_that_pages_unlinked_footnotes() -> None:
    book = _book(
        (
            _heading("b-p0000-001", "THE FIRST", 0, 1),
            _paragraph("b-p0000-002", "Text that ends on page one.", 0, 1),
            _heading("b-p0001-001", "THE SECOND", 1, 1),
            _paragraph("b-p0001-002", "Text below the heading.", 1),
        ),
        (_note("n-p0001-001", 1, "Note of page one.", "1"),),
    )

    markdown = render_markdown(book, CONFIG)

    assert markdown.index("# THE SECOND") < markdown.index("{#n-p0001-001 .note}")
    assert markdown.endswith("1 Note of page one\\.\n:::\n::::\n")


def test_endnotes_and_linked_footnotes_stay_where_they_were() -> None:
    book = _book(
        (
            _heading("b-p0000-001", "THE FIRST", 0, 1),
            _paragraph("b-p0000-002", "Linked", 0, note_ref="n-p0000-001"),
            _paragraph("b-p0000-003", "Unlinked here.", 0),
            _paragraph("b-p0001-001", "Text of page one.", 1),
            _heading("b-p0002-001", "NOTES.", 2, 1),
            _paragraph("b-p0002-002", "Before the endnotes.", 2),
        ),
        (
            _note("n-p0000-001", 0, "A linked note.", "1", referenced=True),
            _note("n-p0000-002", 0, "An unlinked note.", "2"),
            _note("n-p0002-001", 2, "An endnote.", "291.", kind=NoteKind.ENDNOTE),
        ),
    )

    markdown = render_markdown(book, CONFIG)

    assert (
        markdown.index("Linked[^n-p0000-001]")
        < markdown.index("[^n-p0000-001]:\n")
        < markdown.index("{#b-p0000-003}")
        < markdown.index("{#b-p0001-001}")
        < markdown.index("## Notes {#notes-n-p0000-002")
        < markdown.index("{#n-p0000-002 .note}")
        < markdown.index("# NOTES")
        < markdown.index("{#b-p0002-002}")
        < markdown.index("{#n-p0002-001 .endnote}")
    )
    assert len(_notes_headings(markdown)) == 1


def test_a_linked_footnote_of_an_unlinked_one_is_defined_after_it() -> None:
    book = _book(
        (
            _paragraph("b-p0000-001", "Text.", 0),
            _heading("b-p0001-001", "THE NEXT", 1, 1),
        ),
        (
            Note(
                id="n-p0000-001",
                kind=NoteKind.FOOTNOTE,
                marker="1",
                blocks=(
                    _paragraph(
                        "b-p0000-901", "Unlinked, citing", 0, note_ref="n-p0000-002"
                    ),
                ),
                origin=(Origin(0, Box(10.0, 500.0, 300.0, 520.0)),),
                referenced=False,
            ),
            _note("n-p0000-002", 0, "A note of the note.", "2", referenced=True),
        ),
    )

    markdown = render_markdown(book, CONFIG)

    assert (
        markdown.index("## Notes")
        < markdown.index("citing[^n-p0000-002]")
        < markdown.index("[^n-p0000-002]:\n")
        < markdown.index("# THE NEXT")
    )


@pytest.mark.pandoc
def test_the_notes_heading_gives_no_word_and_the_words_are_moved_not_lost() -> None:
    markdown = render_markdown(TWO_CHAPTERS, CONFIG)

    words = read_markdown(markdown)

    assert "Notes" not in tuple(word.text for word in words.words)
    check_stage(FidelityBoundary.MARKDOWN, TWO_CHAPTERS, words)


@pytest.mark.pandoc
def test_read_markdown_refuses_a_chapter_notes_heading_with_other_text() -> None:
    markdown = TWO_CHAPTERS_MARKDOWN.replace(
        "## Notes {#notes-n-p0000-001", "## Notes of Greece {#notes-n-p0000-001"
    )

    with pytest.raises(ExternalProgramError, match="chapter-notes"):
        read_markdown(markdown)


# Excerpt tests (structure spec section 36, "How it is verified").


def _note_id_with(blocks: BlocksFile, text: str) -> str:
    (note_id,) = (
        note.id
        for note in blocks.notes
        if any(text in block_text(block) for block in note.blocks)
    )
    return note_id


# Kadesh's pages 11 and 12 (excerpt pages 3 and 4 of `kadesh_redo`): their
# footnotes, none linked, from the first of page 11 to the last of page
# 12, read on the page images on 19 November 2026.
_KADESH_FIRST_OF_PAGE_11 = "Called by de Rougé the Bulletin."
_KADESH_LAST_OF_PAGE_11 = "Papyrus Raifet contains only one page of ten lines"
_KADESH_LAST_OF_PAGE_12 = "On the rear (south side) of Ramses II.’s pylon."


@pytest.mark.tesseract
@pytest.mark.pandoc
def test_kadesh_notes_of_pages_11_and_12_are_at_the_end_under_notes(
    redo_excerpt_run: Callable[[str], BookFolder],
) -> None:
    folder = redo_excerpt_run("kadesh_redo")
    blocks = read_blocks(folder.blocks_json)
    markdown = render_markdown(blocks, read_config(folder.book_toml))
    pages_notes = tuple(
        note.id for note in blocks.notes if note.origin[0].page_index in {3, 4}
    )
    first = _note_id_with(blocks, _KADESH_FIRST_OF_PAGE_11)
    last_of_11 = _note_id_with(blocks, _KADESH_LAST_OF_PAGE_11)
    last = _note_id_with(blocks, _KADESH_LAST_OF_PAGE_12)
    places = tuple(markdown.index(f"{{#{note_id} .note}}") for note_id in pages_notes)
    (heading,) = _notes_headings(markdown)
    last_body_block = blocks.blocks[-1].id

    assert len(pages_notes) == 11
    assert (pages_notes[0], pages_notes[7], pages_notes[-1]) == (
        first,
        last_of_11,
        last,
    )
    assert heading.startswith("## Notes {#notes-n-p0000-")
    assert markdown.index(f"{{#{last_body_block}") < markdown.index(heading)
    assert markdown.index(heading) < min(places)
    assert places == tuple(sorted(places))
    check_stage(FidelityBoundary.MARKDOWN, blocks, read_markdown(markdown))


# Haskins' page 40 (excerpt page 8 of `haskins_heads_notes`): its footnote
# "Corpus Poeticum Boreale, i, p. 265 f.", whose reference "brand.¹" is not
# linked, and the heading "BIBLIOGRAPHICAL NOTE" of Haskins' page 51
# (excerpt page 10), read on the page images on 19 November 2026.


@pytest.mark.tesseract
@pytest.mark.pandoc
def test_haskins_note_of_page_40_moves_to_before_the_bibliographical_note(
    excerpt_books: frozendict[str, BookFolder],
) -> None:
    folder = excerpt_books["haskins_heads_notes"]
    blocks = read_blocks(folder.blocks_json)
    markdown = folder.book_md.read_text(encoding="utf-8")
    note_id = _note_id_with(blocks, "Corpus Poeticum Boreale")
    quotation = next(
        block.id
        for block in blocks.blocks
        if "The lees of the din of war" in block_text(block)
    )
    race = next(
        block.id
        for block in blocks.blocks
        if "The question of race is more difficult" in block_text(block)
    )

    assert (
        markdown.index(f"{{#{quotation}")
        < markdown.index(f"{{#{race}")
        < markdown.index(f"## Notes {{#notes-{note_id} .unlisted .chapter-notes}}")
        < markdown.index(f"{{#{note_id} .note}}")
        < markdown.index("BIBLIOGRAPHICAL NOTE")
    )
