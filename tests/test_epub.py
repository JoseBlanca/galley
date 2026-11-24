"""Tests of the epub stage: Pandoc's arguments and run (spec section 8)."""

import hashlib
import re
import shutil
import zipfile
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

import pytest
from PIL import Image

from galley import epub, markdown
from galley.book_folder import BookFolder
from galley.config import BookConfig, Language
from galley.epub import pandoc_arguments
from galley.errors import ExternalProgramError, InputFileError
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

BOOK_MD = Path(__file__).parent / "fixtures" / "epub" / "book.md"
STYLE_SHEET = Path(epub.__file__).parent / "style.css"

CONFIG = BookConfig(
    pdf=Path("/books/kadesh.pdf"),
    title="The Battle of Kadesh",
    authors=("J. H. Breasted",),
    language=Language.EN,
)
CONFIG_WITH_COVER = BookConfig(
    pdf=CONFIG.pdf,
    title=CONFIG.title,
    authors=CONFIG.authors,
    language=CONFIG.language,
    cover_page=0,
)


# pandoc_arguments


def test_pandoc_arguments_without_a_cover() -> None:
    folder = BookFolder(Path("/books/kadesh"))

    assert pandoc_arguments(
        folder,
        CONFIG,
        Path("/galley/epub/style.css"),
        Path("/galley/epub/back_links.lua"),
    ) == (
        "/books/kadesh/book.md",
        "--from",
        "markdown-smart-auto_identifiers",
        "--to",
        "epub3",
        "--output",
        "/books/kadesh/book.epub",
        "--css",
        "/galley/epub/style.css",
        "--lua-filter",
        "/galley/epub/back_links.lua",
        "--resource-path",
        "/books/kadesh",
        "--fail-if-warnings",
    )


def test_pandoc_arguments_with_a_cover() -> None:
    folder = BookFolder(Path("/books/kadesh"))

    assert pandoc_arguments(
        folder,
        CONFIG_WITH_COVER,
        Path("/galley/epub/style.css"),
        Path("/galley/epub/back_links.lua"),
    ) == (
        "/books/kadesh/book.md",
        "--from",
        "markdown-smart-auto_identifiers",
        "--to",
        "epub3",
        "--output",
        "/books/kadesh/book.epub",
        "--css",
        "/galley/epub/style.css",
        "--lua-filter",
        "/galley/epub/back_links.lua",
        "--resource-path",
        "/books/kadesh",
        "--fail-if-warnings",
        "--epub-cover-image",
        "/books/kadesh/images/cover.png",
    )


# run


def _folder_with_book_md(root: Path) -> BookFolder:
    folder = BookFolder(root)
    shutil.copyfile(BOOK_MD, folder.book_md)
    return folder


@pytest.mark.pandoc
def test_run_writes_an_epub_with_the_title_language_and_block_ids(
    tmp_path: Path,
) -> None:
    folder = _folder_with_book_md(tmp_path)

    epub.run(folder, CONFIG)

    with zipfile.ZipFile(folder.book_epub) as book:
        first = book.infolist()[0]
        package = book.read("EPUB/content.opf").decode("utf-8")
        chapter = book.read("EPUB/text/ch001.xhtml").decode("utf-8")
        style_sheet = book.read("EPUB/styles/stylesheet1.css")
        assert first.filename == "mimetype"
        assert book.read(first) == b"application/epub+zip"
    assert ">The Battle of Kadesh</dc:title>" in package
    assert "<dc:language>en</dc:language>" in package
    assert '<div id="b-p0000-001">' in chapter
    assert '<div id="b-p0001-001">' in chapter
    assert style_sheet == STYLE_SHEET.read_bytes()
    assert b".margin-note" in style_sheet
    assert b".index-entry.depth-2 p" in style_sheet


def test_run_without_book_md_raises_naming_markdown(tmp_path: Path) -> None:
    folder = BookFolder(tmp_path)
    folder.book_epub.write_bytes(b"an old book.epub")

    with pytest.raises(InputFileError, match="galley2epub markdown"):
        epub.run(folder, CONFIG)

    assert not folder.book_epub.exists()


def test_run_with_a_cover_page_and_no_cover_raises_naming_extract(
    tmp_path: Path,
) -> None:
    folder = _folder_with_book_md(tmp_path)

    with pytest.raises(InputFileError, match="galley2epub extract"):
        epub.run(folder, CONFIG_WITH_COVER)


@pytest.mark.pandoc
def test_run_when_pandoc_fails_raises_with_its_message_and_writes_no_epub(
    tmp_path: Path,
) -> None:
    folder = BookFolder(tmp_path)
    folder.book_md.write_text(
        '---\ntitle: "T"\nlang: en\n---\n\n::: {#b-p0000-001}\n![](missing.png)\n:::\n',
        encoding="utf-8",
    )

    with pytest.raises(ExternalProgramError, match="Could not fetch resource"):
        epub.run(folder, CONFIG)

    assert not folder.book_epub.exists()


