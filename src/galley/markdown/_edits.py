"""The edits files applied to the blocks before book.md is written
(architecture section 10; docs/specs/correct.md, section 10)."""

import dataclasses
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from galley.book_folder import BookFolder
from galley.errors import EditError
from galley.model import (
    Block,
    BlocksFile,
    Edit,
    Note,
    NoteKind,
    Span,
    block_sha256,
    every_block,
    only_occurrence,
    read_edits,
)

# Architecture section 10: correct's file first, the owner's last.
_CORRECT = "correct.jsonl"
_OWNER = "owner.jsonl"


@dataclass(frozen=True, slots=True)
class FiledEdit:
    """An edit with the file and the line (from 1) it was read from."""

    edit: Edit
    path: Path
    line: int


class _Broken(StrEnum):
    """The rule of section 10 an edit that does not apply breaks."""

    NO_BLOCK = "its block is not in blocks.json"
    CHECKSUM = "its block_sha256 is not that of the block as structure wrote it"
    NOT_ONCE = "its old text does not occur exactly once in the block's text"
    ACROSS_SPANS = "its old text is not inside one span that is not a note reference"
    NO_NOTE = "its new text links to a note that is not in blocks.json"
    REFERENCED = (
        "its new text links to a footnote that, with every edit made, a "
        "block refers to twice"
    )


# docs/specs/correct.md, section 10: a link edit's new text ends with a link
# to a note, as markdown writes one: "[3](#n-p0008-004)".
_LINK = re.compile(r"\[([^\[\]]*)\]\(#([^()\s]+)\)\Z")


@dataclass(frozen=True, slots=True)
class _Applied:
    """The spans with an edit made, and the notes whose references it
    changed."""

    spans: tuple[Span, ...]
    notes: frozenset[str]


def read_edits_files(folder: BookFolder) -> tuple[FiledEdit, ...]:
    """The edits of every `*.jsonl` file under edits/, in the order markdown
    applies them: correct.jsonl, then the others by file name, then
    owner.jsonl. A missing folder is no edits; a path edits/ that is not a
    folder, or a malformed line, is an EditError."""
    if not folder.edits_dir.exists():
        return ()
    if not folder.edits_dir.is_dir():
        message = f"{folder.edits_dir} is not a folder; it should hold the edits files"
        raise EditError(message)
    paths = sorted(
        folder.edits_dir.glob("*.jsonl"),
        key=lambda path: (path.name != _CORRECT, path.name == _OWNER, path.name),
    )
    return tuple(
        FiledEdit(edit, path, line)
        for path in paths
        for line, edit in enumerate(read_edits(path), start=1)
    )


def _link(edit: Edit) -> re.Match[str] | None:
    """The link to a note at the end of a link edit's new text; None for an
    edit that is no link edit (its old text holds a link, or new none)."""
    if _LINK.search(edit.old) is not None:
        return None
    return _LINK.search(edit.new)


def _applied(
    spans: tuple[Span, ...], edit: Edit, note_ids: frozenset[str]
) -> _Applied | _Broken:
    """The spans with the edit made, or the rule it breaks (3, 4 or 5)."""
    start = only_occurrence("".join(span.text for span in spans), edit.old)
    if start is None:
        return _Broken.NOT_ONCE
    link = _link(edit)
    if link is not None and link.group(2) not in note_ids:
        return _Broken.NO_NOTE
    offset = 0
    for index, span in enumerate(spans):
        if offset <= start and start + len(edit.old) <= offset + len(span.text):
            if span.note_ref is not None:
                return _Broken.ACROSS_SPANS
            inside = start - offset
            if link is None:
                text = (
                    span.text[:inside] + edit.new + span.text[inside + len(edit.old) :]
                )
                return _Applied(
                    (
                        *spans[:index],
                        dataclasses.replace(span, text=text),
                        *spans[index + 1 :],
                    ),
                    frozenset(),
                )
            return _linked(spans, index, inside, edit, link)
        offset += len(span.text)
    return _Broken.ACROSS_SPANS


