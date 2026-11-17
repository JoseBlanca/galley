"""Tests of galley.model: the formats, their files and the hashes (spec section 3)."""

import hashlib
import json
import math
import re
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import pytest

from galley import model
from galley.config import Language, OcrMode
from galley.errors import EditError, InputFileError
from galley.model import (
    Block,
    BlockKind,
    BlocksFile,
    Box,
    ChangeReason,
    Edit,
    Emphasis,
    Figure,
    Line,
    LinesFile,
    Note,
    NoteKind,
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
    Reread,
    RereadKind,
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
    read_checked_input,
    read_checked_pages,
    read_edits,
    read_lines,
    read_pages,
    read_words,
    write_blocks,
    write_edits,
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
    rereads=(
        Reread(
            page_index=0,
            kind=RereadKind.MARGIN_NOTE,
            box=Box(10.0, 80.0, 46.5, 96.0),
            layer_words=(
                Word(text="Ra-", box=Box(12.0, 82.0, 30.0, 90.0), ocr_confidence=None),
            ),
            ocr_words=(
                Word(
                    text="Rameses", box=Box(12.0, 82.5, 44.0, 90.5), ocr_confidence=88.0
                ),
            ),
            layer_score=-1,
            ocr_score=1,
            kept=True,
            dropped_junk_count=0,
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
            label="CHAPTER III.",
            spans=(Span(text="The Battle", emphasis=Emphasis.NONE, note_ref=None),),
            figure=None,
            origin=(ORIGIN,),
        ),
        Block(
            id="b-p0003-002",
            kind=BlockKind.PARAGRAPH,
            level=None,
            label=None,
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
            label=None,
            spans=(),
            figure="images/p0004-1.png",
            origin=(Origin(page_index=4, box=Box(30.0, 100.0, 300.0, 500.0)),),
        ),
    ),
    notes=(
        Note(
            id="n-p0003-001",
            kind=NoteKind.FOOTNOTE,
            marker="1",
            blocks=(
                Block(
                    id="b-p0003-003",
                    kind=BlockKind.PARAGRAPH,
                    level=None,
                    label=None,
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
                    label=None,
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

FILES: tuple[tuple[str, object, Callable[..., None], Callable[[Path], object]], ...] = (
    ("pages.json", PAGES, write_pages, read_pages),
    ("words.json", WORDS, write_words, read_words),
    ("lines.json", LINES, write_lines, read_lines),
    ("blocks.json", BLOCKS, write_blocks, read_blocks),
)
FILE_IDS = tuple(name for name, *_ in FILES)


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
    assert text.startswith('{\n "format_version": 2,\n "source_pdf_sha256": "aaaa')
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
    check_source_pdf(tmp_path / "words.json", SHA, expected_pdf_sha256=SHA)


def test_check_source_pdf_with_another_hash_names_the_file_and_the_stage(
    tmp_path: Path,
) -> None:
    with pytest.raises(InputFileError, match=r"words\.json") as caught:
        check_source_pdf(tmp_path / "words.json", SHA, expected_pdf_sha256="b" * 64)
    assert "galley2epub extract" in str(caught.value)


def _checked_folder(root: Path, pdf_bytes: bytes) -> tuple[Path, Path, Path]:
    """book.pdf, which holds `%PDF-1.4 the book`, and pages.json and
    lines.json made from a PDF whose bytes are `pdf_bytes`."""
    pdf = root / "book.pdf"
    pdf.write_bytes(b"%PDF-1.4 the book")
    sha = hashlib.sha256(pdf_bytes).hexdigest()
    pages_json = root / "pages.json"
    lines_json = root / "lines.json"
    write_pages(pages_json, replace(PAGES, source_pdf_sha256=sha))
    write_lines(lines_json, replace(LINES, source_pdf_sha256=sha))
    return pdf, pages_json, lines_json


def test_read_checked_input_of_the_same_pdf_returns_both_files(
    tmp_path: Path,
) -> None:
    pdf, pages_json, lines_json = _checked_folder(tmp_path, b"%PDF-1.4 the book")
    sha = hashlib.sha256(b"%PDF-1.4 the book").hexdigest()
    assert read_checked_pages(pages_json, pdf) == replace(PAGES, source_pdf_sha256=sha)
    assert read_checked_input(pages_json, pdf, lines_json, read_lines) == (
        replace(PAGES, source_pdf_sha256=sha),
        replace(LINES, source_pdf_sha256=sha),
    )


def test_read_checked_input_with_pages_json_of_another_pdf_names_analyze(
    tmp_path: Path,
) -> None:
    pdf, pages_json, lines_json = _checked_folder(tmp_path, b"%PDF-1.4 another")
    with pytest.raises(InputFileError, match=r"pages\.json.*galley2epub analyze"):
        read_checked_pages(pages_json, pdf)
    with pytest.raises(InputFileError, match=r"pages\.json.*galley2epub analyze"):
        read_checked_input(pages_json, pdf, lines_json, read_lines)


def test_read_checked_input_with_an_input_of_another_pdf_names_its_stage(
    tmp_path: Path,
) -> None:
    pdf, pages_json, lines_json = _checked_folder(tmp_path, b"%PDF-1.4 the book")
    write_lines(lines_json, replace(LINES, source_pdf_sha256="b" * 64))
    with pytest.raises(InputFileError, match=r"lines\.json.*galley2epub layout"):
        read_checked_input(pages_json, pdf, lines_json, read_lines)


def test_block_text_concatenates_the_spans() -> None:
    assert block_text(BLOCKS.blocks[1]) == "the cities of Greece,1 and Egypt"


def test_block_sha256_is_the_first_12_hex_digits_of_the_text_hash() -> None:
    block = Block(
        id="b-p0000-001",
        kind=BlockKind.PARAGRAPH,
        level=None,
        label=None,
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


# Reading checks everything (spec section 3, "Reading checks everything").

type JsonPath = tuple[str | int, ...]


def _written(tmp_path: Path, name: str) -> Path:
    """The file `name` written from its value of FILES."""
    path = tmp_path / name
    for file_name, value, write, _read in FILES:
        if file_name == name:
            write(path, value)
    return path


def _set(path: Path, json_path: JsonPath, value: object) -> None:
    """Sets the value at `json_path` of the JSON file at `path`."""
    content = json.loads(path.read_text(encoding="utf-8"))
    parent = content
    for key in json_path[:-1]:
        parent = parent[key]
    parent[json_path[-1]] = value
    path.write_text(json.dumps(content), encoding="utf-8")


def _delete(path: Path, json_path: JsonPath) -> None:
    """Deletes the value at `json_path` of the JSON file at `path`."""
    content = json.loads(path.read_text(encoding="utf-8"))
    parent = content
    for key in json_path[:-1]:
        parent = parent[key]
    del parent[json_path[-1]]
    path.write_text(json.dumps(content), encoding="utf-8")


READERS = frozendict(
    {
        "pages.json": read_pages,
        "words.json": read_words,
        "lines.json": read_lines,
        "blocks.json": read_blocks,
    }
)
NAMES = tuple(READERS)

WRITING_STAGE = frozendict(
    {
        "pages.json": "analyze",
        "words.json": "extract",
        "lines.json": "layout",
        "blocks.json": "structure",
    }
)

# A field of each file whose value is a Word's box, or the nearest thing.
SOME_BOX: frozendict[str, JsonPath] = frozendict(
    {
        "pages.json": ("pages", 0, "exclude_regions", 0),
        "words.json": ("pages", 0, "words", 1, "box"),
        "lines.json": ("pages", 0, "regions", 0, "lines", 0, "words", 1, "box"),
        "blocks.json": ("blocks", 0, "origin", 0, "box"),
    }
)
SOME_OBJECT: frozendict[str, JsonPath] = frozendict(
    {
        "pages.json": ("pages", 1),
        "words.json": ("pages", 0, "words", 1),
        "lines.json": ("pages", 0, "regions", 0, "lines", 0, "words", 1),
        "blocks.json": ("notes", 0, "blocks", 1, "spans", 0),
    }
)
SOME_ENUM: frozendict[str, JsonPath] = frozendict(
    {
        "pages.json": ("pages", 0, "kind"),
        "words.json": ("pages", 1, "text_source"),
        "lines.json": ("rereads", 0, "kind"),
        "blocks.json": ("blocks", 0, "kind"),
    }
)


def _dotted(json_path: JsonPath) -> str:
    text = ""
    for key in json_path:
        text += f"[{key}]" if isinstance(key, int) else (f".{key}" if text else key)
    return text


@pytest.mark.parametrize("name", NAMES)
def test_missing_file_names_the_stage_that_writes_it(tmp_path: Path, name: str) -> None:
    with pytest.raises(InputFileError, match=re.escape(name)) as caught:
        READERS[name](tmp_path / name)
    assert f"galley2epub {WRITING_STAGE[name]}" in str(caught.value)


@pytest.mark.parametrize("name", NAMES)
def test_truncated_file_names_the_line_and_column(tmp_path: Path, name: str) -> None:
    path = _written(tmp_path, name)
    text = path.read_text(encoding="utf-8")
    path.write_text(text[: len(text) // 2], encoding="utf-8")
    with pytest.raises(InputFileError, match=re.escape(name)) as caught:
        READERS[name](path)
    assert re.search(r"line \d+, column \d+", str(caught.value))


# For each file, a format_version this galley does not read, and the one it
# reads. Every file is at 2: blocks.json since the second plan of
# structure, the others since the plan clean-text; the old version 1 is the
# case the owner meets (architecture section 8).
UNSUPPORTED_VERSION: frozendict[str, tuple[int, int]] = frozendict(
    {
        "pages.json": (1, 2),
        "words.json": (1, 2),
        "lines.json": (1, 2),
        "blocks.json": (1, 2),
    }
)


@pytest.mark.parametrize("name", NAMES)
def test_unsupported_format_version_names_both_versions(
    tmp_path: Path, name: str
) -> None:
    unsupported, current = UNSUPPORTED_VERSION[name]
    path = _written(tmp_path, name)
    _set(path, ("format_version",), unsupported)
    with pytest.raises(InputFileError, match=re.escape(name)) as caught:
        READERS[name](path)
    assert f"is format version {unsupported};" in str(caught.value)
    assert f"this galley reads format version {current}" in str(caught.value)
    assert str(caught.value).endswith(
        f"; run `galley2epub {WRITING_STAGE[name]}` again"
    )


@pytest.mark.parametrize("version", [0, True])
def test_format_version_0_or_true_is_an_error(tmp_path: Path, version: object) -> None:
    path = _written(tmp_path, "pages.json")
    _set(path, ("format_version",), version)
    with pytest.raises(InputFileError, match="format version 2"):
        read_pages(path)


@pytest.mark.parametrize("name", NAMES)
def test_missing_format_version_is_an_error(tmp_path: Path, name: str) -> None:
    path = _written(tmp_path, name)
    _delete(path, ("format_version",))
    with pytest.raises(InputFileError, match="format_version"):
        READERS[name](path)


def test_format_version_that_is_not_an_integer_is_an_error(tmp_path: Path) -> None:
    path = _written(tmp_path, "words.json")
    _set(path, ("format_version",), "1")
    with pytest.raises(InputFileError, match="format_version"):
        read_words(path)


@pytest.mark.parametrize("name", NAMES)
def test_missing_box_names_its_path(tmp_path: Path, name: str) -> None:
    path = _written(tmp_path, name)
    json_path = (
        SOME_BOX[name] if name != "pages.json" else ("pages", 0, "exclude_regions")
    )
    _delete(path, json_path)
    with pytest.raises(InputFileError, match=re.escape(name)) as caught:
        READERS[name](path)
    assert f"{_dotted(json_path)}: missing" in str(caught.value)


@pytest.mark.parametrize("name", NAMES)
def test_unknown_field_names_its_path(tmp_path: Path, name: str) -> None:
    path = _written(tmp_path, name)
    json_path = (*SOME_OBJECT[name], "colour")
    _set(path, json_path, "red")
    with pytest.raises(InputFileError, match=re.escape(name)) as caught:
        READERS[name](path)
    assert _dotted(json_path) in str(caught.value)


@pytest.mark.parametrize("name", tuple(SOME_ENUM))
def test_enum_value_that_is_not_a_member_names_its_path(
    tmp_path: Path, name: str
) -> None:
    path = _written(tmp_path, name)
    _set(path, SOME_ENUM[name], "cover")
    with pytest.raises(InputFileError, match=re.escape(name)) as caught:
        READERS[name](path)
    assert _dotted(SOME_ENUM[name]) in str(caught.value)
    assert "'cover'" in str(caught.value) or '"cover"' in str(caught.value)


@pytest.mark.parametrize("numbers", [[1.0, 2.0, 3.0], [1.0, 2.0, 3.0, 4.0, 5.0]])
@pytest.mark.parametrize("name", NAMES)
def test_box_of_three_or_five_numbers_names_its_path(
    tmp_path: Path, name: str, numbers: list[float]
) -> None:
    path = _written(tmp_path, name)
    _set(path, SOME_BOX[name], numbers)
    with pytest.raises(InputFileError, match=re.escape(name)) as caught:
        READERS[name](path)
    assert _dotted(SOME_BOX[name]) in str(caught.value)


@pytest.mark.parametrize("coordinate", [True, "81", None])
def test_box_coordinate_that_is_not_a_number_is_an_error(
    tmp_path: Path, coordinate: object
) -> None:
    path = _written(tmp_path, "words.json")
    _set(path, ("removals", 0, "box", 2), coordinate)
    with pytest.raises(InputFileError, match=re.escape("removals[0].box")):
        read_words(path)


@pytest.mark.parametrize(
    ("json_path", "value"),
    [
        (("pages", 0, "index"), "0"),
        (("pages", 0, "index"), 0.5),
        (("pages", 0, "index"), True),
        (("pages", 0, "words", 0, "text"), 7),
        (("pages", 1, "words", 0, "ocr_confidence"), True),
        (("pages", 0, "words"), {"text": "x"}),
        (("removals", 0), ["page_index"]),
        (("source_pdf_sha256",), None),
    ],
)
def test_value_of_the_wrong_json_type_names_its_path(
    tmp_path: Path, json_path: JsonPath, value: object
) -> None:
    path = _written(tmp_path, "words.json")
    _set(path, json_path, value)
    with pytest.raises(InputFileError, match=re.escape(_dotted(json_path))):
        read_words(path)


def test_top_level_that_is_not_an_object_is_an_error(tmp_path: Path) -> None:
    path = tmp_path / "lines.json"
    path.write_text("[1, 2]\n", encoding="utf-8")
    with pytest.raises(InputFileError, match=r"lines\.json"):
        read_lines(path)


def test_file_that_is_not_utf8_is_an_error(tmp_path: Path) -> None:
    path = tmp_path / "lines.json"
    path.write_bytes(b'{"format_version": 1, "x": "\xff"}')
    with pytest.raises(InputFileError, match=r"lines\.json"):
        read_lines(path)


@pytest.mark.parametrize(
    ("json_path", "value", "expected_path"),
    [
        (
            ("pages", 1, "blank_checked_by_ocr"),
            None,
            "pages[1].blank_checked_by_ocr: missing",
        ),
        (("pages", 1, "blank_checked_by_ocr"), 0, "pages[1].blank_checked_by_ocr"),
        (("ocr_audit", "verdict"), "redo", "ocr_audit.verdict"),
        (
            ("ocr_audit", "sampled", 0, "tesseract_score"),
            None,
            "ocr_audit.sampled[0].tesseract_score: missing",
        ),
    ],
    ids=[
        "blank_checked_missing",
        "blank_checked_zero",
        "verdict_redo",
        "tesseract_score_missing",
    ],
)
def test_bad_pages_json_names_the_field_path(
    tmp_path: Path, json_path: JsonPath, value: object, expected_path: str
) -> None:
    path = _written(tmp_path, "pages.json")
    if value is None:
        _delete(path, json_path)
    else:
        _set(path, json_path, value)
    with pytest.raises(InputFileError, match=r"pages\.json") as caught:
        read_pages(path)
    assert expected_path in str(caught.value)


# The edits files.

EDITS = (
    Edit(
        block_id="b-p0003-002",
        block_sha256="0123456789ab",
        old="Greece,",
        new="Grèce,",
        author="owner",
        reason="the owner's spelling",
    ),
    Edit(
        block_id="b-p0003-003",
        block_sha256="ba9876543210",
        old="ii. 4",
        new="ii. 5",
        author="correct",
        reason="OCR read 5 as 4",
    ),
)


def test_edits_written_and_read_back_are_equal(tmp_path: Path) -> None:
    path = tmp_path / "owner.jsonl"
    write_edits(path, EDITS)
    assert read_edits(path) == EDITS


def test_edits_file_is_one_object_per_line_with_the_version_first(
    tmp_path: Path,
) -> None:
    path = tmp_path / "owner.jsonl"
    write_edits(path, EDITS)
    lines = path.read_text(encoding="utf-8").split("\n")
    assert lines[0] == (
        '{"format_version": 1, "block_id": "b-p0003-002", "block_sha256": "0123456789ab", '
        '"old": "Greece,", "new": "Grèce,", "author": "owner", "reason": "the owner\'s spelling"}'
    )
    assert len(lines) == 3
    assert lines[2] == ""


def test_empty_edits_file_is_no_edits(tmp_path: Path) -> None:
    path = tmp_path / "owner.jsonl"
    path.write_text("", encoding="utf-8")
    assert read_edits(path) == ()


def _edits_with_second_line(tmp_path: Path, second_line: str) -> Path:
    path = tmp_path / "owner.jsonl"
    write_edits(path, EDITS[:1])
    path.write_text(
        path.read_text(encoding="utf-8") + second_line + "\n", encoding="utf-8"
    )
    return path


def _edit_line(**changes: object) -> str:
    fields = {
        "format_version": 1,
        "block_id": "b-p0003-003",
        "block_sha256": "ba9876543210",
        "old": "ii. 4",
        "new": "ii. 5",
        "author": "correct",
        "reason": "OCR read 5 as 4",
    } | changes
    return json.dumps(
        {key: value for key, value in fields.items() if value is not None}
    )


@pytest.mark.parametrize(
    "second_line",
    [
        '{"format_version": 1, "block_id": ',
        _edit_line(old=None),
        _edit_line(format_version=2),
        _edit_line(format_version=None),
        _edit_line(colour="red"),
        _edit_line(new=5),
        "",
        "   ",
    ],
    ids=[
        "not_json",
        "lacks_old",
        "version_2",
        "lacks_version",
        "unknown_field",
        "new_not_text",
        "blank",
        "spaces",
    ],
)
def test_bad_edits_line_names_the_file_and_the_line(
    tmp_path: Path, second_line: str
) -> None:
    path = _edits_with_second_line(tmp_path, second_line)
    with pytest.raises(EditError, match=r"owner\.jsonl") as caught:
        read_edits(path)
    assert "line 2" in str(caught.value)
    if second_line.strip() == "":
        assert "blank" in str(caught.value)


def test_edits_file_that_is_not_utf8_names_the_file(tmp_path: Path) -> None:
    path = tmp_path / "owner.jsonl"
    path.write_bytes(_edit_line().encode("utf-8") + b"\n" + b'{"old": "\xff"}\n')
    with pytest.raises(EditError, match=r"owner\.jsonl") as caught:
        read_edits(path)
    assert "UTF-8" in str(caught.value)


def test_edits_file_with_a_byte_order_mark_asks_for_utf8_without_one(
    tmp_path: Path,
) -> None:
    path = tmp_path / "owner.jsonl"
    path.write_bytes(b"\xef\xbb\xbf" + _edit_line().encode("utf-8") + b"\n")
    with pytest.raises(EditError, match=r"owner\.jsonl") as caught:
        read_edits(path)
    assert "UTF-8 without a byte-order mark" in str(caught.value)


@pytest.mark.parametrize("number", [math.nan, math.inf, -math.inf])
@pytest.mark.parametrize(
    "json_path",
    [("removals", 0, "box", 2), ("pages", 1, "words", 0, "ocr_confidence")],
)
def test_number_that_is_not_finite_names_its_path(
    tmp_path: Path, number: float, json_path: JsonPath
) -> None:
    path = _written(tmp_path, "words.json")
    _set(path, json_path, number)  # json.dumps writes NaN and Infinity
    with pytest.raises(InputFileError, match=re.escape(_dotted(json_path))):
        read_words(path)


@pytest.mark.parametrize("number", [math.nan, math.inf])
def test_writer_refuses_a_number_that_is_not_finite(
    tmp_path: Path, number: float
) -> None:
    removal = replace(WORDS.removals[0], box=Box(0.0, 1.0, number, 2.0))
    with pytest.raises(ValueError, match="not JSON compliant"):
        write_words(tmp_path / "words.json", replace(WORDS, removals=(removal,)))


LONE_SURROGATE = "\udc00"


def _words_with_text(text: str) -> WordsFile:
    page = WORDS.pages[0]
    word = replace(page.words[1], text=text)
    return replace(
        WORDS, pages=(replace(page, words=(page.words[0], word)), *WORDS.pages[1:])
    )


def test_writer_given_a_surrogate_names_the_field_and_keeps_the_old_file(
    tmp_path: Path,
) -> None:
    path = tmp_path / "words.json"
    write_words(path, WORDS)
    old_bytes = path.read_bytes()
    with pytest.raises(ValueError, match=re.escape("pages[0].words[1].text")):
        write_words(path, _words_with_text(f"ü{LONE_SURROGATE}ber"))
    assert path.read_bytes() == old_bytes
    assert [child.name for child in tmp_path.iterdir()] == ["words.json"]


def test_writer_given_a_number_that_is_not_finite_keeps_the_old_file(
    tmp_path: Path,
) -> None:
    path = tmp_path / "words.json"
    write_words(path, WORDS)
    old_bytes = path.read_bytes()
    removal = replace(WORDS.removals[0], box=Box(0.0, 1.0, math.nan, 2.0))
    with pytest.raises(ValueError, match="not JSON compliant"):
        write_words(path, replace(WORDS, removals=(removal,)))
    assert path.read_bytes() == old_bytes


def test_writer_leaves_no_other_file_in_the_folder(tmp_path: Path) -> None:
    for name, value, write, _read in FILES:
        write(tmp_path / name, value)
    write_edits(tmp_path / "owner.jsonl", EDITS)
    assert sorted(child.name for child in tmp_path.iterdir()) == sorted(
        [*(name for name, *_ in FILES), "owner.jsonl"]
    )


def test_edits_writer_given_a_surrogate_names_the_edit_and_keeps_the_old_file(
    tmp_path: Path,
) -> None:
    path = tmp_path / "owner.jsonl"
    write_edits(path, EDITS)
    old_bytes = path.read_bytes()
    bad = replace(EDITS[1], new=LONE_SURROGATE)
    with pytest.raises(ValueError, match=re.escape("edits[1].new")):
        write_edits(path, (EDITS[0], bad))
    assert path.read_bytes() == old_bytes


def test_string_holding_a_surrogate_names_its_path(tmp_path: Path) -> None:
    path = _written(tmp_path, "words.json")
    _set(path, ("pages", 0, "words", 1, "text"), f"ü{LONE_SURROGATE}ber")
    assert "\\udc00" in path.read_text(encoding="utf-8")
    with pytest.raises(InputFileError, match=re.escape("pages[0].words[1].text")):
        read_words(path)


def test_edits_line_with_a_surrogate_names_the_line(tmp_path: Path) -> None:
    path = _edits_with_second_line(tmp_path, _edit_line(old=f"ii{LONE_SURROGATE}"))
    with pytest.raises(EditError, match=r"line 2") as caught:
        read_edits(path)
    assert "old" in str(caught.value)


def test_key_given_twice_names_its_path(tmp_path: Path) -> None:
    path = _written(tmp_path, "words.json")
    text = path.read_text(encoding="utf-8")
    # The second word of page 0 gets its text twice, the second one wrong.
    text = text.replace('"text": "über",', '"text": "über",\n      "text": "uber",', 1)
    path.write_text(text, encoding="utf-8")
    with pytest.raises(
        InputFileError, match=re.escape("pages[0].words[1].text")
    ) as caught:
        read_words(path)
    assert "given twice" in str(caught.value)


def test_top_level_key_given_twice_is_an_error(tmp_path: Path) -> None:
    path = _written(tmp_path, "lines.json")
    text = path.read_text(encoding="utf-8")
    text = text.replace(
        '"format_version": 2,', '"format_version": 2,\n "format_version": 2,', 1
    )
    path.write_text(text, encoding="utf-8")
    with pytest.raises(InputFileError, match="format_version") as caught:
        read_lines(path)
    assert "given twice" in str(caught.value)


def test_edits_line_with_a_key_given_twice_names_the_line(tmp_path: Path) -> None:
    line = _edit_line()[:-1] + ', "old": "ii. 6"}'
    path = _edits_with_second_line(tmp_path, line)
    with pytest.raises(EditError, match=r"line 2") as caught:
        read_edits(path)
    assert "old" in str(caught.value)
    assert "given twice" in str(caught.value)


# A frozendict with int keys is written as an object whose keys are the ints
# as strings (architecture section 8). No format has one yet, so the test
# goes through the encoder and decoder that every writer and reader uses.


@dataclass(frozen=True, slots=True)
class _ScoresByPage:
    scores: frozendict[int, Box]
    names: frozendict[str, PageKind]


SCORES = _ScoresByPage(
    scores=frozendict({12: Box(1, 2, 3, 4), 3: Box(5.0, 6.0, 7.0, 8.5)}),
    names=frozendict({"b": PageKind.PLATE, "a": PageKind.TEXT}),
)


def test_frozendict_is_written_as_an_object_and_read_back() -> None:
    content = model._encode(_ScoresByPage, SCORES)
    assert content == {
        "scores": {"3": [5.0, 6.0, 7.0, 8.5], "12": [1.0, 2.0, 3.0, 4.0]},
        "names": {"a": "text", "b": "plate"},
    }
    # The keys in their order, so that equal mappings give equal bytes.
    assert json.dumps(content).startswith('{"scores": {"3": ')
    assert model._decode(_ScoresByPage, json.loads(json.dumps(content)), "") == SCORES


@pytest.mark.parametrize("key", ["x", "01", "1.0", ""])
def test_frozendict_key_that_is_not_an_int_names_its_path(key: str) -> None:
    content = {"scores": {key: [1, 2, 3, 4]}, "names": {}}
    with pytest.raises(model._FieldError, match=re.escape("scores")):
        model._decode(_ScoresByPage, content, "")


def test_negative_zero_is_written_as_zero(tmp_path: Path) -> None:
    removal = WORDS.removals[0]
    negative = replace(
        WORDS, removals=(replace(removal, box=Box(-0.0, -0.0, 1.0, 2.0)),)
    )
    positive = replace(WORDS, removals=(replace(removal, box=Box(0.0, 0.0, 1.0, 2.0)),))
    write_words(tmp_path / "negative.json", negative)
    write_words(tmp_path / "positive.json", positive)
    assert (tmp_path / "negative.json").read_bytes() == (
        tmp_path / "positive.json"
    ).read_bytes()


def _pages_with_numbers(width_pt: float, score: float) -> PagesFile:
    page = replace(PAGES.pages[0], width_pt=width_pt, text_layer_score=score)
    return replace(PAGES, pages=(page, *PAGES.pages[1:]))


def _words_with_confidence(confidence: float) -> WordsFile:
    page = WORDS.pages[1]
    word = replace(page.words[0], ocr_confidence=confidence)
    return replace(WORDS, pages=(WORDS.pages[0], replace(page, words=(word,))))


@pytest.mark.parametrize(
    ("write", "of_integers", "of_floats"),
    [
        (write_pages, _pages_with_numbers(376, 1), _pages_with_numbers(376.0, 1.0)),
        (write_pages, _pages_with_numbers(-0.0, 0), _pages_with_numbers(0.0, 0.0)),
        (write_words, _words_with_confidence(91), _words_with_confidence(91.0)),
        (write_words, _words_with_confidence(-0.0), _words_with_confidence(0.0)),
    ],
    ids=[
        "width_and_score",
        "negative_zero_width",
        "confidence",
        "negative_zero_confidence",
    ],
)
def test_equal_numbers_in_float_fields_give_the_same_bytes(
    tmp_path: Path, write: Callable[..., None], of_integers: object, of_floats: object
) -> None:
    write(tmp_path / "integers.json", of_integers)
    write(tmp_path / "floats.json", of_floats)
    assert (tmp_path / "integers.json").read_bytes() == (
        tmp_path / "floats.json"
    ).read_bytes()


def test_edit_with_line_separators_in_its_text_is_read_back(tmp_path: Path) -> None:
    # U+2028 and U+0085 are line ends for str.splitlines, and json.dumps
    # writes them unescaped with ensure_ascii=False.
    edit = replace(EDITS[0], old=f"Greece,{chr(0x2028)}x", new=f"Grèce,{chr(0x85)}y")
    path = tmp_path / "owner.jsonl"
    write_edits(path, (edit, EDITS[1]))
    assert chr(0x2028) in path.read_text(encoding="utf-8")
    assert read_edits(path) == (edit, EDITS[1])


def test_every_enum_member_has_the_value_of_architecture_section_8() -> None:
    values = {
        enum.__name__: [member.value for member in enum]
        for enum in (
            PageKind,
            TextSource,
            OcrVerdict,
            RemovalReason,
            BlockKind,
            NoteKind,
            Emphasis,
            ChangeReason,
            PageNumberPosition,
            RereadKind,
            Language,
            OcrMode,
        )
    }
    assert values == {
        "PageKind": ["blank", "text", "plate", "excluded", "front_matter"],
        "TextSource": ["text_layer", "ocr", "none"],
        "OcrVerdict": ["layer_kept", "layer_doubtful"],
        "RemovalReason": [
            "excluded_page",
            "excluded_region",
            "front_matter",
            "running_head",
            "page_number",
            "signature_mark",
            "plate_text",
            "stray_mark",
            "guide_words",
        ],
        "BlockKind": [
            "heading",
            "paragraph",
            "quote",
            "verse",
            "chapter_summary",
            "figure",
            "margin_note",
            "index_entry",
        ],
        "NoteKind": ["footnote", "endnote"],
        "Emphasis": ["none"],
        "ChangeReason": [
            "hyphen_join",
            "note_marker",
            "hyphen_join_guessed",
            "hyphen_kept",
        ],
        "PageNumberPosition": ["head", "foot"],
        "RereadKind": [
            "small_print_page",
            "margin_note",
            "cut_in_note",
            "footnote_band",
        ],
        "Language": ["en", "es", "fr", "de", "it"],
        "OcrMode": ["verify", "trust", "redo"],
    }


# Files that use every member of every enum of their format, and a note
# that is not referenced.
EVERY_MEMBER_PAGES = tuple(
    replace(
        PAGES,
        pages=tuple(
            replace(
                PAGES.pages[0],
                index=index,
                kind=kind,
                text_source=tuple(TextSource)[index % len(TextSource)],
            )
            for index, kind in enumerate(PageKind)
        ),
        ocr_audit=replace(PAGES.ocr_audit, verdict=verdict)
        if PAGES.ocr_audit
        else None,
    )
    for verdict in OcrVerdict
)
EVERY_MEMBER_BLOCKS = replace(
    BLOCKS,
    blocks=tuple(
        replace(
            BLOCKS.blocks[1],
            id=f"b-p0003-{number:03}",
            kind=kind,
            # An index entry has its depth (architecture section 8).
            level=1 if kind is BlockKind.INDEX_ENTRY else None,
        )
        for number, kind in enumerate(BlockKind, start=1)
    ),
    notes=tuple(
        replace(
            BLOCKS.notes[0],
            id=f"n-p0003-{number:03}",
            kind=kind,
            referenced=False,
        )
        for number, kind in enumerate(NoteKind, start=1)
    ),
    removals=tuple(
        replace(BLOCKS.removals[0], reason=reason) for reason in RemovalReason
    ),
    word_changes=tuple(
        replace(BLOCKS.word_changes[0], reason=reason) for reason in ChangeReason
    ),
    page_numbers=tuple(
        replace(BLOCKS.page_numbers[0], position=position)
        for position in PageNumberPosition
    ),
)


@pytest.mark.parametrize("pages", EVERY_MEMBER_PAGES)
def test_pages_with_every_member_is_read_back_equal(
    tmp_path: Path, pages: PagesFile
) -> None:
    write_pages(tmp_path / "pages.json", pages)
    assert read_pages(tmp_path / "pages.json") == pages


def test_blocks_with_every_member_and_an_unreferenced_note_is_read_back_equal(
    tmp_path: Path,
) -> None:
    write_blocks(tmp_path / "blocks.json", EVERY_MEMBER_BLOCKS)
    content = json.loads((tmp_path / "blocks.json").read_text(encoding="utf-8"))
    assert content["notes"][0]["referenced"] is False
    assert read_blocks(tmp_path / "blocks.json") == EVERY_MEMBER_BLOCKS


# The second plan of structure: labels, note kinds, the new block kinds and
# removal reason, and margin notes inside a note (architecture section 8).


def _blocks_json(tmp_path: Path, blocks: BlocksFile) -> dict[str, Any]:
    """`blocks` written as blocks.json, then parsed as plain JSON."""
    write_blocks(tmp_path / "blocks.json", blocks)
    return json.loads((tmp_path / "blocks.json").read_text(encoding="utf-8"))


def test_blocks_json_is_format_version_2() -> None:
    assert model.BLOCKS_FORMAT_VERSION == 2
    assert BLOCKS.format_version == 2


def test_heading_label_is_written_after_level_and_read_back(tmp_path: Path) -> None:
    content = _blocks_json(tmp_path, BLOCKS)

    heading = content["blocks"][0]
    assert list(heading) == [
        "id",
        "kind",
        "level",
        "label",
        "spans",
        "figure",
        "origin",
    ]
    assert heading["label"] == "CHAPTER III."
    assert read_blocks(tmp_path / "blocks.json").blocks[0].label == "CHAPTER III."


def test_block_without_label_is_written_with_label_null(tmp_path: Path) -> None:
    content = _blocks_json(tmp_path, BLOCKS)

    assert content["blocks"][1]["label"] is None
    assert content["notes"][0]["blocks"][0]["label"] is None


def test_block_without_its_label_field_names_its_path(tmp_path: Path) -> None:
    write_blocks(tmp_path / "blocks.json", BLOCKS)
    _delete(tmp_path / "blocks.json", ("blocks", 1, "label"))

    with pytest.raises(InputFileError, match=re.escape("blocks[1].label: missing")):
        read_blocks(tmp_path / "blocks.json")


def test_label_that_is_not_a_string_names_its_path(tmp_path: Path) -> None:
    write_blocks(tmp_path / "blocks.json", BLOCKS)
    _set(tmp_path / "blocks.json", ("blocks", 0, "label"), 3)

    with pytest.raises(InputFileError, match=re.escape("blocks[0].label")):
        read_blocks(tmp_path / "blocks.json")


def test_note_kind_is_written_after_id_and_read_back(tmp_path: Path) -> None:
    endnote = replace(BLOCKS.notes[0], kind=NoteKind.ENDNOTE, marker="291.")
    blocks = replace(BLOCKS, notes=(endnote,))

    content = _blocks_json(tmp_path, blocks)

    assert list(content["notes"][0]) == [
        "id",
        "kind",
        "marker",
        "blocks",
        "origin",
        "referenced",
    ]
    assert content["notes"][0]["kind"] == "endnote"
    assert read_blocks(tmp_path / "blocks.json").notes == (endnote,)


def test_note_kind_that_is_not_a_member_names_its_path(tmp_path: Path) -> None:
    write_blocks(tmp_path / "blocks.json", BLOCKS)
    _set(tmp_path / "blocks.json", ("notes", 0, "kind"), "sidenote")

    with pytest.raises(InputFileError, match=re.escape("notes[0].kind")) as caught:
        read_blocks(tmp_path / "blocks.json")
    assert "footnote, endnote" in str(caught.value)


def test_note_without_its_kind_field_names_its_path(tmp_path: Path) -> None:
    write_blocks(tmp_path / "blocks.json", BLOCKS)
    _delete(tmp_path / "blocks.json", ("notes", 0, "kind"))

    with pytest.raises(InputFileError, match=re.escape("notes[0].kind: missing")):
        read_blocks(tmp_path / "blocks.json")


def test_chapter_summary_block_is_written_as_its_kind_and_read_back(
    tmp_path: Path,
) -> None:
    summary = replace(
        BLOCKS.blocks[1],
        kind=BlockKind.CHAPTER_SUMMARY,
        spans=(
            Span(
                text="Character of Henry II. \u2014 His family policy.",
                emphasis=Emphasis.NONE,
                note_ref=None,
            ),
        ),
    )
    blocks = replace(BLOCKS, blocks=(BLOCKS.blocks[0], summary))

    content = _blocks_json(tmp_path, blocks)

    assert content["blocks"][1]["kind"] == "chapter_summary"
    assert read_blocks(tmp_path / "blocks.json") == blocks


def test_verse_block_keeps_the_line_feeds_of_its_text(tmp_path: Path) -> None:
    verse = replace(
        BLOCKS.blocks[1],
        kind=BlockKind.VERSE,
        spans=(
            Span(
                text="Arma virumque cano,\nTroiae qui primus ab oris",
                emphasis=Emphasis.NONE,
                note_ref=None,
            ),
        ),
    )
    blocks = replace(BLOCKS, blocks=(verse,))

    content = _blocks_json(tmp_path, blocks)

    assert content["blocks"][0]["kind"] == "verse"
    assert content["blocks"][0]["spans"][0]["text"] == (
        "Arma virumque cano,\nTroiae qui primus ab oris"
    )
    assert block_text(read_blocks(tmp_path / "blocks.json").blocks[0]) == (
        "Arma virumque cano,\nTroiae qui primus ab oris"
    )


def test_guide_words_removal_is_written_as_its_reason_and_read_back(
    tmp_path: Path,
) -> None:
    guide_words = Removal(
        page_index=3,
        box=Box(120.0, 40.0, 260.0, 52.0),
        text="BUR CON",
        reason=RemovalReason.GUIDE_WORDS,
    )
    blocks = replace(BLOCKS, removals=(guide_words,))

    content = _blocks_json(tmp_path, blocks)

    assert content["removals"][0]["reason"] == "guide_words"
    assert read_blocks(tmp_path / "blocks.json").removals == (guide_words,)


def test_note_with_a_margin_note_before_its_paragraph_is_read_back(
    tmp_path: Path,
) -> None:
    # Gierke prints margin notes beside its endnotes; such a margin note is a
    # block of the note, before the note's block that holds the line.
    margin_note = Block(
        id="b-p0003-005",
        kind=BlockKind.MARGIN_NOTE,
        level=None,
        label=None,
        spans=(Span(text="Medieval Thought.", emphasis=Emphasis.NONE, note_ref=None),),
        figure=None,
        origin=(ORIGIN,),
    )
    note = replace(
        BLOCKS.notes[0],
        kind=NoteKind.ENDNOTE,
        blocks=(margin_note, *BLOCKS.notes[0].blocks),
    )
    blocks = replace(BLOCKS, notes=(note,))

    write_blocks(tmp_path / "blocks.json", blocks)

    read_back = read_blocks(tmp_path / "blocks.json")
    assert read_back == blocks
    assert tuple(block.kind for block in read_back.notes[0].blocks) == (
        BlockKind.MARGIN_NOTE,
        BlockKind.PARAGRAPH,
        BlockKind.PARAGRAPH,
    )


@pytest.mark.parametrize(
    "json_path",
    [("blocks", 1, "label"), ("notes", 0, "blocks", 1, "label")],
    ids=["body", "note"],
)
def test_label_on_a_block_that_is_not_a_heading_names_the_file_and_block(
    tmp_path: Path, json_path: JsonPath
) -> None:
    write_blocks(tmp_path / "blocks.json", BLOCKS)
    _set(tmp_path / "blocks.json", json_path, "CHAPTER IV.")

    with pytest.raises(InputFileError) as caught:
        read_blocks(tmp_path / "blocks.json")

    block_id = "b-p0003-002" if json_path[0] == "blocks" else "b-p0003-004"
    assert str(caught.value) == (
        f"{tmp_path / 'blocks.json'}: block {block_id} is a paragraph and has "
        "the label 'CHAPTER IV.'; only a heading has a label"
    )


# An index entry's depth (architecture section 8)


@pytest.mark.parametrize("depth", [None, 0])
def test_index_entry_without_a_depth_from_1_names_the_block_and_structure(
    tmp_path: Path, depth: int | None
) -> None:
    write_blocks(tmp_path / "blocks.json", EVERY_MEMBER_BLOCKS)
    position = list(BlockKind).index(BlockKind.INDEX_ENTRY)
    _set(tmp_path / "blocks.json", ("blocks", position, "level"), depth)

    with pytest.raises(InputFileError) as caught:
        read_blocks(tmp_path / "blocks.json")

    assert str(caught.value) == (
        f"{tmp_path / 'blocks.json'}: block b-p0003-{position + 1:03} is an index "
        f"entry with the depth {depth!r}, not one from 1 (architecture section 8); "
        "a blocks.json written before index entries had a depth needs "
        "`galley2epub structure` run again"
    )


def test_index_entry_of_depth_2_is_read_back_and_a_level_on_a_paragraph_is_refused(
    tmp_path: Path,
) -> None:
    position = list(BlockKind).index(BlockKind.INDEX_ENTRY)
    deeper = replace(
        EVERY_MEMBER_BLOCKS,
        blocks=tuple(
            replace(block, level=2) if number == position else block
            for number, block in enumerate(EVERY_MEMBER_BLOCKS.blocks)
        ),
    )
    write_blocks(tmp_path / "blocks.json", deeper)
    assert read_blocks(tmp_path / "blocks.json") == deeper

    paragraph = list(BlockKind).index(BlockKind.PARAGRAPH)
    _set(tmp_path / "blocks.json", ("blocks", paragraph, "level"), 1)
    with pytest.raises(InputFileError) as caught:
        read_blocks(tmp_path / "blocks.json")
    assert str(caught.value) == (
        f"{tmp_path / 'blocks.json'}: block b-p0003-{paragraph + 1:03} is a "
        "paragraph and has the level 1; only a heading and an index entry have one"
    )


# Where a note is written (structure spec, section 6, "Order")


@pytest.mark.parametrize(
    ("block_pages", "note_pages", "places"),
    [
        # A paragraph from page 3 to 4, then page 3's margin note: page 3's
        # and page 4's notes both go after the margin note.
        ((3, 3), (3, 4), (2, 2)),
        # A note before every block's page goes first of all.
        ((5, 6), (4,), (0,)),
        # Blocks out of page order: the last block on or before the page.
        ((2, 5, 3), (3, 4, 5), (3, 3, 3)),
        # A block without an origin is passed over, as if it were not there.
        ((1, None, 2), (1,), (1,)),
        ((), (0,), (0,)),
    ],
)
def test_note_places_counts_the_blocks_written_before_each_note(
    block_pages: tuple[int | None, ...],
    note_pages: tuple[int, ...],
    places: tuple[int, ...],
) -> None:
    assert model.note_places(block_pages, note_pages) == places


# The plan clean-text: the front matter (front-matter spec, section 3) and
# the re-reading of small print (reocr spec, section 4, "The record").


def test_pages_words_and_lines_json_are_format_version_2() -> None:
    assert (
        model.PAGES_FORMAT_VERSION,
        model.WORDS_FORMAT_VERSION,
        model.LINES_FORMAT_VERSION,
    ) == (2, 2, 2)
    assert (PAGES.format_version, WORDS.format_version, LINES.format_version) == (
        2,
        2,
        2,
    )


def test_front_matter_page_is_written_as_its_kind_and_read_back(
    tmp_path: Path,
) -> None:
    front_page = replace(
        PAGES.pages[0],
        kind=PageKind.FRONT_MATTER,
        text_source=TextSource.NONE,
        text_layer_score=0.4,
    )
    pages = replace(PAGES, pages=(front_page,))
    write_pages(tmp_path / "pages.json", pages)

    content = json.loads((tmp_path / "pages.json").read_text(encoding="utf-8"))
    assert content["pages"][0]["kind"] == "front_matter"
    assert content["pages"][0]["text_source"] == "none"
    assert read_pages(tmp_path / "pages.json") == pages


def test_front_matter_removal_is_written_as_its_reason_and_read_back(
    tmp_path: Path,
) -> None:
    # A word of a title page, dropped with the front matter.
    title_word = Removal(
        page_index=0,
        box=Box(150.0, 200.0, 230.0, 216.0),
        text="NORMANS",
        reason=RemovalReason.FRONT_MATTER,
    )
    words = replace(WORDS, removals=(title_word,))
    write_words(tmp_path / "words.json", words)

    content = json.loads((tmp_path / "words.json").read_text(encoding="utf-8"))
    assert content["removals"][0]["reason"] == "front_matter"
    assert read_words(tmp_path / "words.json").removals == (title_word,)


@pytest.mark.parametrize("name", ["pages.json", "words.json", "lines.json"])
def test_front_matter_or_reread_file_of_version_1_names_the_stage_to_run_again(
    tmp_path: Path, name: str
) -> None:
    path = _written(tmp_path, name)
    _set(path, ("format_version",), 1)

    with pytest.raises(InputFileError) as caught:
        READERS[name](path)

    assert str(caught.value) == (
        f"{path}: is format version 1; this galley reads format version 2; "
        f"run `galley2epub {WRITING_STAGE[name]}` again"
    )


def test_reread_is_written_with_its_fields_in_order_and_read_back(
    tmp_path: Path,
) -> None:
    write_lines(tmp_path / "lines.json", LINES)

    content = json.loads((tmp_path / "lines.json").read_text(encoding="utf-8"))
    assert list(content) == ["format_version", "source_pdf_sha256", "pages", "rereads"]
    assert content["rereads"] == [
        {
            "page_index": 0,
            "kind": "margin_note",
            "box": [10.0, 80.0, 46.5, 96.0],
            "layer_words": [
                {"text": "Ra-", "box": [12.0, 82.0, 30.0, 90.0], "ocr_confidence": None}
            ],
            "ocr_words": [
                {
                    "text": "Rameses",
                    "box": [12.0, 82.5, 44.0, 90.5],
                    "ocr_confidence": 88.0,
                }
            ],
            "layer_score": -1,
            "ocr_score": 1,
            "kept": True,
            "dropped_junk_count": 0,
        }
    ]
    assert read_lines(tmp_path / "lines.json") == LINES


def test_reread_of_every_kind_kept_or_not_is_read_back_equal(tmp_path: Path) -> None:
    rereads = tuple(
        replace(LINES.rereads[0], kind=kind, kept=kept)
        for kind in RereadKind
        for kept in (True, False)
    )
    lines = replace(LINES, rereads=rereads)
    write_lines(tmp_path / "lines.json", lines)

    assert read_lines(tmp_path / "lines.json") == lines


def test_lines_json_with_no_reread_is_written_as_an_empty_list(tmp_path: Path) -> None:
    lines = replace(LINES, rereads=())
    write_lines(tmp_path / "lines.json", lines)

    content = json.loads((tmp_path / "lines.json").read_text(encoding="utf-8"))
    assert content["rereads"] == []
    assert read_lines(tmp_path / "lines.json") == lines


def test_lines_json_without_its_rereads_field_names_it(tmp_path: Path) -> None:
    path = _written(tmp_path, "lines.json")
    _delete(path, ("rereads",))

    with pytest.raises(InputFileError, match=re.escape("rereads: missing")):
        read_lines(path)


@pytest.mark.parametrize(
    ("field", "value"),
    [("kept", 1), ("layer_score", 1.5), ("ocr_score", True), ("ocr_words", "x")],
)
def test_reread_field_of_the_wrong_type_names_its_path(
    tmp_path: Path, field: str, value: object
) -> None:
    path = _written(tmp_path, "lines.json")
    _set(path, ("rereads", 0, field), value)

    with pytest.raises(InputFileError, match=re.escape(f"rereads[0].{field}")):
        read_lines(path)


# The words a kept Reread replaces (reocr spec, section 4)


@pytest.mark.parametrize(
    ("middle", "under"),
    [
        ((21.0, 15.0), True),
        ((21.1, 15.0), False),
        ((9.0, 15.0), True),
        ((8.9, 15.0), False),
        ((15.0, 22.0), True),
        ((15.0, 22.1), False),
        ((15.0, 8.0), True),
        ((15.0, 7.9), False),
    ],
)
def test_layer_word_is_under_an_ocr_word_widened_2_pt_up_and_down_1_pt_across(
    middle: tuple[float, float], under: bool
) -> None:
    x, y = middle
    layer_word = Word("Moial", Box(x - 2, y - 2, x + 2, y + 2), None)
    ocr_word = Word("Moral", Box(10.0, 10.0, 20.0, 20.0), 90.0)
    assert model.is_under_ocr_word(layer_word, (ocr_word,)) is under


def _layer(text: str, x0: float, top: float) -> Word:
    return Word(text, Box(x0, top, x0 + 20, top + 8), None)


def _tesseract(text: str, x0: float, top: float) -> Word:
    return Word(text, Box(x0, top, x0 + 20, top + 8), 90.0)


def test_layer_word_under_an_ocr_word_of_another_text_is_replaced() -> None:
    layer = (_layer("Moial", 10, 100),)
    assert model.replaced_layer_words(layer, (_tesseract("Moral", 10, 100),)) == layer


def test_layer_word_off_the_box_with_the_text_of_an_ocr_word_is_replaced() -> None:
    # 10 pt below the word Tesseract read, as Gierke's layer lines lie.
    layer = (_layer("Theory.", 10, 110),)
    ocr = (_tesseract("theory", 10, 100),)
    assert model.replaced_layer_words(layer, ocr) == layer


def test_layer_word_of_the_text_of_an_ocr_word_more_than_16_pt_off_stays() -> None:
    layer = (_layer("Theory.", 10, 116.1),)
    assert model.replaced_layer_words(layer, (_tesseract("Theory.", 10, 100),)) == ()
    near = (_layer("Theory.", 10, 116.0),)
    assert model.replaced_layer_words(near, (_tesseract("Theory.", 10, 100),)) == near


def test_ocr_word_matched_under_a_layer_word_of_its_text_matches_no_other() -> None:
    # The layer read "of" twice, once over Tesseract's "of" and once off it.
    over, off = _layer("of", 10, 100), _layer("of", 60, 100)
    ocr = (_tesseract("of", 10, 100),)
    assert model.replaced_layer_words((over, off), ocr) == (over,)
    assert model.replaced_layer_words((off, over), ocr) == (over,)


def test_two_layer_words_of_one_text_take_the_nearest_ocr_words_in_turn() -> None:
    first, second = _layer("the", 10, 112), _layer("the", 70, 112)
    ocr = (_tesseract("the", 70, 105), _tesseract("the", 10, 105))
    assert model.replaced_layer_words((first, second), ocr) == (first, second)
    # Tesseract's one "the" is nearer the second.
    assert model.replaced_layer_words((first, second), ocr[:1]) == (second,)


def test_ocr_word_over_a_layer_word_of_another_text_pairs_with_no_other() -> None:
    # Domesday page 548: the layer's "dominicum," lies under Tesseract's
    # "dominieum,", and the layer's "Domini", a line above, where
    # Tesseract read only "3", is alike to it; "Domini" stays.
    domini = _layer("Domini", 10, 92)
    dominicum = _layer("dominicum,", 10, 100)
    ocr = (_tesseract("3", 60, 92), _tesseract("dominieum,", 10, 100))
    assert model.replaced_layer_words((domini, dominicum), ocr) == (dominicum,)


def test_ocr_word_over_two_layer_lines_replaces_the_words_of_the_nearer() -> None:
    # Gierke page 63: Tesseract's "146" lies between two of the layer's
    # lines "14. c", 8.2 pt apart, and both lie under its widened box.
    first = (
        Word("14.", Box(324.0, 379.7, 329.9, 386.7), None),
        Word("c", Box(332.6, 379.7, 334.7, 386.7), None),
    )
    second = (
        Word("14.", Box(323.4, 387.9, 329.5, 394.9), None),
        Word("c", Box(332.4, 387.9, 334.4, 394.9), None),
    )
    ocr = (Word("146", Box(324.5, 382.8, 336.2, 390.5), 60.0),)
    assert model.replaced_layer_words((*first, *second), ocr) == first


def test_ocr_word_over_two_layer_lines_and_a_word_overlapping_both_takes_one() -> None:
    # Stubbs' index, page 318: Tesseract's "Soca" for "Normans," lies over
    # the layer's "I43" of the line above too, and over a stray "k" whose
    # box overlaps both lines; "I43" stays.
    stray = Word("k", Box(157.6, 437.6, 161.0, 443.3), None)
    above = Word("I43", Box(165.3, 433.4, 175.9, 439.3), None)
    normans = Word("Normans,", Box(157.6, 439.8, 191.9, 446.9), None)
    ocr = (Word("Soca", Box(157.7, 434.6, 177.6, 445.9), 50.0),)
    assert model.replaced_layer_words((stray, above, normans), ocr) == (
        stray,
        normans,
    )


def test_layer_word_glued_over_two_or_three_ocr_words_is_replaced() -> None:
    # Stubbs' index, page 312: the layer's "of,96" where Tesseract read
    # "of," "96"; its middle lies between the two, under neither.
    glued = Word("of,96", Box(100.0, 50.0, 130.0, 58.0), None)
    of, ninety_six = (
        Word("of,", Box(100.5, 50.0, 110.0, 58.0), 90.0),
        Word("96", Box(122.0, 50.0, 129.5, 58.0), 90.0),
    )
    assert model.replaced_layer_words((glued,), (of, ninety_six)) == (glued,)
    # "abolition of,17," read "of," "17," by Tesseract, after "abolition".
    three = Word("of,17,", Box(100.0, 50.0, 130.0, 58.0), None)
    seventeen = Word("17,", Box(122.0, 50.0, 129.5, 58.0), 90.0)
    abolition = Word("abolition", Box(40.0, 50.0, 98.0, 58.0), 90.0)
    assert model.replaced_layer_words((three,), (abolition, of, seventeen)) == (three,)
    # Not when a Tesseract word of the group lies more than 1 pt outside its
    # box, or the group is of four words.
    outside = Word("96", Box(129.0, 50.0, 134.2, 58.0), 90.0)
    assert model.replaced_layer_words((glued,), (of, outside)) == ()
    four = Word("a,b,c,d", Box(100.0, 50.0, 130.0, 58.0), None)
    letters = tuple(
        Word(text, Box(x, 50.0, x + 1.0, 58.0), 90.0)
        for text, x in (("a,", 101.0), ("b,", 109.0), ("c,", 121.0), ("d", 128.0))
    )
    assert model.replaced_layer_words((four,), letters) == ()


def test_ocr_words_read_glued_by_the_layer_pair_with_no_other_layer_word() -> None:
    # The layer's "of," a line below may not take Tesseract's "of," that the
    # glued "of,96" holds.
    glued = Word("of,96", Box(100.0, 50.0, 130.0, 58.0), None)
    below = Word("of,", Box(100.0, 62.0, 110.0, 70.0), None)
    ocr = (
        Word("of,", Box(100.5, 50.0, 110.0, 58.0), 90.0),
        Word("96", Box(122.0, 50.0, 129.5, 58.0), 90.0),
    )
    assert model.replaced_layer_words((glued, below), ocr) == (glued,)


def test_layer_word_without_a_letter_or_digit_is_matched_only_under_a_word() -> None:
    layer = (_layer("—", 10, 110),)
    assert model.replaced_layer_words(layer, (_tesseract("—", 10, 100),)) == ()


def test_layer_word_6_pt_below_an_ocr_word_of_alike_letters_is_replaced() -> None:
    # The layer's garbled copy of a note word Tesseract read (Domesday
    # page 76): "fllght'" and "flight" have a ratio of 0.83. Its middle,
    # at 114, lies 6 pt below Tesseract's box, out of rule (a)'s reach.
    layer = (_layer("fllght'", 10, 110),)
    assert model.replaced_layer_words(layer, (_tesseract("flight.", 10, 100),)) == layer


def test_layer_word_of_letters_less_alike_than_0_6_stays() -> None:
    # "for" and "lord" have a ratio of 0.57: a body word at the column's
    # edge beside a note word (Domesday page 310).
    layer = (_layer("for", 10, 110),)
    assert model.replaced_layer_words(layer, (_tesseract("lord", 10, 100),)) == ()
    # "rega" and "regality" have a ratio of 0.67.
    alike = (_layer("rega", 10, 110),)
    assert model.replaced_layer_words(alike, (_tesseract("regality.", 10, 100),)) == (
        alike
    )


def test_layer_word_of_3_letters_alike_is_replaced_and_one_of_2_stays() -> None:
    # "tbe" and "the" have a ratio of 0.67, "th" and "the" of 0.8; rule (c)
    # takes words of 3 letters or more.
    three = (_layer("tbe", 10, 110),)
    assert model.replaced_layer_words(three, (_tesseract("the", 10, 100),)) == three
    two = (_layer("th", 10, 110),)
    assert model.replaced_layer_words(two, (_tesseract("the", 10, 100),)) == ()


def test_layer_number_of_other_digits_beside_an_ocr_number_stays() -> None:
    # A list number Tesseract did not read (Gierke page 79).
    layer = (_layer("131.", 10, 114),)
    assert model.replaced_layer_words(layer, (_tesseract("130.", 10, 100),)) == ()


def test_layer_word_of_alike_letters_more_than_16_pt_off_stays() -> None:
    layer = (_layer("fllght'", 10, 116.1),)
    assert model.replaced_layer_words(layer, (_tesseract("flight.", 10, 100),)) == ()


def test_two_alike_layer_words_and_one_ocr_word_replace_the_nearer() -> None:
    nearer, further = _layer("fllght'", 10, 110), _layer("fiight", 10, 116)
    ocr = (_tesseract("flight.", 10, 100),)
    assert model.replaced_layer_words((further, nearer), ocr) == (nearer,)


def test_ocr_word_matched_by_its_text_is_not_alike_to_another_layer_word() -> None:
    same, garbled = _layer("flight.", 10, 110), _layer("fllght'", 10, 116)
    ocr = (_tesseract("flight.", 10, 100),)
    assert model.replaced_layer_words((garbled, same), ocr) == (same,)


def _rereads_record(
    layer_words: tuple[Word, ...], ocr_words: tuple[Word, ...], *, kept: bool
) -> Reread:
    return Reread(
        page_index=0,
        kind=RereadKind.MARGIN_NOTE,
        box=Box(0.0, 0.0, 50.0, 50.0),
        layer_words=layer_words,
        ocr_words=ocr_words,
        layer_score=0,
        ocr_score=1,
        kept=kept,
        dropped_junk_count=0,
    )


def test_words_after_rereads_swap_each_kept_records_layer_words_once() -> None:
    # "of" is on the page twice, at the same place, and one is replaced.
    of = Word("of", Box(10.0, 10.0, 20.0, 20.0), None)
    moial = Word("Moial", Box(30.0, 10.0, 40.0, 20.0), None)
    body = Word("The", Box(100.0, 10.0, 120.0, 20.0), None)
    kept = _rereads_record(
        (moial, of), (Word("Moral", Box(30.0, 10.0, 40.0, 20.0), 90.0),), kept=True
    )
    not_kept = _rereads_record(
        (body,), (Word("Tbe", Box(100.0, 10.0, 120.0, 20.0), 40.0),), kept=False
    )
    after = model.words_after_rereads((body, of, moial, of), (kept, not_kept))
    assert tuple(word.text for word in after) == ("The", "of", "Moral")
