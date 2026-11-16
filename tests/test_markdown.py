"""Tests of the markdown stage: escaping, rendering and run (spec section 8)."""

import hashlib
import json
import re
import shutil
import string
import subprocess
import xml.etree.ElementTree as ET
import zipfile
from collections import defaultdict
from dataclasses import replace
from pathlib import Path

import pytest

from galley import epub, markdown
from galley.book_folder import BookFolder
from galley.config import BookConfig, Language
from galley.errors import (
    EditError,
    ExternalProgramError,
    FidelityBoundary,
    FidelityError,
    InputFileError,
)
from galley.fidelity import check_stage, read_markdown
from galley.markdown import escape_markdown, render_markdown
from galley.model import (
    Block,
    BlockKind,
    BlocksFile,
    Box,
    Edit,
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
    write_edits,
    write_pages,
)

_PDF_BYTES = b"%PDF-1.4 a stand-in: markdown reads only its hash"
SOURCE_PDF_SHA256 = hashlib.sha256(_PDF_BYTES).hexdigest()
OTHER_PDF_SHA256 = "b" * 64

CONFIG = BookConfig(
    pdf=Path("/books/gierke.pdf"),
    title="Political Theories of the Middle Age",
    authors=("O. Gierke", "F. W. Maitland"),
    language=Language.EN,
)


# escape_markdown


@pytest.mark.parametrize(
    ("text", "escaped"),
    [
        ("*x*", "\\*x\\*"),
        ("1. Of", "1\\. Of"),
        ("« — »", "« — »"),
        ("ab\rcd", "ab cd"),
        ("ab\tcd", "ab cd"),
        ("ab\x0bcd\x0c\x1c\x1d\x1e\x1fef", "ab cd     ef"),
        ("\x0b\x0c\x1c\x1fab\x1d", "ab"),
        ("\tab", "ab"),
        ("    ab", "ab"),
        ("ab\n\n    cd\t", "ab      cd"),
    ],
)
def test_escape_markdown_escapes_punctuation_and_plains_white_space(
    text: str, escaped: str
) -> None:
    assert escape_markdown(text) == escaped


def test_escape_markdown_puts_a_backslash_before_each_ascii_punctuation() -> None:
    assert escape_markdown(string.punctuation) == (
        "\\!\\\"\\#\\$\\%\\&\\'\\(\\)\\*\\+\\,\\-\\.\\/\\:\\;\\<\\=\\>"
        "\\?\\@\\[\\\\\\]\\^\\_\\`\\{\\|\\}\\~"
    )


def _div(block_id: str, text: str) -> str:
    return f"::: {{#{block_id}}}\n{escape_markdown(text)}\n:::\n"


@pytest.mark.pandoc
def test_escaped_ascii_punctuation_reads_back_as_written() -> None:
    text = f"{string.punctuation} a{string.punctuation}b"

    words = read_markdown(_div("b-p0000-001", text)).words

    assert tuple(word.text for word in words) == tuple(text.split())


# Words that Pandoc's Markdown would read as something else unescaped.
MARKDOWN_LIKE_TEXTS = (
    "jj^J^jjJJ",
    "H~2~O",
    "a\\\\b",
    "# 1 Of",
    "see @doe",
    "*x*",
    "_x_",
    "`x`",
    "[x](y)",
    "$x$",
    "<i>x</i>",
    "<!--x-->",
    "{x}",
    "|a|b|",
)


def _words_by_block(document: str) -> dict[str | None, list[str]]:
    read_back: defaultdict[str | None, list[str]] = defaultdict(list)
    for word in read_markdown(document).words:
        read_back[word.block_id].append(word.text)
    return dict(read_back)


@pytest.mark.pandoc
def test_markdown_like_words_read_back_as_written() -> None:
    document = "\n".join(
        _div(f"case-{position}", text)
        for position, text in enumerate(MARKDOWN_LIKE_TEXTS)
    )

    assert _words_by_block(document) == {
        f"case-{position}": text.split()
        for position, text in enumerate(MARKDOWN_LIKE_TEXTS)
    }


# Every character str.split() splits at, and every C0 and C1 control
# character, which Pandoc might drop or read as layout.
WHITE_SPACE = tuple(chr(code) for code in range(0x3001) if chr(code).isspace())
CONTROL = tuple(
    chr(code)
    for code in (*range(0x20), 0x7F, *range(0x80, 0xA0))
    if not chr(code).isspace()
)
WHITE_SPACE_TEXTS = (
    *(
        text
        for character in WHITE_SPACE + CONTROL
        for text in (
            f"ab{character}cd",
            f"{character}ab cd",
            f"{character * 4}ab cd",
        )
    ),
    "ab\r\rcd",
    "ab\n\n    cd",
    "ab\n\n\tcd",
    "ab\n \n    cd",
    "ab\r\n\r\n    cd",
    " \tab",
)


@pytest.mark.pandoc
def test_white_space_and_control_characters_keep_every_word() -> None:
    # One div per text, so that one run of Pandoc reads them all.
    document = "\n".join(
        _div(f"case-{position}", text)
        for position, text in enumerate(WHITE_SPACE_TEXTS)
    )

    read_back = _words_by_block(document)

    assert len(WHITE_SPACE) == 29
    assert len(CONTROL) == 55
    assert {
        f"case-{position}": text.split()
        for position, text in enumerate(WHITE_SPACE_TEXTS)
    } == read_back


# render_markdown


def _paragraph(block_id: str, *texts: str, note_ref: str | None = None) -> Block:
    return Block(
        id=block_id,
        kind=BlockKind.PARAGRAPH,
        level=None,
        label=None,
        spans=tuple(Span(text, Emphasis.NONE, note_ref) for text in texts),
        figure=None,
        origin=(Origin(0, Box(10.0, 20.0, 300.0, 400.0)),),
    )


def _blocks_file(
    blocks: tuple[Block, ...],
    notes: tuple[Note, ...] = (),
    source_pdf_sha256: str = SOURCE_PDF_SHA256,
) -> BlocksFile:
    return BlocksFile(
        source_pdf_sha256=source_pdf_sha256,
        blocks=blocks,
        notes=notes,
        removals=(),
        word_changes=(),
        page_numbers=(),
    )


TWO_PARAGRAPHS = _blocks_file(
    (
        _paragraph("b-p0000-001", "POLITICAL THEORIES ", "OF THE MIDDLE AGE*"),
        _paragraph("b-p0001-001", "1. Of the «three» — [sic]"),
    )
)

