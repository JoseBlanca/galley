"""Tests of galley.structure (docs/specs/structure.md, section 9).

Every value is written by hand: structure's tests need no output of layout.
The excerpt tests of structure on the reference pages come later, once the
owner has checked those pages.
"""

import hashlib
from dataclasses import replace
from pathlib import Path

import pytest

from galley import structure
from galley.book_folder import BookFolder
from galley.config import BookConfig, Language
from galley.errors import FidelityBoundary, FidelityError, InputFileError
from galley.fidelity import check_stage
from galley.model import (
    Block,
    BlockKind,
    BlocksFile,
    Box,
    Emphasis,
    Line,
    LinesFile,
    Origin,
    PageInfo,
    PageKind,
    PageLayout,
    PageNumber,
    PageNumberPosition,
    PagesFile,
    Region,
    Removal,
    RemovalReason,
    Span,
    TextSource,
    Word,
    block_text,
    read_blocks,
    write_blocks,
    write_lines,
    write_pages,
)
from galley.structure import make_blocks, survey_book


def _word(text: str, x0: float, top: float, x1: float, bottom: float) -> Word:
    return Word(text, Box(x0, top, x1, bottom), None)


_FIRST_LINE = Line(
    Box(50, 100, 120, 113),
    (_word("Alpha", 50, 100, 90, 112), _word("beta,", 95, 101, 120, 113)),
)
_SECOND_LINE = Line(
    Box(40, 120, 130, 132),
    (_word("gamma", 40, 120, 80, 132), _word("delta.", 85, 120, 130, 131)),
)
_REGION = Region(Box(40, 100, 130, 132), (_FIRST_LINE, _SECOND_LINE))


def _paragraph(block_id: str, text: str, page_index: int, box: Box) -> Block:
    return Block(
        id=block_id,
        kind=BlockKind.PARAGRAPH,
        level=None,
        spans=(Span(text, Emphasis.NONE, None),),
        figure=None,
        origin=(Origin(page_index, box),),
    )


# Pages written by hand. A word is 5 pt wide per character and 10 pt high,
# with one character's width between words, unless given otherwise.

_CHAR_PT = 5.0
_WORD_HEIGHT_PT = 10.0
_PITCH_PT = 15.0
_BODY_LEFT_PT = 50.0


def _words_at(
    text: str, x0: float, top: float, height: float = _WORD_HEIGHT_PT
) -> tuple[Word, ...]:
    words = []
    left = x0
    for part in text.split(" "):
        right = left + _CHAR_PT * len(part)
        words.append(Word(part, Box(left, top, right, top + height), None))
        left = right + _CHAR_PT
    return tuple(words)


def _box(boxes: tuple[Box, ...]) -> Box:
    return Box(
        min(box.x0 for box in boxes),
        min(box.top for box in boxes),
        max(box.x1 for box in boxes),
        max(box.bottom for box in boxes),
    )


def _line(text: str, x0: float, top: float, height: float = _WORD_HEIGHT_PT) -> Line:
    words = _words_at(text, x0, top, height)
    return Line(_box(tuple(word.box for word in words)), words)


def _region(*lines: Line) -> Region:
    return Region(_box(tuple(line.box for line in lines)), lines)


def _body(top: float, *texts: str, x0: float = _BODY_LEFT_PT) -> Region:
    """A region of one line per text, 15 pt apart, from `top`."""
    return _region(
        *(
            _line(text, x0, top + _PITCH_PT * number)
            for number, text in enumerate(texts)
        )
    )


_BODY_TEXTS = (
    "the first line of the body",
    "the second line of the body",
    "the third line of the body",
    "the fourth line of the body",
    "the fifth line of the body",
    "the sixth line of the body",
)


def _page_with_head(index: int, head: str, head_top: float = 36.0) -> PageLayout:
    """A page with a head line at `head_top` and six body lines from 34 pt
    below it."""
    return PageLayout(
        index,
        (
            _region(_line(head, _BODY_LEFT_PT, head_top)),
            _body(head_top + 34, *_BODY_TEXTS),
        ),
        (),
    )


# Heads that differ from one another, each at least 0.75 alike to another.
_HEADS_WITHOUT_NUMBERS = (
    "THE BOOK",
    "THE BOKO",
    "TIIE BOOK",
    "THE BOOKS",
    "THF BOOK",
    "THE BQOK",
)


def _lines_of(*pages: PageLayout) -> LinesFile:
    return LinesFile(source_pdf_sha256=_HASH, pages=pages)


