"""The committed excerpt PDFs are the integration fixtures of every stage,
and the reference pages of the layout and structure specs are checked on
them exactly."""

import json
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from typing import Any

import pytest

from galley.book_folder import BookFolder
from galley.errors import FidelityBoundary
from galley.fidelity import check_stage, read_markdown
from galley.model import (
    Block,
    BlockKind,
    BlocksFile,
    LinesFile,
    NoteKind,
    Origin,
    PageKind,
    PageNumber,
    PageNumberPosition,
    RemovalReason,
    block_text,
    read_blocks,
    read_lines,
    read_pages,
    read_words,
)
from galley.text_layer import layer_words, open_pdf

# The excerpts that scripts/fetch_samples.py cuts, with their page counts.
EXPECTED_EXCERPT_PAGES = {
    "kadesh_8-17": 10,
    "gierke_86-93_270-271": 10,
    "haskins_eval": 10,
    "stubbs_51_56-64": 10,
    "domesday_74-83": 10,
    "mariejol_210-219": 10,
    "haskins_quotes_index": 11,
    "stubbs_summaries_index": 10,
    "domesday_headings_quotes": 11,
    "mariejol_headings_verse": 6,
    "kadesh_59-68": 10,
    "haskins_front": 11,
    "domesday_front_flow": 10,
    "gierke_front_flow": 10,
    "haskins_heads_notes": 13,
    "stubbs_heads": 18,
    "gierke_intro_heads": 13,
    "domesday_rereads": 11,
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
    "haskins_front": (),
    "domesday_front_flow": (),
    "gierke_front_flow": (),
    "haskins_heads_notes": (),
    "stubbs_heads": (),
    "gierke_intro_heads": (),
    "domesday_rereads": (),
}


def test_every_excerpt_is_committed(excerpt_pdf: frozendict[str, Path]) -> None:
    assert set(excerpt_pdf) == set(EXPECTED_EXCERPT_PAGES)


def _page_count_and_pages_without_words(pdf_path: Path) -> tuple[int, tuple[int, ...]]:
    with open_pdf(pdf_path) as pdf:
        return len(pdf.pages), tuple(
            page_index
            for page_index, page in enumerate(pdf.pages)
            if not page.extract_words()
        )


# The excerpts' PDFs are read side by side, each in a thread that opens its
# own document: 1.2 s with 6 threads against 3.1 s one after another,
# measured on 16 November 2026 on an M5 Pro.
_EXCERPTS_READ_AT_ONCE = 6


@pytest.fixture(scope="module")
def excerpt_pages_and_pages_without_words(
    excerpt_pdf: frozendict[str, Path],
) -> frozendict[str, tuple[int, tuple[int, ...]]]:
    """Each committed excerpt's page count and the indexes of its pages
    without a word in their text layer, by excerpt name, as pdfplumber's
    extract_words() reads them."""
    names = tuple(excerpt_pdf)
    with ThreadPoolExecutor(max_workers=_EXCERPTS_READ_AT_ONCE) as pool:
        read = tuple(
            pool.map(
                _page_count_and_pages_without_words,
                (excerpt_pdf[name] for name in names),
            )
        )
    return frozendict(zip(names, read, strict=True))


@pytest.mark.parametrize("name", sorted(EXPECTED_EXCERPT_PAGES))
def test_excerpt_has_its_pages_and_words_on_each_but_its_blank_pages(
    excerpt_pages_and_pages_without_words: frozendict[str, tuple[int, tuple[int, ...]]],
    name: str,
) -> None:
    assert excerpt_pages_and_pages_without_words[name] == (
        EXPECTED_EXCERPT_PAGES[name],
        PAGES_WITHOUT_WORDS[name],
    )


# The reference pages (layout spec section 8, structure spec section 9)
#
# Each file of tests/fixtures/expected/ holds what galley must give on one
# reference page, or on one pair of pages across a page break, as checked
# by eye against the page image: its "checked" line says by whom and when,
# "changed" says what a later task changed and who checked that, and
# "known" what the owner found galley gives wrong there, recorded and not
# yet fixed. The expected values are those files, compared exactly; boxes
# are not compared.
#
# Two files record what the excerpt gives, not what the whole book gives
# (their "excerpt_only" says why): Gierke 270, whose head line "Notes. 185"
# stays, and Mariéjol 210, whose foot line with the signature and "(l93)"
# stays. The running-head and signature rules compare a page with others
# that the excerpt lacks; the whole_book test of tests/test_structure.py
# checks both pages on the whole books. Two more, Domesday 30 and 42, record
# a footnote of page 30 that the excerpt runs on to page 42, its next text
# page.
#
# tests/fixtures/expected/owner_books_wp1/ holds, for each page of the four
# excerpts of structure spec section 26 that a case is printed on, what the
# rules of work package 1 of docs/plans/owner-books.md must give there: the
# page's removals and page numbers, and where a case needs them its notes,
# headings, heading lines and first line of the footnote band, with what
# the page image shows ("printed"), read from the 300-dpi render by the
# assistant on 17 November 2026. No test reads them yet: the rules do not
# exist, and task 1.5 of the plan writes the tests.

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