TWO_PARAGRAPHS_MARKDOWN = """\
---
title: "Political Theories of the Middle Age"
author:
- "O\\\\. Gierke"
- "F\\\\. W\\\\. Maitland"
lang: en
---

::: {#b-p0000-001}
POLITICAL THEORIES OF THE MIDDLE AGE\\*
:::

::: {#b-p0001-001}
1\\. Of the «three» — \\[sic\\]
:::
"""


def test_render_markdown_writes_the_header_and_one_div_per_block() -> None:
    assert render_markdown(TWO_PARAGRAPHS, CONFIG) == TWO_PARAGRAPHS_MARKDOWN


def test_render_markdown_writes_title_and_authors_as_json_strings() -> None:
    config = BookConfig(
        pdf=CONFIG.pdf,
        title='The "Battle" of Kadesh: a study',
        authors=("J. H. Breasted",),
        language=Language.DE,
    )

    assert render_markdown(_blocks_file(()), config).startswith(
        "---\n"
        'title: "The \\\\\\"Battle\\\\\\" of Kadesh\\\\: a study"\n'
        "author:\n"
        '- "J\\\\. H\\\\. Breasted"\n'
        "lang: de\n"
        "---\n"
    )


NOTE = Note(
    id="n-p0000-001",
    kind=NoteKind.FOOTNOTE,
    marker="1",
    blocks=(_paragraph("b-p0000-002", "A note."),),
    origin=(Origin(0, Box(10.0, 500.0, 300.0, 520.0)),),
    referenced=True,
)


def _block_of_kind(block_id: str, kind: BlockKind) -> Block:
    return replace(_paragraph(block_id, "Chapter one"), kind=kind)


FIGURE = replace(
    _paragraph("b-p0016-001", "PLATE I. The battle."), kind=BlockKind.FIGURE
)


def _referring(block_id: str, before: str, reference: str, note_id: str) -> Block:
    """A paragraph of `before` and a reference span of `reference` to the
    note `note_id`, on the page of its id."""
    page_index = int(block_id[3:7])
    return Block(
        id=block_id,
        kind=BlockKind.PARAGRAPH,
        level=None,
        label=None,
        spans=(
            Span(before, Emphasis.NONE, None),
            Span(reference, Emphasis.NONE, note_id),
        ),
        figure=None,
        origin=(Origin(page_index, Box(10.0, 20.0, 300.0, 400.0)),),
    )


@pytest.mark.parametrize(
    ("blocks", "named"),
    [
        (
            _blocks_file((replace(FIGURE, figure="images/p0016.png"),)),
            "block b-p0016-001 is a figure with the image images/p0016.png",
        ),
        (
            _blocks_file(
                (),
                (
                    replace(
                        NOTE,
                        referenced=False,
                        blocks=(_block_of_kind("b-p0000-005", BlockKind.HEADING),),
                    ),
                ),
            ),
            "block b-p0000-005 of note n-p0000-001 is a heading",
        ),
        (
            _blocks_file(
                (_referring("b-p0000-003", "Greece,", "1", "n-p0000-001"),),
                (
                    replace(
                        NOTE,
                        blocks=(
                            _referring("b-p0000-002", "Ibid.", "2", "n-p0000-009"),
                        ),
                    ),
                    replace(NOTE, id="n-p0000-009", blocks=(FIGURE,)),
                ),
            ),
            (
                "block b-p0000-002 of footnote n-p0000-001 refers to footnote "
                "n-p0000-009, and Pandoc cannot put a footnote in a footnote"
            ),
        ),
    ],
    ids=["figure with an image", "heading in a note", "footnote in a footnote"],
)
def test_render_markdown_refuses_what_it_does_not_write(
    blocks: BlocksFile, named: str
) -> None:
    with pytest.raises(
        InputFileError,
        match=f"blocks.json holds what markdown does not write: .*{re.escape(named)}",
    ):
        render_markdown(blocks, CONFIG)


@pytest.mark.parametrize(
    ("blocks", "problem"),
    [
        (
            _blocks_file((_referring("b-p0000-003", "Greece,", "1", "n-p0000-001"),)),
            "block b-p0000-003 refers to n-p0000-001, which is no note",
        ),
        (
            _blocks_file((_paragraph("b-p0000-001", "Text."),), (NOTE,)),
            "note n-p0000-001 is referenced and no block refers to it",
        ),
        (
            _blocks_file(
                (_referring("b-p0000-003", "Law", "1", "n-p0000-001"),),
                (replace(NOTE, kind=NoteKind.ENDNOTE, referenced=False),),
            ),
            "note n-p0000-001 is not referenced and a block refers to it",
        ),
        (
            _blocks_file(
                (
                    _referring("b-p0000-003", "Greece,", "1", "n-p0000-001"),
                    _referring("b-p0000-004", "Rome,", "1", "n-p0000-001"),
                ),
                (NOTE,),
            ),
            "footnote n-p0000-001 is referenced 2 times",
        ),
    ],
    ids=[
        "reference to no note",
        "referenced footnote without a reference",
        "unreferenced endnote with a reference",
        "footnote referenced twice",
    ],
)
def test_render_markdown_refuses_a_note_reference_that_disagrees_with_the_notes(
    blocks: BlocksFile, problem: str
) -> None:
    with pytest.raises(
        InputFileError, match=f"blocks.json is malformed: .*{re.escape(problem)}"
    ):
        render_markdown(blocks, CONFIG)


@pytest.mark.parametrize(
    ("note", "problem"),
    [
        (replace(NOTE, referenced=False, blocks=()), "has no blocks"),
        (replace(NOTE, referenced=False, origin=()), "has no origin"),
    ],
    ids=["without blocks", "without origin"],
)
def test_render_markdown_refuses_a_note_without_blocks_or_origin_as_malformed(
    note: Note, problem: str
) -> None:
    with pytest.raises(
        InputFileError,
        match=f"blocks.json is malformed: note n-p0000-001 {problem}",
    ):
        render_markdown(_blocks_file((), (note,)), CONFIG)


# Structure spec section 10, option (b): margin notes and notes with
# `referenced` false.


