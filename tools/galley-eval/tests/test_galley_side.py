"""Tests of galley_eval.galley_side: the tokens of galley's four stage
outputs (spec section 5, "galley's tokens")."""

import dataclasses
from collections.abc import Callable
from pathlib import Path

import pytest

from galley.book_folder import BookFolder
from galley.config import BookConfig, Language
from galley.fidelity import MarkdownWord, MarkdownWords, read_markdown
from galley.markdown import render_markdown
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
    Reread,
    RereadKind,
    Span,
    TextSource,
    Word,
    WordChange,
    WordsFile,
    read_blocks,
    write_blocks,
    write_lines,
    write_words,
)
from galley_eval.align import GalleyStream, GalleyToken
from galley_eval.books import EvaluationBook
from galley_eval.errors import GalleyFilesError
from galley_eval.evaluate import evaluate
from galley_eval.galley_side import (
    GalleyNoteReference,
    blocks_tokens,
    endnote_pages,
    galley_blocks,
    lines_tokens,
    markdown_tokens,
    note_references,
    read_galley_side,
    words_tokens,
)

_SHA = "0" * 64


def _word(text: str, top: float) -> Word:
    return Word(text, Box(0.0, top, 10.0, top + 10.0), None)


def _line(text: str, top: float) -> Line:
    return Line(
        Box(0.0, top, 100.0, top + 10.0),
        tuple(_word(word, top) for word in text.split()),
    )


def _page_lines(index: int, *texts: str) -> PageLayout:
    lines = tuple(_line(text, 10.0 * position) for position, text in enumerate(texts))
    return PageLayout(index, (Region(Box(0.0, 0.0, 100.0, 100.0), lines),), ())


# Two pages, each with a running head on its first line and a page
# number on its last; "repli-" ends page 0 and "cate" starts the text of
# page 1.
_LINES = LinesFile(
    source_pdf_sha256=_SHA,
    pages=(
        _page_lines(0, "THE HEAD", "We must repli-", "7"),
        _page_lines(1, "OTHER HEAD", "cate it here.", "8"),
    ),
    rereads=(),
)


def _words_file(lines: LinesFile) -> WordsFile:
    """The words of `lines`, page by page, in reverse order within the
    page, as a text layer may give them."""
    return WordsFile(
        source_pdf_sha256=_SHA,
        pages=tuple(
            PageWords(
                index=page.index,
                text_source=TextSource.TEXT_LAYER,
                words=tuple(
                    reversed(
                        tuple(
                            word
                            for region in page.regions
                            for line in region.lines
                            for word in line.words
                        )
                    )
                ),
                figures=(),
            )
            for page in lines.pages
        ),
        removals=(),
    )


def _span(text: str, note_ref: str | None = None) -> Span:
    return Span(text, Emphasis.NONE, note_ref)


def _origin(*pages: int) -> tuple[Origin, ...]:
    return tuple(Origin(page, Box(0.0, 0.0, 100.0, 100.0)) for page in pages)


def _block(
    block_id: str,
    kind: BlockKind,
    spans: tuple[Span, ...],
    origin: tuple[Origin, ...],
) -> Block:
    return Block(
        id=block_id,
        kind=kind,
        level=None,
        label=None,
        spans=spans,
        figure=None,
        origin=origin,
    )


# The text over both pages as one paragraph, "replicate" joined by
# structure, with a note reference after "it" and its note; and a margin
# note on page 1.
_BLOCKS = BlocksFile(
    source_pdf_sha256=_SHA,
    blocks=(
        _block(
            "b-p0000-001",
            BlockKind.PARAGRAPH,
            (_span("We must replicate it"), _span("1", "n-p0001-001"), _span(" here.")),
            _origin(0, 1),
        ),
        _block(
            "b-p0001-001",
            BlockKind.MARGIN_NOTE,
            (_span("OTHER HEAD"),),
            _origin(1),
        ),
    ),
    notes=(
        Note(
            id="n-p0001-001",
            kind=NoteKind.FOOTNOTE,
            marker="1",
            blocks=(
                _block(
                    "b-p0001-002",
                    BlockKind.PARAGRAPH,
                    (_span("cate"),),
                    _origin(1),
                ),
            ),
            origin=_origin(1),
            referenced=True,
        ),
    ),
    removals=(),
    word_changes=(
        WordChange(
            page_index=0,
            before=("repli-", "cate"),
            after=("replicate",),
            reason=ChangeReason.HYPHEN_JOIN,
        ),
    ),
    page_numbers=(),
)


