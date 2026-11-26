"""A sample of the correct stage's edits of a book, cut from the page
images for judging, and the count of the verdicts (spec section 9b).

`edit_sheet` picks a seeded random sample of the edits of
`edits/correct.jsonl`, finds where each edit's words are printed, writes
an image of those lines cut from the page rendered from the book's PDF,
and writes a sheet, `sheet.json`, listing each edit with its image and an
empty verdict and note. `sheet_scores` counts the verdicts written into a
sheet, by kind of edit.
"""

import json
import logging
import random
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, fields
from enum import StrEnum
from pathlib import Path
from typing import Final

from PIL import Image, ImageDraw

from galley.book_folder import BookFolder
from galley.config import read_config
from galley.model import (
    Block,
    BlocksFile,
    Box,
    Edit,
    Line,
    LinesFile,
    Word,
    box_holds_middle,
    read_blocks,
    read_edits,
    read_lines,
)
from galley.pdfium import POINTS_PER_INCH, render
from galley_eval.errors import EditSheetError

__all__ = [
    "DEFAULT_COUNT",
    "DEFAULT_SEED",
    "RENDER_DPI",
    "SHEET_FORMAT_VERSION",
    "SHEET_NAME",
    "ComparedEdit",
    "Comparison",
    "EditState",
    "KindScores",
    "Located",
    "Location",
    "NumberedEdit",
    "Sheet",
    "SheetEntry",
    "Verdict",
    "compare_sheet",
    "comparison_report",
    "edit_sheet",
    "locate",
    "numbered_edits",
    "read_sheet",
    "sample_edits",
    "scores_table",
    "sheet_scores",
]

SHEET_FORMAT_VERSION: Final[int] = 1
SHEET_NAME: Final[str] = "sheet.json"

# 60 edits a book is the sample the plan misread-words judges (work
# package 2, deliverable 3).
DEFAULT_COUNT: Final[int] = 60
DEFAULT_SEED: Final[int] = 0

# At 300 dpi the body text of the books, about 10 pt, is some 40 pixels
# high, legible to a reader of the image; the task asked for 300 or more.
RENDER_DPI: Final[int] = 300

# Around the lines of the crop, so that accents and descenders of the
# lines above and below are not cut. Guessed, not measured.
_CROP_MARGIN_PT: Final[float] = 6.0
# The frame drawn around the edit's words: this far outside their boxes,
# this thick, this gray (0 black, 255 white), so that it marks the words
# without hiding a letter. Guessed, not measured.
_FRAME_PAD_PT: Final[float] = 1.5
_FRAME_WIDTH_PX: Final[int] = 3
_FRAME_GRAY: Final[int] = 128

# Characters left out of the key that finds an edit's words among a
# page's: white space, and the hyphens structure drops when it joins a
# word broken at a line end ("cam-" "paigns" is "campaigns" in the block).
_HYPHENS: Final[frozenset[str]] = frozenset("-\u00ad\u2010\u2011")

_logger = logging.getLogger(__name__)


class Verdict(StrEnum):
    """A judge's verdict on an edit, read from the page image."""

    RIGHT = "right"  # the edit's words are what is printed
    WRONG = "wrong"  # galley's words were right, or both are wrong
    UNCLEAR = "unclear"  # the image does not settle it


class Located(StrEnum):
    """How an edit's place on the page was found (spec section 9b)."""

    BLOCK_WORDS = "block_words"  # among the words inside the block's box
    PAGE_WORDS = "page_words"  # among the page's words, outside the block's box
    BLOCK_BOX = "block_box"  # words not found: the block's box on the page
    NOT_FOUND = "not_found"  # the block is not printed on the edit's page


@dataclass(frozen=True, slots=True)
class NumberedEdit:
    """An edit and its id, its line number in edits/correct.jsonl, from 1."""

    id: int
    edit: Edit


