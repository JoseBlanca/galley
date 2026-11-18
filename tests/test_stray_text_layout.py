"""Excerpt tests of the plan stray-text for the stream layout: a page
number boxed apart from its running head (docs/specs/layout.md, section 3,
step 3), footnotes small against their page and one-line notes boxed as
tall as the body (step 4), and Stubbs' cut-in notes on the body's
baselines (step 2b and section 9). The expected output of each page is
that of its file in tests/fixtures/expected/stray_text/, transcribed from
the page rendered at 300 dpi. A test whose work package has not landed is
a strict xfail naming it; the task that makes it pass removes the mark.
The whole-book tests at the end hold the counts of work package 3,
deliverable 3, that layout gives."""

import json
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from galley.book_folder import BookFolder
from galley.cli import main
from galley.layout import measure_book
from galley.layout._page import page_parts
from galley.model import (
    BlocksFile,
    NoteKind,
    PageLayout,
    RemovalReason,
    RereadKind,
    WordsFile,
    block_text,
    read_blocks,
    read_lines,
    read_words,
)
from galley_eval.align import State, align, reference_side
from galley_eval.books import EvaluationBook, read_books
from galley_eval.evaluate import evaluate
from galley_eval.galley_side import words_tokens
from galley_eval.reader import ReferenceKind, Stream, read_reference_file
from galley_eval.stages import StageOutput

_EXPECTED = Path(__file__).parent / "fixtures" / "expected" / "stray_text"

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
@pytest.mark.parametrize("page", [4, 5, 6])
def test_one_line_note_boxed_as_tall_as_the_body_is_the_last_region_alone(
    excerpt_books: frozendict[str, BookFolder], page: int
) -> None:
    # Layout's half of the case: the note is the band, the page's last
    # region, apart from the body's.
    (note,) = _expected("domesday_notes", page)["footnotes"]
    band = _page_layout(excerpt_books["domesday_notes"], page).regions[-1]
    assert [" ".join(word.text for word in line.words) for line in band.lines] == [
        f"{note['marker']} {note['text']}"
    ]


@pytest.mark.pandoc
@pytest.mark.tesseract
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
@pytest.mark.parametrize("page", [0, 2])
def test_cut_in_note_on_the_body_baselines_is_taken_into_the_margin(
    excerpt_books: frozendict[str, BookFolder], page: int
) -> None:
    # The expected words are the layer's. A cut-in note's crop may be
    # re-read with Tesseract (docs/specs/reocr.md, section 3, kind 3),
    # whose kept reading replaces the layer's words in the margin: page 0's
    # "efoch" is then "eroch" (printed "epoch"). Such a word counts as in
    # the margin.
    lines = read_lines(excerpt_books["stubbs_cut_in"].lines_json)
    layout = lines.pages[page]
    expected = _expected("stubbs_cut_in", page)
    margin_words = {
        word for line in _line_texts(layout, margin=True) for word in line.split(" ")
    }
    replaced_in_margin = {
        word.text
        for record in lines.rereads
        if record.kept
        and record.page_index == page
        and record.kind is RereadKind.CUT_IN_NOTE
        for word in record.layer_words
    }
    assert set(expected["in_margin"]) <= margin_words | replaced_in_margin
    assert _in_body_lines(expected["body_lines"], layout)


@pytest.mark.pandoc
@pytest.mark.tesseract
@pytest.mark.parametrize("page", [1, 3, 4, 5])
def test_body_line_beside_a_cut_in_note_keeps_every_word(
    excerpt_books: frozendict[str, BookFolder], page: int
) -> None:
    layout = _page_layout(excerpt_books["stubbs_cut_in"], page)
    assert _in_body_lines(_expected("stubbs_cut_in", page)["body_lines"], layout)


# Whole books (plan stray-text, work package 3, deliverable 3), each count
# beside that of the starting commit a0a1675, measured on the runs of
# 18 November 2026 (runs/lists-figures/ of the main checkout).


def _whole_blocks(whole_book_run: Callable[[str], BookFolder], book: str) -> BlocksFile:
    return read_blocks(whole_book_run(book).blocks_json)


def _footnote_pages(blocks: BlocksFile) -> frozenset[int]:
    return frozenset(
        note.origin[0].page_index
        for note in blocks.notes
        if note.kind is NoteKind.FOOTNOTE
    )


