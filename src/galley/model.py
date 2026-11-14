"""The formats of the files between stages, and the functions that write and read them.

Every format is a frozen dataclass: tuples for sequences, StrEnum for finite
sets, floats for positions in PDF points with the origin at the top left of
the page, page indices from 0 (architecture sections 7 and 8). Each of the
four JSON files, pages.json, words.json, lines.json and blocks.json, has a
`write_<file>` and a `read_<file>`; the edits files under `edits/` have
`write_edits` and `read_edits`. No stage writes or parses these files by
itself.
"""

import dataclasses
import functools
import hashlib
import json
import types
import typing
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from galley.errors import InputFileError

PAGES_FORMAT_VERSION = 1
WORDS_FORMAT_VERSION = 1
LINES_FORMAT_VERSION = 1
BLOCKS_FORMAT_VERSION = 1
EDITS_FORMAT_VERSION = 1


@dataclass(frozen=True, slots=True)
class Box:
    """A rectangle on a page, in PDF points, origin at the top left, `top`
    growing downwards. Written in JSON as a list of four numbers."""

    x0: float
    top: float
    x1: float
    bottom: float


# pages.json


class PageKind(StrEnum):
    BLANK = "blank"
    TEXT = "text"
    PLATE = "plate"  # mostly a picture
    EXCLUDED = "excluded"


class TextSource(StrEnum):
    TEXT_LAYER = "text_layer"
    OCR = "ocr"
    NONE = "none"  # blank and excluded pages


class OcrVerdict(StrEnum):
    LAYER_KEPT = "layer_kept"  # the layer scored as well as Tesseract
    LAYER_DOUBTFUL = "layer_doubtful"  # below, but not clearly; the run goes on


@dataclass(frozen=True, slots=True)
class SampledPage:
    """A page of the OCR audit, scored as the share of its words found in
    the word list, from 0 to 1, for the text layer and for Tesseract."""

    page_index: int
    layer_score: float
    tesseract_score: float


@dataclass(frozen=True, slots=True)
class OcrAudit:
    """The audit of the book's own text layer (architecture section 7b)."""

    sampled: tuple[SampledPage, ...]
    verdict: OcrVerdict


@dataclass(frozen=True, slots=True, kw_only=True)
class PageInfo:
    """What analyze found about one page.

    `text_layer_score` is the share of the layer's words found in the word
    list, from 0 to 1, or None without a layer. `blank_checked_by_ocr` is
    true for a page without a text layer that the OCR audit read and found
    blank.
    """

    index: int
    width_pt: float
    height_pt: float
    kind: PageKind
    text_source: TextSource
    text_layer_score: float | None
    exclude_regions: tuple[Box, ...]
    blank_checked_by_ocr: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class PagesFile:
    """pages.json, written by analyze. `ocr_audit` is None when the config's
    `ocr` is `trust` or `redo`, and in the walking skeleton."""

    format_version: int = PAGES_FORMAT_VERSION
    source_pdf_sha256: str
    pages: tuple[PageInfo, ...]
    ocr_audit: OcrAudit | None


# words.json


@dataclass(frozen=True, slots=True)
class Word:
    """A word as its source gave it. `ocr_confidence` is Tesseract's, from 0
    to 100, or None for a word of the text layer."""

    text: str
    box: Box
    ocr_confidence: float | None


@dataclass(frozen=True, slots=True)
class Figure:
    """A picture cut from a page. `image` is its path relative to the book
    folder, with `/` as separator; `dpi` is the resolution it was rendered at."""

    box: Box
    image: str
    dpi: int


@dataclass(frozen=True, slots=True, kw_only=True)
class PageWords:
    """The words of one page, in the order the source gave them, and its figures."""

    index: int
    text_source: TextSource
    words: tuple[Word, ...]
    figures: tuple[Figure, ...]


class RemovalReason(StrEnum):
    EXCLUDED_PAGE = "excluded_page"
    EXCLUDED_REGION = "excluded_region"
    RUNNING_HEAD = "running_head"
    PAGE_NUMBER = "page_number"
    SIGNATURE_MARK = "signature_mark"
    PLATE_TEXT = "plate_text"  # stray text-layer characters on a plate


@dataclass(frozen=True, slots=True, kw_only=True)
class Removal:
    """Text a stage took out of the book on purpose, with where it was and why."""

    page_index: int
    box: Box
    text: str
    reason: RemovalReason


@dataclass(frozen=True, slots=True, kw_only=True)
class WordsFile:
    """words.json, written by extract. `removals` holds the words of
    excluded pages and regions, one per word."""

    format_version: int = WORDS_FORMAT_VERSION
    source_pdf_sha256: str
    pages: tuple[PageWords, ...]
    removals: tuple[Removal, ...]


# lines.json


@dataclass(frozen=True, slots=True)
class Line:
    """A line of one region of a page, its words left to right."""

    box: Box
    words: tuple[Word, ...]


@dataclass(frozen=True, slots=True)
class Region:
    """A part of a page whose lines are read one after the other."""

    box: Box
    lines: tuple[Line, ...]


