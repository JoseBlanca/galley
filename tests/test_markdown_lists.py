"""Tests of markdown's lists and printed contents (structure spec sections
31 and 32), on blocks written in the test, read back by Pandoc."""

import hashlib
import json
import re
import shutil
import subprocess
import zipfile
from pathlib import Path
from typing import Any

import pytest

from galley.book_folder import BookFolder
from galley.config import BookConfig, Language
from galley.errors import InputFileError
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

_PDF_BYTES = b"%PDF-1.4 a stand-in: markdown reads only its hash"
SOURCE_PDF_SHA256 = hashlib.sha256(_PDF_BYTES).hexdigest()

CONFIG = BookConfig(
    pdf=Path("/books/lists.pdf"),
    title="A Book",
    authors=("A. Author",),
    language=Language.EN,
)


def _block(
    block_id: str,
    kind: BlockKind,
    text: str,
    *,
    level: int | None = None,
    label: str | None = None,
    page_number: str | None = None,
    heading_ref: str | None = None,
    spans: tuple[Span, ...] | None = None,
) -> Block:
    page_index = int(block_id[3:7])
    return Block(
        id=block_id,
        kind=kind,
        level=level,
        label=label,
        page_number=page_number,
        heading_ref=heading_ref,
        spans=spans if spans is not None else (Span(text, Emphasis.NONE, None),),
        figure=None,
        origin=(Origin(page_index, Box(10.0, 20.0, 300.0, 400.0)),),
    )


def _item(block_id: str, label: str, text: str) -> Block:
    return _block(block_id, BlockKind.LIST_ITEM, text, label=label)


def _paragraph(block_id: str, text: str) -> Block:
    return _block(block_id, BlockKind.PARAGRAPH, text)


def _blocks_file(blocks: tuple[Block, ...], notes: tuple[Note, ...] = ()) -> BlocksFile:
    return BlocksFile(
        source_pdf_sha256=SOURCE_PDF_SHA256,
        blocks=blocks,
        notes=notes,
        removals=(),
        word_changes=(),
        page_numbers=(),
    )


def _pandoc_blocks(blocks: BlocksFile) -> list[Any]:
    """The body of book.md as Pandoc 3.14 reads it, its JSON blocks."""
    pandoc = shutil.which("pandoc")
    assert pandoc is not None
    result = subprocess.run(
        [pandoc, "--from", "markdown-smart-auto_identifiers", "--to", "json"],
        input=render_markdown(blocks, CONFIG),
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )
    return json.loads(result.stdout)["blocks"]


def _div_ids(items: list[Any]) -> tuple[object, ...]:
    """The id of the first div each list item holds."""
    return tuple(item[0]["c"][0][0] for item in items)


@pytest.mark.pandoc
def test_a_dash_list_is_a_bullet_list_of_its_items_without_their_dashes(
    lists_book: frozendict[str, BlocksFile],
) -> None:
    dash_list = lists_book["dash_list"]
    body = _pandoc_blocks(dash_list)

    assert [element["t"] for element in body] == ["Div", "BulletList", "Div"]
    items = body[1]["c"]
    assert _div_ids(items) == tuple(f"b-p0016-{number:03d}" for number in range(2, 8))
    assert all(item[0]["c"][0][1] == ["list-item"] for item in items)
    assert "—" not in render_markdown(dash_list, CONFIG)


def test_a_dash_item_is_written_as_the_spec_gives_it(
    lists_book: frozendict[str, BlocksFile],
) -> None:
    written = render_markdown(lists_book["dash_list"], CONFIG)

    assert (
        "-   ::: {#b-p0016-002 .list-item}\n"
        "    The kind 2\\, as it stands\\.\n"
        "    :::\n"
        "\n"
        "-   ::: {#b-p0016-003 .list-item}\n"
    ) in written


