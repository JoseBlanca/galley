"""Tests of galley_eval.galley_side: the tokens of galley's four stage
outputs (spec section 5, "galley's tokens")."""

from collections.abc import Callable
from pathlib import Path

import pytest

from galley.book_folder import BookFolder
from galley.fidelity import MarkdownWord, MarkdownWords
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
    Span,
    TextSource,
    Word,
    WordChange,
    WordsFile,
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
        ("cate", 1, GalleyStream.NOTES, "b-p0001-002"),
        ("it", 1, GalleyStream.BODY, "b-p0000-001"),
        # "here" against "here." of blocks is a replaced pair: page 1.
        ("here", 1, GalleyStream.BODY, "b-p0000-001"),
        ("OTHER", 1, GalleyStream.MARGIN_NOTES, "b-p0001-001"),
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


# The page edge skips lines of marks


def test_a_line_of_marks_above_the_running_head_does_not_take_its_flag() -> None:
    # Haskins page index 28: a "!" from a speck above "NORMANDY IN HISTORY 13".
    lines = LinesFile(
        source_pdf_sha256=_SHA,
        pages=(
            _page_lines(0, "!", "NORMANDY IN HISTORY 13", "the text", "more text", ";"),
        ),
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
    lines = LinesFile(source_pdf_sha256=_SHA, pages=(_page_lines(0, "!", "* ;"),))
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