def _summary(tokens: tuple[GalleyToken, ...]) -> tuple[tuple[str, int, bool], ...]:
    return tuple((token.text, token.page_index, token.edge_of_page) for token in tokens)


def test_lines_tokens_flag_the_first_and_last_line_of_each_page() -> None:
    assert _summary(lines_tokens(_LINES)) == (
        ("THE", 0, True),
        ("HEAD", 0, True),
        ("We", 0, False),
        ("must", 0, False),
        ("repli-", 0, False),
        ("7", 0, True),
        ("OTHER", 1, True),
        ("HEAD", 1, True),
        ("cate", 1, False),
        ("it", 1, False),
        ("here.", 1, False),
        ("8", 1, True),
    )


def test_words_tokens_keep_the_file_order_and_flag_words_on_an_edge_line() -> None:
    tokens = words_tokens(_words_file(_LINES), _LINES)
    assert _summary(tokens)[:6] == (
        ("7", 0, True),
        ("repli-", 0, False),
        ("must", 0, False),
        ("We", 0, False),
        ("HEAD", 0, True),
        ("THE", 0, True),
    )
    assert {token.stream for token in tokens} == {GalleyStream.BODY}
    assert {token.block_id for token in tokens} == {None}


def test_a_word_with_the_text_of_an_edge_word_elsewhere_is_not_flagged() -> None:
    # "HEAD" is on the first line, and again, in another box, in the text.
    lines = LinesFile(
        source_pdf_sha256=_SHA,
        pages=(_page_lines(0, "HEAD", "the HEAD of it", "9"),),
        rereads=(),
    )
    flagged = tuple(
        token.text
        for token in words_tokens(_words_file(lines), lines)
        if token.edge_of_page
    )
    assert sorted(flagged) == ["9", "HEAD"]


def test_a_word_with_a_space_is_split_into_two_tokens() -> None:
    lines = LinesFile(
        source_pdf_sha256=_SHA,
        pages=(
            PageLayout(
                3,
                (
                    Region(
                        Box(0.0, 0.0, 100.0, 100.0),
                        (Line(Box(0.0, 0.0, 9.0, 9.0), (_word("10\xa0000", 0.0),)),),
                    ),
                ),
                (),
            ),
        ),
        rereads=(),
    )
    assert tuple(token.text for token in lines_tokens(lines)) == ("10", "000")
    assert tuple(token.text for token in words_tokens(_words_file(lines), lines)) == (
        "10",
        "000",
    )


def test_blocks_tokens_of_a_block_over_two_pages_have_both_pages() -> None:
    tokens = blocks_tokens(_BLOCKS, _LINES)
    assert tuple(
        (token.text, token.page_index, token.stream, token.block_id) for token in tokens
    ) == (
        # "replicate", joined from "repli-" (page 0) and "cate", has page 0.
        ("We", 0, GalleyStream.BODY, "b-p0000-001"),
        ("must", 0, GalleyStream.BODY, "b-p0000-001"),
        ("replicate", 0, GalleyStream.BODY, "b-p0000-001"),
        # The note reference "1" between "it" and "here." is not a token.
        ("it", 1, GalleyStream.BODY, "b-p0000-001"),
        ("here.", 1, GalleyStream.BODY, "b-p0000-001"),
        ("OTHER", 1, GalleyStream.MARGIN_NOTES, "b-p0001-001"),
        ("HEAD", 1, GalleyStream.MARGIN_NOTES, "b-p0001-001"),
        # The note's marker "1" is not a token either.
        ("cate", 1, GalleyStream.NOTES, "b-p0001-002"),
    )
    assert not any(token.edge_of_page for token in tokens)


def test_note_reference_is_placed_after_the_tokens_before_it() -> None:
    assert note_references(_BLOCKS) == (
        GalleyNoteReference(
            note_id="n-p0001-001", block_id="b-p0000-001", tokens_before=4
        ),
    )