@pytest.mark.pandoc
def test_a_numbered_list_is_an_ordered_list_from_1_in_decimal_with_a_period(
    lists_book: frozendict[str, BlocksFile],
) -> None:
    body = _pandoc_blocks(lists_book["numbered_list"])

    assert body[1]["t"] == "OrderedList"
    attributes, items = body[1]["c"]
    assert attributes == [1, {"t": "Decimal"}, {"t": "Period"}]
    assert _div_ids(items) == tuple(f"b-p0226-{n:03d}" for n in range(2, 7))


@pytest.mark.pandoc
@pytest.mark.parametrize(
    ("labels", "start", "style", "delimiter"),
    [
        (("(iv)", "(v)", "(vi)"), 4, "LowerRoman", "TwoParens"),
        (("A.", "B."), 1, "UpperAlpha", "Period"),
        (("h.", "i.", "j."), 8, "LowerAlpha", "Period"),
        (("i.", "ii.", "iii."), 1, "LowerRoman", "Period"),
        (("9.", "10."), 9, "Decimal", "Period"),
        (("a)", "b)"), 1, "LowerAlpha", "OneParen"),
    ],
    ids=[
        "roman-in-brackets",
        "capital-letter",
        "letter-i-after-h",
        "roman-from-i",
        "nine-ten",
        "a)",
    ],
)
def test_an_ordered_item_is_read_by_pandoc_as_a_list_item_of_its_marker(
    labels: tuple[str, ...], start: int, style: str, delimiter: str
) -> None:
    blocks = _blocks_file(
        tuple(
            _item(f"b-p0003-{position:03d}", label, f"Item {position}.")
            for position, label in enumerate(labels, start=1)
        )
    )

    body = _pandoc_blocks(blocks)

    assert len(body) == 1
    assert body[0]["t"] == "OrderedList"
    attributes, items = body[0]["c"]
    assert attributes == [start, {"t": style}, {"t": delimiter}]
    assert len(items) == len(labels)


# A list ended by the gap of section 29's rule 5, and a new "1." after it,
# with nothing between them.
TWO_LISTS = _blocks_file(
    (
        _item("b-p0156-001", "1.", "Seven sokemen hold one hide."),
        _item("b-p0156-002", "2.", "Two knights hold half a hide."),
        _item("b-p0156-003", "1.", "The abbot holds the vill."),
        _item("b-p0156-004", "2.", "The priest holds a yard."),
    )
)


@pytest.mark.pandoc
def test_two_lists_with_nothing_between_are_kept_apart_by_a_list_break_div() -> None:
    body = _pandoc_blocks(TWO_LISTS)

    assert [element["t"] for element in body] == ["OrderedList", "Div", "OrderedList"]
    assert body[1]["c"] == [["", ["list-break"], []], []]
    assert _div_ids(body[0]["c"][1]) == ("b-p0156-001", "b-p0156-002")
    assert _div_ids(body[2]["c"][1]) == ("b-p0156-003", "b-p0156-004")


def test_a_dash_list_after_a_numbered_one_is_a_list_of_its_own() -> None:
    blocks = _blocks_file(
        (
            _item("b-p0003-001", "1.", "One."),
            _item("b-p0003-002", "2.", "Two."),
            _item("b-p0003-003", "—", "A dash."),
            _item("b-p0003-004", "—", "Another."),
        )
    )

    written = render_markdown(blocks, CONFIG)

    assert "::: {.list-break}\n:::\n\n-   ::: {#b-p0003-003 .list-item}" in written


# A margin note printed beside the second item, which markdown places
# before it, between the first and second.
LIST_WITH_MARGIN_NOTE = _blocks_file(
    (
        _item("b-p0157-001", "1.", "The first holder."),
        _block("b-p0157-002", BlockKind.MARGIN_NOTE, "Wetherley"),
        _item("b-p0157-003", "2.", "The second holder."),
        _item("b-p0157-004", "3.", "The third holder."),
    )
)


