"""The correct stage: a local vision model, served by LM Studio, reads each
text page, and where its words line up with galley's and differ, its words
become edits in edits/correct.jsonl, which markdown applies
(docs/specs/correct.md).

It reads the PDF, pages.json, words.json and blocks.json, and writes
edits/correct.jsonl; it keeps every answer of the model under answers/ and
reads it there instead of asking again when the request is the same
(section 4b). It never changes a note marker or reference, a label,
a running head, the order of blocks, or a page that is not a text page.
"""

import io
import logging
from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from galley import pdfium, wordlist
from galley.book_folder import BookFolder, Stage, delete_stage_outputs
from galley.config import BookConfig
from galley.correct._answers import AnswerSource, kept_or_read, once
from galley.correct._links import (
    Link,
    galley_references,
    link_answer,
    link_edits,
    page_links,
)
from galley.correct._lmstudio import LINKS_PROMPT, PROMPT, Reading, check_models
from galley.correct._merge import (
    Answer,
    Change,
    WordList,
    answer,
    block_edits,
    is_doubtful,
    page_changes,
)
from galley.correct._reading import GalleyToken, Place, page_reading, split_counts
from galley.correct._tokens import tokens
from galley.model import (
    AnswerKind,
    BlocksFile,
    Edit,
    Note,
    NoteKind,
    PageKind,
    RenderedPage,
    check_source_pdf,
    every_block,
    read_blocks,
    read_checked_input,
    read_words,
    write_edits,
)
from galley.parallel import DEFAULT_WORKERS, map_pages

__all__ = [
    "check_server",
    "edits_of",
    "footnote_band_top",
    "footnotes_starting",
    "page_png",
    "run",
    "token_cores",
]

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
    None when it has no notes; the footnotes that start on it, and the note
    galley's reference after a token's word refers to, by its place."""

    page_index: int
    reading: tuple[GalleyToken, ...]
    cores: Mapping[Place, str]
    band_top: float | None
    notes: tuple[Note, ...]
    galley_references: Mapping[Place, str]


@dataclass(frozen=True, slots=True)
class _PageResult:
    page_index: int
    changes: tuple[Change, ...]
    cut_short: bool
    links: tuple[Link, ...] = ()
    links_cut_short: bool = False
    # Where each of the page's answers came from (section 4b).
    sources: tuple[AnswerSource, ...] = ()


def footnote_band_top(blocks: BlocksFile, page_index: int) -> float | None:
    """The top of the page's footnote band in points (section 2): 4 pt above
    the highest note block printed on it; None when no note is."""
    tops = [
        origin.box.top
        for note in blocks.notes
        for block in note.blocks
        for origin in block.origin
        if origin.page_index == page_index
    ]
    return min(tops) - _BAND_MARGIN_PT if tops else None


def page_png(rendered: RenderedPage, top_pt: float | None) -> bytes:
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


def _read_page(
    config: BookConfig,
    answers_dir: Path,
    check_server_once: Callable[[], None],
    known_words: WordList,
    work: _PageWork,
) -> _PageResult:
    """Render the page, have the model read it (and the second model its
    footnote band), and make its changes; on a page where a note starts,
    have the model mark the note references too (section 9b). Each answer
    is the one kept in `answers_dir` when the request is the same (section
    4b); `check_server_once` runs before a request is sent. `known_words`
    is the book's word list, for the guards of a merge (section 7)."""
    rendered = pdfium.render(config.pdf, work.page_index, _DPI)
    png = page_png(rendered, None)
    what = f"page {work.page_index}"
    sources: list[AnswerSource] = []

    def read(
        kind: AnswerKind, model: str, image: bytes, about: str, prompt: str
    ) -> Reading:
        reading, source = kept_or_read(
            answers_dir,
            kind,
            work.page_index,
            config.correct_server,
            model,
            image,
            about,
            prompt,
            check_server_once,
        )
        sources.append(source)
        return reading

    reading = read(AnswerKind.PAGE, config.correct_model, png, what, PROMPT)
    changes: tuple[Change, ...] = ()
    if not reading.cut_short:
        second: Answer | None = None
        if config.correct_second_model is not None and work.band_top is not None:
            second_reading = read(
                AnswerKind.BAND,
                config.correct_second_model,
                page_png(rendered, work.band_top),
                f"the footnote band of {what}",
                PROMPT,
            )
            second = answer(second_reading.text)
        changes = page_changes(
            work.page_index,
            work.reading,
            answer(reading.text),
            work.cores,
            second,
            known_words=known_words,
        )
    links: tuple[Link, ...] = ()
    links_cut_short = False
    if work.notes:
        marked = read(
            AnswerKind.LINKS,
            config.correct_model,
            png,
            f"the note references of {what}",
            LINKS_PROMPT,
        )
        links_cut_short = marked.cut_short
        if not marked.cut_short:
            links = page_links(
                work.page_index,
                work.reading,
                work.notes,
                link_answer(marked.text),
                work.galley_references,
            )
    return _PageResult(
        work.page_index,
        changes,
        cut_short=reading.cut_short,
        links=links,
        links_cut_short=links_cut_short,
        sources=tuple(sources),
    )