def test_block_with_no_origin_is_an_error() -> None:
    block = _block("b-p0000-009", BlockKind.PARAGRAPH, (_span("word"),), ())
    blocks = BlocksFile(
        source_pdf_sha256=_SHA,
        blocks=(block,),
        notes=(),
        removals=(),
        word_changes=(),
        page_numbers=(),
    )
    with pytest.raises(GalleyFilesError, match="b-p0000-009"):
        blocks_tokens(blocks, _LINES)


def test_block_on_a_page_lines_lacks_is_an_error() -> None:
    block = _block("b-p0005-001", BlockKind.PARAGRAPH, (_span("word"),), _origin(5))
    blocks = BlocksFile(
        source_pdf_sha256=_SHA,
        blocks=(block,),
        notes=(),
        removals=(),
        word_changes=(),
        page_numbers=(),
    )
    with pytest.raises(GalleyFilesError, match="page 5"):
        blocks_tokens(blocks, _LINES)


def _markdown(*words: tuple[str, str | None]) -> MarkdownWords:
    return MarkdownWords(
        words=tuple(MarkdownWord(text, block_id) for text, block_id in words),
        note_count=0,
        note_link_count=0,
        list_item_count=0,
        shown_markers=(),
        contents_links=(),
    )


def test_markdown_tokens_take_stream_and_page_from_their_block() -> None:
    markdown = _markdown(
        ("We", "b-p0000-001"),
        ("must", "b-p0000-001"),
        ("replicate", "b-p0000-001"),
        ("cate", "b-p0001-002"),
        ("it", "b-p0000-001"),
        ("here", "b-p0000-001"),
        ("OTHER", "b-p0001-001"),
    )
    tokens = markdown_tokens(markdown, _BLOCKS, blocks_tokens(_BLOCKS, _LINES))
    assert tuple(
        (token.text, token.page_index, token.stream, token.block_id) for token in tokens
    ) == (
        ("We", 0, GalleyStream.BODY, "b-p0000-001"),
        ("must", 0, GalleyStream.BODY, "b-p0000-001"),
        ("replicate", 0, GalleyStream.BODY, "b-p0000-001"),
        ("it", 1, GalleyStream.BODY, "b-p0000-001"),
        # "here" against "here." of blocks is a replaced pair: page 1.
        ("here", 1, GalleyStream.BODY, "b-p0000-001"),
        ("OTHER", 1, GalleyStream.MARGIN_NOTES, "b-p0001-001"),
        # The notes come after, in blocks.json's order (spec section 5).
        ("cate", 1, GalleyStream.NOTES, "b-p0001-002"),
    )


@pytest.mark.parametrize(
    ("block_id", "message"),
    [(None, "in no block"), ("b-p0009-001", "b-p0009-001")],
)
def test_markdown_word_outside_a_known_block_is_an_error(
    block_id: str | None, message: str
) -> None:
    with pytest.raises(GalleyFilesError, match=message):
        markdown_tokens(
            _markdown(("word", block_id)), _BLOCKS, blocks_tokens(_BLOCKS, _LINES)
        )


@pytest.mark.pandoc
def test_read_galley_side_reads_the_four_files_of_a_folder(tmp_path: Path) -> None:
    folder = BookFolder(tmp_path)
    write_words(folder.words_json, _words_file(_LINES))
    write_lines(folder.lines_json, _LINES)
    write_blocks(folder.blocks_json, _BLOCKS)
    folder.book_md.write_text(
        "::: {#b-p0000-001}\nWe must replicate it here.\n:::\n", encoding="utf-8"
    )
    side = read_galley_side(folder)
    assert len(side.words) == len(side.lines) == 12
    assert len(side.blocks) == 8
    assert tuple((token.text, token.page_index) for token in side.markdown) == (
        ("We", 0),
        ("must", 0),
        ("replicate", 0),
        ("it", 1),
        ("here.", 1),
    )
    assert side.galley_blocks["b-p0001-002"].note_id == "n-p0001-001"


