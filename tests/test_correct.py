"""Tests of the correct stage (docs/specs/correct.md) and of markdown's
application of edits (its section 10), with the model's answers recorded:
no model runs here but in the test marked vision_model."""

import base64
import dataclasses
import hashlib
import io
import json
import logging
import shutil
import socket
import threading
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import override

import pytest
from PIL import Image

from galley import correct, pdfium
from galley.book_folder import BookFolder
from galley.config import BookConfig, read_config
from galley.correct import edits_of, footnote_band_top, page_png, token_cores
from galley.correct._align import Pair, align, align_free_tail
from galley.correct._lmstudio import (
    PROMPT,
    check_models,
    read_image,
    request_body,
)
from galley.correct._merge import answer, cased, page_changes
from galley.correct._reading import page_reading, split_counts
from galley.correct._tokens import clean_answer, comparison_form, tokens
from galley.errors import EditError, ExternalProgramError
from galley.markdown import FiledEdit, apply_edits, read_edits_files
from galley.model import (
    Block,
    BlockKind,
    BlocksFile,
    Box,
    Edit,
    Emphasis,
    Note,
    NoteKind,
    Origin,
    PageKind,
    PageWords,
    Removal,
    RemovalReason,
    RenderedPage,
    Span,
    TextSource,
    Word,
    WordsFile,
    block_sha256,
    block_text,
    read_blocks,
    read_edits,
    read_pages,
    read_words,
    write_edits,
)

FIXTURES = Path(__file__).parent / "fixtures" / "correct"
MODEL = "qwen/qwen3.6-35b-a3b"
SECOND = "qwen/qwen3.6-27b"


def _cores(text: str) -> list[str]:
    return [text[token.start : token.end] for token in tokens(text)]


# Section 6: the words compared.


def test_tokens_have_the_cores_of_section_6() -> None:
    assert _cores("struphes.”") == ["struphes"]
    assert _cores("Greece,1") == ["Greece"]
    assert _cores("3%)") == ["3%"]
    assert _cores("—") == []
    assert _cores("3There") == ["There"]
    assert _cores("1X,") == ["1X"]
    assert _cores("A1") == ["A1"]
    assert _cores("Kadesh—the end--of") == ["Kadesh", "the", "end", "of"]


def test_a_marker_glued_after_any_ordinary_punctuation_is_off_the_core() -> None:
    # Section 6, step 3: the class of ordinary punctuation; the Kadesh run
    # replaced "him.”’!7" whole by "him", losing quotes and marker.
    assert _cores("him.”’!7") == ["him"]
    assert _cores("Why?12") == ["Why"]
    assert _cores("ends…3") == ["ends"]
    assert _cores("[sic]4") == ["sic"]
    assert _cores("‘Kadesh’4") == ["Kadesh"]


def test_tokens_know_where_their_core_is() -> None:
    text = "a “puem ia”"
    assert [(token.start, token.end) for token in tokens(text)] == [
        (0, 1),
        (3, 7),
        (8, 10),
    ]


def test_case_accents_quotes_and_hyphens_do_not_change_the_comparison_form() -> None:
    assert comparison_form("Rougé") == comparison_form("ROUGE") == "rouge"
    assert comparison_form("temple-reliefs") == comparison_form("templereliefs")
    assert comparison_form("491–513") == "491513"
    assert comparison_form("ﬁrst") == "first"


def test_a_line_end_hyphen_is_joined_only_before_lower_case_or_capitals_in_capitals() -> (
    None
):
    assert clean_answer("col-\nlated") == "collated"
    assert clean_answer("MARI-\nETTE") == "MARIETTE"
    # The last body line before the first note (section 6, step 1).
    assert clean_answer("com-\nCalled by") == "com-\nCalled by"
    assert clean_answer("**Poem** <b>x</b> Greece¹") == "  Poem    x  Greece"


# Section 7: the alignment.


def test_alignment_pairs_tokens_at_the_same_place_whatever_their_letters() -> None:
    assert align(["a", "puem", "ia"], ["a", "poem", "in"]) == (
        Pair(0, 0),
        Pair(1, 1),
        Pair(2, 2),
    )
    assert align(["a", "c"], ["a", "b", "c"]) == (Pair(0, 0), Pair(None, 1), Pair(1, 2))
    assert align(["a", "b", "c"], ["a", "c"]) == (Pair(0, 0), Pair(1, None), Pair(2, 1))


def test_alignment_with_a_free_tail_leaves_the_rest_of_the_first_out() -> None:
    assert align_free_tail(["a", "b", "c", "d", "e"], ["a", "b"]) == (
        Pair(0, 0),
        Pair(1, 1),
    )


def test_small_capitals_take_galleys_case() -> None:
    assert cased("MASPERO's", "Masrvuo's") == "Maspero's"
    assert cased("POEM", "porm") == "poem"
    assert cased("II.", "Il.") == "II."
    assert cased("Poem", "Porm") == "Poem"
    assert cased("BREASTED", "BREASTEP") == "BREASTED"


