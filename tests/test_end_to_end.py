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
# The block ids of spec section 9 that still hold with layout's regions: the
# first block of each page that has a region.
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


def test_every_word_of_a_page_is_in_one_line_of_that_page(
    excerpt_books: frozendict[str, BookFolder],
) -> None:
    # Layout spec section 7: layout regroups words and removes none.
    for name, word_counts in WORD_COUNTS.items():
        lines = read_lines(excerpt_books[name].lines_json)
        words = read_words(excerpt_books[name].words_json)
        assert tuple(page.index for page in lines.pages) == tuple(
            page.index for page in words.pages
        )
        for page_lines, page_words in zip(lines.pages, words.pages, strict=True):
            assert Counter(
                word.text
                for region in page_lines.regions
                for line in region.lines
                for word in line.words
            ) == Counter(word.text for word in page_words.words)
        assert (
            tuple(
                sum(len(line.words) for region in page.regions for line in region.lines)
                for page in lines.pages
            )
            == word_counts
        )


def test_every_page_has_regions_but_the_excluded_kadesh_page_9(
    excerpt_books: frozendict[str, BookFolder],
) -> None:
    kadesh = read_lines(excerpt_books[KADESH].lines_json)
    gierke = read_lines(excerpt_books[GIERKE].lines_json)

    assert tuple(len(page.regions) > 0 for page in kadesh.pages) == (True,) * 9 + (
        False,
    )
    assert all(page.regions for page in gierke.pages)


def test_kadesh_page_2_has_a_running_head_region_first_and_a_band_of_two_columns(
    excerpt_books: frozendict[str, BookFolder],
) -> None:
    # Layout spec section 8: book page 10 has a running head and two
    # footnote columns. The head region is first and above every other; two
    # regions below the body sit side by side, the left one first.
    regions = read_lines(excerpt_books[KADESH].lines_json).pages[2].regions
    head, body = regions[0], regions[1]
    assert len(head.lines) == 1
    assert all(head.box.bottom <= region.box.top for region in regions[1:])
    below = tuple(region for region in regions[2:] if region.box.top >= body.box.bottom)
    assert any(
        left.box.x1 <= right.box.x0 + 2
        and left.box.top < right.box.bottom
        and right.box.top < left.box.bottom
        for index, left in enumerate(below)
        for right in below[index + 1 :]
    )


def test_kadesh_page_0_reads_its_two_footnote_columns_one_after_the_other(
    excerpt_books: frozendict[str, BookFolder],
) -> None:
    # The skeleton read one line across both columns, from "•Pa" in the
    # left to "'There" in the right; layout puts them in two regions, the
    # left first (layout spec section 3, step 5).
    regions = read_lines(excerpt_books[KADESH].lines_json).pages[0].regions

    def region_of(text: str) -> int:
        (index,) = (
            index
            for index, region in enumerate(regions)
            for line in region.lines
            if text in (word.text for word in line.words)
        )
        return index

    assert region_of("•Pa") < region_of("'There")


def test_gierke_page_2_has_a_margin_region_right_of_the_body(
    excerpt_books: frozendict[str, BookFolder],
) -> None:
    # Layout spec section 8: book page 88 has a running head and margin
    # notes outside the column, on the right of an even page index. The
    # spec's order puts the running-head region first and the body next.
    regions = read_lines(excerpt_books[GIERKE].lines_json).pages[2].regions
    head, body = regions[0], regions[1]
    assert head.box.bottom <= body.box.top
    assert any(region.box.x0 >= body.box.x1 for region in regions[2:])


# blocks.json


def test_blocks_json_has_one_paragraph_per_region_with_every_word_of_it(
    excerpt_books: frozendict[str, BookFolder],
) -> None:
    # The walking skeleton's structure, which work package 3 replaces: each
    # region becomes one paragraph, numbered from 1 on its page.
    for name, block_ids in BLOCK_IDS.items():
        blocks = read_blocks(excerpt_books[name].blocks_json)
        lines = read_lines(excerpt_books[name].lines_json)
        regions = tuple(
            (page.index, number, region)
            for page in lines.pages
            for number, region in enumerate(page.regions, start=1)
        )
        assert tuple(block.id for block in blocks.blocks) == tuple(
            f"b-p{index:04d}-{number:03d}" for index, number, _ in regions
        )
        assert set(block_ids) <= {block.id for block in blocks.blocks}
        assert tuple(block_text(block).split() for block in blocks.blocks) == tuple(
            [word.text for line in region.lines for word in line.words]
            for _, _, region in regions
        )


def test_the_last_kadesh_blocks_are_the_stray_words_of_the_plate(
    excerpt_books: frozendict[str, BookFolder],
) -> None:
    blocks = read_blocks(excerpt_books[KADESH].blocks_json)
    plate_words = [
        word
        for block in blocks.blocks
        if block.id.startswith("b-p0008-")
        for word in block_text(block).split()
    ]

    assert blocks.blocks[-1].id.startswith("b-p0008-")
    assert sorted(plate_words) == sorted([",", "'", "..", "^U;L"])


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
