"""Tests of galley_eval.output: the files the tool writes for a book and
the summary of the books (spec section 7)."""

import dataclasses
import json
from collections.abc import Callable
from pathlib import Path

import pytest

from galley.book_folder import BookFolder
from galley_eval.align import State, Subkind
from galley_eval.books import EvaluationBook
from galley_eval.errors import EvaluationError
from galley_eval.evaluate import Apart, Difference, Evaluation
from galley_eval.output import (
    BookResult,
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
    write_failure,
)
from galley_eval.scores import Part
from galley_eval.stages import StageOutput

type SmallEvaluation = Callable[[EvaluationBook | None], Evaluation]

_RUN = RunInfo(
    galley_commit="abc123",
    comparison_commit="def456",
    date="2026-11-15",
    tool_version="0.1.0",
)


def _difference(
    stage: StageOutput,
    state: State,
    *,
    edge_of_page: bool = False,
    galley: tuple[str, ...] = ("HEAD",),
) -> Difference:
    return Difference(
        stage=stage,
        state=state,
        subkind=None,
        state_at_stage=state,
        subkind_at_stage=None,
        part=Part.BODY,
        page_index=4,
        printed_page=None,
        reference=(),
        galley=galley,
        context_before=(),
        context_after=(),
        block_id=None,
        note_id=None,
        edge_of_page=edge_of_page,
        apart=None,
        cause=None,
    )


@pytest.mark.parametrize(
    ("stage", "state", "edge_of_page", "galley", "work"),
    [
        (StageOutput.WORDS, State.EXTRA, True, ("HEAD",), Work.STRUCTURE),
        (StageOutput.LINES, State.EXTRA, True, ("HEAD",), Work.STRUCTURE),
        (StageOutput.WORDS, State.EXTRA, False, ("HEAD",), Work.ANALYZE_EXTRACT),
        (StageOutput.WORDS, State.CHANGED, True, ("HEAD",), Work.ANALYZE_EXTRACT),
        (StageOutput.WORDS, State.SPLIT, False, ("repli-", "cate"), Work.STRUCTURE),
        (StageOutput.LINES, State.SPLIT, False, ("repli-", "cate"), Work.STRUCTURE),
        (
            StageOutput.WORDS,
            State.SPLIT,
            False,
            ("rep", "licate"),
            Work.ANALYZE_EXTRACT,
        ),
        (StageOutput.WORDS, State.GLUED, False, ("ofthese",), Work.EXTRACT),
        (StageOutput.LINES, State.MISSING, False, ("HEAD",), Work.LAYOUT),
        (StageOutput.BLOCKS, State.SPLIT, False, ("rep", "licate"), Work.STRUCTURE),
        (StageOutput.MARKDOWN, State.SPLIT, False, ("repli-", "cate"), Work.MARKDOWN),
        (StageOutput.MARKDOWN, State.GLUED, False, ("ofthese",), Work.MARKDOWN),
    ],
)
def test_work_of_a_difference_follows_the_spec_routing(
    stage: StageOutput,
    state: State,
    edge_of_page: bool,
    galley: tuple[str, ...],
    work: Work,
) -> None:
    difference = _difference(stage, state, edge_of_page=edge_of_page, galley=galley)
    assert work_of(difference) is work


def test_differences_jsonl_has_one_line_per_difference_in_the_spec_order(
    small_evaluation: SmallEvaluation,
) -> None:
    lines = differences_jsonl(small_evaluation(None).differences).splitlines()
    first = json.loads(lines[0])
    assert list(first) == [
        "stage",
        "state",
        "subkind",
        "state_at_stage",
        "subkind_at_stage",
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
        "cause",
    ]
    assert first == {
        "stage": "words",
        "state": "changed",
        "subkind": Subkind.LETTERS.value,
        "state_at_stage": "changed",
        "subkind_at_stage": Subkind.LETTERS.value,
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
        "cause": None,
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
        content["comparison_commit"],
        content["date"],
        content["tool_version"],
    ) == ("small", 42, "abc123", "def456", "2026-11-15", "0.1.0")
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
        books_summary(
            (
                BookResult(
                    name="broken",
                    scorecard='{"galley_commit": "x", "date": "y"}',
                    failure=None,
                ),
            )
        )
    with pytest.raises(EvaluationError, match="not valid JSON"):
        books_summary((BookResult(name="broken", scorecard="{", failure=None),))


def test_book_that_failed_is_shown_failed_not_with_its_earlier_scores(
    tmp_path: Path,
    small_book: Callable[[str], EvaluationBook],
    small_evaluation: SmallEvaluation,
) -> None:
    folder = BookFolder(tmp_path / "first")
    folder.root.mkdir()
    write_evaluation(small_evaluation(small_book("first")), folder, _RUN)
    write_failure(folder, "galley2epub run exited with 1: ERROR bad page\nmore")
    summary = write_books_summary(tmp_path, ("first",)).read_text(encoding="utf-8")
    (row,) = (line for line in summary.splitlines() if line.startswith("| first"))
    assert row.startswith("| first | failed: galley2epub run exited with 1: ERROR")
    assert "abc123" not in row
    # A later success removes the failure.
    write_evaluation(small_evaluation(small_book("first")), folder, _RUN)
    summary = write_books_summary(tmp_path, ("first",)).read_text(encoding="utf-8")
    assert "| first | abc123 |" in summary


def test_write_evaluation_leaves_no_temporary_file(
    tmp_path: Path, small_evaluation: SmallEvaluation
) -> None:
    write_evaluation(small_evaluation(None), BookFolder(tmp_path), _RUN)
    assert not tuple((tmp_path / "evaluation").glob("*.tmp"))


def test_differences_listed_apart_are_not_grouped_by_work(
    small_evaluation: SmallEvaluation,
) -> None:
    evaluation = small_evaluation(None)
    apart = dataclasses.replace(
        _difference(StageOutput.WORDS, State.EXTRA, galley=("APARTWORD",)),
        apart=Apart.EXCLUDED_PAGE,
    )
    summary = book_summary(
        dataclasses.replace(evaluation, differences=(*evaluation.differences, apart)),
        _RUN,
    )
    works = summary.split("## Differences by the work")[1].split("## Listed apart")[0]
    assert "APARTWORD" not in works
    assert "1 excluded_page" in summary
