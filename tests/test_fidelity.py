"""Tests of galley.fidelity (spec section 5, architecture section 13).

The values are built by hand: the stages of the walking skeleton make no
removal, word change or note, and the check must handle them already.
"""

from dataclasses import replace
from pathlib import Path

import pytest

from galley.errors import ExternalProgramError, FidelityBoundary, FidelityError
from galley.fidelity import (
    MarkdownWord,
    MarkdownWords,
    _words_of_pandoc_json,
    check_stage,
    read_markdown,
)
from galley.model import (
    Block,
    BlockKind,
    BlocksFile,
    Box,
    ChangeReason,
    Emphasis,
    Line,
    LinesFile,
    Note,
    NoteKind,
    Origin,
    PageLayout,
    PageWords,
    Region,
    Removal,
    RemovalReason,
    Reread,
    RereadKind,
    Span,
    TextSource,
    Word,
    WordChange,
    WordsFile,
)

_BOX = Box(10.0, 20.0, 30.0, 40.0)
_SHA = "0" * 64


def _words_file(pages: tuple[str, ...]) -> WordsFile:
    """One page per string, its words split on spaces."""
    return WordsFile(
        source_pdf_sha256=_SHA,
        pages=tuple(
            PageWords(
                index=index,
                text_source=TextSource.TEXT_LAYER,
                words=tuple(Word(text, _BOX, None) for text in page.split()),
                figures=(),
            )
            for index, page in enumerate(pages)
        ),
        removals=(),
    )


def _lines_file(pages: tuple[tuple[str, ...], ...]) -> LinesFile:
    """One page per tuple of lines, each line a string split on spaces, all
    in one region."""
    return LinesFile(
        source_pdf_sha256=_SHA,
        pages=tuple(
            PageLayout(
                index=index,
                regions=(
                    Region(
                        _BOX,
                        tuple(
                            Line(
                                _BOX,
                                tuple(Word(text, _BOX, None) for text in line.split()),
                            )
                            for line in lines
                        ),
                    ),
                ),
                figures=(),
            )
            for index, lines in enumerate(pages)
        ),
        rereads=(),
    )


def _span(text: str, note_ref: str | None = None) -> Span:
    return Span(text, Emphasis.NONE, note_ref)


def _block(block_id: str, pages: tuple[int, ...], spans: tuple[Span, ...]) -> Block:
    return Block(
        id=block_id,
        kind=BlockKind.PARAGRAPH,
        level=None,
        label=None,
        spans=spans,
        figure=None,
        origin=tuple(Origin(page, _BOX) for page in pages),
    )


def _blocks_file(
    blocks: tuple[Block, ...],
    notes: tuple[Note, ...] = (),
    removals: tuple[Removal, ...] = (),
    word_changes: tuple[WordChange, ...] = (),
) -> BlocksFile:
    return BlocksFile(
        source_pdf_sha256=_SHA,
        blocks=blocks,
        notes=notes,
        removals=removals,
        word_changes=word_changes,
        page_numbers=(),
    )


def _markdown(
    words: tuple[tuple[str, str | None], ...],
    note_count: int,
    note_link_count: int = 0,
    back_link_count: int = 0,
) -> MarkdownWords:
    return MarkdownWords(
        words=tuple(MarkdownWord(text, block_id) for text, block_id in words),
        note_count=note_count,
        note_link_count=note_link_count,
        back_link_count=back_link_count,
        list_item_count=0,
        shown_markers=(),
        contents_links=(),
    )


# A paragraph with a note reference glued to "Greece," on page 0, and the
# note it refers to.
_GREECE_LINES = _lines_file((("as in Greece,1 and", "1 A note."),))
_GREECE_WORD_CHANGE = WordChange(
    page_index=0,
    before=("Greece,1",),
    after=("Greece,", "1"),
    reason=ChangeReason.NOTE_MARKER,
)


def _greece_blocks(marker: str, *, referenced: bool) -> BlocksFile:
    return _blocks_file(
        blocks=(
            _block(
                "b-p0000-001",
                (0,),
                (_span("as in Greece,"), _span("1", "n-p0000-001"), _span(" and")),
            ),
        ),
        notes=(
            Note(
                id="n-p0000-001",
                kind=NoteKind.FOOTNOTE,
                marker=marker,
                blocks=(_block("b-p0000-002", (0,), (_span("A note."),)),),
                origin=(Origin(0, _BOX),),
                referenced=referenced,
            ),
        ),
        word_changes=(_GREECE_WORD_CHANGE,),
    )


# layout: words.json against lines.json


def test_layout_with_the_same_words_in_other_lines_passes() -> None:
    words = _words_file(("a b c", "d"))
    lines = _lines_file((("c", "a b"), ("d",)))

    check_stage(FidelityBoundary.LAYOUT, words, lines)


def test_layout_with_a_lost_and_an_invented_word_names_both_with_counts_and_pages() -> (
    None
):
    words = _words_file(("the cat sat", "on the mat"))
    lines = _lines_file((("the sat",), ("on the mat dog",)))

    with pytest.raises(FidelityError) as raised:
        check_stage(FidelityBoundary.LAYOUT, words, lines)

    error = raised.value
    assert error.boundary is FidelityBoundary.LAYOUT
    assert error.missing == frozendict({"cat": 1})
    assert error.invented == frozendict({"dog": 1})
    assert "'cat': input page 0, output none" in error.detail
    assert "'dog': input none, output page 1" in error.detail


def test_layout_with_a_word_twice_in_the_input_and_once_in_the_output_fails() -> None:
    words = _words_file(("the the cat",))
    lines = _lines_file((("the cat",),))

    with pytest.raises(FidelityError) as raised:
        check_stage(FidelityBoundary.LAYOUT, words, lines)

    assert raised.value.missing == frozendict({"the": 1})
    assert raised.value.invented == frozendict()


# structure: lines.json against blocks.json


def test_structure_with_the_same_words_in_blocks_passes() -> None:
    lines = _lines_file((("Some text", "that goes on"), ("to the next page.",)))
    blocks = _blocks_file(
        (
            _block(
                "b-p0000-001",
                (0, 1),
                (_span("Some text that goes on to the next page."),),
            ),
        )
    )

    check_stage(FidelityBoundary.STRUCTURE, lines, blocks)


_RUNNING_HEAD_LINES = _lines_file((("THE BOOK 81", "Some text."),))
_RUNNING_HEAD_BLOCK = _block("b-p0000-001", (0,), (_span("Some text."),))


def test_structure_removal_of_a_running_head_accounts_for_its_words() -> None:
    blocks = _blocks_file(
        (_RUNNING_HEAD_BLOCK,),
        removals=(
            Removal(
                page_index=0,
                box=_BOX,
                text="THE BOOK 81",
                reason=RemovalReason.RUNNING_HEAD,
            ),
        ),
    )

    check_stage(FidelityBoundary.STRUCTURE, _RUNNING_HEAD_LINES, blocks)


def test_structure_running_head_dropped_without_a_removal_is_missing() -> None:
    blocks = _blocks_file((_RUNNING_HEAD_BLOCK,))

    with pytest.raises(FidelityError) as raised:
        check_stage(FidelityBoundary.STRUCTURE, _RUNNING_HEAD_LINES, blocks)

    assert raised.value.boundary is FidelityBoundary.STRUCTURE
    assert raised.value.missing == frozendict({"THE": 1, "BOOK": 1, "81": 1})
    assert raised.value.invented == frozendict()


_HYPHEN_LINES = _lines_file((("to repli-",), ("cate it.",)))
_HYPHEN_BLOCK = _block("b-p0000-001", (0, 1), (_span("to replicate it."),))


def test_structure_hyphen_join_with_its_word_change_passes() -> None:
    blocks = _blocks_file(
        (_HYPHEN_BLOCK,),
        word_changes=(
            WordChange(
                page_index=0,
                before=("repli-", "cate"),
                after=("replicate",),
                reason=ChangeReason.HYPHEN_JOIN,
            ),
        ),
    )

    check_stage(FidelityBoundary.STRUCTURE, _HYPHEN_LINES, blocks)


_COMPOUND_LINES = _lines_file((("an Anglo-",), ("Saxon king",)))


def test_structure_hyphen_kept_with_its_word_change_passes() -> None:
    blocks = _blocks_file(
        (_block("b-p0000-001", (0, 1), (_span("an Anglo-Saxon king"),)),),
        word_changes=(
            WordChange(
                page_index=0,
                before=("Anglo-", "Saxon"),
                after=("Anglo-Saxon",),
                reason=ChangeReason.HYPHEN_KEPT,
            ),
        ),
    )

    check_stage(FidelityBoundary.STRUCTURE, _COMPOUND_LINES, blocks)


def test_structure_hyphen_join_guessed_with_its_word_change_passes() -> None:
    blocks = _blocks_file(
        (_HYPHEN_BLOCK,),
        word_changes=(
            WordChange(
                page_index=0,
                before=("repli-", "cate"),
                after=("replicate",),
                reason=ChangeReason.HYPHEN_JOIN_GUESSED,
            ),
        ),
    )

    check_stage(FidelityBoundary.STRUCTURE, _HYPHEN_LINES, blocks)


@pytest.mark.parametrize(
    ("lines", "block_text", "change"),
    [
        (
            ("the liter¬", "ature of"),
            "the literature of",
            WordChange(
                page_index=0,
                before=("liter¬", "ature"),
                after=("literature",),
                reason=ChangeReason.HYPHEN_JOIN,
            ),
        ),
        (
            ("in 1830¬", "40 then"),
            "in 1830-40 then",
            WordChange(
                page_index=0,
                before=("1830¬", "40"),
                after=("1830-40",),
                reason=ChangeReason.HYPHEN_KEPT,
            ),
        ),
    ],
    ids=["joined", "kept"],
)
def test_structure_join_at_a_not_sign_with_its_word_change_passes(
    lines: tuple[str, ...], block_text: str, change: WordChange
) -> None:
    blocks = _blocks_file(
        (_block("b-p0000-001", (0,), (_span(block_text),)),), word_changes=(change,)
    )

    check_stage(FidelityBoundary.STRUCTURE, _lines_file((lines,)), blocks)


_LOST_HYPHEN_LINES = _lines_file((("Unity of the move.",), ("ment, here",)))


@pytest.mark.parametrize(
    ("before", "after"),
    [(("move.", "ment,"), ("movement,",)), (("move", "ment,"), ("movement,",))],
    ids=["full stop", "lost"],
)
def test_structure_hyphen_lost_with_its_word_change_passes(
    before: tuple[str, str], after: tuple[str]
) -> None:
    # Structure spec section 5: the full stop the join drops is in `before`.
    lines = _lines_file(((f"Unity of the {before[0]}",), (f"{before[1]} here",)))
    blocks = _blocks_file(
        (_margin_note(f"Unity of the {after[0]} here"),),
        word_changes=(
            WordChange(
                page_index=0,
                before=before,
                after=after,
                reason=ChangeReason.HYPHEN_LOST,
            ),
        ),
    )

    check_stage(FidelityBoundary.STRUCTURE, lines, blocks)


def _margin_note(text: str) -> Block:
    """A margin-note block of `text` on pages 0 and 1."""
    return replace(
        _block("b-p0000-001", (0, 1), (_span(text),)), kind=BlockKind.MARGIN_NOTE
    )


def test_structure_hyphen_lost_whose_word_a_sign_was_attached_to_passes() -> None:
    # Structure spec section 5: Domesday page 461's margin note "popula-
    # tion ?" gives "population" by the join, then "population?" by the
    # spaced sign (section 23), which is the word of the margin note.
    lines = _lines_file((("Unity of the popula",), ("tion ? here",)))
    blocks = _blocks_file(
        (_margin_note("Unity of the population? here"),),
        word_changes=(
            WordChange(
                page_index=0,
                before=("popula", "tion"),
                after=("population",),
                reason=ChangeReason.HYPHEN_LOST,
            ),
            WordChange(
                page_index=0,
                before=("population", "?"),
                after=("population?",),
                reason=ChangeReason.PUNCTUATION_ATTACHED,
            ),
        ),
    )

    check_stage(FidelityBoundary.STRUCTURE, lines, blocks)


def test_structure_hyphen_lost_whose_word_was_split_at_its_case_passes() -> None:
    lines = _lines_file((("Unity of theWil",), ("liam here",)))
    blocks = _blocks_file(
        (_margin_note("Unity of the William here"),),
        word_changes=(
            WordChange(
                page_index=0,
                before=("theWil", "liam"),
                after=("theWilliam",),
                reason=ChangeReason.HYPHEN_LOST,
            ),
            WordChange(
                page_index=0,
                before=("theWilliam",),
                after=("the", "William"),
                reason=ChangeReason.CASE_SPLIT,
            ),
        ),
    )

    check_stage(FidelityBoundary.STRUCTURE, lines, blocks)


