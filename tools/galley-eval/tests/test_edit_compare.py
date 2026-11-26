"""Tests of `galley-eval edits-compare` (spec section 9b, "A sheet against a
new run"): judged edits looked for in a new edits file, on literal sheets
and edits."""

import dataclasses
import json
from pathlib import Path

import pytest

from galley.model import Edit, write_edits
from galley_eval.cli import main
from galley_eval.edit_sheet import EditState, compare_sheet, read_sheet


def _entry(id_: int, galley: str, edit: str, verdict: str) -> dict[str, object]:
    return {
        "id": id_,
        "page_index": 4,
        "kind": "vision_word",
        "block_id": "b-p0004-002",
        "galley": galley,
        "edit": edit,
        "second_reading": None,
        "located": "block_words",
        "image": f"edit-{id_:04d}-p0004.png",
        "verdict": verdict,
        "note": "",
    }


def _sheet(tmp_path: Path) -> Path:
    content = {
        "format_version": 1,
        "run": "run",
        "pdf": "book.pdf",
        "seed": 0,
        "count": 60,
        "kinds": None,
        "edits_in_file": 9,
        "edits": [
            _entry(1, "Tue", "The", "right"),
            _entry(2, "puem ia", "poem ia", "right"),
            _entry(3, "Hammamét,", "Hammāmāt,", "wrong"),
            _entry(4, "lined", "wavylined", "wrong"),
            _entry(5, "20%", "2,052", "unclear"),
        ],
    }
    path = tmp_path / "sheet.json"
    path.write_text(json.dumps(content), encoding="utf-8")
    return path


def _edit(old: str, new: str, *, page_index: int = 4) -> Edit:
    return Edit(
        block_id="b-p0004-002",
        block_sha256="0" * 64,
        old=old,
        new=new,
        author="correct",
        reason="vision_word",
        page_index=page_index,
        model="qwen/qwen3.6-35b-a3b",
        second_reading=None,
    )


def _new_edits(tmp_path: Path) -> Path:
    path = tmp_path / "correct.jsonl"
    write_edits(
        path,
        (
            # 1 absent: dropped.
            # 2 with a context word less: kept with other context.
            _edit("puem", "poem"),
            # 3 as it was.
            _edit("Hammamét,", "Hammāmāt,"),
            # 4 on another page: dropped. 5 with another new: dropped.
            _edit("lined", "wavylined", page_index=5),
            _edit("20%", "2,032"),
        ),
    )
    return path


def test_judged_edits_are_kept_kept_with_other_context_or_dropped(
    tmp_path: Path,
) -> None:
    sheet = read_sheet(_sheet(tmp_path))
    comparison = compare_sheet(
        sheet,
        (
            _edit("Tue", "The"),
            _edit("puem", "poem"),
            _edit("Hammamét,", "Hammamât,"),
            _edit("lined", "wavylined", page_index=5),
        ),
    )
    assert tuple((item.id, item.state) for item in comparison.edits) == (
        (1, EditState.KEPT),
        (2, EditState.KEPT_OTHER_CONTEXT),
        (3, EditState.DROPPED),
        (4, EditState.DROPPED),
        (5, EditState.DROPPED),
    )
    assert comparison.edits_before == 9
    assert comparison.edits_after == 4


def test_another_word_with_the_same_change_is_not_the_judged_edit(
    tmp_path: Path,
) -> None:
    sheet = read_sheet(_sheet(tmp_path))
    comparison = compare_sheet(sheet, (_edit("Tue Poem", "The Poem"),))
    assert comparison.edits[0].state is EditState.KEPT_OTHER_CONTEXT
    # The same change on another word of the block: "Rue" holds no "Tue".
    comparison = compare_sheet(sheet, (_edit("Rue", "Rhe"),))
    assert comparison.edits[0].state is EditState.DROPPED
    # The same old and new in another block of the page.
    other_block = dataclasses.replace(_edit("Tue", "The"), block_id="b-p0004-003")
    comparison = compare_sheet(sheet, (other_block,))
    assert comparison.edits[0].state is EditState.DROPPED


def test_edits_compare_prints_the_counts_by_verdict_and_ids_only(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    main(["edits-compare", str(_sheet(tmp_path)), str(_new_edits(tmp_path))])
    out = capsys.readouterr().out
    assert out == (
        "| verdict | kept | dropped | judged |\n"
        "|---|---:|---:|---:|\n"
        "| right | 1 | 1 | 2 |\n"
        "| wrong | 1 | 1 | 2 |\n"
        "| unclear | 0 | 1 | 1 |\n"
        "| not judged | 0 | 0 | 0 |\n"
        "| all | 2 | 3 | 5 |\n"
        "\n"
        "edits: 9 in the judged run, 4 in the new file\n"
        "kept with other context: 1\n"
        "right dropped: 1\n"
        "wrong kept: 3\n"
        "unclear kept: none\n"
    )
    assert "puem" not in out


def test_edits_compare_on_a_missing_edits_file_is_an_error_naming_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    missing = tmp_path / "nothing.jsonl"
    with pytest.raises(SystemExit) as raised:
        main(["edits-compare", str(_sheet(tmp_path)), str(missing)])
    assert raised.value.code == 1
    assert str(missing) in capsys.readouterr().err
