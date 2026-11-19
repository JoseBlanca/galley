"""The edits files applied to the blocks before book.md is written
(architecture section 10; docs/specs/correct.md, section 10)."""

import dataclasses
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from galley.book_folder import BookFolder
from galley.errors import EditError
from galley.model import Block, BlocksFile, Edit, Span, block_sha256, read_edits

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


def _all_blocks(blocks: BlocksFile) -> tuple[Block, ...]:
    return blocks.blocks + tuple(
        block for note in blocks.notes for block in note.blocks
    )


def _occurs_once(text: str, part: str) -> int | None:
    """Where `part` starts in `text` when it occurs there exactly once."""
    first = text.find(part)
    if part == "" or first == -1 or text.find(part, first + 1) != -1:
        return None
    return first


def _applied(spans: tuple[Span, ...], edit: Edit) -> tuple[Span, ...] | _Broken:
    """The spans with the edit made, or the rule it breaks (3 or 4)."""
    start = _occurs_once("".join(span.text for span in spans), edit.old)
    if start is None:
        return _Broken.NOT_ONCE
    offset = 0
    for index, span in enumerate(spans):
        if offset <= start and start + len(edit.old) <= offset + len(span.text):
            if span.note_ref is not None:
                return _Broken.ACROSS_SPANS
            inside = start - offset
            text = span.text[:inside] + edit.new + span.text[inside + len(edit.old) :]
            return (
                *spans[:index],
                dataclasses.replace(span, text=text),
                *spans[index + 1 :],
            )
        offset += len(span.text)
    return _Broken.ACROSS_SPANS


def apply_edits(blocks: BlocksFile, edits: Sequence[FiledEdit]) -> BlocksFile:
    """The blocks with `edits` applied in their order (section 10): an edit
    applies when its block exists, its checksum is that of the block as
    structure wrote it, its `old` occurs once in the block's text as edited
    so far, inside one span that is not a note reference; then `old`
    becomes `new` in that span. Raises EditError listing every edit that
    does not apply, with its file, line and the rule it breaks."""
    originals = {block.id: block for block in _all_blocks(blocks)}
    spans = {block_id: block.spans for block_id, block in originals.items()}
    failures = []
    for filed in edits:
        edit = filed.edit
        block = originals.get(edit.block_id)
        if block is None:
            broken: _Broken | None = _Broken.NO_BLOCK
        elif block_sha256(block) != edit.block_sha256:
            broken = _Broken.CHECKSUM
        else:
            result = _applied(spans[edit.block_id], edit)
            if isinstance(result, _Broken):
                broken = result
            else:
                spans[edit.block_id] = result
                broken = None
        if broken is not None:
            failures.append(
                f"{filed.path}, line {filed.line} ({edit.block_id}, "
                f"{edit.old!r}): {broken.value}"
            )
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

    return dataclasses.replace(
        blocks,
        blocks=tuple(edited(block) for block in blocks.blocks),
        notes=tuple(
            dataclasses.replace(note, blocks=tuple(edited(b) for b in note.blocks))
            for note in blocks.notes
        ),
    )
