"""Tests of the plan notes-vision's work package 1 (docs/plans/notes-vision.md):
a numbered paragraph runs on over a page break past the page's unlinked
notes, which then follow it (docs/specs/structure.md, section 16, "A
numbered paragraph runs on"), and a line-end hyphen the OCR read as a sign
of a note reference is joined, the sign recorded as removed (section 5, "A
hyphen read as a sign").

The literal pages are written by hand: a word is 5 pt wide per character
and 10 pt high, with one character's width between words, and lines lie 15
pt apart in a column from 50 to 400 pt.
"""

from collections.abc import Callable
from dataclasses import replace

import pytest

from galley.book_folder import BookFolder
from galley.config import read_config
from galley.errors import FidelityBoundary, FidelityError, GalleyError
from galley.fidelity import check_stage
from galley.markdown import render_markdown
from galley.model import (
    Block,
    BlocksFile,
    Box,
    ChangeReason,
    Line,
    LinesFile,
    PageLayout,
    Region,
    RemovalReason,
    Word,
    WordChange,
    block_text,
    read_blocks,
)
from galley.structure import make_blocks
from galley.structure._hyphens import (
    HyphenJoin,
    LostHyphens,
    PageLine,
    join_lines,
    join_sign_hyphen,
    sign_removals,
)

_HASH = "a" * 64
_CHAR_PT = 5.0
_HEIGHT_PT = 10.0
_PITCH_PT = 15.0
_LEFT_PT = 50.0
_RIGHT_PT = 400.0


def _block_with(blocks: BlocksFile, text: str) -> Block:
    (block,) = (block for block in blocks.blocks if text in block_text(block))
    return block


def _note_id_with(blocks: BlocksFile, text: str) -> str:
    (note_id,) = (
        note.id
        for note in blocks.notes
        if any(text in block_text(block) for block in note.blocks)
    )
    return note_id


# Kadesh's pages 11 and 12 (excerpt pages 3 and 4 of `kadesh_redo`, read
# with ocr = "redo"): "1. Of the three…" and "3. The RELIEFs…" are numbered
# paragraphs whose page ends in mid-sentence, checked on the page images
# on 19 November 2026.


@pytest.mark.tesseract
@pytest.mark.parametrize(
    ("joined", "pages"),
    [
        ("exhaustively collated with the original of the Sallier Papyrus,", (3, 4)),
        ("by the artists of Ramses II.: Abydos, the Ramesseum (twice),", (4, 5)),
    ],
)
def test_numbered_paragraph_of_kadesh_runs_on_over_the_page_break(
    redo_excerpt_run: Callable[[str], BookFolder],
    joined: str,
    pages: tuple[int, int],
) -> None:
    blocks = read_blocks(redo_excerpt_run("kadesh_redo").blocks_json)
    block = _block_with(blocks, joined)
    assert tuple(origin.page_index for origin in block.origin) == pages


@pytest.mark.tesseract
def test_notes_of_kadesh_page_11_follow_the_joined_paragraph(
    redo_excerpt_run: Callable[[str], BookFolder],
) -> None:
    folder = redo_excerpt_run("kadesh_redo")
    blocks = read_blocks(folder.blocks_json)
    markdown = render_markdown(blocks, read_config(folder.book_toml))
    paragraph = _block_with(blocks, "the Sallier Papyrus, now in the British Museum")
    note = _note_id_with(blocks, "Called by de Rougé the Bulletin.")
    assert markdown.index(f"{{#{paragraph.id}") < markdown.index(f"{{#{note}")


# Domesday's pages 467 and 468 (excerpt pages 2 and 3 of `domesday_run_on`):
# the OCR starts the paragraph with numbers of the table above it, "295…",
# the book's marker form, and the page ends "…No doubt, the", followed on
# the page by its notes, "2 See above, p. 76." among them, and on page 468
# by "medieval sheep were wretched little animals" (page images, 19
# November 2026).