@dataclass(frozen=True, slots=True)
class PageLayout:
    """The regions of one page in reading order, and its figures, copied
    from words.json."""

    index: int
    regions: tuple[Region, ...]
    figures: tuple[Figure, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class LinesFile:
    """lines.json, written by layout. Every word of words.json is in exactly
    one line."""

    format_version: int = LINES_FORMAT_VERSION
    source_pdf_sha256: str
    pages: tuple[PageLayout, ...]


# blocks.json


class BlockKind(StrEnum):
    HEADING = "heading"
    PARAGRAPH = "paragraph"
    QUOTE = "quote"
    FIGURE = "figure"
    MARGIN_NOTE = "margin_note"
    INDEX_ENTRY = "index_entry"


class Emphasis(StrEnum):
    NONE = "none"


@dataclass(frozen=True, slots=True)
class Span:
    """A run of a block's text. A span with a `note_ref` is a note reference:
    its text is the marker as printed and `note_ref` the id of the note."""

    text: str
    emphasis: Emphasis
    note_ref: str | None


@dataclass(frozen=True, slots=True)
class Origin:
    """Where a block, or its part on one page, was printed."""

    page_index: int
    box: Box


@dataclass(frozen=True, slots=True, kw_only=True)
class Block:
    """A heading, paragraph, quote, figure, margin note or index entry.

    `id` is `b-p<page index, 4 digits>-<n, 3 digits>`; `level` is a
    heading's, from 1, and None otherwise; `figure` is the image path of a
    figure block; `origin` has one entry per page the block was printed on.
    """

    id: str
    kind: BlockKind
    level: int | None
    spans: tuple[Span, ...]
    figure: str | None
    origin: tuple[Origin, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class Note:
    """A footnote or endnote. `marker` is as printed at the start of the
    note; `referenced` is false when no reference to it was found."""

    id: str
    marker: str
    blocks: tuple[Block, ...]
    origin: tuple[Origin, ...]
    referenced: bool


class ChangeReason(StrEnum):
    HYPHEN_JOIN = "hyphen_join"
    NOTE_MARKER = "note_marker"


@dataclass(frozen=True, slots=True, kw_only=True)
class WordChange:
    """Words structure changed without losing a letter: `before` became `after`."""

    page_index: int
    before: tuple[str, ...]
    after: tuple[str, ...]
    reason: ChangeReason


class PageNumberPosition(StrEnum):
    HEAD = "head"
    FOOT = "foot"


@dataclass(frozen=True, slots=True)
class PageNumber:
    """The page number printed on a page, as a string ("47", "xiv")."""

    page_index: int
    text: str
    position: PageNumberPosition


@dataclass(frozen=True, slots=True, kw_only=True)
class BlocksFile:
    """blocks.json, written by structure. `removals` holds only what
    structure removed; the removals of words.json are not repeated."""

    format_version: int = BLOCKS_FORMAT_VERSION
    source_pdf_sha256: str
    blocks: tuple[Block, ...]
    notes: tuple[Note, ...]
    removals: tuple[Removal, ...]
    word_changes: tuple[WordChange, ...]
    page_numbers: tuple[PageNumber, ...]


# edits/<author>.jsonl


@dataclass(frozen=True, slots=True, kw_only=True)
class Edit:
    """A change to the text of one block: `old`, found exactly once in the
    block's text, becomes `new`. `block_sha256` is block_sha256 of the block
    as structure wrote it."""

    format_version: int = EDITS_FORMAT_VERSION
    block_id: str
    block_sha256: str
    old: str
    new: str
    author: str
    reason: str


# Not a file: what pdfium.render returns.


@dataclass(frozen=True, slots=True, kw_only=True)
class RenderedPage:
    """A page rendered at `dpi`: 8-bit grayscale pixels, row by row."""

    page_index: int
    dpi: int
    width_px: int
    height_px: int
    pixels: bytes


# Writing and reading. Both follow the dataclasses' field types, so that a
# float field is written as a float whatever number it was given, and
# reading rebuilds the tuples, enums and boxes that JSON turned into lists
# and strings.

_JSON_INDENT = 1
_STAGE_OF_FILE = frozendict(
    {
        "pages.json": "analyze",
        "words.json": "extract",
        "lines.json": "layout",
        "blocks.json": "structure",
    }
)


@functools.cache
def _fields(cls: type) -> tuple[tuple[str, object], ...]:
    # A dataclass's annotations are its fields, in their order.
    return tuple(typing.get_type_hints(cls).items())


def _optional_type(annotation: object) -> object | None:
    """The X of an `X | None` annotation; None for any other annotation."""
    if not isinstance(annotation, types.UnionType):
        return None
    others = tuple(
        arg for arg in typing.get_args(annotation) if arg is not types.NoneType
    )
    return others[0] if len(others) == 1 else None


def _tuple_item_type(annotation: object) -> object | None:
    """The X of a `tuple[X, ...]` annotation; None for any other annotation."""
    if typing.get_origin(annotation) is not tuple:
        return None
    return typing.get_args(annotation)[0]


def _encode(annotation: object, value: object) -> object:
    """The JSON value of `value`, whose type is `annotation`."""
    if value is None:
        return None
    if annotation is Box and isinstance(value, Box):
        return [float(value.x0), float(value.top), float(value.x1), float(value.bottom)]
    if annotation is float and isinstance(value, int | float):
        return float(value)
    if isinstance(value, StrEnum):
        return value.value
    if (item_type := _tuple_item_type(annotation)) is not None and isinstance(
        value, tuple
    ):
        return [_encode(item_type, item) for item in value]
    if (optional := _optional_type(annotation)) is not None:
        return _encode(optional, value)
    if isinstance(annotation, type) and dataclasses.is_dataclass(annotation):
        return {
            name: _encode(field_type, getattr(value, name))
            for name, field_type in _fields(annotation)
        }
    return value


def _decode(annotation: object, value: object) -> object:
    """The value of type `annotation` that `_encode` wrote as `value`."""
    if value is None:
        return None
    if annotation is Box and isinstance(value, list):
        return Box(*(float(coordinate) for coordinate in value))
    if annotation is float and isinstance(value, int | float):
        return float(value)
    if isinstance(annotation, type) and issubclass(annotation, StrEnum):
        return annotation(value)
    if (item_type := _tuple_item_type(annotation)) is not None and isinstance(
        value, list
    ):
        return tuple(_decode(item_type, item) for item in value)
    if (optional := _optional_type(annotation)) is not None:
        return _decode(optional, value)
    if (
        isinstance(annotation, type)
        and dataclasses.is_dataclass(annotation)
        and isinstance(value, dict)
    ):
        return _decode_dataclass(annotation, value)
    return value


def _decode_dataclass[T](cls: type[T], content: dict[str, object]) -> T:
    return cls(
        **{
            name: _decode(field_type, content[name])
            for name, field_type in _fields(cls)
        }
    )


def _write_json(path: Path, value: object) -> None:
    content = _encode(type(value), value)
    text = json.dumps(content, ensure_ascii=False, indent=_JSON_INDENT) + "\n"
    path.write_text(text, encoding="utf-8", newline="\n")


def _read_json[T](path: Path, cls: type[T]) -> T:
    content = json.loads(path.read_text(encoding="utf-8"))
    return _decode_dataclass(cls, content)


def write_pages(path: Path, pages: PagesFile) -> None:
    """Writes pages.json: UTF-8 JSON, keys in field order, indent 1."""
    _write_json(path, pages)


def read_pages(path: Path) -> PagesFile:
    """Reads pages.json as write_pages wrote it."""
    return _read_json(path, PagesFile)


def write_words(path: Path, words: WordsFile) -> None:
    """Writes words.json: UTF-8 JSON, keys in field order, indent 1."""
    _write_json(path, words)


def read_words(path: Path) -> WordsFile:
    """Reads words.json as write_words wrote it."""
    return _read_json(path, WordsFile)


def write_lines(path: Path, lines: LinesFile) -> None:
    """Writes lines.json: UTF-8 JSON, keys in field order, indent 1."""
    _write_json(path, lines)


def read_lines(path: Path) -> LinesFile:
    """Reads lines.json as write_lines wrote it."""
    return _read_json(path, LinesFile)


def write_blocks(path: Path, blocks: BlocksFile) -> None:
    """Writes blocks.json: UTF-8 JSON, keys in field order, indent 1."""
    _write_json(path, blocks)


def read_blocks(path: Path) -> BlocksFile:
    """Reads blocks.json as write_blocks wrote it."""
    return _read_json(path, BlocksFile)


# The hashes.


def pdf_sha256(pdf: Path) -> str:
    """The SHA-256 of the PDF file's bytes, 64 lowercase hex digits."""
    return hashlib.sha256(pdf.read_bytes()).hexdigest()


def check_source_pdf(path: Path, file_pdf_sha256: str, pdf_sha256: str) -> None:
    """Raises InputFileError when the file at `path`, whose
    `source_pdf_sha256` is `file_pdf_sha256`, was made from another PDF
    than the one whose hash is `pdf_sha256`. The message names the stage
    to run again."""
    if file_pdf_sha256 == pdf_sha256:
        return
    stage = _STAGE_OF_FILE.get(path.name)
    rerun = (
        f"run `galley2epub {stage}` again"
        if stage is not None
        else "run the stage that writes it again"
    )
    message = (
        f"{path} was made from another PDF (SHA-256 {file_pdf_sha256}, "
        f"expected {pdf_sha256}); {rerun}"
    )
    raise InputFileError(message)


def block_text(block: Block) -> str:
    """The text of a block: its spans' text concatenated, with nothing between."""
    return "".join(span.text for span in block.spans)


_BLOCK_SHA256_DIGITS = 12  # architecture section 8, the checksum an Edit carries


def block_sha256(block: Block) -> str:
    """The first 12 hex digits of the SHA-256 of the block's text in UTF-8,
    the checksum an Edit carries."""
    return hashlib.sha256(block_text(block).encode("utf-8")).hexdigest()[
        :_BLOCK_SHA256_DIGITS
    ]