# Section 5: galley's reading of a page.


def _span(text: str, note_ref: str | None = None) -> Span:
    return Span(text, Emphasis.NONE, note_ref)


def _block(block_id: str, *spans: Span, origin: tuple[Origin, ...] = ()) -> Block:
    return Block(
        id=block_id,
        kind=BlockKind.PARAGRAPH,
        level=None,
        label=None,
        spans=spans,
        figure=None,
        origin=origin or (Origin(1, Box(60, 100, 460, 300)),),
    )


def _note(note_id: str, marker: str, *blocks: Block) -> Note:
    return Note(
        id=note_id,
        kind=NoteKind.FOOTNOTE,
        marker=marker,
        blocks=blocks,
        origin=blocks[0].origin,
        referenced=False,
    )


def _blocks(blocks: tuple[Block, ...], notes: tuple[Note, ...] = ()) -> BlocksFile:
    return BlocksFile(
        source_pdf_sha256="a" * 64,
        blocks=blocks,
        notes=notes,
        removals=(
            Removal(
                page_index=1,
                box=Box(60, 40, 400, 52),
                text="THE BATTLE OF KADESH 6",
                reason=RemovalReason.RUNNING_HEAD,
            ),
        ),
        word_changes=(),
        page_numbers=(),
    )


NOTE_ORIGIN = (Origin(1, Box(60, 400, 460, 500)),)
PAGE = _blocks(
    (
        _block(
            "b-p0001-001",
            _span("Tue Poem, which"),
            _span("1", "n-p0001-001"),
            _span(" is a puem."),
        ),
    ),
    (
        _note(
            "n-p0001-001",
            "%",
            _block("b-p0001-002", _span("Called by de Rouge the."), origin=NOTE_ORIGIN),
        ),
        _note(
            "n-p0001-002",
            "",
            _block("b-p0001-003", _span("Struggle of Nations, p."), origin=NOTE_ORIGIN),
        ),
    ),
)


def _changes_and_edits(
    blocks: BlocksFile, raw: str, second: str | None = None
) -> tuple[Edit, ...]:
    reading = page_reading(blocks, 1, {})
    cores = token_cores(blocks, reading)
    changes = page_changes(
        1, reading, answer(raw), cores, None if second is None else answer(second)
    )
    return edits_of(blocks, changes, MODEL)


def test_reading_holds_running_head_body_then_notes_with_fixed_markers_and_references() -> (
    None
):
    reading = page_reading(PAGE, 1, {})
    assert [(token.form, token.place is None) for token in reading] == [
        ("the", True),
        ("battle", True),
        ("of", True),
        ("kadesh", True),
        ("6", True),
        ("tue", False),
        ("poem", False),
        ("which", False),
        ("1", True),
        ("is", False),
        ("a", False),
        ("puem", False),
        ("called", False),
        ("by", False),
        ("de", False),
        ("rouge", False),
        ("the", False),
        ("struggle", False),
        ("of", False),
        ("nations", False),
        ("p", False),
    ]
    assert [token.starts_note for token in reading].count(True) == 2


def test_differing_words_are_replaced_and_words_missing_from_a_note_put_in() -> None:
    raw = (
        "6\nTHE BATTLE OF KADESH\nThe POEM, which is a poem.\n"
        "15 Called by de Rougé the Bulletin.\n16 Struggle of the Nations, p. 421.\n82"
    )
    edits = _changes_and_edits(PAGE, raw)
    assert [(edit.old, edit.new, edit.reason) for edit in edits] == [
        ("Tue", "The", "vision_word"),
        ("puem.", "poem.", "vision_word"),
        ("the.", "the. Bulletin", "vision_missing_words"),
        ("of", "of the", "vision_missing_words"),
    ]
    # The model's note numbers "15" and "16" are digits; "421." and "82"
    # come after the page's last token, where nothing is put in. Rougé and
    # Rouge are one form.
    assert {edit.page_index for edit in edits} == {1}
    assert {edit.model for edit in edits} == {MODEL}
    assert {edit.second_reading for edit in edits} == {None}


def test_words_the_page_already_holds_are_not_put_in_again() -> None:
    # Section 7: the model reading a line twice (Kadesh page 32), or words of
    # the body placed in a note (page 51).
    raw = (
        "THE BATTLE OF KADESH 6 The Poem, which is a poem. "
        "Called by de Rouge the. de Rouge the. Struggle of Nations, p."
    )
    edits = _changes_and_edits(PAGE, raw)
    assert [(edit.old, edit.new) for edit in edits] == [
        ("Tue", "The"),
        ("puem.", "poem."),
    ]


def test_no_words_are_put_in_the_body() -> None:
    raw = (
        "THE BATTLE OF KADESH 6 Tue Poem, which is truly a poem. "
        "Called by de Rouge the. Struggle of Nations, p."
    )
    edits = _changes_and_edits(PAGE, raw)
    assert [(edit.old, edit.new) for edit in edits] == [("puem.", "poem.")]