@pytest.mark.pandoc
@pytest.mark.tesseract
def test_paragraph_of_domesday_runs_on_past_the_unlinked_note(
    excerpt_books: frozendict[str, BookFolder],
) -> None:
    folder = excerpt_books["domesday_run_on"]
    blocks = read_blocks(folder.blocks_json)
    paragraph = _block_with(blocks, "No doubt, the medieval sheep were wretched")
    assert tuple(origin.page_index for origin in paragraph.origin) == (2, 3)
    markdown = folder.book_md.read_text(encoding="utf-8")
    note = _note_id_with(blocks, "See above, p. 76.")
    assert markdown.index(f"{{#{paragraph.id}") < markdown.index(f"{{#{note}")


# A hyphen read as a sign (spec section 5): Stubbs' "aggres*" "sive" on its
# pages 24 and 25, whose hyphen the scan prints as a faint dot.

_WORD_LIST = frozenset({"aggressive", "pilgrims"})


@pytest.mark.parametrize(
    ("first", "second", "joined"),
    [
        ("aggres*", "sive", HyphenJoin("aggressive", ChangeReason.HYPHEN_JOIN, "*")),
        ("pil^", "grims", HyphenJoin("pilgrims", ChangeReason.HYPHEN_JOIN, "^")),
        ("aggres•", "sive", HyphenJoin("aggressive", ChangeReason.HYPHEN_JOIN, "•")),
    ],
)
def test_hyphen_read_as_a_sign_is_joined_on_evidence(
    first: str, second: str, joined: HyphenJoin
) -> None:
    assert join_sign_hyphen(first, second, frozenset(), _WORD_LIST) == joined


@pytest.mark.parametrize(
    ("first", "second", "word_list"),
    [
        # Each case but the last two has the word the join would make in
        # its word list, so that it fails on its own guard.
        ("aggres*", "Sive", _WORD_LIST),  # a capital: "aggresSive"
        ("C*", "omes", frozenset({"comes"})),  # one letter before the sign
        ("aggres-", "sive", _WORD_LIST),  # a hyphen, join_hyphen's
        ("aggres**", "sive", frozenset({"aggres*sive"})),  # two signs
        ("justice*", "or", _WORD_LIST),  # a reference: "justiceor" is no word
        ("aggres*", "sive", frozenset()),  # no evidence
    ],
)
def test_sign_at_a_line_end_without_evidence_is_not_joined(
    first: str, second: str, word_list: frozenset[str]
) -> None:
    assert join_sign_hyphen(first, second, frozenset(), word_list) is None


def test_sign_join_over_a_page_break_records_the_sign_after_the_word() -> None:
    joined = join_lines(
        (
            PageLine(24, ("the", "impulse", "of", "aggres*")),
            PageLine(25, ("sive", "warfare,")),
        ),
        frozenset(),
        _WORD_LIST,
        lost_hyphens=LostHyphens.NOT_JOINED,
        common_inner_words=frozenset(),
    )
    assert joined.words == ("the", "impulse", "of", "aggressive", "warfare,")
    assert joined.changes == (
        WordChange(
            page_index=24,
            before=("aggres*", "sive"),
            after=("aggressive", "*"),
            reason=ChangeReason.HYPHEN_JOIN,
        ),
    )


def _line(text: str, row: int) -> Line:
    top = 100.0 + row * _PITCH_PT
    words = []
    left = _LEFT_PT
    for part in text.split(" "):
        right = left + _CHAR_PT * len(part)
        words.append(Word(part, Box(left, top, right, top + _HEIGHT_PT), None))
        left = right + _CHAR_PT
    return Line(Box(_LEFT_PT, top, words[-1].box.x1, top + _HEIGHT_PT), tuple(words))


# 70 characters, 350 pt: a body line from edge to edge, ending with a word
# split at the line end.
_FULL = "the great secular states to break the impulse of warfare in the aggres*"
_NEXT = "sive warfare to serve as models of the government of the other states ."