@pytest.mark.pandoc
def test_read_galley_side_keeps_the_rereads_of_lines_json(tmp_path: Path) -> None:
    # A region of page 0 read again and not kept: it changes no word.
    reread = Reread(
        page_index=0,
        kind=RereadKind.FOOTNOTE_BAND,
        box=Box(0.0, 20.0, 100.0, 30.0),
        layer_words=(_word("7", 20.0),),
        ocr_words=(Word("?", Box(0.0, 20.0, 5.0, 30.0), 12.0),),
        layer_score=0,
        ocr_score=-1,
        kept=False,
    )
    lines = dataclasses.replace(_LINES, rereads=(reread,))
    folder = BookFolder(tmp_path)
    write_words(folder.words_json, _words_file(lines))
    write_lines(folder.lines_json, lines)
    write_blocks(folder.blocks_json, _BLOCKS)
    folder.book_md.write_text(
        "::: {#b-p0000-001}\nWe must replicate it here.\n:::\n", encoding="utf-8"
    )
    assert read_galley_side(folder).rereads == (reread,)


# The page edge skips lines of marks


def test_a_line_of_marks_above_the_running_head_does_not_take_its_flag() -> None:
    # Haskins page index 28: a "!" from a speck above "NORMANDY IN HISTORY 13".
    lines = LinesFile(
        source_pdf_sha256=_SHA,
        pages=(
            _page_lines(0, "!", "NORMANDY IN HISTORY 13", "the text", "more text", ";"),
        ),
        rereads=(),
    )
    flagged = tuple(token.text for token in lines_tokens(lines) if token.edge_of_page)
    assert flagged == ("!", "NORMANDY", "IN", "HISTORY", "13", "more", "text", ";")
    words_flagged = tuple(
        token.text
        for token in words_tokens(_words_file(lines), lines)
        if token.edge_of_page
    )
    assert sorted(words_flagged) == sorted(flagged)


def test_a_page_of_marks_only_is_all_on_the_edge() -> None:
    lines = LinesFile(
        source_pdf_sha256=_SHA, pages=(_page_lines(0, "!", "* ;"),), rereads=()
    )
    assert all(token.edge_of_page for token in lines_tokens(lines))


# Note markers and note references


def _note_blocks(*, referenced: bool) -> BlocksFile:
    return BlocksFile(
        source_pdf_sha256=_SHA,
        blocks=(),
        notes=(
            Note(
                id="n-p0001-001",
                kind=NoteKind.FOOTNOTE,
                marker="*",
                blocks=(
                    _block(
                        "b-p0001-002",
                        BlockKind.PARAGRAPH,
                        (_span("cate"), _span("2", "n-p0001-002"), _span("it")),
                        _origin(1),
                    ),
                ),
                origin=_origin(1),
                referenced=referenced,
            ),
        ),
        removals=(),
        word_changes=(),
        page_numbers=(),
    )


def test_marker_of_an_unreferenced_note_is_its_first_token() -> None:
    tokens = blocks_tokens(_note_blocks(referenced=False), _LINES)
    assert tuple(token.text for token in tokens) == ("*", "cate", "it")
    assert tokens[0].block_id == "b-p0001-002"
    assert tokens[0].stream is GalleyStream.NOTES
    assert note_references(_note_blocks(referenced=False)) == (
        GalleyNoteReference(
            note_id="n-p0001-002", block_id="b-p0001-002", tokens_before=2
        ),
    )


def test_marker_of_a_referenced_note_is_not_a_token() -> None:
    tokens = blocks_tokens(_note_blocks(referenced=True), _LINES)
    assert tuple(token.text for token in tokens) == ("cate", "it")


def test_note_reference_span_separates_the_words_around_it() -> None:
    # "cate" + reference + "it" would be "cateit" if the span gave no space.
    blocks = _note_blocks(referenced=True)
    assert "cateit" not in {token.text for token in blocks_tokens(blocks, _LINES)}


def test_token_with_no_word_in_lines_takes_the_page_of_the_word_before() -> None:
    lines = LinesFile(
        source_pdf_sha256=_SHA,
        pages=(_page_lines(0, "alpha beta"), _page_lines(1, "gamma delta")),
        rereads=(),
    )
    blocks = BlocksFile(
        source_pdf_sha256=_SHA,
        blocks=(
            _block(
                "b-p0000-001",
                BlockKind.PARAGRAPH,
                (_span("inserted alpha beta between gamma delta"),),
                _origin(0, 1),
            ),
        ),
        notes=(),
        removals=(),
        word_changes=(),
        page_numbers=(),
    )
    pages = tuple(token.page_index for token in blocks_tokens(blocks, lines))
    # "between" is in no line: the page of "beta" before it, not of "gamma";
    # "inserted" has no word before it, and takes the page of the one after.
    assert pages == (0, 0, 0, 0, 1, 1)


