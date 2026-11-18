"""Tests of the fidelity check at the markdown boundary for lists, printed
contents and their links (structure spec section 31, "The fidelity check
at the markdown boundary"; architecture section 13), on blocks written in
the test and book.md as markdown writes it, or changed by the test."""

import hashlib
from pathlib import Path

import pytest

from galley.config import BookConfig, Language
from galley.errors import ExternalProgramError, FidelityBoundary, FidelityError
from galley.fidelity import check_stage, read_markdown
from galley.markdown import render_markdown
from galley.model import (
    Block,
    BlockKind,
    BlocksFile,
    Box,
    Emphasis,
    Origin,
    Span,
)

SOURCE_PDF_SHA256 = hashlib.sha256(b"a stand-in").hexdigest()

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
) -> Block:
    return Block(
        id=block_id,
        kind=kind,
        level=level,
        label=label,
        page_number=page_number,
        heading_ref=heading_ref,
        spans=(Span(text, Emphasis.NONE, None),),
        figure=None,
        origin=(Origin(int(block_id[3:7]), Box(10.0, 20.0, 300.0, 400.0)),),
    )


def _items(
    page_index: int, labels: tuple[str, ...], first: int = 1
) -> tuple[Block, ...]:
    return tuple(
        _block(
            f"b-p{page_index:04d}-{number:03d}",
            BlockKind.LIST_ITEM,
            f"Item {number} of the list.",
            label=label,
        )
        for number, label in enumerate(labels, start=first)
    )


def _blocks_file(blocks: tuple[Block, ...]) -> BlocksFile:
    return BlocksFile(
        source_pdf_sha256=SOURCE_PDF_SHA256,
        blocks=blocks,
        notes=(),
        removals=(),
        word_changes=(),
        page_numbers=(),
    )


def _check(blocks: BlocksFile, markdown: str) -> None:
    check_stage(FidelityBoundary.MARKDOWN, blocks, read_markdown(markdown))


CONTENTS = _blocks_file(
    (
        _block("b-p0008-001", BlockKind.HEADING, "CONTENTS", level=1),
        _block(
            "b-p0008-002",
            BlockKind.CONTENTS_ENTRY,
            "The Old Masters",
            level=1,
            label="1.",
            page_number="9",
            heading_ref="b-p0036-001",
        ),
        _block(
            "b-p0008-003",
            BlockKind.CONTENTS_ENTRY,
            "Their workshops",
            level=2,
            page_number="12",
        ),
        _block(
            "b-p0008-004",
            BlockKind.CONTENTS_ENTRY,
            "New Scientists",
            level=1,
            label="2.",
            page_number="23",
            heading_ref="b-p0050-001",
        ),
        _block("b-p0036-001", BlockKind.HEADING, "The Old Masters", level=1),
        _block("b-p0036-002", BlockKind.PARAGRAPH, "The masters worked alone."),
        _block("b-p0050-001", BlockKind.HEADING, "New Scientists", level=1),
    )
)

CASES = {
    "dash-list": _blocks_file(
        (
            _block("b-p0016-001", BlockKind.PARAGRAPH, "Six kinds:"),
            *_items(16, ("—",) * 6, first=2),
            _block("b-p0017-001", BlockKind.PARAGRAPH, "After the list."),
        )
    ),
    "numbered-list": _blocks_file(_items(226, ("1.", "2.", "3.", "4.", "5."))),
    "roman-in-brackets": _blocks_file(_items(3, ("(iv)", "(v)"))),
    "capital-letters": _blocks_file(_items(3, ("A.", "B."))),
    "two-lists": _blocks_file(_items(156, ("1.", "2.", "1.", "2."))),
    "list-ended-by-a-margin-note": _blocks_file(
        (
            *_items(157, ("1.",)),
            _block("b-p0157-002", BlockKind.MARGIN_NOTE, "Wetherley"),
            *_items(157, ("2.", "3."), first=3),
        )
    ),
    "contents": CONTENTS,
}


@pytest.mark.pandoc
@pytest.mark.parametrize("blocks", CASES.values(), ids=CASES.keys())
def test_the_check_passes_on_lists_and_a_contents_as_markdown_writes_them(
    blocks: BlocksFile,
) -> None:
    _check(blocks, render_markdown(blocks, CONFIG))


@pytest.mark.pandoc
def test_the_check_counts_the_list_items_and_the_contents_links() -> None:
    blocks = _blocks_file((*CASES["two-lists"].blocks, *CONTENTS.blocks))

    words = read_markdown(render_markdown(blocks, CONFIG))

    assert words.list_item_count == 4
    assert tuple((link.block_id, link.target) for link in words.contents_links) == (
        ("b-p0008-002", "#b-p0036-001"),
        ("b-p0008-004", "#b-p0050-001"),
    )


@pytest.mark.pandoc
def test_a_list_item_holding_two_divs_is_refused() -> None:
    blocks = CASES["numbered-list"]
    written = render_markdown(blocks, CONFIG).replace(
        "    Item 1 of the list\\.\n    :::\n",
        "    Item 1 of the list\\.\n    :::\n\n    ::: {#b-p0226-099}\n    More\n    :::\n",
    )

    with pytest.raises(ExternalProgramError, match="OrderedList element"):
        read_markdown(written)


@pytest.mark.pandoc
def test_a_written_page_number_is_an_invented_word() -> None:
    written = render_markdown(CONTENTS, CONFIG).replace(
        "[New Scientists](#b-p0050-001)", "[New Scientists](#b-p0050-001) 23"
    )

    with pytest.raises(FidelityError, match="'23'"):
        _check(CONTENTS, written)