def test_structure_hyphen_lost_followed_by_a_split_then_a_sign_passes() -> None:
    # Review of work package 5: a chain of changes after the join, the
    # case split and then the sign attached to the split's second part.
    lines = _lines_file((("Unity of theWil",), ("liam ; here",)))
    blocks = _blocks_file(
        (_margin_note("Unity of the William; here"),),
        word_changes=(
            WordChange(
                page_index=0,
                before=("theWil", "liam"),
                after=("theWilliam",),
                reason=ChangeReason.HYPHEN_LOST,
            ),
            WordChange(
                page_index=0,
                before=("theWilliam",),
                after=("the", "William"),
                reason=ChangeReason.CASE_SPLIT,
            ),
            WordChange(
                page_index=0,
                before=("William", ";"),
                after=("William;",),
                reason=ChangeReason.PUNCTUATION_ATTACHED,
            ),
        ),
    )

    check_stage(FidelityBoundary.STRUCTURE, lines, blocks)


def test_structure_hyphen_lost_whose_changed_word_is_in_the_body_only_fails() -> None:
    # The join, then a sign attached, both in a body paragraph: the word
    # they end in, "movement;", is in no margin note of the page.
    lines = _lines_file((("Unity of the move.",), ("ment ; here",)))
    blocks = _blocks_file(
        (
            _block("b-p0000-001", (0, 1), (_span("Unity of the movement; here"),)),
            _margin_note("A note"),
        ),
        word_changes=(
            WordChange(
                page_index=0,
                before=("move.", "ment"),
                after=("movement",),
                reason=ChangeReason.HYPHEN_LOST,
            ),
            WordChange(
                page_index=0,
                before=("movement", ";"),
                after=("movement;",),
                reason=ChangeReason.PUNCTUATION_ATTACHED,
            ),
        ),
    )

    with pytest.raises(FidelityError, match="not in a margin note"):
        check_stage(FidelityBoundary.STRUCTURE, lines, blocks)


def test_structure_hyphen_lost_outside_a_margin_note_fails() -> None:
    # Structure spec section 5: the join is made in margin notes only.
    blocks = _blocks_file(
        (_block("b-p0000-001", (0, 1), (_span("Unity of the movement, here"),)),),
        word_changes=(
            WordChange(
                page_index=0,
                before=("move.", "ment,"),
                after=("movement,",),
                reason=ChangeReason.HYPHEN_LOST,
            ),
        ),
    )

    with pytest.raises(FidelityError, match="not in a margin note"):
        check_stage(FidelityBoundary.STRUCTURE, _LOST_HYPHEN_LINES, blocks)


@pytest.mark.parametrize(
    ("first", "after"),
    [
        ("move.", "moveent,"),
        ("move.", "move.ment,"),
        ("move.", "move-ment,"),
        ("move..", "movement,"),
    ],
    ids=["a letter dropped", "the stop kept", "a hyphen added", "two stops dropped"],
)
def test_structure_hyphen_lost_that_changes_more_than_the_stop_fails(
    first: str, after: str
) -> None:
    blocks = _blocks_file(
        (_margin_note(f"Unity of the {after} here"),),
        word_changes=(
            WordChange(
                page_index=0,
                before=(first, "ment,"),
                after=(after,),
                reason=ChangeReason.HYPHEN_LOST,
            ),
        ),
    )
    lines = _lines_file(((f"Unity of the {first}",), ("ment, here",)))

    with pytest.raises(FidelityError, match="is not a hyphen_lost"):
        check_stage(FidelityBoundary.STRUCTURE, lines, blocks)


def test_structure_hyphen_join_without_its_word_change_fails() -> None:
    blocks = _blocks_file((_HYPHEN_BLOCK,))

    with pytest.raises(FidelityError) as raised:
        check_stage(FidelityBoundary.STRUCTURE, _HYPHEN_LINES, blocks)

    error = raised.value
    assert error.missing == frozendict({"repli-": 1, "cate": 1})
    assert error.invented == frozendict({"replicate": 1})
    assert (
        "'replicate': input none, output block b-p0000-001 pages 0, 1" in error.detail
    )
    assert "'repli-': input page 0, output none" in error.detail


def test_structure_note_reference_split_off_its_word_is_a_word_of_its_own() -> None:
    # Concatenating the spans would give "Greece,1", which the undone word
    # change does not account for.
    blocks = _greece_blocks("1", referenced=True)

    check_stage(FidelityBoundary.STRUCTURE, _GREECE_LINES, blocks)


def test_structure_note_marker_counts_as_a_word() -> None:
    lines = _lines_file((("as in Greece,1 and", "A note."),))
    blocks = _greece_blocks("1", referenced=True)

    with pytest.raises(FidelityError) as raised:
        check_stage(FidelityBoundary.STRUCTURE, lines, blocks)

    assert raised.value.missing == frozendict()
    assert raised.value.invented == frozendict({"1": 1})


def _greece_blocks_with_reference(reference: Span) -> BlocksFile:
    """The Greece paragraph whose note reference span is `reference`, with
    nothing after it."""
    blocks = _greece_blocks("1", referenced=True)
    return replace(
        blocks,
        blocks=(replace(blocks.blocks[0], spans=(_span("as in Greece,"), reference)),),
    )


def test_structure_note_reference_span_holding_a_body_word_fails() -> None:
    # "and" is counted at structure but would vanish into Pandoc's note at
    # the markdown boundary.
    blocks = _greece_blocks_with_reference(_span("1 and", "n-p0000-001"))

    with pytest.raises(FidelityError) as raised:
        check_stage(FidelityBoundary.STRUCTURE, _GREECE_LINES, blocks)

    assert raised.value.missing == frozendict()
    assert raised.value.invented == frozendict()
    assert "block b-p0000-001" in raised.value.detail
    assert "'1 and'" in raised.value.detail
    assert "does not have a marker's shape" in raised.value.detail


def test_structure_note_reference_to_no_note_fails() -> None:
    blocks = replace(
        _greece_blocks("1", referenced=True),
        blocks=(
            _block(
                "b-p0000-001",
                (0,),
                (_span("as in Greece,"), _span("1", "n-p0009-001"), _span(" and")),
            ),
        ),
    )

    with pytest.raises(FidelityError) as raised:
        check_stage(FidelityBoundary.STRUCTURE, _GREECE_LINES, blocks)

    assert "block b-p0000-001" in raised.value.detail
    assert "n-p0009-001" in raised.value.detail


def test_structure_reference_reading_differently_from_its_marker_passes() -> None:
    # The OCR reads the two sides of a superscript differently: the
    # reference "1" against a note whose marker reads "8" (architecture
    # section 8).
    lines = _lines_file((("as in Greece,1 and", "8 A note."),))
    blocks = _greece_blocks("8", referenced=True)

    check_stage(FidelityBoundary.STRUCTURE, lines, blocks)


def test_structure_reference_span_land_fails_as_no_marker_shape() -> None:
    # Structure spec section 9, the second plan: a reference span "land" is
    # a word, which would vanish into Pandoc's note at the markdown boundary.
    lines = _lines_file((("as in Greece, land", "1 A note."),))
    blocks = replace(
        _greece_blocks_with_reference(_span("land", "n-p0000-001")), word_changes=()
    )

    with pytest.raises(FidelityError) as raised:
        check_stage(FidelityBoundary.STRUCTURE, lines, blocks)

    assert raised.value.missing == frozendict()
    assert raised.value.invented == frozendict()
    assert raised.value.detail == (
        "block b-p0000-001: the note reference span 'land' does not have a "
        "marker's shape (1 to 4 characters, at most 3 letters or digits, no "
        "white space, '&' or dash, and a letter only beside a round bracket, "
        "or a trailing 'V' to a footnote)"
    )


def test_structure_reference_span_naming_no_note_fails_with_a_marker_shape() -> None:
    # Structure spec section 9, the second plan: a span with a marker's
    # shape still fails when its note is not in the file.
    blocks = _greece_blocks_with_reference(_span("1", "n-p0009-001"))

    with pytest.raises(FidelityError) as raised:
        check_stage(FidelityBoundary.STRUCTURE, _GREECE_LINES, blocks)

    assert raised.value.detail == (
        "block b-p0000-001: the note reference span '1' names n-p0009-001, "
        "which is no note"
    )


@pytest.mark.parametrize(
    "reference",
    ["8", "(i)", "^", "345", "(12)", "(t)", "U)", "(3J", "*", "\u00ab"],
)
def test_structure_reference_span_with_a_marker_shape_passes(reference: str) -> None:
    lines = _lines_file(((f"as in Greece,{reference}", "1 A note."),))
    word_change = WordChange(
        page_index=0,
        before=(f"Greece,{reference}",),
        after=("Greece,", reference),
        reason=ChangeReason.NOTE_MARKER,
    )
    blocks = replace(
        _greece_blocks_with_reference(_span(reference, "n-p0000-001")),
        word_changes=(word_change,),
    )

    check_stage(FidelityBoundary.STRUCTURE, lines, blocks)


@pytest.mark.parametrize(
    "reference",
    [
        "the",
        "land",
        "(li)",
        "a1b",
        "1234",
        "12345",
        "(123)",
        "1 2",
        "",
        "1\n",
        # Words of the book a span could hide (architecture section 13).
        "a",
        "\u00e0",
        "I,",
        "&c.",
        "&",
        "12s",
        "\u2014",
        "-",
    ],
)
def test_structure_reference_span_without_a_marker_shape_fails(
    reference: str,
) -> None:
    blocks = _greece_blocks_with_reference(_span(reference, "n-p0000-001"))

    with pytest.raises(FidelityError) as raised:
        check_stage(FidelityBoundary.STRUCTURE, _GREECE_LINES, blocks)

    assert f"span {reference!r} does not have a marker's shape" in (raised.value.detail)


@pytest.mark.parametrize("reference", ["(a)", "U)", "(3J"])
def test_structure_reference_span_with_a_letter_that_was_a_whole_word_fails(
    reference: str,
) -> None:
    # "(a)" printed as a word of its own is a word of the book; only a span
    # split off a word by a note_marker change may hold a letter.
    lines = _lines_file(((f"as in Greece, {reference}", "1 A note."),))
    blocks = replace(
        _greece_blocks_with_reference(_span(reference, "n-p0000-001")),
        word_changes=(),
    )

    with pytest.raises(FidelityError) as raised:
        check_stage(FidelityBoundary.STRUCTURE, lines, blocks)

    assert raised.value.detail == (
        f"block b-p0000-001: the note reference span {reference!r} holds a "
        "letter but was not split off a word by a note_marker word change"
    )


def _trailing_letter_blocks(
    word: str, letter: str, kind: NoteKind = NoteKind.FOOTNOTE, rest: str = ""
) -> tuple[LinesFile, BlocksFile]:
    """The lines "as in {word}{letter}{rest}" and the blocks whose reference
    span is `letter`, split off the word by a note_marker change, to a note
    of `kind` (architecture section 13: a trailing "V" to a footnote)."""
    lines = _lines_file(((f"as in {word}{letter}{rest}", "1 A note."),))
    rest_spans = (_span(rest),) if rest else ()
    blocks = _greece_blocks("1", referenced=True)
    return lines, replace(
        blocks,
        blocks=(
            _block(
                "b-p0000-001",
                (0,),
                (
                    _span(f"as in {word}"),
                    _span(letter, "n-p0000-001"),
                    *rest_spans,
                ),
            ),
        ),
        notes=(replace(blocks.notes[0], kind=kind),),
        word_changes=(
            WordChange(
                page_index=0,
                before=(f"{word}{letter}{rest}",),
                after=(word, letter, *((rest,) if rest else ())),
                reason=ChangeReason.NOTE_MARKER,
            ),
        ),
    )


@pytest.mark.parametrize("rest", ["", "."])
def test_structure_trailing_v_split_off_a_word_to_a_footnote_passes(
    rest: str,
) -> None:
    lines, blocks = _trailing_letter_blocks("fendulm", "V", rest=rest)

    check_stage(FidelityBoundary.STRUCTURE, lines, blocks)


@pytest.mark.parametrize(
    ("word", "letter", "kind", "rest", "problem"),
    [
        # To an endnote; another letter; a "V" after a capital word or a
        # word of one letter, as "XV" or "IV" would be; a "V" from the
        # middle of a word, with letters after it.
        ("fendulm", "V", NoteKind.ENDNOTE, "", "does not have a marker's shape"),
        ("fendulm", "W", NoteKind.FOOTNOTE, "", "does not have a marker's shape"),
        ("QX", "V", NoteKind.FOOTNOTE, "", "was not split off a word"),
        ("d", "V", NoteKind.FOOTNOTE, "", "was not split off a word"),
        ("fendulm", "V", NoteKind.FOOTNOTE, "ille", "was not split off a word"),
    ],
)
def test_structure_trailing_letter_outside_the_exception_fails(
    word: str, letter: str, kind: NoteKind, rest: str, problem: str
) -> None:
    lines, blocks = _trailing_letter_blocks(word, letter, kind, rest)

    with pytest.raises(FidelityError) as raised:
        check_stage(FidelityBoundary.STRUCTURE, lines, blocks)

    assert f"span {letter!r} " in raised.value.detail
    assert problem in raised.value.detail