def _block(block_id: str, kind: BlockKind, text: str, *page_indices: int) -> Block:
    """A block of one span on the pages given, one origin each."""
    return Block(
        id=block_id,
        kind=kind,
        level=None,
        label=None,
        spans=(Span(text, Emphasis.NONE, None),),
        figure=None,
        origin=tuple(
            Origin(page_index, Box(10.0, 20.0, 300.0, 400.0))
            for page_index in page_indices
        ),
    )


def _unreferenced_note(
    note_id: str, page_index: int, *blocks: Block, marker: str = ""
) -> Note:
    return Note(
        id=note_id,
        kind=NoteKind.FOOTNOTE,
        marker=marker,
        blocks=blocks,
        origin=(Origin(page_index, Box(10.0, 500.0, 300.0, 520.0)),),
        referenced=False,
    )


HEADER = """\
---
title: "Political Theories of the Middle Age"
author:
- "O\\\\. Gierke"
- "F\\\\. W\\\\. Maitland"
lang: en
---
"""

# Page 3 holds a paragraph and the start of one that runs on to page 4,
# where the body ends; page 4 has a margin note; each page has a note.
SIDE_TEXT = _blocks_file(
    (
        _block("b-p0003-001", BlockKind.PARAGRAPH, "First paragraph.", 3),
        _block("b-p0003-002", BlockKind.PARAGRAPH, "runs over the page.", 3, 4),
        _block("b-p0004-001", BlockKind.MARGIN_NOTE, "Of kings.", 4),
        _block("b-p0005-001", BlockKind.PARAGRAPH, "Last.", 5),
    ),
    (
        _unreferenced_note(
            "n-p0003-001",
            3,
            _block("b-p0003-003", BlockKind.PARAGRAPH, "A note of page three.", 3),
            marker="*",
        ),
        _unreferenced_note(
            "n-p0004-001",
            4,
            _block("b-p0004-002", BlockKind.PARAGRAPH, "A note,", 4),
            _block("b-p0004-003", BlockKind.PARAGRAPH, "in two paragraphs.", 4),
        ),
    ),
)

SIDE_TEXT_MARKDOWN = (
    HEADER
    + """
::: {#b-p0003-001}
First paragraph\\.
:::

::: {#b-p0003-002}
runs over the page\\.
:::

:::: {#n-p0003-001 .note}
::: {#b-p0003-003}
\\* A note of page three\\.
:::
::::

::: {#b-p0004-001 .margin-note}
Of kings\\.
:::

:::: {#n-p0004-001 .note}
::: {#b-p0004-002}
A note\\,
:::

::: {#b-p0004-003}
in two paragraphs\\.
:::
::::

::: {#b-p0005-001}
Last\\.
:::
"""
)


def test_render_markdown_writes_margin_notes_where_they_are_and_notes_after_their_page() -> (
    None
):
    assert render_markdown(SIDE_TEXT, CONFIG) == SIDE_TEXT_MARKDOWN


def _ids_in_order(markdown_text: str) -> tuple[str, ...]:
    """The ids of the divs, in the order their fences open."""
    return tuple(
        line.split("{#", 1)[1].split()[0].rstrip("}")
        for line in markdown_text.splitlines()
        if line.startswith(":::") and "{#" in line
    )


def test_notes_of_a_page_follow_the_side_text_of_the_page_before() -> None:
    # A paragraph runs from page 3 to page 4; page 3's margin note follows it.
    blocks = _blocks_file(
        (
            _block("b-p0003-001", BlockKind.PARAGRAPH, "Runs over.", 3, 4),
            _block("b-p0003-002", BlockKind.MARGIN_NOTE, "Of page three.", 3),
            _block("b-p0005-001", BlockKind.PARAGRAPH, "Page five.", 5),
        ),
        (
            _unreferenced_note(
                "n-p0003-001",
                3,
                _block("b-p0003-003", BlockKind.PARAGRAPH, "Note three.", 3),
            ),
            _unreferenced_note(
                "n-p0004-001",
                4,
                _block("b-p0004-001", BlockKind.PARAGRAPH, "Note four.", 4),
            ),
        ),
    )

    assert _ids_in_order(render_markdown(blocks, CONFIG)) == (
        "b-p0003-001",
        "b-p0003-002",
        "n-p0003-001",
        "b-p0003-003",
        "n-p0004-001",
        "b-p0004-001",
        "b-p0005-001",
    )


def test_a_note_follows_the_last_block_in_blocks_order_that_starts_on_its_page_or_before() -> (
    None
):
    blocks = _blocks_file(
        (
            _block("b-p0002-001", BlockKind.PARAGRAPH, "Page two.", 2),
            _block("b-p0003-001", BlockKind.PARAGRAPH, "Page three.", 3),
            _block("b-p0006-001", BlockKind.PARAGRAPH, "Page six.", 6),
            # Its first origin is on page 2, though it comes after page 6.
            _block("b-p0002-002", BlockKind.MARGIN_NOTE, "Out of order.", 2),
        ),
        (
            _unreferenced_note(
                "n-p0004-001",
                4,
                _block("b-p0004-001", BlockKind.PARAGRAPH, "Page four.", 4),
            ),
        ),
    )

    assert _ids_in_order(render_markdown(blocks, CONFIG)) == (
        "b-p0002-001",
        "b-p0003-001",
        "b-p0006-001",
        "b-p0002-002",
        "n-p0004-001",
        "b-p0004-001",
    )


def test_a_note_before_every_page_of_the_blocks_comes_first_of_all() -> None:
    blocks = _blocks_file(
        (_block("b-p0002-001", BlockKind.PARAGRAPH, "Page two.", 2),),
        (
            _unreferenced_note(
                "n-p0001-001",
                1,
                _block("b-p0001-001", BlockKind.PARAGRAPH, "Page one.", 1),
            ),
        ),
    )

    assert _ids_in_order(render_markdown(blocks, CONFIG)) == (
        "n-p0001-001",
        "b-p0001-001",
        "b-p0002-001",
    )


def test_notes_after_the_same_block_keep_their_order() -> None:
    blocks = _blocks_file(
        (
            _block("b-p0001-001", BlockKind.PARAGRAPH, "Page one.", 1),
            _block("b-p0002-001", BlockKind.PARAGRAPH, "Page two.", 2),
        ),
        tuple(
            _unreferenced_note(
                f"n-p0001-00{position}",
                1,
                _block(f"b-p0001-00{position + 1}", BlockKind.PARAGRAPH, "A note.", 1),
            )
            for position in (1, 2, 3)
        ),
    )

    assert _ids_in_order(render_markdown(blocks, CONFIG)) == (
        "b-p0001-001",
        "n-p0001-001",
        "b-p0001-002",
        "n-p0001-002",
        "b-p0001-003",
        "n-p0001-003",
        "b-p0001-004",
        "b-p0002-001",
    )


