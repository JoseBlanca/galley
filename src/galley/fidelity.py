"""The fidelity check: no word of the book lost or invented between stages.

`check_stage` compares the words of a stage's input with the words of its
output plus what the stage recorded, as multisets over the whole book, at
three boundaries: layout (words.json against lines.json), structure
(lines.json against blocks.json) and markdown (blocks.json against book.md
as Pandoc reads it). Architecture section 13 and the walking-skeleton spec,
section 5, say which words each side holds.
"""

import json
import re
import shutil
import subprocess
import unicodedata
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal, assert_never, overload

from galley.contents_labels import contents_runs, inferred_labels
from galley.errors import ExternalProgramError, FidelityBoundary, FidelityError
from galley.hyphens import LINE_END_HYPHENS
from galley.list_markers import (
    DASHES,
    ListMarker,
    MarkerKind,
    is_bulleted,
    marker_readings,
)
from galley.model import (
    Block,
    BlockKind,
    BlocksFile,
    Box,
    ChangeReason,
    LinesFile,
    NoteKind,
    Origin,
    RemovalReason,
    Reread,
    Word,
    WordChange,
    WordsFile,
    block_text,
    is_junk_beside_its_copy,
    may_read,
    replaced_layer_words,
    take_out_once,
)
from galley.note_references import is_punctuation


@dataclass(frozen=True, slots=True)
class MarkdownWord:
    """A word of book.md as Pandoc reads it, with the id of the innermost
    div or heading it is in, or None outside any."""

    text: str
    block_id: str | None


@dataclass(frozen=True, slots=True)
class ContentsLink:
    """A link in the div of a contents entry of book.md, as Pandoc reads it:
    the id of that div, and the link's target as written, `#b-p0036-001`."""

    block_id: str | None
    target: str


@dataclass(frozen=True, slots=True)
class ShownMarker:
    """The marker Pandoc shows for an item of a list of list items: the id
    of the item's div; for an ordered list the item's number, its style
    and delimiter as Pandoc's JSON names them ("Decimal", "Period"); for a
    bullet list None and empty names."""

    block_id: str | None
    number: int | None
    style: str
    delimiter: str


@dataclass(frozen=True, slots=True, kw_only=True)
class MarkdownWords:
    """The words of book.md as Pandoc reads it, in order; the number of
    notes Pandoc found (its Note elements), which references to footnotes
    become; the number of links marked `epub:type="noteref"`, which
    references to endnotes become; the number of links with the role
    `doc-backlink`, which the markers of referenced endnotes become
    (architecture section 9, "Back links"); the number of items of the lists of
    list items, each a list item of blocks.json; the marker Pandoc shows
    for each of those items; and the links of the contents entries, in
    order (structure spec section 31)."""

    words: tuple[MarkdownWord, ...]
    note_count: int
    note_link_count: int
    back_link_count: int
    list_item_count: int
    shown_markers: tuple[ShownMarker, ...]
    contents_links: tuple[ContentsLink, ...]


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


# The fidelity check has no word list: no layer word is known to it
# (reocr spec, section 4).
_NO_KNOWN_WORDS: frozenset[str] = frozenset()


def _unmatched(reread: Reread) -> tuple[Word, ...]:
    """The `layer_words` of `reread` that `replaced_layer_words` does not
    match to one of its `ocr_words`, each as many times as it is
    unmatched."""
    (unmatched,) = take_out_once(
        (reread.layer_words,),
        # Without the book's word list every layer word is unknown, so this
        # accepts every glued misreading layout matched (reocr spec,
        # section 4).
        replaced_layer_words(
            reread.layer_words,
            reread.ocr_words,
            is_known=_NO_KNOWN_WORDS.__contains__,
            # The junk under a word paired with its copy is the junk layout
            # named, by its word list, which this check has not.
            is_junk=lambda word, _ocr_word: word in reread.junk_words,
        ),
    )
    return unmatched


def _share_a_line(first: Word, second: Word) -> bool:
    """Whether the boxes of `first` and `second` overlap up and down, as
    the words of one printed line do."""
    return first.box.top < second.box.bottom and second.box.top < first.box.bottom


def _one_reading_of_two_lines(reread: Reread) -> tuple[str, ...]:
    """A problem for each Tesseract word of `reread` that is the only one
    of its `ocr_words` that may read two of its `layer_words` of different
    printed lines (`model.may_read`): it would stand for two printed words.
    Independent of `model.replaced_layer_words`, the pairing layout made.
    The layer's junk under it beside the layer's copy of its word is no
    such pair (`model.is_junk_beside_its_copy`)."""
    sole_readings: dict[int, list[Word]] = {}
    for word in reread.layer_words:
        readings = tuple(
            position
            for position, ocr_word in enumerate(reread.ocr_words)
            if may_read(word, ocr_word)
        )
        if len(readings) == 1:
            sole_readings.setdefault(readings[0], []).append(word)
    return tuple(
        f"a kept reread on page {reread.page_index} has {ocr_word.text!r} at "
        f"{_box_text(ocr_word.box)} as the only ocr word that can read "
        f"{first.text!r} and {second.text!r}, of two printed lines"
        for position, layer_words in sorted(sole_readings.items())
        for ocr_word in (reread.ocr_words[position],)
        for index, first in enumerate(layer_words)
        for second in layer_words[index + 1 :]
        if not _share_a_line(first, second)
        # The layer's junk under the word and its copy of the word beside
        # it: one printed word read twice (reocr spec, section 4).
        and not (
            first in reread.junk_words
            and is_junk_beside_its_copy(first, second, ocr_word)
        )
        and not (
            second in reread.junk_words
            and is_junk_beside_its_copy(second, first, ocr_word)
        )
    )