def _stubbs_lines() -> LinesFile:
    def page(index: int, *texts: str) -> PageLayout:
        lines = tuple(_line(text, row) for row, text in enumerate(texts))
        box = Box(_LEFT_PT, lines[0].box.top, _RIGHT_PT, lines[-1].box.bottom)
        return PageLayout(index=index, regions=(Region(box, lines),), figures=())

    filler = _NEXT.replace("sive ", "here ")
    return LinesFile(
        source_pdf_sha256=_HASH,
        pages=(
            page(24, filler, filler, _FULL),
            page(25, _NEXT, filler, filler),
        ),
        rereads=(),
    )


def test_sign_taken_off_by_a_join_is_a_misread_hyphen_removal() -> None:
    lines = _stubbs_lines()
    blocks = make_blocks(lines, _WORD_LIST, workers=1)
    assert "aggressive warfare" in " ".join(
        block_text(block) for block in blocks.blocks
    )
    sign_word = lines.pages[0].regions[0].lines[-1].words[-1]
    assert [
        (removal.page_index, removal.box, removal.text)
        for removal in blocks.removals
        if removal.reason is RemovalReason.MISREAD_HYPHEN
    ] == [(24, sign_word.box, "*")]
    check_stage(FidelityBoundary.STRUCTURE, lines, blocks)


def test_sign_join_without_its_removal_fails_the_fidelity_check() -> None:
    lines = _stubbs_lines()
    blocks = make_blocks(lines, _WORD_LIST, workers=1)
    without = replace(
        blocks,
        removals=tuple(
            removal
            for removal in blocks.removals
            if removal.reason is not RemovalReason.MISREAD_HYPHEN
        ),
    )
    with pytest.raises(FidelityError, match="misread_hyphen"):
        check_stage(FidelityBoundary.STRUCTURE, lines, without)


def test_sign_join_whose_sign_vanishes_fails_the_fidelity_check() -> None:
    # The change says the join dropped only the sign, but the sign is in no
    # removal and not in the change's `after`: it vanished without a record.
    lines = _stubbs_lines()
    blocks = make_blocks(lines, _WORD_LIST, workers=1)
    vanished = replace(
        blocks,
        removals=tuple(
            removal
            for removal in blocks.removals
            if removal.reason is not RemovalReason.MISREAD_HYPHEN
        ),
        word_changes=tuple(
            replace(change, after=change.after[:1])
            if change.before == ("aggres*", "sive")
            else change
            for change in blocks.word_changes
        ),
    )
    with pytest.raises(FidelityError):
        check_stage(FidelityBoundary.STRUCTURE, lines, vanished)


def test_misread_hyphen_removal_without_its_join_fails_the_fidelity_check() -> None:
    lines = _stubbs_lines()
    blocks = make_blocks(lines, _WORD_LIST, workers=1)
    (removal,) = (
        removal
        for removal in blocks.removals
        if removal.reason is RemovalReason.MISREAD_HYPHEN
    )
    doubled = replace(blocks, removals=(*blocks.removals, replace(removal, text="^")))
    with pytest.raises(FidelityError, match="misread_hyphen"):
        check_stage(FidelityBoundary.STRUCTURE, lines, doubled)


def test_sign_ending_a_word_an_earlier_join_made_is_not_joined() -> None:
    # "con-" / "tinu*" / "ally": the first join makes "continu*", which ends
    # no line of lines.json, so a sign join after it would have no box for
    # the sign's removal. The sign stays (spec section 5).
    filler = _NEXT.replace("sive ", "here ")
    full = _FULL.replace("aggres*", "con-")
    lines = tuple(
        _line(text, row)
        for row, text in enumerate(
            (filler, full, "tinu*", _NEXT.replace("sive ", "ally "), filler)
        )
    )
    box = Box(_LEFT_PT, lines[0].box.top, _RIGHT_PT, lines[-1].box.bottom)
    chained = LinesFile(
        source_pdf_sha256=_HASH,
        pages=(PageLayout(index=3, regions=(Region(box, lines),), figures=()),),
        rereads=(),
    )
    blocks = make_blocks(chained, frozenset({"continually"}), workers=1)
    assert [change.before for change in blocks.word_changes] == [("con-", "tinu*")]
    assert not [
        removal
        for removal in blocks.removals
        if removal.reason is RemovalReason.MISREAD_HYPHEN
    ]
    check_stage(FidelityBoundary.STRUCTURE, chained, blocks)


