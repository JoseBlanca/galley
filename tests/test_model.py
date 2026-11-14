"""Tests of galley.model: the formats, their files and the hashes (spec section 3)."""

import hashlib
import json
import math
import re
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

import pytest

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
    check_source_pdf(tmp_path / "words.json", SHA, expected_pdf_sha256=SHA)


def test_check_source_pdf_with_another_hash_names_the_file_and_the_stage(
    tmp_path: Path,
) -> None:
    with pytest.raises(InputFileError, match=r"words\.json") as caught:
        check_source_pdf(tmp_path / "words.json", SHA, expected_pdf_sha256="b" * 64)
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


READERS = {
    "pages.json": read_pages,
    "words.json": read_words,
    "lines.json": read_lines,
    "blocks.json": read_blocks,
}
NAMES = list(READERS)

WRITING_STAGE = {
    "pages.json": "analyze",
    "words.json": "extract",
    "lines.json": "layout",
    "blocks.json": "structure",
}

# A field of each file whose value is a Word's box, or the nearest thing.
SOME_BOX: dict[str, JsonPath] = {
    "pages.json": ("pages", 0, "exclude_regions", 0),
    "words.json": ("pages", 0, "words", 1, "box"),
    "lines.json": ("pages", 0, "regions", 0, "lines", 0, "words", 1, "box"),
    "blocks.json": ("blocks", 0, "origin", 0, "box"),
}
SOME_OBJECT: dict[str, JsonPath] = {
    "pages.json": ("pages", 1),
    "words.json": ("pages", 0, "words", 1),
    "lines.json": ("pages", 0, "regions", 0, "lines", 0, "words", 1),
    "blocks.json": ("notes", 0, "blocks", 1, "spans", 0),
}
SOME_ENUM: dict[str, JsonPath] = {
    "pages.json": ("pages", 0, "kind"),
    "words.json": ("pages", 1, "text_source"),
    "blocks.json": ("blocks", 0, "kind"),
}


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


@pytest.mark.parametrize("name", NAMES)
def test_format_version_2_names_both_versions(tmp_path: Path, name: str) -> None:
    path = _written(tmp_path, name)
    _set(path, ("format_version",), 2)
    with pytest.raises(InputFileError, match=re.escape(name)) as caught:
        READERS[name](path)
    assert "format version 2" in str(caught.value)
    assert "format version 1" in str(caught.value)


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


@pytest.mark.parametrize("name", list(SOME_ENUM))
def test_enum_value_that_is_not_a_member_names_its_path(
    tmp_path: Path, name: str
) -> None:
    path = _written(tmp_path, name)
    _set(path, SOME_ENUM[name], "cover")
    with pytest.raises(InputFileError, match=re.escape(name)) as caught:
        READERS[name](path)
    assert _dotted(SOME_ENUM[name]) in str(caught.value)
    assert "'cover'" in str(caught.value) or '"cover"' in str(caught.value)


@pytest.mark.parametrize("name", NAMES)
def test_box_of_three_numbers_names_its_path(tmp_path: Path, name: str) -> None:
    path = _written(tmp_path, name)
    _set(path, SOME_BOX[name], [1.0, 2.0, 3.0])
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
        '"format_version": 1,', '"format_version": 1,\n "format_version": 1,', 1
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