@pytest.mark.pandoc
def test_a_margin_note_between_two_items_ends_the_list_and_the_next_starts_at_its_value() -> (
    None
):
    body = _pandoc_blocks(LIST_WITH_MARGIN_NOTE)

    assert [element["t"] for element in body] == ["OrderedList", "Div", "OrderedList"]
    assert body[1]["c"][0] == ["b-p0157-002", ["margin-note"], []]
    assert body[2]["c"][0] == [2, {"t": "Decimal"}, {"t": "Period"}]
    assert _div_ids(body[2]["c"][1]) == ("b-p0157-003", "b-p0157-004")


def _footnote(note_id: str, text: str) -> Note:
    page_index = int(note_id[3:7])
    return Note(
        id=note_id,
        kind=NoteKind.FOOTNOTE,
        marker="1",
        blocks=(_paragraph(f"b-p{page_index:04d}-100", text),),
        origin=(Origin(page_index, Box(10.0, 500.0, 300.0, 520.0)),),
        referenced=True,
        group=None,
    )


@pytest.mark.pandoc
def test_a_footnote_of_an_item_is_defined_after_the_list_which_stays_one() -> None:
    referring = _block(
        "b-p0004-001",
        BlockKind.LIST_ITEM,
        "",
        label="1.",
        spans=(
            Span("The first holder", Emphasis.NONE, None),
            Span("1", Emphasis.NONE, "n-p0004-001"),
            Span(".", Emphasis.NONE, None),
        ),
    )
    blocks = _blocks_file(
        (referring, _item("b-p0004-002", "2.", "The second holder.")),
        (_footnote("n-p0004-001", "A hide is a measure."),),
    )

    body = _pandoc_blocks(blocks)

    assert [element["t"] for element in body] == ["OrderedList"]
    assert len(body[0]["c"][1]) == 2


def test_a_printed_note_after_an_item_ends_the_list() -> None:
    endnote = Note(
        id="n-p0005-001",
        kind=NoteKind.ENDNOTE,
        marker="1",
        blocks=(_paragraph("b-p0005-100", "An endnote."),),
        origin=(Origin(5, Box(10.0, 500.0, 300.0, 520.0)),),
        referenced=False,
        group=None,
    )
    blocks = _blocks_file(
        (
            _item("b-p0005-001", "1.", "One."),
            _item("b-p0006-001", "2.", "Two."),
        ),
        (endnote,),
    )

    written = render_markdown(blocks, CONFIG)

    assert ":::: {#n-p0005-001 .endnote}" in written
    assert "::: {.list-break}" not in written
    assert written.index(".endnote") < written.index("2.  ::: {#b-p0006-001")


@pytest.mark.pandoc
def test_a_contents_is_a_div_holding_a_bullet_list_nested_by_depth(
    lists_book: frozendict[str, BlocksFile],
) -> None:
    body = _pandoc_blocks(lists_book["contents"])

    contents = body[1]
    assert contents["t"] == "Div"
    assert contents["c"][0] == ["", ["contents"], []]
    [entries] = contents["c"][1]
    assert entries["t"] == "BulletList"
    first, second = entries["c"]
    assert first[0]["c"][0] == ["b-p0008-002", ["contents-entry"], []]
    assert first[1]["t"] == "BulletList"
    assert _div_ids(first[1]["c"]) == ("b-p0008-003",)
    assert len(second) == 1
    assert second[0]["c"][0] == ["b-p0008-004", ["contents-entry"], []]


def test_a_contents_entry_is_its_label_and_a_link_to_its_heading_without_its_page(
    lists_book: frozendict[str, BlocksFile],
) -> None:
    written = render_markdown(lists_book["contents"], CONFIG)

    assert (
        "::: contents\n"
        "-   ::: {#b-p0008-002 .contents-entry}\n"
        "    [1\\.]{.label} [The Old Masters](#b-p0036-001)\n"
        "    :::\n"
        "\n"
        "    -   ::: {#b-p0008-003 .contents-entry}\n"
        "        Their workshops\n"
        "        :::\n"
        "\n"
        "-   ::: {#b-p0008-004 .contents-entry}\n"
        "    [2\\.]{.label} [New Engineers](#b-p0050-001)\n"
        "    :::\n"
        ":::\n"
    ) in written
    assert "23" not in written