def _retyped_sign_join(first: str) -> tuple[LinesFile, BlocksFile]:
    """Stubbs' lines and blocks with "aggres*" retyped as `first` in
    lines.json and in its join, and the joined word and the removed sign
    retyped to match: a change shaped like a join over a sign."""
    lines = _stubbs_lines()
    blocks = make_blocks(lines, _WORD_LIST, workers=1)
    joined, sign = first[:-1] + "sive", first[-1:]

    def retyped_word(word: Word) -> Word:
        return replace(word, text=first) if word.text == "aggres*" else word

    retyped_lines = replace(
        lines,
        pages=tuple(
            replace(
                page,
                regions=tuple(
                    replace(
                        region,
                        lines=tuple(
                            replace(line, words=tuple(map(retyped_word, line.words)))
                            for line in region.lines
                        ),
                    )
                    for region in page.regions
                ),
            )
            for page in lines.pages
        ),
    )
    retyped_blocks = replace(
        blocks,
        blocks=tuple(
            replace(
                block,
                spans=tuple(
                    replace(span, text=span.text.replace("aggressive", joined))
                    for span in block.spans
                ),
            )
            for block in blocks.blocks
        ),
        word_changes=tuple(
            replace(change, before=(first, "sive"), after=(joined, sign))
            if change.before == ("aggres*", "sive")
            else change
            for change in blocks.word_changes
        ),
        removals=tuple(
            replace(removal, text=sign)
            if removal.reason is RemovalReason.MISREAD_HYPHEN
            else removal
            for removal in blocks.removals
        ),
    )
    return retyped_lines, retyped_blocks


def test_retyped_sign_join_of_a_real_sign_passes_the_fidelity_check() -> None:
    # `_retyped_sign_join` keeps a true sign join true.
    check_stage(FidelityBoundary.STRUCTURE, *_retyped_sign_join("aggre^"))


@pytest.mark.parametrize(
    "first",
    [
        "aggre1*",  # a digit before the sign
        "aggres.",  # a full stop is no sign of a reference
        "aggres,",  # nor a comma
    ],
)
def test_join_shaped_like_one_over_a_sign_fails_the_fidelity_check(first: str) -> None:
    with pytest.raises(FidelityError):
        check_stage(FidelityBoundary.STRUCTURE, *_retyped_sign_join(first))


def _change(first: str) -> WordChange:
    return WordChange(
        page_index=24,
        before=(first, "sive"),
        after=(first[:-1] + "sive", first[-1:]),
        reason=ChangeReason.HYPHEN_JOIN,
    )


def test_sign_removal_takes_the_box_of_the_first_line_ending_with_the_word() -> None:
    page = PageLayout(
        index=24,
        regions=(
            Region(
                Box(_LEFT_PT, 100.0, _RIGHT_PT, 140.0),
                (_line(_FULL, 0), _line("here", 1), _line(_FULL, 2)),
            ),
        ),
        figures=(),
    )
    lines = LinesFile(source_pdf_sha256=_HASH, pages=(page,), rereads=())
    (removal,) = sign_removals((_change("aggres*"),), lines)
    assert removal.box == page.regions[0].lines[0].words[-1].box
    assert removal.box != page.regions[0].lines[2].words[-1].box


def test_sign_removal_of_a_word_that_ends_no_line_stops_structure() -> None:
    with pytest.raises(GalleyError, match="no line ends with 'regres\\*'"):
        sign_removals((_change("regres*"),), _stubbs_lines())


def test_join_of_two_words_not_over_a_sign_makes_no_sign_removal() -> None:
    # The same shape test as the fidelity check's: "aggressive" and "x" is
    # no join over the sign "*", though it gives two words.
    change = replace(_change("aggres*"), after=("aggressive", "x"))
    assert sign_removals((change,), _stubbs_lines()) == ()