def test_folder_without_book_md_is_an_error_naming_the_stage(tmp_path: Path) -> None:
    folder = BookFolder(tmp_path)
    write_words(folder.words_json, _words_file(_LINES))
    write_lines(folder.lines_json, _LINES)
    write_blocks(folder.blocks_json, _BLOCKS)
    with pytest.raises(GalleyFilesError, match=r"book\.md(.|\n)*galley2epub markdown"):
        read_galley_side(folder)


def test_evaluate_of_a_folder_without_book_md_is_a_book_error(
    tmp_path: Path, small_book: Callable[[str], EvaluationBook]
) -> None:
    folder = BookFolder(tmp_path)
    write_words(folder.words_json, _words_file(_LINES))
    write_lines(folder.lines_json, _LINES)
    write_blocks(folder.blocks_json, _BLOCKS)
    with pytest.raises(GalleyFilesError, match="galley2epub markdown"):
        evaluate(
            small_book("small"),
            folder,
            tmp_path / "never-read.html",
            word_list=frozenset(),
        )


# blocks.json version 2 (architecture section 8; spec section 5): a
# heading's label, verse, chapter summaries and endnotes, on hand-made
# files, since galley's structure does not make them all yet.


def _hand_made(tmp_path: Path, blocks: BlocksFile) -> BlocksFile:
    """`blocks` written as blocks.json and read back, as galley-eval reads
    galley's file."""
    path = tmp_path / "blocks.json"
    write_blocks(path, blocks)
    return read_blocks(path)


def _blocks_file(blocks: tuple[Block, ...], notes: tuple[Note, ...] = ()) -> BlocksFile:
    return BlocksFile(
        source_pdf_sha256=_SHA,
        blocks=blocks,
        notes=notes,
        removals=(),
        word_changes=(),
        page_numbers=(),
    )


def _heading(block_id: str, label: str | None, title: str) -> Block:
    return Block(
        id=block_id,
        kind=BlockKind.HEADING,
        level=1,
        label=label,
        spans=(_span(title),),
        figure=None,
        origin=_origin(0),
    )


_HEADING_LINES = LinesFile(
    source_pdf_sha256=_SHA,
    pages=(_page_lines(0, "CHAPTER III.", "THE EARLY YEARS", "Very few epochs"),),
    rereads=(),
)


def test_heading_label_is_the_first_tokens_of_its_block_at_blocks(
    tmp_path: Path,
) -> None:
    blocks = _hand_made(
        tmp_path,
        _blocks_file((_heading("b-p0000-001", "CHAPTER III.", "THE EARLY YEARS"),)),
    )
    tokens = blocks_tokens(blocks, _HEADING_LINES)
    assert [(token.text, token.in_label) for token in tokens] == [
        ("CHAPTER", True),
        ("III.", True),
        ("THE", False),
        ("EARLY", False),
        ("YEARS", False),
    ]
    assert galley_blocks(blocks)["b-p0000-001"].has_label


def test_heading_label_words_of_book_md_are_marked_as_label(tmp_path: Path) -> None:
    blocks = _hand_made(
        tmp_path,
        _blocks_file((_heading("b-p0000-001", "CHAPTER III.", "THE EARLY YEARS"),)),
    )
    markdown = _markdown(
        *(
            (word, "b-p0000-001")
            for word in ["CHAPTER", "III.", "THE", "EARLY", "YEARS"]
        )
    )
    tokens = markdown_tokens(markdown, blocks, blocks_tokens(blocks, _HEADING_LINES))
    assert [token.in_label for token in tokens] == [True, True, False, False, False]


def test_heading_without_label_has_no_label_token(tmp_path: Path) -> None:
    blocks = _hand_made(
        tmp_path, _blocks_file((_heading("b-p0000-001", None, "THE EARLY YEARS"),))
    )
    tokens = blocks_tokens(blocks, _HEADING_LINES)
    assert [token.text for token in tokens] == ["THE", "EARLY", "YEARS"]
    assert not any(token.in_label for token in tokens)


