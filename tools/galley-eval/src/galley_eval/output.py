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
from galley_eval.note_links import NoteLinks
from galley_eval.page_table import PageRow
from galley_eval.scores import NOTE_REFERENCE_TOKENS, Part, TextScores
from galley_eval.stages import StageOutput

__all__ = [
    "BookResult",
    "RunInfo",
    "Work",
    "book_summary",
    "books_summary",
    "differences_jsonl",
    "evaluation_dir",
    "pages_tsv",
    "read_galley_commit",
    "scorecard_json",
    "work_of",
    "write_books_summary",
    "write_evaluation",
    "write_failure",
    "write_galley_commit",
]

# The kinds of difference summary.md gives for each work, and the examples
# of each; choices, enough to see what each work is about.
_COMMONEST_KINDS = 10
_EXAMPLES = 3


@dataclass(frozen=True, slots=True, kw_only=True)
class RunInfo:
    """What a scorecard says of the run that made it: the commit of galley
    that made the book's files, the commit of the comparison, the date,
    and the tool's version."""

    galley_commit: str
    comparison_commit: str
    date: str
    tool_version: str


class Work(StrEnum):
    """The work a difference calls for: the stage of galley to change."""

    ANALYZE_EXTRACT = "analyze and extract"
    EXTRACT = "extract"
    LAYOUT = "layout"
    STRUCTURE = "structure"
    MARKDOWN = "markdown"


_GALLEY_COMMIT_FILE = "galley-commit.txt"
_FAILED_FILE = "failed.txt"


def evaluation_dir(folder: BookFolder) -> Path:
    """The folder of the tool's files in a book folder."""
    return folder.root / "evaluation"