def test_a_pair_less_alike_than_0_3_is_no_edit() -> None:
    raw = "THE BATTLE OF KADESH 6 Tue Poem, which is a city."
    assert _changes_and_edits(PAGE, raw) == ()


@pytest.mark.parametrize(
    ("galley", "model"),
    [
        ("pp. 542,543.) here", "pp. 543.) here"),
        ("see 12-18). here", "see 18). here"),
        ("see (1.58). here", "see (58). here"),
        ("see %24+in here", "see in here"),
        ("the llast-two here", "the last here"),
    ],
    ids=["comma", "hyphen", "full_stop", "digits", "hyphen_letters"],
)
def test_a_galley_word_that_may_hold_two_printed_words_is_not_replaced(
    galley: str, model: str
) -> None:
    # Section 7: replacing it would lose a word (review, 19 November 2026).
    blocks = _blocks((_block("b-p0001-001", _span(galley)),))
    assert _changes_and_edits(blocks, f"THE BATTLE OF KADESH 6 {model}") == ()


@pytest.mark.parametrize(
    ("galley", "model", "expected"),
    [
        (
            "one hour fiveminutes. here",
            "one hour five minutes. here",
            ("fiveminutes.", "five minutes."),
        ),
        ("pp. 542,543.) here", "pp. 542, 543.) here", ("542,543.)", "542, 543.)")),
    ],
    ids=["glued", "comma"],
)
def test_a_galley_word_glued_from_two_takes_the_models_two_words(
    galley: str, model: str, expected: tuple[str, str]
) -> None:
    # Section 7: the model's token and the unpaired one beside it, joined,
    # are more alike galley's word than the token alone; the unpaired one
    # is not put in again elsewhere.
    blocks = _blocks((_block("b-p0001-001", _span(galley)),))
    edits = _changes_and_edits(blocks, f"THE BATTLE OF KADESH 6 {model}")
    assert [(edit.old, edit.new) for edit in edits] == [expected]


def test_the_model_word_a_glued_replacement_takes_is_not_put_in_a_note() -> None:
    note = _note(
        "n-p0001-001",
        "%",
        _block("b-p0001-002", _span("Called by deRouge the."), origin=NOTE_ORIGIN),
    )
    blocks = _blocks((_block("b-p0001-001", _span("Tue Poem")),), (note,))
    edits = _changes_and_edits(
        blocks, "THE BATTLE OF KADESH 6 The Poem 7 Called by de Rouge the."
    )
    assert [(edit.old, edit.new) for edit in edits] == [
        ("Tue", "The"),
        ("deRouge", "de Rouge"),
    ]


def test_junk_inside_a_word_is_no_mark_of_two_words() -> None:
    blocks = _blocks((_block("b-p0001-001", _span("his maje=ty, here")),))
    edits = _changes_and_edits(blocks, "THE BATTLE OF KADESH 6 his majesty, here")
    assert [(edit.old, edit.new) for edit in edits] == [("maje=ty,", "majesty,")]


def test_a_block_whose_unequal_pairs_are_little_alike_gets_no_edit() -> None:
    # Section 7: words out of place (Kadesh page 14, mean likeness 0.00 to
    # 0.19); "his" and "Mashawasha" pass 0.3 alone. The other block keeps
    # its edit.
    blocks = _blocks(
        (
            _block("b-p0001-001", _span("his use cat dog here")),
            _block("b-p0001-002", _span("a puem"), origin=NOTE_ORIGIN),
        )
    )
    raw = "THE BATTLE OF KADESH 6 Mashawasha assumes xyz qqq here a poem"
    edits = _changes_and_edits(blocks, raw)
    assert [(edit.old, edit.new) for edit in edits] == [("puem", "poem")]


def test_a_note_marker_and_a_reference_are_never_changed() -> None:
    raw = (
        "THE BATTLE OF KADESH 6 Tue Poem, which 7 is a puem. 8 Called by de Rouge the."
    )
    edits = _changes_and_edits(PAGE, raw)
    assert all("1" not in edit.old and "%" not in edit.old for edit in edits)


def test_second_reading_is_recorded_on_note_edits_only() -> None:
    raw = "THE BATTLE OF KADESH 6 The Poem, which is a puem. Called by de Rouge thee. Struggle of Nations, p."
    second = "Called by de Rouge them. Struggle of Nations, p."
    edits = _changes_and_edits(PAGE, raw, second)
    assert [(edit.old, edit.new, edit.second_reading) for edit in edits] == [
        ("Tue", "The", None),
        ("the.", "thee.", "them"),
    ]


def test_second_reading_of_an_insertion_is_what_it_read_in_the_same_gap() -> None:
    raw = (
        "THE BATTLE OF KADESH 6 The Poem, which is a puem. "
        "Called by de Rouge the Bulletin. Struggle of Nations, p."
    )
    second = "Called by de Rouge the Bullein. Struggle of Nations, p."
    edits = _changes_and_edits(PAGE, raw, second)
    assert [(edit.old, edit.new, edit.second_reading) for edit in edits][-1] == (
        "the.",
        "the. Bulletin",
        "Bullein",
    )