def _block_fields(block: Block) -> dict[str, Any]:
    """A block's kind and text, a heading's level and label, and an index
    entry's depth."""
    heading = (
        {"level": block.level, "label": block.label}
        if block.kind is BlockKind.HEADING
        else {"level": block.level}
        if block.kind is BlockKind.INDEX_ENTRY
        else {}
    )
    return {"kind": block.kind.value, "text": block_text(block)} | heading


def _blocks_and_notes_on(blocks: BlocksFile, pages: tuple[int, ...]) -> dict[str, Any]:
    """The blocks and notes with lines on every page of `pages`, in order."""

    def on_pages(origin: tuple[Origin, ...]) -> bool:
        return all(page in _pages(origin) for page in pages)

    return {
        "blocks": [
            _block_fields(block) | {"pages": _pages(block.origin)}
            for block in blocks.blocks
            if on_pages(block.origin)
        ],
        "notes": [
            {
                "marker": note.marker,
                "blocks": [_block_fields(block) for block in note.blocks],
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
    # 9 adds the two pairs, and, of the pages of "The second plan", the 10
    # the owner checked on 16 November 2026 (Domesday 14, 22, 30, 39, 40, 42
    # and 47, Haskins 41 and 209, Mariéjol 51).
    assert len(REFERENCE_PAGES) == 25
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


# Margin notes (structure spec, section 13), on the reference pages of
# section 9, "The second plan".


def _margin_notes_before(
    blocks: BlocksFile, page: int
) -> tuple[tuple[str, str, list[int]], ...]:
    """Each margin note of `page` in `blocks`, with the first three words
    and the pages of the paragraph after it, past other margin notes."""
    body = blocks.blocks
    placed = []
    for position, block in enumerate(body):
        if block.kind is not BlockKind.MARGIN_NOTE or _pages(block.origin) != [page]:
            continue
        after = next(
            later
            for later in body[position + 1 :]
            if later.kind is not BlockKind.MARGIN_NOTE
        )
        placed.append(
            (
                block_text(block),
                " ".join(block_text(after).split(" ")[:3]),
                _pages(after.origin),
            )
        )
    return tuple(placed)


def test_margin_note_before_domesday_75_paragraphs_whose_first_lines_it_is_beside(
    excerpt_outputs: frozendict[str, tuple[LinesFile, BlocksFile]],
) -> None:
    # Excerpt page 1 (75): each stands beside its paragraph's first line;
    # "Can the villein be pursued?" beside the page's last line, the first
    # of a paragraph that runs on to page 2. The second and third notes are
    # Tesseract's readings, kept over the layer's "dOTQ^tht villein." and
    # "Sn°inhbe pursued?" (reocr spec, section 3, kind 2).
    _, blocks = excerpt_outputs[DOMESDAY]
    assert _margin_notes_before(blocks, 1) == (
        ("Free land.", "The idea of", [1]),
        ("The unfree dom of the villein.", "If now we", [1]),
        ("Can the villein be pursued ?", "^ ^e free", [1, 2]),
    )


def test_margin_note_beside_the_middle_stubbs_58_goes_before_its_paragraph(
    excerpt_outputs: frozendict[str, tuple[LinesFile, BlocksFile]],
) -> None:
    # "His great position in Christendom", excerpt page 3 (58), stands
    # beside the middle of a paragraph that starts on page 2 (57): it goes
    # before that paragraph, after page 2's two margin notes beside it.
    _, blocks = excerpt_outputs["stubbs_51_56-64"]
    assert _margin_notes_before(blocks, 3) == (
        ("His great position in Christendom.", "Henry II. was", [2, 3]),
    )
    assert _margin_notes_before(blocks, 2) == (
        ("Character of Henry II.", "Henry II. was", [2, 3]),
        ("His family policy.", "Henry II. was", [2, 3]),
    )


# Headings (structure spec, section 14), on the reference pages of section 9,
# "The second plan": each heading block that starts on the page, with its
# level, label and text.

_HEADINGS_ON_REFERENCE_PAGES = (
    ("haskins_eval", 0, ((1, "V", "NORMANDY AND FRANCE"),)),
    ("haskins_eval", 9, ((1, None, "INDEX"),)),
    ("stubbs_51_56-64", 0, ((1, "CHAPTER III.", "THE EARLY YEARS OF HENRY II."),)),
    # A printed contents page, named in contents_pages.
    ("stubbs_summaries_index", 0, ()),
    # "John." in lower case, a continuation.
    ("stubbs_summaries_index", 3, ((1, "CHAPTER VII.", "John."),)),
    ("domesday_headings_quotes", 0, ()),
    # The label 3.4 pitches above its title.
    ("domesday_headings_quotes", 1, ((1, "ESSAY I.", "DOMESDAY BOOK."),)),
    ("domesday_headings_quotes", 2, ((2, None, "§ 1. Plan of the Survey."),)),
    # A table's title in capitals: a known false heading.
    ("domesday_headings_quotes", 5, ((2, None, "ARMINGFORD HUNDRED."),)),
    (
        "mariejol_headings_verse",
        0,
        ((1, "CHAPITRE PREMIER", "LA JEUNESSE DE CATHERINE DE MÉDICIS"),),
    ),
    # A title that fills the column, a continuation.
    (
        "mariejol_headings_verse",
        3,
        ((1, "CHAPITRE V", "L'EXPÉRIENCE ET L'ÉCHEC DE LA POLITIQUE MODÉRÉE"),),
    ),
    (
        "mariejol_headings_verse",
        5,
        (
            (
                1,
                None,
                "APPENDICE LES DROITS DE CATHERINE SUR LA SUCCESSION DES MÉDICIS",
            ),
        ),
    ),
    (
        "kadesh_8-17",
        0,
        (
            (
                1,
                None,
                (
                    "THE BATTLE OF KADESH A STUDY IN THE EARLIEST KNOWN MILITARY "
                    "STRATEGY* JAMES HENRY BREASTED"
                ),
            ),
        ),
    ),
    (
        "gierke_86-93_270-271",
        0,
        (
            (1, None, "POLITICAL THEORIES OF THE MIDDLE AGE."),
            (2, None, "I. The Evolution of Political Theory."),
        ),
    ),
    # The running head the excerpt does not remove: a known false heading.
    (
        "gierke_86-93_270-271",
        6,
        (
            (1, None, "Macrocosm and Microcosm."),
            (2, None, "II. Macrocosm and Microcosm."),
        ),
    ),
    ("haskins_quotes_index", 0, ((2, None, "BIBLIOGRAPHICAL NOTE"),)),
    ("haskins_quotes_index", 1, ((1, "II", "THE COMING OF THE NORTHMEN"),)),
    ("haskins_quotes_index", 6, ((2, None, "BIBLIOGRAPHICAL NOTE"),)),
)


@pytest.mark.parametrize(
    ("excerpt", "page", "headings"),
    _HEADINGS_ON_REFERENCE_PAGES,
    ids=[f"{excerpt}-{page}" for excerpt, page, _ in _HEADINGS_ON_REFERENCE_PAGES],
)
def test_heading_blocks_of_the_reference_pages(
    excerpt_outputs: frozendict[str, tuple[LinesFile, BlocksFile]],
    excerpt: str,
    page: int,
    headings: tuple[tuple[int, str | None, str], ...],
) -> None:
    _, blocks = excerpt_outputs[excerpt]
    assert (
        tuple(
            (block.level, block.label, block_text(block))
            for block in blocks.blocks
            if block.kind is BlockKind.HEADING and block.origin[0].page_index == page
        )
        == headings
    )


# Chapter summaries and verse (structure spec, sections 15 and 16, rule 4),
# on the reference pages of section 9, "The second plan".


def _blocks_of_kind(blocks: BlocksFile, page: int, kind: BlockKind) -> tuple[str, ...]:
    """The text of each block of `kind` that starts on `page`."""
    return tuple(
        block_text(block)
        for block in blocks.blocks
        if block.kind is kind and block.origin[0].page_index == page
    )


def test_chapter_summary_stubbs_51_is_one_block_and_very_few_starts_a_paragraph(
    excerpt_outputs: frozendict[str, tuple[LinesFile, BlocksFile]],
) -> None:
    _, blocks = excerpt_outputs["stubbs_51_56-64"]
    assert _blocks_of_kind(blocks, 0, BlockKind.CHAPTER_SUMMARY) == (
        (
            "Terms of HenryJs accession — His character — His early reforms "
            "His relations with France—War of Toulouse — Summary of nine years' work."
        ),
    )
    kinds = tuple(
        (block.kind, block_text(block).split(" ")[0])
        for block in blocks.blocks
        if block.origin[0].page_index == 0
    )
    # "accession.", the end of the cut-in note beside "Very few…", goes
    # before that paragraph (section 13).
    assert kinds[1:5] == (
        (BlockKind.HEADING, "THE"),
        (BlockKind.CHAPTER_SUMMARY, "Terms"),
        (BlockKind.MARGIN_NOTE, "accession."),
        (BlockKind.PARAGRAPH, "Very"),
    )


@pytest.mark.parametrize(
    ("page", "summary"),
    [
        # Book page 28: a summary whose words pdfplumber's sorting mixed,
        # whole in the PDF's order (extract spec section 3).
        (
            1,
            (
                (
                    "Accession of Stephen — Arrest of the Bishops — Election of "
                    "Matilda — The Anarchy — The Pacification."
                ),
            ),
        ),
        # Book page 79: a summary whose last line is centred.
        (
            2,
            (
                (
                    "The English Church — Schools of Clergy — Rise of Becket — Quarrel "
                    "with the King- Exile—Death."
                ),
            ),
        ),
        (
            3,
            (
                (
                    "John's succession — Arthur's claims — Loss of Normandy — Quarrel "
                    "with the Church — Submission to the Pope—Quarrel with the Barons "
                    "— The Great Charter and its consequences — Arrival of "
                    "Lewis—John's death."
                ),
            ),
        ),
    ],
)
def test_chapter_summary_stubbs_summaries_index(
    excerpt_outputs: frozendict[str, tuple[LinesFile, BlocksFile]],
    page: int,
    summary: tuple[str, ...],
) -> None:
    _, blocks = excerpt_outputs["stubbs_summaries_index"]
    assert _blocks_of_kind(blocks, page, BlockKind.CHAPTER_SUMMARY) == summary


_VERSE_ON_REFERENCE_PAGES = (
    # Book pages 51 and 52: verse in the middle of each page.
    (
        "mariejol_headings_verse",
        1,
        (
            (
                "Laquelle (Catherine) dé« qtiaiorw ans\nPortoit au b(^ la sagette\n"
                "La robe et les arcs duisans (convenant)\nAux pocelles de Taygette\n"
                "ToDjours dés l'aube du jour\nAlloit aux forftts en qneste\n"
                "Ou de reths tcmt à l'entour\nCemoit le trac d'une beste ;\n"
                "Ou pressoit les cerfs au cours;\nOu i«r le pendant des roches.\n"
                "Sans chiens assaUloit les ours\nEt les sanghers aux dents croches '1)4"
            ),
        ),
    ),
    (
        "mariejol_headings_verse",
        2,
        (
            (
                "Quelle dame a la pratique\nDe tant de math^aatiqne?\n"
                "Quelle princeme «ntend mieux\nDu grand monde la peinture.\n"
                "Les chemin» de la nature,\nEt la mosiqoe des cieux?"
            ),
        ),
    ),
    # Book page 229: two verse quotes on one page.
    (
        "mariejol_headings_verse",
        4,
        (
            (
                "Quand nature accomplit le bastiment du monde\n"
                "Ne voulant poiut ailiuurâ qu'au mesme monde moclre\n"
                "La conduite de tout qui, au monde, peut estre\n"
                "Eir ficha dans le Ciel avec clous éterneb\nLa vie et le Destin (i)."
            ),
            (
                "Le hon jeune le vieux surmontera\n"
                "En champ bolliquc par singuUer duelle :\n"
                "Dans cage d'or les yeux luy crèvera, '\n"
                "Deux classes une, puis mourir, mort cruelle.\n(Cent L, qaatraio 35.)"
            ),
        ),
    ),
    # Haskins' centred Latin verse (209) and English verse (210), whose first
    # two lines are a verse of their own: the second, glued by the OCR into
    # the one word "Inagashofthewind-grievedApennine;", had too few words
    # for a verse line (structure spec section 16), and split (extract spec
    # section 4) it has six.
    (
        "haskins_quotes_index",
        7,
        (
            (
                "O Roma nobilis, orbis et domina,\nCunctarum urbium excellentissima,\n"
                "Roseo martyrum sanguine rubea,\nAlbis et virginum liliis Candida;\n"
                "Salutem dicimus tibi per omnia,\nTe benedicimus: salve per secula."
            ),
        ),
    ),
    (
        "haskins_quotes_index",
        8,
        (
            "A castle, precipice-encurled,\nIn a gash of the wind-grieved Apennine;",
            (
                "A sea-side house to the farther South,\nWhere the baked cicala dies "
                "of drouth,\nAnd one sharp tree — 't is a cypress — stands."
            ),
        ),
    ),
    # Two broken lines inset on both sides after "se sou-": no verse (rule
    # 4 does not start a run after a hyphen).
    ("mariejol_210-219", 2, ()),
    # Known false verse: tables (Domesday 47 and 406).
    (
        "domesday_headings_quotes",
        6,
        (
            (
                "South -Western Group : 49,155\nMid- Western Group: 33,191\n"
                "Eastern Group: 72,883"
            ),
            (
                "South- Western Group : 4,038\nMid-Western Group: 3,514\n"
                "Eastern Group : 7,329"
            ),
            (
                "South- Western Group : 183,842 106,086\n"
                "Mid- Western Group : 158,245 115,679\n"
                "Eastern Group : 255,498 182,830"
            ),
        ),
    ),
    (
        "domesday_headings_quotes",
        10,
        (
            (
                "ij. ac. coll. 1. 1. 36\nEdw. Stand, ij. ac.\nij. ac. coll. 1. 2. 2\n"
                "Edw. Stand, ij. ac.\nij. ac. coll. 1. 2. 2\nEdw. Stand, ij. ac.\n"
                "ij. ac. coll. 1. 0. 39."
            ),
        ),
    ),
)


@pytest.mark.parametrize(
    ("excerpt", "page", "verse"),
    _VERSE_ON_REFERENCE_PAGES,
    ids=[f"{excerpt}-{page}" for excerpt, page, _ in _VERSE_ON_REFERENCE_PAGES],
)
def test_verse_blocks_of_the_reference_pages_keep_their_lines(
    excerpt_outputs: frozendict[str, tuple[LinesFile, BlocksFile]],
    excerpt: str,
    page: int,
    verse: tuple[str, ...],
) -> None:
    _, blocks = excerpt_outputs[excerpt]
    assert _blocks_of_kind(blocks, page, BlockKind.VERSE) == verse


# Quotes and Haskins' bibliographical notes (structure spec, section 16), on
# the reference pages of section 9, "The second plan". Haskins' quotes on
# book pages 53 and 71 to 73 are checked on the whole book
# (tests/test_structure.py): the excerpt, mostly small type, measures a
# body word height of 7.60 pt against the book's 8.32, so they are not
# smaller than its body (structure spec, section 9, the excerpt's list).


def _kinds_on(blocks: BlocksFile, page: int) -> tuple[str, ...]:
    return tuple(
        block.kind.value
        for block in blocks.blocks
        if block.origin[0].page_index == page
    )


def _note_markers_on(blocks: BlocksFile, page: int) -> tuple[str, ...]:
    return tuple(
        note.marker for note in blocks.notes if note.origin[0].page_index == page
    )


def test_bibliographical_note_haskins_39_mid_page_heading_then_paragraphs(
    excerpt_outputs: frozendict[str, tuple[LinesFile, BlocksFile]],
) -> None:
    _, blocks = excerpt_outputs["haskins_quotes_index"]
    assert _kinds_on(blocks, 0) == ("paragraph", "heading", "paragraph")


def test_bibliographical_note_haskins_129_band_of_small_type_is_paragraphs(
    excerpt_outputs: frozendict[str, tuple[LinesFile, BlocksFile]],
) -> None:
    _, blocks = excerpt_outputs["haskins_quotes_index"]
    assert _kinds_on(blocks, 6) == ("heading", "paragraph", "paragraph")
    assert _note_markers_on(blocks, 6) == ()


def test_bibliographical_note_haskins_39_ends_at_the_heading_of_chapter_ii(
    excerpt_outputs: frozendict[str, tuple[LinesFile, BlocksFile]],
) -> None:
    # Book pages 53 and 71 to 73 are outside the note: their bands are notes.
    _, blocks = excerpt_outputs["haskins_quotes_index"]
    assert _note_markers_on(blocks, 2) == ("*",)
    assert _note_markers_on(blocks, 3) == ("^",)


def test_quote_domesday_93_inset_quotes_and_its_footnotes_in_the_band(
    excerpt_outputs: frozendict[str, tuple[LinesFile, BlocksFile]],
) -> None:
    # The items in 9 pt type set in after "…contrasted with the soke :—" are
    # quotes, by rule 2; two of them run on into the next line of the text,
    # which starts at the column's edge, and stay paragraphs (section 16,
    # "Where they fail").
    _, blocks = excerpt_outputs["domesday_headings_quotes"]
    assert _kinds_on(blocks, 7) == (
        "paragraph",
        "paragraph",
        "quote",
        "paragraph",
        "quote",
        "quote",
        "paragraph",
        "quote",
        "paragraph",
    )
    assert _note_markers_on(blocks, 7) == (
        "1",
        "2",
        "3",
        "4",
        "s",
        "8",
        "7",
        "8",
        "9",
        "w",
    )


def test_quote_domesday_274_quotes_across_the_column_and_footnotes_in_the_band(
    excerpt_outputs: frozendict[str, tuple[LinesFile, BlocksFile]],
) -> None:
    _, blocks = excerpt_outputs["domesday_headings_quotes"]
    assert _kinds_on(blocks, 9) == (
        "quote",
        "quote",
        "quote",
        "paragraph",
        "quote",
        "paragraph",
    )
    assert _note_markers_on(blocks, 9) == ("1", "-", "3", "4", "5", "e", "7")


def test_quote_none_on_the_domesday_contents_page(
    excerpt_outputs: frozendict[str, tuple[LinesFile, BlocksFile]],
) -> None:
    _, blocks = excerpt_outputs["domesday_headings_quotes"]
    assert set(_kinds_on(blocks, 0)) == {"paragraph"}


def test_quote_none_of_the_notes_left_in_the_body_of_mariejol_210(
    excerpt_outputs: frozendict[str, tuple[LinesFile, BlocksFile]],
) -> None:
    _, blocks = excerpt_outputs[MARIEJOL]
    assert set(_kinds_on(blocks, 0)) == {"paragraph"}


# Plates (structure spec section 18; plates spec section 1)


def _plate_removals(blocks: BlocksFile, page: int) -> tuple[tuple[str, str], ...]:
    return tuple(
        (removal.reason.value, removal.text)
        for removal in blocks.removals
        if removal.page_index == page
    )


def _figures(blocks: BlocksFile) -> tuple[tuple[str | None, list[int], str], ...]:
    """Each figure block's image, pages and text, in order."""
    return tuple(
        (block.figure, _pages(block.origin), block_text(block))
        for block in blocks.blocks
        if block.kind is BlockKind.FIGURE
    )


def test_figure_block_kadesh_17_without_text_after_the_paragraph_of_page_15(
    excerpt_outputs: frozendict[str, tuple[LinesFile, BlocksFile]],
) -> None:
    # Page 8 (book page 16), the scan of a cover (the owner, 16 November
    # 2026), is excluded by the config; page 9 (17), a plate without a text
    # layer, gives a figure block with no text after the paragraph of page
    # 15 (excerpt page 7), the last page of text in the excerpt.
    _, blocks = excerpt_outputs["kadesh_8-17"]
    assert _plate_removals(blocks, 8) == ()
    assert _figures(blocks) == (("images/plate-0009.png", [9], ""),)
    kinds = tuple(block.kind for block in blocks.blocks)
    first_figure = kinds.index(BlockKind.FIGURE)
    assert _pages(blocks.blocks[first_figure - 1].origin)[-1] == 7


def test_caption_kadesh_64_and_68_kept_and_the_back_of_plate_65_removed(
    excerpt_outputs: frozendict[str, tuple[LinesFile, BlocksFile]],
) -> None:
    _, blocks = excerpt_outputs["kadesh_59-68"]
    figures = _figures(blocks)
    assert tuple((image, pages) for image, pages, _ in figures) == (
        ("images/plate-0005.png", [5]),
        ("images/plate-0006.png", [6]),
        ("images/plate-0009.png", [9]),
    )
    # The excerpt has one plate with the series head, so rule 1 finds
    # nothing alike to it and it stays a caption line.
    assert figures[0][2].startswith(
        "DECENNIAL PUBLICATIONS, V PALIMPSEST WALL SHOWING LATER RELIEFS"
    )
    assert figures[0][2].endswith("(From a photograph by Borchardt)")
    assert figures[1][2] == ""
    assert _plate_removals(blocks, 6) == (("plate_text", "a"), ("plate_text", "t I"))
    assert figures[2][2].endswith("THE MODERN MODND OF KADESH")
    # "V", the end of the garbled series head, lies a row lower than the
    # rest of the head, which layout makes one line with it, left to right
    # (layout spec section 3, step 3); the line is caption (spec section
    # 18, rule 2, by row).
    assert "PUBLICATIONS, V PLATE VIII THE MODERN" in figures[2][2]
    assert _plate_removals(blocks, 9) == ()
    # The paragraph of page 63 runs on over the plates 64 and 65.
    assert any(_pages(block.origin) == [4, 7] for block in blocks.blocks)


def test_caption_domesday_39_and_40_kept_and_their_stray_words_removed(
    excerpt_outputs: frozendict[str, tuple[LinesFile, BlocksFile]],
) -> None:
    _, blocks = excerpt_outputs["domesday_headings_quotes"]
    figures = _figures(blocks)
    assert tuple((image, pages) for image, pages, _ in figures) == (
        ("images/plate-0003.png", [3]),
        ("images/plate-0004.png", [4]),
    )
    assert "A LAND OF VILLAGES On the border between Oxfordshire" in figures[0][2]
    assert figures[0][2].endswith("16 — 17]")
    assert figures[1][2] == (
        "A LAND OF HAMLETS tlm border between tiumersvt and Devon."
    )
    assert ("plate_text", '--,. ^X.^ MoulslVl^rf /\\"?') in _plate_removals(blocks, 3)
    assert {reason for reason, _ in _plate_removals(blocks, 4)} == {"plate_text"}
    # The map's first two rows of specks are one line of the head region
    # (layout spec section 3, step 3).
    assert len(_plate_removals(blocks, 4)) == 7


# Index entries and guide words (structure spec, section 17).


def _index_entries_on(blocks: BlocksFile, page: int) -> tuple[str, ...]:
    return tuple(
        block_text(block)
        for block in blocks.blocks
        if block.kind is BlockKind.INDEX_ENTRY and block.origin[0].page_index == page
    )


def test_index_haskins_266_heading_then_one_entry_per_entry_left_column_then_right(
    excerpt_outputs: frozendict[str, tuple[LinesFile, BlocksFile]],
) -> None:
    _, blocks = excerpt_outputs["haskins_eval"]
    # "Bayeux, …;" and its sub-entry "Black Book, III. …", one glued word
    # "172,187;BlackBook," before the split of extract spec section 4.
    assert _kinds_on(blocks, 9) == ("heading",) + ("index_entry",) * 73
    entries = _index_entries_on(blocks, 9)
    depths = tuple(
        block.level
        for block in blocks.blocks
        if block.kind is BlockKind.INDEX_ENTRY and block.origin[0].page_index == 9
    )
    # The left column's first entry, "Anjou" and its sub-entry with its
    # continuation line (section 17, rule 5), and the left column's last
    # entry before the right column's first. The page is a small-print page
    # whose Tesseract reading is kept (reocr spec, section 3, kind 1): "f."
    # for the layer's "/.", and "28," for "28.".
    assert entries[0] == "Abacus, 106 f."
    assert entries[18:20] == (
        "Anjou, counts of, 61, 85;",
        "relations with Normandy, 61-63, 85, 100, 112, 131, 136 f.",
    )
    assert depths[18:20] == (1, 2)
    assert depths.count(2) == 8
    assert entries[38:40] == ("Avranches, 172, 175, 178.", "Avranchin, 28,")


def test_index_haskins_267_calabria_one_entry_and_the_rows_cut_at_the_gutter(
    excerpt_outputs: frozendict[str, tuple[LinesFile, BlocksFile]],
) -> None:
    # Layout read the first four rows across both columns; the gutter cut
    # puts "Clermont, 211." and the three entries after it in the right
    # column, before "Commerce". The page is a small-print page, read whole
    # by Tesseract and kept: the two readings tie at 250 and Tesseract's
    # holds more known words (reocr spec, section 3), and it reads the
    # printed "10 f.," the layer lost.
    _, blocks = excerpt_outputs["haskins_quotes_index"]
    entries = _index_entries_on(blocks, 9)
    assert entries[:3] == (
        "Caen, 10 f., 71, 133, 139, 143, 153, 160, 166, 172, 184;",
        "abbeys, 12, 58, 160, 163, 171, 174, 186-88, 213.",
        "Calabria, 176, 198, 201-11, 222, 226, 237, 246.",
    )
    clermont = entries.index("Clermont, 211.")
    assert entries[clermont : clermont + 4] == (
        "Clermont, 211.",
        "Clovis, 207.",
        "Cluny, 164.",
        "Colombiéres, 116.",  # Tesseract's misreading of the printed "Colombières"
    )
    assert entries[clermont + 4].startswith("Commerce, Norman, 4, 73, 81,")
    assert "quote" not in _kinds_on(blocks, 9) + _kinds_on(blocks, 10)


def test_index_stubbs_313_to_321_one_guide_words_removal_on_each_page(
    excerpt_outputs: frozendict[str, tuple[LinesFile, BlocksFile]],
) -> None:
    _, blocks = excerpt_outputs["stubbs_summaries_index"]
    guide_words = tuple(
        (removal.page_index, removal.text)
        for removal in blocks.removals
        if removal.reason is RemovalReason.GUIDE_WORDS
    )
    # Known, not yet fixed: on page 4 (312) layout now finds the gutter,
    # since the letter soup of the default options is words in the PDF's
    # order (extract spec section 3), and "BAL" and "BEC" fall in two
    # columns, each the first line of an index entry.
    assert guide_words == (
        (5, "BUR CON"),
        (6, "HEN HUG"),
        (7, "MAT ORD"),
        (8, "PUI ROB"),
        (9, "WAR YPR"),
    )
    # The marks ";;;" above the title stay a paragraph: a head line that is
    # no running head keeps its stray marks (section 3).
    assert _kinds_on(blocks, 4)[:3] == ("paragraph", "heading", "index_entry")
    assert not any(note.origin[0].page_index >= 4 for note in blocks.notes)


# The front matter (front-matter spec section 6, "Excerpt tests"): the three
# excerpts that open with the book's front pages, by excerpt name, with
# their front-matter pages and the number of words of those pages' text
# layer (front-matter spec section 4): Haskins' 1, 2, 8, 9 and 10 have 22,
# 29, 31, 18 and 3 words; Domesday's 4, 8, 9, 10 and 11 have 4, 8, 42, 40
# and 5; Gierke's 1, 6, 7, 8 and 9 have 7, 6, 47, 33 and 7.
FRONT_MATTER_EXCERPTS = frozendict(
    {
        "haskins_front": ((0, 1, 2, 3, 4), 103),
        "domesday_front_flow": ((0, 1, 2, 3, 4), 99),
        "gierke_front_flow": ((0, 1, 2, 3, 4), 100),
    }
)


def _front_matter_layer_words(pdf_path: Path, pages: tuple[int, ...]) -> list[str]:
    texts = []
    with open_pdf(pdf_path) as pdf:
        for index in pages:
            with closing(pdf.pages[index]) as page:
                texts.extend(layer_word.text for layer_word in layer_words(page))
    return texts


@pytest.mark.parametrize("name", sorted(FRONT_MATTER_EXCERPTS))
def test_front_matter_pages_of_an_excerpt_have_no_words_and_are_its_removals(
    excerpt_books: frozendict[str, BookFolder],
    excerpt_pdf: frozendict[str, Path],
    name: str,
) -> None:
    front_matter, word_count = FRONT_MATTER_EXCERPTS[name]
    pages = read_pages(excerpt_books[name].pages_json).pages
    words = read_words(excerpt_books[name].words_json)
    removals = tuple(
        removal
        for removal in words.removals
        if removal.reason is RemovalReason.FRONT_MATTER
    )

    assert (
        tuple(page.index for page in pages if page.kind is PageKind.FRONT_MATTER)
        == front_matter
    )
    assert all(not words.pages[index].words for index in front_matter)
    assert len(removals) == word_count
    assert [removal.text for removal in removals] == _front_matter_layer_words(
        excerpt_pdf[name], front_matter
    )
    assert {removal.page_index for removal in removals} == set(front_matter)


def test_front_matter_of_haskins_front_ends_at_the_preface_page_5_of_layout(
    excerpt_books: frozendict[str, BookFolder],
) -> None:
    lines = read_lines(excerpt_books["haskins_front"].lines_json)
    page_5_lines = [
        " ".join(word.text for word in line.words)
        for region in lines.pages[5].regions
        for line in region.lines
    ]

    assert page_5_lines[:2] == [
        "PREFACE",
        "THE eight lectures which are here published",
    ]


def test_front_matter_of_gierke_front_flow_keeps_its_contents_5_and_errata_6(
    excerpt_books: frozendict[str, BookFolder],
) -> None:
    pages = read_pages(excerpt_books["gierke_front_flow"].pages_json).pages
    words = read_words(excerpt_books["gierke_front_flow"].words_json)

    assert (pages[5].kind, pages[6].kind) == (PageKind.TEXT, PageKind.TEXT)
    assert (words.pages[5].words[0].text, words.pages[6].words[0].text) == (
        "CONTENTS.",
        "ERRATA.",
    )


@pytest.mark.parametrize(
    "name", sorted(set(EXPECTED_EXCERPT_PAGES) - set(FRONT_MATTER_EXCERPTS))
)
def test_front_matter_of_an_excerpt_cut_inside_the_book_is_no_page(
    excerpt_books: frozendict[str, BookFolder], name: str
) -> None:
    # Two start with a contents page, the other nine with running text: the
    # rule ends the front matter at 0 on all eleven.
    pages = read_pages(excerpt_books[name].pages_json).pages
    removals = read_words(excerpt_books[name].words_json).removals

    assert not any(page.kind is PageKind.FRONT_MATTER for page in pages)
    assert not any(removal.reason is RemovalReason.FRONT_MATTER for removal in removals)


# The head of a short section (structure spec, section 3, its last
# paragraph): the second page of a preface of two pages, excerpt page 6
# (book page index 13) of haskins_front and of domesday_front_flow, has a
# head line like no other page's, whose likeness is to the heading
# "PREFACE" or "PREFACE." on the page before. Haskins' misread number
# "vlil" goes with the rest of its line; Domesday's "vi" is a page number.

SHORT_SECTION_HEADS = frozendict(
    {
        "haskins_front": (
            "vlil PREFACE",
            ((RemovalReason.RUNNING_HEAD, "vlil PREFACE"),),
            (),
        ),
        "domesday_front_flow": (
            "vi Preface.",
            (
                (RemovalReason.PAGE_NUMBER, "vi"),
                (RemovalReason.RUNNING_HEAD, "Preface."),
            ),
            (PageNumber(6, "vi", PageNumberPosition.HEAD),),
        ),
    }
)


@pytest.mark.parametrize("name", sorted(SHORT_SECTION_HEADS))
def test_short_section_head_of_the_preface_page_6_is_a_running_head_removal(
    excerpt_outputs: frozendict[str, tuple[LinesFile, BlocksFile]], name: str
) -> None:
    lines, blocks = excerpt_outputs[name]
    first_line, removals, page_numbers = SHORT_SECTION_HEADS[name]
    page_lines = [
        " ".join(word.text for word in line.words)
        for region in lines.pages[6].regions
        for line in region.lines
    ]

    assert page_lines[0] == first_line
    assert (
        tuple(
            (removal.reason, removal.text)
            for removal in blocks.removals
            if removal.page_index == 6
        )
        == removals
    )
    assert (
        tuple(number for number in blocks.page_numbers if number.page_index == 6)
        == page_numbers
    )
