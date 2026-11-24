"""Tests of the back links from an endnote's number to its reference in
book.md (architecture section 9, "Back links"; owner, 24 November 2026).
The notes are made up."""

import hashlib
from dataclasses import replace
from pathlib import Path

import pytest

from galley.config import BookConfig, Language
from galley.errors import FidelityBoundary, FidelityError, InputFileError
from galley.fidelity import check_stage, gets_a_back_link, read_markdown
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
)

CONFIG = BookConfig(
    pdf=Path("/books/a-book.pdf"),
    title="A Book",
    authors=("A. Author",),
    language=Language.EN,
)


def _paragraph(block_id: str, *texts: str | tuple[str, str]) -> Block:
    """A paragraph on the page of its id, of a span for each text, a pair
    being a reference's text and the id of its note."""
    return Block(
        id=block_id,
        kind=BlockKind.PARAGRAPH,
        level=None,
        label=None,
        spans=tuple(
            Span(text[0], Emphasis.NONE, text[1])
            if isinstance(text, tuple)
            else Span(text, Emphasis.NONE, None)
            for text in texts
        ),
        figure=None,
        origin=(Origin(int(block_id[3:7]), Box(10.0, 20.0, 300.0, 400.0)),),
    )


def _endnote(note_id: str, marker: str, text: str, *, referenced: bool) -> Note:
    page_index = int(note_id[3:7])
    return Note(
        id=note_id,
        kind=NoteKind.ENDNOTE,
        marker=marker,
        blocks=(_paragraph(f"b-p{page_index:04d}-0{note_id[-2:]}", text),),
        origin=(Origin(page_index, Box(10.0, 500.0, 300.0, 520.0)),),
        referenced=referenced,
    )


def _blocks_file(blocks: tuple[Block, ...], notes: tuple[Note, ...]) -> BlocksFile:
    return BlocksFile(
        source_pdf_sha256=hashlib.sha256(b"a book").hexdigest(),
        blocks=blocks,
        notes=notes,
        removals=(),
        word_changes=(),
        page_numbers=(),
    )


# Page 1 refers twice to the endnote "6." and once to the endnote "7", the
# second reference to "6." on page 2; the endnotes, printed on page 9, are
# "6.", "7" and the unreferenced "8".
TWICE = _blocks_file(
    (
        _paragraph("b-p0001-001", "The Law", ("6", "n-p0009-001"), " of kings."),
        _paragraph(
            "b-p0002-001",
            "Again",
            ("6", "n-p0009-001"),
            " and the rolls",
            ("7", "n-p0009-002"),
        ),
    ),
    (
        _endnote("n-p0009-001", "6.", "Digest, 1.", referenced=True),
        _endnote("n-p0009-002", "7", "Code, 2.", referenced=True),
        _endnote("n-p0009-003", "8", "Novels, 3.", referenced=False),
    ),
)

TWICE_MARKDOWN = """\
---
title: "A Book"
author:
- "A\\\\. Author"
lang: en
---

::: {#b-p0001-001}
The Law[6](#n-p0009-001){#ref-n-p0009-001 epub:type="noteref"} of kings\\.
:::

::: {#b-p0002-001}
Again[6](#n-p0009-001){epub:type="noteref"} and the rolls\
[7](#n-p0009-002){#ref-n-p0009-002 epub:type="noteref"}
:::

::::: {.endnotes}
:::: {#n-p0009-001 .endnote}
::: {#b-p0009-001}
[6\\.](#ref-n-p0009-001){role="doc-backlink"} Digest\\, 1\\.
:::
::::

:::: {#n-p0009-002 .endnote}
::: {#b-p0009-002}
[7](#ref-n-p0009-002){role="doc-backlink"} Code\\, 2\\.
:::
::::

:::: {#n-p0009-003 .endnote}
::: {#b-p0009-003}
8 Novels\\, 3\\.
:::
::::
:::::
"""


def test_an_endnote_number_links_back_to_its_first_reference_and_an_unreferenced_one_does_not() -> (
    None
):
    assert render_markdown(TWICE, CONFIG) == TWICE_MARKDOWN


def test_an_endnote_with_an_empty_marker_gets_no_back_link_and_its_reference_no_id() -> (
    None
):
    blocks = _blocks_file(
        (_paragraph("b-p0001-001", "The Law", ("*", "n-p0009-001")),),
        (_endnote("n-p0009-001", "", "Digest, 1.", referenced=True),),
    )

    written = render_markdown(blocks, CONFIG)

    assert 'The Law[\\*](#n-p0009-001){epub:type="noteref"}\n' in written
    assert "::: {#b-p0009-001}\nDigest\\, 1\\.\n:::" in written
    assert "doc-backlink" not in written


