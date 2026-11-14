"""Tests of galley.fidelity (spec section 5, architecture section 13).

The values are built by hand: the stages of the walking skeleton make no
removal, word change or note, and the check must handle them already.
"""

from dataclasses import replace
from pathlib import Path

import pytest

from galley.errors import ExternalProgramError, FidelityBoundary, FidelityError
from galley.fidelity import MarkdownWord, MarkdownWords, check_stage, read_markdown
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
    words: tuple[tuple[str, str | None], ...], note_count: int
) -> MarkdownWords:
    return MarkdownWords(
        words=tuple(MarkdownWord(text, block_id) for text, block_id in words),
        note_count=note_count,
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
    assert "marker '1'" in raised.value.detail


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
        "note references in blocks.json: 2; notes in the Markdown: 1"
        in raised.value.detail
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


@pytest.mark.thread_unsafe(reason="changes PATH")
def test_read_markdown_without_pandoc_raises(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("PATH", str(tmp_path))

    with pytest.raises(ExternalProgramError, match="pandoc"):
        read_markdown("Text.\n")
