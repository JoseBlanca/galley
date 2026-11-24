"""Tests of the note links of the correct stage (docs/specs/correct.md,
section 9b) and of how markdown applies a link edit (section 10)."""

import dataclasses
import json
import logging
import re
from collections.abc import Callable
from pathlib import Path

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


def _numbered(note_id: str, number: str, rank: int, skipped: int = 0) -> Link:
    return Link(
        page_index=31,
        place=Place("b-p0031-001", 0, 0, 1),
        note_id=note_id,
        text=number,
        model_word="x",
        rank=rank,
        skipped=skipped,
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


def test_the_numbers_the_model_skips_count_as_references() -> None:
    # Section 9b, Kadesh page 61: the model leaves out 160, so 161 is its
    # third reference and goes to the page's fourth footnote.
    numbered = [
        _numbered("n-p0031-001", "158", 0),
        _numbered("n-p0031-002", "159", 1),
        _numbered("n-p0031-004", "161", 2, skipped=1),
        _numbered("n-p0031-005", "162", 3, skipped=1),
    ]
    assert links_in_order(numbered, _page_notes("", "", "", "", "")) == tuple(numbered)


def test_a_skip_that_does_not_explain_the_note_is_dropped() -> None:
    # 161 skips one number, but its note is the page's sixth footnote.
    numbered = [
        _numbered("n-p0031-001", "159", 0),
        _numbered("n-p0031-006", "161", 1, skipped=1),
    ]
    assert links_in_order(numbered, _page_notes(*[""] * 6)) == (numbered[0],)


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
    # The model marks 15, 17 and 18, and 18 goes to the page's third
    # footnote, its third reference: 15 and 18 are three numbers apart and
    # their notes two places, so whether 17 is the second footnote is not
    # known, and it is not placed.
    answer = link_answer(PAGE_11_ANSWER.replace("Poem [16] by", "Poem by"))
    notes = tuple(note for note in _page_11_notes() if note.id != "n-p0011-002")
    links = page_links(11, _line_page(*PAGE_11_WORDS), notes, answer)
    assert [(link.text, link.note_id) for link in links] == [
        ("15", "n-p0011-001"),
        ("18", "n-p0011-004"),
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


def test_a_link_where_galley_links_another_note_does_not_count_galleys_as_marked() -> (
    None
):
    # Section 9b: galley links "Lenormant" to the page's first note, the
    # model to the second. galley's note is then no note the model marked,
    # so it counts before the model's first reference, which goes to the
    # second note.
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
    assert [(link.note_id, link.text, link.rank) for link in links] == [
        ("n-p0009-002", "5", 0)
    ]


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
# whole book's page index of each excerpt's page 0.
LINK_EXCERPTS = (
    ("kadesh_redo", 8, 15),
    ("kadesh_29-38", 29, 38),
    ("kadesh_59-68", 59, 68),
)
# The links the recorded answers give (section 9b): the page index in the
# whole book, the number printed, the model's number, the model's word
# before the reference, and the first characters of galley's note. Each
# was checked on the page images and is in REFERENCE. Pages 11, 14, 15
# and 29 have links found by order; pages 61 to 63 and 66, where galley
# splits or joins a note or the model leaves a reference out, keep the
# links that keep the order. Pages 10, 12, 13, 30, 31, 33, 36 and 38 have
# none.
RECORDED_LINKS = (
    (8, "1", "1", "Greece,", "J, Kromayer, Ant"),
    (8, "2", "2", "investigation.", "In Ramses III.'s"),
    (8, "3", "3", "forces.", "®There is, howev"),
    (9, "4", "4", "Salvolini", "Campagne de Rham"),
    (9, "5", "5", "Lenormant,", "Sin Correspondan"),
    (9, "7", "7", "“Record”", "This and the oth"),
    (11, "15", "15", "RECORD", "Called by de Rou"),
    (11, "16", "16", "Poem,", "Masrvuo's statem"),
    (11, "17", "17", "Brugsch", "i @engr. Imackr."),
    (11, "18", "18", 'Karnak."', "Strugyle of the "),
    (14, "24", "24", "nomes,", "3¢ LD., 1, 149d "),
    (14, "25", "25", "Delta,", "LD., Il, 149d = "),
    (14, "27", "27", "men,", "Gox., Ham., III,"),
    (14, "28", "28", "men,", "4meni inscriptio"),
    (14, "29", "29", "men.", "Tbid., ll. 14, 1"),
    (14, "33", "33", "people,”", "Great Karnak ins"),
    (15, "34", "34", "enemy;", "The inscription "),
    (15, "35", "35", "2,052", "On the back of t"),
    (15, "36", "36", "soldiers;", "Cuawr., Not. des"),
    (15, "37", "37", "soldiers.", "ueLD., Il, 22e."),
    (15, "38", "38", "certain.", "The Hittite king"),
    (29, "72", "2", 'line."', "Ip. ett. p. 168."),
    (29, "73", "3", 'southwest."', "Op. cst., p. S43"),
    (29, "74", "4", 'advanced."', "Op. cit., pp. S4"),
    (32, "82", "82", "Aranami", "The variant is o"),
    (32, "83", "83", "vizier", "Read the above i"),
    (37, "90", "90", "iter", "®A variable meas"),
    (37, "91", "91", "Amon?];", "“The article is "),
    (37, "92", "92", "attendants.", "The phrase: “ al"),
    (59, "150", "150", "river.", "1% The drawing o"),
    (59, "152", "152", "whatever.", "Va? anyone doubt"),
    (60, "154", "154", "water", "The absurdity of"),
    (60, "155", "155", "bottom", "In both scenes a"),
    (60, "156", "156", "terms:", "The same inciden"),
    (60, "157", "157", '9,000."', "I had no photogr"),
    (61, "158", "158", "claws.”", "Struggle of the "),
    (61, "159", "159", "says:", "Vol. I, p. @; ad"),
    (61, "161", "161", "Hecatæus’s", "Diedorus's descr"),
    (61, "162", "162", "Silsileh", "CnHaup., Mon., 1"),
    (61, "163", "163", "Luxor", "Danesay, Rec., 2"),
    (61, "164", "164", "camp,", "At Abu Simbel ( "),
    (61, "165", "165", "battle.", "1% The words “sl"),
    (62, "166", "166", "tale,", "Besides being he"),
    (62, "167", "167", "Maspero", "Cpamp., Mon., 25"),
    (62, "168", "168", "inscriptions", "Mar. Ab., Vol. I"),
    (63, "172", "172", "Luxor.", "'? This is on th"),
    (63, "173", "173", "reliefs", "M seprge's refer"),
    (66, "175", "175", "perishing,”", "M asPERO, Strugg"),
    (66, "176", "176", "Qodshu”", "Jbid., p. 395."),
)


def _alphanumeric(text: str) -> str:
    return re.sub(r"\W", "", text).casefold()


# Reads the excerpts' runs, which Tesseract made.
@pytest.mark.tesseract
def test_the_recorded_answers_link_the_notes_the_pages_print(
    redo_excerpt_run: Callable[[str], BookFolder],
) -> None:
    found = []
    for name, first, last in LINK_EXCERPTS:
        folder = redo_excerpt_run(name)
        blocks = read_blocks(folder.blocks_json)
        words = read_words(folder.words_json)
        splits = {
            block.id: split_counts(block, words)
            for block in every_block(blocks)
            if len(block.origin) > 1
        }
        for path in sorted(RECORDED.glob("k*.txt")):
            book_page = int(path.stem[1:])
            if not first <= book_page <= last:
                continue
            page = book_page - first
            reading = page_reading(blocks, page, splits)
            notes = footnotes_starting(blocks, page)
            texts = {
                note.id: " ".join(
                    span.text for block in note.blocks for span in block.spans
                )
                for note in notes
            }
            links = page_links(
                page,
                reading,
                notes,
                link_answer(path.read_text(encoding="utf-8")),
                galley_references(blocks, reading),
            )
            found.extend(
                (book_page, link.text, link.model_word, texts[link.note_id][:16])
                for link in links
            )
    assert found == [row[:1] + row[2:] for row in RECORDED_LINKS]


def test_every_recorded_link_follows_the_word_the_page_prints() -> None:
    reference = json.loads(REFERENCE.read_text(encoding="utf-8"))
    after = {
        (page["page_index"], item["number"]): item["after"]
        for page in reference["pages"]
        for item in page["references"]
    }
    for book_page, printed, _, word, _ in RECORDED_LINKS:
        assert _alphanumeric(after[book_page, printed]) == _alphanumeric(word)