# Empties PATH for the whole process.
@pytest.mark.thread_unsafe
def test_run_without_pandoc_says_it_is_not_installed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = _folder_with_book_md(tmp_path)
    monkeypatch.setenv("PATH", "")

    with pytest.raises(ExternalProgramError, match="pandoc is not installed"):
        epub.run(folder, CONFIG)


# An EPUB of every kind of block, from a blocks.json made by hand (structure
# spec section 19).

_PDF_BYTES = b"%PDF-1.4 a stand-in: markdown reads only its hash"


def _block(
    block_id: str,
    kind: BlockKind,
    *texts: str | tuple[str, str],
    level: int | None = None,
    label: str | None = None,
) -> Block:
    """A block on the page of its id, of a span for each text, a pair being
    a reference's text and the id of its note."""
    page_index = int(block_id[3:7])
    return Block(
        id=block_id,
        kind=kind,
        level=level,
        label=label,
        spans=tuple(
            Span(text[0], Emphasis.NONE, text[1])
            if isinstance(text, tuple)
            else Span(text, Emphasis.NONE, None)
            for text in texts
        ),
        figure=None,
        origin=(Origin(page_index, Box(10.0, 20.0, 300.0, 400.0)),),
    )


def _note(
    note_id: str, kind: NoteKind, marker: str, *blocks: Block, referenced: bool
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


# Chapter III on page 0, with a footnote that has a margin note, and a
# reference to an endnote; the endnotes on page 1, the second unreferenced;
# the index on page 2.
EVERY_KIND = BlocksFile(
    source_pdf_sha256=hashlib.sha256(_PDF_BYTES).hexdigest(),
    blocks=(
        _block(
            "b-p0000-001",
            BlockKind.HEADING,
            "THE EARLY YEARS OF HENRY II.",
            level=1,
            label="CHAPTER III.",
        ),
        _block(
            "b-p0000-002", BlockKind.CHAPTER_SUMMARY, "Henry's youth. — His accession."
        ),
        _block("b-p0000-003", BlockKind.MARGIN_NOTE, "Of kings."),
        _block(
            "b-p0000-004",
            BlockKind.PARAGRAPH,
            "1. Of the three estates,",
            ("*", "n-p0000-001"),
            " and the Law",
            ("1", "n-p0001-001"),
            " of the realm.",
        ),
        _block("b-p0000-005", BlockKind.QUOTE, '"Rex in regno suo."'),
        _block(
            "b-p0000-006",
            BlockKind.VERSE,
            "Mignonne, allons voir\nsi la rose,\n\nqui ce matin",
        ),
        _block("b-p0001-001", BlockKind.HEADING, "NOTES.", level=1),
        _block("b-p0002-001", BlockKind.HEADING, "INDEX", level=1),
        _block("b-p0002-002", BlockKind.INDEX_ENTRY, "Aachen, 12, 34-36.", level=1),
        _block("b-p0002-005", BlockKind.INDEX_ENTRY, "council at, 36.", level=2),
        replace(
            _block("b-p0002-003", BlockKind.FIGURE, "PLATE I. The battle."),
            figure="images/plate-0002.png",
        ),
        replace(
            _block("b-p0002-004", BlockKind.FIGURE), figure="images/plate-0003.png"
        ),
    ),
    notes=(
        _note(
            "n-p0000-001",
            NoteKind.FOOTNOTE,
            "*",
            _block("b-p0000-007", BlockKind.MARGIN_NOTE, "The estates."),
            _block("b-p0000-008", BlockKind.PARAGRAPH, "See the rolls."),
            referenced=True,
        ),
        _note(
            "n-p0001-001",
            NoteKind.ENDNOTE,
            "1.",
            _block("b-p0001-002", BlockKind.MARGIN_NOTE, "Roman law."),
            _block("b-p0001-003", BlockKind.PARAGRAPH, "Digest, 1."),
            referenced=True,
        ),
        _note(
            "n-p0001-002",
            NoteKind.ENDNOTE,
            "2.",
            _block("b-p0001-004", BlockKind.PARAGRAPH, "Code, 2."),
            referenced=False,
        ),
    ),
    removals=(),
    word_changes=(),
    page_numbers=(),
)


def _book_of(root: Path, blocks: BlocksFile) -> tuple[BookFolder, BookConfig]:
    """A book folder with book.pdf, pages.json of three pages made from it,
    a small grey image at the path of each figure,
    and `blocks`, and CONFIG with book.pdf as its PDF."""
    pdf = root / "book.pdf"
    pdf.write_bytes(_PDF_BYTES)
    folder = BookFolder(root)
    write_pages(
        folder.pages_json,
        PagesFile(
            source_pdf_sha256=blocks.source_pdf_sha256,
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
                for index in range(3)
            ),
            ocr_audit=None,
        ),
    )
    write_blocks(folder.blocks_json, blocks)
    for block in blocks.blocks:
        if block.figure is not None:
            image_path = root / block.figure
            image_path.parent.mkdir(parents=True, exist_ok=True)
            Image.new("L", (4, 4), color=128).save(image_path)
    return folder, replace(CONFIG, pdf=pdf)