def test_verse_block_line_feeds_separate_its_words(tmp_path: Path) -> None:
    lines = LinesFile(
        source_pdf_sha256=_SHA,
        pages=(_page_lines(0, "O Roma nobilis,", "orbis et domina"),),
        rereads=(),
    )
    blocks = _hand_made(
        tmp_path,
        _blocks_file(
            (
                _block(
                    "b-p0000-001",
                    BlockKind.VERSE,
                    (_span("O Roma nobilis,\norbis et domina"),),
                    _origin(0),
                ),
            )
        ),
    )
    tokens = blocks_tokens(blocks, lines)
    assert [token.text for token in tokens] == [
        "O",
        "Roma",
        "nobilis,",
        "orbis",
        "et",
        "domina",
    ]
    assert galley_blocks(blocks)["b-p0000-001"].kind is BlockKind.VERSE


def test_chapter_summary_block_is_a_body_block_of_its_kind(tmp_path: Path) -> None:
    lines = LinesFile(
        source_pdf_sha256=_SHA,
        pages=(_page_lines(0, "Terms of accession \u2014 His character"),),
        rereads=(),
    )
    blocks = _hand_made(
        tmp_path,
        _blocks_file(
            (
                _block(
                    "b-p0000-001",
                    BlockKind.CHAPTER_SUMMARY,
                    (_span("Terms of accession \u2014 His character"),),
                    _origin(0),
                ),
            )
        ),
    )
    (token, *_) = blocks_tokens(blocks, lines)
    assert token.stream is GalleyStream.BODY
    block = galley_blocks(blocks)["b-p0000-001"]
    assert (block.kind, block.stream) == (BlockKind.CHAPTER_SUMMARY, GalleyStream.BODY)


# Gierke's "Law1" on page 0, linked to endnote 1 printed on page 10 after
# a margin note beside it; and endnote 2, which nothing links.
_ENDNOTE_LINES = LinesFile(
    source_pdf_sha256=_SHA,
    pages=(
        _page_lines(0, "the Law1 of the land"),
        _page_lines(10, "Lex.", "1. See Bracton.", "2. And Glanvill."),
    ),
    rereads=(),
)


def _endnote(
    note_id: str, marker: str, blocks: tuple[Block, ...], *, referenced: bool
) -> Note:
    return Note(
        id=note_id,
        kind=NoteKind.ENDNOTE,
        marker=marker,
        blocks=blocks,
        origin=_origin(10),
        referenced=referenced,
    )


def _endnote_blocks(tmp_path: Path) -> BlocksFile:
    return _hand_made(
        tmp_path,
        _blocks_file(
            (
                _block(
                    "b-p0000-001",
                    BlockKind.PARAGRAPH,
                    (
                        _span("the Law"),
                        _span("1", "n-p0010-001"),
                        _span(" of the land"),
                    ),
                    _origin(0),
                ),
            ),
            (
                _endnote(
                    "n-p0010-001",
                    "1.",
                    (
                        _block(
                            "b-p0010-001",
                            BlockKind.MARGIN_NOTE,
                            (_span("Lex."),),
                            _origin(10),
                        ),
                        _block(
                            "b-p0010-002",
                            BlockKind.PARAGRAPH,
                            (_span("See Bracton."),),
                            _origin(10),
                        ),
                    ),
                    referenced=True,
                ),
                _endnote(
                    "n-p0010-002",
                    "2.",
                    (
                        _block(
                            "b-p0010-003",
                            BlockKind.PARAGRAPH,
                            (_span("And Glanvill."),),
                            _origin(10),
                        ),
                    ),
                    referenced=False,
                ),
            ),
        ),
    )


def test_endnote_marker_is_a_token_after_its_margin_note_referenced_or_not(
    tmp_path: Path,
) -> None:
    tokens = blocks_tokens(_endnote_blocks(tmp_path), _ENDNOTE_LINES)
    assert [(token.text, token.block_id) for token in tokens] == [
        ("the", "b-p0000-001"),
        ("Law", "b-p0000-001"),
        ("of", "b-p0000-001"),
        ("the", "b-p0000-001"),
        ("land", "b-p0000-001"),
        ("Lex.", "b-p0010-001"),
        ("1.", "b-p0010-002"),
        ("See", "b-p0010-002"),
        ("Bracton.", "b-p0010-002"),
        ("2.", "b-p0010-003"),
        ("And", "b-p0010-003"),
        ("Glanvill.", "b-p0010-003"),
    ]
    assert {token.stream for token in tokens[5:]} == {GalleyStream.NOTES}