def test_words_between_the_last_note_and_the_page_number_at_the_foot_are_not_put_in() -> (
    None
):
    # Section 7: the run is not inside a note when the token after it is the
    # page number at the foot, a removal.
    foot = Removal(
        page_index=1,
        box=Box(200, 600, 220, 610),
        text="82",
        reason=RemovalReason.PAGE_NUMBER,
    )
    blocks = dataclasses.replace(PAGE, removals=(*PAGE.removals, foot))
    raw = (
        "THE BATTLE OF KADESH 6 The Poem, which is a poem. "
        "Called by de Rouge the. Struggle of Nations, p. truly 82"
    )
    edits = _changes_and_edits(blocks, raw)
    assert [(edit.old, edit.new) for edit in edits] == [
        ("Tue", "The"),
        ("puem.", "poem."),
    ]


def test_a_note_reference_label_source_page_number_and_marker_are_never_edited() -> (
    None
):
    heading = dataclasses.replace(
        _block("b-p0001-001", _span("THE CAMPAIGN"), _span("3J", "n-p0001-001")),
        kind=BlockKind.HEADING,
        level=1,
        label="CHAPTER Il.",
    )
    entry = dataclasses.replace(
        _block("b-p0001-002", _span("The Poem")),
        kind=BlockKind.CONTENTS_ENTRY,
        level=1,
        label="Il.",
        page_number="1O",
    )
    epigraph = dataclasses.replace(
        _block("b-p0001-003", _span("All is lost")),
        kind=BlockKind.EPIGRAPH,
        source="Ramses Il.",
    )
    note = _note(
        "n-p0001-001",
        "Il",
        _block("b-p0001-004", _span("Called by"), origin=NOTE_ORIGIN),
    )
    blocks = _blocks((heading, entry, epigraph), (note,))
    raw = (
        "THE BATTLE OF KADESH 6 CHAPTER II. THE CAMPAIGN 3 II. The Poem 10 "
        "All is lost Ramses II. 11 Called by"
    )
    assert _changes_and_edits(blocks, raw) == ()


def test_a_run_after_a_reference_at_a_notes_end_goes_after_the_word_before() -> None:
    # Section 7: the token before the run is fixed and no word of the note
    # follows it, so the run goes after the last word before it.
    note = _note(
        "n-p0001-001",
        "%",
        _block(
            "b-p0001-002",
            _span("see the"),
            _span("4", "n-p0001-009"),
            origin=NOTE_ORIGIN,
        ),
    )
    second = _note(
        "n-p0001-002",
        "",
        _block("b-p0001-003", _span("Struggle of"), origin=NOTE_ORIGIN),
    )
    blocks = _blocks((_block("b-p0001-001", _span("Tue Poem")),), (note, second))
    edits = _changes_and_edits(
        blocks, "THE BATTLE OF KADESH 6 The Poem see the 4 Nations Struggle of"
    )
    assert [(edit.old, edit.new) for edit in edits] == [
        ("Tue", "The"),
        ("the", "the Nations"),
    ]


def test_a_pair_between_0_3_and_0_5_alike_is_replaced() -> None:
    # Section 7: the limit is 0.3; "abcd" and "axyzd" are 0.44 alike.
    blocks = _blocks((_block("b-p0001-001", _span("the abcd here")),))
    edits = _changes_and_edits(blocks, "THE BATTLE OF KADESH 6 the axyzd here")
    assert [(edit.old, edit.new) for edit in edits] == [("abcd", "axyzd")]


def test_the_footnote_band_starts_4_pt_above_the_highest_note() -> None:
    assert footnote_band_top(PAGE, 1) == 396.0
    assert footnote_band_top(_blocks((_block("b-p0001-001", _span("x")),)), 1) is None


def test_a_page_cut_to_its_footnote_band_keeps_what_is_below_the_band_top() -> None:
    rendered = RenderedPage(
        page_index=0, dpi=144, width_px=10, height_px=100, pixels=bytes(range(100)) * 10
    )
    with Image.open(io.BytesIO(page_png(rendered, 10.0))) as band:
        assert band.size == (10, 80)
    with Image.open(io.BytesIO(page_png(rendered, None))) as page:
        assert page.size == (10, 100)


def test_a_word_twice_in_its_block_gets_the_words_beside_it() -> None:
    block = _block("b-p0001-001", _span("the ia and the ia here"))
    blocks = _blocks((block,))
    edits = _changes_and_edits(blocks, "THE BATTLE OF KADESH 6 the in and the ia here")
    assert [(edit.old, edit.new) for edit in edits] == [("ia and", "in and")]


