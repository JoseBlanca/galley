"""The fidelity check: no word of the book lost or invented between stages.

`check_stage` compares the words of a stage's input with the words of its
output plus what the stage recorded, as multisets over the whole book, at
three boundaries: layout (words.json against lines.json), structure
(lines.json against blocks.json) and markdown (blocks.json against book.md
as Pandoc reads it). Architecture section 13 and the walking-skeleton spec,
section 5, say which words each side holds.
"""

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal, assert_never, overload

from galley.errors import FidelityBoundary, FidelityError
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


def _note_reference_count(blocks: BlocksFile) -> int:
    all_blocks = blocks.blocks + tuple(
        block for note in blocks.notes for block in note.blocks
    )
    return sum(
        1 for block in all_blocks for span in block.spans if span.note_ref is not None
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
