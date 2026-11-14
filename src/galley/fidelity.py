"""The fidelity check: no word of the book lost or invented between stages.

`check_stage` compares the words of a stage's input with the words of its
output plus what the stage recorded, as multisets over the whole book, at
three boundaries: layout (words.json against lines.json), structure
(lines.json against blocks.json) and markdown (blocks.json against book.md
as Pandoc reads it). Architecture section 13 and the walking-skeleton spec,
section 5, say which words each side holds.
"""

import json
import shutil
import subprocess
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal, assert_never, overload

from galley.errors import ExternalProgramError, FidelityBoundary, FidelityError
from galley.model import Block, BlocksFile, LinesFile, Origin, WordsFile


@dataclass(frozen=True, slots=True)
class MarkdownWord:
    """A word of book.md as Pandoc reads it, with the id of the innermost
    div or heading it is in, or None outside any."""

    text: str
    block_id: str | None


@dataclass(frozen=True, slots=True)
class MarkdownWords:
    """The words of book.md as Pandoc reads it, in order, and the number of
    notes Pandoc found (its Note elements)."""

    words: tuple[MarkdownWord, ...]
    note_count: int


@dataclass(frozen=True, slots=True)
class _PlacedWord:
    """A word of one side of the check, and where it came from, as the
    error's detail names it: "page 3", "block b-p0003-001 pages 3, 4"."""

    text: str
    place: str


def _placed(text: str, place: str) -> tuple[_PlacedWord, ...]:
    return tuple(_PlacedWord(word, place) for word in text.split())


def _pages(origin: tuple[Origin, ...]) -> str:
    page_indices = tuple(dict.fromkeys(part.page_index for part in origin))
    match page_indices:
        case ():
            return "no page"
        case (page_index,):
            return f"page {page_index}"
        case _:
            return "pages " + ", ".join(str(page_index) for page_index in page_indices)


def _words_file_words(words: WordsFile) -> tuple[_PlacedWord, ...]:
    return tuple(
        _PlacedWord(word.text, f"page {page.index}")
        for page in words.pages
        for word in page.words
    )


def _lines_file_words(lines: LinesFile) -> tuple[_PlacedWord, ...]:
    return tuple(
        _PlacedWord(word.text, f"page {page.index}")
        for page in lines.pages
        for region in page.regions
        for line in region.lines
        for word in line.words
    )


type _BlocksBoundary = Literal[FidelityBoundary.STRUCTURE, FidelityBoundary.MARKDOWN]


def _block_words(block: Block, boundary: _BlocksBoundary) -> tuple[_PlacedWord, ...]:
    """The words of a block, its spans split one by one: a note reference
    span is replaced by a space in the block's text, so that it does not
    glue to the word before, and at the structure boundary counted as a
    word of its own."""
    place = f"block {block.id} {_pages(block.origin)}"
    text = "".join(
        " " if span.note_ref is not None else span.text for span in block.spans
    )
    match boundary:
        case FidelityBoundary.STRUCTURE:
            references = tuple(
                word
                for span in block.spans
                if span.note_ref is not None
                for word in _placed(span.text, place)
            )
        case FidelityBoundary.MARKDOWN:
            references = ()
        case _:
            assert_never(boundary)
    return _placed(text, place) + references


def _blocks_file_words(
    blocks: BlocksFile, boundary: _BlocksBoundary
) -> tuple[_PlacedWord, ...]:
    """The words of the body and of every note, with each note's marker,
    except at the markdown boundary the marker of a referenced note, which
    Pandoc replaces with its own number."""
    body = tuple(
        word for block in blocks.blocks for word in _block_words(block, boundary)
    )
    notes = tuple(
        word
        for note in blocks.notes
        for block in note.blocks
        for word in _block_words(block, boundary)
    )
    match boundary:
        case FidelityBoundary.STRUCTURE:
            counted_notes = blocks.notes
        case FidelityBoundary.MARKDOWN:
            counted_notes = tuple(note for note in blocks.notes if not note.referenced)
        case _:
            assert_never(boundary)
    markers = tuple(
        word
        for note in counted_notes
        for word in _placed(note.marker, f"note {note.id} {_pages(note.origin)}")
    )
    return body + notes + markers


