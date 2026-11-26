"""Tests of galley_eval.edit_sheet and the subcommands `edits` and
`edits-score` (spec section 9b), on the excerpt haskins_eval: its PDF,
its committed blocks.json and lines.json, and eight hand-made edits in
tests/fixtures/evaluation/haskins_eval_edits/correct.jsonl."""

import dataclasses
import json
import shutil
from pathlib import Path

import pytest
from PIL import Image

from galley.model import Box, Edit, Origin, read_blocks, read_edits, read_lines
from galley_eval.cli import main
from galley_eval.edit_sheet import (
    Located,
    NumberedEdit,
    locate,
    numbered_edits,
    read_sheet,
    sample_edits,
    scores_table,
    sheet_scores,
)
from galley_eval.errors import EditSheetError

_REPOSITORY = Path(__file__).resolve().parents[3]
_FIXTURES = _REPOSITORY / "tests" / "fixtures"
_FOLDER = _FIXTURES / "evaluation" / "haskins_eval"
_EDITS = _FIXTURES / "evaluation" / "haskins_eval_edits" / "correct.jsonl"
_PDF = _FIXTURES / "pdf" / "haskins_eval.pdf"

_BLOCKS = read_blocks(_FOLDER / "blocks.json")
_LINES = read_lines(_FOLDER / "lines.json")
_NUMBERED = numbered_edits(read_edits(_EDITS))


def _edit(id_: int) -> Edit:
    return _NUMBERED[id_ - 1].edit


def _line_texts_in(box: Box, page_index: int) -> tuple[str, ...]:
    """The text of each line of the page whose box is wholly in `box`."""
    return tuple(
        " ".join(word.text for word in line.words)
        for page in _LINES.pages
        if page.index == page_index
        for region in page.regions
        for line in region.lines
        if box.x0 <= line.box.x0
        and line.box.x1 <= box.x1
        and box.top <= line.box.top
        and line.box.bottom <= box.bottom
    )


def _words_in(box: Box, page_index: int) -> tuple[str, ...]:
    return tuple(
        word.text
        for page in _LINES.pages
        if page.index == page_index
        for region in page.regions
        for line in region.lines
        for word in line.words
        if box.x0 <= word.box.x0
        and word.box.x1 <= box.x1
        and box.top <= word.box.top
        and word.box.bottom <= box.bottom
    )


def test_one_word_is_found_in_its_block_with_the_lines_above_and_below() -> None:
    location = locate(_edit(1), _BLOCKS, _LINES)
    assert location.located is Located.BLOCK_WORDS
    assert location.page_index == 0
    assert location.crop is not None
    assert tuple(_words_in(box, 0) for box in location.words_boxes) == (
        ("hurailiating",),
    )
    assert _line_texts_in(location.crop, 0) == (
        "driven from LeMans and Tours by Philip of",
        "France and forced to a hurailiating peace, sick In",
        "body and broken in spirit, the aged king made his way",
    )


def test_two_words_are_framed_together() -> None:
    location = locate(_edit(2), _BLOCKS, _LINES)
    assert location.located is Located.BLOCK_WORDS
    assert tuple(_words_in(box, 0) for box in location.words_boxes) == (("sick", "In"),)


def test_a_word_joined_across_a_line_end_is_found_on_both_lines() -> None:
    location = locate(_edit(3), _BLOCKS, _LINES)
    assert location.located is Located.BLOCK_WORDS
    assert location.crop is not None
    assert tuple(_words_in(box, 0) for box in location.words_boxes) == (
        ("val-",),
        ("ley",),
    )
    assert _line_texts_in(location.crop, 0) == (
        "body and broken in spirit, the aged king made his way",
        "to the old stronghold of the Angevin counts in the val-",
        "ley of the VIenne. Cursing the faithless Richard as he",
        "gave him the enforced kiss of peace at Colombieres, he",
    )


def test_a_word_outside_its_blocks_box_is_found_among_the_pages_words() -> None:
    # The block's box shrunk to the chapter heading, above the word.
    block = _BLOCKS.blocks[0]
    shrunk = dataclasses.replace(
        block, origin=(Origin(0, Box(x0=53.0, top=94.0, x1=322.0, bottom=126.0)),)
    )
    blocks = dataclasses.replace(_BLOCKS, blocks=(shrunk, *_BLOCKS.blocks[1:]))
    location = locate(_edit(1), blocks, _LINES)
    assert location.located is Located.PAGE_WORDS
    assert tuple(_words_in(box, 0) for box in location.words_boxes) == (
        ("hurailiating",),
    )


