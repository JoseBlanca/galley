"""Tests of galley.model: the formats, their files and the hashes (spec section 3)."""

import hashlib
import json
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

import pytest

from galley.errors import InputFileError
from galley.model import (
    Block,
    BlockKind,
    BlocksFile,
    Box,
    ChangeReason,
    Emphasis,
    Figure,
    Line,
    LinesFile,
    Note,
    OcrAudit,
    OcrVerdict,
    Origin,
    PageInfo,
    PageKind,
    PageLayout,
    PageNumber,
    PageNumberPosition,
    PagesFile,
    PageWords,
    Region,
    Removal,
    RemovalReason,
    SampledPage,
    Span,
    TextSource,
    Word,
    WordChange,
    WordsFile,
    block_sha256,
    block_text,
    check_source_pdf,
    pdf_sha256,
    read_blocks,
    read_lines,
    read_pages,
    read_words,
    write_blocks,
    write_lines,
    write_pages,
    write_words,
)

SHA = "a" * 64

PAGES = PagesFile(
    source_pdf_sha256=SHA,
    pages=(
        PageInfo(
            index=0,
            width_pt=376.128,
            height_pt=612.0,
            kind=PageKind.TEXT,
            text_source=TextSource.TEXT_LAYER,
            text_layer_score=0.93,
            exclude_regions=(Box(240.0, 620.0, 252.0, 632.0),),
            blank_checked_by_ocr=False,
        ),
        PageInfo(
            index=1,
            width_pt=376.128,
            height_pt=612.0,
            kind=PageKind.BLANK,
            text_source=TextSource.NONE,
            text_layer_score=None,
            exclude_regions=(),
            blank_checked_by_ocr=True,
        ),
    ),
    ocr_audit=OcrAudit(
        sampled=(
            SampledPage(page_index=0, layer_score=0.93, tesseract_score=0.9),
            SampledPage(page_index=4, layer_score=0.88, tesseract_score=0.91),
        ),
        verdict=OcrVerdict.LAYER_DOUBTFUL,
    ),
)

WORDS = WordsFile(
    source_pdf_sha256=SHA,
    pages=(
        PageWords(
            index=0,
            text_source=TextSource.TEXT_LAYER,
            words=(
                Word(
                    text="Ramses", box=Box(50.5, 80.25, 90.0, 92.0), ocr_confidence=None
                ),
                Word(
                    text="über", box=Box(95.0, 80.25, 120.0, 92.0), ocr_confidence=None
                ),
            ),
            figures=(),
        ),
        PageWords(
            index=1,
            text_source=TextSource.OCR,
            words=(
                Word(
                    text="Kadesh", box=Box(10.0, 20.0, 60.0, 32.0), ocr_confidence=91.5
                ),
            ),
            figures=(
                Figure(
                    box=Box(30.0, 40.0, 300.0, 500.0),
                    image="images/p0001-1.png",
                    dpi=300,
                ),
            ),
        ),
    ),
    removals=(
        Removal(
            page_index=0,
            box=Box(241.68, 622.509, 249.07648, 629.509),
            text="81",
            reason=RemovalReason.EXCLUDED_REGION,
        ),
    ),
)

LINES = LinesFile(
    source_pdf_sha256=SHA,
    pages=(
        PageLayout(
            index=0,
            regions=(
                Region(
                    box=Box(50.5, 80.25, 120.0, 92.0),
                    lines=(
                        Line(
                            box=Box(50.5, 80.25, 120.0, 92.0),
                            words=(
                                Word(
                                    text="Ramses",
                                    box=Box(50.5, 80.25, 90.0, 92.0),
                                    ocr_confidence=None,
                                ),
                                Word(
                                    text="über",
                                    box=Box(95.0, 80.25, 120.0, 92.0),
                                    ocr_confidence=None,
                                ),
                            ),
                        ),
                    ),
                ),
            ),
            figures=(
                Figure(
                    box=Box(30.0, 40.0, 300.0, 500.0),
                    image="images/p0000-1.png",
                    dpi=300,
                ),
            ),
        ),
    ),
)

ORIGIN = Origin(page_index=3, box=Box(50.0, 100.0, 300.0, 200.0))

