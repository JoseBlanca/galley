"""Excerpt tests of the plan ocr-redo (docs/plans/ocr-redo.md) on
`kadesh_redo`, Kadesh's pages 8 to 16, 32 and 34 read with `ocr = "redo"`:
analyze marks the text pages `ocr` (architecture section 7b), extract reads
them with Tesseract and puts back the note references Tesseract loses
(docs/specs/extract.md, section 9), and structure makes no heading of a line
of low Tesseract confidence (docs/specs/structure.md, section 34). The
expected output of each page is that of its file in
tests/fixtures/expected/ocr_redo/, transcribed from the page image. A test
whose task has not landed is a strict xfail naming it; the task that makes
it pass removes the mark."""

import json
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import pytest

from galley.book_folder import BookFolder
from galley.model import (
    BlockKind,
    PageKind,
    RemovalReason,
    TextSource,
    block_text,
    read_blocks,
    read_lines,
    read_pages,
    read_words,
)

_EXPECTED = Path(__file__).parent / "fixtures" / "expected" / "ocr_redo"
_EXCERPT = "kadesh_redo"
# Excerpt page indices: 0 to 7 are Kadesh's text pages 8 to 15, 8 its page
# 16 (excluded), 9 its page 32 (text) and 10 its page 34 (a plate).
_EXCLUDED_PAGE = 8
_PLATE_PAGE = 10


def _expected(page: int) -> dict[str, Any]:
    return json.loads(
        (_EXPECTED / f"{_EXCERPT}_page{page}.json").read_text(encoding="utf-8")
    )["expected"]


def _holds_run(words: Sequence[str], run: Sequence[str]) -> bool:
    return any(
        tuple(words[start : start + len(run)]) == tuple(run)
        for start in range(len(words) - len(run) + 1)
    )


@pytest.mark.tesseract
def test_redo_marks_text_pages_ocr_and_keeps_the_plate_and_excluded_page(
    redo_excerpt_run: Callable[[str], BookFolder],
) -> None:
    pages = read_pages(redo_excerpt_run(_EXCERPT).pages_json)
    sources = {page.index: (page.kind, page.text_source) for page in pages.pages}
    assert sources[_PLATE_PAGE] == (PageKind.PLATE, TextSource.TEXT_LAYER)
    assert sources[_EXCLUDED_PAGE] == (PageKind.EXCLUDED, TextSource.NONE)
    assert {
        index: source
        for index, (kind, source) in sources.items()
        if kind is PageKind.TEXT
    } == {index: TextSource.OCR for index in (*range(8), 9)}
    assert pages.ocr_audit is None


@pytest.mark.tesseract
def test_page_with_a_bad_layer_has_tesseracts_words(
    redo_excerpt_run: Callable[[str], BookFolder],
) -> None:
    words = read_words(redo_excerpt_run(_EXCERPT).words_json)
    page = next(page for page in words.pages if page.index == 1)
    expected = _expected(1)
    texts = tuple(word.text for word in page.words)
    assert page.text_source is TextSource(expected["text_source"])
    assert [run for run in expected["word_runs"] if not _holds_run(texts, run)] == []
    assert [word for word in expected["absent_words"] if word in texts] == []
    # Every word is Tesseract's but those of the layer it missed: the first
    # line of note 8, "CHABAS was conscious of the thoroughness of his",
    # and "FRANÇOIS" (extract spec section 9).
    assert [word.text for word in page.words if word.ocr_confidence is None] == [
        ">C||ABA*",
        "wu",
        "eocueiou*",
        "of",
        "the",
        "thoroughness",
        "of",
        "his",
        "FftAigou",
    ]


@pytest.mark.tesseract
def test_plate_keeps_the_layers_words_under_redo(
    redo_excerpt_run: Callable[[str], BookFolder],
) -> None:
    words = read_words(redo_excerpt_run(_EXCERPT).words_json)
    page = next(page for page in words.pages if page.index == _PLATE_PAGE)
    expected = _expected(_PLATE_PAGE)
    assert page.text_source is TextSource(expected["text_source"])
    assert [word.text for word in page.words] == expected["words"]
    assert all(word.ocr_confidence is None for word in page.words)


@pytest.mark.tesseract
def test_excluded_page_keeps_the_layers_words_as_removals_under_redo(
    redo_excerpt_run: Callable[[str], BookFolder],
) -> None:
    words = read_words(redo_excerpt_run(_EXCERPT).words_json)
    expected = _expected(_EXCLUDED_PAGE)
    assert [
        removal.text
        for removal in words.removals
        if removal.page_index == _EXCLUDED_PAGE
        and removal.reason is RemovalReason(expected["removal_reason"])
    ] == expected["removed_words"]