def test_words_found_nowhere_give_the_blocks_box_and_no_frame() -> None:
    location = locate(_edit(6), _BLOCKS, _LINES)
    assert location.located is Located.BLOCK_BOX
    assert location.page_index == 1
    assert location.words_boxes == ()
    assert location.crop == Box(
        x0=13.47375 - 6,
        top=29.809686374999956 - 6,
        x1=282.0501407 + 6,
        bottom=484.279413,
    )


def test_a_block_not_in_blocks_json_is_not_found() -> None:
    location = locate(_edit(7), _BLOCKS, _LINES)
    assert location.located is Located.NOT_FOUND
    assert location.crop is None


def test_an_edit_on_a_page_its_block_is_not_on_is_not_found() -> None:
    edit = dataclasses.replace(_edit(1), page_index=1)
    assert locate(edit, _BLOCKS, _LINES).located is Located.NOT_FOUND


def test_an_edit_with_no_page_is_looked_for_on_its_blocks_pages() -> None:
    edit = dataclasses.replace(_edit(1), page_index=None)
    location = locate(edit, _BLOCKS, _LINES)
    assert location.located is Located.BLOCK_WORDS
    assert location.page_index == 0


def _ids(sample: tuple[NumberedEdit, ...]) -> tuple[int, ...]:
    return tuple(item.id for item in sample)


def test_a_seeded_sample_has_the_count_is_repeatable_and_in_id_order() -> None:
    first = sample_edits(_NUMBERED, count=3, seed=7, kinds=None)
    assert len(first) == 3
    assert first == sample_edits(_NUMBERED, count=3, seed=7, kinds=None)
    assert _ids(first) == tuple(sorted(_ids(first)))
    others = {
        _ids(sample_edits(_NUMBERED, count=3, seed=s, kinds=None)) for s in range(10)
    }
    assert len(others) > 1


def test_a_count_above_the_edits_takes_them_all() -> None:
    assert _ids(sample_edits(_NUMBERED, count=60, seed=0, kinds=None)) == tuple(
        range(1, 9)
    )


def test_kinds_keep_only_their_edits() -> None:
    sample = sample_edits(
        _NUMBERED,
        count=60,
        seed=0,
        kinds=frozenset(("vision_note_link", "vision_missing_words")),
    )
    assert _ids(sample) == (4, 5)


def test_an_unknown_kind_is_an_error_naming_the_kinds() -> None:
    with pytest.raises(EditSheetError, match="vision_missing_words, vision_note_link"):
        sample_edits(_NUMBERED, count=60, seed=0, kinds=frozenset(("vision_wrod",)))


def _run_folder(tmp_path: Path) -> Path:
    run = tmp_path / "run"
    (run / "edits").mkdir(parents=True)
    (run / "book.toml").write_text(
        f'pdf = "{_PDF}"\ntitle = "Excerpt"\nauthors = ["A"]\nlanguage = "en"\n',
        encoding="utf-8",
    )
    shutil.copy(_FOLDER / "blocks.json", run / "blocks.json")
    shutil.copy(_FOLDER / "lines.json", run / "lines.json")
    shutil.copy(_EDITS, run / "edits" / "correct.jsonl")
    return run


@pytest.mark.thread_unsafe  # renders with PDFium
def test_edits_writes_a_sheet_and_images_at_300_dpi(tmp_path: Path) -> None:
    run = _run_folder(tmp_path)
    main(["edits", str(run), "--count", "60"])
    out = run / "evaluation" / "edits"
    content = json.loads((out / "sheet.json").read_text(encoding="utf-8"))
    assert content["edits_in_file"] == 8
    first = content["edits"][0]
    assert first == {
        "id": 1,
        "page_index": 0,
        "kind": "vision_word",
        "block_id": "b-p0000-001",
        "galley": "hurailiating",
        "edit": "humiliating",
        "second_reading": None,
        "located": "block_words",
        "image": "edit-0001-p0000.png",
        "verdict": "",
        "note": "",
    }
    images = {entry["id"]: entry["image"] for entry in content["edits"]}
    assert images[7] is None
    assert images[6] == "edit-0006-p0001.png"
    assert sorted(path.name for path in out.glob("*.png")) == sorted(
        image for image in images.values() if image is not None
    )
    crop = locate(_edit(1), _BLOCKS, _LINES).crop
    assert crop is not None
    with Image.open(out / "edit-0001-p0000.png") as image:
        assert image.mode == "L"
        # 300 dpi: 300 / 72 pixels a point.
        assert image.size == (
            round(crop.x1 * 300 / 72) - round(crop.x0 * 300 / 72),
            round(crop.bottom * 300 / 72) - round(crop.top * 300 / 72),
        )