def test_a_word_another_edit_changes_is_never_context() -> None:
    block = _block("b-p0001-001", _span("ia ib x ia"))
    edits = _changes_and_edits(_blocks((block,)), "THE BATTLE OF KADESH 6 in in x ia")
    # The first "ia" occurs twice alone, and its one neighbour, "ib", is
    # changed too: it is not proposed. "ib" occurs once.
    assert [(edit.old, edit.new) for edit in edits] == [("ib", "in")]


def test_each_correct_edit_applies_whether_or_not_the_others_do() -> None:
    block = _block("b-p0001-001", _span("one puem, tvo puem; three puem."))
    blocks = _blocks((block,))
    edits = _changes_and_edits(
        blocks, "THE BATTLE OF KADESH 6 one poem, two poem; three poem."
    )
    assert len(edits) == 4
    for left_out in range(len(edits)):
        kept = edits[:left_out] + edits[left_out + 1 :]
        applied = apply_edits(
            blocks, [FiledEdit(edit, Path("correct.jsonl"), 1) for edit in kept]
        )
        assert block_text(applied.blocks[0]).count("poem") >= 2


def test_a_block_on_two_pages_is_split_where_the_page_begins() -> None:
    block = _block(
        "b-p0000-001",
        _span("the first page ends here and the second goes on"),
        origin=(Origin(0, Box(60, 500, 460, 560)), Origin(1, Box(60, 100, 460, 130))),
    )

    def word(text: str, x: float, top: float) -> Word:
        return Word(text, Box(x, top, x + 30, top + 10), 90.0)

    page0 = (
        word("the", 60, 500),
        word("first", 100, 500),
        word("pagc", 140, 500),
        word("ends", 60, 520),
        word("here", 100, 520),
    )
    page1 = (word("and", 60, 100), word("the", 100, 100))
    words = WordsFile(
        source_pdf_sha256="a" * 64,
        pages=(
            PageWords(index=0, text_source=TextSource.OCR, words=page0, figures=()),
            PageWords(index=1, text_source=TextSource.OCR, words=page1, figures=()),
        ),
        removals=(),
    )
    assert split_counts(block, words) == (5, 5)


# Kadesh page 11, with the 35B model's recorded answer (section 14).


def _kadesh_page_11(second: bool) -> tuple[BlocksFile, tuple[Edit, ...]]:
    blocks = read_blocks(FIXTURES / "kadesh_p011_blocks.json")
    first = blocks.blocks[0]
    text = block_text(first)
    on_page_10 = len(tokens(text[: text.index("(Newaey.")]))
    splits = {first.id: (on_page_10, len(tokens(text)) - on_page_10)}
    reading = page_reading(blocks, 11, splits)
    cores = token_cores(blocks, reading)
    raw = (FIXTURES / "kadesh_p011_35b.txt").read_text(encoding="utf-8")
    second_answer = (
        answer((FIXTURES / "kadesh_p011_27b_band.txt").read_text(encoding="utf-8"))
        if second
        else None
    )
    changes = page_changes(11, reading, answer(raw), cores, second_answer)
    return blocks, edits_of(blocks, changes, MODEL)


def test_kadesh_page_11_note_is_corrected_as_section_14_says() -> None:
    blocks, edits = _kadesh_page_11(second=False)
    note = "n-p0011-002"
    note_block = next(n for n in blocks.notes if n.id == note).blocks[0]
    mine = [(edit.old, edit.new) for edit in edits if edit.block_id == note_block.id]
    assert mine == [
        ("Masrvuo's", "Maspero's"),
        ("3%)", "305)"),
        ("puem", "poem"),
        ("ia", "in"),
        ("struphes.”", "strophes.”"),
    ]
    applied = apply_edits(
        blocks,
        [FiledEdit(edit, Path("correct.jsonl"), n) for n, edit in enumerate(edits, 1)],
    )
    assert block_text(next(n for n in applied.notes if n.id == note).blocks[0]) == (
        "Maspero's statement (Struggle, p. 305) that it is “a poem in rhymed "
        "strophes.” is totally without foundation."
    )
    # Every edit applies, and none changes a marker or a reference.
    assert next(n for n in applied.notes if n.id == "n-p0011-001").marker == "%"


def test_kadesh_page_11_body_is_corrected_on_page_11_only() -> None:
    _, edits = _kadesh_page_11(second=False)
    body = [(edit.old, edit.new) for edit in edits if edit.block_id == "b-p0011-001"]
    assert ("suber", "sober") in body
    assert all(edit.page_index == 11 for edit in edits)
    # The words of the paragraph printed on page 10 are not lined up.
    first = [edit for edit in edits if edit.block_id == "b-p0010-001"]
    assert all("com-" not in edit.old for edit in first)


def test_kadesh_page_11_second_reading_flags_the_citation() -> None:
    _, edits = _kadesh_page_11(second=True)
    citation = next(edit for edit in edits if edit.old == "3%)")
    # The 27B model read "395" on the band, the 35B "305" on the page.
    assert citation.second_reading == "395"
    assert next(edit for edit in edits if edit.old == "puem").second_reading == "poem"