# The heads whose page number the text layer boxes apart (step 3): none
# removed at a0a1675, all three now. Gierke's 16 and 84 are structure's
# (task 3.2), and Gierke's 167 is left (the plan's "Out").
@pytest.mark.whole_book
@pytest.mark.thread_unsafe
@pytest.mark.timeout(900)
@pytest.mark.parametrize(
    ("book", "page"),
    [
        ("battleofkadeshst00breauoft", 38),
        ("domesdaybook00maituoft", 200),
        ("domesdaybook00maituoft", 428),
    ],
)
def test_whole_head_with_its_page_number_boxed_apart_is_removed(
    whole_book_run: Callable[[str], BookFolder], book: str, page: int
) -> None:
    removals = _whole_blocks(whole_book_run, book).removals
    assert any(
        removal.page_index == page and removal.reason is RemovalReason.RUNNING_HEAD
        for removal in removals
    )


# The pages of Gierke's introduction that print footnotes (layout spec,
# section 3, step 4, "Small against the page"), page 40 among them: at
# a0a1675 only page 40 had a footnote, a speck "£ 2" read as one.
_GIERKE_INTRODUCTION_NOTE_PAGES = frozenset(
    (*range(15, 19), *range(23, 32), *range(34, 46), 48, 49)
)


@pytest.mark.whole_book
@pytest.mark.thread_unsafe
@pytest.mark.timeout(900)
def test_whole_gierke_introduction_footnotes_are_footnotes(
    whole_book_run: Callable[[str], BookFolder],
) -> None:
    blocks = _whole_blocks(whole_book_run, "politicaltheorie00gieruoft")
    assert _GIERKE_INTRODUCTION_NOTE_PAGES <= _footnote_pages(blocks)


# The one-line notes boxed as tall as the body (step 4): at a0a1675 each
# but Domesday's 472 is a paragraph opening "1 ", and only 472 has a
# footnote.
_ONE_LINE_NOTE_PAGES = {
    "domesdaybook00maituoft": frozenset(
        (163, 174, 185, 278, 303, 308, 315, 347, 472, 485)
    ),
    "politicaltheorie00gieruoft": frozenset((61,)),
}


@pytest.mark.whole_book
@pytest.mark.thread_unsafe
@pytest.mark.timeout(900)
@pytest.mark.parametrize("book", sorted(_ONE_LINE_NOTE_PAGES))
def test_whole_one_line_notes_are_footnotes_and_no_paragraph(
    whole_book_run: Callable[[str], BookFolder], book: str
) -> None:
    blocks = _whole_blocks(whole_book_run, book)
    pages = _ONE_LINE_NOTE_PAGES[book]
    assert pages <= _footnote_pages(blocks)
    assert not any(
        block.origin[0].page_index in pages and block_text(block).startswith("1 ")
        for block in blocks.blocks
    )


# The number of pages with a footnote at a0a1675, by book, which may not
# fall: no page loses its band. Gierke had 3, but its page 40's footnote
# was a speck, "£ 2", above the notes, where step 4 now starts the band at
# their first; that page is not counted.
_FOOTNOTE_PAGES_AT_START = {
    "normansineuropea00hask": 65,
    "earlyplantagenet01stub": 2,
    "catherinedemedic00mariuoft": 334,
    "domesdaybook00maituoft": 480,
    "politicaltheorie00gieruoft": 2,
    "battleofkadeshst00breauoft": 40,
}


@pytest.mark.whole_book
@pytest.mark.thread_unsafe
@pytest.mark.timeout(900)
@pytest.mark.parametrize("book", sorted(_FOOTNOTE_PAGES_AT_START))
def test_whole_no_page_loses_its_footnotes(
    whole_book_run: Callable[[str], BookFolder], book: str
) -> None:
    pages = _footnote_pages(_whole_blocks(whole_book_run, book))
    assert len(pages) >= _FOOTNOTE_PAGES_AT_START[book]


