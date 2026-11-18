"""Excerpt tests of the plan stray-text for the stream layout: a page
number boxed apart from its running head (docs/specs/layout.md, section 3,
step 3), footnotes small against their page and one-line notes boxed as
tall as the body (step 4), and Stubbs' cut-in notes on the body's
baselines (step 2b and section 9). The expected output of each page is
that of its file in tests/fixtures/expected/stray_text/, transcribed from
the page rendered at 300 dpi. A test whose work package has not landed is
a strict xfail naming it; the task that makes it pass removes the mark."""

import json
from pathlib import Path
from typing import Any

import pytest

from galley.book_folder import BookFolder
from galley.model import (
    NoteKind,
    PageLayout,
    RemovalReason,
    block_text,
    read_blocks,
    read_lines,
)

_EXPECTED = Path(__file__).parent / "fixtures" / "expected" / "stray_text"

_TASK_3_3 = "task 3.3 of docs/plans/stray-text.md: the footnote band and one-line notes"
_TASK_4_1 = (
    "task 4.1 of docs/plans/stray-text.md: the shortened-row test by size in "
    "the cut-in zones"
)
# A margin region of Stubbs is a column of a note, at most about 60 pt wide;
# a body region spans the text column, 268 pt.
_MARGIN_REGION_MOST_PT = 120.0


def _expected(excerpt: str, page: int) -> dict[str, Any]:
    return json.loads(
        (_EXPECTED / f"{excerpt}_page{page}.json").read_text(encoding="utf-8")
    )["expected"]


def _page_layout(folder: BookFolder, page: int) -> PageLayout:
    return read_lines(folder.lines_json).pages[page]


def _line_texts(layout: PageLayout, *, margin: bool) -> list[str]:
    """The text of each line of the page's margin regions, or of its other
    regions, words joined by one space."""
    return [
        " ".join(word.text for word in line.words)
        for region in layout.regions
        if (region.box.x1 - region.box.x0 <= _MARGIN_REGION_MOST_PT) is margin
        for line in region.lines
    ]


def _in_body_lines(texts: list[str], layout: PageLayout) -> bool:
    """Whether each of `texts`, words joined by one space, is part of one
    line of the page's body regions: no word of it moved into a margin."""
    lines = _line_texts(layout, margin=False)
    return all(any(text in line for line in lines) for text in texts)


# The running head with its page number boxed apart (step 3).


@pytest.mark.pandoc
@pytest.mark.tesseract
@pytest.mark.parametrize(
    ("excerpt", "page"),
    [("kadesh_29-38", 9), ("domesday_front_flow", 9), ("domesday_notes", 7)],
)
def test_page_number_boxed_above_the_head_is_one_head_line_with_it(
    excerpt_books: frozendict[str, BookFolder], excerpt: str, page: int
) -> None:
    head_region = _page_layout(excerpt_books[excerpt], page).regions[0]
    assert [
        " ".join(word.text for word in line.words) for line in head_region.lines
    ] == [_expected(excerpt, page)["head_line"]]


@pytest.mark.pandoc
@pytest.mark.tesseract
@pytest.mark.parametrize(
    ("excerpt", "page"),
    [("kadesh_29-38", 9), ("domesday_notes", 7), ("domesday_notes", 8)],
)
def test_head_with_its_page_number_boxed_apart_is_removed_as_a_running_head(
    excerpt_books: frozendict[str, BookFolder], excerpt: str, page: int
) -> None:
    expected = _expected(excerpt, page)
    removals = read_blocks(excerpt_books[excerpt].blocks_json).removals
    assert {
        (removal.reason, removal.text)
        for removal in removals
        if removal.page_index == page
        and removal.reason in {RemovalReason.RUNNING_HEAD, RemovalReason.PAGE_NUMBER}
    } == {
        (RemovalReason.RUNNING_HEAD, expected["running_head"]),
        (RemovalReason.PAGE_NUMBER, expected["page_number"]),
    }


# Footnotes (step 4).


def _footnotes_of_page(folder: BookFolder, page: int) -> list[tuple[str, str]]:
    return [
        (note.marker, " ".join(block_text(block) for block in note.blocks))
        for note in read_blocks(folder.blocks_json).notes
        if note.kind is NoteKind.FOOTNOTE and note.origin[0].page_index == page
    ]


@pytest.mark.pandoc
@pytest.mark.tesseract
@pytest.mark.xfail(strict=True, reason=_TASK_3_3)
@pytest.mark.parametrize("page", [4, 5, 6])
def test_one_line_note_boxed_as_tall_as_the_body_is_a_footnote(
    excerpt_books: frozendict[str, BookFolder], page: int
) -> None:
    folder = excerpt_books["domesday_notes"]
    expected = _expected("domesday_notes", page)
    assert _footnotes_of_page(folder, page) == [
        (note["marker"], note["text"]) for note in expected["footnotes"]
    ]
    assert expected["no_body_block"] not in [
        block_text(block)
        for block in read_blocks(folder.blocks_json).blocks
        if block.origin[0].page_index == page
    ]


@pytest.mark.pandoc
@pytest.mark.tesseract
@pytest.mark.parametrize("page", [1, 2, 3, 4, 5, 9])
def test_gierke_introduction_footnotes_are_footnotes_from_the_first(
    excerpt_books: frozendict[str, BookFolder], page: int
) -> None:
    # On this excerpt the notes are small already (see the expected files'
    # "read"); the test keeps them so while step 4 changes.
    found = _footnotes_of_page(excerpt_books["gierke_notes_heads"], page)
    expected = _expected("gierke_notes_heads", page)["footnotes"]
    assert [marker for marker, _ in found] == [note["marker"] for note in expected]
    assert all(
        text.startswith(note["text_starts"])
        for (_, text), note in zip(found, expected, strict=True)
    )


# Stubbs' cut-in notes (step 2b).


@pytest.mark.pandoc
@pytest.mark.tesseract
@pytest.mark.xfail(strict=True, reason=_TASK_4_1)
@pytest.mark.parametrize("page", [0, 2])
def test_cut_in_note_on_the_body_baselines_is_taken_into_the_margin(
    excerpt_books: frozendict[str, BookFolder], page: int
) -> None:
    layout = _page_layout(excerpt_books["stubbs_cut_in"], page)
    expected = _expected("stubbs_cut_in", page)
    margin_words = {
        word for line in _line_texts(layout, margin=True) for word in line.split(" ")
    }
    assert set(expected["in_margin"]) <= margin_words
    assert _in_body_lines(expected["body_lines"], layout)


@pytest.mark.pandoc
@pytest.mark.tesseract
@pytest.mark.parametrize("page", [1, 3, 4, 5])
def test_body_line_beside_a_cut_in_note_keeps_every_word(
    excerpt_books: frozendict[str, BookFolder], page: int
) -> None:
    layout = _page_layout(excerpt_books["stubbs_cut_in"], page)
    assert _in_body_lines(_expected("stubbs_cut_in", page)["body_lines"], layout)
