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
) -> MarkdownWords:
    return MarkdownWords(
        words=tuple(MarkdownWord(text, block_id) for text, block_id in words),
        note_count=note_count,
        note_link_count=note_link_count,
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
        "white space, '&' or dash, and a letter only beside a round bracket)"
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
        _ENDNOTE_MARKDOWN + _ENDNOTE_LINK_WORD, note_count=0, note_link_count=1
    )

    check_stage(FidelityBoundary.MARKDOWN, blocks, markdown)


def test_markdown_endnote_link_without_the_reference_text_fails() -> None:
    blocks = _endnote_blocks(referenced=True)
    markdown = _markdown(_ENDNOTE_MARKDOWN, note_count=0, note_link_count=1)

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
    )

    with pytest.raises(FidelityError) as raised:
        check_stage(FidelityBoundary.MARKDOWN, blocks, markdown)

    assert raised.value.missing == frozendict()
    assert raised.value.invented == frozendict({"and": 1})


def test_markdown_endnote_counts_differing_with_footnote_counts_agreeing_fail() -> None:
    blocks = _endnote_blocks(referenced=True)
    markdown = _markdown(
        _ENDNOTE_MARKDOWN + _ENDNOTE_LINK_WORD, note_count=0, note_link_count=0
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
        _ENDNOTE_MARKDOWN + _ENDNOTE_LINK_WORD, note_count=1, note_link_count=0
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
