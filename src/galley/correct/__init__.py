"""The correct stage: a local vision model, served by LM Studio, reads each
text page, and where its words line up with galley's and differ, its words
become edits in edits/correct.jsonl, which markdown applies
(docs/specs/correct.md).

It reads the PDF, pages.json, words.json and blocks.json, and writes only
edits/correct.jsonl. It never changes a note marker or reference, a label,
a running head, the order of blocks, or a page that is not a text page.
"""

import io
import logging
from collections.abc import Mapping
from dataclasses import dataclass

from PIL import Image

from galley import pdfium
from galley.book_folder import BookFolder, Stage, delete_stage_outputs
from galley.config import BookConfig
from galley.correct._lmstudio import Reading, check_models, read_image
from galley.correct._merge import (
    Answer,
    Change,
    answer,
    block_edits,
    is_doubtful,
    page_changes,
)
from galley.correct._reading import GalleyToken, Place, page_reading, split_counts
from galley.model import (
    Block,
    BlocksFile,
    Edit,
    PageKind,
    RenderedPage,
    check_source_pdf,
    read_blocks,
    read_checked_input,
    read_words,
    write_edits,
)
from galley.parallel import DEFAULT_WORKERS, map_pages

__all__ = ["check_server", "run"]

_logger = logging.getLogger(__name__)

# Section 4: the page is read at 300 dpi, as the measurement read it.
_DPI = 300
# Section 2: the footnote band starts this far above the highest note.
_BAND_MARGIN_PT = 4


def check_server(config: BookConfig) -> None:
    """ExternalProgramError when LM Studio's server at config.correct_server
    does not answer, or does not list config.correct_model or, when given,
    config.correct_second_model among its models."""
    models = (config.correct_model,) + (
        (config.correct_second_model,)
        if config.correct_second_model is not None
        else ()
    )
    check_models(config.correct_server, models)


@dataclass(frozen=True, slots=True, kw_only=True)
class _PageWork:
    """What a worker needs for one page: galley's reading of it, the core
    of each changeable token, and the top of its footnote band in points,
    None when it has no notes."""

    page_index: int
    reading: tuple[GalleyToken, ...]
    cores: Mapping[Place, str]
    band_top: float | None


@dataclass(frozen=True, slots=True)
class _PageResult:
    page_index: int
    changes: tuple[Change, ...]
    cut_short: bool


def _all_blocks(blocks: BlocksFile) -> tuple[Block, ...]:
    return blocks.blocks + tuple(
        block for note in blocks.notes for block in note.blocks
    )


def _band_top(blocks: BlocksFile, page_index: int) -> float | None:
    tops = [
        origin.box.top
        for note in blocks.notes
        for block in note.blocks
        for origin in block.origin
        if origin.page_index == page_index
    ]
    return min(tops) - _BAND_MARGIN_PT if tops else None


def _png(rendered: RenderedPage, top_pt: float | None) -> bytes:
    """The rendered page as a grayscale PNG, cut from `top_pt` down when it
    is given."""
    image = Image.frombytes(
        "L", (rendered.width_px, rendered.height_px), rendered.pixels
    )
    if top_pt is not None:
        top_px = max(0, int(top_pt * rendered.dpi / pdfium.POINTS_PER_INCH))
        image = image.crop((0, top_px, rendered.width_px, rendered.height_px))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _read_page(config: BookConfig, work: _PageWork) -> _PageResult:
    """Render the page, have the model read it (and the second model its
    footnote band), and make its changes."""
    rendered = pdfium.render(config.pdf, work.page_index, _DPI)
    what = f"page {work.page_index}"
    reading = read_image(
        config.correct_server, config.correct_model, _png(rendered, None), what
    )
    if reading.cut_short:
        return _PageResult(work.page_index, (), cut_short=True)
    second: Answer | None = None
    if config.correct_second_model is not None and work.band_top is not None:
        second_reading: Reading = read_image(
            config.correct_server,
            config.correct_second_model,
            _png(rendered, work.band_top),
            f"the footnote band of {what}",
        )
        second = answer(second_reading.text)
    changes = page_changes(
        work.page_index, work.reading, answer(reading.text), work.cores, second
    )
    return _PageResult(work.page_index, changes, cut_short=False)


def _cores(blocks: BlocksFile, reading: tuple[GalleyToken, ...]) -> dict[Place, str]:
    spans = {block.id: block.spans for block in _all_blocks(blocks)}
    return {
        token.place: spans[token.place.block_id][token.place.span_index].text[
            token.place.start : token.place.end
        ]
        for token in reading
        if token.place is not None
    }


def edits_of(
    blocks: BlocksFile, changes: tuple[Change, ...], model: str
) -> tuple[Edit, ...]:
    """The edits of `changes`, in page order and, on a page, in the order of
    galley's reading: each block's edits come where its first change is."""
    by_block: dict[str, list[Change]] = {}
    for change in changes:
        by_block.setdefault(change.place.block_id, []).append(change)
    block_by_id = {block.id: block for block in _all_blocks(blocks)}
    return tuple(
        edit
        for block_id, block_changes in by_block.items()
        for edit in block_edits(block_by_id[block_id], block_changes, model)
    )


def run(
    folder: BookFolder, config: BookConfig, *, workers: int = DEFAULT_WORKERS
) -> None:
    """Write edits/correct.jsonl: the vision model's fixes to galley's words
    of every text page, as edits (docs/specs/correct.md).

    Deletes edits/correct.jsonl, book.md and book.epub first. Raises
    ExternalProgramError when LM Studio does not answer or lacks the model,
    and InputFileError for an input made from another PDF.
    """
    delete_stage_outputs(folder, Stage.CORRECT)
    pages, blocks = read_checked_input(
        folder.pages_json, config.pdf, folder.blocks_json, read_blocks
    )
    words = read_words(folder.words_json)
    check_source_pdf(
        folder.words_json, words.source_pdf_sha256, pages.source_pdf_sha256
    )
    check_server(config)
    splits = {
        block.id: split_counts(block, words)
        for block in _all_blocks(blocks)
        if len(block.origin) > 1
    }
    work = []
    for page in pages.pages:
        if page.kind is not PageKind.TEXT:
            continue
        reading = page_reading(blocks, page.index, splits)
        if any(token.place is not None for token in reading):
            work.append(
                _PageWork(
                    page_index=page.index,
                    reading=reading,
                    cores=_cores(blocks, reading),
                    band_top=_band_top(blocks, page.index),
                )
            )
    results = map_pages(lambda item: _read_page(config, item), work, workers)
    changes = tuple(change for result in results for change in result.changes)
    edits = edits_of(blocks, changes, config.correct_model)
    folder.edits_dir.mkdir(exist_ok=True)
    write_edits(folder.correct_jsonl, edits)
    cut_short = [result.page_index for result in results if result.cut_short]
    for page_index in cut_short:
        _logger.warning(
            "page %d: the model's answer was cut short; the page is left as "
            "galley read it",
            page_index,
        )
    doubtful = sum(1 for change in changes if is_doubtful(change))
    _logger.info(
        "wrote %s: %d edits on %d pages%s%s",
        folder.correct_jsonl,
        len(edits),
        len(work),
        f", {doubtful} doubtful by the second reading"
        if config.correct_second_model is not None
        else "",
        f"; left as galley read them: pages {', '.join(map(str, cut_short))}"
        if cut_short
        else "",
    )