def _removal_words(blocks: BlocksFile) -> tuple[_PlacedWord, ...]:
    return tuple(
        word
        for removal in blocks.removals
        for word in _placed(removal.text, f"removal page {removal.page_index}")
    )


def _words_before_changes(blocks: BlocksFile) -> tuple[_PlacedWord, ...]:
    return tuple(
        _PlacedWord(word, f"word change page {change.page_index}")
        for change in blocks.word_changes
        for word in change.before
    )


def _words_after_changes(blocks: BlocksFile) -> tuple[_PlacedWord, ...]:
    return tuple(
        _PlacedWord(word, f"word change page {change.page_index}")
        for change in blocks.word_changes
        for word in change.after
    )


def _markdown_words(markdown: MarkdownWords) -> tuple[_PlacedWord, ...]:
    return tuple(
        _PlacedWord(
            word.text,
            f"block {word.block_id}" if word.block_id is not None else "no block",
        )
        for word in markdown.words
    )


def _all_blocks(blocks: BlocksFile) -> tuple[Block, ...]:
    """The blocks of the body, then those of every note."""
    return blocks.blocks + tuple(
        block for note in blocks.notes for block in note.blocks
    )


def _note_reference_count(blocks: BlocksFile) -> int:
    return sum(
        1
        for block in _all_blocks(blocks)
        for span in block.spans
        if span.note_ref is not None
    )


def _places(words: Iterable[_PlacedWord], text: str) -> str:
    places = tuple(dict.fromkeys(word.place for word in words if word.text == text))
    return ", ".join(places) if places else "none"


def _check_words(
    boundary: FidelityBoundary,
    input_words: tuple[_PlacedWord, ...],
    output_words: tuple[_PlacedWord, ...],
    taken_out: tuple[_PlacedWord, ...],
    note_detail: str,
) -> None:
    """Raise FidelityError when the input words, as a multiset, are not the
    output words less those taken out, or when `note_detail` reports a
    difference in the note counts; return otherwise."""
    difference = Counter(word.text for word in input_words)
    difference.subtract(word.text for word in output_words)
    difference.update(word.text for word in taken_out)
    missing = frozendict(
        sorted((text, count) for text, count in difference.items() if count > 0)
    )
    invented = frozendict(
        sorted((text, -count) for text, count in difference.items() if count < 0)
    )
    if not missing and not invented and not note_detail:
        return
    word_details = tuple(
        f"{text!r}: input {_places(input_words, text)}, "
        f"output {_places(output_words + taken_out, text)}"
        for text in sorted(missing | invented)
    )
    detail = "; ".join(word_details + ((note_detail,) if note_detail else ()))
    raise FidelityError(boundary, missing, invented, detail)


def _reference_problems(blocks: BlocksFile) -> tuple[str, ...]:
    """The note reference spans whose text is not exactly the marker of the
    note they name, or that name no note. At the markdown boundary a
    reference span becomes Pandoc's note and its text is not counted, so
    any other word in it would be lost there unseen."""
    markers = {note.id: note.marker for note in blocks.notes}
    return tuple(
        (
            f"block {block.id}: the note reference span {span.text!r} names "
            f"{span.note_ref}, which is no note"
            if span.note_ref not in markers
            else f"block {block.id}: the note reference span {span.text!r} is not "
            f"the marker {markers[span.note_ref]!r} of note {span.note_ref}"
        )
        for block in _all_blocks(blocks)
        for span in block.spans
        if span.note_ref is not None and markers.get(span.note_ref) != span.text
    )


def _check_records(boundary: FidelityBoundary, problems: tuple[str, ...]) -> None:
    """Raise FidelityError, with no missing or invented word, when a record
    of the stage is wrong; `problems` says which and where."""
    if problems:
        raise FidelityError(boundary, frozendict(), frozendict(), "; ".join(problems))


def _wrong_types(stage: FidelityBoundary, before: object, after: object) -> TypeError:
    message = (
        f"check_stage at the {stage.value} boundary was given "
        f"{type(before).__name__} and {type(after).__name__}"
    )
    return TypeError(message)


