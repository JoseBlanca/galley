"""The end-to-end test: the files `galley2epub run` writes for each excerpt
(spec section 9, "The end-to-end test").

Every test reads the folders of the session fixture `excerpt_books`, which
runs `main(["run", folder])` once per excerpt. The counts are those of spec
section 2, as literals; the excerpt tests of analyze and extract, in
test_analyze.py and test_extract.py, read the same folders.

At the end, the configs of the six whole books that tests/conftest.py
holds for the whole_book tests: the same as evaluation/books.toml for the
four books of the evaluation set, and taken by analyze on each book.
"""

import tomllib
import zipfile
from collections import Counter
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from xml.etree import ElementTree

import pytest

from galley.book_folder import BookFolder
from galley.cli import main
from galley.fidelity import read_markdown
from galley.model import (
    BlockKind,
    BlocksFile,
    Note,
    NoteKind,
    RemovalReason,
    block_text,
    read_blocks,
    read_lines,
    read_words,
)
from galley.text_layer import open_pdf

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
    # The cover and the images of the plates on pages 8 and 9.
    assert sorted(path.name for path in excerpt_books[KADESH].images_dir.iterdir()) == [
        "cover.png",
        "plate-0008.png",
        "plate-0009.png",
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


def _structure_words(blocks: BlocksFile) -> Counter[str]:
    """The words of blocks.json's blocks and notes, with structure's word
    changes undone and its removals added back: the words of words.json
    (the structure spec, section 7, and architecture section 13)."""
    words = Counter(
        word
        for block in (
            *blocks.blocks,
            *(b for note in blocks.notes for b in note.blocks),
        )
        for span in block.spans
        for word in span.text.split()
    )
    words.update(word for note in blocks.notes for word in note.marker.split())
    words.update(word for removal in blocks.removals for word in removal.text.split())
    words.update(word for change in blocks.word_changes for word in change.before)
    words.subtract(word for change in blocks.word_changes for word in change.after)
    return +words


def test_blocks_json_with_its_records_holds_every_word_of_words_json(
    excerpt_books: frozendict[str, BookFolder],
) -> None:
    for name, word_counts in WORD_COUNTS.items():
        blocks = read_blocks(excerpt_books[name].blocks_json)
        words = read_words(excerpt_books[name].words_json)
        assert _structure_words(blocks) == Counter(
            word.text for page in words.pages for word in page.words
        )
        assert _structure_words(blocks).total() == sum(word_counts)


def test_the_stray_words_of_the_kadesh_plate_are_removed_as_plate_text(
    excerpt_books: frozendict[str, BookFolder],
) -> None:
    # analyze finds page 8 a plate, and structure removes its two lines of
    # stray words (structure spec, section 18); the last blocks are the
    # figure blocks of pages 8 and 9, without text.
    blocks = read_blocks(excerpt_books[KADESH].blocks_json)
    assert sorted(
        removal.text
        for removal in blocks.removals
        if removal.reason is RemovalReason.PLATE_TEXT
    ) == [", ' ..", "^U;L"]
    assert tuple(
        (block.kind, block.figure, block_text(block)) for block in blocks.blocks[-2:]
    ) == (
        (BlockKind.FIGURE, "images/plate-0008.png", ""),
        (BlockKind.FIGURE, "images/plate-0009.png", ""),
    )


def test_every_page_number_of_blocks_json_is_a_page_number_removed_on_its_page(
    excerpt_books: frozendict[str, BookFolder],
) -> None:
    for folder in excerpt_books.values():
        blocks = read_blocks(folder.blocks_json)
        removed = {
            (removal.page_index, removal.text.replace(" ", ""))
            for removal in blocks.removals
            if removal.reason is RemovalReason.PAGE_NUMBER
        }
        assert {
            (number.page_index, number.text) for number in blocks.page_numbers
        } == removed


# book.md


def _words_of_book_md_and_their_expected_count(
    folder: BookFolder,
) -> tuple[Counter[str], Counter[str], int, int]:
    """The words of a folder's book.md as Pandoc reads them, those of its
    words.json less structure's records and the footnotes' markers and
    references, the number of notes Pandoc counts in book.md, and the number
    of references to a footnote in blocks.json."""
    markdown = read_markdown(folder.book_md.read_text(encoding="utf-8"))
    blocks = read_blocks(folder.blocks_json)
    words = Counter(
        word.text for page in read_words(folder.words_json).pages for word in page.words
    )
    words.subtract(word for removal in blocks.removals for word in removal.text.split())
    words.subtract(word for change in blocks.word_changes for word in change.before)
    words.update(word for change in blocks.word_changes for word in change.after)
    # A referenced footnote's marker and its reference are Pandoc's
    # number, not words.
    footnotes = frozenset(
        note.id for note in blocks.notes if _is_written_as_a_footnote(note)
    )
    words.subtract(
        word
        for note in blocks.notes
        if note.id in footnotes
        for word in note.marker.split()
    )
    references = tuple(
        span
        for block in (*blocks.blocks, *(b for n in blocks.notes for b in n.blocks))
        for span in block.spans
        if span.note_ref in footnotes
    )
    words.subtract(word for span in references for word in span.text.split())
    return (
        Counter(word.text for word in markdown.words),
        +words,
        markdown.note_count,
        len(references),
    )


# Pandoc reads the excerpts' book.md side by side: 0.9 s one after another
# on 16 November 2026, most of it Pandoc's.
_BOOK_MDS_READ_AT_ONCE = 6


@pytest.mark.pandoc
def test_book_md_holds_the_words_of_words_json_less_structures_records_and_no_note(
    excerpt_books: frozendict[str, BookFolder],
) -> None:
    with ThreadPoolExecutor(max_workers=_BOOK_MDS_READ_AT_ONCE) as pool:
        counts = tuple(
            pool.map(_words_of_book_md_and_their_expected_count, excerpt_books.values())
        )

    for name, (words, expected_words, note_count, references) in zip(
        excerpt_books, counts, strict=True
    ):
        assert words == expected_words, name
        assert note_count == references, name


# book.epub


def _opf(epub: zipfile.ZipFile) -> ElementTree.Element:
    return ElementTree.fromstring(epub.read("EPUB/content.opf"))


def test_book_epub_is_an_epub_with_the_title_language_and_every_block(
    excerpt_books: frozendict[str, BookFolder],
) -> None:
    for name in TITLES:
        block_ids = tuple(
            block.id for block in read_blocks(excerpt_books[name].blocks_json).blocks
        )
        with zipfile.ZipFile(excerpt_books[name].book_epub) as epub:
            first = epub.infolist()[0]
            assert first.filename == "mimetype"
            assert epub.read(first) == b"application/epub+zip"
            opf = _opf(epub)
            title = opf.findtext("opf:metadata/dc:title", namespaces=_OPF)
            language = opf.findtext("opf:metadata/dc:language", namespaces=_OPF)
            assert title == TITLES[name]
            assert language == "en"
            chapters = "".join(
                ElementTree.tostring(chapter, encoding="unicode")
                for chapter in _chapters(epub)
            )
            for block_id in block_ids:
                assert f'id="{block_id}"' in chapters


def test_each_block_div_of_the_epub_holds_the_words_of_its_block(
    excerpt_books: frozendict[str, BookFolder],
) -> None:
    for folder in excerpt_books.values():
        blocks = read_blocks(folder.blocks_json)
        with zipfile.ZipFile(folder.book_epub) as epub:
            chapters = _chapters(epub)
        # A note's div holds the divs of its blocks; only block divs count. A
        # heading is a section whose id is its block's, holding its heading
        # element, the label first. Pandoc writes its own number for a
        # reference to a footnote.
        divs = {
            div.get("id"): _text_without_footnote_numbers(div).split()
            for chapter in chapters
            for div in chapter.iter(f"{{{_XHTML}}}div")
            if (div.get("id") or "").startswith("b-")
        } | {
            section.get("id"): _text_without_footnote_numbers(
                next(child for child in section if child.tag in _HEADING_TAGS)
            ).split()
            for chapter in chapters
            for section in chapter.iter(f"{{{_XHTML}}}section")
            if (section.get("id") or "").startswith("b-")
        }
        footnotes = frozenset(
            note.id for note in blocks.notes if _is_written_as_a_footnote(note)
        )
        # markdown writes the marker of a note written where it was printed
        # at the start of its first block that is not a margin note.
        markers = {
            next(
                (b for b in note.blocks if b.kind is not BlockKind.MARGIN_NOTE),
                note.blocks[0],
            ).id: note.marker.split()
            for note in blocks.notes
            if note.id not in footnotes
        }
        note_blocks = tuple(block for note in blocks.notes for block in note.blocks)
        assert divs == {
            block.id: markers.get(block.id, [])
            + (block.label.split() if block.label is not None else [])
            + "".join(
                span.text for span in block.spans if span.note_ref not in footnotes
            ).split()
            for block in (*blocks.blocks, *note_blocks)
        }


def test_each_figure_block_div_of_the_epub_holds_one_image(
    excerpt_books: frozendict[str, BookFolder],
) -> None:
    # The owner's decision: plates go into the EPUB as pictures with their
    # caption. Pandoc renames the images it packs, so they are counted.
    figure_counts = {}
    for name, folder in excerpt_books.items():
        figures = tuple(
            block.id
            for block in read_blocks(folder.blocks_json).blocks
            if block.kind is BlockKind.FIGURE
        )
        figure_counts[name] = len(figures)
        with zipfile.ZipFile(folder.book_epub) as epub:
            divs = {
                div.get("id"): div
                for chapter in _chapters(epub)
                for div in chapter.iter(f"{{{_XHTML}}}div")
            }
        for block_id in figures:
            assert len(tuple(divs[block_id].iter(f"{{{_XHTML}}}img"))) == 1, block_id
    assert {name: count for name, count in figure_counts.items() if count} == {
        "kadesh_8-17": 2,
        "kadesh_59-68": 3,
        "domesday_headings_quotes": 2,
    }


_HEADING_TAGS = frozenset(f"{{{_XHTML}}}h{level}" for level in range(1, 7))


def _chapters(epub: zipfile.ZipFile) -> tuple[ElementTree.Element, ...]:
    """The EPUB's chapter files, in order: Pandoc starts one at each level-1
    heading."""
    return tuple(
        ElementTree.fromstring(epub.read(name))
        for name in sorted(epub.namelist())
        if name.startswith("EPUB/text/ch") and name.endswith(".xhtml")
    )


def _is_written_as_a_footnote(note: Note) -> bool:
    """Whether markdown writes `note` as a Pandoc footnote at its reference:
    a referenced footnote."""
    return note.kind is NoteKind.FOOTNOTE and note.referenced


def _text_without_footnote_numbers(element: ElementTree.Element) -> str:
    """The text of `element` without the numbers of Pandoc's footnote
    references, links of class "footnote-ref"."""
    if element.get("class") == "footnote-ref":
        return element.tail or ""
    inner = "".join(_text_without_footnote_numbers(child) for child in element)
    return (element.text or "") + inner + (element.tail or "")


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
def test_the_excerpt_epubs_of_kadesh_and_gierke_pass_epubcheck(
    excerpt_books: frozendict[str, BookFolder], check_epubs: Callable[..., None]
) -> None:
    check_epubs(excerpt_books[KADESH].book_epub, excerpt_books[GIERKE].book_epub)


# The configs of the six whole books (tests/conftest.py, WHOLE_BOOK_CONFIGS)

_BOOKS_TOML = Path(__file__).parents[1] / "evaluation" / "books.toml"
_PAGE_KEYS = ("exclude_pages", "contents_pages", "plate_pages")
# The headings a run of contents pages starts with: a table of contents,
# and Gierke's analytical summary.
_CONTENTS_HEADINGS = ("CONTENTS", "TABLE DES MATI", "ANALYTICAL SUMMARY")


def test_the_evaluation_books_have_the_same_config_in_conftest_and_books_toml(
    whole_book_configs: frozendict[str, str],
) -> None:
    books = tomllib.loads(_BOOKS_TOML.read_text(encoding="utf-8"))["book"]
    assert len(books) == 4
    for book in books:
        config = tomllib.loads(whole_book_configs[book["archive_id"]])
        assert config["language"] == book["language"]
        for key in _PAGE_KEYS:
            assert config.get(key, []) == book.get(key, []), (book["name"], key)


@pytest.mark.whole_book
@pytest.mark.thread_unsafe
@pytest.mark.timeout(600)
@pytest.mark.parametrize(
    "book",
    [
        "battleofkadeshst00breauoft",
        "catherinedemedic00mariuoft",
        "domesdaybook00maituoft",
        "earlyplantagenet01stub",
        "normansineuropea00hask",
        "politicaltheorie00gieruoft",
    ],
)
def test_analyze_takes_the_whole_book_config_and_its_contents_pages_say_so(
    book: str, whole_book_toml: frozendict[str, str], tmp_path: Path
) -> None:
    folder = BookFolder(tmp_path)
    folder.book_toml.write_text(whole_book_toml[book], encoding="utf-8")
    # analyze raises when a page index is past the end of the book, or a
    # page without a text layer is not excluded.
    main(["analyze", str(tmp_path)])
    assert folder.pages_json.exists()
    config = tomllib.loads(whole_book_toml[book])
    # Each run of contents pages starts at a page with a contents heading at
    # its top (the comment of WHOLE_BOOK_CONFIGS); the pages after the first
    # of a run carry a running head, which may be the book's title.
    contents_pages = config.get("contents_pages", [])
    run_starts = tuple(
        page_index
        for page_index in contents_pages
        if page_index - 1 not in contents_pages
    )
    with open_pdf(Path(config["pdf"])) as pdf:
        for page_index in run_starts:
            top = " ".join(
                word["text"] for word in pdf.pages[page_index].extract_words()[:4]
            ).upper()
            assert any(heading in top for heading in _CONTENTS_HEADINGS), (
                page_index,
                top,
            )
