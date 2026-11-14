"""Tests of galley.structure (spec section 7, "structure" and "Their tests").

Every value is written by hand: structure's tests need no output of layout.
The excerpt tests of structure are in work package 4.
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
    PagesFile,
    Region,
    Span,
    TextSource,
    Word,
    read_blocks,
    write_blocks,
    write_lines,
    write_pages,
)
from galley.structure import make_blocks, page_blocks


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


# page_blocks


def test_region_of_two_lines_gives_one_paragraph_of_its_words() -> None:
    page = PageLayout(12, (_REGION,), ())
    assert page_blocks(page) == (
        _paragraph("b-p0012-001", "Alpha beta, gamma delta.", 12, _REGION.box),
    )


def test_page_with_no_region_gives_no_block() -> None:
    assert page_blocks(PageLayout(3, (), ())) == ()


def test_second_region_of_a_page_gives_the_block_id_002() -> None:
    lower = Region(
        Box(40, 300, 80, 312),
        (Line(Box(40, 300, 80, 312), (_word("Omega", 40, 300, 80, 312),)),),
    )
    page = PageLayout(7, (_REGION, lower), ())
    assert page_blocks(page) == (
        _paragraph("b-p0007-001", "Alpha beta, gamma delta.", 7, _REGION.box),
        _paragraph("b-p0007-002", "Omega", 7, lower.box),
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
    assert make_blocks(_LINES) == BlocksFile(
        source_pdf_sha256=_HASH,
        blocks=(
            _paragraph("b-p0000-001", "Alpha beta, gamma delta.", 0, _REGION.box),
            _paragraph("b-p0002-001", "gamma delta.", 2, _REGION.box),
        ),
        notes=(),
        removals=(),
        word_changes=(),
        page_numbers=(),
    )


# The fidelity check at the structure boundary


def test_fidelity_check_passes_on_the_blocks_of_hand_made_lines() -> None:
    check_stage(FidelityBoundary.STRUCTURE, _LINES, make_blocks(_LINES))


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
                origin=(Origin(2, Box(40, 100, 130, 132)),),
            ),
        ),
        notes=(),
        removals=(),
        word_changes=(),
        page_numbers=(),
    )


@pytest.mark.thread_unsafe
def test_run_with_a_pages_json_of_another_pdf_names_analyze(tmp_path: Path) -> None:
    folder, config = _book(tmp_path)
    write_blocks(folder.blocks_json, make_blocks(_LINES))
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

    def make_blocks_losing_a_word(lines: LinesFile) -> BlocksFile:
        blocks = make_blocks(lines)
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