# Markdown's four rules (section 10).

BLOCKS = _blocks(
    (
        _block(
            "b-p0001-001",
            _span("Tue Poem, which"),
            _span("1", "n-p0001-001"),
            _span(" is a puem."),
        ),
    )
)
SHA = block_sha256(BLOCKS.blocks[0])


def _edit(old: str, new: str, *, block_id: str = "b-p0001-001", sha: str = SHA) -> Edit:
    return Edit(
        block_id=block_id,
        block_sha256=sha,
        old=old,
        new=new,
        author="owner",
        reason="r",
    )


def test_edits_apply_in_order_inside_their_span() -> None:
    edits = [
        FiledEdit(_edit("Tue", "The"), Path("edits/correct.jsonl"), 1),
        FiledEdit(_edit("puem", "poem"), Path("edits/correct.jsonl"), 2),
        FiledEdit(_edit("The Poem", "The Song"), Path("edits/owner.jsonl"), 1),
    ]
    applied = apply_edits(BLOCKS, edits)
    assert [span.text for span in applied.blocks[0].spans] == [
        "The Song, which",
        "1",
        " is a poem.",
    ]
    assert applied.blocks[0].spans[1].note_ref == "n-p0001-001"


@pytest.mark.parametrize(
    ("edit", "broken"),
    [
        (_edit("Tue", "The", block_id="b-p0009-001"), "is not in blocks.json"),
        (_edit("Tue", "The", sha="0" * 12), "block_sha256"),
        (_edit("e", "x"), "exactly once"),
        (_edit("which1 is", "which is"), "not a note reference"),
        (_edit("1", "2"), "not a note reference"),
    ],
    ids=["no_block", "checksum", "not_once", "across_spans", "a_reference"],
)
def test_an_edit_that_breaks_a_rule_is_an_error_naming_file_line_and_rule(
    edit: Edit, broken: str
) -> None:
    edits = [
        FiledEdit(_edit("puem", "poem"), Path("edits/correct.jsonl"), 1),
        FiledEdit(edit, Path("edits/owner.jsonl"), 3),
    ]
    with pytest.raises(EditError, match="1 edits do not apply") as raised:
        apply_edits(BLOCKS, edits)
    assert "edits/owner.jsonl, line 3" in str(raised.value)
    assert broken in str(raised.value)


# The calls to LM Studio (section 4), with a server inside the test.


@dataclass
class _FakeLmStudio:
    """A stand-in for LM Studio on localhost: it lists `models` and answers
    each page from `answers`, by the SHA-256 of the image it is sent, or
    with `status` when that is not 200. An image it has no answer for takes
    the first answer of `in_order`, which is then its answer: the answers
    of a run with one worker, in the order of its requests."""

    models: tuple[str, ...]
    answers: dict[str, str] = field(default_factory=dict)
    finish: str = "stop"
    status: int = 200
    redirect: str | None = None
    in_order: list[str] = field(default_factory=list)
    bodies: list[dict[str, object]] = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock)


def _image_key(png: bytes) -> str:
    return hashlib.sha256(png).hexdigest()


def _handler(fake: _FakeLmStudio) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        @override
        def log_message(self, format: str, *args: object) -> None:
            del format, args

        def _send(self, status: int, content: object) -> None:
            data = json.dumps(content).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self) -> None:
            self._send(200, {"data": [{"id": model} for model in fake.models]})

        def do_POST(self) -> None:
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            with fake.lock:
                fake.bodies.append(body)
            if fake.redirect is not None:
                self.send_response(302)
                self.send_header("Location", fake.redirect)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            if fake.status != 200:
                self._send(fake.status, {"error": "Model is not loaded"})
                return
            url = body["messages"][0]["content"][1]["image_url"]["url"]
            png = base64.b64decode(url.removeprefix("data:image/png;base64,"))
            key = _image_key(png)
            with fake.lock:
                if key not in fake.answers and fake.in_order:
                    fake.answers[key] = fake.in_order.pop(0)
                text = fake.answers.get(key, "")
            self._send(
                200,
                {
                    "choices": [
                        {"message": {"content": text}, "finish_reason": fake.finish}
                    ]
                },
            )

    return Handler


@pytest.fixture
def lm_studio() -> Iterator[Callable[..., tuple[_FakeLmStudio, str]]]:
    servers: list[ThreadingHTTPServer] = []

    def start(
        models: tuple[str, ...] = (MODEL,),
        *,
        finish: str = "stop",
        status: int = 200,
        redirect: str | None = None,
    ) -> tuple[_FakeLmStudio, str]:
        fake = _FakeLmStudio(models, finish=finish, status=status, redirect=redirect)
        server = ThreadingHTTPServer(("127.0.0.1", 0), _handler(fake))
        threading.Thread(
            target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True
        ).start()
        servers.append(server)
        return fake, f"http://127.0.0.1:{server.server_address[1]}"

    yield start
    for server in servers:
        server.shutdown()
        server.server_close()


