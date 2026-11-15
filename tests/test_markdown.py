"""Tests of the markdown stage: escaping, rendering and run (spec section 8)."""

import hashlib
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
    marker="1",
    blocks=(_paragraph("b-p0000-002", "A note."),),
    origin=(Origin(0, Box(10.0, 500.0, 300.0, 520.0)),),
    referenced=True,
)


def _block_of_kind(block_id: str, kind: BlockKind) -> Block:
    return replace(_paragraph(block_id, "Chapter one"), kind=kind)


HEADING = replace(_block_of_kind("b-p0000-001", BlockKind.HEADING), level=1)


@pytest.mark.parametrize(
    ("blocks", "named"),
    [
        (_blocks_file((HEADING,)), "b-p0000-001"),
        *(
            (_blocks_file((_block_of_kind("b-p0000-004", kind),)), "b-p0000-004")
            for kind in (BlockKind.QUOTE, BlockKind.FIGURE, BlockKind.INDEX_ENTRY)
        ),
        (_blocks_file((_paragraph("b-p0000-001", "Text."),), (NOTE,)), "n-p0000-001"),
        (
            _blocks_file(
                (_paragraph("b-p0000-003", "Greece,", "1", note_ref="n-p0000-001"),),
            ),
            "b-p0000-003",
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
            "b-p0000-005",
        ),
        (
            _blocks_file(
                (),
                (
                    replace(
                        NOTE,
                        referenced=False,
                        blocks=(_block_of_kind("b-p0000-006", BlockKind.MARGIN_NOTE),),
                    ),
                ),
            ),
            "b-p0000-006",
        ),
        (
            _blocks_file(
                (),
                (
                    replace(
                        NOTE,
                        referenced=False,
                        blocks=(
                            _paragraph(
                                "b-p0000-007", "Ibid.", "2", note_ref="n-p0000-009"
                            ),
                        ),
                    ),
                ),
            ),
            "b-p0000-007",
        ),
        (
            _blocks_file((), (replace(NOTE, referenced=False, blocks=()),)),
            "n-p0000-001",
        ),
        (
            _blocks_file((), (replace(NOTE, referenced=False, origin=()),)),
            "n-p0000-001",
        ),
    ],
    ids=[
        "heading",
        "quote",
        "figure",
        "index entry",
        "referenced note",
        "note reference",
        "heading in a note",
        "margin note in a note",
        "note reference in a note",
        "note without blocks",
        "note without origin",
    ],
)
def test_render_markdown_refuses_what_it_does_not_write_yet(
    blocks: BlocksFile, named: str
) -> None:
    with pytest.raises(InputFileError, match=f"blocks.json.*{named}"):
        render_markdown(blocks, CONFIG)


# Structure spec section 10, option (b): margin notes and notes with
# `referenced` false.


def _block(block_id: str, kind: BlockKind, text: str, *page_indices: int) -> Block:
    """A block of one span on the pages given, one origin each."""
    return Block(
        id=block_id,
        kind=kind,
        level=None,
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

    with pytest.raises(EditError, match="owner.jsonl") as raised:
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