def test_an_entry_deeper_than_one_below_the_entry_before_goes_one_deeper() -> None:
    blocks = _blocks_file(
        (
            _block("b-p0008-001", BlockKind.CONTENTS_ENTRY, "Essay", level=1),
            _block("b-p0008-002", BlockKind.CONTENTS_ENTRY, "Topic", level=3),
            _block("b-p0008-003", BlockKind.CONTENTS_ENTRY, "Section", level=2),
        )
    )

    written = render_markdown(blocks, CONFIG)

    assert "\n    -   ::: {#b-p0008-002 .contents-entry}\n" in written
    assert "\n    -   ::: {#b-p0008-003 .contents-entry}\n" in written


@pytest.mark.parametrize(
    ("block", "message"),
    [
        (
            _item("b-p0003-001", "1 .", "Not a marker."),
            r"list item b-p0003-001 has the label '1 \.', which is not a list marker",
        ),
        (
            _block(
                "b-p0003-001",
                BlockKind.CONTENTS_ENTRY,
                "",
                level=1,
                heading_ref="b-p0003-002",
                spans=(
                    Span("Title", Emphasis.NONE, None),
                    Span("1", Emphasis.NONE, "n-p0003-001"),
                ),
            ),
            r"contents entry b-p0003-001 links to its heading and has a note reference",
        ),
    ],
    ids=["label-not-a-marker", "note-reference-in-a-link"],
)
def test_render_markdown_refuses_a_list_item_or_entry_it_cannot_write(
    block: Block, message: str
) -> None:
    heading = _block("b-p0003-002", BlockKind.HEADING, "Title", level=1)
    blocks = _blocks_file(
        (block, heading),
        (_footnote("n-p0003-001", "A note."),)
        if block.spans[-1].note_ref is not None
        else (),
    )

    with pytest.raises(InputFileError, match=message):
        render_markdown(blocks, CONFIG)


@pytest.mark.parametrize(
    ("block", "message"),
    [
        (
            _block("b-p0003-001", BlockKind.LIST_ITEM, "No label."),
            r"list item b-p0003-001 has no label",
        ),
        (
            _block("b-p0003-001", BlockKind.CONTENTS_ENTRY, "No depth."),
            r"contents entry b-p0003-001 has the depth None",
        ),
        (
            _block(
                "b-p0003-001",
                BlockKind.CONTENTS_ENTRY,
                "Title",
                level=1,
                heading_ref="b-p0003-009",
            ),
            r"contents entry b-p0003-001 refers to b-p0003-009, which is no heading",
        ),
    ],
    ids=["item-without-label", "entry-without-depth", "reference-to-no-heading"],
)
def test_render_markdown_refuses_a_malformed_list_item_or_entry(
    block: Block, message: str
) -> None:
    with pytest.raises(InputFileError, match=message):
        render_markdown(_blocks_file((block,)), CONFIG)


# epubcheck validates this EPUB in test_epub.py, in one call with the other
# EPUBs of hand-written blocks: Java starts in about a second and a half.
@pytest.mark.pandoc
def test_the_epub_of_lists_links_a_contents_entry_into_another_chapter(
    lists_book_epub: BookFolder,
) -> None:
    folder = lists_book_epub
    with zipfile.ZipFile(folder.book_epub) as book:
        names = book.namelist()
        chapters = {
            name: book.read(name).decode()
            for name in names
            if name.endswith(".xhtml") and "nav" not in name
        }
        style_sheet = b"".join(
            book.read(name) for name in names if name.endswith(".css")
        )
    contents_file = next(
        name for name, text in chapters.items() if 'class="contents"' in text
    )
    chapter_file = next(
        name for name, text in chapters.items() if 'id="b-p0036-001"' in text
    )
    assert contents_file != chapter_file
    chapter_name = Path(chapter_file).name
    assert re.search(
        rf'href="{re.escape(chapter_name)}#b-p0036-001"', chapters[contents_file]
    )
    assert b".contents-entry" in style_sheet
    assert b"list-style: none" in style_sheet
