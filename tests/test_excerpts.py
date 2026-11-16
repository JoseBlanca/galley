"""The committed excerpt PDFs are the integration fixtures of every stage,
and the reference pages of the layout and structure specs are checked on
them exactly."""

import json
from pathlib import Path
from typing import Any

import pytest

from galley.book_folder import BookFolder
from galley.errors import FidelityBoundary
from galley.fidelity import check_stage, read_markdown
from galley.model import (
    BlockKind,
    BlocksFile,
    LinesFile,
    NoteKind,
    Origin,
    block_text,
    read_blocks,
    read_lines,
    read_words,
)
from galley.text_layer import open_pdf

# The excerpts that scripts/fetch_samples.py cuts, with their page counts.
EXPECTED_EXCERPT_PAGES = {
    "kadesh_8-17": 10,
    "gierke_86-93_270-271": 10,
    "haskins_eval": 10,
    "stubbs_51_56-64": 10,
    "domesday_74-83": 10,
    "mariejol_210-219": 10,
    "haskins_quotes_index": 10,
    "stubbs_summaries_index": 10,
    "domesday_headings_quotes": 10,
    "mariejol_headings_verse": 6,
    "kadesh_59-68": 10,
}

# The pages of each excerpt, by index in the excerpt, that have no word in
# their text layer, as scripts/fetch_samples.py describes them: Kadesh's
# blank page and Haskins' blank page before the index. Every other page
# has words.
PAGES_WITHOUT_WORDS = {
    "kadesh_8-17": (9,),
    "gierke_86-93_270-271": (),
    "haskins_eval": (8,),
    "stubbs_51_56-64": (),
    "domesday_74-83": (),
    "mariejol_210-219": (),
    "haskins_quotes_index": (),
    "stubbs_summaries_index": (),
    "domesday_headings_quotes": (),
    "mariejol_headings_verse": (),
    "kadesh_59-68": (),
}


def test_every_excerpt_is_committed(excerpt_pdf: frozendict[str, Path]) -> None:
    assert set(excerpt_pdf) == set(EXPECTED_EXCERPT_PAGES)


@pytest.mark.parametrize("name", sorted(EXPECTED_EXCERPT_PAGES))
def test_excerpt_has_its_pages_and_words_on_each_but_its_blank_pages(
    excerpt_pdf: frozendict[str, Path], name: str
) -> None:
    with open_pdf(excerpt_pdf[name]) as pdf:
        assert len(pdf.pages) == EXPECTED_EXCERPT_PAGES[name]
        pages_without_words = tuple(
            page_index
            for page_index, page in enumerate(pdf.pages)
            if not page.extract_words()
        )

    assert pages_without_words == PAGES_WITHOUT_WORDS[name]


# The reference pages (layout spec section 8, structure spec section 9)
#
# Each file of tests/fixtures/expected/ holds what galley must give on one
# reference page, or on one pair of pages across a page break, as checked
# by eye against the page image: its "checked" line says by whom and when,
# and "changed" says what a later task changed and who checked that. The
# expected values are those files, compared exactly; boxes are not compared.
#
# Two files record what the excerpt gives, not what the whole book gives
# (their "excerpt_only" says why): Gierke 270, whose head line "Notes. 185"
# stays, and Mariéjol 210, whose foot line with the signature and "(l93)"
# stays. The running-head and signature rules compare a page with others
# that the excerpt lacks; the whole_book test of tests/test_structure.py
# checks both pages on the whole books.

EXPECTED_DIR = Path(__file__).parent / "fixtures" / "expected"
REFERENCE_PAGES = tuple(
    sorted(path.stem for path in EXPECTED_DIR.glob("*_page[0-9]*.json"))
)
PAGE_BREAK_PAIRS = tuple(
    sorted(path.stem for path in EXPECTED_DIR.glob("*_pages[0-9]*.json"))
)


