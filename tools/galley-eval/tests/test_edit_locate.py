"""Tests of where galley-eval's edit sheet finds an edit on its page (spec
section 9b, "Where an edit is printed"), on literal blocks and lines: a
word broken across a page, a match that starts on the next page, the
lines above an edit in another column, and an edit in a note."""

from galley.model import (
    Block,
    BlockKind,
    BlocksFile,
    Box,
    Edit,
    Emphasis,
    Line,
    LinesFile,
    Note,
    NoteKind,
    Origin,
    PageLayout,
    Region,
    Span,
    Word,
)
from galley_eval.edit_sheet import Located, locate

_SHA = "a" * 64


def _word(text: str, x0: float, top: float) -> Word:
    return Word(text, Box(x0, top, x0 + 10 * len(text), top + 10), None)


def _line(*words: Word) -> Line:
    return Line(
        Box(
            min(word.box.x0 for word in words),
            min(word.box.top for word in words),
            max(word.box.x1 for word in words),
            max(word.box.bottom for word in words),
        ),
        words,
    )


def _page(index: int, *lines: Line) -> PageLayout:
    return PageLayout(index, (Region(Box(0, 0, 600, 800), lines),), ())


def _block(block_id: str, text: str, *origin: Origin) -> Block:
    return Block(
        id=block_id,
        kind=BlockKind.PARAGRAPH,
        level=None,
        label=None,
        spans=(Span(text, Emphasis.NONE, None),),
        figure=None,
        origin=origin,
    )


def _edit(block_id: str, old: str, page_index: int) -> Edit:
    return Edit(
        block_id=block_id,
        block_sha256="0" * 64,
        old=old,
        new=old.upper(),
        author="correct",
        reason="vision_word",
        page_index=page_index,
        model="qwen/qwen3.6-35b-a3b",
        second_reading=None,
    )


# A paragraph from page 0 to page 1, "par-" at the foot of page 0 and
# "ticular" at the top of page 1 (Kadesh, edit 442, "particular").
_BROKEN = _word("par-", 200, 100)
_LINES = LinesFile(
    source_pdf_sha256=_SHA,
    pages=(
        _page(0, _line(_word("the", 60, 100), _word("great", 100, 100), _BROKEN)),
        _page(1, _line(_word("ticular", 60, 100), _word("case", 150, 100))),
        # Page 2: two columns; the edit's word is in the left one, below a
        # line of the left column and level with a line of the right.
        _page(
            2,
            _line(_word("left", 60, 100)),
            _line(_word("right", 300, 113)),
            _line(_word("word", 60, 124)),
        ),
    ),
    rereads=(),
)
_NOTE_BLOCK = _block("b-p0002-009", "word", Origin(2, Box(50, 120, 250, 140)))
_BLOCKS = BlocksFile(
    source_pdf_sha256=_SHA,
    blocks=(
        _block(
            "b-p0000-001",
            "the great particular case",
            Origin(0, Box(50, 90, 400, 120)),
            Origin(1, Box(50, 90, 400, 120)),
        ),
    ),
    notes=(
        Note(
            id="n-p0002-001",
            kind=NoteKind.FOOTNOTE,
            marker="1",
            blocks=(_NOTE_BLOCK,),
            origin=_NOTE_BLOCK.origin,
            referenced=False,
        ),
    ),
    removals=(),
    word_changes=(),
    page_numbers=(),
)


def test_a_word_broken_across_a_page_is_framed_on_its_page() -> None:
    location = locate(_edit("b-p0000-001", "particular", 0), _BLOCKS, _LINES)
    assert location.located is Located.BLOCK_WORDS
    assert location.words_boxes == (_BROKEN.box,)


def test_a_match_that_starts_on_the_next_page_is_not_on_this_one() -> None:
    location = locate(_edit("b-p0000-001", "ticular case", 0), _BLOCKS, _LINES)
    assert location.located is Located.BLOCK_BOX


def test_the_line_above_in_the_crop_is_one_of_the_same_column() -> None:
    location = locate(_edit("b-p0002-009", "word", 2), _BLOCKS, _LINES)
    # A note's block is found among the notes' blocks.
    assert location.located is Located.BLOCK_WORDS
    assert location.crop is not None
    # The left column's line above, top 100, not the right column's, top
    # 113, which is nearer; less the margin of 6 pt.
    assert location.crop.top == 100 - 6