@overload
def check_stage(
    stage: Literal[FidelityBoundary.LAYOUT], before: WordsFile, after: LinesFile
) -> None: ...
@overload
def check_stage(
    stage: Literal[FidelityBoundary.STRUCTURE], before: LinesFile, after: BlocksFile
) -> None: ...
@overload
def check_stage(
    stage: Literal[FidelityBoundary.MARKDOWN], before: BlocksFile, after: MarkdownWords
) -> None: ...
def check_stage(
    stage: FidelityBoundary,
    before: WordsFile | LinesFile | BlocksFile,
    after: LinesFile | BlocksFile | MarkdownWords,
) -> None:
    """Check that no word was lost or invented at one stage boundary.

    layout: the words of words.json against those of lines.json. structure:
    the words of lines.json against those of blocks.json's blocks and notes,
    with each note's marker, plus its removals, with each word change undone.
    markdown: the words of blocks.json, with the edits applied, against
    book.md as `read_markdown` gives it, without note references and the
    markers of referenced notes, and the number of note references against
    Pandoc's notes. The words are compared as multisets over the whole book,
    split on white space, nothing normalised.

    Raises FidelityError with the missing and invented words, their counts,
    and the pages or blocks each came from.
    """
    match stage:
        case FidelityBoundary.LAYOUT:
            if not (isinstance(before, WordsFile) and isinstance(after, LinesFile)):
                raise _wrong_types(stage, before, after)
            _check_words(
                stage, _words_file_words(before), _lines_file_words(after), (), ""
            )
        case FidelityBoundary.STRUCTURE:
            if not (isinstance(before, LinesFile) and isinstance(after, BlocksFile)):
                raise _wrong_types(stage, before, after)
            _check_records(stage, _reference_problems(after))
            _check_words(
                stage,
                _lines_file_words(before),
                _blocks_file_words(after, stage)
                + _removal_words(after)
                + _words_before_changes(after),
                _words_after_changes(after),
                "",
            )
        case FidelityBoundary.MARKDOWN:
            if not (
                isinstance(before, BlocksFile) and isinstance(after, MarkdownWords)
            ):
                raise _wrong_types(stage, before, after)
            reference_count = _note_reference_count(before)
            note_detail = (
                f"note references in blocks.json: {reference_count}; "
                f"notes in the Markdown: {after.note_count}"
                if reference_count != after.note_count
                else ""
            )
            _check_words(
                stage,
                _blocks_file_words(before, stage),
                _markdown_words(after),
                (),
                note_detail,
            )
        case _:
            assert_never(stage)


# Reading book.md with Pandoc

# Spec section 5: Pandoc reads a whole book's Markdown in about a second;
# a minute means it hangs.
_PANDOC_TIMEOUT_S = 60
_PANDOC_ARGUMENTS = ("--from", "markdown-smart", "--to", "json", "--fail-if-warnings")


class _Boundary(StrEnum):
    """Where a word of Pandoc's JSON ends: at a space or line break or the
    start or end of a block element, or at the start of a note, which is
    also counted."""

    BREAK = "break"
    NOTE = "note"


@dataclass(frozen=True, slots=True)
class _Text:
    """The text of one Str element, in the div or heading of `block_id`."""

    text: str
    block_id: str | None


type _Token = _Text | _Boundary


def _not_read(element: str, block_id: str | None) -> ExternalProgramError:
    message = (
        f"Pandoc read the Markdown as a {element} element in block {block_id}, "
        "which galley's Markdown does not make, so its words cannot be checked"
    )
    return ExternalProgramError(message)


def _inline_tokens(inline: object, block_id: str | None) -> tuple[_Token, ...]:
    match inline:
        case {"t": "Str", "c": str() as text}:
            return (_Text(text, block_id),)
        case {"t": "Space" | "SoftBreak" | "LineBreak"}:
            return (_Boundary.BREAK,)
        case {"t": "Emph" | "Strong", "c": list() as inlines}:
            return _inlines_tokens(inlines, block_id)
        case {"t": "Span", "c": [_, list() as inlines]}:
            return _inlines_tokens(inlines, block_id)
        case {"t": "Note", "c": list() as blocks}:
            return (_Boundary.NOTE, *_blocks_tokens(blocks, block_id), _Boundary.BREAK)
        case {"t": str() as element}:
            raise _not_read(element, block_id)
        case _:
            raise _not_read(repr(inline)[:80], block_id)


def _inlines_tokens(inlines: list[object], block_id: str | None) -> tuple[_Token, ...]:
    return tuple(
        token for inline in inlines for token in _inline_tokens(inline, block_id)
    )