def _expected(name: str) -> dict[str, Any]:
    return json.loads((EXPECTED_DIR / f"{name}.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def excerpt_outputs(
    excerpt_books: frozendict[str, BookFolder],
) -> frozendict[str, tuple[LinesFile, BlocksFile]]:
    """lines.json and blocks.json of each excerpt's run, read once."""
    return frozendict(
        {
            name: (read_lines(folder.lines_json), read_blocks(folder.blocks_json))
            for name, folder in excerpt_books.items()
        }
    )


def _pages(origin: tuple[Origin, ...]) -> list[int]:
    return [part.page_index for part in origin]


def _blocks_and_notes_on(blocks: BlocksFile, pages: tuple[int, ...]) -> dict[str, Any]:
    """The blocks and notes with lines on every page of `pages`, in order."""

    def on_pages(origin: tuple[Origin, ...]) -> bool:
        return all(page in _pages(origin) for page in pages)

    return {
        "blocks": [
            {
                "kind": block.kind.value,
                "text": block_text(block),
                "pages": _pages(block.origin),
            }
            for block in blocks.blocks
            if on_pages(block.origin)
        ],
        "notes": [
            {
                "marker": note.marker,
                "blocks": [
                    {"kind": block.kind.value, "text": block_text(block)}
                    for block in note.blocks
                ],
                "pages": _pages(note.origin),
            }
            for note in blocks.notes
            if on_pages(note.origin)
        ],
    }


def _structure_of_page(blocks: BlocksFile, page: int) -> dict[str, Any]:
    return _blocks_and_notes_on(blocks, (page,)) | {
        "removals": [
            {"reason": removal.reason.value, "text": removal.text}
            for removal in blocks.removals
            if removal.page_index == page
        ],
        "word_changes": [
            {
                "before": list(change.before),
                "after": list(change.after),
                "reason": change.reason.value,
            }
            for change in blocks.word_changes
            if change.page_index == page
        ],
        "page_numbers": [
            {"text": number.text, "position": number.position.value}
            for number in blocks.page_numbers
            if number.page_index == page
        ],
    }


def test_every_reference_page_and_page_break_pair_has_its_expected_file() -> None:
    # Layout spec section 8 lists 15 reference pages; structure spec section
    # 9 adds the two pairs.
    assert len(REFERENCE_PAGES) == 15
    assert PAGE_BREAK_PAIRS == ("haskins_eval_pages1-2", "stubbs_51_56-64_pages4-5")


@pytest.mark.parametrize("name", REFERENCE_PAGES)
def test_reference_page_layout_gives_its_regions(
    excerpt_outputs: frozendict[str, tuple[LinesFile, BlocksFile]], name: str
) -> None:
    expected = _expected(name)
    lines, _ = excerpt_outputs[expected["excerpt"]]
    page = next(page for page in lines.pages if page.index == expected["page"])
    regions = [
        [" ".join(word.text for word in line.words) for line in region.lines]
        for region in page.regions
    ]
    assert regions == expected["layout"]


@pytest.mark.parametrize("name", REFERENCE_PAGES)
def test_reference_page_structure_gives_its_blocks_notes_removals_and_numbers(
    excerpt_outputs: frozendict[str, tuple[LinesFile, BlocksFile]], name: str
) -> None:
    expected = _expected(name)
    _, blocks = excerpt_outputs[expected["excerpt"]]
    actual = _structure_of_page(blocks, expected["page"])
    assert actual == {key: expected[key] for key in actual}


@pytest.mark.parametrize("name", PAGE_BREAK_PAIRS)
def test_reference_page_break_pair_gives_the_blocks_and_joins_across_the_break(
    excerpt_outputs: frozendict[str, tuple[LinesFile, BlocksFile]], name: str
) -> None:
    # A pair holds the blocks and notes with lines on both pages, and the
    # word changes of the first page, where a join across the break is
    # recorded.
    expected = _expected(name)
    _, blocks = excerpt_outputs[expected["excerpt"]]
    first, _ = expected["pages"]
    actual = _blocks_and_notes_on(blocks, tuple(expected["pages"])) | {
        "word_changes": _structure_of_page(blocks, first)["word_changes"]
    }
    assert actual == {key: expected[key] for key in actual}


@pytest.mark.parametrize("name", sorted(EXPECTED_EXCERPT_PAGES))
def test_fidelity_check_passes_on_the_excerpt_at_every_boundary(
    excerpt_books: frozendict[str, BookFolder], name: str
) -> None:
    folder = excerpt_books[name]
    words = read_words(folder.words_json)
    lines = read_lines(folder.lines_json)
    blocks = read_blocks(folder.blocks_json)
    check_stage(FidelityBoundary.LAYOUT, words, lines)
    check_stage(FidelityBoundary.STRUCTURE, lines, blocks)
    markdown = read_markdown(folder.book_md.read_text(encoding="utf-8"))
    check_stage(FidelityBoundary.MARKDOWN, blocks, markdown)


# Notes (structure spec section 11), on the reference pages of section 9,
# "The second plan", before the owner checks the whole pages.

MARIEJOL = "mariejol_210-219"
DOMESDAY = "domesday_74-83"


def _notes_on(blocks: BlocksFile, page: int) -> tuple[tuple[str, list[int]], ...]:
    """The marker and the pages of each note that has lines on `page`."""
    return tuple(
        (note.marker, _pages(note.origin))
        for note in blocks.notes
        if page in _pages(note.origin)
    )


def test_footnote_two_on_one_line_domesday_76_gives_two_notes(
    excerpt_outputs: frozendict[str, tuple[LinesFile, BlocksFile]],
) -> None:
    _, blocks = excerpt_outputs[DOMESDAY]
    notes = tuple(note for note in blocks.notes if _pages(note.origin) == [2])
    assert tuple(
        (note.marker, block_text(note.blocks[0]).split()[0]) for note in notes[:3]
    ) == (("1", "Dialogus,"), ("2", "Dialogus,"), ("z", "Will."))


def test_footnote_run_on_from_mariejol_213_is_one_note_on_214(
    excerpt_outputs: frozendict[str, tuple[LinesFile, BlocksFile]],
) -> None:
    _, blocks = excerpt_outputs[MARIEJOL]
    assert _notes_on(blocks, 4) == (
        ("(4)", [3, 4]),
        ("(t)", [4]),
        ("(a)", [4]),
        ("(3J", [4]),
    )


def test_footnote_left_in_the_body_mariejol_210_stays_paragraphs_not_run_on(
    excerpt_outputs: frozendict[str, tuple[LinesFile, BlocksFile]],
) -> None:
    # The markers read 1, 2, 3, none, 11, 5: out of order, so the notes stay
    # in the body, each a paragraph of page 210 alone (structure spec,
    # sections 11 and 16).
    _, blocks = excerpt_outputs[MARIEJOL]
    led = tuple(
        (block_text(block).split()[0], _pages(block.origin))
        for block in blocks.blocks
        if 0 in _pages(block.origin)
    )[-6:]
    assert led == (
        ("(t)", [0]),
        ("(2)", [0]),
        ("(3)", [0]),
        ("U)", [0]),
        ("li)", [0]),
        ("(S)", [0]),
    )
    assert _notes_on(blocks, 0) == ()


def test_footnote_left_in_the_body_mariejol_217_is_taken_as_a_note(
    excerpt_outputs: frozendict[str, tuple[LinesFile, BlocksFile]],
) -> None:
    _, blocks = excerpt_outputs[MARIEJOL]
    assert _notes_on(blocks, 7)[0] == ("(I)", [7])
    assert not any(
        block_text(block).startswith("(I)")
        for block in blocks.blocks
        if 7 in _pages(block.origin)
    )


def _references_on(blocks: BlocksFile, page: int) -> tuple[tuple[str, str], ...]:
    """For each reference in the body blocks that start on `page`: the word
    it was printed in, rebuilt from the spans around it, and the marker of
    its note."""
    markers = {note.id: note.marker for note in blocks.notes}
    found: list[tuple[str, str]] = []
    for block in blocks.blocks:
        if block.origin[0].page_index != page:
            continue
        for position, span in enumerate(block.spans):
            if span.note_ref is None:
                continue
            before = block.spans[position - 1].text if position > 0 else ""
            after = (
                block.spans[position + 1].text
                if position + 1 < len(block.spans)
                else ""
            )
            word = (
                (before.split(" ")[-1] if before else "")
                + span.text
                + (after.split(" ")[0] if after else "")
            )
            found.append((word, markers[span.note_ref]))
    return tuple(found)


def test_referenced_domesday_74_links_seven_glued_references(
    excerpt_outputs: frozendict[str, tuple[LinesFile, BlocksFile]],
) -> None:
    _, blocks = excerpt_outputs[DOMESDAY]
    assert _references_on(blocks, 0) == (
        ("pleased1/", "1"),
        ("it2.'", "3"),
        ("free3.", "3"),
        ("things4.", "4"),
        ("themselves5.'", "6"),
        ("would6.'", "«"),
        ("mercy7.'", "7"),
    )
    assert all(note.referenced for note in blocks.notes if _pages(note.origin) == [0])


def test_referenced_domesday_75_links_references_to_misread_markers(
    excerpt_outputs: frozendict[str, tuple[LinesFile, BlocksFile]],
) -> None:
    _, blocks = excerpt_outputs[DOMESDAY]
    assert _references_on(blocks, 1)[:3] == (
        ("day1.'", "1"),
        ("land2.", "2"),
        ("land3.", "9"),
    )


def test_referenced_domesday_83_links_shillings_and_pence_references(
    excerpt_outputs: frozendict[str, tuple[LinesFile, BlocksFile]],
) -> None:
    _, blocks = excerpt_outputs[DOMESDAY]
    words = tuple(word for word, _ in _references_on(blocks, 8))
    assert "12s.2" in words
    assert "30d8" in words
    assert not any(word.startswith("£") for word in words)


def test_referenced_haskins_132_and_133_link_signs(
    excerpt_outputs: frozendict[str, tuple[LinesFile, BlocksFile]],
) -> None:
    _, blocks = excerpt_outputs["haskins_eval"]
    assert _references_on(blocks, 1) == (("^", "*"), ("protojournalist,^", "*"))


def test_referenced_kadesh_10_links_notes_12_to_14_and_leaves_10_and_11(
    excerpt_outputs: frozendict[str, tuple[LinesFile, BlocksFile]],
) -> None:
    _, blocks = excerpt_outputs["kadesh_8-17"]
    assert ("Kadesh,12", "12") in _references_on(blocks, 1)
    assert (";13", "13") in _references_on(blocks, 1)
    assert ("above).'*", "u") in _references_on(blocks, 1)
    assert tuple(
        (note.marker, note.referenced)
        for note in blocks.notes
        if _pages(note.origin)[0] == 2
    )[:2] == (("\"'", False), ("11", False))


def test_referenced_mariejol_214_leaves_note_1_unreferenced(
    excerpt_outputs: frozendict[str, tuple[LinesFile, BlocksFile]],
) -> None:
    _, blocks = excerpt_outputs[MARIEJOL]
    assert tuple(
        (note.marker, note.referenced)
        for note in blocks.notes
        if _pages(note.origin) == [4]
    ) == (("(t)", False), ("(a)", True), ("(3J", True))


def test_endnote_gierke_270_and_271_give_endnotes_291_to_302(
    excerpt_outputs: frozendict[str, tuple[LinesFile, BlocksFile]],
) -> None:
    # The end of note 290 at the top of page 270 is an endnote without a
    # marker, not joined to the last paragraph of page 93 (structure spec,
    # section 12).
    _, blocks = excerpt_outputs["gierke_86-93_270-271"]
    endnotes = tuple(note for note in blocks.notes if note.kind is NoteKind.ENDNOTE)
    assert tuple(note.marker for note in endnotes) == (
        "",
        *(f"{n}." for n in range(291, 303)),
    )
    assert _pages(endnotes[0].origin) == [8]
    assert not any(note.referenced for note in endnotes)
    assert not any(
        8 in _pages(block.origin)
        for block in blocks.blocks
        if block.kind is BlockKind.PARAGRAPH
    )


def test_endnote_gierke_270_margin_notes_go_inside_their_endnotes(
    excerpt_outputs: frozendict[str, tuple[LinesFile, BlocksFile]],
) -> None:
    # Each margin note beside an endnote's line is a block of that note,
    # before its text (structure spec, section 13, rule 5).
    _, blocks = excerpt_outputs["gierke_86-93_270-271"]
    assert not any(
        block.kind is BlockKind.MARGIN_NOTE and _pages(block.origin)[0] in (8, 9)
        for block in blocks.blocks
    )
    note_292 = next(note for note in blocks.notes if note.marker == "292.")
    assert tuple(block.kind for block in note_292.blocks) == (
        BlockKind.MARGIN_NOTE,
        BlockKind.PARAGRAPH,
    )
