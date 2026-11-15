"""The files the tool writes for a book, under `<book folder>/evaluation/`,
and the summary of all books, `runs/evaluation/summary.md` (spec section
7).

- `scorecard.json`: the scorecard, with galley's commit, the date, the
  Gutenberg ebook number and the tool's version;
- `differences.jsonl`: one difference per line;
- `pages.tsv`: the table of pages;
- `summary.md`: the scorecard, the commonest differences grouped by the
  work they call for, and what is listed apart.

The functions that make the text of each file are pure; `write_evaluation`
and `write_books_summary` write them. JSON is written with
`ensure_ascii=False`, keys in the order of the dataclasses' fields and an
indent of 2, so that a run on the same files gives the same bytes but for
the commit and the date.

How the spec is read here, where it leaves a choice: the work a
difference calls for is that of the stage it is attributed to (analyze
and extract for words, layout for lines, structure for blocks, markdown
for markdown), except that an extra token on the edge of a page calls for
structure's work, which is to remove running heads, page numbers and
signature marks. The differences listed apart, unplaced or on a page that
is not scored, are counted in summary.md but not grouped by work.
"""

import dataclasses
import json
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum, StrEnum
from pathlib import Path
from typing import assert_never

from galley.book_folder import BookFolder
from galley_eval.align import State
from galley_eval.errors import EvaluationError
from galley_eval.evaluate import Difference, Evaluation, OutputScores, Scorecard
from galley_eval.page_table import PageRow
from galley_eval.scores import Part, TextScores
from galley_eval.stages import StageOutput

__all__ = [
    "RunInfo",
    "Work",
    "book_summary",
    "books_summary",
    "differences_jsonl",
    "evaluation_dir",
    "pages_tsv",
    "scorecard_json",
    "work_of",
    "write_books_summary",
    "write_evaluation",
]

# The kinds of difference summary.md gives for each work, and the examples
# of each; choices, enough to see what each work is about.
_COMMONEST_KINDS = 10
_EXAMPLES = 3


@dataclass(frozen=True, slots=True, kw_only=True)
class RunInfo:
    """What a scorecard says of the run that made it: galley's commit, the
    date, and the tool's version."""

    galley_commit: str
    date: str
    tool_version: str


class Work(StrEnum):
    """The work a difference calls for: the stage of galley to change."""

    ANALYZE_EXTRACT = "analyze and extract"
    LAYOUT = "layout"
    STRUCTURE = "structure"
    MARKDOWN = "markdown"


def evaluation_dir(folder: BookFolder) -> Path:
    """The folder of the tool's files in a book folder."""
    return folder.root / "evaluation"


def work_of(difference: Difference) -> Work:
    """The work `difference` calls for: its stage's, but structure's for an
    extra token on the edge of a page."""
    if difference.state is State.EXTRA and difference.edge_of_page:
        return Work.STRUCTURE
    match difference.stage:
        case StageOutput.WORDS:
            return Work.ANALYZE_EXTRACT
        case StageOutput.LINES:
            return Work.LAYOUT
        case StageOutput.BLOCKS:
            return Work.STRUCTURE
        case StageOutput.MARKDOWN:
            return Work.MARKDOWN
        case _:
            assert_never(difference.stage)


# JSON


def _plain(value: object) -> object:
    """A value as JSON holds it: dataclasses as objects in field order,
    enums as their values, tuples as lists."""
    match value:
        case Enum():
            return value.value
        case str() | int() | float() | bool() | None:
            return value
        case tuple():
            return [_plain(item) for item in value]
        case frozendict() | dict():
            return {str(_plain(key)): _plain(item) for key, item in value.items()}
        case _ if dataclasses.is_dataclass(value) and not isinstance(value, type):
            return {
                field.name: _plain(getattr(value, field.name))
                for field in dataclasses.fields(value)
            }
        case _:
            message = f"no JSON form for {type(value).__name__}: {value!r}"
            raise TypeError(message)


def scorecard_json(scorecard: Scorecard, run: RunInfo) -> str:
    """The text of scorecard.json."""
    content = {
        "book": scorecard.book,
        "gutenberg_number": scorecard.gutenberg_number,
        "galley_commit": run.galley_commit,
        "date": run.date,
        "tool_version": run.tool_version,
        "equal_key_share": scorecard.equal_key_share,
        "anchor_mismatches": scorecard.anchor_mismatches,
        "unplaced": scorecard.unplaced,
        "outputs": {
            scores.output.value: {
                key: item for key, item in _items(scores) if key != "output"
            }
            for scores in scorecard.outputs
        },
    }
    return json.dumps(content, ensure_ascii=False, indent=2) + "\n"