def test_endnote_reference_text_is_no_token_at_blocks_or_markdown(
    tmp_path: Path,
) -> None:
    blocks = _endnote_blocks(tmp_path)
    at_blocks = blocks_tokens(blocks, _ENDNOTE_LINES)
    assert "1" not in [token.text for token in at_blocks]
    # Pandoc gives the link's text as a word of its own, between "Law" and
    # "of"; the body's other words keep their places.
    markdown = _markdown(
        *((word, "b-p0000-001") for word in ("the", "Law", "1", "of", "the", "land")),
        ("Lex.", "b-p0010-001"),
        *((word, "b-p0010-002") for word in ("1.", "See", "Bracton.")),
        *((word, "b-p0010-003") for word in ("2.", "And", "Glanvill.")),
    )
    at_markdown = markdown_tokens(markdown, blocks, at_blocks)
    assert [token.text for token in at_markdown] == [token.text for token in at_blocks]


def test_endnote_reference_word_equal_to_a_word_of_the_text_is_told_by_its_place(
    tmp_path: Path,
) -> None:
    # "1" is also a word of the body after the reference.
    blocks = _hand_made(
        tmp_path,
        _blocks_file(
            (
                _block(
                    "b-p0000-001",
                    BlockKind.PARAGRAPH,
                    (_span("Law"), _span("1", "n-p0010-001"), _span(" 1 more")),
                    _origin(0),
                ),
            ),
            (
                _endnote(
                    "n-p0010-001",
                    "1.",
                    (
                        _block(
                            "b-p0010-002",
                            BlockKind.PARAGRAPH,
                            (_span("See Bracton."),),
                            _origin(10),
                        ),
                    ),
                    referenced=True,
                ),
            ),
        ),
    )
    at_blocks = blocks_tokens(blocks, _ENDNOTE_LINES)
    markdown = _markdown(
        *((word, "b-p0000-001") for word in ("Law", "1", "1", "more")),
        *((word, "b-p0010-002") for word in ("1.", "See", "Bracton.")),
    )
    at_markdown = markdown_tokens(markdown, blocks, at_blocks)
    assert [token.text for token in at_markdown] == [
        "Law",
        "1",
        "more",
        "1.",
        "See",
        "Bracton.",
    ]


def test_endnote_words_stand_near_the_page_of_their_first_reference(
    tmp_path: Path,
) -> None:
    blocks = _endnote_blocks(tmp_path)
    tokens = endnote_pages(
        blocks_tokens(blocks, _ENDNOTE_LINES), blocks, note_references(blocks)
    )
    near = {
        (token.text, token.page_index, token.near_page)
        for token in tokens
        if token.block_id is not None and token.block_id.startswith("b-p0010")
    }
    assert near == {
        ("Lex.", 10, 0),
        ("1.", 10, 0),
        ("See", 10, 0),
        ("Bracton.", 10, 0),
        # Endnote 2 has no reference and keeps its own page.
        ("2.", 10, None),
        ("And", 10, None),
        ("Glanvill.", 10, None),
    }
    assert {token.window_page for token in tokens[5:9]} == {0}


# The order of the notes at markdown (spec section 5): book.md writes a
# referenced footnote after the block that refers to it and an
# unreferenced one after the last block of its page, as on Mariéjol's
# page 20, where the unreferenced note 1 follows notes 2 and 3.


def _footnote(
    note_id: str, block_id: str, marker: str, text: str, *, referenced: bool
) -> Note:
    return Note(
        id=note_id,
        kind=NoteKind.FOOTNOTE,
        marker=marker,
        blocks=(_block(block_id, BlockKind.PARAGRAPH, (_span(text),), _origin(0)),),
        origin=_origin(0),
        referenced=referenced,
    )


_PAGE_OF_NOTES = LinesFile(
    source_pdf_sha256=_SHA,
    pages=(_page_lines(0, "the text2 here", "(1) A stray note.", "(2) Glanvill."),),
    rereads=(),
)