def _closed_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def test_request_body_is_the_measurements() -> None:
    body = request_body(MODEL, b"png")
    assert body["temperature"] == 0
    assert body["reasoning_effort"] == "none"
    assert body["max_tokens"] == 6000
    assert body["messages"] == [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": PROMPT},
                {
                    "type": "image_url",
                    "image_url": {"url": "data:image/png;base64,cG5n"},
                },
            ],
        }
    ]


def test_no_server_is_an_error_that_says_to_start_it() -> None:
    server = f"http://127.0.0.1:{_closed_port()}"
    with pytest.raises(ExternalProgramError, match="not running at .*lms server start"):
        check_models(server, (MODEL,))


def test_a_model_lm_studio_lacks_is_an_error_that_says_how_to_get_it(
    lm_studio: Callable[..., tuple[_FakeLmStudio, str]],
) -> None:
    _, server = lm_studio(models=(SECOND,))
    with pytest.raises(
        ExternalProgramError,
        match=f"no model {MODEL}: download it with `lms get {MODEL}`; it has {SECOND}",
    ):
        check_models(server, (MODEL,))


def test_an_http_error_names_the_page_and_lm_studios_message(
    lm_studio: Callable[..., tuple[_FakeLmStudio, str]],
) -> None:
    _, server = lm_studio(status=400)
    with pytest.raises(
        ExternalProgramError, match="page 11.*HTTP 400.*Model is not loaded"
    ):
        read_image(server, MODEL, b"png", "page 11")