def test_a_block_whose_id_is_that_of_a_reference_is_refused() -> None:
    blocks = _blocks_file(
        (
            _paragraph("b-p0001-001", "The Law", ("6", "n-p0009-001")),
            replace(_paragraph("b-p0001-002", "A block."), id="ref-n-p0009-001"),
        ),
        (_endnote("n-p0009-001", "6.", "Digest, 1.", referenced=True),),
    )

    with pytest.raises(InputFileError, match="id ref-n-p0009-001 is given 2 times"):
        render_markdown(blocks, CONFIG)


@pytest.mark.parametrize(
    "note_id", ["n-p0009 001", "n-p0009-001}", "9-n-p0009-001", "n-p0009-é01"]
)
def test_a_referenced_endnote_whose_id_makes_no_valid_reference_id_is_refused(
    note_id: str,
) -> None:
    blocks = _blocks_file(
        (_paragraph("b-p0001-001", "The Law", ("6", note_id)),),
        (
            replace(
                _endnote("n-p0009-001", "6.", "Digest, 1.", referenced=True),
                id=note_id,
            ),
        ),
    )

    with pytest.raises(InputFileError, match="not an id Pandoc and XML read"):
        render_markdown(blocks, CONFIG)


# The fidelity check at the markdown boundary reads the back link.


@pytest.mark.pandoc
def test_pandoc_reads_the_back_links_and_their_numbers_as_words() -> None:
    read = read_markdown(TWICE_MARKDOWN)

    assert (read.note_count, read.note_link_count, read.back_link_count) == (0, 3, 2)
    assert [word.text for word in read.words if word.block_id == "b-p0009-001"] == [
        "6.",
        "Digest,",
        "1.",
    ]
    check_stage(FidelityBoundary.MARKDOWN, TWICE, read)


@pytest.mark.pandoc
def test_a_word_put_into_a_back_link_is_found() -> None:
    damaged = TWICE_MARKDOWN.replace("[6\\.](#ref", "[6\\. and](#ref", 1)

    with pytest.raises(FidelityError) as raised:
        check_stage(FidelityBoundary.MARKDOWN, TWICE, read_markdown(damaged))

    assert dict(raised.value.invented) == {"and": 1}


@pytest.mark.pandoc
def test_a_back_link_lost_is_found_by_its_count() -> None:
    damaged = TWICE_MARKDOWN.replace(
        '[7](#ref-n-p0009-002){role="doc-backlink"} Code', "7 Code", 1
    )

    with pytest.raises(FidelityError) as raised:
        check_stage(FidelityBoundary.MARKDOWN, TWICE, read_markdown(damaged))

    assert raised.value.detail == (
        "referenced endnotes with a marker in blocks.json: 2; back links in the "
        "Markdown: 1"
    )


@pytest.mark.parametrize(
    ("note", "gets_one"),
    [
        (_endnote("n-p0009-001", "6.", "Digest, 1.", referenced=True), True),
        (_endnote("n-p0009-001", "6.", "Digest, 1.", referenced=False), False),
        (_endnote("n-p0009-001", "", "Digest, 1.", referenced=True), False),
        (_endnote("n-p0009-001", " ", "Digest, 1.", referenced=True), False),
        (_endnote("n-p0009-001", "\xa0", "Digest, 1.", referenced=True), False),
        (
            replace(
                _endnote("n-p0009-001", "6.", "Digest, 1.", referenced=True),
                kind=NoteKind.FOOTNOTE,
            ),
            False,
        ),
    ],
)
def test_only_a_referenced_endnote_with_a_marker_of_some_word_gets_a_back_link(
    note: Note, gets_one: bool
) -> None:
    assert gets_a_back_link(note) is gets_one


@pytest.mark.pandoc
@pytest.mark.parametrize("marker", [" ", "\xa0"])
def test_an_endnote_whose_marker_is_white_space_gets_no_back_link(
    marker: str,
) -> None:
    blocks = _blocks_file(
        (_paragraph("b-p0001-001", "The Law", ("*", "n-p0009-001")),),
        (_endnote("n-p0009-001", marker, "Digest, 1.", referenced=True),),
    )

    written = render_markdown(blocks, CONFIG)

    assert "doc-backlink" not in written
    assert "#ref-n-p0009-001" not in written
    check_stage(FidelityBoundary.MARKDOWN, blocks, read_markdown(written))
