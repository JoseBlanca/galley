"""The end-to-end test: the files `galley2epub run` writes for each excerpt
(spec section 9, "The end-to-end test").

Every test reads the folders of the session fixture `excerpt_books`, which
runs `main(["run", folder])` once per excerpt. The counts are those of spec
section 2, as literals; the excerpt tests of analyze and extract, in
test_analyze.py and test_extract.py, read the same folders.
"""

import shutil
import subprocess
import zipfile
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree

import pytest

from galley.book_folder import BookFolder
from galley.fidelity import read_markdown
from galley.model import block_text, read_blocks, read_lines, read_words

KADESH = "kadesh_8-17"
GIERKE = "gierke_86-93_270-271"

# Spec section 2: the lines of each page under the skeleton's layout rule.
# Kadesh page 0 keeps 41 lines without the page number 81, which shared a
# line with other words.
LINE_COUNTS = frozendict(
    {
        KADESH: (41, 45, 45, 52, 51, 50, 52, 49, 2, 0),
        GIERKE: (24, 37, 37, 36, 36, 36, 34, 30, 43, 53),
    }
)
# Spec sections 2 and 6: the words of each page in words.json. Kadesh page 0
# loses 81 to its excluded region, and page 9 is excluded.
WORD_COUNTS = frozendict(
    {
        KADESH: (583, 641, 671, 904, 822, 764, 909, 822, 4, 0),
        GIERKE: (192, 311, 297, 325, 319, 309, 292, 273, 547, 541),
    }
)
TITLES = frozendict(
    {KADESH: "The Battle of Kadesh", GIERKE: "Political Theories of the Middle Age"}
)
# The block ids of spec section 9: one paragraph per page that has a region.
BLOCK_IDS = frozendict(
    {
        KADESH: tuple(f"b-p{page:04d}-001" for page in range(9)),
        GIERKE: tuple(f"b-p{page:04d}-001" for page in range(10)),
    }
)

_XHTML = "http://www.w3.org/1999/xhtml"
_OPF = {
    "opf": "http://www.idpf.org/2007/opf",
    "dc": "http://purl.org/dc/elements/1.1/",
}


# The files of the book folder


def test_every_file_of_the_book_folder_but_edits_is_written(
    excerpt_books: frozendict[str, BookFolder],
) -> None:
    for folder in excerpt_books.values():
        assert sorted(path.name for path in folder.root.iterdir()) == [
            "blocks.json",
            "book.epub",
            "book.md",
            "book.toml",
            "images",
            "lines.json",
            "pages.json",
            "words.json",
        ]
    assert list(excerpt_books[KADESH].images_dir.iterdir()) == [
        excerpt_books[KADESH].cover_png
    ]
    assert list(excerpt_books[GIERKE].images_dir.iterdir()) == []


# lines.json


def test_lines_json_has_the_line_counts_of_spec_section_2(
    excerpt_books: frozendict[str, BookFolder],
) -> None:
    for name, line_counts in LINE_COUNTS.items():
        lines = read_lines(excerpt_books[name].lines_json)
        assert (
            tuple(
                sum(len(region.lines) for region in page.regions)
                for page in lines.pages
            )
            == line_counts
        )


def test_lines_json_has_one_region_per_page_but_on_the_excluded_kadesh_page_9(
    excerpt_books: frozendict[str, BookFolder],
) -> None:
    kadesh = read_lines(excerpt_books[KADESH].lines_json)
    gierke = read_lines(excerpt_books[GIERKE].lines_json)

    assert tuple(len(page.regions) for page in kadesh.pages) == (1,) * 9 + (0,)
    assert tuple(len(page.regions) for page in gierke.pages) == (1,) * 10


def test_kadesh_page_0_has_the_line_across_both_footnote_columns(
    excerpt_books: frozendict[str, BookFolder],
) -> None:
    (region,) = read_lines(excerpt_books[KADESH].lines_json).pages[0].regions
    texts = tuple(" ".join(word.text for word in line.words) for line in region.lines)

    assert (
        "•Pa per read before the International Congress of Ori- 'There is, "
        "however, much material for studying the"
    ) in texts


# blocks.json


def test_blocks_json_has_one_paragraph_per_page_with_every_word_of_it(
    excerpt_books: frozendict[str, BookFolder],
) -> None:
    for name, block_ids in BLOCK_IDS.items():
        blocks = read_blocks(excerpt_books[name].blocks_json)
        words = read_words(excerpt_books[name].words_json)
        assert tuple(block.id for block in blocks.blocks) == block_ids
        block_word_counts = tuple(
            len(block_text(block).split()) for block in blocks.blocks
        )
        assert block_word_counts == tuple(
            len(page.words) for page in words.pages if page.words
        )
        assert block_word_counts == tuple(
            count for count in WORD_COUNTS[name] if count > 0
        )