def _items(scores: OutputScores) -> Iterable[tuple[str, object]]:
    plain = _plain(scores)
    assert isinstance(plain, dict)  # a dataclass becomes a dict
    return tuple((str(key), item) for key, item in plain.items())


def differences_jsonl(differences: tuple[Difference, ...]) -> str:
    """The text of differences.jsonl, one difference per line, with its
    context as {"before": [...], "after": [...]}."""
    lines = []
    for difference in differences:
        plain = _plain(difference)
        assert isinstance(plain, dict)  # a dataclass becomes a dict
        before = plain.pop("context_before")
        after = plain.pop("context_after")
        ordered = {
            key: plain[key]
            for key in (
                "stage",
                "state",
                "subkind",
                "part",
                "page_index",
                "printed_page",
                "reference",
                "galley",
            )
        }
        ordered["context"] = {"before": before, "after": after}
        ordered |= {key: item for key, item in plain.items() if key not in ordered}
        lines.append(json.dumps(ordered, ensure_ascii=False) + "\n")
    return "".join(lines)


# pages.tsv

_PAGE_COLUMNS = tuple(field.name for field in dataclasses.fields(PageRow))


def _cell(value: object) -> str:
    match value:
        case None:
            return ""
        case Enum():
            return str(value.value)
        case float():
            return f"{value:.4f}"
        case _:
            return str(value)


def pages_tsv(rows: tuple[PageRow, ...]) -> str:
    """The text of pages.tsv: a header and one row per page; an empty cell
    for a value that is None, shares with 4 decimals."""
    lines = ["\t".join(_PAGE_COLUMNS)]
    lines.extend(
        "\t".join(_cell(getattr(row, column)) for column in _PAGE_COLUMNS)
        for row in rows
    )
    return "\n".join(lines) + "\n"


# summary.md of a book


def _rate(value: float | None) -> str:
    return "" if value is None else f"{value:.3f}"


