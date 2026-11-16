"""The comparison of one book: galley's four stage outputs against the
reference, as a frozen Evaluation of scores, differences and pages (spec
sections 5 to 9). `evaluate` reads the files; `evaluation_of` does the
rest and touches none.

How the spec is read here, where it leaves a choice:

- One difference is written per pairing of markdown other than matched:
  a missing, changed, split or glued pairing, and one per extra token.
  A changed pair of subkind `convention` is a difference too.
- A pairing with several reference tokens, a glued one, is attributed to
  the latest of their stages: the output from which none of them is
  matched again.
- `state` and `subkind` are those of the pairing at markdown;
  `state_at_stage` and `subkind_at_stage` those of the first reference
  token's pairing at the attributed output, `extra` for an extra token.
- A difference's `edge_of_page` is that of its extra token at the output
  it is attributed to, or, for a reference token, whether a galley token
  of its pairing at that output is flagged.
- A difference's page is that of its first reference token, or of its
  extra token. Its printed page is that of the first body anchor whose
  page is that page.
- `context` holds up to 8 reference tokens before and after the
  difference, within its stream (the body or the notes). For an extra
  token, it holds up to 8 galley tokens at markdown before and after it
  on its page.
- A difference that is unplaced, or on a page of `exclude_pages` or
  `not_in_reference`, is written with `apart` saying which, and is not
  scored.
- The tokens of a reference note that galley makes an endnote at blocks
  are `not_scored` at words and lines, and taken as matched there for the
  attribution to stages.
- The cause `endnote_reference_far` pairs a reference note with a galley
  endnote at markdown, for the cause only, when the note is not found
  `as_note` there and at least half of its tokens with a non-empty key
  have their key, counted with repeats, among the endnote's. The
  endnote's first reference is placed by the `near_page` of its tokens;
  the reference text's by the page of the reference token before its
  first reference to the note.
"""

import dataclasses
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from galley import wordlist
from galley.book_folder import BookFolder
from galley_eval.align import (
    Alignment,
    GalleyToken,
    ReferencePlace,
    State,
    Subkind,
    align,
    alignment_key,
    equal_key_share,
    extra_tokens,
    reference_side,
    reference_states,
)
from galley_eval.books import EvaluationBook
from galley_eval.errors import AlignmentError, BooksFileError
from galley_eval.galley_side import GalleySide, read_galley_side
from galley_eval.page_table import PageRow, page_rows
from galley_eval.pages import AnchorPage, reference_pages
from galley_eval.reader import PageAnchor, ReferenceText, Stream, read_reference_file
from galley_eval.scores import (
    BoundaryScores,
    HeadingScores,
    KindCount,
    MarginNoteScores,
    NoteScores,
    Part,
    Placement,
    TextScores,
    block_kinds,
    endnote_notes,
    galley_parts,
    heading_scores,
    kinds_right,
    margin_note_scores,
    note_scores,
    notes_found_as_notes,
    page_parts,
    paragraph_boundaries,
    reference_part,
    text_scores,
)
from galley_eval.stages import StageOutput, TracedExtra, token_fate, trace_extras

__all__ = [
    "Apart",
    "Cause",
    "Difference",
    "Evaluation",
    "OutputScores",
    "Scorecard",
    "UnplacedRun",
    "evaluate",
    "evaluation_of",
]

# The lowest share of the reference's tokens that galley's words must align
# to a token with the same key; a guess, under Mariéjol's 76.0% in the
# first build (spec section 5).
_LEAST_EQUAL_KEY_SHARE = 0.5

# The reference tokens given before and after a difference; a choice,
# enough to find the place in the book (spec section 7).
_CONTEXT_TOKENS = 8


# The outputs where galley has no notes yet, so that an endnote cannot be
# aligned near its reference (spec section 5).
_BEFORE_NOTES = frozenset((StageOutput.WORDS, StageOutput.LINES))


class Apart(StrEnum):
    """Why a difference is listed apart and not scored."""

    UNPLACED = "unplaced"
    EXCLUDED_PAGE = "excluded_page"
    NOT_IN_REFERENCE = "not_in_reference"


class Cause(StrEnum):
    """What is known to have caused a difference (spec section 7)."""

    # galley linked an endnote to a reference more than a page from the
    # reference text's, so the note is out of the alignment's window.
    ENDNOTE_REFERENCE_FAR = "endnote_reference_far"