def test_the_last_kadesh_block_is_the_stray_words_of_the_plate(
    excerpt_books: frozendict[str, BookFolder],
) -> None:
    blocks = read_blocks(excerpt_books[KADESH].blocks_json)

    assert block_text(blocks.blocks[-1]) == ", ' .. ^U;L"


def test_blocks_json_has_no_notes_removals_word_changes_or_page_numbers(
    excerpt_books: frozendict[str, BookFolder],
) -> None:
    for folder in excerpt_books.values():
        blocks = read_blocks(folder.blocks_json)
        assert blocks.notes == ()
        assert blocks.removals == ()
        assert blocks.word_changes == ()
        assert blocks.page_numbers == ()


# book.md


@pytest.mark.pandoc
def test_book_md_holds_every_word_of_words_json_and_no_note(
    excerpt_books: frozendict[str, BookFolder],
) -> None:
    for name, word_count in ((KADESH, 6120), (GIERKE, 3406)):
        folder = excerpt_books[name]
        markdown = read_markdown(folder.book_md.read_text(encoding="utf-8"))
        words = read_words(folder.words_json)
        assert len(markdown.words) == word_count
        assert Counter(word.text for word in markdown.words) == Counter(
            word.text for page in words.pages for word in page.words
        )
        assert markdown.note_count == 0


# book.epub


def _opf(epub: zipfile.ZipFile) -> ElementTree.Element:
    return ElementTree.fromstring(epub.read("EPUB/content.opf"))


def test_book_epub_is_an_epub_with_the_title_language_and_every_block(
    excerpt_books: frozendict[str, BookFolder],
) -> None:
    for name, block_ids in BLOCK_IDS.items():
        with zipfile.ZipFile(excerpt_books[name].book_epub) as epub:
            first = epub.infolist()[0]
            assert first.filename == "mimetype"
            assert epub.read(first) == b"application/epub+zip"
            opf = _opf(epub)
            title = opf.findtext("opf:metadata/dc:title", namespaces=_OPF)
            language = opf.findtext("opf:metadata/dc:language", namespaces=_OPF)
            assert title == TITLES[name]
            assert language == "en"
            chapter = epub.read("EPUB/text/ch001.xhtml").decode("utf-8")
            for block_id in block_ids:
                assert f'<div id="{block_id}">' in chapter


def test_each_block_div_of_the_epub_holds_the_words_of_its_block(
    excerpt_books: frozendict[str, BookFolder],
) -> None:
    for folder in excerpt_books.values():
        blocks = read_blocks(folder.blocks_json)
        with zipfile.ZipFile(folder.book_epub) as epub:
            chapter = ElementTree.fromstring(epub.read("EPUB/text/ch001.xhtml"))
        divs = {
            div.get("id"): "".join(div.itertext()).split()
            for div in chapter.iter(f"{{{_XHTML}}}div")
            if div.get("id") is not None
        }
        assert divs == {block.id: block_text(block).split() for block in blocks.blocks}


def test_only_the_kadesh_epub_has_the_cover_extract_rendered(
    excerpt_books: frozendict[str, BookFolder],
) -> None:
    def cover_images(folder: BookFolder) -> tuple[bytes, ...]:
        with zipfile.ZipFile(folder.book_epub) as epub:
            return tuple(
                epub.read(f"EPUB/{item.get('href')}")
                for item in _opf(epub).iterfind("opf:manifest/opf:item", _OPF)
                if item.get("properties") == "cover-image"
            )

    kadesh = excerpt_books[KADESH]
    assert cover_images(kadesh) == (kadesh.cover_png.read_bytes(),)
    assert cover_images(excerpt_books[GIERKE]) == ()


# Java starts in about a second; the 8-thread run would start it 8 times.
@pytest.mark.thread_unsafe
@pytest.mark.epubcheck
@pytest.mark.parametrize("name", [KADESH, GIERKE])
def test_the_excerpt_epub_passes_epubcheck(
    name: str, excerpt_books: frozendict[str, BookFolder]
) -> None:
    epubcheck = shutil.which("epubcheck")
    assert epubcheck is not None
    epub_path: Path = excerpt_books[name].book_epub

    # Not captured, so that pytest shows epubcheck's report on failure;
    # check=True makes any error a CalledProcessError.
    subprocess.run([epubcheck, str(epub_path)], check=True, timeout=60)