def _numbered_heads() -> tuple[PageLayout, ...]:
    """Pages 10 to 15 printed 25 to 30, the number first on even pages."""
    return tuple(
        _page_with_head(
            index,
            f"{index + 15} THE BOOK" if index % 2 == 0 else f"THE BOOK {index + 15}",
        )
        for index in range(10, 16)
    )


# survey_book


def test_survey_finds_numbered_heads_running_heads_and_the_offset() -> None:
    survey = survey_book(_lines_of(*_numbered_heads()), workers=1)
    assert survey.running_heads == frozenset(range(10, 16))
    assert survey.head_page_offset == -15
    assert survey.first_arabic_page == 10
    assert survey.body_word_height == _WORD_HEIGHT_PT
    assert survey.body_line_pitch == _PITCH_PT


def test_survey_finds_heads_without_numbers_running_heads_by_their_letters() -> None:
    pages = tuple(
        _page_with_head(index, head)
        for index, head in enumerate(_HEADS_WITHOUT_NUMBERS, start=10)
    )
    survey = survey_book(_lines_of(*pages), workers=1)
    assert survey.running_heads == frozenset(range(10, 16))
    assert survey.head_page_offset is None
    assert survey.first_arabic_page is None


def test_survey_does_not_take_a_head_line_alike_to_no_other_for_a_running_head() -> (
    None
):
    pages = (
        _page_with_head(10, "THE BOOK"),
        _page_with_head(11, "THE BOOK"),
        _page_with_head(12, "CHAPTER ON NORMANDY"),
    )
    assert survey_book(_lines_of(*pages), workers=1).running_heads == frozenset(
        {10, 11}
    )


def test_survey_does_not_take_the_same_title_70_pt_lower_for_a_running_head() -> None:
    pages = (
        *(
            _page_with_head(index, head)
            for index, head in enumerate(_HEADS_WITHOUT_NUMBERS, start=10)
        ),
        _page_with_head(16, "THE BOOK", head_top=106.0),
    )
    survey = survey_book(_lines_of(*pages), workers=1)
    assert survey.running_heads == frozenset(range(10, 16))


def test_survey_book_words_leave_out_the_parts_of_a_hyphenated_word() -> None:
    page = PageLayout(
        0, (_body(70, "Of the neces-", "sary Anglo-Saxon things,", "and so"),), ()
    )
    assert survey_book(_lines_of(page), workers=1).book_words == frozenset(
        {"of", "the", "anglo-saxon", "things", "and", "so"}
    )


def test_survey_body_word_height_is_the_median_of_the_lines_medians() -> None:
    small = _region(
        *(_line("a small note", 50, 300 + 10 * n, height=7.0) for n in range(3))
    )
    page = PageLayout(0, (_body(70, *_BODY_TEXTS[:4]), small), ())
    assert survey_book(_lines_of(page), workers=1).body_word_height == _WORD_HEIGHT_PT


# Running heads and page numbers in the head


def _removals_of(page_index: int, blocks: BlocksFile) -> tuple[Removal, ...]:
    return tuple(
        removal for removal in blocks.removals if removal.page_index == page_index
    )


def test_head_with_a_page_number_and_a_mark_above_is_removed_in_three_parts() -> None:
    mark = _line(";", 120, 20)
    head = _line("214 NORMANS IN EUROPEAN HISTORY", _BODY_LEFT_PT, 36)
    page = PageLayout(229, (_region(mark, head), _body(70, *_BODY_TEXTS)), ())
    others = (
        _page_with_head(230, "THE COMING OF THE NORMANS 215"),
        _page_with_head(231, "216 NORMANS IN EUROPEAN HISTORY"),
    )
    blocks = make_blocks(_lines_of(page, *others), workers=1)
    assert _removals_of(229, blocks) == (
        Removal(
            page_index=229, box=mark.box, text=";", reason=RemovalReason.STRAY_MARK
        ),
        Removal(
            page_index=229,
            box=head.words[0].box,
            text="214",
            reason=RemovalReason.PAGE_NUMBER,
        ),
        Removal(
            page_index=229,
            box=_box(tuple(word.box for word in head.words[1:])),
            text="NORMANS IN EUROPEAN HISTORY",
            reason=RemovalReason.RUNNING_HEAD,
        ),
    )
    assert blocks.page_numbers == (
        PageNumber(229, "214", PageNumberPosition.HEAD),
        PageNumber(230, "215", PageNumberPosition.HEAD),
        PageNumber(231, "216", PageNumberPosition.HEAD),
    )
    assert all("NORMANS" not in block_text(block) for block in blocks.blocks)


