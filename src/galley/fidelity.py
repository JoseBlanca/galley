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
import unicodedata
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal, assert_never, overload

from galley.errors import ExternalProgramError, FidelityBoundary, FidelityError
from galley.model import (
    Block,
    BlocksFile,
    Box,
    ChangeReason,
    LinesFile,
    NoteKind,
    Origin,
    Reread,
    WordChange,
    WordsFile,
    is_under_ocr_word,
)


@dataclass(frozen=True, slots=True)
class MarkdownWord:
    """A word of book.md as Pandoc reads it, with the id of the innermost
    div or heading it is in, or None outside any."""

    text: str
    block_id: str | None


@dataclass(frozen=True, slots=True, kw_only=True)
class MarkdownWords:
    """The words of book.md as Pandoc reads it, in order; the number of
    notes Pandoc found (its Note elements), which references to footnotes
    become; and the number of links marked `epub:type="noteref"`, which
    references to endnotes become."""

    words: tuple[MarkdownWord, ...]
    note_count: int
    note_link_count: int


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
    """The words of words.json, each word's text split like every other
    text, so that "10\xa0000" counts as the same two words as in a block."""
    return tuple(
        placed
        for page in words.pages
        for word in page.words
        for placed in _placed(word.text, f"page {page.index}")
    )


def _lines_file_words(lines: LinesFile) -> tuple[_PlacedWord, ...]:
    """The words of lines.json, split as those of words.json are."""
    return tuple(
        placed
        for page in lines.pages
        for region in page.regions
        for line in region.lines
        for word in line.words
        for placed in _placed(word.text, f"page {page.index}")
    )


def _kept_rereads(lines: LinesFile) -> tuple[Reread, ...]:
    return tuple(reread for reread in lines.rereads if reread.kept)


def _reread_layer_words(lines: LinesFile) -> tuple[_PlacedWord, ...]:
    """The words of words.json that kept re-readings replaced."""
    return tuple(
        placed
        for reread in _kept_rereads(lines)
        for word in reread.layer_words
        for placed in _placed(word.text, f"page {reread.page_index}")
    )


def _reread_ocr_words(lines: LinesFile) -> tuple[_PlacedWord, ...]:
    """Tesseract's words that kept re-readings put in their place."""
    return tuple(
        placed
        for reread in _kept_rereads(lines)
        for word in reread.ocr_words
        for placed in _placed(word.text, f"page {reread.page_index}")
    )


def _box_text(box: Box) -> str:
    return f"({box.x0}, {box.top}, {box.x1}, {box.bottom})"


def _reread_problems(words: WordsFile, lines: LinesFile) -> tuple[str, ...]:
    """What is wrong with the kept re-readings of lines.json: a word of
    their `layer_words` that its page of words.json does not have, or one
    that more kept records name than the page has, compared as page, text
    and box; or one that none of its record's `ocr_words` lies over (reocr
    spec, section 4)."""
    on_pages = Counter(
        (page.index, word.text, word.box) for page in words.pages for word in page.words
    )
    named = Counter(
        (reread.page_index, word.text, word.box)
        for reread in _kept_rereads(lines)
        for word in reread.layer_words
    )
    problems = [
        f"a kept reread replaces {word.text!r} at {_box_text(word.box)} on page "
        f"{reread.page_index}, which none of its ocr_words lies over"
        for reread in _kept_rereads(lines)
        for word in reread.layer_words
        if not is_under_ocr_word(word, reread.ocr_words)
    ]
    for (page_index, text, box), count in named.items():
        where = f"{text!r} at {_box_text(box)}"
        if on_pages[page_index, text, box] == 0:
            problems.append(
                f"a kept reread names {where}, a word page {page_index} does not have"
            )
        elif count > on_pages[page_index, text, box]:
            problems.append(
                f"{where} on page {page_index} is among the layer words of two "
                "kept rereads"
            )
    return tuple(problems)


type _BlocksBoundary = Literal[FidelityBoundary.STRUCTURE, FidelityBoundary.MARKDOWN]