def work_of(difference: Difference) -> Work:
    """The work `difference` calls for (spec section 5): structure's for an
    extra token on the edge of a page, and for a split of words or lines
    whose first galley token ends with "-"; extract's for a glued of
    words; analyze's and extract's for the other differences of words;
    each later stage's own for its differences."""
    if difference.state is State.EXTRA and difference.edge_of_page:
        return Work.STRUCTURE
    if (
        difference.state is State.SPLIT
        and difference.stage in {StageOutput.WORDS, StageOutput.LINES}
        and difference.galley
        and difference.galley[0].endswith("-")
    ):
        return Work.STRUCTURE
    match difference.stage:
        case StageOutput.WORDS:
            if difference.state is State.GLUED:
                return Work.EXTRACT
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
        "comparison_commit": run.comparison_commit,
        "date": run.date,
        "tool_version": run.tool_version,
        "equal_key_share": scorecard.equal_key_share,
        "anchor_mismatches": scorecard.anchor_mismatches,
        "unplaced": scorecard.unplaced,
        "front_matter_not_scored": scorecard.front_matter_not_scored,
        "wrong_note_links": scorecard.wrong_note_links,
        "joined_notes": scorecard.joined_notes,
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
                "state_at_stage",
                "subkind_at_stage",
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
            "| extra on page edge | repaired | unplaced | not scored "
            "| galley tokens |"
        ),
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for scores in scorecard.outputs:
        for part, text in scores.text.items():
            if text.reference_tokens == text.galley_tokens == text.unplaced == 0:
                continue  # a part the book does not have
            rows.append(
                f"| {scores.output.value} | {part.value} | {text.reference_tokens} "
                f"| {_rate(text.token_error_rate)} | {text.matched} "
                f"| {_changed(text)} | {text.changed_convention} | {text.split} "
                f"| {text.glued} | {text.missing} | {text.extra} "
                f"| {text.edge_of_page_extra} "
                f"| {'' if text.repaired is None else text.repaired} "
                f"| {text.unplaced} | {text.not_scored} | {text.galley_tokens} |"
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
    rows.append(
        "Reference tokens not scored as front matter galley dropped: "
        f"{evaluation.scorecard.front_matter_not_scored}."
    )
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


def _note_link_rows(links: NoteLinks) -> list[str]:
    """The lines of `summary.md` that list the wrong note links and the
    joined notes, each list under its heading with its count."""
    rows = [
        f"### Wrong note links: {len(links.wrong_links)}",
        "",
        (
            "At markdown, the note links whose note begins as none of the "
            "notes the reference text references within "
            f"{NOTE_REFERENCE_TOKENS} tokens: "
            "`other_note` when it references one there, `no_reference` when "
            "it references none."
        ),
        "",
    ]
    rows.extend(
        f"- page {link.page_index}: {link.note_id} from {link.block_id}, "
        f"{link.fault.value} (Gutenberg's: "
        f"{', '.join(link.reference_notes) or 'none'})"
        for link in links.wrong_links
    )
    rows.extend(
        (
            "",
            f"### Joined notes: {len(links.joined_notes)}",
            "",
            (
                "At markdown, the galley notes that also hold the start of the "
                "next note of the reference text."
            ),
            "",
        )
    )
    rows.extend(
        f"- page {joined.page_index}: {joined.note_id} holds "
        f"{joined.reference_note} and {joined.next_reference_note}"
        for joined in links.joined_notes
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
            f"Gutenberg ebook {scorecard.gutenberg_number}; galley's files made "
            f"at {run.galley_commit}, compared at {run.comparison_commit}; "
            f"galley-eval {run.tool_version}; {run.date}. "
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
        *_note_link_rows(evaluation.note_links),
        "## Differences by the work they call for",
        "",
        (
            "Tokens not matched at markdown, by the stage of galley to change. "
            "An extra token on the edge of a page, a running head or page "
            "number, is structure's to remove, and so is a word split by a "
            "hyphen at a line end to join; words glued together are "
            "extract's, which reads the spaces between words."
        ),
        "",
        *_work_rows(evaluation.differences),
        "## Listed apart",
        "",
        *_apart_rows(evaluation),
    ]
    return "\n".join(lines).rstrip("\n") + "\n"


def _write_atomically(files: tuple[tuple[Path, str], ...]) -> None:
    """Write each text to a temporary file beside its path, then move each
    into place, so that a run cut short leaves the earlier files whole."""
    for path, text in files:
        path.with_name(path.name + ".tmp").write_text(text, encoding="utf-8")
    for path, _ in files:
        path.with_name(path.name + ".tmp").replace(path)


def write_evaluation(evaluation: Evaluation, folder: BookFolder, run: RunInfo) -> None:
    """Write the four files of a book under `<folder>/evaluation/`, and
    remove the record of an earlier failure."""
    directory = evaluation_dir(folder)
    directory.mkdir(exist_ok=True)
    _write_atomically(
        (
            (directory / "scorecard.json", scorecard_json(evaluation.scorecard, run)),
            (
                directory / "differences.jsonl",
                differences_jsonl(evaluation.differences),
            ),
            (directory / "pages.tsv", pages_tsv(evaluation.pages)),
            (directory / "summary.md", book_summary(evaluation, run)),
        )
    )
    (directory / _FAILED_FILE).unlink(missing_ok=True)


def write_failure(folder: BookFolder, error: str) -> None:
    """Record in `<folder>/evaluation/` that the book's last run or
    comparison failed, with its error, so that the books' summary shows
    it failed and not its earlier scores."""
    directory = evaluation_dir(folder)
    directory.mkdir(parents=True, exist_ok=True)
    _write_atomically(((directory / _FAILED_FILE, error + "\n"),))


def write_galley_commit(folder: BookFolder, commit: str) -> None:
    """Record in the book folder the commit of galley that made its files."""
    _write_atomically(((folder.root / _GALLEY_COMMIT_FILE, commit + "\n"),))


def read_galley_commit(folder: BookFolder) -> str:
    """The commit of galley that made the book's files, as `run` recorded
    it. Raises EvaluationError when it was not recorded."""
    path = folder.root / _GALLEY_COMMIT_FILE
    try:
        return path.read_text(encoding="utf-8").strip()
    except FileNotFoundError as err:
        message = (
            f"{path} does not exist, so the commit of galley that made the "
            f"files of {folder.root} is not known; run `galley-eval run` on it"
        )
        raise EvaluationError(message) from err


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
    *(
        (
            f"margin notes error rate, {output.value}",
            (
                "outputs",
                output.value,
                "text",
                Part.MARGIN_NOTES.value,
                "token_error_rate",
            ),
        )
        for output in StageOutput
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
    (
        "notes whose reference is right",
        ("outputs", "markdown", "notes", "reference_right"),
    ),
    ("wrong note links, markdown", ("wrong_note_links",)),
    ("joined notes, markdown", ("joined_notes",)),
    ("notes in body", ("outputs", "markdown", "notes", "in_body")),
    ("notes missing", ("outputs", "markdown", "notes", "missing")),
    (
        "margin notes as margin notes",
        ("outputs", "markdown", "margin_notes", "as_margin_note"),
    ),
    ("margin notes in body", ("outputs", "markdown", "margin_notes", "in_body")),
    ("margin notes missing", ("outputs", "markdown", "margin_notes", "missing")),
    (
        "reference headings, body range",
        ("outputs", "markdown", "headings", "reference_headings"),
    ),
    (
        "reference headings in heading blocks, body range",
        ("outputs", "markdown", "headings", "in_heading_blocks"),
    ),
    (
        "index paragraph precision, markdown",
        ("outputs", "markdown", "paragraph_boundaries", "index", "precision"),
    ),
    (
        "index paragraph recall, markdown",
        ("outputs", "markdown", "paragraph_boundaries", "index", "recall"),
    ),
    ("unplaced", ("unplaced",)),
    ("front matter not scored", ("front_matter_not_scored",)),
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


@dataclass(frozen=True, slots=True, kw_only=True)
class BookResult:
    """What the books' summary shows of a book: the text of its
    scorecard.json, or the error of its last failed run or comparison;
    neither when it was never compared."""

    name: str
    scorecard: str | None
    failure: str | None


def _book_row(result: BookResult, columns: int) -> str | None:
    if result.failure is not None:
        first_line = (
            result.failure.strip().splitlines()[0] if result.failure.strip() else ""
        )
        cells = (result.name, f"failed: {first_line}", *([""] * (columns - 2)))
        return "| " + " | ".join(cells) + " |"
    if result.scorecard is None:
        return None
    source = f"the scorecard of {result.name}"
    try:
        content = json.loads(result.scorecard)
    except json.JSONDecodeError as err:
        message = f"{source} is not valid JSON: {err}"
        raise EvaluationError(message) from err
    cells = (
        result.name,
        _summary_cell(_value_at(content, ("galley_commit",), source)),
        _summary_cell(_value_at(content, ("date",), source)),
        *(
            _summary_cell(_value_at(content, path, source))
            for _, path in _SUMMARY_COLUMNS
        ),
    )
    return "| " + " | ".join(cells) + " |"


def books_summary(results: tuple[BookResult, ...]) -> str:
    """The text of runs/evaluation/summary.md: one row per book that was
    compared or failed, a failed one with its error and no score."""
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
    lines.extend(
        row for result in results if (row := _book_row(result, len(header))) is not None
    )
    return "\n".join(lines) + "\n"


def _read_if_there(path: Path) -> str | None:
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")


def write_books_summary(runs_dir: Path, names: tuple[str, ...]) -> Path:
    """Rewrite `runs_dir/summary.md` from the books `names`, in that order:
    the scorecard of each, or its failure; return its path."""
    results = tuple(
        BookResult(
            name=name,
            scorecard=_read_if_there(runs_dir / name / "evaluation" / "scorecard.json"),
            failure=_read_if_there(runs_dir / name / "evaluation" / _FAILED_FILE),
        )
        for name in names
    )
    summary = runs_dir / "summary.md"
    _write_atomically(((summary, books_summary(results)),))
    return summary