def test_marks_above_a_head_line_that_is_no_running_head_stay() -> None:
    page = PageLayout(
        3,
        (
            _region(_line(";", 120, 20), _line("A TITLE", 80, 36)),
            _body(70, *_BODY_TEXTS),
        ),
        (),
    )
    blocks = make_blocks(_lines_of(page), workers=1)
    assert blocks.removals == ()
    assert block_text(blocks.blocks[0]) == "; A TITLE"


def test_misread_head_number_goes_with_the_running_head_and_gives_no_page_number() -> (
    None
):
    pages = (
        _page_with_head(130, "THE BOOK ii8"),
        _page_with_head(131, "THE BOOK 119"),
    )
    blocks = make_blocks(_lines_of(*pages), workers=1)
    assert _removals_of(130, blocks) == (
        Removal(
            page_index=130,
            box=pages[0].regions[0].box,
            text="THE BOOK ii8",
            reason=RemovalReason.RUNNING_HEAD,
        ),
    )
    assert blocks.page_numbers == (PageNumber(131, "119", PageNumberPosition.HEAD),)


def test_roman_head_number_counts_only_before_the_first_arabic_one() -> None:
    pages = (
        _page_with_head(5, "PREFACE xi"),
        _page_with_head(6, "PREFACE xii"),
        _page_with_head(20, "THE EARLY KINGS 3"),
        _page_with_head(21, "THE EARLY KINGS. ch. i."),
    )
    blocks = make_blocks(_lines_of(*pages), workers=1)
    assert blocks.page_numbers == (
        PageNumber(5, "xi", PageNumberPosition.HEAD),
        PageNumber(6, "xii", PageNumberPosition.HEAD),
        PageNumber(20, "3", PageNumberPosition.HEAD),
    )
    assert _removals_of(21, blocks)[0].text == "THE EARLY KINGS. ch. i."


def test_of_two_head_numbers_the_one_the_offset_gives_is_the_page_number() -> None:
    pages = (
        _page_with_head(20, "5 THE BOOK"),
        _page_with_head(21, "THE BOOK 6"),
        _page_with_head(22, "12 THE BOOK 7"),
    )
    blocks = make_blocks(_lines_of(*pages), workers=1)
    assert blocks.page_numbers[-1] == PageNumber(22, "7", PageNumberPosition.HEAD)
    assert tuple(removal.text for removal in _removals_of(22, blocks)) == (
        "12 THE BOOK",
        "7",
    )


# make_blocks

_HASH = "a" * 64
_LINES = LinesFile(
    source_pdf_sha256=_HASH,
    pages=(
        PageLayout(0, (_REGION,), ()),
        PageLayout(1, (), ()),
        PageLayout(2, (replace(_REGION, lines=(_SECOND_LINE,)),), ()),
    ),
)


def test_make_blocks_gives_the_paragraphs_in_page_order_and_nothing_else() -> None:
    assert make_blocks(_LINES, workers=1) == BlocksFile(
        source_pdf_sha256=_HASH,
        blocks=(
            _paragraph("b-p0000-001", "Alpha beta, gamma delta.", 0, _REGION.box),
            _paragraph("b-p0002-001", "gamma delta.", 2, _SECOND_LINE.box),
        ),
        notes=(),
        removals=(),
        word_changes=(),
        page_numbers=(),
    )


# The fidelity check at the structure boundary


def test_fidelity_check_passes_on_the_blocks_of_hand_made_lines() -> None:
    check_stage(FidelityBoundary.STRUCTURE, _LINES, make_blocks(_LINES, workers=1))


def test_fidelity_check_fails_when_a_word_is_dropped_from_a_line() -> None:
    dropped = replace(_FIRST_LINE, words=_FIRST_LINE.words[1:])
    lines_without_alpha = replace(
        _LINES,
        pages=(
            PageLayout(0, (replace(_REGION, lines=(dropped, _SECOND_LINE)),), ()),
            *_LINES.pages[1:],
        ),
    )
    with pytest.raises(FidelityError) as raised:
        check_stage(
            FidelityBoundary.STRUCTURE, lines_without_alpha, make_blocks(_LINES)
        )
    assert raised.value.missing == frozendict()
    assert raised.value.invented == frozendict({"Alpha": 1})


# run, on a book folder of its own


_PDF_BYTES = b"%PDF-1.4 a stand-in: structure reads only its hash"
_PDF_HASH = hashlib.sha256(_PDF_BYTES).hexdigest()