def footnotes_starting(blocks: BlocksFile, page_index: int) -> tuple[Note, ...]:
    """The footnotes whose first origin is on the page: the notes a link
    may go to, and on whose pages the model is asked for the references
    (section 9b). An endnote is not one: Gierke's start on 93 pages."""
    return tuple(
        note
        for note in blocks.notes
        if note.kind is NoteKind.FOOTNOTE
        and note.origin
        and note.origin[0].page_index == page_index
    )


def token_cores(
    blocks: BlocksFile, reading: tuple[GalleyToken, ...]
) -> frozendict[Place, str]:
    """The core of each changeable token of `reading`, by its place: the
    text of the token's span between its start and end."""
    spans = {block.id: block.spans for block in every_block(blocks)}
    return frozendict(
        {
            token.place: spans[token.place.block_id][token.place.span_index].text[
                token.place.start : token.place.end
            ]
            for token in reading
            if token.place is not None
        }
    )


def edits_of(
    blocks: BlocksFile, changes: tuple[Change, ...], model: str
) -> tuple[Edit, ...]:
    """The edits of `changes`, in page order and, on a page, in the order of
    galley's reading (section 8): a block's edits come where its first
    change is, and those of a block printed on two pages on each page."""
    by_block: dict[str, list[Change]] = {}
    for change in changes:
        by_block.setdefault(change.place.block_id, []).append(change)
    block_by_id = {block.id: block for block in every_block(blocks)}
    edits = (
        edit
        for block_id, block_changes in by_block.items()
        for edit in block_edits(block_by_id[block_id], block_changes, model)
    )
    # A stable sort: on a page the order of the reading stays.
    return tuple(sorted(edits, key=lambda edit: edit.page_index or 0))


def run(
    folder: BookFolder, config: BookConfig, *, workers: int = DEFAULT_WORKERS
) -> None:
    """Write edits/correct.jsonl: the vision model's fixes to galley's words
    of every text page, as edits (docs/specs/correct.md).

    Deletes edits/correct.jsonl, book.md and book.epub first, never
    answers/: each answer of the model is kept there and read instead of
    asking again when the request is the same (section 4b). Raises
    ExternalProgramError when a request is to be sent and LM Studio does
    not answer or lacks the model,
    and InputFileError for an input made from another PDF or a kept answer
    that cannot be read.
    """
    delete_stage_outputs(folder, Stage.CORRECT)
    pages, blocks = read_checked_input(
        folder.pages_json, config.pdf, folder.blocks_json, read_blocks
    )
    words = read_words(folder.words_json)
    check_source_pdf(
        folder.words_json, words.source_pdf_sha256, pages.source_pdf_sha256
    )
    splits = {
        block.id: split_counts(block, words)
        for block in every_block(blocks)
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
                    cores=token_cores(blocks, reading),
                    band_top=footnote_band_top(blocks, page.index),
                    notes=footnotes_starting(blocks, page.index)
                    if config.correct_links
                    else (),
                    galley_references=galley_references(blocks, reading)
                    if config.correct_links
                    else frozendict(),
                )
            )
    folder.answers_dir.mkdir(exist_ok=True)
    # Section 4: LM Studio is checked once, before the first request sent.
    check_server_once = once(lambda: check_server(config))
    known_words = WordList.of(
        wordlist.word_list(config.language, wordlist.DEFAULT_CACHE_DIR),
        frozendict(
            Counter(
                token.form
                for block in every_block(blocks)
                for span in block.spans
                for token in tokens(span.text)
            )
        ),
    )
    results = map_pages(
        lambda item: _read_page(
            config, folder.answers_dir, check_server_once, known_words, item
        ),
        work,
        workers,
    )
    changes = tuple(change for result in results for change in result.changes)
    word_edits = edits_of(blocks, changes, config.correct_model)
    links = link_edits(
        blocks,
        tuple(link for result in results for link in result.links),
        changes,
        word_edits,
        config.correct_model,
    )
    edits = word_edits + links
    folder.edits_dir.mkdir(exist_ok=True)
    write_edits(folder.correct_jsonl, edits)
    for result in results:
        if result.links_cut_short:
            _logger.warning(
                "page %d: the model's answer for the note references was cut "
                "short; no links on it",
                result.page_index,
            )
    cut_short = [result.page_index for result in results if result.cut_short]
    for page_index in cut_short:
        _logger.warning(
            "page %d: the model's answer was cut short; the page is left as "
            "galley read it",
            page_index,
        )
    doubtful = sum(1 for change in changes if is_doubtful(change))
    sources = [source for result in results for source in result.sources]
    _logger.info(
        "wrote %s: %d edits, %d of them note links, on %d pages, from %d "
        "answers kept in %s and %d asked of the model%s%s",
        folder.correct_jsonl,
        len(edits),
        len(links),
        len(work),
        sources.count(AnswerSource.KEPT),
        folder.answers_dir,
        sources.count(AnswerSource.ASKED),
        f", {doubtful} doubtful by the second reading"
        if config.correct_second_model is not None
        else "",
        f"; left as galley read them: pages {', '.join(map(str, cut_short))}"
        if cut_short
        else "",
    )