# Sets http_proxy for the whole process.
@pytest.mark.thread_unsafe
def test_a_proxy_in_the_environment_is_not_used(
    lm_studio: Callable[..., tuple[_FakeLmStudio, str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Section 4: the image goes to LM Studio on this machine and nowhere else.
    _, server = lm_studio()
    proxy = f"http://127.0.0.1:{_closed_port()}"
    for name in ("http_proxy", "HTTP_PROXY", "all_proxy", "ALL_PROXY"):
        monkeypatch.setenv(name, proxy)
    monkeypatch.delenv("no_proxy", raising=False)
    monkeypatch.delenv("NO_PROXY", raising=False)
    check_models(server, (MODEL,))
    assert read_image(server, MODEL, b"png", "page 11").text == ""


def test_a_redirect_is_an_error(
    lm_studio: Callable[..., tuple[_FakeLmStudio, str]],
) -> None:
    _, server = lm_studio(redirect="http://example.com/v1/chat/completions")
    with pytest.raises(ExternalProgramError, match="redirect"):
        read_image(server, MODEL, b"png", "page 11")


def test_an_answer_cut_short_is_marked(
    lm_studio: Callable[..., tuple[_FakeLmStudio, str]],
) -> None:
    fake, server = lm_studio(finish="length")
    reading = read_image(server, MODEL, b"png", "page 11")
    assert reading.cut_short
    assert fake.bodies[0]["model"] == MODEL


# The stage on the excerpt kadesh_redo, the model's answers recorded.

KADESH_REDO = "kadesh_redo"


def _excerpt_folder(
    tmp_path: Path, redo_excerpt_run: Callable[[str], BookFolder], server: str
) -> tuple[BookFolder, BookConfig]:
    source = redo_excerpt_run(KADESH_REDO)
    tmp_path.mkdir(parents=True, exist_ok=True)
    folder = BookFolder(tmp_path)
    for name in ("pages.json", "words.json", "lines.json", "blocks.json"):
        (tmp_path / name).write_bytes((source.root / name).read_bytes())
    shutil.copytree(source.images_dir, folder.images_dir)
    toml = source.book_toml.read_text(encoding="utf-8")
    folder.book_toml.write_text(
        toml + f'correct = true\ncorrect_server = "{server}"\n', encoding="utf-8"
    )
    return folder, read_config(folder.book_toml)


def _recorded_answers(folder: BookFolder) -> list[str]:
    """The recorded answers of the excerpt's text pages, in page order: the
    order of the requests of a run with one worker."""
    pages = read_pages(folder.pages_json)
    return [
        (FIXTURES / KADESH_REDO / f"p{page.index:03d}.txt").read_text(encoding="utf-8")
        for page in pages.pages
        if page.kind is PageKind.TEXT
    ]


# The excerpt's literal edits, checked by eye against the page images and
# the recorded answers: the two halves of the paragraph b-p0001-001, which
# runs from excerpt page 1 to page 2, and the note of page 3 (Kadesh's 11).
EXCERPT_EDITS = (
    ("b-p0001-001", 1, "Brugsech", "Brugsch"),
    ("b-p0001-001", 2, "Maller\u2019s", "M\u00fcller's"),
    ("b-p0003-003", 3, "Masrvuo's", "Maspero's"),
    ("b-p0003-003", 3, "puem", "poem"),
)
# The number of edits on the excerpt with the recorded answers, so that a
# change of the rules shows: without the split of a block printed on two
# pages the stage made about 230 more (review of 19 November 2026).
EXCERPT_EDIT_COUNT = 477


# Renders with PDFium.
@pytest.mark.thread_unsafe
@pytest.mark.tesseract
@pytest.mark.pandoc
def test_excerpt_edits_are_the_same_with_1_and_2_workers_and_markdown_applies_them(
    tmp_path: Path,
    redo_excerpt_run: Callable[[str], BookFolder],
    lm_studio: Callable[..., tuple[_FakeLmStudio, str]],
) -> None:
    from galley import markdown

    fake, server = lm_studio()
    written = {}
    for workers in (1, 2):
        folder, config = _excerpt_folder(
            tmp_path / str(workers), redo_excerpt_run, server
        )
        if workers == 1:
            fake.in_order.extend(_recorded_answers(folder))
        correct.run(folder, config, workers=workers)
        written[workers] = folder.correct_jsonl.read_bytes()
    assert written[1] == written[2]
    assert fake.in_order == []
    edits = read_edits(folder.correct_jsonl)
    assert len(edits) == EXCERPT_EDIT_COUNT
    assert {edit.author for edit in edits} == {"correct"}
    pages = [edit.page_index for edit in edits]
    assert pages == sorted(pages)
    found = {(edit.block_id, edit.page_index, edit.old, edit.new) for edit in edits}
    assert set(EXCERPT_EDITS) <= found
    markdown.run(folder, config)
    assert "a poem in rhymed" in folder.book_md.read_text(encoding="utf-8")


# Renders with PDFium.
@pytest.mark.thread_unsafe
@pytest.mark.tesseract
def test_pages_whose_answers_are_cut_short_get_no_edits_and_are_logged(
    tmp_path: Path,
    redo_excerpt_run: Callable[[str], BookFolder],
    lm_studio: Callable[..., tuple[_FakeLmStudio, str]],
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Section 4: an answer cut short leaves its page as galley read it.
    fake, server = lm_studio(finish="length")
    folder, config = _excerpt_folder(tmp_path, redo_excerpt_run, server)
    fake.in_order.extend(_recorded_answers(folder))
    with caplog.at_level(logging.WARNING, logger="galley.correct"):
        correct.run(folder, config, workers=2)
    assert read_edits(folder.correct_jsonl) == ()
    assert "page 3: the model's answer was cut short" in caplog.text


def test_markdown_reads_correct_first_then_agents_by_name_then_the_owner(
    tmp_path: Path,
) -> None:
    # Architecture section 10.
    folder = BookFolder(tmp_path)
    folder.edits_dir.mkdir()
    edit = _edit("Tue", "The")
    for name in ("owner.jsonl", "zeta.jsonl", "correct.jsonl", "alpha.jsonl"):
        write_edits(folder.edits_dir / name, (edit, edit))
    assert [(filed.path.name, filed.line) for filed in read_edits_files(folder)] == [
        ("correct.jsonl", 1),
        ("correct.jsonl", 2),
        ("alpha.jsonl", 1),
        ("alpha.jsonl", 2),
        ("zeta.jsonl", 1),
        ("zeta.jsonl", 2),
        ("owner.jsonl", 1),
        ("owner.jsonl", 2),
    ]


# One page of Kadesh read by the model in LM Studio (section 15).


# The model takes about 25 s on the page, more when LM Studio loads it.
@pytest.mark.vision_model
@pytest.mark.timeout(600)
@pytest.mark.thread_unsafe
@pytest.mark.tesseract
def test_lm_studio_reads_kadesh_page_11_and_its_edits_fix_the_note(
    tmp_path: Path, redo_excerpt_run: Callable[[str], BookFolder]
) -> None:
    folder, config = _excerpt_folder(
        tmp_path, redo_excerpt_run, "http://localhost:1234"
    )
    correct.check_server(config)
    blocks = read_blocks(folder.blocks_json)
    words = read_words(folder.words_json)
    splits = {
        block.id: split_counts(block, words)
        for block in (*blocks.blocks, *(b for n in blocks.notes for b in n.blocks))
        if len(block.origin) > 1
    }
    reading = page_reading(blocks, 3, splits)
    every = {
        block.id: block
        for block in (*blocks.blocks, *(b for n in blocks.notes for b in n.blocks))
    }
    cores = token_cores(blocks, reading)
    raw = read_image(
        config.correct_server,
        MODEL,
        page_png(pdfium.render(config.pdf, 3, 300), None),
        "page 3",
    )
    edits = edits_of(blocks, page_changes(3, reading, answer(raw.text), cores), MODEL)
    pairs = {(edit.old, edit.new) for edit in edits}
    assert ("puem", "poem") in pairs
    assert ("Masrvuo's", "Maspero's") in pairs
    references = {
        span.text
        for block in every.values()
        for span in block.spans
        if span.note_ref is not None
    }
    assert not any(edit.old in references for edit in edits)