@dataclass(frozen=True, slots=True, kw_only=True)
class Location:
    """Where an edit is printed: `page_index`; `words_boxes`, the box of
    its words on each line they are on, which the image frames, empty when
    they were not found; and `crop`, the box the image is cut to, None
    when not found. Boxes in points."""

    located: Located
    page_index: int | None
    words_boxes: tuple[Box, ...]
    crop: Box | None


@dataclass(frozen=True, slots=True, kw_only=True)
class SheetEntry:
    """One edit of the sheet. `galley` is the edit's `old`, `edit` its
    `new`, `kind` its `reason`; `image` is the image's path relative to the
    sheet, None when the edit was not found on its page; `verdict` is a
    Verdict or "" while not judged."""

    id: int
    page_index: int | None
    kind: str
    block_id: str
    galley: str
    edit: str
    second_reading: str | None
    located: Located
    image: str | None
    verdict: str
    note: str


@dataclass(frozen=True, slots=True, kw_only=True)
class Sheet:
    """sheet.json: the sample of a run's edits and their verdicts."""

    format_version: int = SHEET_FORMAT_VERSION
    run: str
    pdf: str
    seed: int
    count: int
    kinds: tuple[str, ...] | None
    edits_in_file: int
    edits: tuple[SheetEntry, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class KindScores:
    """The verdicts on the edits of one kind; `kind` "all" for the total."""

    kind: str
    right: int
    wrong: int
    unclear: int
    not_judged: int

    @property
    def edits(self) -> int:
        """The number of edits of the kind on the sheet."""
        return self.right + self.wrong + self.unclear + self.not_judged


def numbered_edits(edits: Iterable[Edit]) -> tuple[NumberedEdit, ...]:
    """The edits of edits/correct.jsonl, in the file's order, each with its
    line number."""
    return tuple(NumberedEdit(number, edit) for number, edit in enumerate(edits, 1))


def sample_edits(
    edits: Sequence[NumberedEdit],
    *,
    count: int,
    seed: int,
    kinds: frozenset[str] | None,
) -> tuple[NumberedEdit, ...]:
    """`count` of `edits` picked at random with `seed`, among those whose
    reason is one of `kinds` (all when None), in the order of their ids;
    all of them when there are no more than `count`. Raises EditSheetError
    for a kind no edit has, naming the kinds there are."""
    if kinds is not None:
        present = frozenset(item.edit.reason for item in edits)
        unknown = sorted(kinds - present)
        if unknown:
            message = (
                f"no edit of kind {', '.join(unknown)}; "
                f"the kinds of the file are {', '.join(sorted(present))}"
            )
            raise EditSheetError(message)
    chosen = [item for item in edits if kinds is None or item.edit.reason in kinds]
    if len(chosen) > count:
        chosen = random.Random(seed).sample(chosen, count)
    return tuple(sorted(chosen, key=lambda item: item.id))


def _key(text: str) -> str:
    return "".join(char for char in text if not char.isspace() and char not in _HYPHENS)


def _union(boxes: Iterable[Box]) -> Box:
    boxes = tuple(boxes)
    return Box(
        x0=min(box.x0 for box in boxes),
        top=min(box.top for box in boxes),
        x1=max(box.x1 for box in boxes),
        bottom=max(box.bottom for box in boxes),
    )


def _find_words(old: str, words: Sequence[Word]) -> tuple[int, ...]:
    """The positions in `words`, in order, of the words that hold the first
    place where the key of `old` (no white space, no hyphen) is in their
    keys run together; none when it is not there."""
    target = _key(old)
    if target == "":
        return ()
    joined: list[str] = []
    owner: list[int] = []
    for position, word in enumerate(words):
        key = _key(word.text)
        joined.append(key)
        owner.extend([position] * len(key))
    start = "".join(joined).find(target)
    if start < 0:
        return ()
    return tuple(range(owner[start], owner[start + len(target) - 1] + 1))


def _blocks_by_id(blocks: BlocksFile) -> dict[str, Block]:
    found = {block.id: block for block in blocks.blocks}
    found.update((block.id, block) for note in blocks.notes for block in note.blocks)
    return found


def _page_lines(lines: LinesFile, page_index: int) -> tuple[Line, ...]:
    return tuple(
        line
        for page in lines.pages
        if page.index == page_index
        for region in page.regions
        for line in region.lines
    )


def _overlaps_across(line: Line, left: float, right: float) -> bool:
    return line.box.x0 < right and line.box.x1 > left


def _crop(page_lines: Sequence[Line], words: Sequence[Word]) -> Box:
    """The lines that hold `words`, across; down, also the nearest line
    above them and the nearest below that overlap them across; and a
    margin."""
    held = frozenset(words)
    matched = tuple(line for line in page_lines if held & frozenset(line.words))
    span = _union(line.box for line in matched)
    others = tuple(
        line
        for line in page_lines
        if line not in matched and _overlaps_across(line, span.x0, span.x1)
    )
    above = tuple(line for line in others if line.box.bottom <= span.top + 1)
    below = tuple(line for line in others if line.box.top >= span.bottom - 1)
    neighbours = (
        *((max(above, key=lambda line: line.box.bottom),) if above else ()),
        *((min(below, key=lambda line: line.box.top),) if below else ()),
    )
    whole = _union(line.box for line in (*matched, *neighbours))
    return _with_margin(Box(x0=span.x0, top=whole.top, x1=span.x1, bottom=whole.bottom))


def _with_margin(box: Box) -> Box:
    return Box(
        x0=box.x0 - _CROP_MARGIN_PT,
        top=box.top - _CROP_MARGIN_PT,
        x1=box.x1 + _CROP_MARGIN_PT,
        bottom=box.bottom + _CROP_MARGIN_PT,
    )


def _block_words(block: Block, lines: LinesFile, page_index: int) -> tuple[Word, ...]:
    """The words of lines.json on page `page_index` whose middle is inside
    one of `block`'s boxes on that page, in the order of lines.json."""
    boxes = tuple(o.box for o in block.origin if o.page_index == page_index)
    return tuple(
        word
        for line in _page_lines(lines, page_index)
        for word in line.words
        if any(box_holds_middle(box, word.box) for box in boxes)
    )


def _boxes_by_line(
    page_lines: Sequence[Line], words: Sequence[Word]
) -> tuple[Box, ...]:
    """The box of `words` on each line of `page_lines` that holds some."""
    held = frozenset(words)
    return tuple(
        _union(word.box for word in line.words if word in held)
        for line in page_lines
        if held & frozenset(line.words)
    )


def _found(
    located: Located, page_index: int, lines: LinesFile, words: Sequence[Word]
) -> Location:
    return Location(
        located=located,
        page_index=page_index,
        words_boxes=_boxes_by_line(_page_lines(lines, page_index), words),
        crop=_crop(_page_lines(lines, page_index), words),
    )


def _locate_on_page(
    edit: Edit, block: Block, lines: LinesFile, page_index: int
) -> Location | None:
    """Where `edit` is on page `page_index`, among the block's words, the
    match starting on that page and running on to the block's words of
    its next page, for a word broken across the page; else among the
    page's words; None when not found."""
    pages = tuple(dict.fromkeys(origin.page_index for origin in block.origin))
    following = pages[pages.index(page_index) + 1 :][:1]
    on_page = _block_words(block, lines, page_index)
    after = tuple(
        word for page in following for word in _block_words(block, lines, page)
    )
    positions = _find_words(edit.old, (*on_page, *after))
    if positions and positions[0] < len(on_page):
        held = tuple(on_page[i] for i in positions if i < len(on_page))
        return _found(Located.BLOCK_WORDS, page_index, lines, held)
    page_words = tuple(
        word for line in _page_lines(lines, page_index) for word in line.words
    )
    positions = _find_words(edit.old, page_words)
    if positions:
        held = tuple(page_words[i] for i in positions)
        return _found(Located.PAGE_WORDS, page_index, lines, held)
    return None


def locate(edit: Edit, blocks: BlocksFile, lines: LinesFile) -> Location:
    """Where `edit` is printed (spec section 9b), on its `page_index`, or,
    when it has none, on the first of its block's pages where its words
    are found: its words among those of lines.json inside its block's box,
    else among all the page's words, else the block's box on the page; not
    found when the block is not in `blocks` or not printed on the page."""
    block = _blocks_by_id(blocks).get(edit.block_id)
    block_pages = (
        () if block is None else tuple(origin.page_index for origin in block.origin)
    )
    pages = (
        tuple(dict.fromkeys(block_pages))
        if edit.page_index is None
        else tuple(page for page in (edit.page_index,) if page in block_pages)
    )
    if block is None or not pages:
        return Location(
            located=Located.NOT_FOUND,
            page_index=edit.page_index,
            words_boxes=(),
            crop=None,
        )
    for page_index in pages:
        location = _locate_on_page(edit, block, lines, page_index)
        if location is not None:
            return location
    return Location(
        located=Located.BLOCK_BOX,
        page_index=pages[0],
        words_boxes=(),
        crop=_with_margin(
            _union(o.box for o in block.origin if o.page_index == pages[0])
        ),
    )


def _pixels(value_pt: float) -> int:
    return round(value_pt * RENDER_DPI / POINTS_PER_INCH)


def _cut(page: Image.Image, location: Location) -> Image.Image:
    """The crop of `location` from `page`, rendered at RENDER_DPI, with a
    frame around the edit's words when they were found."""
    assert location.crop is not None  # only found edits are cut
    crop = location.crop
    left = max(0, _pixels(crop.x0))
    top = max(0, _pixels(crop.top))
    image = page.crop(
        (
            left,
            top,
            min(page.width, _pixels(crop.x1)),
            min(page.height, _pixels(crop.bottom)),
        )
    )
    for box in location.words_boxes:
        ImageDraw.Draw(image).rectangle(
            (
                _pixels(box.x0 - _FRAME_PAD_PT) - left,
                _pixels(box.top - _FRAME_PAD_PT) - top,
                _pixels(box.x1 + _FRAME_PAD_PT) - left,
                _pixels(box.bottom + _FRAME_PAD_PT) - top,
            ),
            outline=_FRAME_GRAY,
            width=_FRAME_WIDTH_PX,
        )
    return image


def _image_name(item: NumberedEdit, page_index: int) -> str:
    return f"edit-{item.id:04d}-p{page_index:04d}.png"


def _entry(item: NumberedEdit, location: Location, image: str | None) -> SheetEntry:
    edit = item.edit
    return SheetEntry(
        id=item.id,
        page_index=location.page_index,
        kind=edit.reason,
        block_id=edit.block_id,
        galley=edit.old,
        edit=edit.new,
        second_reading=edit.second_reading,
        located=location.located,
        image=image,
        verdict="",
        note="",
    )


def _sheet_json(sheet: Sheet) -> str:
    content = {
        field.name: getattr(sheet, field.name)
        for field in fields(sheet)
        if field.name != "edits"
    }
    content["edits"] = [
        {field.name: getattr(entry, field.name) for field in fields(entry)}
        for entry in sheet.edits
    ]
    return json.dumps(content, ensure_ascii=False, indent=1) + "\n"


def edit_sheet(
    run: Path,
    out: Path,
    *,
    count: int = DEFAULT_COUNT,
    seed: int = DEFAULT_SEED,
    kinds: frozenset[str] | None = None,
) -> Sheet:
    """Write the sheet and images of a sample of the edits of the run
    folder `run` into `out`, made if missing, and return the sheet.

    Raises EditSheetError when `out` already holds a sheet, whose verdicts
    would be lost, or for a kind no edit has; galley's own errors for a
    book.toml, blocks.json, lines.json or edits file it cannot read, and a
    missing PDF."""
    sheet_path = out / SHEET_NAME
    if sheet_path.exists():
        message = (
            f"{sheet_path} exists, and its verdicts would be lost; "
            "remove it or give another --out"
        )
        raise EditSheetError(message)
    folder = BookFolder(run)
    pdf = read_config(folder.book_toml).pdf
    edits = numbered_edits(read_edits(folder.correct_jsonl))
    blocks = read_blocks(folder.blocks_json)
    lines = read_lines(folder.lines_json)
    chosen = sample_edits(edits, count=count, seed=seed, kinds=kinds)
    located = tuple((item, locate(item.edit, blocks, lines)) for item in chosen)
    out.mkdir(parents=True, exist_ok=True)
    images: dict[int, str] = {}
    # One render a page, in page order; PDFium runs in galley's one PDFium
    # thread, whatever thread calls render.
    pages = sorted(
        {
            loc.page_index
            for _, loc in located
            if loc.crop is not None and loc.page_index is not None
        }
    )
    for page_index in pages:
        rendered = render(pdf, page_index, RENDER_DPI)
        page = Image.frombytes(
            "L", (rendered.width_px, rendered.height_px), rendered.pixels
        )
        for item, location in located:
            if location.page_index == page_index and location.crop is not None:
                name = _image_name(item, page_index)
                _cut(page, location).save(out / name)
                images[item.id] = name
    for item, location in located:
        if location.located is not Located.BLOCK_WORDS:
            _logger.warning(
                "edit %d (%r, block %s, page %s): %s",
                item.id,
                item.edit.old,
                item.edit.block_id,
                location.page_index,
                location.located.value,
            )
    sheet = Sheet(
        run=str(run),
        pdf=str(pdf),
        seed=seed,
        count=count,
        kinds=None if kinds is None else tuple(sorted(kinds)),
        edits_in_file=len(edits),
        edits=tuple(
            _entry(item, location, images.get(item.id)) for item, location in located
        ),
    )
    temporary = sheet_path.with_name(SHEET_NAME + ".tmp")
    temporary.write_text(_sheet_json(sheet), encoding="utf-8")
    temporary.replace(sheet_path)
    return sheet


def _value(content: dict[str, object], name: str, where: str) -> object:
    if name not in content:
        message = f"{where}: no field `{name}`"
        raise EditSheetError(message)
    return content[name]


def _wrong_type(name: str, value: object, where: str) -> EditSheetError:
    message = f"{where}: field `{name}` is {value!r}, of the wrong type"
    return EditSheetError(message)


def _field[T](content: dict[str, object], name: str, kind: type[T], where: str) -> T:
    """The field `name` of `content`, of type `kind` (a bool is no int)."""
    value = _value(content, name, where)
    if isinstance(value, kind) and not isinstance(value, bool):
        return value
    raise _wrong_type(name, value, where)


def _optional[T](
    content: dict[str, object], name: str, kind: type[T], where: str
) -> T | None:
    """The field `name` of `content`, of type `kind` or null."""
    value = _value(content, name, where)
    if value is None:
        return None
    if isinstance(value, kind) and not isinstance(value, bool):
        return value
    raise _wrong_type(name, value, where)


def _entry_from(content: object, where: str) -> SheetEntry:
    if not isinstance(content, dict):
        message = f"{where}: not a JSON object"
        raise EditSheetError(message)
    verdict = _field(content, "verdict", str, where)
    if verdict not in ("", *Verdict):
        message = (
            f"{where}: verdict {verdict!r} is none of "
            f'{", ".join(Verdict)} or "" (not judged)'
        )
        raise EditSheetError(message)
    located = _field(content, "located", str, where)
    if located not in tuple(Located):
        message = f"{where}: located {located!r} is none of {', '.join(Located)}"
        raise EditSheetError(message)
    return SheetEntry(
        id=_field(content, "id", int, where),
        page_index=_optional(content, "page_index", int, where),
        kind=_field(content, "kind", str, where),
        block_id=_field(content, "block_id", str, where),
        galley=_field(content, "galley", str, where),
        edit=_field(content, "edit", str, where),
        second_reading=_optional(content, "second_reading", str, where),
        located=Located(located),
        image=_optional(content, "image", str, where),
        verdict=verdict,
        note=_field(content, "note", str, where),
    )


def read_sheet(path: Path) -> Sheet:
    """The sheet written by edit_sheet at `path`, with the verdicts and
    notes a judge wrote into it. Raises EditSheetError, naming the file
    and the edit, for a file that is not JSON, a format_version other than
    SHEET_FORMAT_VERSION, a missing or mistyped field, or a verdict that is
    none of right, wrong, unclear and "" (not judged)."""
    try:
        content = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as err:
        message = f"{path} is not JSON: {err}"
        raise EditSheetError(message) from err
    where = str(path)
    if not isinstance(content, dict):
        message = f"{where}: not a JSON object"
        raise EditSheetError(message)
    version = _field(content, "format_version", int, where)
    if version != SHEET_FORMAT_VERSION:
        message = (
            f"{where}: format_version {version}; galley-eval reads "
            f"{SHEET_FORMAT_VERSION}"
        )
        raise EditSheetError(message)
    entries = _field(content, "edits", list, where)
    kinds = _optional(content, "kinds", list, where)
    return Sheet(
        run=_field(content, "run", str, where),
        pdf=_field(content, "pdf", str, where),
        seed=_field(content, "seed", int, where),
        count=_field(content, "count", int, where),
        kinds=None if kinds is None else tuple(str(kind) for kind in kinds),
        edits_in_file=_field(content, "edits_in_file", int, where),
        edits=tuple(
            _entry_from(entry, f"{where}, edit {position}")
            for position, entry in enumerate(entries, 1)
        ),
    )


def _scores_of(kind: str, verdicts: Sequence[str]) -> KindScores:
    counted = Counter(verdicts)
    return KindScores(
        kind=kind,
        right=counted[Verdict.RIGHT],
        wrong=counted[Verdict.WRONG],
        unclear=counted[Verdict.UNCLEAR],
        not_judged=counted[""],
    )


def sheet_scores(sheet: Sheet) -> tuple[KindScores, ...]:
    """The verdicts of `sheet` counted by kind of edit, the kinds in
    alphabetical order, then the total as kind "all"."""
    kinds = sorted({entry.kind for entry in sheet.edits})
    return (
        *(
            _scores_of(kind, [e.verdict for e in sheet.edits if e.kind == kind])
            for kind in kinds
        ),
        _scores_of("all", [entry.verdict for entry in sheet.edits]),
    )


def scores_table(scores: Sequence[KindScores]) -> str:
    """`scores` as a Markdown table, one row a kind."""
    rows = [
        "| kind | right | wrong | unclear | not judged | edits |",
        "|---|---:|---:|---:|---:|---:|",
        *(
            f"| {s.kind} | {s.right} | {s.wrong} | {s.unclear} "
            f"| {s.not_judged} | {s.edits} |"
            for s in scores
        ),
    ]
    return "\n".join(rows) + "\n"


class EditState(StrEnum):
    """Whether a new run of correct still makes a judged edit (spec section
    9b, "A sheet against a new run")."""

    KEPT = "kept"  # the same page, block, old and new
    KEPT_OTHER_CONTEXT = "kept_other_context"  # the same change, other context words
    DROPPED = "dropped"


@dataclass(frozen=True, slots=True)
class ComparedEdit:
    """A judged edit of a sheet, its verdict (None when not judged) and its
    state in the new edits file."""

    id: int
    verdict: Verdict | None
    state: EditState


@dataclass(frozen=True, slots=True, kw_only=True)
class Comparison:
    """A sheet's judged edits looked for in a new edits file: each edit's
    state, the number of edits in the judged run and in the new file."""

    edits: tuple[ComparedEdit, ...]
    edits_before: int
    edits_after: int


def _change(old: str, new: str) -> tuple[str, str]:
    """`old` and `new` less the characters they share at the start and at
    the end: "puem was" to "poem was" is "u" to "o"."""
    start = 0
    while start < min(len(old), len(new)) and old[start] == new[start]:
        start += 1
    end = 0
    while end < min(len(old), len(new)) - start and old[-1 - end] == new[-1 - end]:
        end += 1
    return old[start : len(old) - end], new[start : len(new) - end]


def _state(entry: SheetEntry, edits: Sequence[Edit]) -> EditState:
    same_place = [
        edit
        for edit in edits
        if edit.page_index == entry.page_index and edit.block_id == entry.block_id
    ]
    if any(edit.old == entry.galley and edit.new == entry.edit for edit in same_place):
        return EditState.KEPT
    change = _change(entry.galley, entry.edit)
    if any(
        (entry.galley in edit.old or edit.old in entry.galley)
        and _change(edit.old, edit.new) == change
        for edit in same_place
    ):
        return EditState.KEPT_OTHER_CONTEXT
    return EditState.DROPPED


def compare_sheet(sheet: Sheet, edits: Sequence[Edit]) -> Comparison:
    """Each edit of `sheet` looked for among `edits`, a new run's: kept
    when an edit has its page, block, old and new; kept with other context
    when an edit of its page and block makes the same change with context
    words gained or lost; dropped otherwise (spec section 9b)."""
    return Comparison(
        edits=tuple(
            ComparedEdit(
                entry.id,
                Verdict(entry.verdict) if entry.verdict else None,
                _state(entry, edits),
            )
            for entry in sheet.edits
        ),
        edits_before=sheet.edits_in_file,
        edits_after=len(edits),
    )


_KEPT_STATES: Final[frozenset[EditState]] = frozenset(
    {EditState.KEPT, EditState.KEPT_OTHER_CONTEXT}
)
_DROPPED_STATES: Final[frozenset[EditState]] = frozenset({EditState.DROPPED})


def _ids(comparison: Comparison, verdict: Verdict, states: frozenset[EditState]) -> str:
    """The ids of the edits of `verdict` whose state is one of `states`."""
    ids = [
        str(item.id)
        for item in comparison.edits
        if item.verdict is verdict and item.state in states
    ]
    return ", ".join(ids) if ids else "none"


def comparison_report(comparison: Comparison) -> str:
    """`comparison` as a Markdown table of kept, dropped and judged edits by
    verdict, then the edits before and after, and the ids of the right
    edits dropped and of the wrong and unclear ones kept; no edit's words."""
    rows = [
        "| verdict | kept | dropped | judged |",
        "|---|---:|---:|---:|",
    ]
    rows_of: tuple[tuple[str, tuple[Verdict | None, ...]], ...] = (
        *((verdict.value, (verdict,)) for verdict in Verdict),
        ("not judged", (None,)),
        ("all", (*Verdict, None)),
    )
    for label, verdicts in rows_of:
        items = [item for item in comparison.edits if item.verdict in verdicts]
        dropped = sum(1 for item in items if item.state is EditState.DROPPED)
        rows.append(f"| {label} | {len(items) - dropped} | {dropped} | {len(items)} |")
    other = sum(
        1 for item in comparison.edits if item.state is EditState.KEPT_OTHER_CONTEXT
    )
    return (
        "\n".join(
            [
                *rows,
                "",
                (
                    f"edits: {comparison.edits_before} in the judged run, "
                    f"{comparison.edits_after} in the new file"
                ),
                f"kept with other context: {other}",
                f"right dropped: {_ids(comparison, Verdict.RIGHT, _DROPPED_STATES)}",
                f"wrong kept: {_ids(comparison, Verdict.WRONG, _KEPT_STATES)}",
                f"unclear kept: {_ids(comparison, Verdict.UNCLEAR, _KEPT_STATES)}",
            ]
        )
        + "\n"
    )