def _reread_problems(words: WordsFile, lines: LinesFile) -> tuple[str, ...]:
    """What is wrong with the kept re-readings of lines.json: a word of
    their `layer_words` that its page of words.json does not have, or one
    that more kept records name than the page has, compared as page, text
    and box; or one that is not the same printed word as one of its
    record's `ocr_words`, by `model.replaced_layer_words` (reocr spec,
    section 4); or a Tesseract word that is the only one of its record
    that may read two of its layer words of different printed lines
    (architecture section 13); or a word of its `junk_words` that is not
    among its `layer_words`."""
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
        f"{reread.page_index}, which none of its ocr_words lies over or reads"
        for reread in _kept_rereads(lines)
        for word in _unmatched(reread)
    ]
    problems.extend(
        problem
        for reread in _kept_rereads(lines)
        for problem in _one_reading_of_two_lines(reread)
    )
    problems.extend(
        f"a kept reread on page {reread.page_index} names {word.text!r} at "
        f"{_box_text(word.box)} as junk, which is not among its layer words"
        for reread in _kept_rereads(lines)
        for word in take_out_once((reread.junk_words,), reread.layer_words)[0]
    )
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
    """The words of a block: its label, whatever its kind but at the
    markdown boundary a list item's, which markdown does not write, then
    its spans split one by one, then an epigraph's source, and at the
    structure boundary a contents entry's page number, which markdown does
    not write (structure spec section 31). A note reference span is replaced
    by a space in the block's text,
    so that it does not glue to the word before, and counted as a word of
    its own: at the structure boundary every one, at the markdown boundary
    those to the endnotes of `endnote_ids`, whose links keep their text."""
    place = f"block {block.id} {_pages(block.origin)}"
    label = (
        _placed(block.label, place)
        if block.label is not None
        and not (
            boundary is FidelityBoundary.MARKDOWN and block.kind is BlockKind.LIST_ITEM
        )
        else ()
    )
    source = _placed(block.source, place) if block.source is not None else ()
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
            page_number = (
                _placed(block.page_number, place)
                if block.page_number is not None
                else ()
            )
        case FidelityBoundary.MARKDOWN:
            references = tuple(
                word
                for span in block.spans
                if span.note_ref in endnote_ids
                for word in _placed(span.text, place)
            )
            page_number = ()
        case _:
            assert_never(boundary)
    return label + _placed(text, place) + source + references + page_number


def _blocks_file_words(
    blocks: BlocksFile, boundary: _BlocksBoundary
) -> tuple[_PlacedWord, ...]:
    """The words of the body and of every note, with each note's marker,
    except at the markdown boundary the marker of a referenced footnote,
    which Pandoc replaces with its own number, and each note's group. An
    endnote is written where it was printed, its marker with it, referenced
    or not, and its group in the div before it."""
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
    groups = tuple(
        word
        for note in blocks.notes
        if note.group is not None
        for word in _placed(note.group, f"note {note.id} {_pages(note.origin)}")
    )
    return body + notes + markers + groups


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


def _back_link_count_detail(blocks: BlocksFile, markdown: MarkdownWords) -> str:
    """Empty when the links with the role `doc-backlink` are as many as the
    endnotes with `referenced` true and a marker (architecture section 9,
    "Back links"); otherwise both numbers."""
    back_linked = sum(
        1
        for note in blocks.notes
        if note.kind is NoteKind.ENDNOTE and note.referenced and note.marker.strip()
    )
    if back_linked == markdown.back_link_count:
        return ""
    return (
        f"referenced endnotes with a marker in blocks.json: {back_linked}; "
        f"back links in the Markdown: {markdown.back_link_count}"
    )


def _list_count_detail(blocks: BlocksFile, markdown: MarkdownWords) -> str:
    """Empty when the list items of blocks.json are as many as the items of
    the lists of list items in the Markdown, and the contents entries with
    a heading reference as many as the contents links; otherwise the
    numbers that differ (structure spec section 31)."""
    every_block = _all_blocks(blocks)
    list_items = sum(1 for block in every_block if block.kind is BlockKind.LIST_ITEM)
    linked = sum(1 for block in every_block if block.heading_ref is not None)
    items_detail = (
        f"list items in blocks.json: {list_items}; items of lists of list "
        f"items in the Markdown: {markdown.list_item_count}"
        if list_items != markdown.list_item_count
        else ""
    )
    links_detail = (
        f"contents entries with a heading reference in blocks.json: {linked}; "
        f"contents links in the Markdown: {len(markdown.contents_links)}"
        if linked != len(markdown.contents_links)
        else ""
    )
    return "; ".join(detail for detail in (items_detail, links_detail) if detail)


# Structure spec section 31: the style and delimiter Pandoc's JSON names
# for each kind and form of an ordered list's marker.
_PANDOC_STYLES = frozendict(
    {
        (MarkerKind.NUMBER, False): "Decimal",
        (MarkerKind.LETTER, False): "LowerAlpha",
        (MarkerKind.LETTER, True): "UpperAlpha",
        (MarkerKind.ROMAN, False): "LowerRoman",
        (MarkerKind.ROMAN, True): "UpperRoman",
    }
)
_PANDOC_DELIMITERS = frozendict({".": "Period", ")": "OneParen", "()": "TwoParens"})


def _shows(marker: ListMarker, shown: ShownMarker) -> bool:
    """Whether `shown`, what Pandoc shows for an item, is the reading
    `marker` of its label (structure spec section 31)."""
    if is_bulleted(marker) or shown.number is None:
        return is_bulleted(marker) and shown.number is None
    upper = any(character.isupper() for character in marker.form)
    sign = "".join(c for c in marker.form if not c.isalnum())
    return (
        shown.number == marker.value
        and _PANDOC_STYLES.get((marker.kind, upper)) == shown.style
        and _PANDOC_DELIMITERS.get(sign) == shown.delimiter
    )


def _shown_marker_problems(
    blocks: BlocksFile, markdown: MarkdownWords
) -> tuple[str, ...]:
    """The items of lists whose marker in the Markdown, as Pandoc shows it,
    is no reading of their list item's label (structure spec section 31)."""
    labels = {
        block.id: block.label
        for block in _all_blocks(blocks)
        if block.kind is BlockKind.LIST_ITEM
    }
    return tuple(
        f"the list item {shown.block_id} shows the marker "
        f"{shown.number} {shown.style} {shown.delimiter} where its label is "
        f"{labels.get(shown.block_id or '')!r}"
        for shown in markdown.shown_markers
        if not any(
            _shows(marker, shown)
            for marker in marker_readings(labels.get(shown.block_id or "") or "")
        )
    )


# Structure spec section 30, "Terms": the words of a page number, a
# page-number form (1 to 3 digits, or a roman numeral in lower case, with
# at most one "." or "," after it) or a range of two, with "pp." or "p."
# before it. Written here, as the fidelity check reads no stage's code.
_PAGE_FORM = (
    r"(?:[0-9]{1,3}"
    r"|(?=[ivxlcdm])m{0,3}(?:cm|cd|d?c{0,3})(?:xc|xl|l?x{0,3})(?:ix|iv|v?i{0,3}))"
    r"[.,]?"
)
_PAGE_NUMBER = re.compile(
    rf"(?:pp?\. )?(?:{_PAGE_FORM}|{_PAGE_FORM} ?[-–—] ?{_PAGE_FORM})"
)


def _page_number_problems(blocks: BlocksFile) -> tuple[str, ...]:
    """The contents entries whose page number, which markdown does not
    write, has no page number's form (structure spec section 31)."""
    return tuple(
        f"block {block.id} has the page number {block.page_number!r}, which "
        "has no page number's form and would not be in the Markdown"
        for block in _all_blocks(blocks)
        if block.page_number is not None
        and _PAGE_NUMBER.fullmatch(block.page_number) is None
    )