@dataclass(frozen=True, slots=True, kw_only=True)
class Difference:
    """One line of `differences.jsonl` (spec section 7): its state and
    subkind at markdown, the error of the book, and at `stage`, the output
    it is attributed to."""

    stage: StageOutput
    state: State
    subkind: Subkind | None
    state_at_stage: State
    subkind_at_stage: Subkind | None
    part: Part
    page_index: int | None
    printed_page: str | None
    reference: tuple[str, ...]
    galley: tuple[str, ...]
    context_before: tuple[str, ...]
    context_after: tuple[str, ...]
    block_id: str | None
    note_id: str | None
    edge_of_page: bool
    apart: Apart | None
    cause: Cause | None


@dataclass(frozen=True, slots=True, kw_only=True)
class OutputScores:
    """The scores of one stage output. The structure scores are None at
    words and lines."""

    output: StageOutput
    text: frozendict[Part, TextScores]
    paragraph_boundaries: frozendict[Part, BoundaryScores] | None
    block_kinds: frozendict[Part, tuple[KindCount, ...]] | None
    kinds_right: frozendict[Part, int] | None
    headings: HeadingScores | None
    notes: NoteScores | None
    margin_notes: MarginNoteScores | None


@dataclass(frozen=True, slots=True, kw_only=True)
class Scorecard:
    """The scores of a book at the four outputs, and the counts that say
    how far the alignment can be trusted. galley's commit and the date
    are added when it is written."""

    book: str
    gutenberg_number: int
    equal_key_share: float
    anchor_mismatches: int
    unplaced: int
    outputs: tuple[OutputScores, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class UnplacedRun:
    """Consecutive reference tokens whose page cannot be known, with the
    reference tokens before them."""

    tokens: tuple[str, ...]
    context_before: tuple[str, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class Evaluation:
    """What the comparison of one book found: the scorecard, the
    differences, the table of pages, and what `summary.md` lists apart:
    the anchor mismatches, the unplaced tokens and the page anchors among
    the notes."""

    scorecard: Scorecard
    differences: tuple[Difference, ...]
    pages: tuple[PageRow, ...]
    anchor_mismatches: tuple[AnchorPage, ...]
    unplaced: tuple[UnplacedRun, ...]
    anchors_in_notes: tuple[PageAnchor, ...]


def evaluate(
    book: EvaluationBook,
    folder: BookFolder,
    reference_html: Path,
    *,
    word_list: frozenset[str] | None = None,
) -> Evaluation:
    """Compare galley's files in `folder` with the reference; write nothing.

    `word_list` is the set of lowered words of the book's language, by
    default galley's word list. Raises ReferenceReadError when the HTML
    cannot be read, galley's InputFileError or ExternalProgramError when
    its files or Pandoc fail, GalleyFilesError when its files do not fit
    together, and AlignmentError when galley's words align less than half
    of the reference."""
    side = read_galley_side(folder)
    reference = read_reference_file(reference_html, book.rules, book.html_sha256)
    words = (
        word_list
        if word_list is not None
        else frozenset(word.lower() for word in wordlist.word_list(book.language))
    )
    return evaluation_of(book, reference, side, words)


def evaluation_of(
    book: EvaluationBook,
    reference: ReferenceText,
    side: GalleySide,
    word_list: frozenset[str],
) -> Evaluation:
    """The comparison of galley's side `side` with `reference`, for
    `book`; `word_list` holds the lowered words of its language."""
    _check_body_pages(book, side)
    prepared = reference_side(reference)
    places = prepared.places
    outputs = (side.words, side.lines, side.blocks, side.markdown)
    words_alignment = align(reference, side.words, prepared)
    share = equal_key_share(words_alignment, places, side.words)
    if share < _LEAST_EQUAL_KEY_SHARE:
        message = (
            f"galley's words of {book.name} align only {share:.1%} of the "
            f"reference's tokens to a token with the same key, under "
            f"{_LEAST_EQUAL_KEY_SHARE:.0%}: a wrong scan or a broken reading rule "
            "is likelier than galley being that far off"
        )
        raise AlignmentError(message)
    alignments = (words_alignment,) + tuple(
        align(reference, galley, prepared) for galley in outputs[1:]
    )
    pages = reference_pages(
        reference, words_alignment, side.words, frozenset(book.exclude_pages)
    )
    parts = tuple(reference_part(place) for place in places)
    parts_of_pages = page_parts(places, pages.page_indices)
    apart_pages = _apart_pages(book)
    placements = tuple(
        Placement.UNPLACED
        if page is None
        else Placement.NOT_SCORED
        if page in apart_pages
        else Placement.SCORED
        for page in pages.page_indices
    )
    in_endnotes = endnote_notes(alignments[2], places, side.blocks, side.galley_blocks)
    endnote_tokens = frozenset(
        index
        for index, place in enumerate(places)
        if place.note_index is not None and place.note_index in in_endnotes
    )
    early_placements = tuple(
        Placement.NOT_SCORED
        if index in endnote_tokens and placement is Placement.SCORED
        else placement
        for index, placement in enumerate(placements)
    )
    states = tuple(
        tuple(
            State.MATCHED
            if output in _BEFORE_NOTES and index in endnote_tokens
            else state
            for index, state in enumerate(reference_states(alignment))
        )
        for output, alignment in zip(StageOutput, alignments, strict=True)
    )
    fates = tuple(
        token_fate((at_words, at_lines, at_blocks, at_markdown))
        for at_words, at_lines, at_blocks, at_markdown in zip(*states, strict=True)
    )
    printed_pages = _printed_pages(pages.anchors)
    output_scores = tuple(
        _output_scores(
            output,
            alignment,
            galley,
            book=book,
            reference=reference,
            side=side,
            places=places,
            parts=parts,
            placements=early_placements
            if output in {StageOutput.WORDS, StageOutput.LINES}
            else placements,
            page_indices=pages.page_indices,
            parts_of_pages=parts_of_pages,
            apart_pages=apart_pages,
            repaired=None
            if output is StageOutput.WORDS
            else tuple(fate.repaired_by is output for fate in fates),
        )
        for output, alignment, galley in zip(
            StageOutput, alignments, outputs, strict=True
        )
    )
    far_notes, far_endnotes = _far_endnotes(
        reference, alignments[-1], places, side, pages.page_indices
    )
    differences = _reference_differences(
        alignments,
        outputs,
        places,
        far_notes=far_notes,
        parts=parts,
        page_indices=pages.page_indices,
        fates=tuple(fate.difference_stage for fate in fates),
        printed_pages=printed_pages,
        side=side,
        apart_pages=apart_pages,
    ) + _extra_differences(
        alignments,
        outputs,
        far_endnotes=far_endnotes,
        parts_of_pages=parts_of_pages,
        printed_pages=printed_pages,
        side=side,
        apart_pages=apart_pages,
    )
    mismatches = tuple(anchor for anchor in pages.anchors if anchor.anchor_mismatch)
    unplaced = _unplaced_runs(places, pages.page_indices)
    return Evaluation(
        scorecard=Scorecard(
            book=book.name,
            gutenberg_number=book.gutenberg_number,
            equal_key_share=share,
            anchor_mismatches=len(mismatches),
            unplaced=sum(len(run.tokens) for run in unplaced),
            outputs=output_scores,
        ),
        differences=differences,
        pages=page_rows(
            side.words_file,
            side.words,
            words_alignment,
            places,
            page_indices=pages.page_indices,
            parts_of_pages=parts_of_pages,
            printed_pages=printed_pages,
            word_list=word_list,
            language=book.language,
        ),
        anchor_mismatches=mismatches,
        unplaced=unplaced,
        anchors_in_notes=reference.anchors_in_notes,
    )


def _check_body_pages(book: EvaluationBook, side: GalleySide) -> None:
    """Raises BooksFileError when the book's body range ends after the
    PDF's last page, as galley's words.json counts its pages."""
    last_page = max((page.index for page in side.words_file.pages), default=-1)
    if book.body_pages[1] > last_page:
        message = (
            f"the body range of {book.name}, body_pages = "
            f"[{book.body_pages[0]}, {book.body_pages[1]}], ends after the "
            f"PDF's last page index, {last_page}"
        )
        raise BooksFileError(message)


def _far_endnotes(
    reference: ReferenceText,
    alignment: Alignment,
    places: tuple[ReferencePlace, ...],
    side: GalleySide,
    page_indices: tuple[int | None, ...],
) -> tuple[frozenset[int], frozenset[str]]:
    """The reference notes, by index, and the galley endnotes, by id, whose
    differences have the cause `endnote_reference_far`: a note not found
    as a note at markdown, `alignment`, that is the same note by its keys
    as a galley endnote whose first reference galley placed more than one
    page from the reference text's."""
    near, keys = _linked_endnotes(side)
    if not near:
        return frozenset(), frozenset()
    found = notes_found_as_notes(alignment, places, side.markdown, side.galley_blocks)
    by_note: dict[int, list[int]] = {}
    for index, place in enumerate(places):
        if place.note_index is not None:
            by_note.setdefault(place.note_index, []).append(index)
    gutenberg_page = _gutenberg_reference_pages(reference, page_indices)
    far_notes: set[int] = set()
    far_endnotes: set[str] = set()
    for note_index, indices in by_note.items():
        if note_index in found:
            continue  # found as a note: no cause to give
        note = Counter(
            key for index in indices if (key := alignment_key(places[index].token.text))
        )
        total = note.total()
        if total == 0:
            continue
        shared = {
            note_id: (note & endnote).total() for note_id, endnote in keys.items()
        }
        best = max(shared, key=lambda note_id: shared[note_id])
        page = gutenberg_page.get(reference.notes[note_index].note_id)
        if (
            shared[best] * 2 >= total
            and page is not None
            and abs(near[best] - page) > 1
        ):
            far_notes.add(note_index)
            far_endnotes.add(best)
    return frozenset(far_notes), frozenset(far_endnotes)


def _linked_endnotes(
    side: GalleySide,
) -> tuple[dict[str, int], dict[str, Counter[str]]]:
    """For each galley endnote linked from a reference, the page of its
    first reference, and the alignment keys of its tokens at markdown."""
    near: dict[str, int] = {}
    keys: dict[str, Counter[str]] = {}
    for token in side.markdown:
        if token.block_id is None or token.near_page is None:
            continue
        note_id = side.galley_blocks[token.block_id].note_id
        if note_id is None:
            continue
        near[note_id] = token.near_page
        key = alignment_key(token.text)
        if key:
            keys.setdefault(note_id, Counter())[key] += 1
    return near, keys


def _gutenberg_reference_pages(
    reference: ReferenceText, page_indices: tuple[int | None, ...]
) -> dict[str, int]:
    """For each reference note, the page of the body token before the
    reference text's first reference to it."""
    pages: dict[str, int] = {}
    for note_reference in reference.note_references:
        gap = note_reference.gap
        if gap.stream is not Stream.BODY or note_reference.note_id in pages:
            continue
        page = page_indices[max(gap.token_index - 1, 0)] if page_indices else None
        if page is not None:
            pages[note_reference.note_id] = page
    return pages


def _apart_pages(book: EvaluationBook) -> frozendict[int, Apart]:
    return frozendict(
        {page: Apart.NOT_IN_REFERENCE for page in book.not_in_reference}
        | {page: Apart.EXCLUDED_PAGE for page in book.exclude_pages}
    )


def _printed_pages(anchors: tuple[AnchorPage, ...]) -> frozendict[int, str]:
    found: dict[int, str] = {}
    for anchor in anchors:
        if anchor.page_index is not None and anchor.page_index not in found:
            found[anchor.page_index] = anchor.anchor.printed_page
    return frozendict(found)


def _output_scores(
    output: StageOutput,
    alignment: Alignment,
    galley: tuple[GalleyToken, ...],
    *,
    book: EvaluationBook,
    reference: ReferenceText,
    side: GalleySide,
    places: tuple[ReferencePlace, ...],
    parts: tuple[Part, ...],
    placements: tuple[Placement, ...],
    page_indices: tuple[int | None, ...],
    parts_of_pages: frozendict[int, Part],
    apart_pages: frozendict[int, Apart],
    repaired: tuple[bool, ...] | None,
) -> OutputScores:
    text = text_scores(
        alignment,
        galley,
        parts=parts,
        placements=placements,
        galley_part=galley_parts(galley, parts_of_pages),
        galley_scored=tuple(token.page_index not in apart_pages for token in galley),
        repaired=repaired,
    )
    if output in {StageOutput.WORDS, StageOutput.LINES}:
        return OutputScores(
            output=output,
            text=text,
            paragraph_boundaries=None,
            block_kinds=None,
            kinds_right=None,
            headings=None,
            notes=None,
            margin_notes=None,
        )
    kinds = block_kinds(alignment, places, galley, side.galley_blocks, parts)
    return OutputScores(
        output=output,
        text=text,
        paragraph_boundaries=paragraph_boundaries(
            alignment, places, galley, parts, galley_blocks=side.galley_blocks
        ),
        block_kinds=kinds,
        kinds_right=kinds_right(kinds),
        headings=heading_scores(
            alignment,
            places,
            galley,
            side.galley_blocks,
            page_indices=page_indices,
            body_pages=book.body_pages,
        ),
        notes=note_scores(
            reference,
            alignment,
            places,
            galley,
            side.galley_blocks,
            side.note_references,
        ),
        margin_notes=_margin_notes(book, margin_note_scores(alignment, places, galley)),
    )


def _margin_notes(book: EvaluationBook, scores: MarginNoteScores) -> MarginNoteScores:
    """The margin note scores, without their position when Gutenberg moved
    the book's margin notes."""
    if book.margin_notes_moved:
        return dataclasses.replace(scores, position_right=None)
    return scores


def _context(
    places: tuple[ReferencePlace, ...], first: int, last: int
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """The reference tokens of the same stream before `first` and after
    `last`, up to _CONTEXT_TOKENS each."""
    stream = places[first].stream
    start = first
    while (
        start > 0
        and first - start < _CONTEXT_TOKENS
        and places[start - 1].stream is stream
    ):
        start -= 1
    end = last + 1
    while (
        end < len(places)
        and end - last - 1 < _CONTEXT_TOKENS
        and places[end].stream is stream
    ):
        end += 1
    return (
        tuple(place.token.text for place in places[start:first]),
        tuple(place.token.text for place in places[last + 1 : end]),
    )


def _stage_of(
    fates: Sequence[StageOutput | None], indices: tuple[int, ...]
) -> StageOutput:
    order = tuple(StageOutput)
    stages = tuple(fate for index in indices if (fate := fates[index]) is not None)
    return max(stages, key=order.index)


def _reference_differences(
    alignments: tuple[Alignment, ...],
    outputs: tuple[tuple[GalleyToken, ...], ...],
    places: tuple[ReferencePlace, ...],
    *,
    far_notes: frozenset[int],
    parts: tuple[Part, ...],
    page_indices: tuple[int | None, ...],
    fates: tuple[StageOutput | None, ...],
    printed_pages: frozendict[int, str],
    side: GalleySide,
    apart_pages: frozendict[int, Apart],
) -> tuple[Difference, ...]:
    markdown_alignment, markdown = alignments[-1], outputs[-1]
    stage_position = {output: position for position, output in enumerate(StageOutput)}
    differences: list[Difference] = []
    for pairing in sorted(
        (
            pairing
            for pairing in markdown_alignment.pairings
            if pairing.state not in {State.MATCHED, State.EXTRA}
        ),
        key=lambda pairing: pairing.reference_indices[0],
    ):
        indices = pairing.reference_indices
        stage = _stage_of(fates, indices)
        at_stage = stage_position[stage]
        stage_alignment = alignments[at_stage]
        pairing_at_stage = stage_alignment.pairings[
            stage_alignment.reference_pairing[indices[0]]
        ]
        edge = any(
            outputs[at_stage][galley_index].edge_of_page
            for index in indices
            for galley_index in stage_alignment.pairings[
                stage_alignment.reference_pairing[index]
            ].galley_indices
        )
        page = page_indices[indices[0]]
        before, after = _context(places, indices[0], indices[-1])
        block_id = (
            markdown[pairing.galley_indices[0]].block_id
            if pairing.galley_indices
            else None
        )
        differences.append(
            Difference(
                stage=stage,
                state=pairing.state,
                subkind=pairing.subkind,
                state_at_stage=pairing_at_stage.state,
                subkind_at_stage=pairing_at_stage.subkind,
                part=parts[indices[0]],
                page_index=page,
                printed_page=None if page is None else printed_pages.get(page),
                reference=tuple(places[index].token.text for index in indices),
                galley=tuple(markdown[index].text for index in pairing.galley_indices),
                context_before=before,
                context_after=after,
                block_id=block_id,
                note_id=_note_id(side, block_id),
                edge_of_page=edge,
                apart=Apart.UNPLACED if page is None else apart_pages.get(page),
                cause=Cause.ENDNOTE_REFERENCE_FAR
                if places[indices[0]].note_index in far_notes
                else None,
            )
        )
    return tuple(differences)


def _note_id(side: GalleySide, block_id: str | None) -> str | None:
    if block_id is None:
        return None
    return side.galley_blocks[block_id].note_id


def _extra_differences(
    alignments: tuple[Alignment, ...],
    outputs: tuple[tuple[GalleyToken, ...], ...],
    *,
    far_endnotes: frozenset[str],
    parts_of_pages: frozendict[int, Part],
    printed_pages: frozendict[int, str],
    side: GalleySide,
    apart_pages: frozendict[int, Apart],
) -> tuple[Difference, ...]:
    extras = tuple(
        extra_tokens(alignment, galley)
        for alignment, galley in zip(alignments, outputs, strict=True)
    )
    traced = trace_extras((extras[0], extras[1], extras[2], extras[3]))
    markdown_alignment, markdown = alignments[-1], outputs[-1]
    on_page: dict[int, list[int]] = {}
    for index, token in enumerate(markdown):
        on_page.setdefault(token.page_index, []).append(index)
    extra_positions = tuple(
        index
        for index, pairing_index in enumerate(markdown_alignment.galley_pairing)
        if markdown_alignment.pairings[pairing_index].state is State.EXTRA
    )
    return tuple(
        _extra_difference(
            extra,
            _page_context(markdown, on_page[markdown[position].page_index], position),
            parts_of_pages=parts_of_pages,
            printed_pages=printed_pages,
            side=side,
            apart_pages=apart_pages,
            far_endnotes=far_endnotes,
        )
        for extra, position in zip(traced, extra_positions, strict=True)
    )


def _page_context(
    markdown: tuple[GalleyToken, ...], page_positions: list[int], position: int
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """The galley tokens at markdown on the same page before and after the
    one at `position`, up to _CONTEXT_TOKENS each."""
    at = page_positions.index(position)
    before = page_positions[max(at - _CONTEXT_TOKENS, 0) : at]
    after = page_positions[at + 1 : at + 1 + _CONTEXT_TOKENS]
    return (
        tuple(markdown[index].text for index in before),
        tuple(markdown[index].text for index in after),
    )


def _extra_difference(
    extra: TracedExtra,
    context: tuple[tuple[str, ...], tuple[str, ...]],
    *,
    parts_of_pages: frozendict[int, Part],
    printed_pages: frozendict[int, str],
    side: GalleySide,
    apart_pages: frozendict[int, Apart],
    far_endnotes: frozenset[str],
) -> Difference:
    page = extra.token.page_index
    note_id = _note_id(side, extra.token.block_id)
    return Difference(
        stage=extra.stage,
        state=State.EXTRA,
        subkind=None,
        state_at_stage=State.EXTRA,
        subkind_at_stage=None,
        part=parts_of_pages.get(page, Part.BODY),
        page_index=page,
        printed_page=printed_pages.get(page),
        reference=(),
        galley=(extra.token.text,),
        context_before=context[0],
        context_after=context[1],
        block_id=extra.token.block_id,
        note_id=note_id,
        edge_of_page=extra.origin.edge_of_page,
        apart=apart_pages.get(page),
        cause=Cause.ENDNOTE_REFERENCE_FAR if note_id in far_endnotes else None,
    )


def _unplaced_runs(
    places: tuple[ReferencePlace, ...], page_indices: tuple[int | None, ...]
) -> tuple[UnplacedRun, ...]:
    runs: list[UnplacedRun] = []
    start: int | None = None
    for index in range(len(places) + 1):
        unplaced = index < len(places) and page_indices[index] is None
        if unplaced and start is None:
            start = index
        elif not unplaced and start is not None:
            before, _ = _context(places, start, index - 1)
            runs.append(
                UnplacedRun(
                    tokens=tuple(place.token.text for place in places[start:index]),
                    context_before=before,
                )
            )
            start = None
    return tuple(runs)