def _chapters(epub_path: Path) -> str:
    """The text of every chapter file of an EPUB, one after the other."""
    with zipfile.ZipFile(epub_path) as book:
        return "".join(
            book.read(name).decode("utf-8")
            for name in sorted(book.namelist())
            if name.startswith("EPUB/text/ch")
        )


@pytest.mark.pandoc
def test_the_epub_of_every_kind_and_of_a_footnote_and_endnotes_has_each_in_its_html(
    tmp_path: Path,
) -> None:
    folder, config = _book_of(tmp_path, EVERY_KIND)

    markdown.run(folder, config)
    epub.run(folder, config)

    chapters = _chapters(folder.book_epub)
    assert '<h1><span class="label">CHAPTER III.</span> THE EARLY YEARS' in chapters
    assert '<div id="b-p0000-002" class="chapter-summary">' in chapters
    assert '<div id="b-p0000-006" class="verse">' in chapters
    # An index entry's depth is a class, which the style sheet indents.
    assert '<div id="b-p0002-002" class="index-entry depth-1">' in chapters
    assert '<div id="b-p0002-005" class="index-entry depth-2">' in chapters
    assert "<p>Mignonne, allons voir<br />\nsi la rose,</p>" in chapters
    # The reference to the endnote, in chapter III, points into the file of
    # the notes, where the endnotes are one list.
    assert (
        'the Law<a href="ch002.xhtml#n-p0001-001" id="ref-n-p0001-001" '
        'epub:type="noteref">1</a>'
    ) in chapters
    # The endnote's number links back to it, and the unreferenced
    # endnote's number is plain text (architecture section 9, "Back links").
    assert (
        '<div id="b-p0001-003">\n<p><a href="ch001.xhtml#ref-n-p0001-001" '
        'role="doc-backlink">1.</a> Digest, 1.</p>'
    ) in chapters
    assert '<div class="endnotes">\n<div id="n-p0001-001" class="endnote">' in (
        chapters
    )
    assert "<p>2. Code, 2.</p>" in chapters
    # Each figure's image is in the EPUB, the caption under the first.
    assert re.search(
        r'<div id="b-p0002-003" class="figure">\s*<figure>\s*<img src="[^"]+\.png"'
        r"[^>]*/>\s*<figcaption[^>]*>PLATE I\. The battle\.</figcaption>",
        chapters,
    )
    assert re.search(
        r'<div id="b-p0002-004" class="figure">\s*<p><img src="[^"]+\.png"', chapters
    )
    # The footnote is Pandoc's, its margin note inside it, and its number
    # at the start of its paragraph, after the margin note, links back to
    # Pandoc's reference.
    assert re.search(
        r'<aside epub:type="footnote"[^>]*>\s*<div id="b-p0000-007" '
        r'class="margin-note">\s*<p>The estates.</p>\s*</div>\s*'
        r'<div id="b-p0000-008">\s*<p><a href="#fnref1" class="footnote-back" '
        r'role="doc-backlink">1</a> '
        r"See the rolls.</p>",
        chapters,
    )


# Two chapters, the first with two footnotes, the second with one and an
# unlinked footnote, which goes under the chapter's "Notes" heading.
TWO_CHAPTERS = replace(
    EVERY_KIND,
    blocks=(
        _block("b-p0000-001", BlockKind.HEADING, "ONE", level=1),
        _block(
            "b-p0000-002",
            BlockKind.PARAGRAPH,
            "Of Greece",
            ("*", "n-p0000-001"),
            " and Rome",
            ("\u2020", "n-p0000-002"),
            ".",
        ),
        _block("b-p0001-001", BlockKind.HEADING, "TWO", level=1),
        _block("b-p0001-002", BlockKind.PARAGRAPH, "Of Gaul", ("1", "n-p0001-001")),
    ),
    notes=(
        _note(
            "n-p0000-001",
            NoteKind.FOOTNOTE,
            "*",
            _block("b-p0000-003", BlockKind.PARAGRAPH, "Plato."),
            referenced=True,
        ),
        _note(
            "n-p0000-002",
            NoteKind.FOOTNOTE,
            "\u2020",
            _block("b-p0000-004", BlockKind.PARAGRAPH, "Livy."),
            referenced=True,
        ),
        _note(
            "n-p0001-001",
            NoteKind.FOOTNOTE,
            "1",
            _block("b-p0001-003", BlockKind.PARAGRAPH, "Caesar."),
            referenced=True,
        ),
        _note(
            "n-p0001-002",
            NoteKind.FOOTNOTE,
            "2",
            _block("b-p0001-004", BlockKind.PARAGRAPH, "Strabo."),
            referenced=False,
        ),
    ),
)