# Architecture section 9: a link's target in book.md is "#" and an id.
_LINK_TARGET_PREFIX = "#"


def _contents_link_problems(
    blocks: BlocksFile, markdown: MarkdownWords
) -> tuple[str, ...]:
    """The contents links whose target is not "#" and the id of a heading
    block of blocks.json (structure spec section 31), and those to a
    heading that is not the one their entry's heading_ref names."""
    every_block = _all_blocks(blocks)
    headings = frozenset(
        _LINK_TARGET_PREFIX + block.id
        for block in every_block
        if block.kind is BlockKind.HEADING
    )
    references = {
        block.id: _LINK_TARGET_PREFIX + block.heading_ref
        for block in every_block
        if block.heading_ref is not None
    }
    not_headings = tuple(
        f"the contents entry {link.block_id} links to {link.target!r}, which is "
        "not the id of a heading block"
        for link in markdown.contents_links
        if link.target not in headings
    )
    other_headings = tuple(
        f"the contents entry {link.block_id} links to {link.target!r}, and its "
        f"heading reference is {references.get(link.block_id or '')!r}"
        for link in markdown.contents_links
        if link.target in headings
        and references.get(link.block_id or "") != link.target
    )
    return not_headings + other_headings


def _places(words: Iterable[_PlacedWord], text: str) -> str:
    places = tuple(dict.fromkeys(word.place for word in words if word.text == text))
    return ", ".join(places) if places else "none"


def _inside(box: Box, origin: tuple[Origin, ...], page_index: int) -> bool:
    """Whether the centre of `box`, on page `page_index`, lies in the box of
    an origin on that page."""
    x = (box.x0 + box.x1) / 2
    y = (box.top + box.bottom) / 2
    return any(
        part.page_index == page_index
        and part.box.x0 <= x <= part.box.x1
        and part.box.top <= y <= part.box.bottom
        for part in origin
    )


def _label_lack(block: Block, page_words: frozendict[int, tuple[Word, ...]]) -> int:
    """How many more times a contents entry block holds its label than the
    words of lines.json inside its origin do (structure spec section 31):
    0 for a label that was read."""
    if block.label is None:
        return 0
    held = sum(
        word == block.label
        for word in (
            *block.label.split(),
            *block_text(block).split(),
            *(block.page_number or "").split(),
        )
    )
    read = sum(
        part == block.label
        for page_index in dict.fromkeys(part.page_index for part in block.origin)
        for word in page_words.get(page_index, ())
        if _inside(word.box, block.origin, page_index)
        for part in word.text.split()
    )
    return max(held - read, 0)


def _inferred_label_words(
    lines: LinesFile, blocks: BlocksFile, contents_pages: frozenset[int]
) -> Counter[str]:
    """The labels of contents entry blocks that rule 12 of structure spec
    section 30 inferred, as the check admits them (section 31): in each
    contents run of `contents_pages`, the labels that their blocks hold
    more often than their lines are set to none, rule 12 is applied, and
    each such label that it gives back to its own block is counted as
    many times as the block lacks it."""
    page_words = frozendict(
        {
            page.index: tuple(
                word
                for region in page.regions
                for line in region.lines
                for word in line.words
            )
            for page in lines.pages
        }
    )
    entries = tuple(b for b in blocks.blocks if b.kind is BlockKind.CONTENTS_ENTRY)
    admitted: Counter[str] = Counter()
    for run in contents_runs(contents_pages):
        in_run = tuple(b for b in entries if b.origin and b.origin[0].page_index in run)
        lacks = tuple(_label_lack(block, page_words) for block in in_run)
        given = inferred_labels(
            tuple(
                None if lack else block.label
                for block, lack in zip(in_run, lacks, strict=True)
            ),
            tuple(block.level or 0 for block in in_run),
        )
        for position, (block, lack) in enumerate(zip(in_run, lacks, strict=True)):
            if lack and block.label is not None and given.get(position) == block.label:
                admitted[block.label] += lack
    return admitted


def _check_words(
    boundary: FidelityBoundary,
    input_words: tuple[_PlacedWord, ...],
    output_words: tuple[_PlacedWord, ...],
    taken_out: tuple[_PlacedWord, ...],
    note_detail: str,
    *,
    admitted: Counter[str],
) -> None:
    """Raise FidelityError when the input words, as a multiset, are not the
    output words less those taken out, or when `note_detail` reports a
    difference in the note counts; return otherwise. A word of `admitted`
    that the output holds more often than the input is not invented, up
    to its count there."""
    difference = Counter(word.text for word in input_words)
    difference.subtract(word.text for word in output_words)
    difference.update(word.text for word in taken_out)
    for text, count in admitted.items():
        if difference[text] < 0:
            difference[text] += min(count, -difference[text])
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
# The one letter a footnote reference may be without a round bracket:
# Domesday's OCR reads a raised number glued to its word as a capital "V"
# ("adquesieritV", page 53), which structure links only between two linked
# neighbours (architecture section 13; owner, 23 November 2026). The part
# of the word before it ends with two lower-case letters, so that a roman
# numeral ("IV", "XV") or a capital word keeps its "V".
_TRAILING_V = "V"
_BEFORE_A_TRAILING_V = re.compile(r".*[a-z]{2}")


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
    block: Block,
    span_text: str,
    note_ref: str,
    footnote_ids: frozenset[str],
    endnote_ids: frozenset[str],
) -> str | None:
    """Why a note reference span is wrong, or None when it names a note of
    the file and has a marker's shape, or is a trailing "V" that names a
    footnote."""
    if note_ref not in footnote_ids | endnote_ids:
        return (
            f"block {block.id}: the note reference span {span_text!r} names "
            f"{note_ref}, which is no note"
        )
    if span_text == _TRAILING_V and note_ref in footnote_ids:
        return None
    if not _has_marker_shape(span_text):
        return (
            f"block {block.id}: the note reference span {span_text!r} does not "
            "have a marker's shape (1 to 4 characters, at most 3 letters or "
            "digits, no white space, '&' or dash, and a letter only beside a "
            "round bracket, or a trailing 'V' to a footnote)"
        )
    return None