def _book(root: Path) -> tuple[BookFolder, BookConfig]:
    """A book folder with pages.json and lines.json of 3 pages written by hand."""
    pdf = root / "book.pdf"
    pdf.write_bytes(_PDF_BYTES)
    folder = BookFolder(root)
    pages = PagesFile(
        source_pdf_sha256=_PDF_HASH,
        pages=tuple(
            PageInfo(
                index=index,
                width_pt=500.0,
                height_pt=700.0,
                kind=PageKind.TEXT,
                text_source=TextSource.TEXT_LAYER,
                text_layer_score=None,
                exclude_regions=(),
                blank_checked_by_ocr=False,
            )
            for index in range(3)
        ),
        ocr_audit=None,
    )
    write_pages(folder.pages_json, pages)
    write_lines(folder.lines_json, replace(_LINES, source_pdf_sha256=_PDF_HASH))
    config = BookConfig(
        pdf=pdf, title="A Book", authors=("An Author",), language=Language.EN
    )
    return folder, config


def _replace_hash(path: Path) -> None:
    stale = path.read_text(encoding="utf-8").replace(_PDF_HASH, "f" * 64)
    path.write_text(stale, encoding="utf-8")


@pytest.mark.thread_unsafe
def test_run_writes_the_blocks_of_every_region(tmp_path: Path) -> None:
    folder, config = _book(tmp_path)
    structure.run(folder, config, workers=1)
    assert read_blocks(folder.blocks_json) == BlocksFile(
        source_pdf_sha256=_PDF_HASH,
        blocks=(
            Block(
                id="b-p0000-001",
                kind=BlockKind.PARAGRAPH,
                level=None,
                spans=(Span("Alpha beta, gamma delta.", Emphasis.NONE, None),),
                figure=None,
                origin=(Origin(0, Box(40, 100, 130, 132)),),
            ),
            Block(
                id="b-p0002-001",
                kind=BlockKind.PARAGRAPH,
                level=None,
                spans=(Span("gamma delta.", Emphasis.NONE, None),),
                figure=None,
                origin=(Origin(2, Box(40, 120, 130, 132)),),
            ),
        ),
        notes=(),
        removals=(),
        word_changes=(),
        page_numbers=(),
    )


@pytest.mark.thread_unsafe
def test_run_with_a_config_of_another_pdf_names_analyze(tmp_path: Path) -> None:
    folder, config = _book(tmp_path)
    other_pdf = tmp_path / "other.pdf"
    other_pdf.write_bytes(b"%PDF-1.4 another book")
    with pytest.raises(InputFileError, match=r"pages\.json.*galley2epub analyze"):
        structure.run(folder, replace(config, pdf=other_pdf), workers=1)
    assert not folder.blocks_json.exists()


@pytest.mark.thread_unsafe
def test_run_with_a_pages_json_of_another_pdf_names_analyze(tmp_path: Path) -> None:
    folder, config = _book(tmp_path)
    write_blocks(folder.blocks_json, make_blocks(_LINES, workers=1))
    _replace_hash(folder.pages_json)
    with pytest.raises(InputFileError, match=r"pages\.json.*galley2epub analyze"):
        structure.run(folder, config, workers=1)
    assert not folder.blocks_json.exists()


@pytest.mark.thread_unsafe
def test_run_with_a_lines_json_of_another_pdf_names_layout(tmp_path: Path) -> None:
    folder, config = _book(tmp_path)
    _replace_hash(folder.lines_json)
    with pytest.raises(InputFileError, match=r"lines\.json.*galley2epub layout"):
        structure.run(folder, config, workers=1)
    assert not folder.blocks_json.exists()


@pytest.mark.thread_unsafe
def test_run_that_loses_a_word_raises_and_writes_no_blocks_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder, config = _book(tmp_path)

    def make_blocks_losing_a_word(lines: LinesFile, *, workers: int) -> BlocksFile:
        blocks = make_blocks(lines, workers=workers)
        first = blocks.blocks[0]
        shorter = replace(
            first,
            spans=(replace(first.spans[0], text=first.spans[0].text.split(" ", 1)[1]),),
        )
        return replace(blocks, blocks=(shorter, *blocks.blocks[1:]))

    monkeypatch.setattr(structure, "make_blocks", make_blocks_losing_a_word)
    with pytest.raises(FidelityError):
        structure.run(folder, config, workers=1)
    assert not folder.blocks_json.exists()