def _text_rows(scorecard: Scorecard) -> list[str]:
    rows = [
        (
            "| output | part | reference tokens | token error rate | matched "
            "| changed | convention | split | glued | missing | extra "
            "| extra on page edge | repaired | unplaced |"
        ),
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for scores in scorecard.outputs:
        for part, text in scores.text.items():
            if text.reference_tokens == 0 and text.extra == 0 and text.unplaced == 0:
                continue  # a part the book does not have
            rows.append(
                f"| {scores.output.value} | {part.value} | {text.reference_tokens} "
                f"| {_rate(text.token_error_rate)} | {text.matched} "
                f"| {_changed(text)} | {text.changed_convention} | {text.split} "
                f"| {text.glued} | {text.missing} | {text.extra} "
                f"| {text.edge_of_page_extra} "
                f"| {'' if text.repaired is None else text.repaired} "
                f"| {text.unplaced} |"
            )
    return rows


def _changed(text: TextScores) -> int:
    return (
        text.changed_case
        + text.changed_punctuation
        + text.changed_diacritic
        + text.changed_letters
    )


def _structure_rows(scorecard: Scorecard) -> list[str]:
    rows: list[str] = []
    for scores in scorecard.outputs:
        if scores.paragraph_boundaries is None:
            continue  # words and lines have no structure
        rows.append(f"### At {scores.output.value}")
        rows.append("")
        rows.append(
            "| part | galley boundaries | right | reference boundaries "
            "| found | precision | recall |"
        )
        rows.append("|---|---|---|---|---|---|---|")
        for part, boundaries in scores.paragraph_boundaries.items():
            if boundaries.galley_boundaries == boundaries.reference_boundaries == 0:
                continue  # a part with no boundary on either side
            rows.append(
                f"| {part.value} | {boundaries.galley_boundaries} "
                f"| {boundaries.right} | {boundaries.reference_boundaries} "
                f"| {boundaries.found} | {_rate(boundaries.precision)} "
                f"| {_rate(boundaries.recall)} |"
            )
        rows.append("")
        if scores.notes is not None:
            notes = scores.notes
            rows.append(
                f"Notes: {notes.as_note} as notes ({notes.reference_right} with "
                f"their reference right), {notes.in_body} in the body, "
                f"{notes.missing} missing."
            )
        if scores.margin_notes is not None:
            margin = scores.margin_notes
            position = (
                "position not scored"
                if margin.position_right is None
                else f"{margin.position_right} in the right place"
            )
            rows.append(
                f"Margin notes: {margin.as_margin_note} as margin notes "
                f"({position}), {margin.in_body} in the body, "
                f"{margin.missing} missing."
            )
        rows.append("")
        if scores.block_kinds is not None:
            rows.append("| part | reference kind | galley kind | blocks |")
            rows.append("|---|---|---|---|")
            for part, kinds in scores.block_kinds.items():
                rows.extend(
                    f"| {part.value} | {kind.reference} | {kind.galley} | {kind.count} |"
                    for kind in kinds
                )
            rows.append("")
    return rows


def _kind(difference: Difference) -> str:
    if difference.subkind is None:
        return difference.state.value
    return f"{difference.state.value} ({difference.subkind.value})"


def _example(difference: Difference) -> str:
    reference = " ".join(difference.reference) or "–"
    galley = " ".join(difference.galley) or "–"
    page = "?" if difference.page_index is None else str(difference.page_index)
    return f"`{reference}` → `{galley}` (page {page})"


def _token_count(difference: Difference) -> int:
    return max(len(difference.reference), 1)


def _work_rows(differences: tuple[Difference, ...]) -> list[str]:
    scored = tuple(difference for difference in differences if difference.apart is None)
    rows: list[str] = []
    for work in Work:
        mine = tuple(difference for difference in scored if work_of(difference) is work)
        tokens = sum(_token_count(difference) for difference in mine)
        rows.append(f"### {work.value}: {tokens} tokens")
        rows.append("")
        if not mine:
            rows.append("No difference.")
            rows.append("")
            continue
        kinds: Counter[tuple[StageOutput, str]] = Counter()
        examples: dict[tuple[StageOutput, str], list[Difference]] = {}
        for difference in mine:
            key = (difference.stage, _kind(difference))
            kinds[key] += _token_count(difference)
            examples.setdefault(key, []).append(difference)
        rows.append("| first seen at | kind | tokens | examples |")
        rows.append("|---|---|---|---|")
        for (stage, kind), count in kinds.most_common(_COMMONEST_KINDS):
            shown = "; ".join(
                _example(difference) for difference in examples[stage, kind][:_EXAMPLES]
            )
            rows.append(f"| {stage.value} | {kind} | {count} | {shown} |")
        rows.append("")
    return rows


def _apart_rows(evaluation: Evaluation) -> list[str]:
    rows: list[str] = []
    apart = Counter(
        difference.apart.value
        for difference in evaluation.differences
        if difference.apart is not None
    )
    listed = ", ".join(f"{count} {reason}" for reason, count in sorted(apart.items()))
    rows.append(f"Differences listed apart and not scored: {listed or 'none'}.")
    rows.append("")
    rows.append(f"### Anchor mismatches: {len(evaluation.anchor_mismatches)}")
    rows.append("")
    rows.extend(
        f"- printed page {anchor.anchor.printed_page}: offset {anchor.offset}, "
        f"page index {anchor.page_index}"
        for anchor in evaluation.anchor_mismatches
    )
    unplaced = sum(len(run.tokens) for run in evaluation.unplaced)
    rows.append("")
    rows.append(f"### Unplaced tokens: {unplaced}")
    rows.append("")
    rows.extend(
        f"- `{' '.join(run.tokens)}`, after “{' '.join(run.context_before)}”"
        for run in evaluation.unplaced
    )
    rows.append("")
    rows.append(f"### Page anchors among the notes: {len(evaluation.anchors_in_notes)}")
    rows.append("")
    rows.extend(
        f"- printed page {anchor.printed_page}, before token "
        f"{anchor.gap.token_index} of the notes"
        for anchor in evaluation.anchors_in_notes
    )
    rows.append("")
    return rows


def book_summary(evaluation: Evaluation, run: RunInfo) -> str:
    """The text of a book's summary.md."""
    scorecard = evaluation.scorecard
    lines = [
        f"# {scorecard.book}",
        "",
        (
            f"Gutenberg ebook {scorecard.gutenberg_number}; galley at "
            f"{run.galley_commit}; galley-eval {run.tool_version}; {run.date}. "
            f"galley's words align {scorecard.equal_key_share:.1%} of the "
            "reference's tokens to a token with the same key."
        ),
        "",
        "## Text",
        "",
        *_text_rows(scorecard),
        "",
        "## Structure",
        "",
        *_structure_rows(scorecard),
        "## Differences by the work they call for",
        "",
        (
            "Tokens not matched at markdown, by the stage of galley to change. "
            "An extra token on the edge of a page, a running head or page "
            "number, is structure's to remove."
        ),
        "",
        *_work_rows(evaluation.differences),
        "## Listed apart",
        "",
        *_apart_rows(evaluation),
    ]
    return "\n".join(lines).rstrip("\n") + "\n"


def write_evaluation(evaluation: Evaluation, folder: BookFolder, run: RunInfo) -> None:
    """Write the four files of a book under `<folder>/evaluation/`."""
    directory = evaluation_dir(folder)
    directory.mkdir(exist_ok=True)
    (directory / "scorecard.json").write_text(
        scorecard_json(evaluation.scorecard, run), encoding="utf-8"
    )
    (directory / "differences.jsonl").write_text(
        differences_jsonl(evaluation.differences), encoding="utf-8"
    )
    (directory / "pages.tsv").write_text(pages_tsv(evaluation.pages), encoding="utf-8")
    (directory / "summary.md").write_text(
        book_summary(evaluation, run), encoding="utf-8"
    )


# runs/evaluation/summary.md

# Each column of the books' summary: its heading, and the path of its value
# in scorecard.json.
_SUMMARY_COLUMNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("equal-key share", ("equal_key_share",)),
    *(
        (
            f"body error rate, {output.value}",
            ("outputs", output.value, "text", Part.BODY.value, "token_error_rate"),
        )
        for output in StageOutput
    ),
    (
        "notes error rate, markdown",
        ("outputs", "markdown", "text", Part.NOTES.value, "token_error_rate"),
    ),
    (
        "body extra on page edge, words",
        ("outputs", "words", "text", Part.BODY.value, "edge_of_page_extra"),
    ),
    (
        "paragraph precision, markdown",
        ("outputs", "markdown", "paragraph_boundaries", "body", "precision"),
    ),
    (
        "paragraph recall, markdown",
        ("outputs", "markdown", "paragraph_boundaries", "body", "recall"),
    ),
    ("notes as notes", ("outputs", "markdown", "notes", "as_note")),
    ("notes in body", ("outputs", "markdown", "notes", "in_body")),
    ("notes missing", ("outputs", "markdown", "notes", "missing")),
    (
        "margin notes as margin notes",
        ("outputs", "markdown", "margin_notes", "as_margin_note"),
    ),
    ("unplaced", ("unplaced",)),
    ("anchor mismatches", ("anchor_mismatches",)),
)