@pytest.mark.pandoc
def test_pandoc_reads_margin_notes_and_notes_in_their_divs() -> None:
    assert _words_by_block(SIDE_TEXT_MARKDOWN) == {
        "b-p0003-001": ["First", "paragraph."],
        "b-p0003-002": ["runs", "over", "the", "page."],
        "b-p0003-003": ["*", "A", "note", "of", "page", "three."],
        "b-p0004-001": ["Of", "kings."],
        "b-p0004-002": ["A", "note,"],
        "b-p0004-003": ["in", "two", "paragraphs."],
        "b-p0005-001": ["Last."],
    }


@pytest.mark.pandoc
def test_fidelity_check_passes_on_margin_notes_and_notes() -> None:
    check_stage(FidelityBoundary.MARKDOWN, SIDE_TEXT, read_markdown(SIDE_TEXT_MARKDOWN))


@pytest.mark.pandoc
@pytest.mark.parametrize(
    ("written", "damaged", "lost"),
    [
        ("\\* A note", "A note", "*"),
        ("page three", "page", "three."),
        ("Of kings", "Of", "kings."),
    ],
    ids=["marker", "note word", "margin note word"],
)
def test_fidelity_check_finds_a_word_lost_from_a_note_or_margin_note(
    written: str, damaged: str, lost: str
) -> None:
    markdown_text = SIDE_TEXT_MARKDOWN.replace(written, damaged, 1)

    with pytest.raises(FidelityError) as raised:
        check_stage(FidelityBoundary.MARKDOWN, SIDE_TEXT, read_markdown(markdown_text))

    assert lost in raised.value.missing


# Structure spec section 19 and the module's docstring: how each kind is
# written.


def _heading(block_id: str, level: int | None, label: str | None, title: str) -> Block:
    return replace(
        _block(block_id, BlockKind.HEADING, title, 2), level=level, label=label
    )


@pytest.mark.parametrize(
    ("heading", "written"),
    [
        (
            _heading("b-p0002-001", 1, "CHAPTER III.", "THE EARLY YEARS."),
            "# [CHAPTER III\\.]{.label} THE EARLY YEARS\\. {#b-p0002-001}\n",
        ),
        (
            _heading("b-p0002-001", 2, None, "BIBLIOGRAPHICAL NOTE"),
            "## BIBLIOGRAPHICAL NOTE {#b-p0002-001}\n",
        ),
        (
            _heading("b-p0002-001", 1, "V", ""),
            "# [V]{.label} {#b-p0002-001}\n",
        ),
    ],
    ids=["with a label", "level 2 without a label", "label without a title"],
)
def test_a_heading_is_written_at_its_level_with_its_label_as_a_span(
    heading: Block, written: str
) -> None:
    assert render_markdown(_blocks_file((heading,)), CONFIG) == HEADER + "\n" + written


@pytest.mark.parametrize("level", [None, 0, 7])
def test_a_heading_without_a_level_from_1_to_6_is_malformed(level: int | None) -> None:
    heading = _heading("b-p0002-001", level, None, "Title")

    with pytest.raises(
        InputFileError,
        match=f"blocks.json is malformed: heading b-p0002-001 has the level {level}",
    ):
        render_markdown(_blocks_file((heading,)), CONFIG)


@pytest.mark.parametrize(
    ("kind", "class_name"),
    [
        (BlockKind.QUOTE, "quote"),
        (BlockKind.CHAPTER_SUMMARY, "chapter-summary"),
        (BlockKind.INDEX_ENTRY, "index-entry"),
        (BlockKind.FIGURE, "figure"),
        (BlockKind.MARGIN_NOTE, "margin-note"),
    ],
)
def test_quote_chapter_summary_index_entry_figure_and_margin_note_have_a_class_of_their_kind(
    kind: BlockKind, class_name: str
) -> None:
    block = _block("b-p0002-001", kind, "Henry's youth. — His accession.", 2)

    assert render_markdown(_blocks_file((block,)), CONFIG) == (
        HEADER
        + f"\n::: {{#b-p0002-001 .{class_name}}}\n"
        + "Henry\\'s youth\\. — His accession\\.\n:::\n"
    )


@pytest.mark.parametrize(
    ("text", "written"),
    [
        (
            "Mignonne, allons voir\nsi la rose,\n* qui ce matin",
            "Mignonne\\, allons voir\\\nsi la rose\\,\\\n\\* qui ce matin",
        ),
        (
            "First line,\nsecond.\n\n  \nStanza two\nends.\n",
            "First line\\,\\\nsecond\\.\n\nStanza two\\\nends\\.",
        ),
        ("  one\tline  \r\n    two", "one line\\\ntwo"),
    ],
    ids=["lines", "stanzas", "white space"],
)
def test_verse_ends_each_line_with_a_hard_line_break_and_a_stanza_with_a_blank_line(
    text: str, written: str
) -> None:
    verse = _block("b-p0002-001", BlockKind.VERSE, text, 2)

    assert render_markdown(_blocks_file((verse,)), CONFIG) == (
        HEADER + f"\n::: {{#b-p0002-001 .verse}}\n{written}\n:::\n"
    )


EVERY_KIND = _blocks_file(
    (
        _heading("b-p0002-001", 1, "CHAPTER III.", "THE EARLY YEARS OF HENRY II."),
        _block(
            "b-p0002-002",
            BlockKind.CHAPTER_SUMMARY,
            "Henry's youth. — His accession.",
            2,
        ),
        _block("b-p0002-003", BlockKind.MARGIN_NOTE, "Of kings.", 2),
        _block("b-p0002-004", BlockKind.PARAGRAPH, "1. Of the three estates.", 2),
        _block("b-p0002-005", BlockKind.QUOTE, '"Rex in regno suo."', 2),
        _block(
            "b-p0002-006",
            BlockKind.VERSE,
            "Mignonne, allons voir\nsi la rose,\n\n# qui ce matin\\",
            2,
        ),
        _heading("b-p0003-001", 2, None, "INDEX"),
        _block("b-p0003-002", BlockKind.INDEX_ENTRY, "Aachen, 12, 34-36.", 3),
        _block("b-p0003-003", BlockKind.FIGURE, "PLATE I. The battle.", 3),
    )
)