@pytest.mark.pandoc
@pytest.mark.parametrize(
    "target",
    ["#b-p0036-002", "#b-p0008-003", "https://example.org/", "#nowhere"],
    ids=["a-paragraph", "another-entry", "outside-the-book", "no-block"],
)
def test_a_contents_link_to_anything_but_a_heading_fails(target: str) -> None:
    written = render_markdown(CONTENTS, CONFIG).replace("(#b-p0050-001)", f"({target})")

    with pytest.raises(FidelityError, match="not the id of a heading"):
        _check(CONTENTS, written)


@pytest.mark.pandoc
def test_fewer_contents_links_than_entries_with_a_heading_reference_fail() -> None:
    written = render_markdown(CONTENTS, CONFIG).replace(
        "[New Scientists](#b-p0050-001)", "New Scientists"
    )

    with pytest.raises(
        FidelityError,
        match="entries with a heading reference in blocks.json: 2; "
        "contents links in the Markdown: 1",
    ):
        _check(CONTENTS, written)


@pytest.mark.pandoc
def test_a_link_outside_a_contents_entry_is_refused() -> None:
    written = render_markdown(CONTENTS, CONFIG).replace(
        "The masters worked alone\\.", "The masters [worked](#b-p0036-001) alone\\."
    )

    with pytest.raises(
        ExternalProgramError, match=r"Link element in block b-p0036-002"
    ):
        read_markdown(written)


@pytest.mark.pandoc
def test_a_contents_link_with_attributes_is_refused() -> None:
    written = render_markdown(CONTENTS, CONFIG).replace(
        "(#b-p0050-001)", "(#b-p0050-001){.chapter}"
    )

    with pytest.raises(
        ExternalProgramError, match=r"Link element in block b-p0008-004"
    ):
        read_markdown(written)


@pytest.mark.pandoc
def test_a_list_item_written_outside_a_list_fails_on_the_count_of_items() -> None:
    blocks = CASES["numbered-list"]
    written = render_markdown(blocks, CONFIG).replace(
        "5.  ::: {#b-p0226-005 .list-item}\n    Item 5 of the list\\.\n    :::\n",
        "::: {.list-break}\n:::\n\n::: {#b-p0226-005 .list-item}\nItem 5 of the "
        "list\\.\n:::\n",
    )

    with pytest.raises(
        FidelityError,
        match="list items in blocks.json: 5; items of lists of list items in "
        "the Markdown: 4",
    ):
        _check(blocks, written)


@pytest.mark.pandoc
def test_a_list_items_label_written_as_text_is_an_invented_word() -> None:
    blocks = CASES["numbered-list"]
    written = render_markdown(blocks, CONFIG).replace(
        "    Item 2 of the list", "    2\\. Item 2 of the list"
    )

    with pytest.raises(FidelityError, match="'2.'"):
        _check(blocks, written)


@pytest.mark.pandoc
def test_an_ordered_list_of_contents_entries_is_refused() -> None:
    written = (
        render_markdown(CONTENTS, CONFIG)
        .replace("-   ::: {#b-p0008-002", "1.  ::: {#b-p0008-002")
        .replace("-   ::: {#b-p0008-004", "2.  ::: {#b-p0008-004")
    )

    with pytest.raises(ExternalProgramError, match="OrderedList element"):
        read_markdown(written)


@pytest.mark.pandoc
def test_two_contents_links_swapped_fail_though_each_targets_a_heading() -> None:
    written = (
        render_markdown(CONTENTS, CONFIG)
        .replace("(#b-p0036-001)", "(#swap)")
        .replace("(#b-p0050-001)", "(#b-p0036-001)")
        .replace("(#swap)", "(#b-p0050-001)")
    )

    with pytest.raises(
        FidelityError,
        match="the contents entry b-p0008-002 links to '#b-p0050-001', and its "
        "heading reference is '#b-p0036-001'",
    ):
        _check(CONTENTS, written)


# The markers Pandoc shows (structure spec section 31).


@pytest.mark.pandoc
@pytest.mark.parametrize(
    ("case", "printed", "written"),
    [
        ("numbered-list", "1.  ::: {#b-p0226-001", "7.  ::: {#b-p0226-001"),
        ("numbered-list", "1.  ::: {#b-p0226-001", "1)  ::: {#b-p0226-001"),
        ("capital-letters", "A.  ::: {#b-p0003-001", "a.  ::: {#b-p0003-001"),
        ("roman-in-brackets", "(iv) ::: {#b-p0003-001", "(i)  ::: {#b-p0003-001"),
        ("dash-list", "-   ::: {#b-p0016-002", "1.  ::: {#b-p0016-002"),
    ],
    ids=["start", "delimiter", "style", "roman-start", "bullet-to-number"],
)
def test_a_list_whose_shown_marker_is_not_the_items_label_fails(
    case: str, printed: str, written: str
) -> None:
    blocks = CASES[case]
    markdown = render_markdown(blocks, CONFIG)
    assert printed in markdown

    with pytest.raises(FidelityError, match="shows the marker"):
        _check(blocks, markdown.replace(printed, written, 1))


@pytest.mark.pandoc
def test_a_page_number_without_a_page_numbers_form_fails() -> None:
    blocks = _blocks_file(
        tuple(
            block
            if block.id != "b-p0008-003"
            else _block(
                "b-p0008-003",
                BlockKind.CONTENTS_ENTRY,
                "Their workshops",
                level=2,
                page_number="Faustus",
            )
            for block in CONTENTS.blocks
        )
    )

    with pytest.raises(FidelityError, match="'Faustus'"):
        _check(blocks, render_markdown(CONTENTS, CONFIG))