def test_structure_trailing_v_that_was_a_whole_word_fails() -> None:
    lines = _lines_file((("as in fendulm V", "1 A note."),))
    _, blocks = _trailing_letter_blocks("fendulm", "V")
    blocks = replace(blocks, word_changes=())

    with pytest.raises(FidelityError) as raised:
        check_stage(FidelityBoundary.STRUCTURE, lines, blocks)

    assert "span 'V' holds a letter but was not split off" in raised.value.detail


def test_structure_two_spans_with_a_letter_and_one_split_off_fails() -> None:
    # One note_marker change accounts for one span "(a)", not two.
    lines = _lines_file((("as in Greece,(a) and (a)", "1 A note."),))
    blocks = replace(
        _greece_blocks("1", referenced=True),
        blocks=(
            _block(
                "b-p0000-001",
                (0,),
                (
                    _span("as in Greece,"),
                    _span("(a)", "n-p0000-001"),
                    _span(" and"),
                    _span("(a)", "n-p0000-001"),
                ),
            ),
        ),
        word_changes=(
            WordChange(
                page_index=0,
                before=("Greece,(a)",),
                after=("Greece,", "(a)"),
                reason=ChangeReason.NOTE_MARKER,
            ),
        ),
    )

    with pytest.raises(FidelityError) as raised:
        check_stage(FidelityBoundary.STRUCTURE, lines, blocks)

    assert "span '(a)' holds a letter but was not split off" in raised.value.detail


def _heading(label: str | None, title: str) -> Block:
    return replace(
        _block("b-p0000-001", (0,), (_span(title),)),
        kind=BlockKind.HEADING,
        level=1,
        label=label,
    )


def test_structure_heading_label_counts_as_words_of_its_block() -> None:
    lines = _lines_file((("CHAPTER III.", "THE EARLY YEARS"),))
    blocks = _blocks_file((_heading("CHAPTER III.", "THE EARLY YEARS"),))

    check_stage(FidelityBoundary.STRUCTURE, lines, blocks)


def test_structure_heading_label_not_in_the_lines_is_invented() -> None:
    lines = _lines_file((("THE EARLY YEARS",),))
    blocks = _blocks_file((_heading("CHAPTER III.", "THE EARLY YEARS"),))

    with pytest.raises(FidelityError) as raised:
        check_stage(FidelityBoundary.STRUCTURE, lines, blocks)

    assert raised.value.missing == frozendict()
    assert raised.value.invented == frozendict({"CHAPTER": 1, "III.": 1})
    assert "'CHAPTER': input none, output block b-p0000-001 page 0" in (
        raised.value.detail
    )


def test_structure_heading_label_dropped_from_the_block_is_missing() -> None:
    lines = _lines_file((("V", "NORMANDY AND FRANCE"),))
    blocks = _blocks_file((_heading(None, "NORMANDY AND FRANCE"),))

    with pytest.raises(FidelityError) as raised:
        check_stage(FidelityBoundary.STRUCTURE, lines, blocks)

    assert raised.value.missing == frozendict({"V": 1})
    assert raised.value.invented == frozendict()


@pytest.mark.parametrize(
    ("lines", "block_text", "change"),
    [
        # A letter changed: Greece became Greek.
        (
            ("as in Greece",),
            "as in Greek",
            WordChange(
                page_index=0,
                before=("Greece",),
                after=("Greek",),
                reason=ChangeReason.NOTE_MARKER,
            ),
        ),
        # A deletion: "Greece" dropped with nothing after it.
        (
            ("as in Greece",),
            "as in",
            WordChange(
                page_index=0,
                before=("Greece",),
                after=(),
                reason=ChangeReason.HYPHEN_JOIN,
            ),
        ),
        # An invention: "Greece" added from nothing.
        (
            ("as in",),
            "as in Greece",
            WordChange(
                page_index=0,
                before=(),
                after=("Greece",),
                reason=ChangeReason.NOTE_MARKER,
            ),
        ),
        # A hyphen join whose first part has no hyphen.
        (
            ("to repli", "cate it."),
            "to replicate it.",
            WordChange(
                page_index=0,
                before=("repli", "cate"),
                after=("replicate",),
                reason=ChangeReason.HYPHEN_JOIN,
            ),
        ),
        # A hyphen join that invents letters: the tomatoda of ocr_lab.
        (
            ("toma-", "to da"),
            "tomatoda da",
            WordChange(
                page_index=0,
                before=("toma-", "to"),
                after=("tomatoda",),
                reason=ChangeReason.HYPHEN_JOIN,
            ),
        ),
        # A hyphen join of three words.
        (
            ("re-", "pli-", "cate"),
            "replicate",
            WordChange(
                page_index=0,
                before=("re-", "pli-", "cate"),
                after=("replicate",),
                reason=ChangeReason.HYPHEN_JOIN,
            ),
        ),
        # A kept hyphen whose word drops the hyphen.
        (
            ("an Anglo-", "Saxon king"),
            "an AngloSaxon king",
            WordChange(
                page_index=0,
                before=("Anglo-", "Saxon"),
                after=("AngloSaxon",),
                reason=ChangeReason.HYPHEN_KEPT,
            ),
        ),
        # A kept hyphen whose first part has no hyphen.
        (
            ("an Anglo", "Saxon king"),
            "an AngloSaxon king",
            WordChange(
                page_index=0,
                before=("Anglo", "Saxon"),
                after=("AngloSaxon",),
                reason=ChangeReason.HYPHEN_KEPT,
            ),
        ),
        # A guessed join that changes a letter.
        (
            ("Bal-", "hazar"),
            "Balthazar",
            WordChange(
                page_index=0,
                before=("Bal-", "hazar"),
                after=("Balthazar",),
                reason=ChangeReason.HYPHEN_JOIN_GUESSED,
            ),
        ),
        # A kept hyphen written as the not sign of the text layer.
        (
            ("in 1830¬", "40 then"),
            "in 1830¬40 then",
            WordChange(
                page_index=0,
                before=("1830¬", "40"),
                after=("1830¬40",),
                reason=ChangeReason.HYPHEN_KEPT,
            ),
        ),
        # A guessed join that keeps the hyphen.
        (
            ("Bal-", "hazar"),
            "Bal-hazar",
            WordChange(
                page_index=0,
                before=("Bal-", "hazar"),
                after=("Bal-hazar",),
                reason=ChangeReason.HYPHEN_JOIN_GUESSED,
            ),
        ),
    ],
    ids=[
        "changed-letter",
        "deletion",
        "invention",
        "no-hyphen",
        "tomatoda",
        "three-words",
        "kept-hyphen-dropped",
        "kept-without-hyphen",
        "kept-as-not-sign",
        "guessed-changed-letter",
        "guessed-hyphen-kept",
    ],
)
def test_structure_word_change_that_breaks_its_rules_fails(
    lines: tuple[str, ...], block_text: str, change: WordChange
) -> None:
    # Each change accounts for the words exactly, so only its rules can
    # make the check fail.
    blocks = _blocks_file(
        (_block("b-p0000-001", (0,), (_span(block_text),)),), word_changes=(change,)
    )

    with pytest.raises(FidelityError) as raised:
        check_stage(FidelityBoundary.STRUCTURE, _lines_file((lines,)), blocks)

    assert raised.value.missing == frozendict()
    assert raised.value.invented == frozendict()
    assert "word change on page 0" in raised.value.detail
    assert repr(change.before) in raised.value.detail


@pytest.mark.parametrize("text", ["10\xa0000", "a\tb"], ids=["no-break-space", "tab"])
def test_structure_word_holding_white_space_splits_the_same_on_both_sides(
    text: str,
) -> None:
    # The helpers split on white space, so the line is built by hand to
    # keep the text as one word of lines.json.
    lines = LinesFile(
        source_pdf_sha256=_SHA,
        pages=(
            PageLayout(
                index=0,
                regions=(Region(_BOX, (Line(_BOX, (Word(text, _BOX, None),)),)),),
                figures=(),
            ),
        ),
        rereads=(),
    )
    blocks = _blocks_file((_block("b-p0000-001", (0,), (_span(text),)),))

    check_stage(FidelityBoundary.STRUCTURE, lines, blocks)


def test_structure_with_a_word_once_in_the_input_and_twice_in_the_output_fails() -> (
    None
):
    lines = _lines_file((("the cat",),))
    blocks = _blocks_file((_block("b-p0000-001", (0,), (_span("the the cat"),)),))

    with pytest.raises(FidelityError) as raised:
        check_stage(FidelityBoundary.STRUCTURE, lines, blocks)

    assert raised.value.missing == frozendict()
    assert raised.value.invented == frozendict({"the": 1})


def test_structure_detail_names_the_word_change_that_produced_a_missing_word() -> None:
    # The join is valid, but the block lost the word it produced.
    blocks = _blocks_file(
        (_block("b-p0000-001", (0, 1), (_span("to it."),)),),
        word_changes=(
            WordChange(
                page_index=0,
                before=("repli-", "cate"),
                after=("replicate",),
                reason=ChangeReason.HYPHEN_JOIN,
            ),
        ),
    )

    with pytest.raises(FidelityError) as raised:
        check_stage(FidelityBoundary.STRUCTURE, _HYPHEN_LINES, blocks)

    assert raised.value.missing == frozendict({"replicate": 1})
    assert raised.value.invented == frozendict()
    assert "'replicate': input none, output word change page 0" in raised.value.detail


def test_check_stage_with_files_of_the_wrong_boundary_raises_type_error() -> None:
    lines = _lines_file((("a",),))

    with pytest.raises(
        TypeError, match="layout boundary was given LinesFile and LinesFile"
    ):
        check_stage(FidelityBoundary.LAYOUT, lines, lines)  # ty: ignore[no-matching-overload]


# markdown: blocks.json against book.md as Pandoc reads it


def test_markdown_with_the_same_words_passes() -> None:
    blocks = _blocks_file(
        (
            _block("b-p0000-001", (0,), (_span("First paragraph."),)),
            _block("b-p0001-001", (1,), (_span("Second, "), _span("in two spans."))),
        ),
        removals=(
            Removal(
                page_index=1, box=_BOX, text="81", reason=RemovalReason.PAGE_NUMBER
            ),
        ),
    )
    markdown = _markdown(
        (
            ("First", "b-p0000-001"),
            ("paragraph.", "b-p0000-001"),
            ("Second,", "b-p0001-001"),
            ("in", "b-p0001-001"),
            ("two", "b-p0001-001"),
            ("spans.", "b-p0001-001"),
        ),
        note_count=0,
    )

    check_stage(FidelityBoundary.MARKDOWN, blocks, markdown)


def test_markdown_referenced_note_marker_and_reference_are_not_words() -> None:
    blocks = _greece_blocks("1", referenced=True)
    markdown = _markdown(
        (
            ("as", "b-p0000-001"),
            ("in", "b-p0000-001"),
            ("Greece,", "b-p0000-001"),
            ("A", "b-p0000-001"),
            ("note.", "b-p0000-001"),
            ("and", "b-p0000-001"),
        ),
        note_count=1,
    )

    check_stage(FidelityBoundary.MARKDOWN, blocks, markdown)


def test_markdown_unreferenced_note_marker_is_a_word() -> None:
    blocks = _blocks_file(
        (_block("b-p0000-001", (0,), (_span("Text."),)),),
        notes=(
            Note(
                id="n-p0000-001",
                kind=NoteKind.FOOTNOTE,
                marker="*",
                blocks=(_block("b-p0000-002", (0,), (_span("An endnote."),)),),
                origin=(Origin(0, _BOX),),
                referenced=False,
            ),
        ),
    )
    markdown = _markdown(
        (("Text.", "b-p0000-001"), ("An", "b-p0000-002"), ("endnote.", "b-p0000-002")),
        note_count=0,
    )

    with pytest.raises(FidelityError) as raised:
        check_stage(FidelityBoundary.MARKDOWN, blocks, markdown)

    assert raised.value.boundary is FidelityBoundary.MARKDOWN
    assert raised.value.missing == frozendict({"*": 1})
    assert raised.value.invented == frozendict()
    assert "'*': input note n-p0000-001 page 0, output none" in raised.value.detail


def test_markdown_two_note_references_against_one_pandoc_note_fail() -> None:
    blocks = _blocks_file(
        (
            _block(
                "b-p0000-001",
                (0,),
                (
                    _span("One"),
                    _span("1", "n-p0000-001"),
                    _span(" two"),
                    _span("2", "n-p0000-002"),
                ),
            ),
        ),
        notes=tuple(
            Note(
                id=f"n-p0000-00{number}",
                kind=NoteKind.FOOTNOTE,
                marker=str(number),
                blocks=(
                    _block(
                        f"b-p0000-00{number + 1}", (0,), (_span(f"Note {number}."),)
                    ),
                ),
                origin=(Origin(0, _BOX),),
                referenced=True,
            )
            for number in (1, 2)
        ),
    )
    markdown = _markdown(
        (
            ("One", "b-p0000-001"),
            ("Note", "b-p0000-001"),
            ("1.", "b-p0000-001"),
            ("two", "b-p0000-001"),
            ("Note", "b-p0000-001"),
            ("2.", "b-p0000-001"),
        ),
        note_count=1,
    )

    with pytest.raises(FidelityError) as raised:
        check_stage(FidelityBoundary.MARKDOWN, blocks, markdown)

    assert raised.value.missing == frozendict()
    assert raised.value.invented == frozendict()
    assert (
        "references to footnotes in blocks.json: 2; notes in the Markdown: 1"
        in raised.value.detail
    )


