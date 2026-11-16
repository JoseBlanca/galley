"""Tests of the epub stage: Pandoc's arguments and run (spec section 8)."""

import hashlib
import shutil
import subprocess
import zipfile
from dataclasses import replace
from pathlib import Path

import pytest

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

    assert pandoc_arguments(folder, CONFIG, Path("/galley/epub/style.css")) == (
        "/books/kadesh/book.md",
        "--from",
        "markdown-smart-auto_identifiers",
        "--to",
        "epub3",
        "--output",
        "/books/kadesh/book.epub",
        "--css",
        "/galley/epub/style.css",
        "--fail-if-warnings",
    )


def test_pandoc_arguments_with_a_cover() -> None:
    folder = BookFolder(Path("/books/kadesh"))

    assert pandoc_arguments(
        folder, CONFIG_WITH_COVER, Path("/galley/epub/style.css")
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


# Java starts in about a second; the 8-thread run would start it 8 times.
@pytest.mark.thread_unsafe
@pytest.mark.pandoc
@pytest.mark.epubcheck
def test_the_epub_of_a_hand_written_book_md_passes_epubcheck(tmp_path: Path) -> None:
    folder = _folder_with_book_md(tmp_path)
    epub.run(folder, CONFIG)
    epubcheck = shutil.which("epubcheck")
    assert epubcheck is not None

    # Not captured here, so that pytest shows epubcheck's report on failure;
    # check=True makes any error a CalledProcessError.
    subprocess.run([epubcheck, str(folder.book_epub)], check=True, timeout=60)


# An EPUB of every kind of block, from a blocks.json made by hand (structure
# spec section 19).

_PDF_BYTES = b"%PDF-1.4 a stand-in: markdown reads only its hash"


def _block(
    block_id: str,
    kind: BlockKind,
    text: str,
    *,
    level: int | None = None,
    label: str | None = None,
) -> Block:
    page_index = int(block_id[3:7])
    return Block(
        id=block_id,
        kind=kind,
        level=level,
        label=label,
        spans=(Span(text, Emphasis.NONE, None),),
        figure=None,
        origin=(Origin(page_index, Box(10.0, 20.0, 300.0, 400.0)),),
    )


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
        _block("b-p0000-004", BlockKind.PARAGRAPH, "1. Of the three estates."),
        _block("b-p0000-005", BlockKind.QUOTE, '"Rex in regno suo."'),
        _block(
            "b-p0000-006",
            BlockKind.VERSE,
            "Mignonne, allons voir\nsi la rose,\n\nqui ce matin",
        ),
        _block("b-p0001-001", BlockKind.HEADING, "INDEX", level=2),
        _block("b-p0001-002", BlockKind.INDEX_ENTRY, "Aachen, 12, 34-36."),
        _block("b-p0001-003", BlockKind.FIGURE, "PLATE I. The battle."),
    ),
    notes=(),
    removals=(),
    word_changes=(),
    page_numbers=(),
)


def _book_of(root: Path, blocks: BlocksFile) -> tuple[BookFolder, BookConfig]:
    """A book folder with book.pdf, pages.json of two pages made from it,
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
                    blank_checked_by_ocr=False,
                )
                for index in range(2)
            ),
            ocr_audit=None,
        ),
    )
    write_blocks(folder.blocks_json, blocks)
    return folder, replace(CONFIG, pdf=pdf)


def _chapters(epub_path: Path) -> str:
    """The text of every chapter file of an EPUB, one after the other."""
    with zipfile.ZipFile(epub_path) as book:
        return "".join(
            book.read(name).decode("utf-8")
            for name in sorted(book.namelist())
            if name.startswith("EPUB/text/ch")
        )


# Java starts in about a second; the 8-thread run would start it 8 times.
@pytest.mark.thread_unsafe
@pytest.mark.pandoc
@pytest.mark.epubcheck
def test_the_epub_of_every_kind_passes_epubcheck_with_the_verse_lines_kept(
    tmp_path: Path,
) -> None:
    folder, config = _book_of(tmp_path, EVERY_KIND)

    markdown.run(folder, config)
    epub.run(folder, config)

    chapters = _chapters(folder.book_epub)
    assert '<span class="label">CHAPTER III.</span>' in chapters
    assert '<div id="b-p0000-006" class="verse">' in chapters
    assert "Mignonne, allons voir<br />\nsi la rose,</p>" in chapters
    assert '<div id="b-p0000-002" class="chapter-summary">' in chapters
    epubcheck = shutil.which("epubcheck")
    assert epubcheck is not None
    # Not captured here, so that pytest shows epubcheck's report on failure;
    # check=True makes any error a CalledProcessError.
    subprocess.run([epubcheck, str(folder.book_epub)], check=True, timeout=60)