def _chapter_files(epub_path: Path) -> dict[str, str]:
    with zipfile.ZipFile(epub_path) as book:
        return {
            name: book.read(name).decode("utf-8")
            for name in sorted(book.namelist())
            if name.startswith("EPUB/text/ch")
        }


@pytest.mark.pandoc
def test_each_footnote_number_links_back_to_its_reference_in_its_chapter_file(
    tmp_path: Path,
) -> None:
    folder, config = _book_of(tmp_path, TWO_CHAPTERS)

    markdown.run(folder, config)
    epub.run(folder, config)

    files = _chapter_files(folder.book_epub)
    back_links = {
        name: re.findall(
            r'<aside epub:type="footnote" role="doc-footnote" id="fn(\d+)">\s*'
            r'<div id="[^"]+">\s*<p><a href="#fnref(\d+)" class="footnote-back" '
            r'role="doc-backlink">'
            r"(\d+)</a> (\w+)\.",
            text,
        )
        for name, text in files.items()
    }
    references = {
        name: re.findall(r'id="fnref(\d+)"[^>]*>(\d+)</a>', text)
        for name, text in files.items()
    }
    assert back_links == {
        "EPUB/text/ch001.xhtml": [("1", "1", "1", "Plato"), ("2", "2", "2", "Livy")],
        "EPUB/text/ch002.xhtml": [("1", "1", "1", "Caesar")],
    }
    assert references == {
        "EPUB/text/ch001.xhtml": [("1", "1"), ("2", "2")],
        "EPUB/text/ch002.xhtml": [("1", "1")],
    }
    # The unlinked footnote keeps its marker as text, with no back link.
    assert "<p>2 Strabo.</p>" in files["EPUB/text/ch002.xhtml"]
    assert files["EPUB/text/ch002.xhtml"].count("doc-backlink") == 1


# Java starts in about a second; the 8-thread run would start it 8 times.
# One call checks these and the lists book's EPUB (structure spec sections
# 31 and 32), which test_markdown_lists.py reads: a call of its own took
# about 1.5 s of the default run (18 November 2026).
@pytest.mark.thread_unsafe
@pytest.mark.pandoc
@pytest.mark.epubcheck
def test_the_epubs_of_a_hand_written_book_md_of_every_kind_and_of_lists_pass_epubcheck(
    tmp_path: Path, check_epubs: Callable[..., None], lists_book_epub: BookFolder
) -> None:
    (tmp_path / "hand_written").mkdir()
    (tmp_path / "every_kind").mkdir()
    hand_written = _folder_with_book_md(tmp_path / "hand_written")
    epub.run(hand_written, CONFIG)
    every_kind, config = _book_of(tmp_path / "every_kind", EVERY_KIND)
    markdown.run(every_kind, config)
    epub.run(every_kind, config)

    (tmp_path / "two_chapters").mkdir()
    two_chapters, config = _book_of(tmp_path / "two_chapters", TWO_CHAPTERS)
    markdown.run(two_chapters, config)
    epub.run(two_chapters, config)

    check_epubs(
        hand_written.book_epub,
        every_kind.book_epub,
        two_chapters.book_epub,
        lists_book_epub.book_epub,
    )


@pytest.mark.pandoc
def test_footnote_of_margin_notes_only_gets_its_number_before_them(
    tmp_path: Path,
) -> None:
    # The Lua filter's last case: no paragraph outside a margin note's div,
    # so the number goes first in the note, a line of its own.
    blocks = replace(
        EVERY_KIND,
        blocks=(
            _block("b-p0000-001", BlockKind.HEADING, "ONE", level=1),
            _block(
                "b-p0000-002", BlockKind.PARAGRAPH, "Of Greece", ("*", "n-p0000-001")
            ),
        ),
        notes=(
            _note(
                "n-p0000-001",
                NoteKind.FOOTNOTE,
                "*",
                _block("b-p0000-003", BlockKind.MARGIN_NOTE, "Plato."),
                referenced=True,
            ),
        ),
    )
    folder, config = _book_of(tmp_path, blocks)

    markdown.run(folder, config)
    epub.run(folder, config)

    chapters = "".join(_chapter_files(folder.book_epub).values())
    assert re.search(
        r'<aside epub:type="footnote"[^>]*>\s*<a href="#fnref1" '
        r'class="footnote-back" role="doc-backlink">1</a>\s*'
        r'<div id="b-p0000-003" class="margin-note">',
        chapters,
    ), chapters