def _page_of_notes(tmp_path: Path) -> BlocksFile:
    return _hand_made(
        tmp_path,
        _blocks_file(
            (
                _block(
                    "b-p0000-001",
                    BlockKind.PARAGRAPH,
                    (_span("the text"), _span("2", "n-p0000-002"), _span(" here")),
                    _origin(0),
                ),
            ),
            (
                _footnote(
                    "n-p0000-001",
                    "b-p0000-002",
                    "(1)",
                    "A stray note.",
                    referenced=False,
                ),
                _footnote(
                    "n-p0000-002", "b-p0000-003", "(2)", "Glanvill.", referenced=True
                ),
            ),
        ),
    )


def test_notes_at_markdown_keep_the_order_of_blocks_json(tmp_path: Path) -> None:
    blocks = _page_of_notes(tmp_path)
    # book.md's order: the referenced note's definition after its block,
    # then the unreferenced note, printed first.
    markdown = _markdown(
        ("the", "b-p0000-001"),
        ("text", "b-p0000-001"),
        ("here", "b-p0000-001"),
        ("Glanvill.", "b-p0000-003"),
        ("(1)", "b-p0000-002"),
        ("A", "b-p0000-002"),
        ("stray", "b-p0000-002"),
        ("note.", "b-p0000-002"),
    )
    tokens = markdown_tokens(markdown, blocks, blocks_tokens(blocks, _PAGE_OF_NOTES))
    assert [token.text for token in tokens] == [
        "the",
        "text",
        "here",
        "(1)",
        "A",
        "stray",
        "note.",
        "Glanvill.",
    ]


# galley's markdown stage on a file with every kind of note: its words, as
# read_markdown reads them, are the tokens at blocks, word for word.

_EVERY_NOTE_LINES = LinesFile(
    source_pdf_sha256=_SHA,
    pages=(
        _page_lines(
            0,
            "CHAPTER I.",
            "OF LAW",
            "the Law1 of the land2 here",
            "* A stray note.",
            "2 Glanvill.",
        ),
        _page_lines(10, "Lex.", "1. See Bracton.", "2. And more."),
    ),
    rereads=(),
)


def _every_note(tmp_path: Path) -> BlocksFile:
    return _hand_made(
        tmp_path,
        _blocks_file(
            (
                _heading("b-p0000-001", "CHAPTER I.", "OF LAW"),
                _block(
                    "b-p0000-002",
                    BlockKind.PARAGRAPH,
                    (
                        _span("the Law"),
                        _span("1", "n-p0010-001"),
                        _span(" of the land"),
                        _span("2", "n-p0000-002"),
                        _span(" here"),
                    ),
                    _origin(0),
                ),
            ),
            (
                _footnote(
                    "n-p0000-001", "b-p0000-003", "*", "A stray note.", referenced=False
                ),
                _footnote(
                    "n-p0000-002", "b-p0000-004", "2", "Glanvill.", referenced=True
                ),
                _endnote(
                    "n-p0010-001",
                    "1.",
                    (
                        _block(
                            "b-p0010-001",
                            BlockKind.MARGIN_NOTE,
                            (_span("Lex."),),
                            _origin(10),
                        ),
                        _block(
                            "b-p0010-002",
                            BlockKind.PARAGRAPH,
                            (_span("See Bracton."),),
                            _origin(10),
                        ),
                    ),
                    referenced=True,
                ),
                _endnote(
                    "n-p0010-002",
                    "2.",
                    (
                        _block(
                            "b-p0010-003",
                            BlockKind.PARAGRAPH,
                            (_span("And more."),),
                            _origin(10),
                        ),
                    ),
                    referenced=False,
                ),
            ),
        ),
    )


@pytest.mark.pandoc
def test_markdown_tokens_of_galleys_book_md_are_the_tokens_at_blocks(
    tmp_path: Path,
) -> None:
    blocks = _every_note(tmp_path)
    config = BookConfig(
        pdf=tmp_path / "book.pdf", title="Law", authors=("A",), language=Language.EN
    )
    markdown = read_markdown(render_markdown(blocks, config))
    at_blocks = blocks_tokens(blocks, _EVERY_NOTE_LINES)
    at_markdown = markdown_tokens(markdown, blocks, at_blocks)
    assert [(token.text, token.block_id) for token in at_markdown] == [
        (token.text, token.block_id) for token in at_blocks
    ]
    assert [token.in_label for token in at_markdown] == [
        token.in_label for token in at_blocks
    ]
