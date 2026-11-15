"""Tests of galley_eval.output: the files the tool writes for a book and
the summary of the books (spec section 7)."""

import json
from collections.abc import Callable
from pathlib import Path

import pytest

from galley.book_folder import BookFolder
from galley_eval.align import State, Subkind
from galley_eval.books import EvaluationBook
from galley_eval.errors import EvaluationError
from galley_eval.evaluate import Difference, Evaluation
from galley_eval.output import (
    RunInfo,
    Work,
    book_summary,
    books_summary,
    differences_jsonl,
    pages_tsv,
    scorecard_json,
    work_of,
    write_books_summary,
    write_evaluation,
)
from galley_eval.scores import Part
from galley_eval.stages import StageOutput

type SmallEvaluation = Callable[[EvaluationBook | None], Evaluation]

_RUN = RunInfo(galley_commit="abc123", date="2026-11-15", tool_version="0.1.0")


def _difference(
    stage: StageOutput, state: State, *, edge_of_page: bool = False
) -> Difference:
    return Difference(
        stage=stage,
        state=state,
        subkind=None,
        part=Part.BODY,
        page_index=4,
        printed_page=None,
        reference=(),
        galley=("HEAD",),
        context_before=(),
        context_after=(),
        block_id=None,
        note_id=None,
        edge_of_page=edge_of_page,
        apart=None,
    )


@pytest.mark.parametrize(
    ("stage", "state", "edge_of_page", "work"),
    [
        (StageOutput.WORDS, State.EXTRA, True, Work.STRUCTURE),
        (StageOutput.WORDS, State.EXTRA, False, Work.ANALYZE_EXTRACT),
        (StageOutput.WORDS, State.CHANGED, True, Work.ANALYZE_EXTRACT),
        (StageOutput.LINES, State.MISSING, False, Work.LAYOUT),
        (StageOutput.BLOCKS, State.SPLIT, False, Work.STRUCTURE),
        (StageOutput.MARKDOWN, State.GLUED, False, Work.MARKDOWN),
    ],
)
def test_work_of_a_difference_is_its_stage_but_structure_for_page_edges(
    stage: StageOutput, state: State, edge_of_page: bool, work: Work
) -> None:
    assert work_of(_difference(stage, state, edge_of_page=edge_of_page)) is work


def test_differences_jsonl_has_one_line_per_difference_in_the_spec_order(
    small_evaluation: SmallEvaluation,
) -> None:
    lines = differences_jsonl(small_evaluation(None).differences).splitlines()
    first = json.loads(lines[0])
    assert list(first) == [
        "stage",
        "state",
        "subkind",
        "part",
        "page_index",
        "printed_page",
        "reference",
        "galley",
        "context",
        "block_id",
        "note_id",
        "edge_of_page",
        "apart",
    ]
    assert first == {
        "stage": "words",
        "state": "changed",
        "subkind": Subkind.LETTERS.value,
        "part": "body",
        "page_index": 1,
        "printed_page": None,
        "reference": ["work"],
        "galley": ["werk"],
        "context": {
            "before": ["We", "must", "replicate", "the"],
            "after": ["of", "the", "Normans", "in", "Sicily"],
        },
        "block_id": "b-p0001-001",
        "note_id": None,
        "edge_of_page": False,
        "apart": None,
    }
    # The running head's two words, extra from words on.
    assert len(lines) == 3


def test_scorecard_json_has_the_run_and_every_output(
    small_evaluation: SmallEvaluation,
) -> None:
    content = json.loads(scorecard_json(small_evaluation(None).scorecard, _RUN))
    assert (
        content["book"],
        content["gutenberg_number"],
        content["galley_commit"],
        content["date"],
        content["tool_version"],
    ) == ("small", 42, "abc123", "2026-11-15", "0.1.0")
    assert list(content["outputs"]) == ["words", "lines", "blocks", "markdown"]
    body = content["outputs"]["markdown"]["text"]["body"]
    # werk, RUNNING and HEAD in ten reference tokens.
    assert body["token_error_rate"] == pytest.approx(0.3)
    assert content["outputs"]["words"]["paragraph_boundaries"] is None
    assert content["outputs"]["blocks"]["notes"] == {
        "as_note": 0,
        "in_body": 0,
        "missing": 0,
        "reference_right": 0,
    }


def test_pages_tsv_leaves_empty_cells_and_gives_four_decimals(
    small_evaluation: SmallEvaluation,
) -> None:
    header, row = pages_tsv(small_evaluation(None).pages).splitlines()
    cells = dict(zip(header.split("\t"), row.split("\t"), strict=True))
    assert cells["page_index"] == "1"
    assert cells["printed_page"] == ""
    assert cells["text_source"] == "text_layer"
    assert cells["ocr_confidence_mean"] == ""
    # 9 of the 10 reference tokens read: "werk" is not.
    assert cells["ocr_recall"] == "0.9000"


def test_book_summary_lists_the_running_head_under_structure(
    small_evaluation: SmallEvaluation,
) -> None:
    summary = book_summary(small_evaluation(None), _RUN)
    structure = summary.split("### structure: ")[1].split("###")[0]
    assert structure.startswith("2 tokens")
    assert "`–` → `RUNNING` (page 1)" in structure
    extract = summary.split("### analyze and extract: ")[1].split("###")[0]
    assert extract.startswith("1 tokens")
    assert "`work` → `werk`" in extract
    assert "### Unplaced tokens: 0" in summary


def test_write_evaluation_writes_the_four_files(
    tmp_path: Path, small_evaluation: SmallEvaluation
) -> None:
    write_evaluation(small_evaluation(None), BookFolder(tmp_path), _RUN)
    assert sorted(path.name for path in (tmp_path / "evaluation").iterdir()) == [
        "differences.jsonl",
        "pages.tsv",
        "scorecard.json",
        "summary.md",
    ]


def test_books_summary_has_one_row_per_book_with_a_scorecard(
    tmp_path: Path,
    small_book: Callable[[str], EvaluationBook],
    small_evaluation: SmallEvaluation,
) -> None:
    for name in ("first", "second"):
        folder = BookFolder(tmp_path / name)
        folder.root.mkdir()
        write_evaluation(small_evaluation(small_book(name)), folder, _RUN)
    summary = write_books_summary(tmp_path, ("first", "never_run", "second"))
    rows = [
        line
        for line in summary.read_text(encoding="utf-8").splitlines()
        if line.startswith(("| first", "| second", "| never_run"))
    ]
    assert len(rows) == 2
    # Equal-key share 8 of 10; at words and lines, werk, the split
    # replicate and the running head; at blocks and markdown, not the split.
    assert rows[0].startswith(
        "| first | abc123 | 2026-11-15 | 0.800 | 0.400 | 0.400 | 0.300 | 0.300 |"
    )


def test_books_summary_of_a_scorecard_without_a_score_is_an_error() -> None:
    with pytest.raises(EvaluationError, match="scorecard of broken has no"):
        books_summary((("broken", '{"galley_commit": "x", "date": "y"}'),))
    with pytest.raises(EvaluationError, match="not valid JSON"):
        books_summary((("broken", "{"),))
