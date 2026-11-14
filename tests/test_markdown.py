"""Tests of the markdown stage: escaping, rendering and run (spec section 8)."""

import re
import string
import xml.etree.ElementTree as ET
import zipfile
from collections import defaultdict
from pathlib import Path

import pytest

from galley import epub, markdown
from galley.book_folder import BookFolder
from galley.config import BookConfig, Language
from galley.errors import EditError, FidelityError, InputFileError
from galley.fidelity import read_markdown
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

SOURCE_PDF_SHA256 = "a" * 64
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
HEADING = Block(
    id="b-p0000-001",
    kind=BlockKind.HEADING,
    level=1,
    spans=(Span("Chapter one", Emphasis.NONE, None),),
    figure=None,
    origin=(Origin(0, Box(10.0, 20.0, 300.0, 40.0)),),
)


@pytest.mark.parametrize(
    ("blocks", "named"),
    [
        (_blocks_file((HEADING,)), "b-p0000-001"),
        (_blocks_file((_paragraph("b-p0000-001", "Text."),), (NOTE,)), "n-p0000-001"),
        (
            _blocks_file(
                (_paragraph("b-p0000-003", "Greece,", "1", note_ref="n-p0000-001"),),
            ),
            "b-p0000-003",
        ),
    ],
    ids=["heading", "note", "note reference"],
)
def test_render_markdown_refuses_what_the_skeleton_does_not_write(
    blocks: BlocksFile, named: str
) -> None:
    with pytest.raises(InputFileError, match=f"blocks.json.*{named}"):
        render_markdown(blocks, CONFIG)


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


def _book_folder(root: Path, blocks: BlocksFile = TWO_PARAGRAPHS) -> BookFolder:
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
    return folder


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
    folder = _book_folder(tmp_path)
    folder.edits_dir.mkdir()
    write_edits(folder.edits_dir / "correct.jsonl", ())
    write_edits(folder.edits_dir / "owner.jsonl", (EDIT,))
    folder.book_md.write_text("an old book.md\n", encoding="utf-8")

    with pytest.raises(EditError, match="owner.jsonl") as raised:
        markdown.run(folder, CONFIG)

    assert "correct.jsonl" not in str(raised.value)
    assert not folder.book_md.exists()


@pytest.mark.pandoc
def test_run_with_an_empty_edits_file_writes_book_md(tmp_path: Path) -> None:
    folder = _book_folder(tmp_path)
    folder.edits_dir.mkdir()
    write_edits(folder.edits_dir / "owner.jsonl", ())

    markdown.run(folder, CONFIG)

    assert folder.book_md.read_text(encoding="utf-8") == TWO_PARAGRAPHS_MARKDOWN


@pytest.mark.pandoc
def test_run_without_an_edits_folder_writes_book_md(tmp_path: Path) -> None:
    folder = _book_folder(tmp_path)
    folder.book_md.write_text("an old book.md\n", encoding="utf-8")

    markdown.run(folder, CONFIG)

    assert folder.book_md.read_text(encoding="utf-8") == TWO_PARAGRAPHS_MARKDOWN


# Replaces render_markdown in the module for every thread.
@pytest.mark.thread_unsafe
@pytest.mark.pandoc
def test_run_with_a_word_lost_in_the_markdown_raises_and_writes_no_book_md(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = _book_folder(tmp_path)

    render = markdown.render_markdown

    def render_without_a_word(blocks: BlocksFile, config: BookConfig) -> str:
        return render(blocks, config).replace("THEORIES ", "")

    monkeypatch.setattr(markdown, "render_markdown", render_without_a_word)

    with pytest.raises(FidelityError) as raised:
        markdown.run(folder, CONFIG)

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
    folder = _book_folder(tmp_path, _blocks_file((_paragraph("b-p0000-001", text),)))

    markdown.run(folder, CONFIG)

    book_md = folder.book_md.read_text(encoding="utf-8")
    assert [word.text for word in read_markdown(book_md).words] == text.split()
    assert not any(character in book_md for character in XML_FORBIDDEN_WHITE_SPACE)


def test_run_on_blocks_of_another_pdf_raises_naming_structure(tmp_path: Path) -> None:
    folder = _book_folder(
        tmp_path,
        _blocks_file(TWO_PARAGRAPHS.blocks, source_pdf_sha256=OTHER_PDF_SHA256),
    )

    with pytest.raises(InputFileError, match="galley2epub structure"):
        markdown.run(folder, CONFIG)

    assert not folder.book_md.exists()


def test_run_without_blocks_json_raises_naming_structure(tmp_path: Path) -> None:
    folder = _book_folder(tmp_path)
    folder.blocks_json.unlink()

    with pytest.raises(InputFileError, match="galley2epub structure"):
        markdown.run(folder, CONFIG)