def _split_off_words(blocks: BlocksFile) -> Counter[str]:
    """The words that note_marker word changes split off the words they
    were glued to, as a multiset: every word of a change's `after` but its
    first, and a "V" only off the end of a word: the part before it ends
    with two lower-case letters and every part after it is punctuation
    ("adquesierit", "V", ".")."""
    return Counter(
        word
        for change in blocks.word_changes
        if change.reason is ChangeReason.NOTE_MARKER
        for place, word in enumerate(change.after[1:], start=1)
        if word != _TRAILING_V
        or (
            _BEFORE_A_TRAILING_V.fullmatch(change.after[place - 1]) is not None
            and all(is_punctuation(rest) for rest in change.after[place + 1 :])
        )
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
    footnote_ids = frozenset(
        note.id for note in blocks.notes if note.kind is NoteKind.FOOTNOTE
    )
    endnote_ids = frozenset(
        note.id for note in blocks.notes if note.kind is not NoteKind.FOOTNOTE
    )
    problems = (
        _reference_problem(block, span.text, span.note_ref, footnote_ids, endnote_ids)
        for block in _all_blocks(blocks)
        for span in block.spans
        if span.note_ref is not None
    )
    shape_problems = tuple(problem for problem in problems if problem is not None)
    return shape_problems or _whole_word_problems(blocks)


# A hyphen join is two parts of a word split at a line end (glossary).
_HYPHEN_JOIN_PARTS = 2
# The signs of a note reference that the OCR reads in place of a line-end
# hyphen, which a hyphen join takes off and structure records as removed
# (structure spec section 5, "A hyphen read as a sign"). Written here again,
# not imported from structure's _hyphens.py, for the reason given for
# _SOURCE_DASHES below.
_HYPHEN_SIGNS = frozenset("^*•")
# The dashes that may start an epigraph's source line, alone or several
# (structure spec section 22, rule 3). Written here again, not imported
# from structure's _epigraphs.py: the check states its rules on its own,
# so that a change to the stage does not change what it is checked
# against.
_SOURCE_DASHES = "\u2014\u2013-"
# A spaced sign is attached to the one word before it, and a word glued
# at a case change is split in two (structure spec sections 23 and 24).
_PUNCTUATION_ATTACHED_PARTS = 2
# Written here again, not imported from structure's _spaced.py, for the
# reason given for _SOURCE_DASHES.
_SPACED_SIGNS = frozenset("?;:!")
_CASE_SPLIT_PARTS = 2
# A list item's dash split off its first word: the dash and the word
# (structure spec section 29, "Blocks").
_LIST_MARKER_PARTS = 2
# The changes structure makes after the joins of lost hyphens (structure
# spec section 2, the paragraph after the steps).
_CHANGES_AFTER_A_JOIN = frozenset(
    {ChangeReason.PUNCTUATION_ATTACHED, ChangeReason.CASE_SPLIT}
)


def _is_source_dash(change: WordChange) -> bool:
    """Whether a source_dash change takes the dashes off the start of an
    epigraph's source and nothing else: one word that starts with a dash,
    or a word of dashes alone and the word after, become the one word
    without them (structure spec section 22)."""
    match change.before:
        case (word,) if word[:1] in _SOURCE_DASHES:
            undashed = word.lstrip(_SOURCE_DASHES)
        case (dashes, word) if dashes and not dashes.strip(_SOURCE_DASHES):
            undashed = word.lstrip(_SOURCE_DASHES)
        case _:
            return False
    return bool(undashed) and change.after == (undashed,)


def is_sign_join(change: WordChange) -> bool:
    """Whether `change`, a hyphen join, is one over a sign read in place of
    the hyphen (structure spec section 5): two parts, the first ending with
    a sign of `_HYPHEN_SIGNS` after a letter, become the first without the
    sign followed by the second, and then the sign, which a removal records
    (`_sign_problems`). Structure records those removals by the same test."""
    if len(change.before) != _HYPHEN_JOIN_PARTS:
        return False
    first, second = change.before
    sign = first[-1:]
    return (
        sign in _HYPHEN_SIGNS
        and first[-2:-1].isalpha()
        and change.after == (first[:-1] + second, sign)
    )


def _sign_problems(blocks: BlocksFile) -> tuple[str, ...]:
    """The pages and signs whose hyphen joins over a sign and removals of
    the reason `misread_hyphen` differ in number: each such join needs one
    removal of its sign on its page, and each such removal its join
    (structure spec section 5)."""
    joins = Counter(
        (change.page_index, change.after[-1])
        for change in blocks.word_changes
        if change.reason is ChangeReason.HYPHEN_JOIN and is_sign_join(change)
    )
    removed = Counter(
        (removal.page_index, removal.text)
        for removal in blocks.removals
        if removal.reason is RemovalReason.MISREAD_HYPHEN
    )
    return tuple(
        f"page {page}: {joins[page, sign]} hyphen join(s) over the sign "
        f"{sign!r}, but {removed[page, sign]} misread_hyphen removal(s) of it"
        for page, sign in sorted(joins.keys() | removed.keys())
        if removed[page, sign] != joins[page, sign]
    )


def _change_follows_its_reason(change: WordChange) -> bool:
    """Whether a word change keeps every letter as its reason allows: a note
    marker split off its word keeps the text; a hyphen join of two parts,
    on evidence or guessed, drops only the hyphen ending the first; a kept
    hyphen joins two parts, the first ending with a hyphen, as they are,
    the hyphen written "-" whether the first ends with "-" or "¬"; a lost
    hyphen joins two parts as they are, but for one full stop ending the
    first; a source dash is taken off a source's first word; a spaced
    sign is attached to the word before it; a word glued at a case change
    becomes two whose second starts with a capital; a list item's dash,
    "—" or "–", is split off the word it starts."""
    if not change.before or not change.after:
        return False
    joined_after = "".join(change.after)
    match change.reason:
        case ChangeReason.NOTE_MARKER:
            return "".join(change.before) == joined_after
        case ChangeReason.HYPHEN_JOIN if is_sign_join(change):
            return True
        case ChangeReason.HYPHEN_JOIN | ChangeReason.HYPHEN_JOIN_GUESSED:
            return (
                len(change.before) == _HYPHEN_JOIN_PARTS
                and change.before[0][-1:] in LINE_END_HYPHENS
                and change.before[0][:-1] + change.before[1] == joined_after
            )
        case ChangeReason.HYPHEN_LOST:
            return (
                len(change.before) == _HYPHEN_JOIN_PARTS
                and change.before[0].removesuffix(".") + change.before[1]
                == joined_after
            )
        case ChangeReason.HYPHEN_KEPT:
            return (
                len(change.before) == _HYPHEN_JOIN_PARTS
                and change.before[0][-1:] in LINE_END_HYPHENS
                and change.before[0][:-1] + "-" + change.before[1] == joined_after
            )
        case ChangeReason.SOURCE_DASH:
            return _is_source_dash(change)
        case ChangeReason.PUNCTUATION_ATTACHED:
            return (
                len(change.before) == _PUNCTUATION_ATTACHED_PARTS
                and len(change.after) == 1
                and change.before[1][:1] in _SPACED_SIGNS
                and "".join(change.before) == joined_after
            )
        case ChangeReason.CASE_SPLIT:
            return (
                len(change.before) == 1
                and len(change.after) == _CASE_SPLIT_PARTS
                and all(change.after)
                and change.after[1][0].isupper()
                and change.before[0] == joined_after
            )
        case ChangeReason.LIST_MARKER:
            return (
                len(change.before) == 1
                and len(change.after) == _LIST_MARKER_PARTS
                and change.after[0] in DASHES
                and bool(change.after[1])
                and change.before[0] == joined_after
            )
        case _:
            assert_never(change.reason)


def _margin_note_words(blocks: BlocksFile) -> frozenset[tuple[int, str]]:
    """The words of the margin-note blocks, each with the page its block
    starts on."""
    return frozenset(
        (block.origin[0].page_index, word)
        for block in _all_blocks(blocks)
        if block.kind is BlockKind.MARGIN_NOTE
        for span in block.spans
        for word in span.text.split()
    )


def _margin_note_words_before_changes(
    blocks: BlocksFile,
) -> frozenset[tuple[int, str]]:
    """The words of the margin-note blocks, as `_margin_note_words` gives
    them, and every word that a chain of signs attached and case splits
    turned into such words on their page (structure spec section 5): a
    join of a lost hyphen comes before both, so its word may be one of
    these ("theWilliam" split into "the" "William", then "William;").
    A word is added only when every word of the change's `after` already
    is one, so a join is admitted only when the words its chain ends in
    are words of a margin note of its page, as without the chain."""
    words = _margin_note_words(blocks)
    later = tuple(
        change
        for change in blocks.word_changes
        if change.reason in _CHANGES_AFTER_A_JOIN
    )
    while True:
        undone = frozenset(
            (change.page_index, change.before[0])
            for change in later
            if all((change.page_index, word) in words for word in change.after)
        )
        if undone <= words:
            return words
        words |= undone


def _source_first_words(blocks: BlocksFile) -> frozenset[tuple[int, str]]:
    """The first word of the source of each epigraph, with each page the
    epigraph has a part on."""
    return frozenset(
        (origin.page_index, words[0])
        for block in _all_blocks(blocks)
        if block.kind is BlockKind.EPIGRAPH and block.source is not None
        for words in (block.source.split(),)
        if words
        for origin in block.origin
    )


def _change_problems(blocks: BlocksFile) -> tuple[str, ...]:
    """The word changes that delete or invent words or change a letter,
    which the multiset comparison would take on trust, the joins of a lost
    hyphen whose word is in no margin note of their page (structure spec
    section 5), and the source dashes taken off a word that is not the
    first of an epigraph's source on their page (section 22)."""
    in_margin_notes = _margin_note_words_before_changes(blocks)
    source_first_words = _source_first_words(blocks)
    return (
        tuple(
            f"word change on page {change.page_index}: {change.before!r} to "
            f"{change.after!r} is not a {change.reason.value}"
            for change in blocks.word_changes
            if not _change_follows_its_reason(change)
        )
        + tuple(
            f"word change on page {change.page_index}: {change.after!r}, a "
            f"{change.reason.value}, is not in a margin note"
            for change in blocks.word_changes
            if change.reason is ChangeReason.HYPHEN_LOST
            and _change_follows_its_reason(change)
            and (change.page_index, change.after[0]) not in in_margin_notes
        )
        + tuple(
            f"word change on page {change.page_index}: {change.after!r}, a "
            f"{change.reason.value}, is not the first word of an epigraph's source"
            for change in blocks.word_changes
            if change.reason is ChangeReason.SOURCE_DASH
            and _change_follows_its_reason(change)
            and (change.page_index, change.after[0]) not in source_first_words
        )
    )


def _source_problems(blocks: BlocksFile) -> tuple[str, ...]:
    """The blocks that are not epigraphs and have a source, whose words
    would be counted at the structure boundary but which markdown does not
    write (structure spec section 7)."""
    return tuple(
        f"block {block.id} is a {block.kind.value} and has the source "
        f"{block.source!r}; only an epigraph has a source"
        for block in _all_blocks(blocks)
        if block.source is not None and block.kind is not BlockKind.EPIGRAPH
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
    stage: Literal[FidelityBoundary.STRUCTURE],
    before: LinesFile,
    after: BlocksFile,
    *,
    contents_pages: frozenset[int] = ...,
) -> None: ...
@overload
def check_stage(
    stage: Literal[FidelityBoundary.MARKDOWN], before: BlocksFile, after: MarkdownWords
) -> None: ...
def check_stage(
    stage: FidelityBoundary,
    before: WordsFile | LinesFile | BlocksFile,
    after: LinesFile | BlocksFile | MarkdownWords,
    *,
    contents_pages: frozenset[int] = frozenset(),
) -> None:
    """Check that no word was lost or invented at one stage boundary.

    layout: the words of words.json, less the layer words of every kept
    re-reading of lines.json and with its Tesseract words added, against
    the words of lines.json's lines. structure:
    the words of lines.json against those of blocks.json's blocks and notes,
    with each block's label, each epigraph's source, each contents entry's
    page number, and each note's marker and group, plus its removals,
    with each word change undone, admitting a contents entry's label that
    rule 12 of the structure spec inferred: one that the words of
    lines.json inside its block lack and that rule 12, applied to the
    entries of its contents run of `contents_pages` (page indices from 0,
    the config's), gives back to that block. markdown: the words of blocks.json, with
    the edits applied, against book.md as `read_markdown` gives it, without
    the references to footnotes and the markers of referenced footnotes,
    and without the dash markdown writes before an epigraph's source;
    the number of references to footnotes against Pandoc's notes, and to
    endnotes against the links marked as note references, whose text is
    the reference's; without a list item's label, which is not written,
    and a contents entry's page number; the number of list items against
    the items of Pandoc's lists of list items, and of contents entries with
    a heading reference against the links of contents entries, each of which
    must target the heading its entry's heading_ref names. The words are
    compared as multisets over the whole book, split on white space, nothing
    normalised.

    Raises FidelityError with the missing and invented words, their counts,
    and the pages or blocks each came from. At the layout boundary it also
    raises, with no word, when a kept re-reading names a layer word that
    its page of words.json does not have (page, text and box), one that
    another kept re-reading names too, or one that none of its Tesseract
    words lies over. At the structure and markdown
    boundaries it also raises, with no word, when a note reference span
    names no note, does not have a marker's shape (1 to 4 characters, at
    most 3 letters or digits, no white space, "&" or dash, a letter only
    beside a round bracket) and is not a "V" to a footnote, or holds a
    letter without a note_marker word change that split it off a word (a
    "V" off a word whose part before it ends with two lower-case letters),
    or when a block that is not an
    epigraph has a source; at the markdown boundary when a contents link
    targets anything but "#" and the id of a heading block, or a heading
    other than its entry's heading_ref; and at the
    structure boundary when a word
    change does more than its reason allows (a hyphen join of two parts,
    with the hyphen dropped or kept, a marker split off its word, the
    dashes taken off a source, a spaced sign attached, a word split at a
    case change, a list item's dash split off its word).
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
                admitted=Counter(),
            )
        case FidelityBoundary.STRUCTURE:
            if not (isinstance(before, LinesFile) and isinstance(after, BlocksFile)):
                raise _wrong_types(stage, before, after)
            _check_records(
                stage,
                _source_problems(after)
                + _reference_problems(after)
                + _change_problems(after)
                + _sign_problems(after),
            )
            _check_words(
                stage,
                _lines_file_words(before),
                _blocks_file_words(after, stage)
                + _removal_words(after)
                + _words_before_changes(after),
                _words_after_changes(after),
                "",
                admitted=_inferred_label_words(before, after, contents_pages),
            )
        case FidelityBoundary.MARKDOWN:
            if not (
                isinstance(before, BlocksFile) and isinstance(after, MarkdownWords)
            ):
                raise _wrong_types(stage, before, after)
            _check_records(
                stage,
                _source_problems(before)
                + _reference_problems(before)
                + _contents_link_problems(before, after)
                + _shown_marker_problems(before, after)
                + _page_number_problems(before),
            )
            _check_words(
                stage,
                _blocks_file_words(before, stage),
                _markdown_words(after),
                (),
                "; ".join(
                    detail
                    for detail in (
                        _note_count_detail(before, after),
                        _back_link_count_detail(before, after),
                        _list_count_detail(before, after),
                    )
                    if detail
                ),
                admitted=Counter(),
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
    start or end of a block element, at the start of a note, at the start
    of a link marked as a note reference or of a back link from a note, or
    at the start of an item of a list of list items; the last four are
    also counted."""

    BREAK = "break"
    NOTE = "note"
    NOTE_LINK = "note_link"
    BACK_LINK = "back_link"
    LIST_ITEM = "list_item"


# Architecture section 9: a reference to an endnote is a link with this
# attribute, which Pandoc keeps.
_NOTE_LINK_ATTRIBUTE = ("epub:type", "noteref")


# Architecture section 9, "Back links": the marker of a referenced endnote
# is a link back to its reference with this attribute.
_BACK_LINK_ATTRIBUTE = ("role", "doc-backlink")


def _has_attribute(attributes: list[object], attribute: tuple[str, str]) -> bool:
    """Whether a link's key-value attributes, as Pandoc's JSON gives them,
    hold `attribute`."""
    return any(
        isinstance(given, list) and tuple(given) == attribute for given in attributes
    )


def _is_note_link(attributes: list[object]) -> bool:
    """Whether a link's key-value attributes, as Pandoc's JSON gives them,
    mark it as a note reference."""
    return _has_attribute(attributes, _NOTE_LINK_ATTRIBUTE)


def _is_back_link(attributes: list[object]) -> bool:
    """Whether a link's key-value attributes, as Pandoc's JSON gives them,
    mark it as a back link from a note to its reference."""
    return _has_attribute(attributes, _BACK_LINK_ATTRIBUTE)


@dataclass(frozen=True, slots=True)
class _Text:
    """The text of one Str element, in the div or heading of `block_id`."""

    text: str
    block_id: str | None


type _Token = _Text | _Boundary | ContentsLink | ShownMarker


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
        case {
            "t": "Link",
            "c": [[_, _, list() as attributes], list() as inlines, _],
        } if _is_back_link(attributes):
            # The link's text is a referenced endnote's marker, a word of
            # its own (architecture section 13).
            return (
                _Boundary.BACK_LINK,
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
    alone in a paragraph none (architecture section 13). An epigraph's div
    gives its source's words without the dash before them (structure spec
    section 25)."""
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
        case {"t": "BulletList", "c": list() as items}:
            content = _list_tokens(items, _ListElement.BULLET_LIST, block_id)
        case {
            "t": "OrderedList",
            "c": [
                [int() as start, {"t": str() as style}, {"t": str() as delimiter}],
                list() as items,
            ],
        }:
            content = _list_tokens(
                items,
                _ListElement.ORDERED_LIST,
                block_id,
                _Numbering(start, style, delimiter),
            )
        case {
            "t": "Div",
            "c": [[str() as div_id, list() as classes, *_], list() as blocks],
        }:
            content = _div_tokens(classes, blocks, div_id or block_id)
        case {
            "t": "Header",
            "c": [int(), [str(), list() as classes, *_], list() as inlines],
        } if _CHAPTER_NOTES_CLASS in classes:
            content = _chapter_notes_tokens(inlines, block_id)
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


# Structure spec section 36: the class of the heading markdown writes before
# a chapter's unlinked footnotes, and its one word, which is no word of the
# book. Written here again, not imported from the markdown stage, for the
# reason given for _SOURCE_DASHES.
_CHAPTER_NOTES_CLASS = "chapter-notes"
_CHAPTER_NOTES_TITLE = ({"t": "Str", "c": "Notes"},)


def _chapter_notes_tokens(
    inlines: list[object], block_id: str | None
) -> tuple[_Token, ...]:
    """No token for the "Notes" heading of a chapter's unlinked footnotes
    (structure spec section 36). Raises ExternalProgramError when its text
    is anything but "Notes", so that no word of the book hides in it."""
    if tuple(inlines) == _CHAPTER_NOTES_TITLE:
        return ()
    where = f"in block {block_id}" if block_id is not None else "outside any block"
    message = (
        f"a chapter-notes heading {where} reads {inlines!r:.80}, not "
        "'Notes', which galley's Markdown does not make"
    )
    raise ExternalProgramError(message)


def _blocks_tokens(blocks: list[object], block_id: str | None) -> tuple[_Token, ...]:
    """The tokens of a list of block elements. A note group's div gives its
    words to the endnote whose div follows it (structure spec section 25)."""
    tokens: list[_Token] = []
    for position, block in enumerate(blocks):
        if _NOTE_GROUP_CLASS in _div_classes(block):
            following = blocks[position + 1] if position + 1 < len(blocks) else None
            tokens.extend(_note_group_tokens(block, following, block_id))
        else:
            tokens.extend(_block_tokens(block, block_id))
    return tuple(tokens)


# Structure spec section 25: the classes of the divs markdown writes for an
# epigraph, its source and a note group, and markdown's for an endnote.
_EPIGRAPH_CLASS = "epigraph"
_EPIGRAPH_SOURCE_CLASS = "epigraph-source"
_NOTE_GROUP_CLASS = "note-group"
_ENDNOTE_CLASS = "endnote"
_DIV = "Div"
# The dash markdown writes before an epigraph's source, followed by a
# no-break space, which splits it off as a word of its own. Written here
# again, not imported from the markdown stage, for the reason given for
# _SOURCE_DASHES.
_SOURCE_DASH = "\u2014"


def _div_classes(block: object) -> tuple[str, ...]:
    """The classes of a Div element; none for any other element."""
    match block:
        case {"t": "Div", "c": [[_, list() as classes, *_], _]}:
            return tuple(name for name in classes if isinstance(name, str))
        case _:
            return ()


def _div_tokens(
    classes: list[object], blocks: list[object], block_id: str | None
) -> tuple[_Token, ...]:
    """The tokens of the blocks of a div of `classes`. An epigraph's source
    div is read only inside an epigraph's div; a note group's never comes
    here, since _blocks_tokens reads it."""
    if _EPIGRAPH_SOURCE_CLASS in classes:
        raise _not_read(_DIV, block_id)
    if _EPIGRAPH_CLASS in classes:
        return _epigraph_tokens(blocks, block_id)
    return _blocks_tokens(blocks, block_id)


def _epigraph_tokens(blocks: list[object], block_id: str | None) -> tuple[_Token, ...]:
    """The tokens of the blocks of an epigraph's div: its quotation, and
    its source div's words without the dash markdown wrote. Any other div
    inside it is an element galley's Markdown does not make."""
    tokens: list[_Token] = []
    for block in blocks:
        match block:
            case {"t": "Div", "c": [_, list() as source_blocks]} if (
                _EPIGRAPH_SOURCE_CLASS in _div_classes(block)
            ):
                tokens.extend(_source_tokens(source_blocks, block_id))
            case {"t": "Div"}:
                raise _not_read(_DIV, block_id)
            case _:
                tokens.extend(_block_tokens(block, block_id))
    return tuple(tokens)


def _source_tokens(blocks: list[object], block_id: str | None) -> tuple[_Token, ...]:
    """The words of an epigraph's source div, counted to the epigraph's
    block, without the dash markdown writes as their first word, which
    blocks.json does not hold (structure spec section 25). Raises
    ExternalProgramError when the div holds a note or does not start with
    that dash."""
    content = _blocks_tokens(blocks, block_id)
    where = f"in block {block_id}" if block_id is not None else "outside any block"
    if _Boundary.NOTE in content or _Boundary.NOTE_LINK in content:
        message = (
            f"the epigraph-source div {where} holds a note or a note reference, "
            "which galley's Markdown does not make"
        )
        raise ExternalProgramError(message)
    words = _token_words(content)
    if not words or words[0].text != _SOURCE_DASH:
        message = (
            f"the epigraph-source div {where} does not start with the dash "
            f"markdown writes before a source, {_SOURCE_DASH!r} and a no-break "
            "space, so its words cannot be checked"
        )
        raise ExternalProgramError(message)
    return (
        _Boundary.BREAK,
        *(
            token
            for word in words[1:]
            for token in (_Text(word.text, word.block_id), _Boundary.BREAK)
        ),
    )


def _note_group_tokens(
    group: object, following: object, block_id: str | None
) -> tuple[_Token, ...]:
    """The words of a note group's div, counted to the endnote whose div
    `following` is (structure spec section 25). Raises ExternalProgramError
    when `following` is not an endnote's div with its id."""
    match group, following:
        case (
            {"t": "Div", "c": [_, list() as blocks]},
            {"t": "Div", "c": [[str() as note_id, *_], _]},
        ) if note_id and _ENDNOTE_CLASS in _div_classes(following):
            return (_Boundary.BREAK, *_blocks_tokens(blocks, note_id), _Boundary.BREAK)
        case _:
            where = (
                f"in block {block_id}" if block_id is not None else "outside any block"
            )
            message = (
                f"a note-group div {where} is not followed by an endnote's div, "
                "which galley's Markdown does not make"
            )
            raise ExternalProgramError(message)


# Structure spec section 31: the classes of the divs markdown writes for a
# list item and a contents entry.
_LIST_ITEM_CLASS = "list-item"
_CONTENTS_ENTRY_CLASS = "contents-entry"


class _ListElement(StrEnum):
    """The two list elements of Pandoc's JSON that galley's Markdown makes."""

    BULLET_LIST = "BulletList"
    ORDERED_LIST = "OrderedList"


class _ItemForm(StrEnum):
    """The forms of a list's item that galley's Markdown makes (structure
    spec section 31): one div of a list item; or one div of a contents
    entry, alone or followed by a bullet list of contents entries."""

    LIST_ITEM = "list_item"
    CONTENTS_ENTRY = "contents_entry"


def _item_form(item: object) -> _ItemForm | None:
    """The form of an item of a list, as Pandoc's JSON gives it (a list of
    block elements); None when it is none of galley's."""
    match item:
        case [div] if _LIST_ITEM_CLASS in _div_classes(div):
            return _ItemForm.LIST_ITEM
        case [div] if _CONTENTS_ENTRY_CLASS in _div_classes(div):
            return _ItemForm.CONTENTS_ENTRY
        case [div, {"t": "BulletList"}] if _CONTENTS_ENTRY_CLASS in _div_classes(div):
            return _ItemForm.CONTENTS_ENTRY
        case _:
            return None


@dataclass(frozen=True, slots=True)
class _Numbering:
    """An ordered list's attributes in Pandoc's JSON: its start, style and
    delimiter."""

    start: int
    style: str
    delimiter: str


def _shown(
    item: object, number: int, numbering: _Numbering | None
) -> tuple[ShownMarker, ...]:
    """The marker Pandoc shows for `item`, the `number`-th of its list from
    0, whose numbering is `numbering`, None for a bullet list; none when
    the item is not one div, which _list_item_tokens refuses."""
    match item:
        case [{"t": "Div", "c": [[str() as div_id, *_], *_]}]:
            if numbering is None:
                return (ShownMarker(div_id or None, None, "", ""),)
            return (
                ShownMarker(
                    div_id or None,
                    numbering.start + number,
                    numbering.style,
                    numbering.delimiter,
                ),
            )
        case _:
            return ()


def _list_tokens(
    items: list[object],
    element: _ListElement,
    block_id: str | None,
    numbering: _Numbering | None = None,
) -> tuple[_Token, ...]:
    """The tokens of a list's items, each between two breaks: a list item's
    div after a LIST_ITEM boundary, which counts it; a contents entry's div
    as _contents_entry_tokens reads it, then its nested list. Raises
    ExternalProgramError for a list galley's Markdown does not make: an
    item of none of its forms, items of both forms, or an ordered list of
    contents entries."""
    forms = frozenset(_item_form(item) for item in items)
    match tuple(forms), element:
        case ((_ItemForm.LIST_ITEM,), _):
            return tuple(
                token
                for number, item in enumerate(items)
                for token in (
                    *_shown(item, number, numbering),
                    *_list_item_tokens(item, element, block_id),
                )
            )
        case ((_ItemForm.CONTENTS_ENTRY,), _ListElement.BULLET_LIST):
            return tuple(
                token
                for item in items
                for token in _contents_item_tokens(item, block_id)
            )
        case _:
            raise _not_read(element.value, block_id)


def _list_item_tokens(
    item: object, element: _ListElement, block_id: str | None
) -> tuple[_Token, ...]:
    """The tokens of an item of a list of list items, its one div's, after
    a LIST_ITEM boundary, which counts it."""
    match item:
        case [div]:
            return (_Boundary.LIST_ITEM, *_block_tokens(div, block_id))
        case _:
            raise _not_read(element.value, block_id)


def _contents_item_tokens(item: object, block_id: str | None) -> tuple[_Token, ...]:
    """The tokens of an item of a list of contents entries: its entry's
    div, then the nested list, which must be of contents entries too."""
    match item:
        case [
            {"t": "Div", "c": [[str() as div_id, *_], list() as blocks]},
            *nested,
        ]:
            entry = _contents_entry_tokens(blocks, div_id or block_id)
            inner = tuple(
                token
                for element in nested
                for token in _nested_contents_tokens(element, block_id)
            )
            return (_Boundary.BREAK, *entry, _Boundary.BREAK, *inner)
        case _:
            raise _not_read(_ListElement.BULLET_LIST.value, block_id)


def _nested_contents_tokens(
    element: object, block_id: str | None
) -> tuple[_Token, ...]:
    """The tokens of a bullet list inside an item of contents entries,
    which must hold contents entries."""
    match element:
        case {"t": "BulletList", "c": list() as items} if all(
            _item_form(item) is _ItemForm.CONTENTS_ENTRY for item in items
        ):
            return _list_tokens(items, _ListElement.BULLET_LIST, block_id)
        case _:
            raise _not_read(_ListElement.BULLET_LIST.value, block_id)


def _contents_entry_tokens(
    blocks: list[object], block_id: str | None
) -> tuple[_Token, ...]:
    """The tokens of a contents entry's div: its paragraph's inlines, a
    link with no attributes and no title read as a ContentsLink and its
    text, between breaks. Any other block in the div is an element galley's
    Markdown does not make."""
    tokens: list[_Token] = []
    for block in blocks:
        match block:
            case {"t": "Para" | "Plain", "c": list() as inlines}:
                tokens.append(_Boundary.BREAK)
                for inline in inlines:
                    match inline:
                        case {
                            "t": "Link",
                            "c": [
                                attributes,
                                list() as link_inlines,
                                [str() as target, str() as title],
                            ],
                        } if _has_no_attributes(attributes) and title == _NO_TITLE:
                            tokens.extend(
                                (
                                    ContentsLink(block_id, target),
                                    *_inlines_tokens(link_inlines, block_id),
                                    _Boundary.BREAK,
                                )
                            )
                        case _:
                            tokens.extend(_inline_tokens(inline, block_id))
                tokens.append(_Boundary.BREAK)
            case {"t": str() as element}:
                raise _not_read(element, block_id)
            case _:
                raise _not_read(repr(block)[:80], block_id)
    return tuple(tokens)


def _joined_words(texts: tuple[_Text, ...]) -> tuple[MarkdownWord, ...]:
    """The words of adjacent Str elements: their text joined, then split on
    white space. Every element of one run is in the same block."""
    if not texts:
        return ()
    joined = "".join(text.text for text in texts)
    return tuple(MarkdownWord(word, texts[0].block_id) for word in joined.split())


def _token_words(tokens: tuple[_Token, ...]) -> tuple[MarkdownWord, ...]:
    """The words of `tokens`: each run of text between two boundaries
    joined, then split on white space."""
    words: list[MarkdownWord] = []
    run: list[_Text] = []
    for token in tokens:
        match token:
            case _Text():
                run.append(token)
            case (
                _Boundary.BREAK
                | _Boundary.NOTE
                | _Boundary.NOTE_LINK
                | _Boundary.BACK_LINK
                | _Boundary.LIST_ITEM
                | ContentsLink()
                | ShownMarker()
            ):
                words.extend(_joined_words(tuple(run)))
                run = []
            case _:
                assert_never(token)
    words.extend(_joined_words(tuple(run)))
    return tuple(words)


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
    return MarkdownWords(
        words=_token_words(tokens),
        note_count=sum(1 for token in tokens if token is _Boundary.NOTE),
        note_link_count=sum(1 for token in tokens if token is _Boundary.NOTE_LINK),
        back_link_count=sum(1 for token in tokens if token is _Boundary.BACK_LINK),
        list_item_count=sum(1 for token in tokens if token is _Boundary.LIST_ITEM),
        shown_markers=tuple(
            token for token in tokens if isinstance(token, ShownMarker)
        ),
        contents_links=tuple(
            token for token in tokens if isinstance(token, ContentsLink)
        ),
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
    of notes, the number of links marked `epub:type="noteref"`, the number
    of back links (links with the role `doc-backlink`), the number of items of the lists of list items, and the links of the contents
    entries.

    Words are split at spaces and line breaks, and at the start and end of
    every block, note, link marked as a note reference and back link, whose
    text is read as its own words; emphasis does not split a word. The words of an
    epigraph's source div count to the epigraph, without the dash markdown
    writes first, and those of a note group's div to the endnote whose div
    follows it. A heading of class `chapter-notes` whose text is "Notes",
    which markdown writes before a chapter's unlinked footnotes, gives no
    word (structure spec section 36). A list is read item by item, in the forms markdown writes
    (structure spec section 31): an item holding one div of class
    `list-item`, or one div of class `contents-entry` and after it a bullet
    list of the same form; in a contents entry's div a link with no
    attributes and no title is read as its text and kept as a contents
    link. A figure's
    caption is read once, and its image's alt text, which Pandoc copies
    from the caption, not at all. The metadata header, the title and
    authors, gives no words. Raises
    ExternalProgramError, with Pandoc's standard error, when `pandoc` is
    missing, fails or warns (a note definition no reference uses), runs
    longer than 60 s, or reads an element galley's Markdown does not make,
    such as a list of another form, a link that is no note reference or
    back link outside a contents entry's div, or an image that is
    not alone in its paragraph, whose alt text is not its figure's caption,
    or that has a title or attributes; or a div inside an epigraph's div
    that is not its source's, a source's div that does not start with the
    dash, or a note group's div not followed by an endnote's, or a
    heading of class `chapter-notes` whose text is not "Notes".
    """
    return _words_of_pandoc_json(_pandoc_json(markdown))