@pytest.mark.pandoc
def test_pandoc_reads_every_kind_and_the_label_in_their_blocks() -> None:
    assert _words_by_block(render_markdown(EVERY_KIND, CONFIG)) == {
        "b-p0002-001": [
            "CHAPTER",
            "III.",
            "THE",
            "EARLY",
            "YEARS",
            "OF",
            "HENRY",
            "II.",
        ],
        "b-p0002-002": ["Henry's", "youth.", "—", "His", "accession."],
        "b-p0002-003": ["Of", "kings."],
        "b-p0002-004": ["1.", "Of", "the", "three", "estates."],
        "b-p0002-005": ['"Rex', "in", "regno", 'suo."'],
        "b-p0002-006": ["Mignonne,", "allons", "voir", "si", "la", "rose,"]
        + ["#", "qui", "ce", "matin\\"],
        "b-p0003-001": ["INDEX"],
        "b-p0003-002": ["Aachen,", "12,", "34-36."],
        "b-p0003-003": ["PLATE", "I.", "The", "battle."],
    }


def _pandoc_blocks(markdown_text: str) -> object:
    """The blocks of Pandoc's JSON of a Markdown text."""
    pandoc = shutil.which("pandoc")
    assert pandoc is not None
    completed = subprocess.run(
        [pandoc, "--from", "markdown-smart-auto_identifiers", "--to", "json"],
        input=markdown_text,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
        timeout=60,
    )
    return json.loads(completed.stdout)["blocks"]


@pytest.mark.pandoc
def test_pandoc_reads_a_verse_as_one_paragraph_a_stanza_with_a_line_break_a_line() -> (
    None
):
    verse = _block("b-p0002-001", BlockKind.VERSE, "One,\ntwo.\n\nThree", 2)

    match _pandoc_blocks(render_markdown(_blocks_file((verse,)), CONFIG)):
        case [
            {
                "t": "Div",
                "c": [
                    ["b-p0002-001", ["verse"], []],
                    [
                        {
                            "t": "Para",
                            "c": [{"t": "Str"}, {"t": "LineBreak"}, {"t": "Str"}],
                        },
                        {"t": "Para", "c": [{"t": "Str"}]},
                    ],
                ],
            }
        ]:
            pass
        case blocks:
            pytest.fail(f"not one verse div of two stanzas: {blocks}")


@pytest.mark.pandoc
def test_pandoc_reads_a_level_2_heading_with_its_label_in_a_label_span() -> None:
    heading = _heading("b-p0002-001", 2, "CHAPTER III.", "THE EARLY YEARS.")

    match _pandoc_blocks(render_markdown(_blocks_file((heading,)), CONFIG)):
        case [
            {
                "t": "Header",
                "c": [
                    2,
                    ["b-p0002-001", [], []],
                    [{"t": "Span", "c": [["", ["label"], []], _]}, *_],
                ],
            }
        ]:
            pass
        case blocks:
            pytest.fail(f"not one heading with a label span: {blocks}")


@pytest.mark.pandoc
def test_fidelity_check_passes_on_every_kind_with_a_heading_label() -> None:
    check_stage(
        FidelityBoundary.MARKDOWN,
        EVERY_KIND,
        read_markdown(render_markdown(EVERY_KIND, CONFIG)),
    )


@pytest.mark.pandoc
@pytest.mark.parametrize(
    ("written", "damaged", "lost"),
    [
        ("[CHAPTER III\\.]{.label}", "[CHAPTER]{.label}", "III."),
        ("allons voir\\\n", "allons\\\n", "voir"),
        ("Henry\\'s youth", "youth", "Henry's"),
    ],
    ids=["label", "verse", "chapter_summary"],
)
def test_fidelity_check_finds_a_word_lost_from_a_label_verse_or_chapter_summary(
    written: str, damaged: str, lost: str
) -> None:
    markdown_text = render_markdown(EVERY_KIND, CONFIG)
    assert written in markdown_text

    with pytest.raises(FidelityError) as raised:
        check_stage(
            FidelityBoundary.MARKDOWN,
            EVERY_KIND,
            read_markdown(markdown_text.replace(written, damaged, 1)),
        )

    assert lost in raised.value.missing


def test_render_markdown_refuses_a_label_with_a_character_xml_does_not_allow() -> None:
    heading = _heading("b-p0002-001", 1, "CHAPTER￾", "Title")

    with pytest.raises(
        InputFileError, match=r"blocks.json.*label of block b-p0002-001.*U\+FFFE"
    ):
        render_markdown(_blocks_file((heading,)), CONFIG)


# Structure spec section 19: referenced footnotes as Pandoc footnotes,
# endnotes as one list where they were printed.


def _note(
    note_id: str,
    kind: NoteKind,
    marker: str,
    *blocks: Block,
    referenced: bool,
) -> Note:
    page_index = int(note_id[3:7])
    return Note(
        id=note_id,
        kind=kind,
        marker=marker,
        blocks=blocks,
        origin=(Origin(page_index, Box(10.0, 500.0, 300.0, 520.0)),),
        referenced=referenced,
    )


# Page 5 refers to a footnote, with a margin note beside it, and to an
# endnote; page 9 holds the endnotes after their heading, the first with a
# margin note, the second unreferenced; page 10 a paragraph after them.
NOTES = _blocks_file(
    (
        _referring("b-p0005-001", "Of Greece,", "1", "n-p0005-001"),
        _referring("b-p0005-002", "The Law", "3", "n-p0009-001"),
        replace(_block("b-p0009-001", BlockKind.HEADING, "NOTES.", 9), level=1),
        _block("b-p0010-001", BlockKind.PARAGRAPH, "After.", 10),
    ),
    (
        _note(
            "n-p0005-001",
            NoteKind.FOOTNOTE,
            "1",
            _block("b-p0005-003", BlockKind.MARGIN_NOTE, "Greek law.", 5),
            _block("b-p0005-004", BlockKind.PARAGRAPH, "See Plato.", 5),
            referenced=True,
        ),
        _note(
            "n-p0009-001",
            NoteKind.ENDNOTE,
            "3.",
            _block("b-p0009-002", BlockKind.MARGIN_NOTE, "Roman law.", 9),
            _block("b-p0009-003", BlockKind.PARAGRAPH, "Digest, 1.", 9),
            _block("b-p0009-004", BlockKind.QUOTE, "Quod principi placuit.", 9),
            referenced=True,
        ),
        _note(
            "n-p0009-002",
            NoteKind.ENDNOTE,
            "4.",
            _block("b-p0009-005", BlockKind.PARAGRAPH, "Code, 2.", 9),
            referenced=False,
        ),
    ),
)