@pytest.mark.tesseract
def test_page_number_in_the_region_drawn_where_tesseract_boxes_it_is_removed(
    redo_excerpt_run: Callable[[str], BookFolder],
) -> None:
    # The excerpt's page 0 (Kadesh's 8): its region holds the journal's
    # page number 81 where Tesseract boxes it, 12 pt below the layer's box.
    words = read_words(redo_excerpt_run(_EXCERPT).words_json)
    assert [
        (removal.text, removal.reason)
        for removal in words.removals
        if removal.page_index == 0
    ] == [("81", RemovalReason.EXCLUDED_REGION)]


@pytest.mark.tesseract
def test_layout_rereads_nothing_under_redo(
    redo_excerpt_run: Callable[[str], BookFolder],
) -> None:
    # Architecture section 7b: under redo every text page is Tesseract's
    # already, and layout re-reads no region.
    assert read_lines(redo_excerpt_run(_EXCERPT).lines_json).rereads == ()


@pytest.mark.tesseract
def test_reference_tesseract_read_as_a_sign_is_linked_from_the_layer(
    redo_excerpt_run: Callable[[str], BookFolder],
) -> None:
    blocks = read_blocks(redo_excerpt_run(_EXCERPT).blocks_json)
    expected = _expected(0)
    notes = {note.id: note for note in blocks.notes}
    linked = [
        " ".join(block_text(note_block) for note_block in notes[span.note_ref].blocks)
        for block in blocks.blocks
        if block.origin[0].page_index == 0
        for before, span in zip(block.spans, block.spans[1:], strict=False)
        if span.note_ref is not None
        and before.text.rstrip().endswith(expected["reference_after"])
    ]
    assert len(linked) == 1
    assert expected["note_holds"] in linked[0]


@pytest.mark.tesseract
def test_rows_of_hieroglyphs_read_by_tesseract_make_no_heading(
    redo_excerpt_run: Callable[[str], BookFolder],
) -> None:
    blocks = read_blocks(redo_excerpt_run(_EXCERPT).blocks_json)
    headings = [
        (block.origin[0].page_index, block_text(block))
        for block in blocks.blocks
        if block.kind is BlockKind.HEADING
    ]
    expected = [
        (heading["page"], heading["starts"])
        for page in (0, 9)
        for heading in _expected(page)["headings"]
    ]
    assert [
        (page, text[: len(starts)])
        for (page, text), (_, starts) in zip(headings, expected, strict=False)
    ] == expected
    assert len(headings) == len(expected)


@pytest.mark.tesseract
def test_line_tesseract_skipped_is_kept_from_the_layer(
    redo_excerpt_run: Callable[[str], BookFolder],
) -> None:
    # Extract spec section 9, "Layer words Tesseract missed": on Kadesh's
    # page 11 (the excerpt's page 3) Tesseract skips the line "with the
    # accession of new material made the compilation" of the right column
    # (checked on the page at 200 dpi); the layer's words of it are kept,
    # without a confidence.
    words = read_words(redo_excerpt_run(_EXCERPT).words_json)
    page = next(page for page in words.pages if page.index == 3)
    kept = tuple(word.text for word in page.words if word.ocr_confidence is None)
    assert _holds_run(
        kept,
        (
            "with",
            "the",
            "ieeeeslon",
            "of",
            "new",
            "material",
            "made",
            "the",
            "compilation",
        ),
    )
    assert page.text_source is TextSource.OCR


# The whole Kadesh book with ocr = "redo" (plan ocr-redo, work package 3,
# deliverable 2; extract spec section 9; structure spec section 34).
_KADESH_BOOK = "battleofkadeshst00breauoft"
# At least the 31 notes the layer links; 42 were measured on 19 November
# 2026 (34 by the references alone, more with the notes the layer's
# heights give back).
_KADESH_LINKED_NOTES_LEAST = 31
# The layer's 3 headings: the article's title, the caption of the battle
# plan on page 39 (a false heading with the layer too) and "ADDENDUM".
_KADESH_HEADING_PAGES = (8, 39, 66)


@pytest.mark.whole_book
@pytest.mark.tesseract
@pytest.mark.thread_unsafe
@pytest.mark.timeout(900)
def test_whole_kadesh_with_redo_links_at_least_the_layers_notes(
    whole_book_run: Callable[[str], BookFolder],
) -> None:
    notes = read_blocks(whole_book_run(_KADESH_BOOK).blocks_json).notes
    assert sum(note.referenced for note in notes) >= _KADESH_LINKED_NOTES_LEAST


@pytest.mark.whole_book
@pytest.mark.tesseract
@pytest.mark.thread_unsafe
@pytest.mark.timeout(900)
def test_whole_kadesh_with_redo_has_the_layers_headings_and_none_of_hieroglyphs(
    whole_book_run: Callable[[str], BookFolder],
) -> None:
    blocks = read_blocks(whole_book_run(_KADESH_BOOK).blocks_json).blocks
    assert (
        tuple(
            block.origin[0].page_index
            for block in blocks
            if block.kind is BlockKind.HEADING
        )
        == _KADESH_HEADING_PAGES
    )