BLOCKS = BlocksFile(
    source_pdf_sha256=SHA,
    blocks=(
        Block(
            id="b-p0003-001",
            kind=BlockKind.HEADING,
            level=1,
            spans=(Span(text="The Battle", emphasis=Emphasis.NONE, note_ref=None),),
            figure=None,
            origin=(ORIGIN,),
        ),
        Block(
            id="b-p0003-002",
            kind=BlockKind.PARAGRAPH,
            level=None,
            spans=(
                Span(
                    text="the cities of Greece,", emphasis=Emphasis.NONE, note_ref=None
                ),
                Span(text="1", emphasis=Emphasis.NONE, note_ref="n-p0003-001"),
                Span(text=" and Egypt", emphasis=Emphasis.NONE, note_ref=None),
            ),
            figure=None,
            origin=(ORIGIN, Origin(page_index=4, box=Box(50.0, 60.0, 300.0, 90.0))),
        ),
        Block(
            id="b-p0004-001",
            kind=BlockKind.FIGURE,
            level=None,
            spans=(),
            figure="images/p0004-1.png",
            origin=(Origin(page_index=4, box=Box(30.0, 100.0, 300.0, 500.0)),),
        ),
    ),
    notes=(
        Note(
            id="n-p0003-001",
            marker="1",
            blocks=(
                Block(
                    id="b-p0003-003",
                    kind=BlockKind.PARAGRAPH,
                    level=None,
                    spans=(
                        Span(
                            text="Herodotus, ii. 4.",
                            emphasis=Emphasis.NONE,
                            note_ref=None,
                        ),
                    ),
                    figure=None,
                    origin=(ORIGIN,),
                ),
                Block(
                    id="b-p0003-004",
                    kind=BlockKind.PARAGRAPH,
                    level=None,
                    spans=(
                        Span(
                            text="See also Strabo.",
                            emphasis=Emphasis.NONE,
                            note_ref=None,
                        ),
                    ),
                    figure=None,
                    origin=(ORIGIN,),
                ),
            ),
            origin=(ORIGIN,),
            referenced=True,
        ),
    ),
    removals=(
        Removal(
            page_index=3,
            box=Box(180.0, 20.0, 200.0, 30.0),
            text="47",
            reason=RemovalReason.PAGE_NUMBER,
        ),
    ),
    word_changes=(
        WordChange(
            page_index=3,
            before=("Greece,1",),
            after=("Greece,", "1"),
            reason=ChangeReason.NOTE_MARKER,
        ),
    ),
    page_numbers=(
        PageNumber(page_index=3, text="47", position=PageNumberPosition.HEAD),
    ),
)

FILES: list[tuple[str, object, Callable[..., None], Callable[[Path], object]]] = [
    ("pages.json", PAGES, write_pages, read_pages),
    ("words.json", WORDS, write_words, read_words),
    ("lines.json", LINES, write_lines, read_lines),
    ("blocks.json", BLOCKS, write_blocks, read_blocks),
]
FILE_IDS = [name for name, *_ in FILES]


@pytest.mark.parametrize(("name", "value", "write", "read"), FILES, ids=FILE_IDS)
def test_file_written_and_read_back_is_equal(
    tmp_path: Path,
    name: str,
    value: object,
    write: Callable[..., None],
    read: Callable[[Path], object],
) -> None:
    path = tmp_path / name
    write(path, value)
    assert read(path) == value


@pytest.mark.parametrize(("name", "value", "write", "read"), FILES, ids=FILE_IDS)
def test_file_written_twice_has_the_same_bytes(
    tmp_path: Path,
    name: str,
    value: object,
    write: Callable[..., None],
    read: Callable[[Path], object],
) -> None:
    first = tmp_path / "first" / name
    second = tmp_path / "second" / name
    first.parent.mkdir()
    second.parent.mkdir()
    write(first, value)
    write(second, read(first))
    assert first.read_bytes() == second.read_bytes()


def test_pages_json_is_written_in_field_order_with_indent_one(tmp_path: Path) -> None:
    path = tmp_path / "pages.json"
    write_pages(path, PAGES)
    text = path.read_text(encoding="utf-8")
    assert text.startswith('{\n "format_version": 1,\n "source_pdf_sha256": "aaaa')
    assert text.endswith("}\n")
    assert list(json.loads(text)) == [
        "format_version",
        "source_pdf_sha256",
        "pages",
        "ocr_audit",
    ]
    assert list(json.loads(text)["pages"][0]) == [
        "index",
        "width_pt",
        "height_pt",
        "kind",
        "text_source",
        "text_layer_score",
        "exclude_regions",
        "blank_checked_by_ocr",
    ]