NOTES_MARKDOWN = (
    HEADER
    + """
::: {#b-p0005-001}
Of Greece\\,[^n-p0005-001]
:::

[^n-p0005-001]:
    ::: {#b-p0005-003 .margin-note}
    Greek law\\.
    :::

    ::: {#b-p0005-004}
    See Plato\\.
    :::

::: {#b-p0005-002}
The Law[3](#n-p0009-001){epub:type="noteref"}
:::

# NOTES\\. {#b-p0009-001}

::::: {.endnotes}
:::: {#n-p0009-001 .endnote}
::: {#b-p0009-002 .margin-note}
Roman law\\.
:::

::: {#b-p0009-003}
3\\. Digest\\, 1\\.
:::

::: {#b-p0009-004 .quote}
Quod principi placuit\\.
:::
::::

:::: {#n-p0009-002 .endnote}
::: {#b-p0009-005}
4\\. Code\\, 2\\.
:::
::::
:::::

::: {#b-p0010-001}
After\\.
:::
"""
)


def test_footnote_at_its_reference_and_endnotes_as_one_list_with_a_noteref_link() -> (
    None
):
    assert render_markdown(NOTES, CONFIG) == NOTES_MARKDOWN


def test_a_footnote_referred_to_from_an_endnote_is_defined_after_the_endnote_list() -> (
    None
):
    blocks = _blocks_file(
        (_block("b-p0009-001", BlockKind.PARAGRAPH, "NOTES.", 9),),
        (
            _note(
                "n-p0009-001",
                NoteKind.ENDNOTE,
                "",
                _referring("b-p0009-002", "Ibid.", "*", "n-p0009-002"),
                referenced=False,
            ),
            _note(
                "n-p0009-002",
                NoteKind.FOOTNOTE,
                "*",
                _block("b-p0009-003", BlockKind.PARAGRAPH, "A footnote.", 9),
                referenced=True,
            ),
        ),
    )

    assert render_markdown(blocks, CONFIG) == (
        HEADER
        + """
::: {#b-p0009-001}
NOTES\\.
:::

::::: {.endnotes}
:::: {#n-p0009-001 .endnote}
::: {#b-p0009-002}
Ibid\\.[^n-p0009-002]
:::
::::
:::::

[^n-p0009-002]:
    ::: {#b-p0009-003}
    A footnote\\.
    :::
"""
    )


def test_a_footnote_reference_in_verse_stays_on_its_line_and_its_verse_lines_are_indented() -> (
    None
):
    verse = replace(
        _block("b-p0005-001", BlockKind.VERSE, "", 5),
        spans=(
            Span("Arma virumque\ncano,", Emphasis.NONE, None),
            Span("1", Emphasis.NONE, "n-p0005-001"),
            Span("\nTroiae", Emphasis.NONE, None),
        ),
    )
    note = _note(
        "n-p0005-001",
        NoteKind.FOOTNOTE,
        "1",
        _block("b-p0005-002", BlockKind.VERSE, "Virgil,\nAeneid.", 5),
        referenced=True,
    )

    assert render_markdown(_blocks_file((verse,), (note,)), CONFIG) == (
        HEADER
        + """
::: {#b-p0005-001 .verse}
Arma virumque\\
cano\\,[^n-p0005-001]\\
Troiae
:::

[^n-p0005-001]:
    ::: {#b-p0005-002 .verse}
    Virgil\\,\\
    Aeneid\\.
    :::
"""
    )


def test_an_unreferenced_footnote_writes_its_marker_after_its_margin_note() -> None:
    note = _note(
        "n-p0003-001",
        NoteKind.FOOTNOTE,
        "*",
        _block("b-p0003-002", BlockKind.MARGIN_NOTE, "Of kings.", 3),
        _block("b-p0003-003", BlockKind.PARAGRAPH, "A note.", 3),
        referenced=False,
    )

    assert render_markdown(_blocks_file((), (note,)), CONFIG) == (
        HEADER
        + """
:::: {#n-p0003-001 .note}
::: {#b-p0003-002 .margin-note}
Of kings\\.
:::

::: {#b-p0003-003}
\\* A note\\.
:::
::::
"""
    )


def test_an_endnote_of_margin_notes_only_writes_its_marker_in_the_first() -> None:
    note = _note(
        "n-p0009-001",
        NoteKind.ENDNOTE,
        "7.",
        _block("b-p0009-002", BlockKind.MARGIN_NOTE, "Of kings.", 9),
        referenced=False,
    )

    assert "::: {#b-p0009-002 .margin-note}\n7\\. Of kings\\.\n:::" in (
        render_markdown(_blocks_file((), (note,)), CONFIG)
    )


def test_endnotes_with_a_body_block_between_them_are_two_lists() -> None:
    blocks = _blocks_file(
        (
            _block("b-p0009-001", BlockKind.PARAGRAPH, "Notes of chapter one.", 9),
            _block("b-p0010-001", BlockKind.PARAGRAPH, "Notes of chapter two.", 10),
        ),
        (
            _note(
                "n-p0009-001",
                NoteKind.ENDNOTE,
                "1.",
                _block("b-p0009-002", BlockKind.PARAGRAPH, "One.", 9),
                referenced=False,
            ),
            _note(
                "n-p0010-001",
                NoteKind.ENDNOTE,
                "1.",
                _block("b-p0010-002", BlockKind.PARAGRAPH, "Two.", 10),
                referenced=False,
            ),
        ),
    )

    written = render_markdown(blocks, CONFIG)

    assert written.count("::::: {.endnotes}") == 2
    assert _ids_in_order(written) == (
        "b-p0009-001",
        "n-p0009-001",
        "b-p0009-002",
        "b-p0010-001",
        "n-p0010-001",
        "b-p0010-002",
    )