def test_markdown_with_a_word_twice_in_the_blocks_and_once_in_the_markdown_fails() -> (
    None
):
    blocks = _blocks_file((_block("b-p0000-001", (0,), (_span("the the cat"),)),))
    markdown = _markdown((("the", "b-p0000-001"), ("cat", "b-p0000-001")), note_count=0)

    with pytest.raises(FidelityError) as raised:
        check_stage(FidelityBoundary.MARKDOWN, blocks, markdown)

    assert raised.value.missing == frozendict({"the": 1})
    assert raised.value.invented == frozendict()


def test_markdown_reference_pandoc_left_as_text_is_an_invented_word() -> None:
    # A reference with no definition comes back from Pandoc as the text
    # "Greece,[^1]" and no note.
    blocks = _greece_blocks("1", referenced=True)
    markdown = _markdown(
        (
            ("as", "b-p0000-001"),
            ("in", "b-p0000-001"),
            ("Greece,[^1]", "b-p0000-001"),
            ("and", "b-p0000-001"),
            ("A", "b-p0000-001"),
            ("note.", "b-p0000-001"),
        ),
        note_count=0,
    )

    with pytest.raises(FidelityError) as raised:
        check_stage(FidelityBoundary.MARKDOWN, blocks, markdown)

    assert raised.value.missing == frozendict({"Greece,": 1})
    assert raised.value.invented == frozendict({"Greece,[^1]": 1})
    assert "references to footnotes in blocks.json: 1; notes in the Markdown: 0" in (
        raised.value.detail
    )


def test_markdown_counts_note_references_inside_note_blocks() -> None:
    # The body refers to note 1, and note 1 to note 2: two references.
    blocks = _blocks_file(
        (_block("b-p0000-001", (0,), (_span("Text"), _span("1", "n-p0000-001"))),),
        notes=(
            Note(
                id="n-p0000-001",
                kind=NoteKind.FOOTNOTE,
                marker="1",
                blocks=(
                    _block(
                        "b-p0000-002",
                        (0,),
                        (_span("First"), _span("2", "n-p0000-002")),
                    ),
                ),
                origin=(Origin(0, _BOX),),
                referenced=True,
            ),
            Note(
                id="n-p0000-002",
                kind=NoteKind.FOOTNOTE,
                marker="2",
                blocks=(_block("b-p0000-003", (0,), (_span("Second"),)),),
                origin=(Origin(0, _BOX),),
                referenced=True,
            ),
        ),
    )
    markdown = _markdown(
        (("Text", "b-p0000-001"), ("First", "b-p0000-001"), ("Second", "b-p0000-001")),
        note_count=1,
    )

    with pytest.raises(FidelityError) as raised:
        check_stage(FidelityBoundary.MARKDOWN, blocks, markdown)

    assert "references to footnotes in blocks.json: 2; notes in the Markdown: 1" in (
        raised.value.detail
    )


def test_markdown_heading_label_counts_as_words_of_its_block() -> None:
    blocks = _blocks_file((_heading("V", "NORMANDY AND FRANCE"),))
    markdown = _markdown(
        (
            ("V", "b-p0000-001"),
            ("NORMANDY", "b-p0000-001"),
            ("AND", "b-p0000-001"),
            ("FRANCE", "b-p0000-001"),
        ),
        note_count=0,
    )

    check_stage(FidelityBoundary.MARKDOWN, blocks, markdown)


def test_markdown_heading_label_left_out_of_the_markdown_is_missing() -> None:
    blocks = _blocks_file((_heading("V", "NORMANDY AND FRANCE"),))
    markdown = _markdown(
        (
            ("NORMANDY", "b-p0000-001"),
            ("AND", "b-p0000-001"),
            ("FRANCE", "b-p0000-001"),
        ),
        note_count=0,
    )

    with pytest.raises(FidelityError) as raised:
        check_stage(FidelityBoundary.MARKDOWN, blocks, markdown)

    assert raised.value.missing == frozendict({"V": 1})
    assert raised.value.invented == frozendict()
    assert "'V': input block b-p0000-001 page 0, output none" in raised.value.detail


def _endnote_blocks(*, referenced: bool) -> BlocksFile:
    """A paragraph whose word "Law" is followed by a reference to the
    endnote "291." when `referenced`, and the endnote."""
    reference = (_span("291", "n-p0001-001"),) if referenced else ()
    return _blocks_file(
        (_block("b-p0000-001", (0,), (_span("of the Law"), *reference)),),
        notes=(
            Note(
                id="n-p0001-001",
                kind=NoteKind.ENDNOTE,
                marker="291.",
                blocks=(_block("b-p0001-001", (1,), (_span("See Gierke."),)),),
                origin=(Origin(1, _BOX),),
                referenced=referenced,
            ),
        ),
    )


_ENDNOTE_MARKDOWN = (
    ("of", "b-p0000-001"),
    ("the", "b-p0000-001"),
    ("Law", "b-p0000-001"),
    ("291.", "b-p0001-001"),
    ("See", "b-p0001-001"),
    ("Gierke.", "b-p0001-001"),
)


# The reference "291" as the text of its link, a word of its own.
_ENDNOTE_LINK_WORD = (("291", "b-p0000-001"),)


def test_markdown_unreferenced_endnote_marker_is_a_word() -> None:
    blocks = _endnote_blocks(referenced=False)
    markdown = _markdown(_ENDNOTE_MARKDOWN, note_count=0, note_link_count=0)

    check_stage(FidelityBoundary.MARKDOWN, blocks, markdown)


def test_markdown_referenced_endnote_marker_and_link_text_are_words() -> None:
    blocks = _endnote_blocks(referenced=True)
    markdown = _markdown(
        _ENDNOTE_MARKDOWN + _ENDNOTE_LINK_WORD,
        note_count=0,
        note_link_count=1,
        back_link_count=1,
    )

    check_stage(FidelityBoundary.MARKDOWN, blocks, markdown)


def test_markdown_endnote_link_without_the_reference_text_fails() -> None:
    blocks = _endnote_blocks(referenced=True)
    markdown = _markdown(
        _ENDNOTE_MARKDOWN, note_count=0, note_link_count=1, back_link_count=1
    )

    with pytest.raises(FidelityError) as raised:
        check_stage(FidelityBoundary.MARKDOWN, blocks, markdown)

    assert raised.value.missing == frozendict({"291": 1})
    assert raised.value.invented == frozendict()


def test_markdown_endnote_link_with_a_word_put_into_it_fails() -> None:
    blocks = _endnote_blocks(referenced=True)
    markdown = _markdown(
        (*_ENDNOTE_MARKDOWN, *_ENDNOTE_LINK_WORD, ("and", "b-p0000-001")),
        note_count=0,
        note_link_count=1,
        back_link_count=1,
    )

    with pytest.raises(FidelityError) as raised:
        check_stage(FidelityBoundary.MARKDOWN, blocks, markdown)

    assert raised.value.missing == frozendict()
    assert raised.value.invented == frozendict({"and": 1})


def test_markdown_endnote_counts_differing_with_footnote_counts_agreeing_fail() -> None:
    blocks = _endnote_blocks(referenced=True)
    markdown = _markdown(
        _ENDNOTE_MARKDOWN + _ENDNOTE_LINK_WORD,
        note_count=0,
        note_link_count=0,
        back_link_count=1,
    )

    with pytest.raises(FidelityError) as raised:
        check_stage(FidelityBoundary.MARKDOWN, blocks, markdown)

    assert raised.value.missing == frozendict()
    assert raised.value.invented == frozendict()
    assert raised.value.detail == (
        "references to footnotes in blocks.json: 0; notes in the Markdown: 0; "
        "references to endnotes in blocks.json: 1; note reference links in the "
        "Markdown: 0"
    )


@pytest.mark.parametrize(
    ("reference", "note_id", "problem"),
    [
        ("land", "n-p0001-001", "does not have a marker's shape"),
        ("291", "n-p0009-001", "which is no note"),
    ],
    ids=["no-marker-shape", "no-note"],
)
def test_markdown_endnote_reference_span_that_structure_would_refuse_fails(
    reference: str, note_id: str, problem: str
) -> None:
    # The reference checks run at markdown too, on the blocks with the
    # edits applied, so a span an edit changed is checked again.
    blocks = _endnote_blocks(referenced=True)
    blocks = replace(
        blocks,
        blocks=(
            replace(
                blocks.blocks[0],
                spans=(_span("of the Law"), _span(reference, note_id)),
            ),
        ),
    )
    markdown = _markdown(
        (*_ENDNOTE_MARKDOWN, (reference, "b-p0000-001")),
        note_count=0 if note_id == "n-p0001-001" else 1,
        note_link_count=1 if note_id == "n-p0001-001" else 0,
        back_link_count=1,
    )

    with pytest.raises(FidelityError) as raised:
        check_stage(FidelityBoundary.MARKDOWN, blocks, markdown)

    assert raised.value.boundary is FidelityBoundary.MARKDOWN
    assert problem in raised.value.detail


def test_markdown_referenced_endnote_without_its_marker_fails() -> None:
    blocks = _endnote_blocks(referenced=True)
    markdown = _markdown(
        tuple(word for word in _ENDNOTE_MARKDOWN if word[0] != "291.")
        + _ENDNOTE_LINK_WORD,
        note_count=0,
        note_link_count=1,
        back_link_count=1,
    )

    with pytest.raises(FidelityError) as raised:
        check_stage(FidelityBoundary.MARKDOWN, blocks, markdown)

    assert raised.value.missing == frozendict({"291.": 1})
    assert raised.value.invented == frozendict()
    assert "'291.': input note n-p0001-001 page 1, output none" in (raised.value.detail)


def test_markdown_endnote_reference_made_a_pandoc_note_fails() -> None:
    # A reference to an endnote is a link to the endnote's place; a Pandoc
    # note would show the endnote's text twice.
    blocks = _endnote_blocks(referenced=True)
    markdown = _markdown(
        _ENDNOTE_MARKDOWN + _ENDNOTE_LINK_WORD,
        note_count=1,
        note_link_count=0,
        back_link_count=1,
    )

    with pytest.raises(FidelityError) as raised:
        check_stage(FidelityBoundary.MARKDOWN, blocks, markdown)

    assert raised.value.missing == frozendict()
    assert raised.value.invented == frozendict()
    assert raised.value.detail == (
        "references to footnotes in blocks.json: 0; notes in the Markdown: 1; "
        "references to endnotes in blocks.json: 1; note reference links in the "
        "Markdown: 0"
    )


# read_markdown: book.md as Pandoc reads it


def _texts(markdown: MarkdownWords) -> tuple[str, ...]:
    return tuple(word.text for word in markdown.words)


@pytest.mark.pandoc
def test_read_markdown_separates_the_last_word_of_a_paragraph_from_the_next() -> None:
    markdown = read_markdown("a b\n\nc\n")

    assert _texts(markdown) == ("a", "b", "c")
    assert markdown.note_count == 0


@pytest.mark.pandoc
def test_read_markdown_reads_escaped_punctuation_as_itself() -> None:
    assert _texts(read_markdown("\\*x\\*y\n")) == ("*x*y",)


@pytest.mark.pandoc
def test_read_markdown_keeps_a_word_half_in_emphasis_as_one_word() -> None:
    assert _texts(read_markdown("re*mark*able **bold**ly\n")) == (
        "remarkable",
        "boldly",
    )


@pytest.mark.pandoc
def test_read_markdown_counts_the_words_of_a_footnote_apart_from_the_text() -> None:
    markdown = read_markdown("Text[^1] and.\n\n[^1]: A *short* note.\n")

    assert _texts(markdown) == ("Text", "A", "short", "note.", "and.")


@pytest.mark.pandoc
def test_read_markdown_counts_two_footnotes() -> None:
    markdown = read_markdown("One[^1] two[^2].\n\n[^1]: First.\n\n[^2]: Second.\n")

    assert markdown.note_count == 2


@pytest.mark.pandoc
def test_read_markdown_gives_each_word_the_id_of_its_div() -> None:
    markdown = read_markdown(
        "Before.\n\n::: {#b-p0000-001}\nIn the div.\n:::\n\n# A heading {#b-p0001-001}\n"
    )

    assert markdown.words == (
        MarkdownWord("Before.", None),
        MarkdownWord("In", "b-p0000-001"),
        MarkdownWord("the", "b-p0000-001"),
        MarkdownWord("div.", "b-p0000-001"),
        MarkdownWord("A", "b-p0001-001"),
        MarkdownWord("heading", "b-p0001-001"),
    )