def _block_words(
    block: Block, boundary: _BlocksBoundary, endnote_ids: frozenset[str]
) -> tuple[_PlacedWord, ...]:
    """The words of a block: a heading's label, then its spans split one by
    one. A note reference span is replaced by a space in the block's text,
    so that it does not glue to the word before, and counted as a word of
    its own: at the structure boundary every one, at the markdown boundary
    those to the endnotes of `endnote_ids`, whose links keep their text."""
    place = f"block {block.id} {_pages(block.origin)}"
    label = _placed(block.label, place) if block.label is not None else ()
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
            references = tuple(
                word
                for span in block.spans
                if span.note_ref in endnote_ids
                for word in _placed(span.text, place)
            )
        case _:
            assert_never(boundary)
    return label + _placed(text, place) + references


def _blocks_file_words(
    blocks: BlocksFile, boundary: _BlocksBoundary
) -> tuple[_PlacedWord, ...]:
    """The words of the body and of every note, with each note's marker,
    except at the markdown boundary the marker of a referenced footnote,
    which Pandoc replaces with its own number. An endnote is written where
    it was printed, its marker with it, referenced or not."""
    endnote_ids = _endnote_ids(blocks)
    body = tuple(
        word
        for block in blocks.blocks
        for word in _block_words(block, boundary, endnote_ids)
    )
    notes = tuple(
        word
        for note in blocks.notes
        for block in note.blocks
        for word in _block_words(block, boundary, endnote_ids)
    )
    match boundary:
        case FidelityBoundary.STRUCTURE:
            counted_notes = blocks.notes
        case FidelityBoundary.MARKDOWN:
            counted_notes = tuple(
                note
                for note in blocks.notes
                if not note.referenced or note.kind is NoteKind.ENDNOTE
            )
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


def _endnote_ids(blocks: BlocksFile) -> frozenset[str]:
    return frozenset(note.id for note in blocks.notes if note.kind is NoteKind.ENDNOTE)


def _note_reference_counts(blocks: BlocksFile) -> tuple[int, int]:
    """The number of note reference spans to footnotes, and to endnotes. A
    span that names no note is counted with the footnotes: Pandoc gives it
    no note, so the counts differ."""
    endnote_ids = _endnote_ids(blocks)
    references = tuple(
        span.note_ref
        for block in _all_blocks(blocks)
        for span in block.spans
        if span.note_ref is not None
    )
    to_endnotes = sum(1 for note_id in references if note_id in endnote_ids)
    return len(references) - to_endnotes, to_endnotes