def _value_at(content: object, path: tuple[str, ...], source: str) -> object:
    value = content
    for key in path:
        match value:
            case dict() if key in value:
                value = value[key]
            case _:
                message = f"{source} has no {'.'.join(path)}"
                raise EvaluationError(message)
    return value


def _summary_cell(value: object) -> str:
    match value:
        case None:
            return ""
        case float():
            return f"{value:.3f}"
        case _:
            return str(value)


def books_summary(scorecards: tuple[tuple[str, str], ...]) -> str:
    """The text of runs/evaluation/summary.md: one row per book, from each
    book's name and the text of its scorecard.json."""
    header = ("book", "commit", "date", *(heading for heading, _ in _SUMMARY_COLUMNS))
    lines = [
        "# galley on the evaluation set",
        "",
        (
            "Rewritten by `galley-eval` from each book's "
            "`evaluation/scorecard.json`. Error rates are those of the body "
            "unless named; lower is better."
        ),
        "",
        "| " + " | ".join(header) + " |",
        "|" + "---|" * len(header),
    ]
    for name, text in scorecards:
        source = f"the scorecard of {name}"
        try:
            content = json.loads(text)
        except json.JSONDecodeError as err:
            message = f"{source} is not valid JSON: {err}"
            raise EvaluationError(message) from err
        cells = (
            name,
            _summary_cell(_value_at(content, ("galley_commit",), source)),
            _summary_cell(_value_at(content, ("date",), source)),
            *(
                _summary_cell(_value_at(content, path, source))
                for _, path in _SUMMARY_COLUMNS
            ),
        )
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def write_books_summary(runs_dir: Path, names: tuple[str, ...]) -> Path:
    """Rewrite `runs_dir/summary.md` from the scorecards of the books
    `names` that have one, in that order; return its path."""
    scorecards = tuple(
        (name, path.read_text(encoding="utf-8"))
        for name in names
        if (path := runs_dir / name / "evaluation" / "scorecard.json").exists()
    )
    summary = runs_dir / "summary.md"
    summary.write_text(books_summary(scorecards), encoding="utf-8")
    return summary