def _linked(
    spans: tuple[Span, ...], index: int, inside: int, edit: Edit, link: re.Match[str]
) -> _Applied:
    """The spans with a link edit made in span `index`, where its old text
    starts at `inside`: the new text less the link, then a reference span,
    which takes the place of a reference span that follows directly."""
    span = spans[index]
    end = inside + len(edit.old)
    before = span.text[:inside] + edit.new[: link.start()]
    after = span.text[end:]
    reference = Span(link.group(1), span.emphasis, link.group(2))
    rest = spans[index + 1 :]
    notes = {link.group(2)}
    if after == "" and rest and rest[0].note_ref is not None:
        notes.add(rest[0].note_ref)
        rest = rest[1:]
    made = (
        dataclasses.replace(span, text=before),
        reference,
        *((dataclasses.replace(span, text=after),) if after else ()),
    )
    return _Applied((*spans[:index], *made, *rest), frozenset(notes))


def _twice_referenced(
    spans: Mapping[str, tuple[Span, ...]],
    links: Sequence[tuple[FiledEdit, str]],
    footnotes: frozenset[str],
) -> tuple[str, ...]:
    """The link edits whose footnote a block refers to more than once once
    every edit is made (section 10, rule 6), each with its file and line."""
    counts = Counter(
        span.note_ref
        for block_spans in spans.values()
        for span in block_spans
        if span.note_ref in footnotes
    )
    return tuple(
        f"{filed.path}, line {filed.line} ({filed.edit.block_id}, "
        f"{filed.edit.old!r}): {_Broken.REFERENCED.value}"
        for filed, note_id in links
        if counts[note_id] > 1
    )


def apply_edits(blocks: BlocksFile, edits: Sequence[FiledEdit]) -> BlocksFile:
    """The blocks with `edits` applied in their order (section 10): an edit
    applies when its block exists, its checksum is that of the block as
    structure wrote it, its `old` occurs once in the block's text as edited
    so far, inside one span that is not a note reference; then `old`
    becomes `new` in that span. A link edit, whose `new` ends with a link
    to a note of blocks.json, puts a reference span after the new text, in
    place of one that follows it directly, and the notes whose references
    it changed are `referenced` when a block refers to them. Raises
    EditError listing every edit that does not apply, with its file, line
    and the rule it breaks."""
    originals = {block.id: block for block in every_block(blocks)}
    spans = {block_id: block.spans for block_id, block in originals.items()}
    note_ids = frozenset(note.id for note in blocks.notes)
    footnotes = frozenset(
        note.id for note in blocks.notes if note.kind is NoteKind.FOOTNOTE
    )
    relinked: set[str] = set()
    links: list[tuple[FiledEdit, str]] = []
    failures = []
    for filed in edits:
        edit = filed.edit
        block = originals.get(edit.block_id)
        if block is None:
            broken: _Broken | None = _Broken.NO_BLOCK
        elif block_sha256(block) != edit.block_sha256:
            broken = _Broken.CHECKSUM
        else:
            result = _applied(spans[edit.block_id], edit, note_ids)
            if isinstance(result, _Broken):
                broken = result
            else:
                spans[edit.block_id] = result.spans
                relinked |= result.notes
                if (link := _link(edit)) is not None:
                    links.append((filed, link.group(2)))
                broken = None
        if broken is not None:
            failures.append(
                f"{filed.path}, line {filed.line} ({edit.block_id}, "
                f"{edit.old!r}): {broken.value}"
            )
    failures.extend(_twice_referenced(spans, links, footnotes))
    if failures:
        message = (
            f"{len(failures)} edits do not apply; correct or delete them, or run "
            "the stage that wrote them again:\n" + "\n".join(failures)
        )
        raise EditError(message)

    def edited(block: Block) -> Block:
        if spans[block.id] is block.spans:
            return block
        return dataclasses.replace(block, spans=spans[block.id])

    referring = {
        span.note_ref
        for block_spans in spans.values()
        for span in block_spans
        if span.note_ref is not None
    }

    def note_edited(note: Note) -> Note:
        changed = dataclasses.replace(
            note, blocks=tuple(edited(b) for b in note.blocks)
        )
        if note.id not in relinked:
            return changed
        return dataclasses.replace(changed, referenced=note.id in referring)

    return dataclasses.replace(
        blocks,
        blocks=tuple(edited(block) for block in blocks.blocks),
        notes=tuple(note_edited(note) for note in blocks.notes),
    )
