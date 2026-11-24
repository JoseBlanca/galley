"""Tests of the note links of the correct stage (docs/specs/correct.md,
section 9b) and of how markdown applies a link edit (section 10)."""

import dataclasses
import difflib
import json
import logging
import re
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from galley.book_folder import BookFolder
from galley.correct import footnotes_starting
from galley.correct._links import (
    Link,
    MarkedReference,
    galley_references,
    link_answer,
    link_edits,
    links_in_order,
    misread_reference,
    note_of,
    page_links,
    reference_place,
)
from galley.correct._merge import Change, ChangeKind
from galley.correct._reading import GalleyToken, Place, page_reading, split_counts
from galley.errors import EditError
from galley.markdown import FiledEdit, apply_edits
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
    Span,
    block_sha256,
    every_block,
    read_blocks,
    read_words,
)

MODEL = "qwen/qwen3.6-35b-a3b"
ORIGIN = (Origin(8, Box(60, 100, 460, 300)),)
NOTE_ORIGIN = (Origin(8, Box(60, 500, 460, 600)),)


def _span(text: str, note_ref: str | None = None) -> Span:
    return Span(text, Emphasis.NONE, note_ref)


def _block(block_id: str, *spans: Span, origin: tuple[Origin, ...] = ORIGIN) -> Block:
    return Block(
        id=block_id,
        kind=BlockKind.PARAGRAPH,
        level=None,
        label=None,
        spans=spans,
        figure=None,
        origin=origin,
    )


def _note(note_id: str, text: str, *, referenced: bool = False) -> Note:
    block = _block(f"b-{note_id}", _span(text), origin=NOTE_ORIGIN)
    return Note(
        id=note_id,
        kind=NoteKind.FOOTNOTE,
        marker="",
        blocks=(block,),
        origin=NOTE_ORIGIN,
        referenced=referenced,
    )


def _blocks(blocks: tuple[Block, ...], notes: tuple[Note, ...]) -> BlocksFile:
    return BlocksFile(
        source_pdf_sha256="a" * 64,
        blocks=blocks,
        notes=notes,
        removals=(),
        word_changes=(),
        page_numbers=(),
    )


# The answer (section 9b), in the forms the 35B model's recorded answers
# show for Kadesh's pages 8, 9, 15 and 40.


def test_references_are_brackets_sup_tags_and_superscript_digits() -> None:
    raw = (
        "work like that of Kromayer on the battlefields of Greece,¹ but\n"
        "battle, the first study of the poem was that of Salvolini [4] in 1835,\n"
        "Then followed a study by Lenormant,<sup>5</sup> in 1858\n"
        "[6] a reference with no word before it\n"
    )
    found = link_answer(raw).references
    assert found == (
        MarkedReference("1", ("battlefields", "of", "Greece,"), ("but",)),
        MarkedReference("4", ("that", "of", "Salvolini"), ("in",)),
        MarkedReference("5", ("study", "by", "Lenormant,"), ("in",)),
    )


@pytest.mark.parametrize(
    "line",
    [
        "NOTE 4 | Campagne de Rhamsès-le-Grand",
        "NOTE, 4, Campagne de Rhamsès-le-Grand",
        "4 Campagne de Rhamsès-le-Grand (Sesostris) contre les",
        "\u2074 Campagne de Rhamsès-le-Grand",
    ],
    ids=["as_asked", "commas", "copied_whole", "superscript"],
)
def test_note_lines_are_read_in_each_form_the_model_writes(line: str) -> None:
    answer = link_answer(f"of Salvolini [4] in 1835\n{line}\n")
    assert answer.notes["4"].startswith("Campagne de Rhamsès-le-Grand")


def test_a_note_line_whose_number_no_reference_has_is_left_out() -> None:
    answer = link_answer(
        "of Salvolini [4] in 1835\n2. The Record was\nNOTE 4 | Campagne\n"
    )
    assert dict(answer.notes) == {"4": "Campagne"}


# Where the reference is, and which note.


def _token(form: str, start: int = 0, *, fixed: bool = False) -> GalleyToken:
    place = None if fixed else Place("b-p0008-001", 0, start, start + len(form))
    return GalleyToken(form=form, place=place, block_id="b-p0008-001", note_id=None)


BODY = tuple(
    _token(form, position * 10)
    for position, form in enumerate(
        ["the", "battle", "by", "lenormant", "in", "1858", "misled", "lenormant", "viz"]
    )
)


def test_a_reference_is_placed_after_the_word_its_context_picks() -> None:
    # Section 9b: two "Lenormant" on Kadesh's page 9; the words before pick
    # the first, the 0.5 lead holds.
    reference = MarkedReference("5", ("battle", "by", "Lenormant,"), ("in",))
    assert reference_place(BODY, reference) == 3


def test_a_reference_whose_context_cannot_choose_is_not_placed() -> None:
    reference = MarkedReference("5", ("Lenormant,",), ())
    assert reference_place(BODY, reference) is None


def test_a_reference_after_a_longer_word_is_not_placed() -> None:
    # Kadesh page 45: the model's "order" is galley's "ordered" (the page
    # prints "ordered"), 0.83 alike but two letters longer.
    body = (_token("vizier"), _token("was"), _token("ordered"))
    reference = MarkedReference("107", ("vizier", "was", "order"), ())
    assert reference_place(body, reference) is None


def test_a_reference_after_a_fixed_token_is_not_placed() -> None:
    body = (_token("greece"), _token("1", fixed=True))
    assert reference_place(body, MarkedReference("1", ("1",), ())) is None


NOTES = (
    _note("n-p0008-001", "Paper read before the International Congress"),
    _note("n-p0008-002", "J, Kromayer, Antike Schlachtfelder"),
    _note("n-p0029-001", "Op. cst., p. S43."),
    _note("n-p0029-002", "Op. cit., pp. S42, 543."),
)


def test_a_note_is_the_one_whose_first_words_are_alike() -> None:
    assert note_of(NOTES[:2], "J. KROMAYER, Antike") == "n-p0008-002"


def test_two_notes_nearly_as_alike_give_no_note() -> None:
    # Kadesh page 29: "Op. cit., p. 164." is as near one note as the other.
    assert note_of(NOTES[2:], "(Op. cit., p. 164.") is None


# The misread reference left in galley's word.


@pytest.mark.parametrize(
    ("galley_core", "galley_after", "model_word", "number", "misread"),
    [
        ("forces", ".3", "forces.", "3", "3"),
        ("enemy;™", "", "enemy;", "34", "™"),
        ("Zahi", "“", "Zahi", "64", "“"),
        ("advanced", ".”", 'advanced."', "74", ""),
        ("forces", ".", "forces.", "3", ""),
        ("forces", ".abc", "forces.", "3", ""),
        ("forces", ".1234", "forces.", "3", ""),
        # The number is in galley's word: the printed quote before it,
        # which the model left out, stays in the word.
        ("soldiers", ".”37", "soldiers.", "37", "37"),
        # A sign the core keeps: taken out when it is one the OCR gives for
        # a raised number and the model's word lacks it.
        ("map®", "", "map", "43", "®"),
        ("map®", "", "map®", "43", ""),
        ("50%", "", "50", "3", None),
        ("50%", "", "50%", "3", ""),
        ("soldiers;™", "", "soldiers.", "36", None),
        ("map®", ".abc", "map", "43", None),
        # A core made only of signs is not cut.
        ("®", "", "®", "3", ""),
    ],
    ids=[
        "digit",
        "trade_mark",
        "quote",
        "real_quote",
        "none",
        "letters",
        "too_long",
        "quote_before_the_number",
        "raised_sign",
        "raised_sign_the_model_has",
        "printed_sign",
        "printed_sign_the_model_has",
        "other_punctuation",
        "sign_left_in_the_word",
        "only_signs",
    ],
)
def test_the_misread_reference_is_what_galley_has_past_the_models_punctuation(
    galley_core: str,
    galley_after: str,
    model_word: str,
    number: str,
    misread: str | None,
) -> None:
    assert misread_reference(galley_core, galley_after, model_word, number) == misread