@pytest.mark.pandoc
def test_read_markdown_gives_a_div_without_an_id_the_id_around_it() -> None:
    markdown = read_markdown(":::: {#b-p0000-001}\n::: quote\n> Quoted.\n:::\n::::\n")

    assert markdown.words == (MarkdownWord("Quoted.", "b-p0000-001"),)


@pytest.mark.pandoc
def test_read_markdown_gives_a_heading_without_an_id_the_id_of_its_div() -> None:
    # Pandoc's auto_identifiers would give the heading the id chapter-one,
    # which is no block of book.md.
    markdown = read_markdown("::: {#b-p0000-001}\n# Chapter one\n:::\n")

    assert markdown.words == (
        MarkdownWord("Chapter", "b-p0000-001"),
        MarkdownWord("one", "b-p0000-001"),
    )


@pytest.mark.pandoc
def test_read_markdown_leaves_out_the_metadata() -> None:
    markdown = read_markdown(
        '---\ntitle: "The Title"\nauthor:\n- "An Author"\n---\n\nText.\n'
    )

    assert _texts(markdown) == ("Text.",)


@pytest.mark.pandoc
def test_read_markdown_with_an_unused_note_definition_raises() -> None:
    with pytest.raises(ExternalProgramError, match="not used"):
        read_markdown("Text.\n\n[^1]: A note nobody refers to.\n")


@pytest.mark.pandoc
def test_read_markdown_keeps_a_reference_without_a_definition_as_text() -> None:
    markdown = read_markdown("Greece,[^1]\n")

    assert _texts(markdown) == ("Greece,[^1]",)
    assert markdown.note_count == 0


@pytest.mark.pandoc
def test_read_markdown_with_an_element_galley_does_not_write_raises() -> None:
    with pytest.raises(ExternalProgramError, match=r"BulletList.*b-p0000-001"):
        read_markdown("::: {#b-p0000-001}\n- an item\n:::\n")


@pytest.mark.pandoc
def test_read_markdown_counts_a_link_to_an_endnote_and_its_text_as_a_word() -> None:
    markdown = read_markdown(
        "::: {#b-p0000-001}\n"
        'of the Law[291](#n-p0001-001){epub:type="noteref"} and\n'
        ":::\n"
    )

    assert _texts(markdown) == ("of", "the", "Law", "291", "and")
    assert markdown.note_link_count == 1
    assert markdown.note_count == 0


@pytest.mark.pandoc
def test_read_markdown_with_a_link_that_is_no_note_reference_raises() -> None:
    with pytest.raises(ExternalProgramError, match=r"Link.*b-p0000-001"):
        read_markdown("::: {#b-p0000-001}\nsee [the law](#n-p0001-001)\n:::\n")


# The walk of Pandoc's JSON, on literal JSON as Pandoc 3.14 writes it


def _str(text: str) -> str:
    return f'{{"t":"Str","c":"{text}"}}'


def _div(div_id: str, blocks: str) -> str:
    return f'{{"t":"Div","c":[["{div_id}",[],[]],[{blocks}]]}}'


def _pandoc_document(blocks: str) -> str:
    return f'{{"pandoc-api-version":[1,23,1,2],"meta":{{}},"blocks":[{blocks}]}}'


_SPACE = '{"t":"Space"}'


def test_walk_joins_adjacent_text_and_splits_at_spaces_and_blocks() -> None:
    paragraph_a = f'{{"t":"Para","c":[{_str("a")},{_SPACE},{_str("b")}]}}'
    paragraph_c = f'{{"t":"Para","c":[{_str("c")},{_str("d")}]}}'

    markdown = _words_of_pandoc_json(_pandoc_document(f"{paragraph_a},{paragraph_c}"))

    assert _texts(markdown) == ("a", "b", "cd")
    assert markdown.note_count == 0


def test_walk_gives_words_of_nested_divs_the_innermost_id() -> None:
    inner = _div("b-p0000-002", f'{{"t":"Para","c":[{_str("inner")}]}}')
    outer = _div("b-p0000-001", f'{{"t":"Para","c":[{_str("outer")}]}},{inner}')

    markdown = _words_of_pandoc_json(_pandoc_document(outer))

    assert markdown.words == (
        MarkdownWord("outer", "b-p0000-001"),
        MarkdownWord("inner", "b-p0000-002"),
    )


def test_walk_counts_a_note_and_separates_its_words() -> None:
    note = f'{{"t":"Note","c":[{{"t":"Para","c":[{_str("note")}]}}]}}'
    paragraph = f'{{"t":"Para","c":[{_str("Greece,")},{note},{_str("and")}]}}'

    markdown = _words_of_pandoc_json(_pandoc_document(paragraph))

    assert _texts(markdown) == ("Greece,", "note", "and")
    assert markdown.note_count == 1


def test_walk_of_an_element_outside_any_div_raises_saying_so() -> None:
    bullet_list = f'{{"t":"BulletList","c":[[{{"t":"Plain","c":[{_str("item")}]}}]]}}'

    with pytest.raises(
        ExternalProgramError, match="BulletList element outside any block"
    ):
        _words_of_pandoc_json(_pandoc_document(bullet_list))


def _link(attributes: str, inlines: str) -> str:
    return (
        f'{{"t":"Link","c":[["",[],[{attributes}]],[{inlines}],["#n-p0001-001",""]]}}'
    )


def test_walk_counts_a_link_to_an_endnote_and_its_text_as_a_word_of_its_own() -> None:
    link = _link('["epub:type","noteref"]', _str("291"))
    paragraph = f'{{"t":"Para","c":[{_str("Law")},{link},{_str("and")}]}}'

    markdown = _words_of_pandoc_json(_pandoc_document(_div("b-p0000-001", paragraph)))

    assert _texts(markdown) == ("Law", "291", "and")
    assert markdown.note_link_count == 1
    assert markdown.note_count == 0


def test_walk_of_an_endnote_link_holding_an_element_galley_refuses_raises() -> None:
    code = '{"t":"Code","c":[["",[],[]],"291"]}'
    link = _link('["epub:type","noteref"]', code)
    paragraph = f'{{"t":"Para","c":[{_str("Law")},{link}]}}'

    with pytest.raises(ExternalProgramError, match="Code element in block b-p0000-001"):
        _words_of_pandoc_json(_pandoc_document(_div("b-p0000-001", paragraph)))


@pytest.mark.parametrize(
    "attributes",
    ['["epub:type","chapter"]', '["class","noteref"]', ""],
    ids=["other-epub-type", "other-attribute", "none"],
)
def test_walk_of_a_link_that_is_no_note_reference_raises(attributes: str) -> None:
    link = _link(attributes, _str("291"))
    paragraph = f'{{"t":"Para","c":[{_str("Law")},{link}]}}'

    with pytest.raises(ExternalProgramError, match="Link element in block b-p0000-001"):
        _words_of_pandoc_json(_pandoc_document(_div("b-p0000-001", paragraph)))


# A figure's image (architecture section 13): the caption counts once, and
# no word hides in an image's alt text, title or attributes.


@pytest.mark.pandoc
def test_read_markdown_counts_a_figure_caption_once_in_the_figure_block() -> None:
    markdown = read_markdown(
        "::: {#b-p0016-001 .figure}\n![PLATE I\\. The battle\\.](images/plate-0016.png)\n:::\n"
    )

    assert markdown.words == tuple(
        MarkdownWord(text, "b-p0016-001") for text in ("PLATE", "I.", "The", "battle.")
    )


@pytest.mark.pandoc
def test_read_markdown_reads_a_figure_image_without_a_caption_as_no_word() -> None:
    markdown = read_markdown(
        "::: {#b-p0016-001 .figure}\n![](images/plate-0016.png)\n:::\n"
    )

    assert markdown.words == ()


@pytest.mark.pandoc
@pytest.mark.parametrize(
    "markdown_text",
    [
        "Before ![a plate](images/plate-0016.png) after.\n",
        "![a plate](images/plate-0016.png) after.\n",
        '![PLATE I](images/plate-0016.png "hidden words")\n',
        "![PLATE I](images/plate-0016.png){#hidden}\n",
        '![PLATE I](images/plate-0016.png){fig-alt="hidden words"}\n',
        '![](images/plate-0016.png "hidden words")\n',
    ],
    ids=[
        "inside a sentence",
        "before words",
        "with a title",
        "with an id",
        "with an alt text of its own",
        "without a caption, with a title",
    ],
)
def test_read_markdown_refuses_an_image_that_is_no_figure_of_galley(
    markdown_text: str,
) -> None:
    with pytest.raises(ExternalProgramError, match="(Image|Figure) element"):
        read_markdown(f"::: {{#b-p0016-001}}\n{markdown_text}:::\n")


def _image(alt: str, title: str = "") -> str:
    return (
        f'{{"t":"Image","c":[["",[],[]],[{alt}],["images/plate-0016.png","{title}"]]}}'
    )


def _figure(caption: str, body: str) -> str:
    return (
        f'{{"t":"Figure","c":[["",[],[]],[null,[{{"t":"Plain","c":[{caption}]}}]],'
        f"[{body}]]}}"
    )


def test_walk_counts_the_caption_of_a_figure_and_not_its_image_alt_text() -> None:
    caption = f"{_str('PLATE')},{_SPACE},{_str('I.')}"
    figure = _figure(caption, f'{{"t":"Plain","c":[{_image(caption)}]}}')

    markdown = _words_of_pandoc_json(_pandoc_document(_div("b-p0016-001", figure)))

    assert _texts(markdown) == ("PLATE", "I.")


@pytest.mark.parametrize(
    "body",
    [
        f'{{"t":"Plain","c":[{_image(_str("hidden"))}]}}',
        f'{{"t":"Plain","c":[{_image(_str("PLATE"))},{_str("hidden")}]}}',
        f'{{"t":"Plain","c":[{_image(_str("PLATE"))}]}},{{"t":"Para","c":[{_str("x")}]}}',
        f'{{"t":"Plain","c":[{_image(_str("PLATE"), "hidden")}]}}',
        f'{{"t":"Para","c":[{_str("hidden")}]}}',
    ],
    ids=[
        "alt text not the caption",
        "a word beside the image",
        "a block after the image",
        "a title",
        "no image",
    ],
)
def test_walk_of_a_figure_that_galley_does_not_write_raises(body: str) -> None:
    figure = _figure(_str("PLATE"), body)

    with pytest.raises(
        ExternalProgramError, match="Figure element in block b-p0016-001"
    ):
        _words_of_pandoc_json(_pandoc_document(_div("b-p0016-001", figure)))