def _block_tokens(block: object, block_id: str | None) -> tuple[_Token, ...]:
    """The tokens of a block element, between two breaks. A div or heading
    with an id gives it to the words inside; one without keeps `block_id`."""
    match block:
        case {"t": "Para" | "Plain", "c": list() as inlines}:
            content = _inlines_tokens(inlines, block_id)
        case {"t": "BlockQuote", "c": list() as blocks}:
            content = _blocks_tokens(blocks, block_id)
        case {"t": "Div", "c": [[str() as div_id, *_], list() as blocks]}:
            content = _blocks_tokens(blocks, div_id or block_id)
        case {
            "t": "Header",
            "c": [int(), [str() as heading_id, *_], list() as inlines],
        }:
            content = _inlines_tokens(inlines, heading_id or block_id)
        case {"t": str() as element}:
            raise _not_read(element, block_id)
        case _:
            raise _not_read(repr(block)[:80], block_id)
    return (_Boundary.BREAK, *content, _Boundary.BREAK)


def _blocks_tokens(blocks: list[object], block_id: str | None) -> tuple[_Token, ...]:
    return tuple(token for block in blocks for token in _block_tokens(block, block_id))


def _joined_words(texts: tuple[_Text, ...]) -> tuple[MarkdownWord, ...]:
    """The words of adjacent Str elements: their text joined, then split on
    white space. Every element of one run is in the same block."""
    if not texts:
        return ()
    joined = "".join(text.text for text in texts)
    return tuple(MarkdownWord(word, texts[0].block_id) for word in joined.split())


def _pandoc_words(document: object) -> MarkdownWords:
    """The words of the `blocks` of Pandoc's JSON, not of its `meta`, and
    the number of its Note elements."""
    match document:
        case {"blocks": list() as blocks}:
            tokens = _blocks_tokens(blocks, None)
        case _:
            message = f"Pandoc's JSON has no list of blocks: {repr(document)[:80]}"
            raise ExternalProgramError(message)
    words: list[MarkdownWord] = []
    run: list[_Text] = []
    for token in tokens:
        match token:
            case _Text():
                run.append(token)
            case _Boundary.BREAK | _Boundary.NOTE:
                words.extend(_joined_words(tuple(run)))
                run = []
            case _:
                assert_never(token)
    words.extend(_joined_words(tuple(run)))
    return MarkdownWords(
        words=tuple(words),
        note_count=sum(1 for token in tokens if token is _Boundary.NOTE),
    )


def _stderr_text(stderr: str | bytes | None) -> str:
    match stderr:
        case None:
            return ""
        case bytes():
            return stderr.decode("utf-8", errors="replace").strip()
        case str():
            return stderr.strip()
        case _:
            assert_never(stderr)


def read_markdown(markdown: str) -> MarkdownWords:
    """The words of a Markdown text as Pandoc reads it (`pandoc --from
    markdown-smart --to json --fail-if-warnings`), each with the id of the
    innermost div or heading it is in, and the number of notes.

    Words are split at spaces and line breaks and at the start and end of
    every block and note; emphasis does not split a word. The metadata
    header, the title and authors, gives no words. Raises
    ExternalProgramError, with Pandoc's standard error, when `pandoc` is
    missing, fails or warns (a note definition no reference uses), runs
    longer than 60 s, or reads an element galley's Markdown does not make,
    such as a list.
    """
    pandoc = shutil.which("pandoc")
    if pandoc is None:
        message = "pandoc is not installed; install it with `brew install pandoc`"
        raise ExternalProgramError(message)
    try:
        completed = subprocess.run(
            [pandoc, *_PANDOC_ARGUMENTS],
            input=markdown,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
            timeout=_PANDOC_TIMEOUT_S,
        )
    except subprocess.CalledProcessError as error:
        message = (
            f"pandoc exited with {error.returncode} reading the Markdown: "
            f"{_stderr_text(error.stderr)}"
        )
        raise ExternalProgramError(message) from error
    except subprocess.TimeoutExpired as error:
        message = (
            f"pandoc did not finish reading the Markdown in {_PANDOC_TIMEOUT_S} s: "
            f"{_stderr_text(error.stderr)}"
        )
        raise ExternalProgramError(message) from error
    return _pandoc_words(json.loads(completed.stdout))