# The link edits.


def _place(block: Block, word: str) -> Place:
    text = block.spans[0].text
    start = text.index(word)
    return Place(block.id, 0, start, start + len(word))


def _link(block: Block, word: str, note_id: str, text: str, model_word: str) -> Link:
    return Link(
        page_index=8,
        place=_place(block, word),
        note_id=note_id,
        text=text,
        model_word=model_word,
    )


BODY_BLOCK = _block(
    "b-p0008-002",
    _span("needs special investigation.’ The value of forces.3 These two"),
)
PAGE = _blocks(
    (BODY_BLOCK,),
    (_note("n-p0008-003", "In Ramses III."), _note("n-p0008-004", "There is, however")),
)


def test_a_link_edit_drops_the_misread_reference_and_keeps_the_models_number() -> None:
    links = (
        _link(BODY_BLOCK, "investigation", "n-p0008-003", "2", "investigation."),
        _link(BODY_BLOCK, "forces", "n-p0008-004", "3", "forces."),
    )
    edits = link_edits(PAGE, links, (), (), MODEL)
    assert [(edit.old, edit.new, edit.reason) for edit in edits] == [
        (
            "investigation.’",
            "investigation.[2](#n-p0008-003)",
            "vision_note_link",
        ),
        ("forces.3", "forces.[3](#n-p0008-004)", "vision_note_link"),
    ]
    assert {edit.block_sha256 for edit in edits} == {block_sha256(BODY_BLOCK)}


def test_a_link_takes_the_place_of_a_sign_the_words_core_keeps() -> None:
    # Section 6 keeps "™" and "®" in the core, and the ";" before them,
    # so the place, galley's token, ends after the sign (Kadesh).
    block = _block("b-p0014-002", _span("the soldiers;™ and Blanckenhorn’s map® then"))
    text = block.spans[0].text
    links = tuple(
        Link(
            page_index=8,
            place=Place(block.id, 0, text.index(core), text.index(core) + len(core)),
            note_id=note_id,
            text=number,
            model_word=model_word,
        )
        for core, note_id, number, model_word in (
            ("soldiers;™", "n-p0008-003", "36", "soldiers;"),
            ("map®", "n-p0008-004", "43", "map"),
        )
    )
    page = _blocks((block,), PAGE.notes)
    assert [
        (edit.old, edit.new) for edit in link_edits(page, links, (), (), MODEL)
    ] == [
        ("soldiers;™", "soldiers;[36](#n-p0008-003)"),
        ("map®", "map[43](#n-p0008-004)"),
    ]


def test_a_printed_sign_the_core_keeps_and_the_model_lacks_gives_no_link() -> None:
    # Section 9b: "%" may be printed, so "50%" against the model's "50"
    # keeps its sign and gets no link.
    block = _block("b-p0014-002", _span("about 50% of them"))
    text = block.spans[0].text
    link = Link(
        page_index=8,
        place=Place(block.id, 0, text.index("50%"), text.index("50%") + 3),
        note_id="n-p0008-003",
        text="3",
        model_word="50",
    )
    assert link_edits(_blocks((block,), PAGE.notes), (link,), (), (), MODEL) == ()


def test_a_word_twice_in_its_block_takes_the_words_before_it() -> None:
    block = _block("b-p0008-002", _span("of the enemy; but of the enemy; then"))
    start = block.spans[0].text.rindex("enemy")
    link = Link(
        page_index=8,
        place=Place(block.id, 0, start, start + 5),
        note_id="n-p0008-003",
        text="34",
        model_word="enemy;",
    )
    page = _blocks((block,), PAGE.notes)
    (edit,) = link_edits(page, (link,), (), (), MODEL)
    assert (edit.old, edit.new) == (
        "but of the enemy;",
        "but of the enemy;[34](#n-p0008-003)",
    )


def test_links_are_refused_where_section_9b_says(
    caplog: pytest.LogCaptureFixture,
) -> None:
    galley_link = _block(
        "b-p0008-005",
        _span("exposed by Chabas"),
        _span("*", "n-p0008-004"),
        _span(" with caustic"),
    )
    page = _blocks((BODY_BLOCK, galley_link), PAGE.notes)
    word_change = Change(
        kind=ChangeKind.REPLACE,
        page_index=8,
        place=_place(BODY_BLOCK, "investigation"),
        text="investigation",
        second_reading=None,
    )
    links = (
        # Another edit changes the word.
        _link(BODY_BLOCK, "investigation", "n-p0008-003", "2", "investigation."),
        # galley references the note elsewhere and no link replaces it.
        _link(BODY_BLOCK, "forces", "n-p0008-004", "3", "forces."),
    )
    with caplog.at_level(logging.INFO, logger="galley.correct"):
        assert link_edits(page, links, (word_change,), (), MODEL) == ()
    assert "another edit changes the word" in caplog.text
    assert "galley references note n-p0008-004 elsewhere" in caplog.text


def test_two_links_to_one_note_give_neither(caplog: pytest.LogCaptureFixture) -> None:
    links = (
        _link(BODY_BLOCK, "investigation", "n-p0008-003", "2", "investigation."),
        _link(BODY_BLOCK, "forces", "n-p0008-003", "3", "forces."),
    )
    with caplog.at_level(logging.INFO, logger="galley.correct"):
        assert link_edits(PAGE, links, (), (), MODEL) == ()
    assert "two links to note n-p0008-003" in caplog.text