@pytest.mark.thread_unsafe(reason="changes PATH")
def test_read_markdown_without_pandoc_raises(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("PATH", str(tmp_path))

    with pytest.raises(ExternalProgramError, match="pandoc"):
        read_markdown("Text.\n")


# The layout boundary with re-read regions (reocr spec, section 4, "The
# fidelity check"). A page with a body word and a margin note of three
# layer words, which Tesseract reads as two.

_BODY = Word("Normandy", Box(100.0, 50.0, 160.0, 60.0), None)
_NOTE_LAYER = (
    Word("Wil-", Box(20.0, 50.0, 30.0, 58.0), None),
    Word("1", Box(31.0, 50.0, 33.0, 58.0), None),
    Word("iam", Box(34.0, 50.0, 44.0, 58.0), None),
)
_NOTE_OCR = (
    Word("William", Box(20.0, 50.0, 44.0, 58.0), 91.0),
    Word("I.", Box(20.0, 59.0, 26.0, 67.0), 88.0),
)
_NOTE_WORDS = WordsFile(
    source_pdf_sha256=_SHA,
    pages=(
        PageWords(
            index=0,
            text_source=TextSource.TEXT_LAYER,
            words=(_BODY, *_NOTE_LAYER),
            figures=(),
        ),
        PageWords(
            index=1,
            text_source=TextSource.TEXT_LAYER,
            words=(Word("Rouen", _BOX, None),),
            figures=(),
        ),
    ),
    removals=(),
)


def _note_reread(
    layer_words: tuple[Word, ...] = _NOTE_LAYER,
    *,
    page_index: int = 0,
    kept: bool = True,
) -> Reread:
    return Reread(
        page_index=page_index,
        kind=RereadKind.MARGIN_NOTE,
        box=Box(18.0, 48.0, 46.0, 69.0),
        layer_words=layer_words,
        ocr_words=_NOTE_OCR,
        layer_score=-1,
        ocr_score=2,
        kept=kept,
        dropped_junk_count=0,
    )


def _note_lines(page_0: tuple[Word, ...], rereads: tuple[Reread, ...]) -> LinesFile:
    """lines.json of _NOTE_WORDS: page 0 with `page_0` in one line, page 1
    as words.json has it."""
    return LinesFile(
        source_pdf_sha256=_SHA,
        pages=(
            PageLayout(
                index=0, regions=(Region(_BOX, (Line(_BOX, page_0),)),), figures=()
            ),
            PageLayout(
                index=1,
                regions=(Region(_BOX, (Line(_BOX, (Word("Rouen", _BOX, None),)),)),),
                figures=(),
            ),
        ),
        rereads=rereads,
    )


def test_layout_with_a_kept_reread_swaps_its_layer_words_for_its_ocr_words() -> None:
    lines = _note_lines((_BODY, *_NOTE_OCR), (_note_reread(),))

    check_stage(FidelityBoundary.LAYOUT, _NOTE_WORDS, lines)


def test_layout_with_a_kept_reread_whose_ocr_words_are_missing_fails() -> None:
    lines = _note_lines((_BODY,), (_note_reread(),))

    with pytest.raises(FidelityError) as raised:
        check_stage(FidelityBoundary.LAYOUT, _NOTE_WORDS, lines)

    assert raised.value.missing == frozendict({"I.": 1, "William": 1})
    assert raised.value.invented == frozendict()


def test_layout_with_a_reread_not_kept_changes_nothing() -> None:
    lines = _note_lines((_BODY, *_NOTE_LAYER), (_note_reread(kept=False),))

    check_stage(FidelityBoundary.LAYOUT, _NOTE_WORDS, lines)


def test_layout_with_a_reread_not_kept_whose_ocr_words_are_in_the_lines_fails() -> None:
    lines = _note_lines((_BODY, *_NOTE_OCR), (_note_reread(kept=False),))

    with pytest.raises(FidelityError) as raised:
        check_stage(FidelityBoundary.LAYOUT, _NOTE_WORDS, lines)

    assert raised.value.missing == frozendict({"1": 1, "Wil-": 1, "iam": 1})
    assert raised.value.invented == frozendict({"I.": 1, "William": 1})


def test_layout_with_a_kept_reread_naming_a_word_its_page_does_not_have_fails() -> None:
    # "Wil-" at another place, and "Rouen", which is page 1's.
    elsewhere = replace(_NOTE_LAYER[0], box=Box(20.0, 70.0, 30.0, 78.0))
    for layer_words, page_index in (
        ((elsewhere, *_NOTE_LAYER[1:]), 0),
        (_NOTE_LAYER, 1),
    ):
        reread = _note_reread(layer_words, page_index=page_index)
        lines = _note_lines((_BODY, *_NOTE_OCR), (reread,))

        with pytest.raises(FidelityError) as raised:
            check_stage(FidelityBoundary.LAYOUT, _NOTE_WORDS, lines)

        assert raised.value.missing == frozendict()
        assert raised.value.invented == frozendict()
        assert f"page {page_index} does not have" in raised.value.detail


def test_layout_with_a_word_in_two_kept_rereads_fails() -> None:
    # The second record names "iam" again and reads it as "iam": the words
    # alone balance, so only the record check can find it.
    second = replace(
        _note_reread((_NOTE_LAYER[2],)),
        kind=RereadKind.CUT_IN_NOTE,
        ocr_words=(Word("iam", Box(34.0, 50.0, 44.0, 58.0), 70.0),),
    )
    lines = _note_lines((_BODY, *_NOTE_OCR), (_note_reread(), second))

    with pytest.raises(FidelityError) as raised:
        check_stage(FidelityBoundary.LAYOUT, _NOTE_WORDS, lines)

    assert raised.value.missing == frozendict()
    assert "'iam'" in raised.value.detail
    assert "two kept rereads" in raised.value.detail


def test_layout_with_a_kept_reread_replacing_a_word_no_ocr_word_lies_over_fails() -> (
    None
):
    # The record names the body word "Normandy", which no word of
    # Tesseract's lies over, and the lines lack it: the words alone balance,
    # so only the record check can find it.
    reread = _note_reread((*_NOTE_LAYER, _BODY))
    lines = _note_lines(_NOTE_OCR, (reread,))

    with pytest.raises(FidelityError) as raised:
        check_stage(FidelityBoundary.LAYOUT, _NOTE_WORDS, lines)

    assert raised.value.missing == frozendict()
    assert raised.value.invented == frozendict()
    assert "'Normandy'" in raised.value.detail
    assert "none of its ocr_words lies over" in raised.value.detail


def test_layout_with_a_kept_reread_replacing_a_word_off_its_box_by_its_text_passes() -> (
    None
):
    # Tesseract also read the body word "Normandy" 10 pt above the layer's:
    # no box lies over the layer's word, but the texts match (reocr spec,
    # section 4, rule (b)).
    normandy = Word("Normandy", Box(100.0, 40.0, 160.0, 50.0), 90.0)
    reread = replace(
        _note_reread((*_NOTE_LAYER, _BODY)), ocr_words=(*_NOTE_OCR, normandy)
    )
    lines = _note_lines((*_NOTE_OCR, normandy), (reread,))

    check_stage(FidelityBoundary.LAYOUT, _NOTE_WORDS, lines)


def test_layout_with_one_ocr_word_the_only_reading_of_two_lines_words_fails() -> None:
    # Domesday page 548: Tesseract read "3" for "Dominium, 224" and
    # "dominieum," over the layer's "dominicum," one line down; a record
    # that replaces the layer's "Domini" too has "dominieum," stand for two
    # printed words, and one is lost.
    domini = Word("Domini", Box(10.0, 92.0, 30.0, 100.0), None)
    dominicum = Word("dominicum,", Box(10.0, 101.0, 30.0, 109.0), None)
    ocr = (
        Word("3", Box(60.0, 92.0, 66.0, 100.0), 40.0),
        Word("dominieum,", Box(10.0, 101.0, 30.0, 109.0), 80.0),
    )
    words = WordsFile(
        source_pdf_sha256=_SHA,
        pages=(
            PageWords(
                index=0,
                text_source=TextSource.TEXT_LAYER,
                words=(domini, dominicum),
                figures=(),
            ),
        ),
        removals=(),
    )
    reread = Reread(
        page_index=0,
        kind=RereadKind.SMALL_PRINT_PAGE,
        box=Box(0.0, 90.0, 100.0, 110.0),
        layer_words=(domini, dominicum),
        ocr_words=ocr,
        layer_score=-2,
        ocr_score=0,
        kept=True,
        dropped_junk_count=0,
    )
    lines = LinesFile(
        source_pdf_sha256=_SHA,
        pages=(
            PageLayout(
                index=0, regions=(Region(_BOX, (Line(_BOX, ocr),)),), figures=()
            ),
        ),
        rereads=(reread,),
    )

    with pytest.raises(FidelityError) as raised:
        check_stage(FidelityBoundary.LAYOUT, words, lines)

    assert "'dominieum,'" in raised.value.detail
    assert "the only ocr word that can read 'Domini'" in raised.value.detail


def _junk_and_copy_files(
    under: Word, copy: Word, ocr_word: Word, junk_words: tuple[Word, ...]
) -> tuple[WordsFile, LinesFile]:
    """words.json and lines.json of one page whose layer words `under` and
    `copy` a kept margin-note record replaces by `ocr_word`, naming
    `junk_words` as junk."""
    words = WordsFile(
        source_pdf_sha256=_SHA,
        pages=(
            PageWords(
                index=0,
                text_source=TextSource.TEXT_LAYER,
                words=(under, copy),
                figures=(),
            ),
        ),
        removals=(),
    )
    reread = Reread(
        page_index=0,
        kind=RereadKind.MARGIN_NOTE,
        box=Box(0.0, 90.0, 40.0, 120.0),
        layer_words=(under, copy),
        ocr_words=(ocr_word,),
        layer_score=-1,
        ocr_score=-1,
        kept=True,
        dropped_junk_count=0,
        junk_words=junk_words,
    )
    lines = LinesFile(
        source_pdf_sha256=_SHA,
        pages=(
            PageLayout(
                index=0,
                regions=(Region(_BOX, (Line(_BOX, (ocr_word,)),)),),
                figures=(),
            ),
        ),
        rereads=(reread,),
    )
    return words, lines


# Domesday page 36: the layer's junk "&g" lies under Tesseract's "seat-"
# and its copy "scat'" 6 pt below, out of the widened box; both are
# readings of the printed "scat-" (reocr spec, section 4, the exception in
# (a)).
_UNDER_BOX = Box(10.0, 101.0, 30.0, 106.5)  # of a line above the copy's
_SCAT = Word("scat'", Box(10.0, 107.0, 30.0, 115.0), None)
_SEAT = Word("seat-", Box(10.0, 100.0, 30.0, 108.0), 80.0)


def test_layout_with_one_ocr_word_reading_the_junk_under_it_and_its_copy_passes() -> (
    None
):
    junk = Word("&g", _UNDER_BOX, None)
    check_stage(
        FidelityBoundary.LAYOUT, *_junk_and_copy_files(junk, _SCAT, _SEAT, (junk,))
    )


@pytest.mark.parametrize("under_text", ["&g", "the", "Ælfric"])
def test_layout_with_a_word_under_the_copys_ocr_word_not_named_junk_fails(
    under_text: str,
) -> None:
    # The check has no word list: it takes as junk only the words the
    # record names, so a known word, or junk layout did not name, under
    # Tesseract's word is read by no rule.
    under = Word(under_text, _UNDER_BOX, None)
    with pytest.raises(FidelityError) as raised:
        check_stage(
            FidelityBoundary.LAYOUT, *_junk_and_copy_files(under, _SCAT, _SEAT, ())
        )
    assert f"replaces {under_text!r}" in raised.value.detail


def test_layout_with_a_word_of_the_next_line_under_the_copys_ocr_word_fails() -> None:
    # Gierke page 127: the layer's "vacant", of the next line, lies under
    # Tesseract's "Empire." beside the layer's copy "Empire."; a record
    # that has Tesseract's "Empire." read it lets "Empire." stand for two
    # printed words.
    vacant = Word("vacant", Box(10.0, 105.0, 30.0, 113.0), None)
    copy = Word("Empire.", Box(10.0, 92.0, 30.0, 100.0), None)
    empire = Word("Empire.", Box(10.0, 100.0, 30.0, 108.0), 80.0)
    with pytest.raises(FidelityError) as raised:
        check_stage(
            FidelityBoundary.LAYOUT, *_junk_and_copy_files(vacant, copy, empire, ())
        )
    assert "replaces 'vacant'" in raised.value.detail


def test_layout_with_junk_named_outside_the_layer_words_fails() -> None:
    junk = Word("&g", _UNDER_BOX, None)
    words, lines = _junk_and_copy_files(junk, _SCAT, _SEAT, (junk,))
    stray = Word("~", Box(50.0, 101.0, 60.0, 109.0), None)
    (reread,) = lines.rereads
    lines = replace(lines, rereads=(replace(reread, junk_words=(junk, stray)),))
    with pytest.raises(FidelityError) as raised:
        check_stage(FidelityBoundary.LAYOUT, words, lines)
    assert "names '~'" in raised.value.detail
    assert "not among its layer words" in raised.value.detail


# The plan owner-books (structure spec sections 22 to 25, architecture
# section 13): an epigraph's source and a note's group are words of their
# block and note; the dash before a source, a spaced sign and a word glued
# at a case change are word changes the check verifies.


def _epigraph(source: str | None, quotation: str = "The life of man.") -> Block:
    return replace(
        _block("b-p0000-002", (0,), (_span(quotation),)),
        kind=BlockKind.EPIGRAPH,
        source=source,
    )


_SOURCE_DASH = WordChange(
    page_index=0,
    before=("—Thomas",),
    after=("Thomas",),
    reason=ChangeReason.SOURCE_DASH,
)
_EPIGRAPH_LINES = _lines_file((("The life of man.", "—Thomas Hobbes, 1651"),))


def test_structure_epigraph_source_counts_as_words_of_its_block() -> None:
    blocks = _blocks_file(
        (_epigraph("Thomas Hobbes, 1651"),), word_changes=(_SOURCE_DASH,)
    )

    check_stage(FidelityBoundary.STRUCTURE, _EPIGRAPH_LINES, blocks)


def test_structure_source_dash_of_a_dash_word_and_the_word_after_passes() -> None:
    lines = _lines_file((("The life of man.", "— Hobbes"),))
    change = WordChange(
        page_index=0,
        before=("—", "Hobbes"),
        after=("Hobbes",),
        reason=ChangeReason.SOURCE_DASH,
    )
    blocks = _blocks_file((_epigraph("Hobbes"),), word_changes=(change,))

    check_stage(FidelityBoundary.STRUCTURE, lines, blocks)


def test_structure_source_dash_of_several_dashes_read_by_the_ocr_passes() -> None:
    # Haynes' OCR reads the dash as "—-" (structure spec section 22).
    lines = _lines_file((("The life of man.", "—-Hobbes"),))
    change = WordChange(
        page_index=0,
        before=("—-Hobbes",),
        after=("Hobbes",),
        reason=ChangeReason.SOURCE_DASH,
    )
    blocks = _blocks_file((_epigraph("Hobbes"),), word_changes=(change,))

    check_stage(FidelityBoundary.STRUCTURE, lines, blocks)


@pytest.mark.parametrize(
    ("lines", "blocks"),
    [
        # A dash taken off a word of the body: no epigraph has the word.
        (
            _lines_file((("—Thomas Hobbes, 1651",),)),
            _blocks_file(
                (_block("b-p0000-001", (0,), (_span("Thomas Hobbes, 1651"),)),),
                word_changes=(_SOURCE_DASH,),
            ),
        ),
        # An epigraph whose source starts with another word.
        (
            _lines_file((("The life of man.", "Hobbes", "—Thomas 1651"),)),
            _blocks_file(
                (
                    _epigraph("Hobbes"),
                    _block("b-p0000-003", (0,), (_span("Thomas 1651"),)),
                ),
                word_changes=(_SOURCE_DASH,),
            ),
        ),
        # The epigraph's one part is on another page.
        (
            _lines_file(((), ("The life of man.", "—Thomas Hobbes, 1651"))),
            _blocks_file(
                (replace(_epigraph("Thomas Hobbes, 1651"), origin=(Origin(1, _BOX),)),),
                word_changes=(_SOURCE_DASH,),
            ),
        ),
    ],
    ids=["body-word", "other-source", "other-page"],
)
def test_structure_source_dash_not_at_an_epigraphs_source_fails(
    lines: LinesFile, blocks: BlocksFile
) -> None:
    with pytest.raises(FidelityError) as raised:
        check_stage(FidelityBoundary.STRUCTURE, lines, blocks)

    assert raised.value.detail == (
        "word change on page 0: ('Thomas',), a source_dash, is not the first word "
        "of an epigraph's source"
    )


def test_structure_epigraph_source_dropped_from_the_block_is_missing() -> None:
    blocks = _blocks_file((_epigraph("Thomas Hobbes,"),), word_changes=(_SOURCE_DASH,))

    with pytest.raises(FidelityError) as raised:
        check_stage(FidelityBoundary.STRUCTURE, _EPIGRAPH_LINES, blocks)

    assert raised.value.missing == frozendict({"1651": 1})
    assert raised.value.invented == frozendict()
    assert "'1651': input page 0, output none" in raised.value.detail


# A paragraph with a source: its words balance, only the record is wrong.
_SOURCED_PARAGRAPH = _blocks_file(
    (replace(_epigraph("Hobbes"), kind=BlockKind.PARAGRAPH),)
)
_SOURCED_PARAGRAPH_DETAIL = (
    "block b-p0000-002 is a paragraph and has the source 'Hobbes'; only an "
    "epigraph has a source"
)


def test_structure_block_that_is_not_an_epigraph_with_a_source_fails() -> None:
    lines = _lines_file((("The life of man.", "Hobbes"),))

    with pytest.raises(FidelityError) as raised:
        check_stage(FidelityBoundary.STRUCTURE, lines, _SOURCED_PARAGRAPH)

    assert raised.value.missing == frozendict()
    assert raised.value.invented == frozendict()
    assert raised.value.detail == _SOURCED_PARAGRAPH_DETAIL


def test_markdown_block_that_is_not_an_epigraph_with_a_source_fails() -> None:
    markdown = _markdown(
        tuple(
            (word, "b-p0000-002") for word in ("The", "life", "of", "man.", "Hobbes")
        ),
        note_count=0,
    )

    with pytest.raises(FidelityError) as raised:
        check_stage(FidelityBoundary.MARKDOWN, _SOURCED_PARAGRAPH, markdown)

    assert raised.value.missing == frozendict()
    assert raised.value.invented == frozendict()
    assert raised.value.detail == _SOURCED_PARAGRAPH_DETAIL


def _grouped_endnote(group: str | None) -> BlocksFile:
    return _blocks_file(
        (_block("b-p0000-001", (0,), (_span("Text."),)),),
        notes=(
            Note(
                id="n-p0001-001",
                kind=NoteKind.ENDNOTE,
                marker="1",
                blocks=(_block("b-p0001-001", (1,), (_span("See Gierke."),)),),
                origin=(Origin(1, _BOX),),
                referenced=False,
                group=group,
            ),
        ),
    )


def test_structure_note_group_counts_as_words_of_its_note() -> None:
    lines = _lines_file((("Text.",), ("Chapter 1.", "The Seed", "1 See Gierke.")))

    check_stage(
        FidelityBoundary.STRUCTURE, lines, _grouped_endnote("Chapter 1. The Seed")
    )


def test_structure_note_group_not_in_the_lines_is_invented() -> None:
    lines = _lines_file((("Text.",), ("1 See Gierke.",)))

    with pytest.raises(FidelityError) as raised:
        check_stage(FidelityBoundary.STRUCTURE, lines, _grouped_endnote("Chapter 1."))

    assert raised.value.missing == frozendict()
    assert raised.value.invented == frozendict({"Chapter": 1, "1.": 1})
    assert "'Chapter': input none, output note n-p0001-001 page 1" in (
        raised.value.detail
    )


def test_structure_punctuation_attached_with_its_word_change_passes() -> None:
    lines = _lines_file((("held in subjection ; and",),))
    change = WordChange(
        page_index=0,
        before=("subjection", ";"),
        after=("subjection;",),
        reason=ChangeReason.PUNCTUATION_ATTACHED,
    )
    blocks = _blocks_file(
        (_block("b-p0000-001", (0,), (_span("held in subjection; and"),)),),
        word_changes=(change,),
    )

    check_stage(FidelityBoundary.STRUCTURE, lines, blocks)


def test_structure_case_split_with_its_word_change_passes() -> None:
    lines = _lines_file((("valley of theAvre.",),))
    change = WordChange(
        page_index=0,
        before=("theAvre.",),
        after=("the", "Avre."),
        reason=ChangeReason.CASE_SPLIT,
    )
    blocks = _blocks_file(
        (_block("b-p0000-001", (0,), (_span("valley of the Avre."),)),),
        word_changes=(change,),
    )

    check_stage(FidelityBoundary.STRUCTURE, lines, blocks)


@pytest.mark.parametrize(
    ("lines", "block_text", "change"),
    [
        # The dash taken out with a letter.
        (
            ("—Hobbes",),
            "obbes",
            WordChange(
                page_index=0,
                before=("—Hobbes",),
                after=("obbes",),
                reason=ChangeReason.SOURCE_DASH,
            ),
        ),
        # No dash to take out.
        (
            ("Hobbes",),
            "Hobbes",
            WordChange(
                page_index=0,
                before=("Hobbes",),
                after=("Hobbes",),
                reason=ChangeReason.SOURCE_DASH,
            ),
        ),
        # Two words of the source glued: the first is more than a dash.
        (
            ("—Thomas Hobbes",),
            "ThomasHobbes",
            WordChange(
                page_index=0,
                before=("—Thomas", "Hobbes"),
                after=("ThomasHobbes",),
                reason=ChangeReason.SOURCE_DASH,
            ),
        ),
        # The first of two words is more than dashes: it is dropped.
        (
            ("—Thomas Hobbes",),
            "Hobbes",
            WordChange(
                page_index=0,
                before=("—Thomas", "Hobbes"),
                after=("Hobbes",),
                reason=ChangeReason.SOURCE_DASH,
            ),
        ),
        # An empty first word is no dash.
        (
            ("Hobbes",),
            "Hobbes",
            WordChange(
                page_index=0,
                before=("", "Hobbes"),
                after=("Hobbes",),
                reason=ChangeReason.SOURCE_DASH,
            ),
        ),
        # A word of dashes alone becomes no word.
        (
            ("—",),
            "",
            WordChange(
                page_index=0,
                before=("—",),
                after=("",),
                reason=ChangeReason.SOURCE_DASH,
            ),
        ),
        # A dash inside the word taken out too.
        (
            ("—1873—1881",),
            "18731881",
            WordChange(
                page_index=0,
                before=("—1873—1881",),
                after=("18731881",),
                reason=ChangeReason.SOURCE_DASH,
            ),
        ),
        # A second word that is not a sign.
        (
            ("in subjection and",),
            "in subjectionand",
            WordChange(
                page_index=0,
                before=("subjection", "and"),
                after=("subjectionand",),
                reason=ChangeReason.PUNCTUATION_ATTACHED,
            ),
        ),
        # The sign changed on the way.
        (
            ("in subjection ;",),
            "in subjection:",
            WordChange(
                page_index=0,
                before=("subjection", ";"),
                after=("subjection:",),
                reason=ChangeReason.PUNCTUATION_ATTACHED,
            ),
        ),
        # Three words joined.
        (
            ("in subjection ; ;",),
            "in subjection;;",
            WordChange(
                page_index=0,
                before=("subjection", ";", ";"),
                after=("subjection;;",),
                reason=ChangeReason.PUNCTUATION_ATTACHED,
            ),
        ),
        # Parts that do not make the word.
        (
            ("theAvre",),
            "the Avra",
            WordChange(
                page_index=0,
                before=("theAvre",),
                after=("the", "Avra"),
                reason=ChangeReason.CASE_SPLIT,
            ),
        ),
        # A second part that does not start with a capital.
        (
            ("theavre",),
            "the avre",
            WordChange(
                page_index=0,
                before=("theavre",),
                after=("the", "avre"),
                reason=ChangeReason.CASE_SPLIT,
            ),
        ),
        # A second word of before dropped.
        (
            ("theAvre x",),
            "the Avre",
            WordChange(
                page_index=0,
                before=("theAvre", "x"),
                after=("the", "Avre"),
                reason=ChangeReason.CASE_SPLIT,
            ),
        ),
        # An empty part.
        (
            ("the",),
            "the",
            WordChange(
                page_index=0,
                before=("the",),
                after=("the", ""),
                reason=ChangeReason.CASE_SPLIT,
            ),
        ),
        # Three parts.
        (
            ("ofTheAvre",),
            "of The Avre",
            WordChange(
                page_index=0,
                before=("ofTheAvre",),
                after=("of", "The", "Avre"),
                reason=ChangeReason.CASE_SPLIT,
            ),
        ),
    ],
    ids=[
        "source_dash-drops-a-letter",
        "source_dash-without-a-dash",
        "source_dash-glues-two-words",
        "source_dash-drops-the-first-word",
        "source_dash-empty-first-word",
        "source_dash-leaves-no-word",
        "source_dash-inside-the-word",
        "punctuation_attached-no-sign",
        "punctuation_attached-changed-sign",
        "punctuation_attached-three-words",
        "case_split-other-letters",
        "case_split-lower-case",
        "case_split-drops-a-word",
        "case_split-empty-part",
        "case_split-three-parts",
    ],
)
def test_structure_new_word_change_that_breaks_its_rules_fails(
    lines: tuple[str, ...], block_text: str, change: WordChange
) -> None:
    # Each change accounts for the words exactly, so only its rules can
    # make the check fail.
    blocks = _blocks_file(
        (_block("b-p0000-001", (0,), (_span(block_text),)),), word_changes=(change,)
    )

    with pytest.raises(FidelityError) as raised:
        check_stage(FidelityBoundary.STRUCTURE, _lines_file((lines,)), blocks)

    assert raised.value.missing == frozendict()
    assert raised.value.invented == frozendict()
    assert raised.value.detail == (
        f"word change on page 0: {change.before!r} to {change.after!r} is not a "
        f"{change.reason.value}"
    )


# The markdown boundary: the dash before the source is markdown's and taken
# out by the walk; the words of the source and of a note group are counted.

_EPIGRAPH_MARKDOWN = tuple(
    (word, "b-p0000-002")
    for word in ("The", "life", "of", "man.", "Thomas", "Hobbes,", "1651")
)


def test_markdown_epigraph_source_counts_as_words_of_its_block() -> None:
    blocks = _blocks_file((_epigraph("Thomas Hobbes, 1651"),))

    check_stage(
        FidelityBoundary.MARKDOWN, blocks, _markdown(_EPIGRAPH_MARKDOWN, note_count=0)
    )


def test_markdown_epigraph_source_left_out_of_the_markdown_is_missing() -> None:
    blocks = _blocks_file((_epigraph("Thomas Hobbes, 1651"),))
    markdown = _markdown(_EPIGRAPH_MARKDOWN[:4], note_count=0)

    with pytest.raises(FidelityError) as raised:
        check_stage(FidelityBoundary.MARKDOWN, blocks, markdown)

    assert raised.value.missing == frozendict({"Thomas": 1, "Hobbes,": 1, "1651": 1})
    assert raised.value.invented == frozendict()


def test_markdown_note_group_counts_as_words_of_the_note_after_it() -> None:
    markdown = _markdown(
        (
            ("Text.", "b-p0000-001"),
            ("Chapter", "n-p0001-001"),
            ("1.", "n-p0001-001"),
            ("1", "b-p0001-001"),
            ("See", "b-p0001-001"),
            ("Gierke.", "b-p0001-001"),
        ),
        note_count=0,
    )

    check_stage(FidelityBoundary.MARKDOWN, _grouped_endnote("Chapter 1."), markdown)


def test_markdown_note_group_left_out_of_the_markdown_is_missing() -> None:
    markdown = _markdown(
        (
            ("Text.", "b-p0000-001"),
            ("1", "b-p0001-001"),
            ("See", "b-p0001-001"),
            ("Gierke.", "b-p0001-001"),
        ),
        note_count=0,
    )

    with pytest.raises(FidelityError) as raised:
        check_stage(FidelityBoundary.MARKDOWN, _grouped_endnote("Chapter 1."), markdown)

    assert raised.value.missing == frozendict({"Chapter": 1, "1.": 1})


# The walk of an epigraph's and a note group's divs, on literal JSON as
# Pandoc 3.14 writes the Markdown of structure spec section 25.


def _classed_div(div_id: str, class_name: str, blocks: str) -> str:
    return f'{{"t":"Div","c":[["{div_id}",["{class_name}"],[]],[{blocks}]]}}'


def _para(*words: str) -> str:
    inlines = f",{_SPACE},".join(_str(word) for word in words)
    return f'{{"t":"Para","c":[{inlines}]}}'


# The em dash and no-break space markdown writes before a source, one Str
# with the source's first word.
_SOURCE_START = "— Thomas"


def test_walk_takes_the_dash_out_of_an_epigraph_source_and_counts_it_to_the_epigraph() -> (
    None
):
    source = _classed_div("", "epigraph-source", _para(_SOURCE_START, "Hobbes"))
    epigraph = _classed_div(
        "b-p0000-002", "epigraph", f"{_para('The', 'life.')},{source}"
    )

    markdown = _words_of_pandoc_json(_pandoc_document(epigraph))

    assert markdown.words == tuple(
        MarkdownWord(word, "b-p0000-002")
        for word in ("The", "life.", "Thomas", "Hobbes")
    )


@pytest.mark.parametrize(
    "first_word",
    ["Thomas", "- Thomas", "—— Thomas"],
    ids=["no-dash", "hyphen", "two-dashes"],
)
def test_walk_of_an_epigraph_source_without_the_dash_markdown_writes_raises(
    first_word: str,
) -> None:
    source = _classed_div("", "epigraph-source", _para(first_word, "Hobbes"))
    epigraph = _classed_div("b-p0000-002", "epigraph", f"{_para('The')},{source}")

    with pytest.raises(
        ExternalProgramError, match="epigraph-source div in block b-p0000-002"
    ):
        _words_of_pandoc_json(_pandoc_document(epigraph))


@pytest.mark.parametrize(
    "inner_div",
    [
        _classed_div("", "quote", _para("Hobbes")),
        _div("b-p0000-003", _para("Hobbes")),
    ],
    ids=["other-class", "block-div"],
)
def test_walk_of_another_div_inside_an_epigraph_raises(inner_div: str) -> None:
    epigraph = _classed_div("b-p0000-002", "epigraph", f"{_para('The')},{inner_div}")

    with pytest.raises(ExternalProgramError, match="Div element in block b-p0000-002"):
        _words_of_pandoc_json(_pandoc_document(epigraph))


def test_walk_of_an_epigraph_source_holding_a_note_reference_raises() -> None:
    link = _link('["epub:type","noteref"]', _str("1"))
    paragraph = f'{{"t":"Para","c":[{_str(_SOURCE_START)},{link}]}}'
    source = _classed_div("", "epigraph-source", paragraph)
    epigraph = _classed_div("b-p0000-002", "epigraph", f"{_para('The')},{source}")

    with pytest.raises(
        ExternalProgramError,
        match="epigraph-source div in block b-p0000-002 holds a note or a note "
        "reference",
    ):
        _words_of_pandoc_json(_pandoc_document(epigraph))


def test_walk_of_an_epigraph_source_outside_an_epigraph_raises() -> None:
    source = _classed_div("", "epigraph-source", _para(_SOURCE_START))
    paragraph = _div("b-p0000-002", f"{_para('The')},{source}")

    with pytest.raises(ExternalProgramError, match="Div element in block b-p0000-002"):
        _words_of_pandoc_json(_pandoc_document(paragraph))


def test_walk_gives_note_group_words_to_the_endnote_after_it() -> None:
    group = _classed_div("", "note-group", _para("Chapter", "1."))
    endnote = _classed_div(
        "n-p0001-001", "endnote", _div("b-p0001-001", _para("1", "See."))
    )
    endnotes = _classed_div("", "endnotes", f"{group},{endnote}")

    markdown = _words_of_pandoc_json(_pandoc_document(endnotes))

    assert markdown.words == (
        MarkdownWord("Chapter", "n-p0001-001"),
        MarkdownWord("1.", "n-p0001-001"),
        MarkdownWord("1", "b-p0001-001"),
        MarkdownWord("See.", "b-p0001-001"),
    )


@pytest.mark.parametrize(
    "after_group",
    ["", f",{_div('b-p0001-001', _para('See.'))}"],
    ids=["last", "before-a-block"],
)
def test_walk_of_a_note_group_not_before_an_endnote_raises(after_group: str) -> None:
    group = _classed_div("", "note-group", _para("Chapter", "1."))
    endnotes = _classed_div("", "endnotes", f"{group}{after_group}")

    with pytest.raises(ExternalProgramError, match="note-group div"):
        _words_of_pandoc_json(_pandoc_document(endnotes))


@pytest.mark.pandoc
def test_read_markdown_reads_an_epigraph_source_and_a_note_group() -> None:
    markdown = read_markdown(
        "::: {#b-p0000-002 .epigraph}\n"
        "The life.\n\n"
        "::: epigraph-source\n"
        "— Thomas Hobbes\n"
        ":::\n"
        ":::\n\n"
        "::::: endnotes\n"
        "::: note-group\n"
        "Chapter 1.\n"
        ":::\n\n"
        ":::: {#n-p0001-001 .endnote}\n"
        "::: {#b-p0001-001}\n"
        "1 See.\n"
        ":::\n"
        "::::\n"
        ":::::\n"
    )

    assert markdown.words == (
        MarkdownWord("The", "b-p0000-002"),
        MarkdownWord("life.", "b-p0000-002"),
        MarkdownWord("Thomas", "b-p0000-002"),
        MarkdownWord("Hobbes", "b-p0000-002"),
        MarkdownWord("Chapter", "n-p0001-001"),
        MarkdownWord("1.", "n-p0001-001"),
        MarkdownWord("1", "b-p0001-001"),
        MarkdownWord("See.", "b-p0001-001"),
    )


# The structure boundary of the plan lists-figures (structure spec section
# 31, its last paragraph): a block's label counts whatever its kind, a
# contents entry's page number too, a list item's dash split off its word
# is verified, and the removals of leader dots and of the words inside an
# in-page figure are read as any removal.


def _list_item(label: str, text: str) -> Block:
    return replace(
        _block("b-p0000-001", (0,), (_span(text),)),
        kind=BlockKind.LIST_ITEM,
        label=label,
    )


def _contents_entry(label: str | None, title: str, page_number: str | None) -> Block:
    return replace(
        _block("b-p0000-001", (0,), (_span(title),)),
        kind=BlockKind.CONTENTS_ENTRY,
        level=1,
        label=label,
        page_number=page_number,
    )


def _removal(text: str, reason: RemovalReason) -> Removal:
    return Removal(page_index=0, box=_BOX, text=text, reason=reason)


@pytest.mark.parametrize("dash", ["\u2014", "\u2013"], ids=["em-dash", "en-dash"])
def test_structure_list_marker_split_off_its_word_with_the_dash_as_label_passes(
    dash: str,
) -> None:
    lines = _lines_file(((f"{dash}The founder, who returns",),))
    change = WordChange(
        page_index=0,
        before=(f"{dash}The",),
        after=(dash, "The"),
        reason=ChangeReason.LIST_MARKER,
    )
    blocks = _blocks_file(
        (_list_item(dash, "The founder, who returns"),), word_changes=(change,)
    )

    check_stage(FidelityBoundary.STRUCTURE, lines, blocks)


@pytest.mark.parametrize(
    ("line", "label", "text", "after"),
    [
        # A marker that is not a dash.
        ("1.The King", "1.", "The King", ("1.", "The")),
        # A hyphen, which is no list dash.
        ("-The King", "-", "The King", ("-", "The")),
        # The dash split off with a letter of the word.
        ("—The King", "—T", "he King", ("—T", "he")),
        # Nothing left after the dash.
        ("— King", "—", "King", ("—", "")),
        # The word after the dash is not the word the dash was split off.
        ("—The King", "—", "Cat King", ("—", "Cat")),
        ("–The King", "–", "Cat King", ("–", "Cat")),
    ],
    ids=[
        "number",
        "hyphen",
        "dash-with-a-letter",
        "empty-word",
        "em-dash-another-word",
        "en-dash-another-word",
    ],
)
def test_structure_list_marker_not_a_dash_split_off_its_own_word_fails(
    line: str, label: str, text: str, after: tuple[str, ...]
) -> None:
    # The change accounts for the words exactly, so only its rule can make
    # the check fail.
    before = (line.split()[0],)
    change = WordChange(
        page_index=0, before=before, after=after, reason=ChangeReason.LIST_MARKER
    )
    lines = _lines_file(((line,),))
    blocks = _blocks_file((_list_item(label, text),), word_changes=(change,))

    with pytest.raises(FidelityError) as raised:
        check_stage(FidelityBoundary.STRUCTURE, lines, blocks)

    assert raised.value.detail == (
        f"word change on page 0: {change.before!r} to {change.after!r} is not a "
        "list_marker"
    )


@pytest.mark.parametrize(
    ("block", "lines"),
    [
        (_list_item("1.", "The King"), ("1. The King",)),
        (
            _contents_entry("2.", "Carver's New Engineers", "23"),
            ("2. Carver's New Engineers 23",),
        ),
    ],
    ids=["list_item", "contents_entry"],
)
def test_structure_any_label_counts_as_words_of_its_block(
    block: Block, lines: tuple[str, ...]
) -> None:
    check_stage(
        FidelityBoundary.STRUCTURE, _lines_file((lines,)), _blocks_file((block,))
    )


def test_structure_any_label_dropped_from_a_list_item_is_missing() -> None:
    lines = _lines_file((("1. The King",),))
    blocks = _blocks_file(
        (
            replace(
                _block("b-p0000-001", (0,), (_span("The King"),)),
                kind=BlockKind.PARAGRAPH,
            ),
        )
    )

    with pytest.raises(FidelityError) as raised:
        check_stage(FidelityBoundary.STRUCTURE, lines, blocks)

    assert raised.value.missing == frozendict({"1.": 1})


def test_structure_page_number_of_a_contents_entry_not_in_the_lines_is_invented() -> (
    None
):
    lines = _lines_file((("Introduction",),))
    blocks = _blocks_file((_contents_entry(None, "Introduction", "pp. 9 — 26."),))

    with pytest.raises(FidelityError) as raised:
        check_stage(FidelityBoundary.STRUCTURE, lines, blocks)

    assert raised.value.missing == frozendict()
    assert raised.value.invented == frozendict({"pp.": 1, "9": 1, "—": 1, "26.": 1})


def test_structure_page_number_dropped_from_a_contents_entry_is_missing() -> None:
    lines = _lines_file((("Introduction 1",),))
    blocks = _blocks_file((_contents_entry(None, "Introduction", None),))

    with pytest.raises(FidelityError) as raised:
        check_stage(FidelityBoundary.STRUCTURE, lines, blocks)

    assert raised.value.missing == frozendict({"1": 1})


def test_structure_leader_dots_removed_between_title_and_page_number_pass() -> None:
    lines = _lines_file((("PREFACE . . . . v",),))
    blocks = _blocks_file(
        (_contents_entry(None, "PREFACE", "v"),),
        removals=(_removal(". . . .", RemovalReason.LEADER_DOTS),),
    )

    check_stage(FidelityBoundary.STRUCTURE, lines, blocks)


def test_structure_leader_dots_dropped_without_a_removal_are_missing() -> None:
    lines = _lines_file((("PREFACE . . v",),))
    blocks = _blocks_file((_contents_entry(None, "PREFACE", "v"),))

    with pytest.raises(FidelityError) as raised:
        check_stage(FidelityBoundary.STRUCTURE, lines, blocks)

    assert raised.value.missing == frozendict({".": 2})


def test_structure_figure_text_removed_with_a_record_passes_and_without_is_missing() -> (
    None
):
    lines = _lines_file((("Kadesh", "Orontes", "country grows lower"),))
    figure = replace(
        _block("b-p0000-002", (0,), ()), kind=BlockKind.FIGURE, figure="images/f.png"
    )
    body = _block("b-p0000-001", (0,), (_span("country grows lower"),))
    removals = (
        _removal("Kadesh", RemovalReason.FIGURE_TEXT),
        _removal("Orontes", RemovalReason.FIGURE_TEXT),
    )

    check_stage(
        FidelityBoundary.STRUCTURE,
        lines,
        _blocks_file((body, figure), removals=removals),
    )
    with pytest.raises(FidelityError) as raised:
        check_stage(
            FidelityBoundary.STRUCTURE,
            lines,
            _blocks_file((body, figure), removals=removals[:1]),
        )
    assert raised.value.missing == frozendict({"Orontes": 1})