@pytest.mark.pandoc
def test_pandoc_reads_one_footnote_one_noteref_link_and_every_word_in_its_block() -> (
    None
):
    read = read_markdown(NOTES_MARKDOWN)

    assert (read.note_count, read.note_link_count) == (1, 1)
    assert _words_by_block(NOTES_MARKDOWN) == {
        "b-p0005-001": ["Of", "Greece,"],
        "b-p0005-003": ["Greek", "law."],
        "b-p0005-004": ["See", "Plato."],
        "b-p0005-002": ["The", "Law", "3"],
        "b-p0009-001": ["NOTES."],
        "b-p0009-002": ["Roman", "law."],
        "b-p0009-003": ["3.", "Digest,", "1."],
        "b-p0009-004": ["Quod", "principi", "placuit."],
        "b-p0009-005": ["4.", "Code,", "2."],
        "b-p0010-001": ["After."],
    }


@pytest.mark.pandoc
def test_fidelity_check_passes_on_a_footnote_and_endnotes() -> None:
    check_stage(FidelityBoundary.MARKDOWN, NOTES, read_markdown(NOTES_MARKDOWN))


@pytest.mark.pandoc
@pytest.mark.parametrize(
    ("written", "damaged", "lost"),
    [
        ("    See Plato\\.", "    See", "Plato."),
        ("Law[3](#n-p0009-001)", "Law[](#n-p0009-001)", "3"),
        ("3\\. Digest", "Digest", "3."),
        ("    Greek law\\.", "    Greek", "law."),
    ],
    ids=[
        "footnote word",
        "endnote reference",
        "endnote marker",
        "margin note in a footnote",
    ],
)
def test_fidelity_check_finds_a_word_lost_from_a_footnote_or_endnote(
    written: str, damaged: str, lost: str
) -> None:
    assert written in NOTES_MARKDOWN

    with pytest.raises(FidelityError) as raised:
        check_stage(
            FidelityBoundary.MARKDOWN,
            NOTES,
            read_markdown(NOTES_MARKDOWN.replace(written, damaged, 1)),
        )

    assert lost in raised.value.missing


@pytest.mark.pandoc
def test_fidelity_check_finds_an_endnote_reference_written_as_a_plain_link() -> None:
    markdown_text = NOTES_MARKDOWN.replace('{epub:type="noteref"}', "", 1)

    with pytest.raises(ExternalProgramError, match="Link element in block b-p0005-002"):
        read_markdown(markdown_text)


# Spec section 8: XML 1.0 does not allow these, and Pandoc copies them into
# the EPUB's XHTML.
@pytest.mark.parametrize(
    ("character", "code_point"),
    [
        ("\x00", "U+0000"),
        ("\x08", "U+0008"),
        ("\x0e", "U+000E"),
        ("\x1b", "U+001B"),
        ("\ufffe", "U+FFFE"),
        ("\uffff", "U+FFFF"),
        ("\ud800", "U+D800"),
    ],
)
def test_render_markdown_refuses_a_character_xml_does_not_allow(
    character: str, code_point: str
) -> None:
    blocks = _blocks_file((_paragraph("b-p0003-002", f"ab{character}cd"),))

    with pytest.raises(
        InputFileError, match=rf"blocks.json.*b-p0003-002.*{re.escape(code_point)}"
    ):
        render_markdown(blocks, CONFIG)


@pytest.mark.parametrize("character", ["\x7f", "\x80", "\x9f", "\ufdd0", "\U0010ffff"])
def test_render_markdown_writes_c1_controls_and_other_noncharacters(
    character: str,
) -> None:
    blocks = _blocks_file((_paragraph("b-p0003-002", f"ab{character}cd"),))

    assert f"ab{character}cd" in render_markdown(blocks, CONFIG)


DC = "{http://purl.org/dc/elements/1.1/}"


@pytest.mark.pandoc
def test_title_and_author_reach_the_epub_unchanged(tmp_path: Path) -> None:
    title = "The Life of *Gargantua* C:\\Windows <b> [x](y) _Pantagruel_ Ærø"
    author = "F. *Rabelais* \\ <i> [x](y) _Ñ_"
    config = BookConfig(
        pdf=CONFIG.pdf, title=title, authors=(author,), language=Language.FR
    )
    folder = BookFolder(tmp_path)
    folder.book_md.write_text(render_markdown(TWO_PARAGRAPHS, config), encoding="utf-8")

    epub.run(folder, config)

    with zipfile.ZipFile(folder.book_epub) as book:
        package = ET.fromstring(book.read("EPUB/content.opf"))
    assert [element.text for element in package.iter(f"{DC}title")] == [title]
    assert [element.text for element in package.iter(f"{DC}creator")] == [author]


# run


def _book(
    root: Path, blocks: BlocksFile = TWO_PARAGRAPHS
) -> tuple[BookFolder, BookConfig]:
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
                    blank_checked_by_ocr=False,
                )
                for index in range(2)
            ),
            ocr_audit=None,
        ),
    )
    write_blocks(folder.blocks_json, blocks)
    return folder, replace(CONFIG, pdf=pdf)


EDIT = Edit(
    block_id="b-p0001-001",
    block_sha256="0123456789ab",
    old="three",
    new="four",
    author="owner",
    reason="a typo",
)


def test_run_with_an_edit_raises_naming_the_file_and_leaves_no_book_md(
    tmp_path: Path,
) -> None:
    folder, config = _book(tmp_path)
    folder.edits_dir.mkdir()
    write_edits(folder.edits_dir / "correct.jsonl", ())
    write_edits(folder.edits_dir / "owner.jsonl", (EDIT,))
    folder.book_md.write_text("an old book.md\n", encoding="utf-8")

    with pytest.raises(
        EditError, match="owner.jsonl.*markdown does not apply edits yet"
    ) as raised:
        markdown.run(folder, config)

    assert "correct.jsonl" not in str(raised.value)
    assert not folder.book_md.exists()


@pytest.mark.pandoc
def test_run_with_an_empty_edits_file_writes_book_md(tmp_path: Path) -> None:
    folder, config = _book(tmp_path)
    folder.edits_dir.mkdir()
    write_edits(folder.edits_dir / "owner.jsonl", ())

    markdown.run(folder, config)

    assert folder.book_md.read_text(encoding="utf-8") == TWO_PARAGRAPHS_MARKDOWN


@pytest.mark.pandoc
def test_run_without_an_edits_folder_writes_book_md(tmp_path: Path) -> None:
    folder, config = _book(tmp_path)
    folder.book_md.write_text("an old book.md\n", encoding="utf-8")

    markdown.run(folder, config)

    assert folder.book_md.read_text(encoding="utf-8") == TWO_PARAGRAPHS_MARKDOWN