def _note_count_detail(blocks: BlocksFile, markdown: MarkdownWords) -> str:
    """Empty when the references to footnotes are as many as Pandoc's notes
    and those to endnotes as many as the links marked as note references;
    otherwise all four numbers."""
    to_footnotes, to_endnotes = _note_reference_counts(blocks)
    if (to_footnotes, to_endnotes) == (markdown.note_count, markdown.note_link_count):
        return ""
    return (
        f"references to footnotes in blocks.json: {to_footnotes}; "
        f"notes in the Markdown: {markdown.note_count}; "
        f"references to endnotes in blocks.json: {to_endnotes}; "
        f"note reference links in the Markdown: {markdown.note_link_count}"
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


# A marker's shape (architecture section 13): short enough that no word of
# two letters or more fits in it, long enough for "345" and "(12)"; a
# letter only beside a round bracket, for "(i)", "(t)" and the OCR's "U)"
# and "(3J"; no "&" ("&c.") and no dash ("—"), which are words.
_MARKER_MAX_CHARACTERS = 4
_MARKER_MAX_LETTERS_OR_DIGITS = 3
_MARKER_MAX_LETTERS = 1
_MARKER_BRACKETS = frozenset("()")
_NOT_IN_A_MARKER = frozenset("&")


def _has_marker_shape(text: str) -> bool:
    """Whether a note reference span's text has a marker's shape: 1 to 4
    characters, at most 3 of them letters or digits, no white space, "&" or
    dash, and a letter only in a span holding a round bracket, then at most
    one ("8", "^", "345", "(12)", "(i)", "U)")."""
    letters = sum(character.isalpha() for character in text)
    return (
        0 < len(text) <= _MARKER_MAX_CHARACTERS
        and not any(
            character.isspace()
            or character in _NOT_IN_A_MARKER
            or unicodedata.category(character) == "Pd"
            for character in text
        )
        and sum(character.isalnum() for character in text)
        <= _MARKER_MAX_LETTERS_OR_DIGITS
        and (
            letters == 0
            or (
                letters <= _MARKER_MAX_LETTERS
                and any(character in _MARKER_BRACKETS for character in text)
            )
        )
    )


def _reference_problem(
    block: Block, span_text: str, note_ref: str, note_ids: frozenset[str]
) -> str | None:
    """Why a note reference span is wrong, or None when it names a note of
    the file and has a marker's shape."""
    if note_ref not in note_ids:
        return (
            f"block {block.id}: the note reference span {span_text!r} names "
            f"{note_ref}, which is no note"
        )
    if not _has_marker_shape(span_text):
        return (
            f"block {block.id}: the note reference span {span_text!r} does not "
            "have a marker's shape (1 to 4 characters, at most 3 letters or "
            "digits, no white space, '&' or dash, and a letter only beside a "
            "round bracket)"
        )
    return None


def _split_off_words(blocks: BlocksFile) -> Counter[str]:
    """The words that note_marker word changes split off the words they
    were glued to, as a multiset: every word of a change's `after` but its
    first."""
    return Counter(
        word
        for change in blocks.word_changes
        if change.reason is ChangeReason.NOTE_MARKER
        for word in change.after[1:]
    )


def _whole_word_problems(blocks: BlocksFile) -> tuple[str, ...]:
    """The note reference spans with a letter that no note_marker word
    change split off a word: a span that was a whole word of the lines
    holds only digits and symbols (architecture section 13), so that "(a)"
    printed as a word stays a word. Each split-off word accounts for one
    span."""
    split_off = _split_off_words(blocks)
    problems: list[str] = []
    for block in _all_blocks(blocks):
        for span in block.spans:
            if span.note_ref is None or not any(
                character.isalpha() for character in span.text
            ):
                continue
            if split_off[span.text] > 0:
                split_off[span.text] -= 1
            else:
                problems.append(
                    f"block {block.id}: the note reference span {span.text!r} "
                    "holds a letter but was not split off a word by a "
                    "note_marker word change"
                )
    return tuple(problems)


def _reference_problems(blocks: BlocksFile) -> tuple[str, ...]:
    """The note reference spans that name no note of the file, whose text
    does not have a marker's shape, or that hold a letter without having
    been split off a word. A word of the book in a reference span would be
    lost unseen at the markdown boundary, where a span to a footnote becomes
    Pandoc's note. The span need not read as its note's marker: the OCR
    reads the two sides of a superscript differently."""
    note_ids = frozenset(note.id for note in blocks.notes)
    problems = (
        _reference_problem(block, span.text, span.note_ref, note_ids)
        for block in _all_blocks(blocks)
        for span in block.spans
        if span.note_ref is not None
    )
    shape_problems = tuple(problem for problem in problems if problem is not None)
    return shape_problems or _whole_word_problems(blocks)


# A hyphen join is two parts of a word split at a line end (glossary).
_HYPHEN_JOIN_PARTS = 2
# The hyphens at a line's end (structure spec section 5): the ASCII
# hyphen-minus and the not sign "¬" of the OCR of two of the owner's books.
_LINE_END_HYPHENS = frozenset({"-", "\N{NOT SIGN}"})


def _change_follows_its_reason(change: WordChange) -> bool:
    """Whether a word change keeps every letter as its reason allows: a note
    marker split off its word keeps the text; a hyphen join of two parts,
    on evidence or guessed, drops only the hyphen ending the first; a kept
    hyphen joins two parts, the first ending with a hyphen, as they are,
    the hyphen written "-" whether the first ends with "-" or "¬"."""
    if not change.before or not change.after:
        return False
    joined_after = "".join(change.after)
    match change.reason:
        case ChangeReason.NOTE_MARKER:
            return "".join(change.before) == joined_after
        case ChangeReason.HYPHEN_JOIN | ChangeReason.HYPHEN_JOIN_GUESSED:
            return (
                len(change.before) == _HYPHEN_JOIN_PARTS
                and change.before[0][-1:] in _LINE_END_HYPHENS
                and change.before[0][:-1] + change.before[1] == joined_after
            )
        case ChangeReason.HYPHEN_KEPT:
            return (
                len(change.before) == _HYPHEN_JOIN_PARTS
                and change.before[0][-1:] in _LINE_END_HYPHENS
                and change.before[0][:-1] + "-" + change.before[1] == joined_after
            )
        case _:
            assert_never(change.reason)


def _change_problems(blocks: BlocksFile) -> tuple[str, ...]:
    """The word changes that delete or invent words or change a letter,
    which the multiset comparison would take on trust."""
    return tuple(
        f"word change on page {change.page_index}: {change.before!r} to "
        f"{change.after!r} is not a {change.reason.value}"
        for change in blocks.word_changes
        if not _change_follows_its_reason(change)
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

    layout: the words of words.json, less the layer words of every kept
    re-reading of lines.json and with its Tesseract words added, against
    the words of lines.json's lines. structure:
    the words of lines.json against those of blocks.json's blocks and notes,
    with each heading's label and each note's marker, plus its removals,
    with each word change undone. markdown: the words of blocks.json, with
    the edits applied, against book.md as `read_markdown` gives it, without
    the references to footnotes and the markers of referenced footnotes;
    the number of references to footnotes against Pandoc's notes, and to
    endnotes against the links marked as note references, whose text is
    the reference's. The words are compared as multisets over the whole
    book, split on white space, nothing normalised.

    Raises FidelityError with the missing and invented words, their counts,
    and the pages or blocks each came from. At the layout boundary it also
    raises, with no word, when a kept re-reading names a layer word that
    its page of words.json does not have (page, text and box), one that
    another kept re-reading names too, or one that none of its Tesseract
    words lies over. At the structure and markdown
    boundaries it also raises, with no word, when a note reference span
    names no note, does not have a marker's shape (1 to 4 characters, at
    most 3 letters or digits, no white space, "&" or dash, a letter only
    beside a round bracket), or holds a letter without a note_marker word
    change that split it off a word; and at the structure boundary when a
    word change does more than its reason allows (a hyphen join of two
    parts, with the hyphen dropped or kept, a marker split off its word).
    """
    match stage:
        case FidelityBoundary.LAYOUT:
            if not (isinstance(before, WordsFile) and isinstance(after, LinesFile)):
                raise _wrong_types(stage, before, after)
            _check_records(stage, _reread_problems(before, after))
            _check_words(
                stage,
                _words_file_words(before),
                _lines_file_words(after) + _reread_layer_words(after),
                _reread_ocr_words(after),
                "",
            )
        case FidelityBoundary.STRUCTURE:
            if not (isinstance(before, LinesFile) and isinstance(after, BlocksFile)):
                raise _wrong_types(stage, before, after)
            _check_records(stage, _reference_problems(after) + _change_problems(after))
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
            _check_records(stage, _reference_problems(before))
            _check_words(
                stage,
                _blocks_file_words(before, stage),
                _markdown_words(after),
                (),
                _note_count_detail(before, after),
            )
        case _:
            assert_never(stage)


# Reading book.md with Pandoc

# Spec section 5: Pandoc reads a whole book's Markdown in about a second;
# a minute means it hangs.
_PANDOC_TIMEOUT_S = 60
# -auto_identifiers: Pandoc would otherwise give every heading an id made
# from its text, chapter-one, which is no block of book.md (spec section 5).
_PANDOC_ARGUMENTS = (
    "--from",
    "markdown-smart-auto_identifiers",
    "--to",
    "json",
    "--fail-if-warnings",
)


class _Boundary(StrEnum):
    """Where a word of Pandoc's JSON ends: at a space or line break or the
    start or end of a block element, at the start of a note, or at the
    start of a link marked as a note reference; the last two are also
    counted."""

    BREAK = "break"
    NOTE = "note"
    NOTE_LINK = "note_link"


# Architecture section 9: a reference to an endnote is a link with this
# attribute, which Pandoc keeps.
_NOTE_LINK_ATTRIBUTE = ("epub:type", "noteref")


def _is_note_link(attributes: list[object]) -> bool:
    """Whether a link's key-value attributes, as Pandoc's JSON gives them,
    mark it as a note reference."""
    return any(
        isinstance(attribute, list) and tuple(attribute) == _NOTE_LINK_ATTRIBUTE
        for attribute in attributes
    )


@dataclass(frozen=True, slots=True)
class _Text:
    """The text of one Str element, in the div or heading of `block_id`."""

    text: str
    block_id: str | None


type _Token = _Text | _Boundary


def _not_read(element: str, block_id: str | None) -> ExternalProgramError:
    where = f"in block {block_id}" if block_id is not None else "outside any block"
    message = (
        f"Pandoc read the Markdown as a {element} element {where}, "
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
        case {
            "t": "Link",
            "c": [[_, _, list() as attributes], list() as inlines, _],
        } if _is_note_link(attributes):
            # The link's text is the reference to an endnote, a word of its
            # own (architecture section 13).
            return (
                _Boundary.NOTE_LINK,
                *_inlines_tokens(inlines, block_id),
                _Boundary.BREAK,
            )
        case {"t": str() as element}:
            raise _not_read(element, block_id)
        case _:
            raise _not_read(repr(inline)[:80], block_id)


def _inlines_tokens(inlines: list[object], block_id: str | None) -> tuple[_Token, ...]:
    return tuple(
        token for inline in inlines for token in _inline_tokens(inline, block_id)
    )


# Architecture section 13: an image's empty title.
_NO_TITLE = ""


def _has_no_attributes(attributes: object) -> bool:
    """Whether Pandoc's attributes of an element are empty: no id, no
    class, no key and value, which a figure and its image must have
    (architecture section 13)."""
    match attributes:
        case ["", [], []]:
            return True
        case _:
            return False


def _is_figure_image(inline: object, alt: list[object]) -> bool:
    """Whether an inline is an image whose alt text is `alt`, with no
    attributes and no title."""
    match inline:
        case {"t": "Image", "c": [attributes, list() as image_alt, [str(), title]]}:
            return (
                _has_no_attributes(attributes)
                and image_alt == alt
                and title == _NO_TITLE
            )
        case _:
            return False


def _is_galley_figure(
    attributes: object, caption: list[object], body: list[object]
) -> bool:
    """Whether a Figure element is a figure as galley writes it (architecture
    section 13): no attributes, a caption of one Plain block, and a body of
    one Plain block holding only an image whose alt text is the caption."""
    match caption, body:
        case (
            [{"t": "Plain", "c": list() as inlines}],
            [{"t": "Plain", "c": [image]}],
        ):
            return _has_no_attributes(attributes) and _is_figure_image(image, inlines)
        case _:
            return False


def _block_tokens(block: object, block_id: str | None) -> tuple[_Token, ...]:
    """The tokens of a block element, between two breaks. A div or heading
    with an id gives it to the words inside; one without keeps `block_id`.
    A figure gives its caption's words once, and an image without a caption
    alone in a paragraph none (architecture section 13)."""
    match block:
        case {"t": "Para" | "Plain", "c": [image]} if _is_figure_image(image, []):
            content = ()
        case {
            "t": "Figure",
            "c": [attributes, [_, list() as caption], list() as body],
        } if _is_galley_figure(attributes, caption, body):
            content = _blocks_tokens(caption, block_id)
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


def _words_of_pandoc_json(pandoc_json: str) -> MarkdownWords:
    """The words of the `blocks` of Pandoc's JSON, as `pandoc --to json`
    writes it, not of its `meta`, and the number of its Note elements."""
    document = json.loads(pandoc_json)
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
            case _Boundary.BREAK | _Boundary.NOTE | _Boundary.NOTE_LINK:
                words.extend(_joined_words(tuple(run)))
                run = []
            case _:
                assert_never(token)
    words.extend(_joined_words(tuple(run)))
    return MarkdownWords(
        words=tuple(words),
        note_count=sum(1 for token in tokens if token is _Boundary.NOTE),
        note_link_count=sum(1 for token in tokens if token is _Boundary.NOTE_LINK),
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


def _pandoc_json(markdown: str) -> str:
    """Pandoc's JSON of a Markdown text, as text; ExternalProgramError, with
    Pandoc's standard error, when pandoc is missing, fails, warns or runs
    longer than 60 s."""
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
    return completed.stdout


def read_markdown(markdown: str) -> MarkdownWords:
    """The words of a Markdown text as Pandoc reads it (`pandoc --from
    markdown-smart-auto_identifiers --to json --fail-if-warnings`), each with
    the id of the innermost div or heading with an id it is in, the number
    of notes, and the number of links marked `epub:type="noteref"`.

    Words are split at spaces and line breaks, and at the start and end of
    every block, note and link marked as a note reference, whose text is
    read as its own words; emphasis does not split a word. A figure's
    caption is read once, and its image's alt text, which Pandoc copies
    from the caption, not at all. The metadata header, the title and
    authors, gives no words. Raises
    ExternalProgramError, with Pandoc's standard error, when `pandoc` is
    missing, fails or warns (a note definition no reference uses), runs
    longer than 60 s, or reads an element galley's Markdown does not make,
    such as a list, a link that is no note reference, or an image that is
    not alone in its paragraph, whose alt text is not its figure's caption,
    or that has a title or attributes.
    """
    return _words_of_pandoc_json(_pandoc_json(markdown))