@pytest.mark.thread_unsafe  # renders with PDFium
def test_edits_leaves_a_sheet_that_exists_alone(tmp_path: Path) -> None:
    run = _run_folder(tmp_path)
    out = tmp_path / "out"
    out.mkdir()
    (out / "sheet.json").write_text("verdicts", encoding="utf-8")
    with pytest.raises(SystemExit) as raised:
        main(["edits", str(run), "--out", str(out)])
    assert raised.value.code == 1
    assert (out / "sheet.json").read_text(encoding="utf-8") == "verdicts"
    assert not tuple(out.glob("*.png"))


def _judged_sheet(tmp_path: Path) -> Path:
    """A sheet of the eight hand-made edits with verdicts written in, made
    without rendering a page: edits-score reads only the kinds and the
    verdicts."""
    verdicts = {1: "right", 2: "wrong", 3: "right", 4: "unclear", 5: "right"}
    content = {
        "format_version": 1,
        "run": "run",
        "pdf": "book.pdf",
        "seed": 0,
        "count": 60,
        "kinds": None,
        "edits_in_file": len(_NUMBERED),
        "edits": [
            {
                "id": item.id,
                "page_index": item.edit.page_index,
                "kind": item.edit.reason,
                "block_id": item.edit.block_id,
                "galley": item.edit.old,
                "edit": item.edit.new,
                "second_reading": item.edit.second_reading,
                "located": "not_found",
                "image": None,
                "verdict": verdicts.get(item.id, ""),
                "note": "",
            }
            for item in _NUMBERED
        ],
    }
    path = tmp_path / "sheet.json"
    path.write_text(json.dumps(content), encoding="utf-8")
    return path


def test_edits_score_counts_the_verdicts_by_kind(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _judged_sheet(tmp_path)
    capsys.readouterr()
    main(["edits-score", str(path)])
    assert capsys.readouterr().out == (
        "| kind | right | wrong | unclear | not judged | edits |\n"
        "|---|---:|---:|---:|---:|---:|\n"
        "| vision_missing_words | 1 | 0 | 0 | 0 | 1 |\n"
        "| vision_note_link | 0 | 0 | 1 | 0 | 1 |\n"
        "| vision_word | 2 | 1 | 0 | 3 | 6 |\n"
        "| all | 3 | 1 | 1 | 3 | 8 |\n"
    )


def _sheet_text(**changes: object) -> str:
    entry = {
        "id": 1,
        "page_index": 0,
        "kind": "vision_word",
        "block_id": "b-p0000-001",
        "galley": "hurailiating",
        "edit": "humiliating",
        "second_reading": None,
        "located": "block_words",
        "image": "edit-0001-p0000.png",
        "verdict": "right",
        "note": "",
    }
    content: dict[str, object] = {
        "format_version": 1,
        "run": "run",
        "pdf": "book.pdf",
        "seed": 0,
        "count": 60,
        "kinds": None,
        "edits_in_file": 8,
        "edits": [entry],
    }
    for name, value in changes.items():
        if name in entry:
            entry[name] = value
        else:
            content[name] = value
    return json.dumps(content)


def test_a_written_sheet_is_read_back(tmp_path: Path) -> None:
    path = tmp_path / "sheet.json"
    path.write_text(_sheet_text(), encoding="utf-8")
    sheet = read_sheet(path)
    assert sheet.edits[0].galley == "hurailiating"
    assert scores_table(sheet_scores(sheet)).endswith("| all | 1 | 0 | 0 | 0 | 1 |\n")


@pytest.mark.parametrize(
    ("text", "message"),
    [
        (_sheet_text(verdict="maybe"), "verdict 'maybe' is none of"),
        (_sheet_text(format_version=2), "format_version 2"),
        (_sheet_text(id="one"), "field `id` is 'one'"),
        (_sheet_text(located="somewhere"), "located 'somewhere'"),
        (_sheet_text()[:40], "is not JSON"),
    ],
)
def test_a_malformed_sheet_is_an_error_naming_it(
    tmp_path: Path, text: str, message: str
) -> None:
    path = tmp_path / "sheet.json"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(EditSheetError, match=message):
        read_sheet(path)


def test_a_field_missing_is_named_with_its_edit(tmp_path: Path) -> None:
    content = json.loads(_sheet_text())
    del content["edits"][0]["note"]
    path = tmp_path / "sheet.json"
    path.write_text(json.dumps(content), encoding="utf-8")
    with pytest.raises(EditSheetError, match=r"edit 1: no field `note`"):
        read_sheet(path)