def test_words_json_keeps_non_ascii_characters(tmp_path: Path) -> None:
    path = tmp_path / "words.json"
    write_words(path, WORDS)
    assert '"text": "über"' in path.read_text(encoding="utf-8")


def test_ocr_audit_none_is_written_as_null_and_read_back(tmp_path: Path) -> None:
    path = tmp_path / "pages.json"
    pages = PagesFile(source_pdf_sha256=SHA, pages=PAGES.pages, ocr_audit=None)
    write_pages(path, pages)
    assert json.loads(path.read_text(encoding="utf-8"))["ocr_audit"] is None
    assert read_pages(path) == pages


def test_box_is_written_as_a_list_of_four_numbers(tmp_path: Path) -> None:
    path = tmp_path / "words.json"
    write_words(path, WORDS)
    removal = json.loads(path.read_text(encoding="utf-8"))["removals"][0]
    assert removal["box"] == [241.68, 622.509, 249.07648, 629.509]


def test_enum_is_written_as_its_string(tmp_path: Path) -> None:
    path = tmp_path / "words.json"
    write_words(path, WORDS)
    content = json.loads(path.read_text(encoding="utf-8"))
    assert content["removals"][0]["reason"] == "excluded_region"
    assert content["pages"][0]["text_source"] == "text_layer"


def test_integer_coordinates_are_read_as_floats(tmp_path: Path) -> None:
    path = tmp_path / "words.json"
    write_words(path, WORDS)
    content = json.loads(path.read_text(encoding="utf-8"))
    content["removals"][0]["box"] = [241, 622, 249, 629]
    path.write_text(json.dumps(content), encoding="utf-8")
    box = read_words(path).removals[0].box
    assert box == Box(241.0, 622.0, 249.0, 629.0)
    assert all(
        type(coordinate) is float
        for coordinate in (box.x0, box.top, box.x1, box.bottom)
    )


def test_pdf_sha256_is_the_hash_of_the_bytes(tmp_path: Path) -> None:
    pdf = tmp_path / "book.pdf"
    pdf.write_bytes(b"%PDF-1.4 not really")
    assert pdf_sha256(pdf) == hashlib.sha256(b"%PDF-1.4 not really").hexdigest()


def test_check_source_pdf_with_the_same_hash_passes(tmp_path: Path) -> None:
    check_source_pdf(tmp_path / "words.json", SHA, SHA)


def test_check_source_pdf_with_another_hash_names_the_file_and_the_stage(
    tmp_path: Path,
) -> None:
    with pytest.raises(InputFileError, match=r"words\.json") as caught:
        check_source_pdf(tmp_path / "words.json", SHA, "b" * 64)
    assert "galley2epub extract" in str(caught.value)


def test_block_text_concatenates_the_spans() -> None:
    assert block_text(BLOCKS.blocks[1]) == "the cities of Greece,1 and Egypt"


def test_block_sha256_is_the_first_12_hex_digits_of_the_text_hash() -> None:
    block = Block(
        id="b-p0000-001",
        kind=BlockKind.PARAGRAPH,
        level=None,
        spans=(
            Span(text="Ramses ", emphasis=Emphasis.NONE, note_ref=None),
            Span(text="über alles", emphasis=Emphasis.NONE, note_ref=None),
        ),
        figure=None,
        origin=(),
    )
    expected = hashlib.sha256("Ramses über alles".encode()).hexdigest()[:12]
    assert block_sha256(block) == expected
    assert len(block_sha256(block)) == 12


def test_box_of_integers_is_written_as_the_equal_box_of_floats(tmp_path: Path) -> None:
    removal = WORDS.removals[0]
    of_floats = WordsFile(
        source_pdf_sha256=SHA,
        pages=(),
        removals=(replace(removal, box=Box(241.0, 622.0, 249.0, 629.0)),),
    )
    of_integers = WordsFile(
        source_pdf_sha256=SHA,
        pages=(),
        removals=(replace(removal, box=Box(241, 622, 249, 629)),),
    )
    write_words(tmp_path / "floats.json", of_floats)
    write_words(tmp_path / "integers.json", of_integers)
    assert (tmp_path / "floats.json").read_bytes() == (
        tmp_path / "integers.json"
    ).read_bytes()