# Replaces render_markdown in the module for every thread.
@pytest.mark.thread_unsafe
@pytest.mark.pandoc
def test_run_with_a_word_lost_in_the_markdown_raises_and_writes_no_book_md(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder, config = _book(tmp_path)

    render = markdown.render_markdown

    def render_without_a_word(blocks: BlocksFile, config: BookConfig) -> str:
        return render(blocks, config).replace("THEORIES ", "")

    monkeypatch.setattr(markdown, "render_markdown", render_without_a_word)

    with pytest.raises(FidelityError) as raised:
        markdown.run(folder, config)

    assert raised.value.missing == frozendict({"THEORIES": 1})
    assert not folder.book_md.exists()


# Spec section 8: white space to str.split() that XML 1.0 does not allow.
XML_FORBIDDEN_WHITE_SPACE = "\x0b\x0c\x1c\x1d\x1e\x1f"


@pytest.mark.pandoc
def test_run_writes_xml_forbidden_white_space_as_spaces_keeping_every_word(
    tmp_path: Path,
) -> None:
    text = " ".join(
        f"a{character}b {character * 4}c" for character in XML_FORBIDDEN_WHITE_SPACE
    )
    folder, config = _book(tmp_path, _blocks_file((_paragraph("b-p0000-001", text),)))

    markdown.run(folder, config)

    book_md = folder.book_md.read_text(encoding="utf-8")
    assert [word.text for word in read_markdown(book_md).words] == text.split()
    assert not any(character in book_md for character in XML_FORBIDDEN_WHITE_SPACE)


def test_run_on_blocks_of_another_pdf_raises_naming_structure(tmp_path: Path) -> None:
    folder, config = _book(
        tmp_path,
        _blocks_file(TWO_PARAGRAPHS.blocks, source_pdf_sha256=OTHER_PDF_SHA256),
    )

    with pytest.raises(InputFileError, match="galley2epub structure"):
        markdown.run(folder, config)

    assert not folder.book_md.exists()


def test_run_with_a_config_of_another_pdf_raises_naming_analyze(
    tmp_path: Path,
) -> None:
    folder, config = _book(tmp_path)
    other_pdf = tmp_path / "other.pdf"
    other_pdf.write_bytes(b"%PDF-1.4 another book")
    folder.book_md.write_text("an old book.md\n", encoding="utf-8")

    with pytest.raises(InputFileError, match=r"pages\.json.*galley2epub analyze"):
        markdown.run(folder, replace(config, pdf=other_pdf))

    assert not folder.book_md.exists()


def test_run_without_blocks_json_raises_naming_structure(tmp_path: Path) -> None:
    folder, config = _book(tmp_path)
    folder.blocks_json.unlink()

    with pytest.raises(InputFileError, match="galley2epub structure"):
        markdown.run(folder, config)


# Pages 0 and 1, which _book's pages.json has.
SIDE_TEXT_ON_TWO_PAGES = _blocks_file(
    (
        _block("b-p0000-001", BlockKind.PARAGRAPH, "Of the three estates.", 0),
        _block("b-p0000-002", BlockKind.MARGIN_NOTE, "The estates.", 0),
        _block("b-p0001-001", BlockKind.PARAGRAPH, "Of the clergy.", 1),
    ),
    (
        _unreferenced_note(
            "n-p0000-001",
            0,
            _block("b-p0000-003", BlockKind.PARAGRAPH, "See the rolls.", 0),
            marker="1",
        ),
    ),
)


@pytest.mark.parametrize(
    ("blocks", "repeated"),
    [
        (
            _blocks_file(
                (
                    _block("b-p0003-001", BlockKind.PARAGRAPH, "One.", 3),
                    _block("b-p0003-001", BlockKind.MARGIN_NOTE, "Two.", 3),
                ),
            ),
            "b-p0003-001",
        ),
        (
            _blocks_file(
                (_block("b-p0003-001", BlockKind.PARAGRAPH, "One.", 3),),
                (
                    _unreferenced_note(
                        "n-p0003-001",
                        3,
                        _block("b-p0003-001", BlockKind.PARAGRAPH, "Two.", 3),
                    ),
                ),
            ),
            "b-p0003-001",
        ),
        (
            _blocks_file(
                (_block("n-p0003-001", BlockKind.PARAGRAPH, "One.", 3),),
                (
                    _unreferenced_note(
                        "n-p0003-001",
                        3,
                        _block("b-p0003-002", BlockKind.PARAGRAPH, "Two.", 3),
                    ),
                ),
            ),
            "n-p0003-001",
        ),
        (
            _blocks_file(
                (),
                tuple(
                    _unreferenced_note(
                        "n-p0003-001",
                        3,
                        _block(block_id, BlockKind.PARAGRAPH, "A note.", 3),
                    )
                    for block_id in ("b-p0003-001", "b-p0003-002")
                ),
            ),
            "n-p0003-001",
        ),
    ],
    ids=["two blocks", "a note block and a block", "a note and a block", "two notes"],
)
def test_render_markdown_refuses_an_id_given_twice(
    blocks: BlocksFile, repeated: str
) -> None:
    with pytest.raises(
        InputFileError, match=rf"blocks.json.*id {repeated} is given 2 times"
    ):
        render_markdown(blocks, CONFIG)


def test_render_markdown_refuses_a_marker_with_a_character_xml_does_not_allow() -> None:
    note = replace(SIDE_TEXT.notes[0], marker="\ufffe")
    blocks = replace(SIDE_TEXT, notes=(note,))

    with pytest.raises(
        InputFileError, match=r"blocks.json.*marker of note n-p0003-001.*U\+FFFE"
    ):
        render_markdown(blocks, CONFIG)


# Java starts in about a second; the 8-thread run would start it 8 times.
@pytest.mark.thread_unsafe
@pytest.mark.pandoc
@pytest.mark.epubcheck
def test_the_epub_of_margin_notes_and_notes_passes_epubcheck(tmp_path: Path) -> None:
    folder, config = _book(tmp_path, SIDE_TEXT_ON_TWO_PAGES)

    markdown.run(folder, config)
    epub.run(folder, config)

    epubcheck = shutil.which("epubcheck")
    assert epubcheck is not None
    # Not captured here, so that pytest shows epubcheck's report on failure;
    # check=True makes any error a CalledProcessError.
    subprocess.run([epubcheck, str(folder.book_epub)], check=True, timeout=60)
