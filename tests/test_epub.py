"""Tests of the epub stage: Pandoc's arguments and run (spec section 8)."""

import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest

from galley import epub
from galley.book_folder import BookFolder
from galley.config import BookConfig, Language
from galley.epub import pandoc_arguments
from galley.errors import InputFileError

BOOK_MD = Path(__file__).parent / "fixtures" / "epub" / "book.md"

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
        "markdown-smart",
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
        "markdown-smart",
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
        assert first.filename == "mimetype"
        assert book.read(first) == b"application/epub+zip"
    assert ">The Battle of Kadesh</dc:title>" in package
    assert "<dc:language>en</dc:language>" in package
    assert '<div id="b-p0000-001">' in chapter
    assert '<div id="b-p0001-001">' in chapter


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