def test_two_links_after_one_word_give_neither(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Section 9b, review of 24 November 2026: markdown would put the second
    # link in place of the first.
    links = (
        _link(BODY_BLOCK, "forces", "n-p0008-003", "2", "forces."),
        _link(BODY_BLOCK, "forces", "n-p0008-004", "3", "forces."),
    )
    with caplog.at_level(logging.INFO, logger="galley.correct"):
        assert link_edits(PAGE, links, (), (), MODEL) == ()
    assert "two links after one word" in caplog.text


def test_a_link_takes_the_place_of_galleys_link_to_another_note() -> None:
    # Kadesh page 9: galley links Lenormant to note 4, the model to 5, and
    # Salvolini to 4.
    block = _block(
        "b-p0009-001",
        _span("of Salvolini in 1835, by Lenormant,"),
        _span("*", "n-p0009-001"),
        _span(" in 1858"),
    )
    page = _blocks(
        (block,),
        (
            _note("n-p0009-001", "Campagne de", referenced=True),
            _note("n-p0009-002", "In Correspondant"),
        ),
    )
    links = (
        _link(block, "Salvolini", "n-p0009-001", "4", "Salvolini"),
        _link(block, "Lenormant", "n-p0009-002", "5", "Lenormant,"),
    )
    edits = link_edits(page, links, (), (), MODEL)
    assert [(edit.old, edit.new) for edit in edits] == [
        ("Salvolini", "Salvolini[4](#n-p0009-001)"),
        ("Lenormant,", "Lenormant,[5](#n-p0009-002)"),
    ]
    applied = apply_edits(
        page,
        [
            FiledEdit(edit, Path("edits/correct.jsonl"), n)
            for n, edit in enumerate(edits, 1)
        ],
    )
    assert applied.blocks[0].spans == (
        _span("of Salvolini"),
        _span("4", "n-p0009-001"),
        _span(" in 1835, by Lenormant,"),
        _span("5", "n-p0009-002"),
        _span(" in 1858"),
    )
    assert [note.referenced for note in applied.notes] == [True, True]


def test_a_reference_after_white_space_gets_no_link(
    caplog: pytest.LogCaptureFixture,
) -> None:
    block = _block(
        "b-p0010-001",
        _span("(Nos. 1, 2, 13, 14) "),
        _span(";13", "n-p0008-004"),
    )
    page = _blocks((block,), PAGE.notes)
    link = Link(
        page_index=8,
        place=Place(block.id, 0, 16, 18),  # "14" in "14)"
        note_id="n-p0008-003",
        text="13",
        model_word="14)",
    )
    with caplog.at_level(logging.INFO, logger="galley.correct"):
        assert link_edits(page, (link,), (), (), MODEL) == ()
    assert "only after white space" in caplog.text


# markdown (section 10).


def _filed(old: str, new: str, block: Block = BODY_BLOCK) -> FiledEdit:
    edit = Edit(
        block_id=block.id,
        block_sha256=block_sha256(block),
        old=old,
        new=new,
        author="correct",
        reason="vision_note_link",
    )
    return FiledEdit(edit, Path("edits/correct.jsonl"), 1)


def test_markdown_puts_a_reference_span_after_the_new_text() -> None:
    applied = apply_edits(PAGE, [_filed("forces.3", "forces.[3](#n-p0008-004)")])
    assert applied.blocks[0].spans == (
        _span("needs special investigation.’ The value of forces."),
        _span("3", "n-p0008-004"),
        _span(" These two"),
    )
    assert [note.referenced for note in applied.notes] == [False, True]


def test_a_link_to_a_note_that_is_not_there_is_an_error() -> None:
    with pytest.raises(EditError, match="links to a note that is not in blocks.json"):
        apply_edits(PAGE, [_filed("forces.3", "forces.[3](#n-p0099-001)")])


def test_a_link_galley_has_already_proposes_nothing() -> None:
    block = _block(
        "b-p0008-005",
        _span("exposed by Chabas"),
        _span("*", "n-p0008-004"),
        _span(" with caustic"),
    )
    page = _blocks((block,), PAGE.notes)
    link = _link(block, "Chabas", "n-p0008-004", "6", "Chabas")
    assert link_edits(page, (link,), (), (), MODEL) == ()


def test_a_refused_link_brings_back_galleys_link_and_refuses_the_next() -> None:
    # Kadesh page 9: "Lenormant," to note 5 is refused since galley links
    # note 5 from "Chabas"; galley's link from "Lenormant," to note 4 then
    # stays, and "Salvolini" to note 4 is refused too.
    block = _block(
        "b-p0009-001",
        _span("of Salvolini in 1835, by Lenormant,"),
        _span("*", "n-p0009-001"),
        _span(" in 1858, by Chabas"),
        _span("*", "n-p0009-002"),
        _span(" with"),
    )
    page = _blocks(
        (block,),
        (
            _note("n-p0009-001", "Campagne de", referenced=True),
            _note("n-p0009-002", "In Correspondant", referenced=True),
        ),
    )
    links = (
        _link(block, "Salvolini", "n-p0009-001", "4", "Salvolini"),
        _link(block, "Lenormant", "n-p0009-002", "5", "Lenormant,"),
    )
    assert link_edits(page, links, (), (), MODEL) == ()


def test_an_edit_whose_old_text_holds_a_link_is_a_plain_edit() -> None:
    # Section 10: a link edit's old text holds no link; this one changes
    # text that happens to look like one.
    block = _block("b-p0008-002", _span("see [3](#n-p0008-004) here"))
    page = _blocks((block,), PAGE.notes)
    applied = apply_edits(
        page, [_filed("see [3](#n-p0008-004)", "see [4](#n-p0008-004)", block)]
    )
    assert applied.blocks[0].spans == (_span("see [4](#n-p0008-004) here"),)


def test_an_owner_link_to_a_footnote_referenced_already_is_refused() -> None:
    # Section 10, rule 6: the edit is named with its file and line, not
    # left for markdown's check of blocks.json.
    block = _block(
        "b-p0008-002",
        _span("by Chabas"),
        _span("*", "n-p0008-004"),
        _span(" and by forces.3 here"),
    )
    page = _blocks((block,), PAGE.notes)
    edit = Edit(
        block_id=block.id,
        block_sha256=block_sha256(block),
        old="forces.3",
        new="forces.[3](#n-p0008-004)",
        author="owner",
        reason="page_image",
    )
    with pytest.raises(EditError) as raised:
        apply_edits(page, [FiledEdit(edit, Path("edits/owner.jsonl"), 3)])
    assert "edits/owner.jsonl, line 3" in str(raised.value)
    assert "a block refers to twice" in str(raised.value)


def test_links_are_asked_for_on_pages_where_a_footnote_starts_only() -> None:
    # Section 9b: an endnote starts a page of Gierke's endnote section,
    # where no reference is printed.
    endnote = dataclasses.replace(
        _note("n-p0008-009", "Endnote"), kind=NoteKind.ENDNOTE
    )
    page = _blocks((BODY_BLOCK,), (*PAGE.notes, endnote))
    assert [note.id for note in footnotes_starting(page, 8)] == [
        "n-p0008-003",
        "n-p0008-004",
    ]
    assert footnotes_starting(_blocks((BODY_BLOCK,), (endnote,)), 8) == ()


def _numbered(note_id: str, number: str, rank: int) -> Link:
    return Link(
        page_index=31,
        place=Place("b-p0031-001", 0, 0, 1),
        note_id=note_id,
        text=number,
        model_word="x",
        rank=rank,
    )


def _page_notes(*markers: str, referenced: tuple[int, ...] = ()) -> tuple[Note, ...]:
    return tuple(
        dataclasses.replace(
            _note(f"n-p0031-{index:03d}", "Text"),
            marker=marker,
            referenced=index in referenced,
        )
        for index, marker in enumerate(markers, start=1)
    )


@pytest.mark.parametrize(
    ("links", "markers", "referenced", "kept"),
    [
        ((("n-p0031-001", "76", 0), ("n-p0031-002", "77", 1)), ("", ""), (), (0, 1)),
        # Kadesh page 21 in the run of 19 November 2026: 10, then 7.
        ((("n-p0031-001", "10", 0), ("n-p0031-002", "7", 1)), ("", ""), (), ()),
        ((("n-p0031-002", "76", 0), ("n-p0031-001", "77", 1)), ("", ""), (), ()),
        ((("n-p0031-001", "76", 0), ("n-p0031-001", "76", 1)), ("", ""), (), ()),
        # galley reads note 2's marker 78, after the link's 77 on note 3:
        # the model's numbers are not compared with galley's markers.
        ((("n-p0031-003", "77", 2),), ("", "78", ""), (), (0,)),
        # Kadesh page 26, 21 November 2026: the model reads 66 to 68 for the
        # printed 56 to 58, and galley's markers are 59, 62 and 63.
        (
            (
                ("n-p0031-001", "66", 0),
                ("n-p0031-002", "67", 1),
                ("n-p0031-003", "68", 2),
            ),
            ("8", "", "", "59", "1", "62", "63"),
            (4, 6),
            (0, 1, 2),
        ),
        # Kadesh page 53: 120 to 129 for 130 to 139, galley's marker 137.
        (
            (
                ("n-p0031-001", "120", 0),
                ("n-p0031-002", "121", 1),
                ("n-p0031-009", "128", 8),
                ("n-p0031-010", "129", 9),
            ),
            ("", "11", "13", "12", "", "", "36", "137", "188", ""),
            (),
            (0, 1, 2, 3),
        ),
        # galley's markers, cut by the OCR or not, are not compared.
        ((("n-p0031-002", "77", 1),), ("8", ""), (), (0,)),
        ((("n-p0031-001", "76", 0),), ("", "77"), (), (0,)),
        # Kadesh page 31: the model's first reference goes to the second
        # note, though nothing references the first: one note too far.
        ((("n-p0031-002", "17", 0), ("n-p0031-003", "18", 1)), ("", "", ""), (), ()),
        # Kadesh page 8: galley links the first note from the heading's
        # "*", which the model does not bracket.
        (
            (("n-p0031-002", "2", 0), ("n-p0031-003", "3", 1)),
            ("", "", ""),
            (1,),
            (0, 1),
        ),
        # Kadesh page 62: galley joins note 169 to 168, whose reference
        # gives no link; 170 and 171 then go one note short, and only they
        # are dropped.
        (
            (
                ("n-p0031-001", "166", 0),
                ("n-p0031-002", "167", 1),
                ("n-p0031-003", "168", 2),
                ("n-p0031-004", "170", 4),
                ("n-p0031-005", "171", 5),
            ),
            ("", "", "", "", ""),
            (),
            (0, 1, 2),
        ),
        # A link out of order drops the links it is out of order with, and
        # no other: 13 after 14 (no note twice, both k-th).
        (
            (
                ("n-p0031-001", "12", 0),
                ("n-p0031-002", "14", 1),
                ("n-p0031-003", "13", 2),
                ("n-p0031-004", "15", 3),
            ),
            ("", "", "", ""),
            (),
            (0, 3),
        ),
    ],
    ids=[
        "rising",
        "falling_numbers",
        "notes_out_of_order",
        "one_note_twice",
        "against_galleys_marker",
        "tens_misread_page_26",
        "tens_misread_page_53",
        "cut_marker",
        "with_galleys_marker",
        "one_note_too_far",
        "a_note_galley_links",
        "a_join_drops_the_links_after_it",
        "only_the_links_out_of_order",
    ],
)
def test_the_links_that_break_the_order_of_a_pages_notes_are_dropped(
    links: tuple[tuple[str, str, int], ...],
    markers: tuple[str, ...],
    referenced: tuple[int, ...],
    kept: tuple[int, ...],
) -> None:
    # Section 9b, review of 19 November 2026: page 31's five links each one
    # note too far, page 21's two.
    numbered = [_numbered(note_id, number, rank) for note_id, number, rank in links]
    found = links_in_order(numbered, _page_notes(*markers, referenced=referenced))
    assert found == tuple(numbered[index] for index in kept)


def test_a_number_the_model_leaves_out_is_not_counted() -> None:
    # Section 9b, Kadesh page 61: the model leaves out 160, so its 161 is
    # its third reference and goes to the fourth footnote: one note past
    # the k-th, as a 160 misread 161 would be, so it is dropped.
    numbered = [
        _numbered("n-p0031-001", "158", 0),
        _numbered("n-p0031-002", "159", 1),
        _numbered("n-p0031-004", "161", 2),
        _numbered("n-p0031-005", "162", 3),
    ]
    assert links_in_order(numbered, _page_notes("", "", "", "", "")) == tuple(
        numbered[:2]
    )


def test_a_page_read_with_one_number_misread_keeps_no_wrong_link() -> None:
    # Review of 24 November 2026: a page printing 76 to 81, the model
    # reading the references after the words of 76 to 80 as 76, 78, 79, 80,
    # 81 and its note lines, with the same numbers, naming the notes 76 and
    # 78 to 81. Only 76 is right; it comes before a skip (76, 78) and the
    # others go one note past the k-th, so none is kept.
    words = ("one", "two", "three", "four", "five", "six")
    answer = link_answer(
        "one [76] x\n"
        "two [78] x\n"
        "three [79] x\n"
        "four [80] x\n"
        "five [81] x\n"
        "NOTE 76 | Alpha first note\n"
        "NOTE 78 | Gamma third note\n"
        "NOTE 79 | Delta fourth note\n"
        "NOTE 80 | Epsilon fifth note\n"
        "NOTE 81 | Zeta sixth note\n"
    )
    notes = tuple(
        _note(f"n-p0031-{index:03d}", text)
        for index, text in enumerate(
            (
                "Alpha first note",
                "Beta second note",
                "Gamma third note",
                "Delta fourth note",
                "Epsilon fifth note",
                "Zeta sixth note",
            ),
            start=1,
        )
    )
    links = page_links(31, _line_page(*words), notes, answer)
    assert links == ()


def test_a_number_marked_twice_gives_no_link() -> None:
    # Section 9b, Kadesh page 9 with 8 read as 9: the 9 after "poem" shows
    # the repeat, and neither 9 is linked, by its note line or by order.
    answer = link_answer(
        PAGE_11_ANSWER.replace("Brugsch [17] at", "Brugsch [16] at").replace(
            "NOTE 17 | Geogr.", "NOTE 16 | Geogr."
        )
    )
    links = page_links(11, _line_page(*PAGE_11_WORDS), _page_11_notes(), answer)
    assert [link.text for link in links] == ["15"]


def test_a_reference_with_no_note_makes_galleys_count_unknown() -> None:
    # Section 9b: galley references the third note from a word the model
    # does not mark, and the model's 18 and 19 give no note. Whether one
    # of them is the reference to galley's note is not known, so its 20 to
    # the fifth note, the k-th only when galley's note counts, is dropped.
    lines = (
        "w0 [17] x\nw1 [18] x\nw2 [19] x\nw3 [20] x\n"
        "NOTE 17 | Alpha note 1\nNOTE 18 | Omega\nNOTE 19 | Omega\n"
        "NOTE 20 | Epsilon note 5\n"
    )
    found = _by_order(lines, _greek_notes(5, referenced=(3,)), {5: "n-p0031-003"})
    assert found == [("17", "n-p0031-001")]


def _line_page(*words: str) -> tuple[GalleyToken, ...]:
    """galley's reading of a page whose body is `words`, one span."""
    block = "b-p0011-001"
    tokens = []
    start = 0
    for word in words:
        tokens.append(
            GalleyToken(
                form=word.lower(),
                place=Place(block, 0, start, start + len(word)),
                block_id=block,
                note_id=None,
            )
        )
        start += len(word) + 1
    return tuple(tokens)


# Kadesh page 11 (section 9b): galley reads the first words of notes 16
# and 17 as "Masrvuo's" and "i @engr.", so the model's note lines
# "MASPERO's" and "Geogr." name no footnote.
PAGE_11_WORDS = ("brief", "Record", "the", "Poem", "by", "Brugsch", "at", "Karnak")
PAGE_11_ANSWER = (
    "A brief Record [15] the\n"
    "like the Poem [16] by\n"
    "said by Brugsch [17] at\n"
    "Luxor, at Karnak [18] and\n"
    "NOTE 15 | Called by de\n"
    "NOTE 16 | MASPERO's\n"
    "NOTE 17 | Geogr.\n"
    "NOTE 18 | Struggle of the\n"
)


def _page_11_notes() -> tuple[Note, ...]:
    return (
        _note("n-p0011-001", "Called by de Rougé the Bulletin."),
        _note("n-p0011-002", "Masrvuo's statement (Struggle, p. 3%)"),
        _note("n-p0011-003", "i @engr. Imackr., 11, 23."),
        _note("n-p0011-004", "Strugyle of the Nations, p. 1."),
    )


def test_a_note_line_that_names_no_note_is_placed_between_its_neighbours() -> None:
    links = page_links(
        11,
        _line_page(*PAGE_11_WORDS),
        _page_11_notes(),
        link_answer(PAGE_11_ANSWER),
    )
    assert [(link.text, link.note_id) for link in links] == [
        ("15", "n-p0011-001"),
        ("16", "n-p0011-002"),
        ("17", "n-p0011-003"),
        ("18", "n-p0011-004"),
    ]


def test_no_note_is_placed_without_a_link_after_it() -> None:
    # Kadesh page 62: by the link before alone, a reference whose note
    # galley joined to the one before would go to the next note.
    answer = link_answer(PAGE_11_ANSWER.replace("Karnak [18] and", "Karnak and"))
    links = page_links(11, _line_page(*PAGE_11_WORDS), _page_11_notes(), answer)
    assert [link.text for link in links] == ["15"]


def test_no_note_is_placed_when_its_neighbours_numbers_skip_a_note() -> None:
    # Kadesh page 62 with 168 left out (review of 24 November 2026): galley
    # joins 169 to 168, so 170 and 171 keep the k-th count, and 169, whose
    # note line names no note, would go by order to the joined note 168.
    # Between 166 and 170 lie four numbers and three notes: not placed.
    lines = (
        "w0 [166] x\nw1 [167] x\nw2 [169] x\nw3 [170] x\nw4 [171] x\n"
        "NOTE 166 | Alpha note 1\nNOTE 167 | Beta note 2\n"
        "NOTE 169 | Publication has\nNOTE 170 | Delta note 4\n"
        "NOTE 171 | Epsilon note 5\n"
    )
    assert _by_order(lines, _greek_notes(5)) == [
        ("166", "n-p0031-001"),
        ("170", "n-p0031-004"),
        ("171", "n-p0031-005"),
    ]


def _greek_notes(count: int, *, referenced: tuple[int, ...] = ()) -> tuple[Note, ...]:
    """`count` notes of page 31 with first words no note line names."""
    names = ("Alpha", "Beta", "Gamma", "Delta", "Epsilon", "Zeta")
    return tuple(
        _note(
            f"n-p0031-{index:03d}",
            f"{names[index - 1]} note {index}",
            referenced=index in referenced,
        )
        for index in range(1, count + 1)
    )


def _by_order(
    lines: str,
    notes: tuple[Note, ...],
    references: Mapping[int, str] = frozendict(),
) -> list[tuple[str, str]]:
    """The links of page 31 whose body is "w0 w1 ...", one word per
    reference of `lines`, each "wK [n] x"; `references` gives galley's
    reference after a word, by its position."""
    reading = _line_page(*(f"w{index}" for index in range(8)))
    galley = {}
    for position, note_id in references.items():
        place = reading[position].place
        assert place is not None
        galley[place] = note_id
    links = page_links(31, reading, notes, link_answer(lines), frozendict(galley))
    return [(link.text, link.note_id) for link in links]


def test_no_link_follows_the_first_mark_of_a_number_marked_twice() -> None:
    # Section 9b, Kadesh page 31 with "[17]" doubled: the model's note
    # lines, one note off there, come back in line with its references.
    lines = (
        "w0 [17] x\nw1 [17] x\nw2 [18] x\nw3 [19] x\nw4 [20] x\n"
        "NOTE 17 | Beta note 2\nNOTE 18 | Gamma note 3\n"
        "NOTE 19 | Delta note 4\nNOTE 20 | Epsilon note 5\n"
    )
    assert _by_order(lines, _greek_notes(6)) == []


def test_a_mark_at_galleys_reference_counts_galleys_note_as_marked() -> None:
    # Section 9b, Kadesh page 61 with 159 read as 160: galley links note
    # 2 from the fifth word, where the page prints 163; the model marks
    # that word too, so note 2 is no reference it left out, and its 160,
    # its second reference, is not linked to note 3.
    lines = (
        "w0 [158] x\nw1 [160] x\nw2 [161] x\nw3 [162] x\nw4 [163] x\n"
        "NOTE 158 | Alpha note 1\nNOTE 160 | Gamma note 3\n"
        "NOTE 161 | Delta note 4\nNOTE 162 | Epsilon note 5\n"
        "NOTE 163 | Zeta note 6\n"
    )
    found = _by_order(lines, _greek_notes(6, referenced=(2,)), {4: "n-p0031-002"})
    assert found == []


def test_a_number_the_next_skips_past_gives_no_link() -> None:
    # Section 9b, Kadesh page 61 with 161 read as 160: in 158, 159, 160,
    # 162 the model may have left out 160 and misread 161.
    lines = (
        "w0 [158] x\nw1 [159] x\nw2 [160] x\nw3 [162] x\n"
        "NOTE 158 | Alpha note 1\nNOTE 159 | Beta note 2\n"
        "NOTE 160 | Gamma note 3\nNOTE 162 | Epsilon note 5\n"
    )
    assert _by_order(lines, _greek_notes(5)) == [
        ("158", "n-p0031-001"),
        ("159", "n-p0031-002"),
    ]


def test_a_number_far_below_the_next_links_finds_no_note() -> None:
    # The fallback's note would lie before the page's first footnote.
    lines = "w0 [3] x\nw1 [15] x\nNOTE 15 | Beta note 2\n"
    assert _by_order(lines, _greek_notes(2)) == [("15", "n-p0031-002")]


def test_no_note_galley_references_is_found_by_order() -> None:
    # The model marks galley's reference to the second note with "*" and a
    # note line that names none (counted as marked); its "2" would go by
    # order to that note, which galley links already.
    lines = (
        "w0 [1] x\nw1 [2] x\nw2 [*] x\nw3 [4] x\n"
        "NOTE 1 | Alpha note 1\nNOTE 4 | Delta note 4\n"
    )
    found = _by_order(lines, _greek_notes(4, referenced=(2,)), {2: "n-p0031-002"})
    assert found == [("1", "n-p0031-001"), ("4", "n-p0031-004")]


def test_no_note_a_dropped_link_names_is_found_by_order() -> None:
    # "5" names the first note but breaks the order; "1", whose note line
    # names none, would go by order to that note.
    lines = (
        "w0 [1] x\nw1 [5] x\nw2 [3] x\nNOTE 5 | Alpha note 1\nNOTE 3 | Gamma note 3\n"
    )
    assert _by_order(lines, _greek_notes(3)) == [("3", "n-p0031-003")]


def test_a_note_found_by_order_must_be_the_k_th() -> None:
    # By the numbers, "1" and "2" go to the second and third notes, one
    # and two before 3's; but the model marked something more ("*") among
    # them, so they are its first and second references, not the k-th.
    lines = (
        "w0 [1] x\nw1 [2] x\nw2 [*] x\nw3 [3] x\n"
        "NOTE 1 | Omega\nNOTE 2 | Omega\nNOTE 3 | Delta note 4\n"
    )
    assert _by_order(lines, _greek_notes(4)) == [("3", "n-p0031-004")]


def test_a_reference_at_galleys_reference_is_not_found_by_order() -> None:
    # galley links the second word to a note of another page; the model's
    # "2" there names no note, and is not moved to the page's second note.
    lines = (
        "w0 [1] x\nw1 [2] x\nw2 [3] x\nNOTE 1 | Alpha note 1\nNOTE 3 | Gamma note 3\n"
    )
    found = _by_order(lines, _greek_notes(3), {1: "n-p0030-001"})
    assert found == [("1", "n-p0031-001"), ("3", "n-p0031-003")]


def test_a_note_found_by_order_without_a_guard_is_linked() -> None:
    # The cases above with the reference's number right: it is linked.
    lines = (
        "w0 [1] x\nw1 [2] x\nw2 [3] x\nNOTE 1 | Alpha note 1\nNOTE 3 | Gamma note 3\n"
    )
    assert _by_order(lines, _greek_notes(3)) == [
        ("1", "n-p0031-001"),
        ("2", "n-p0031-002"),
        ("3", "n-p0031-003"),
    ]


def test_a_reference_the_model_marks_where_galley_links_the_note_counts_once() -> None:
    # Section 9b, Kadesh's page 9: galley links "Chabas" to note 6; the
    # model's "Chabas" [6] gives no link, its note line missing, and its
    # "Record" [7], the second reference it marks, goes to note 7, the
    # page's second footnote.
    chabas = Place("b-p0009-001", 0, 0, 6)
    reading = (
        GalleyToken(form="chabas", place=chabas, block_id="b-p0009-001", note_id=None),
        GalleyToken(
            form="with",
            place=Place("b-p0009-001", 2, 1, 5),
            block_id="b-p0009-001",
            note_id=None,
        ),
        GalleyToken(
            form="record",
            place=Place("b-p0009-001", 2, 7, 13),
            block_id="b-p0009-001",
            note_id=None,
        ),
        GalleyToken(
            form="inscription",
            place=Place("b-p0009-001", 2, 15, 26),
            block_id="b-p0009-001",
            note_id=None,
        ),
    )
    notes = (
        dataclasses.replace(_note("n-p0009-003", "Rev. arch., 1858"), referenced=True),
        _note("n-p0009-004", "This and the other documentary sources"),
    )
    answer = link_answer(
        "exposed by Chabas [6] with\nthe Record [7] inscription\n"
        "NOTE 7 | This and the\n"
    )
    links = page_links(9, reading, notes, answer, frozendict({chabas: "n-p0009-003"}))
    assert [(link.note_id, link.text, link.rank) for link in links] == [
        ("n-p0009-004", "7", 1)
    ]


def test_a_reference_where_galley_links_another_note_counts_galleys_as_marked() -> None:
    # Section 9b, review of 24 November 2026: galley links "Lenormant" to
    # the page's first note, the model to the second. The model marked
    # galley's reference, perhaps misreading its number, so galley's note
    # counts as marked, and the model's first reference going to the
    # second note is one note past the k-th: no link.
    lenormant = Place("b-p0009-001", 0, 0, 9)
    reading = (
        GalleyToken(
            form="lenormant", place=lenormant, block_id="b-p0009-001", note_id=None
        ),
        GalleyToken(
            form="in",
            place=Place("b-p0009-001", 2, 1, 3),
            block_id="b-p0009-001",
            note_id=None,
        ),
    )
    notes = (
        dataclasses.replace(
            _note("n-p0009-001", "Campagne de Rhamses"), referenced=True
        ),
        _note("n-p0009-002", "Rev. arch., 1858"),
    )
    answer = link_answer("by Lenormant [5] in\nNOTE 5 | Rev. arch., 1858\n")
    links = page_links(
        9, reading, notes, answer, frozendict({lenormant: "n-p0009-001"})
    )
    assert links == ()


def test_galleys_reference_after_white_space_is_not_one_right_after_the_word() -> None:
    # Section 9b: only a reference span right after the word's end counts;
    # "Chabas " then "*" has white space between.
    block = _block(
        "b-p0009-001",
        _span("by Lenormant"),
        _span("4", "n-p0009-001"),
        _span(" exposed by Chabas "),
        _span("*", "n-p0009-002"),
    )
    reading = (
        GalleyToken(
            form="lenormant",
            place=Place(block.id, 0, 3, 12),
            block_id=block.id,
            note_id=None,
        ),
        GalleyToken(
            form="chabas",
            place=Place(block.id, 2, 12, 18),
            block_id=block.id,
            note_id=None,
        ),
    )
    assert galley_references(_blocks((block,), ()), reading) == {
        Place(block.id, 0, 3, 12): "n-p0009-001"
    }


def test_a_bracket_that_is_no_number_or_sign_is_no_reference() -> None:
    # Kadesh page 27: the model brackets "[at]", printed so in the text.
    answer = link_answer("L. P. H., arrived [at] the city\nthe ford [66] of the\n")
    assert [reference.text for reference in answer.references] == ["66"]


def test_a_reference_with_no_place_to_a_note_galley_references_counts_once() -> None:
    # Section 9b, Kadesh's page 40 on 21 November 2026: galley reads
    # "beaten" as "»aten" and links it to note 103, so the model's "beaten"
    # [103] has no place among galley's words. Counted both as the model's
    # fifth reference and as a note galley references, it put "is." [104]
    # one note too far, and the page lost its three right links.
    block = "b-p0040-001"
    words = ("was", "(B’wy).", "camp", "away.", "»aten", "of", "Kheta", "is.")
    starts = [0]
    for word in words[:-1]:
        starts.append(starts[-1] + len(word) + 1)
    places = {
        word: Place(block, 0, start, start + len(word.strip("().")))
        for word, start in zip(words, starts, strict=True)
    }
    reading = tuple(
        GalleyToken(form=form, place=places[word], block_id=block, note_id=None)
        for word, form in zip(
            words,
            ("was", "b'wy", "camp", "away", "aten", "of", "kheta", "is"),
            strict=True,
        )
    )
    notes = (
        _note("n-p0040-001", "This clause shows that"),
        _note("n-p0040-002", "Abu Simbel: Champ., Mon., 32"),
        _note("n-p0040-003", "This is a march", referenced=True),
        _note("n-p0040-004", "Maspero's statement (Struggle", referenced=True),
        _note("n-p0040-005", "Literally, one is beating", referenced=True),
        _note("n-p0040-006", "Inscription by the scene"),
    )
    references = frozendict(
        {
            places["camp"]: "n-p0040-003",
            places["away."]: "n-p0040-004",
            places["»aten"]: "n-p0040-005",
        }
    )
    answer = link_answer(
        "L. P. H., was⁹⁹ had not finished\n"
        "forest of Baul (B’wy).¹⁰⁰\n"
        "and gone into camp¹⁰¹ while\n"
        "evidently too far away.¹⁰² They\n"
        "They are being beaten.¹⁰³\n"
        "the vanquished of Kheta is.¹⁰⁴\n"
        "NOTE 99 | This clause shows\n"
        "NOTE 100 | Abu Simbel: CHAMP.,\n"
        "NOTE 101 | This is a\n"
        "NOTE 102 | MASPERO’s statement (Struggle,\n"
        "NOTE 103 | Literally, “one is\n"
        "NOTE 104 | Inscription by the\n"
    )
    links = page_links(40, reading, notes, answer, references)
    assert [(link.note_id, link.text) for link in links] == [
        ("n-p0040-001", "99"),
        ("n-p0040-002", "100"),
        ("n-p0040-003", "101"),
        ("n-p0040-004", "102"),
        ("n-p0040-006", "104"),
    ]


# The vision model's answers to the links prompt on the 22 Kadesh pages of
# the three excerpts where a footnote starts, recorded on 24 November 2026
# (scripts/record_kadesh_link_answers.py), each file named by its page
# index in the whole book.
RECORDED = Path(__file__).parent / "fixtures" / "correct" / "kadesh_links"
REFERENCE = (
    Path(__file__).parent
    / "fixtures"
    / "expected"
    / "kadesh_reference"
    / "note_references.json"
)
# The excerpts read with `ocr = "redo"`, as the whole book is, and the
# whole book's page indices of each excerpt's first and last pages.
LINK_EXCERPTS = (
    ("kadesh_redo", 8, 15),
    ("kadesh_29-38", 29, 38),
    ("kadesh_59-68", 59, 68),
)
# The links the recorded answers give (section 9b): the page index in the
# whole book, the number printed, the model's number, the model's word
# before the reference, galley's last four words up to the place, and the
# first characters of galley's note. Each was checked on the page images
# and against REFERENCE. Pages 11, 14, 15 and 29 have links found by
# order; pages 61 to 63 and 66, where galley splits or joins a note or
# the model leaves a reference out, keep the links before. Pages 10, 12,
# 13, 30, 31, 33, 36 and 38 have none.
RECORDED_LINKS = (
    (
        8,
        "1",
        "1",
        "Greece,",
        "the battlefields of Greece",
        "J, Kromayer, Antike Schlachtfeld",
    ),
    (
        8,
        "2",
        "2",
        "investigation.",
        "question needs special investigation",
        "In Ramses III.'s day the Purasat",
    ),
    (
        8,
        "3",
        "3",
        "forces.",
        "clever manipulation of forces",
        "®There is, however, much materia",
    ),
    (
        9,
        "4",
        "4",
        "Salvolini",
        "was that of Salvolini",
        "Campagne de Rhamete-le-Grand (Se",
    ),
    (
        9,
        "5",
        "5",
        "Lenormant,",
        "the battle by Lenormant",
        "Sin Correspondant, VII, February",
    ),
    (
        9,
        "7",
        "7",
        "“Record”",
        "drawn from the “Record",
        "This and the other documentary s",
    ),
    (
        11,
        "15",
        "15",
        "RECORD",
        "position p. brief Recorp",
        "Called by de Rougé the Bulletin.",
    ),
    (
        11,
        "16",
        "16",
        "Poem,",
        "which, like the Poem",
        "Masrvuo's statement (Struggle, p",
    ),
    (11, "17", "17", "Brugsch", "are said by Brugseh", "i @engr. Imackr., 11, 23."),
    (
        11,
        "18",
        "18",
        'Karnak."',
        "at Luxor, at Karnak",
        "Strugyle of the Nations, p. 1.",
    ),
    (
        14,
        "24",
        "24",
        "nomes,",
        "from the southern nomes",
        "3¢ LD., 1, 149d =Goun., Ham., XI",
    ),
    (
        14,
        "25",
        "25",
        "Delta,",
        "sailors from the Delta",
        "LD., Il, 149d = Gou., Ham., XI.",
    ),
    (14, "27", "27", "men,", "was only 200 men", "Gox., Ham., III, 3. They brought"),
    (14, "28", "28", "men,", "Nubian wars 400 men", "4meni inscription (1. 12)."),
    (14, "29", "29", "men.", "to Coptos, 600 men", "Tbid., ll. 14, 15."),
    # 32 and 33 since the structure stage's signs after "5,000.”" and
    # "people,”" left notes 29 and 30 (structure spec section 11, "A value
    # out of order").
    (
        14,
        "32",
        "32",
        "5,000.”",
        "Negroes, 880; total, 5,000",
        "Pap, Anastasi, I, Plate XVII, 11",
    ),
    (
        14,
        "33",
        "33",
        "people,”",
        "he slew 9,376 people",
        "Great Karnak inscription, 1. 58,",
    ),
    (
        15,
        "34",
        "34",
        "enemy;",
        "12,535 of the enemy;™",
        "The inscription is unpublished; ",
    ),
    (
        15,
        "35",
        "35",
        "2,052",
        "2,175 and captured 2,052",
        "On the back of the first pylon a",
    ),
    (
        15,
        "36",
        "36",
        "soldiers;",
        "whom 2,000 were soldiers;™",
        "Cuawr., Not. descr. 1,246.37 = L",
    ),
    (15, "37", "37", "soldiers.", "whom 4,000 were soldiers", "ueLD., Il, 22e."),
    (
        15,
        "38",
        "38",
        "certain.",
        "to me tolerably certain",
        "The Hittite king first sent 2.50",
    ),
    (29, "72", "2", 'line."', "against the sky line", "Ip. ett. p. 168."),
    (
        29,
        "73",
        "3",
        'southwest."',
        "direction, except the southwest",
        "Op. cst., p. S43.",
    ),
    (29, "74", "4", 'advanced."', "lower as we advanced", "Op. cit., pp. S42, 543."),
    (
        32,
        "82",
        "82",
        "Aranami",
        "the town of Aranami",
        "The variant is of no importance ",
    ),
    (
        32,
        "83",
        "83",
        "vizier",
        "orders to the vizier",
        "Read the above is a typographica",
    ),
    (
        37,
        "90",
        "90",
        "iter",
        "distance of an iter™",
        "®A variable measure of distance,",
    ),
    (
        37,
        "91",
        "91",
        "Amon?];",
        "the (division of Amon",
        "“The article is masculine, as it",
    ),
    (
        37,
        "92",
        "92",
        "attendants.",
        "by his personal attendants",
        "The phrase: “ alone by himself, ",
    ),
    (
        59,
        "150",
        "150",
        "river.",
        "west of the river",
        "1% The drawing of the river is q",
    ),
    (
        59,
        "152",
        "152",
        "whatever.",
        "no topographical significance whatever.™",
        "Va? anyone doubts the Egyptian's",
    ),
    (
        60,
        "154",
        "154",
        "water",
        "backs up the water",
        "The absurdity of identifying thi",
    ),
    (
        60,
        "155",
        "155",
        "bottom",
        "water at the bottom",
        "In both scenes at the Ramesseum ",
    ),
    (
        60,
        "156",
        "156",
        "terms:",
        "characterizes in these terms",
        "The same incident is also narrat",
    ),
    (
        60,
        "157",
        "157",
        '9,000."',
        "(tw-hi-r’) before him, 9,000",
        "I had no photograph of this insc",
    ),
    (
        61,
        "158",
        "158",
        "claws.”",
        "his teeth and claws.”™",
        "Struggle of the Nations, p. 93.",
    ),
    (
        62,
        "166",
        "166",
        "tale,",
        "basis for the tale",
        "Besides being here in the Pharac",
    ),
    (
        62,
        "167",
        "167",
        "Maspero",
        "scenes cited by Maspero",
        "Cpamp., Mon., 25; Roseun., Mon. ",
    ),
    (
        62,
        "168",
        "168",
        "inscriptions",
        "but the accompanying inscriptions",
        "Mar. Ab., Vol. II, p.10. 16° Pub",
    ),
    (
        63,
        "172",
        "172",
        "Luxor.",
        "left as at Luxor",
        "'? This is on the supposition th",
    ),
    (
        63,
        "173",
        "173",
        "reliefs",
        "Record or the reliefs",
        "M seprge's reference (Struggle. ",
    ),
    # Added on 24 November 2026 (plan wrong-links, task 3.2): page 63's
    # false note "2 Si thuentawen…" is gone, so the model's 174 finds its
    # note, as the page image shows.
    (
        63,
        "174",
        "174",
        "doubtful.",
        "but this is doubtful",
        "MOLLER ( Asien, p. 216, n.1) wou",
    ),
    (
        66,
        "175",
        "175",
        "perishing,”",
        "the point of perishing",
        "M asPERO, Struggle, p. 394.",
    ),
    (66, "176", "176", "Qodshu”", '“the surrender of Qodshu”"™', "Jbid., p. 395."),
)
# Least likeness of galley's words before a link, and of its note's
# first words, with the reference's: galley's OCR misreads some ("brief
# Recorp", "i @engr."); guessed, and each row is checked by eye too.
_LEAST_ALIKE = 0.6


def _alphanumeric(text: str) -> str:
    return re.sub(r"\W", "", text).casefold()


def _cut(galley: str, reference: str) -> tuple[str, str]:
    """galley's note opening cut to the length of the reference's."""
    return galley[: len(reference)], reference


def _alike(first: str, second: str) -> float:
    return difflib.SequenceMatcher(None, first, second).ratio()


@dataclass(frozen=True, slots=True)
class _LinkPage:
    """What page_links needs of one page of an excerpt, and what a row of
    RECORDED_LINKS shows of a link on it."""

    page_index: int
    reading: tuple[GalleyToken, ...]
    notes: tuple[Note, ...]
    galley_references: frozendict[Place, str]
    blocks: frozendict[str, Block]
    note_texts: frozendict[str, str]


def _link_pages(folders: Mapping[str, BookFolder]) -> frozendict[int, _LinkPage]:
    """Each page of the excerpts that has a recorded answer, by its page
    index in the whole book."""
    pages = {}
    recorded = {int(path.stem[1:]) for path in RECORDED.glob("k*.txt")}
    for name, first, last in LINK_EXCERPTS:
        blocks = read_blocks(folders[name].blocks_json)
        words = read_words(folders[name].words_json)
        splits = {
            block.id: split_counts(block, words)
            for block in every_block(blocks)
            if len(block.origin) > 1
        }
        by_id = frozendict({block.id: block for block in every_block(blocks)})
        for book_page in sorted(recorded):
            if not first <= book_page <= last:
                continue
            reading = page_reading(blocks, book_page - first, splits)
            notes = footnotes_starting(blocks, book_page - first)
            pages[book_page] = _LinkPage(
                page_index=book_page - first,
                reading=reading,
                notes=notes,
                galley_references=galley_references(blocks, reading),
                blocks=by_id,
                note_texts=frozendict(
                    {
                        note.id: " ".join(
                            span.text for block in note.blocks for span in block.spans
                        )
                        for note in notes
                    }
                ),
            )
    return frozendict(pages)


def _recorded_rows(
    pages: Mapping[int, _LinkPage], answers: Mapping[int, str]
) -> list[tuple[int, str, str, str, str]]:
    """The links of `answers`, by page index in the whole book, on the
    excerpts' structures, as RECORDED_LINKS gives them less the printed
    number."""
    found = []
    for book_page, raw in sorted(answers.items()):
        page = pages[book_page]
        for link in page_links(
            page.page_index,
            page.reading,
            page.notes,
            link_answer(raw),
            page.galley_references,
        ):
            spans = page.blocks[link.place.block_id].spans
            before = (
                "".join(span.text for span in spans[: link.place.span_index])
                + spans[link.place.span_index].text[: link.place.end]
            )
            found.append(
                (
                    book_page,
                    link.text,
                    link.model_word,
                    " ".join(before.split()[-4:]),
                    page.note_texts[link.note_id][:32],
                )
            )
    return found


@pytest.fixture(scope="module")
def kadesh_link_pages(
    kadesh_link_excerpts: frozendict[str, BookFolder],
) -> frozendict[int, _LinkPage]:
    """The pages of the recorded answers, read once for the module."""
    return _link_pages(kadesh_link_excerpts)


def _recorded_answers() -> dict[int, str]:
    return {
        int(path.stem[1:]): path.read_text(encoding="utf-8")
        for path in RECORDED.glob("k*.txt")
    }


# Reads the excerpts' runs, which Tesseract made.
@pytest.mark.tesseract
def test_the_recorded_answers_link_the_notes_the_pages_print(
    kadesh_link_pages: frozendict[int, _LinkPage],
) -> None:
    found = _recorded_rows(kadesh_link_pages, _recorded_answers())
    assert found == [row[:1] + row[2:] for row in RECORDED_LINKS]


@pytest.mark.tesseract
@pytest.mark.parametrize(
    ("page", "old", "new", "links"),
    [
        # 8 read as 9: the 9 after "poem" repeats it, so nothing from the
        # first 9 on is linked, and 7, before the skip to 9, neither.
        (9, "[8]", "[9]", ("4", "5")),
        # 25 read as 26: 24 comes before a skip, and 26 is marked twice.
        (14, "[25]", "[26]", ()),
        # 18 left out, or read as 19: the model's numbers are one note
        # off on this page already, and nothing is linked.
        (31, "[18]", "", ()),
        (31, "[18]", "[19]", ()),
    ],
    ids=[
        "page_9_8_as_9",
        "page_14_25_as_26",
        "page_31_18_left_out",
        "page_31_18_as_19",
    ],
)
def test_a_misread_or_missing_number_makes_no_wrong_link(
    kadesh_link_pages: frozendict[int, _LinkPage],
    page: int,
    old: str,
    new: str,
    links: tuple[str, ...],
) -> None:
    # Review of 24 November 2026: counting the numbers the model skips
    # made 1 to 3 wrong links on each of these pages.
    raw = (RECORDED / f"k{page:03d}.txt").read_text(encoding="utf-8")
    assert old in raw
    found = _recorded_rows(kadesh_link_pages, {page: raw.replace(old, new, 1)})
    assert tuple(row[1] for row in found) == links
    right = {(row[0], row[2]): row[4] for row in RECORDED_LINKS}
    assert all(right[row[0], row[1]] == row[3] for row in found)


def _reference_pages() -> dict[int, dict[str, Any]]:
    reference = json.loads(REFERENCE.read_text(encoding="utf-8"))
    return {page["page_index"]: page for page in reference["pages"]}


def _printed_numbers(
    page: Mapping[str, Any], galley_before: str, note_start: str
) -> tuple[str, str]:
    """The printed number of the reference whose words before it are most
    alike galley's before a link, and that of the note whose opening is
    most alike galley's note's, on a page of REFERENCE."""
    alike_context = {
        item["number"]: _alike(
            _alphanumeric(
                " ".join(galley_before.split()[-len(item["context"].split()) :])
            ),
            _alphanumeric(item["context"]),
        )
        for item in page["references"]
    }
    alike_note = {
        note["marker"]: _alike(
            *_cut(_alphanumeric(note_start), _alphanumeric(note["starts"]))
        )
        for note in page["notes"]
    }
    return (
        max(alike_context, key=alike_context.__getitem__),
        max(alike_note, key=alike_note.__getitem__),
    )


def test_every_recorded_link_is_where_the_page_prints_it_and_to_its_note() -> None:
    pages = _reference_pages()
    for book_page, printed, _, word, galley_before, note_start in RECORDED_LINKS:
        item = next(
            item for item in pages[book_page]["references"] if item["number"] == printed
        )
        assert _alphanumeric(item["after"]) == _alphanumeric(word)
        context = " ".join(galley_before.split()[-len(item["context"].split()) :])
        assert (
            _alike(_alphanumeric(context), _alphanumeric(item["context"]))
            >= _LEAST_ALIKE
        )
        # galley's words before the place are most alike the words before
        # this reference, of all the page's: a link after the wrong "men"
        # on page 14 is caught.
        assert _printed_numbers(pages[book_page], galley_before, note_start) == (
            printed,
            printed,
        ), (book_page, printed, galley_before, note_start)


_MARK = re.compile(r"\[([0-9]{1,3})\]")
_NOTE_SEPARATOR = "[\\s,.:|]"


def _mutations(raw: str) -> Iterator[tuple[str, str]]:
    """Each mark of a number in a recorded answer changed one way: read
    one more or one less (in the text only, or in its note line too),
    left out, or marked twice. Adapted from the second review of 24
    November 2026; moving a mark to the next word is left out, since the
    link follows the model's word."""
    for mark in _MARK.finditer(raw):
        number = mark.group(1)
        start, end = mark.span()
        for step in (1, -1):
            new = str(int(number) + step)
            in_text = raw[:start] + f"[{new}]" + raw[end:]
            yield f"[{number}] as [{new}]", in_text
            in_both = re.sub(
                f"(?m)^(NOTE{_NOTE_SEPARATOR}*){number}(?={_NOTE_SEPARATOR})",
                lambda line, new=new: line.group(1) + new,
                in_text,
            )
            if in_both != in_text:
                yield f"[{number}] as [{new}] with its note line", in_both
        yield f"[{number}] left out", raw[:start].rstrip(" ") + raw[end:]
        yield f"[{number}] twice", raw[:end] + f" [{number}]" + raw[end:]


@pytest.mark.tesseract
def test_no_misread_left_out_or_doubled_mark_gives_a_wrong_link(
    kadesh_link_pages: frozendict[int, _LinkPage],
) -> None:
    # Section 9b, second review of 24 November 2026: every mark of the
    # recorded answers misread, left out or doubled; each link given is to
    # the note of the reference printed where it is put.
    reference = _reference_pages()
    answers = _recorded_answers()
    wrong = []
    for book_page in sorted(answers):
        for label, mutated in _mutations(answers[book_page]):
            for row in _recorded_rows(kadesh_link_pages, {book_page: mutated}):
                if book_page not in reference:
                    wrong.append((book_page, label, row, "page not in REFERENCE"))
                    continue
                by_place, by_note = _printed_numbers(
                    reference[book_page], row[3], row[4]
                )
                if by_place != by_note:
                    wrong.append((book_page, label, row, by_place, by_note))
    assert wrong == []
