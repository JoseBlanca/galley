"""Tests of the note links of the correct stage (docs/specs/correct.md,
section 9b) and of how markdown applies a link edit (section 10)."""

import logging
from pathlib import Path

import pytest

from galley.correct._links import (
    Link,
    MarkedReference,
    link_answer,
    link_edits,
    misread_reference,
    note_of,
    reference_place,
)
from galley.correct._merge import Change, ChangeKind
from galley.correct._reading import GalleyToken, Place
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
    ("galley_after", "model_word", "misread"),
    [
        (".3", "forces.", "3"),
        (";™", "enemy;", "™"),
        ("“", "Zahi", "“"),
        (".”", 'advanced."', ""),
        (".", "forces.", ""),
        (".abc", "forces.", ""),
        (".1234", "forces.", ""),
    ],
    ids=["digit", "trade_mark", "quote", "real_quote", "none", "letters", "too_long"],
)
def test_the_misread_reference_is_what_galley_has_past_the_models_punctuation(
    galley_after: str, model_word: str, misread: str
) -> None:
    assert misread_reference(galley_after, model_word) == misread


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


def test_a_link_edit_takes_the_misread_reference_into_the_link() -> None:
    links = (
        _link(BODY_BLOCK, "investigation", "n-p0008-003", "2", "investigation."),
        _link(BODY_BLOCK, "forces", "n-p0008-004", "3", "forces."),
    )
    edits = link_edits(PAGE, links, (), (), MODEL)
    assert [(edit.old, edit.new, edit.reason) for edit in edits] == [
        (
            "investigation.’",
            "investigation.[’](#n-p0008-003)",
            "vision_note_link",
        ),
        ("forces.3", "forces.[3](#n-p0008-004)", "vision_note_link"),
    ]
    assert {edit.block_sha256 for edit in edits} == {block_sha256(BODY_BLOCK)}


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