# Stubbs' cut-in notes on the whole book (plan stray-text, work package 4,
# deliverable 2), by the evaluation tool (tools/galley-eval) against the
# Gutenberg edition. At a0a1675 (runs/lists-figures/), 169 of the
# reference's 467 margin notes were in the body, 291 margin notes; on 18
# November 2026 with the shortened-row test by size, 46 and 413.
_STUBBS = "earlyplantagenet01stub"
_STUBBS_NOTES_IN_BODY_MOST = 110
# Layout's cut-in words that the words' alignment pairs with the
# reference's body, not a margin note: 24 at a0a1675, of 922 cut-in words;
# 31 of 1,512 with the test by size, the 7 added on pages 37, 51, 96, 175,
# 244, 247 and 264 ("Coinage" on 37 and "attached" on 51 are note words
# the alignment paired with the body). The plan allows 20 more.
_STUBBS_CUT_IN_BODY_WORDS_AT_START = 24
_STUBBS_CUT_IN_BODY_WORDS_MORE = 20
_ALIGNED = frozenset((State.MATCHED, State.CHANGED, State.SPLIT, State.GLUED))


def _stubbs_evaluation_book() -> EvaluationBook:
    books = read_books(Path(__file__).parents[1] / "evaluation" / "books.toml")
    return next(book for book in books if book.archive_id == _STUBBS)


def _gutenberg_html(books_dir: Path, book: EvaluationBook) -> Path:
    html = books_dir / "gutenberg" / book.html_name
    if not html.is_file():
        pytest.skip(f"{html} is missing; run `uv run python scripts/fetch_samples.py`")
    return html


@pytest.mark.whole_book
@pytest.mark.pandoc
@pytest.mark.thread_unsafe
@pytest.mark.timeout(900)
def test_whole_stubbs_cut_in_notes_left_in_the_body_are_at_most_110(
    whole_book_run: Callable[[str], BookFolder], books_dir: Path, tmp_path: Path
) -> None:
    book = _stubbs_evaluation_book()
    html = _gutenberg_html(books_dir, book)
    # The run's folder is read only: markdown is written in a copy.
    folder = BookFolder(tmp_path / _STUBBS)
    shutil.copytree(whole_book_run(_STUBBS).root, folder.root)
    main(["markdown", str(folder.root)])
    scores = {
        output.output: output.margin_notes
        for output in evaluate(book, folder, html).scorecard.outputs
    }
    margin_notes = scores[StageOutput.MARKDOWN]
    assert margin_notes is not None
    assert margin_notes.in_body <= _STUBBS_NOTES_IN_BODY_MOST


def _cut_in_words(words: WordsFile) -> frozenset[tuple[int, int]]:
    """The cut-in words layout takes out of the body column of each page of
    `words` (layout spec, section 3, step 2b), as (page index, place among
    the page's words)."""
    measures = measure_book(words)
    assert measures is not None
    return frozenset(
        (page.index, place)
        for page in words.pages
        if page.words
        for parts in (page_parts(page.words, page.index, measures),)
        for cut_in in ((*parts.left_cut_in, *parts.right_cut_in),)
        for place, word in enumerate(page.words)
        if any(word is moved for moved in cut_in)
    )


@pytest.mark.whole_book
@pytest.mark.thread_unsafe
@pytest.mark.timeout(900)
def test_whole_stubbs_cut_in_words_paired_with_the_body_rise_by_at_most_20(
    whole_book_run: Callable[[str], BookFolder], books_dir: Path
) -> None:
    book = _stubbs_evaluation_book()
    html = _gutenberg_html(books_dir, book)
    folder = whole_book_run(_STUBBS)
    words = read_words(folder.words_json)
    reference = read_reference_file(
        html, book.rules, book.html_sha256, ends_at=book.reference_ends_at
    )
    prepared = reference_side(reference)
    tokens = words_tokens(words, read_lines(folder.lines_json))
    alignment = align(reference, tokens, prepared)
    cut_in = _cut_in_words(words)
    # Each word's tokens, in the order words_tokens gives them.
    token = 0
    paired_with_body = 0
    for page in words.pages:
        for place, word in enumerate(page.words):
            count = len(word.text.split())
            pairings = tuple(
                alignment.pairings[alignment.galley_pairing[index]]
                for index in range(token, token + count)
            )
            token += count
            if (page.index, place) in cut_in and any(
                pairing.state in _ALIGNED
                and pairing.reference_indices
                and prepared.places[pairing.reference_indices[0]].kind
                is not ReferenceKind.MARGIN_NOTE
                and prepared.places[pairing.reference_indices[0]].stream is Stream.BODY
                for pairing in pairings
            ):
                paired_with_body += 1
    assert token == len(tokens)
    assert paired_with_body <= (
        _STUBBS_CUT_IN_BODY_WORDS_AT_START + _STUBBS_CUT_IN_BODY_WORDS_MORE
    )
