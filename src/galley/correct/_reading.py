"""galley's reading of a page: the tokens of the blocks and notes printed on
it, in the order of docs/specs/correct.md, section 5, each changeable or
fixed."""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace

from galley.body_measures import group_rows
from galley.correct._align import align_free_tail
from galley.correct._tokens import tokens
from galley.model import Block, BlocksFile, Box, Removal, RemovalReason, WordsFile

# Step 1 of section 5: the removals the models print as text.
_PRINTED_REMOVALS = frozenset(
    {
        RemovalReason.RUNNING_HEAD,
        RemovalReason.PAGE_NUMBER,
        RemovalReason.SIGNATURE_MARK,
    }
)


@dataclass(frozen=True, slots=True)
class Place:
    """Where a changeable token's core is: `text[start:end]` of the span
    `span_index` of the block `block_id`."""

    block_id: str
    span_index: int
    start: int
    end: int


@dataclass(frozen=True, slots=True, kw_only=True)
class GalleyToken:
    """A token of galley's reading of a page. `place` is None for a fixed
    token; `block_id` is the block it belongs to, None for a note's marker
    or group and for a removal; `note_id` the note it belongs to, None in
    the body and for a removal; `starts_note` is true on a note's first
    token on the page."""

    form: str
    place: Place | None
    block_id: str | None
    note_id: str | None
    starts_note: bool = False


def _fixed(
    text: str, block_id: str | None, note_id: str | None
) -> tuple[GalleyToken, ...]:
    return tuple(
        GalleyToken(form=token.form, place=None, block_id=block_id, note_id=note_id)
        for token in tokens(text)
    )


def block_tokens(block: Block, note_id: str | None) -> tuple[GalleyToken, ...]:
    """The tokens of a block, as step 2 of section 5 orders them: its label,
    its spans, its source and page number. Only the words of the spans that
    are not note references are changeable."""
    found: list[GalleyToken] = []
    if block.label is not None:
        found.extend(_fixed(block.label, block.id, note_id))
    for span_index, span in enumerate(block.spans):
        if span.note_ref is not None:
            found.extend(_fixed(span.text, block.id, note_id))
            continue
        found.extend(
            GalleyToken(
                form=token.form,
                place=Place(block.id, span_index, token.start, token.end),
                block_id=block.id,
                note_id=note_id,
            )
            for token in tokens(span.text)
        )
    for extra in (block.source, block.page_number):
        if extra is not None:
            found.extend(_fixed(extra, block.id, note_id))
    return tuple(found)


def _middle_in(box: Box, word_box: Box) -> bool:
    middle_x = (word_box.x0 + word_box.x1) / 2
    middle_y = (word_box.top + word_box.bottom) / 2
    return box.x0 <= middle_x <= box.x1 and box.top <= middle_y <= box.bottom


def _printed_forms(words: WordsFile, page_index: int, box: Box) -> tuple[str, ...]:
    """The comparison forms of the words of words.json on the page whose
    middle is in `box`, in rows from the top, left to right in a row."""
    inside = tuple(
        word for word in words.pages[page_index].words if _middle_in(box, word.box)
    )
    return tuple(
        token.form
        for row in group_rows(inside)
        for word in row.words
        for token in tokens(word.text)
    )


def split_counts(block: Block, words: WordsFile) -> tuple[int, ...]:
    """How many of the block's tokens are printed on each page of its
    origin, in its order (section 5, "A block printed on two pages"). A
    block on one page has all its tokens there."""
    forms = tuple(token.form for token in block_tokens(block, None))
    counts: list[int] = []
    placed = 0
    for origin in block.origin[:-1]:
        rest = forms[placed:]
        pairs = align_free_tail(
            rest, _printed_forms(words, origin.page_index, origin.box)
        )
        paired = [
            pair.first
            for pair in pairs
            if pair.first is not None and pair.second is not None
        ]
        count = paired[-1] + 1 if paired else 0
        counts.append(count)
        placed += count
    counts.append(len(forms) - placed)
    return tuple(counts)


def _on_page(
    block: Block,
    note_id: str | None,
    page_index: int,
    counts: tuple[int, ...],
) -> tuple[GalleyToken, ...]:
    """The block's tokens printed on `page_index`."""
    all_tokens = block_tokens(block, note_id)
    pages = [origin.page_index for origin in block.origin]
    position = pages.index(page_index)
    start = sum(counts[:position])
    return all_tokens[start : start + counts[position]]


def _top_on(block: Block, page_index: int) -> float:
    return next(
        origin.box.top for origin in block.origin if origin.page_index == page_index
    )


def _prints_on(block: Block, page_index: int) -> bool:
    return any(origin.page_index == page_index for origin in block.origin)


def page_reading(
    blocks: BlocksFile,
    page_index: int,
    splits: Mapping[str, tuple[int, ...]],
) -> tuple[GalleyToken, ...]:
    """galley's reading of the page `page_index`, as section 5 orders it.
    `splits` gives, for each block printed on several pages, the number of
    its tokens on each (split_counts); a block missing from it has all its
    tokens on every page it is printed on, which is right for a block on
    one page."""

    def counts(block: Block) -> tuple[int, ...]:
        if (split := splits.get(block.id)) is not None:
            return split
        length = len(block_tokens(block, None))
        return tuple(length for _ in block.origin)

    body = sorted(
        (
            (position, block)
            for position, block in enumerate(blocks.blocks)
            if _prints_on(block, page_index)
        ),
        key=lambda item: (_top_on(item[1], page_index), item[0]),
    )
    notes = tuple(
        (note, tuple(block for block in note.blocks if _prints_on(block, page_index)))
        for note in blocks.notes
    )
    tops = [_top_on(block, page_index) for _, block in body] + [
        _top_on(block, page_index) for _, printed in notes for block in printed
    ]
    highest = min(tops, default=None)
    removals = tuple(
        removal
        for removal in blocks.removals
        if removal.page_index == page_index and removal.reason in _PRINTED_REMOVALS
    )
    above = tuple(
        removal
        for removal in removals
        if highest is not None and (removal.box.top + removal.box.bottom) / 2 < highest
    )
    below = tuple(removal for removal in removals if removal not in above)
    reading: list[GalleyToken] = []
    reading.extend(_removal_tokens(above))
    for _, block in body:
        reading.extend(_on_page(block, None, page_index, counts(block)))
    for note, printed in notes:
        if not printed:
            continue
        first = len(reading)
        for text in (note.group, note.marker):
            if text is not None:
                reading.extend(_fixed(text, None, note.id))
        for block in printed:
            reading.extend(_on_page(block, note.id, page_index, counts(block)))
        if len(reading) > first:
            reading[first] = replace(reading[first], starts_note=True)
    reading.extend(_removal_tokens(below))
    return tuple(reading)


def _removal_tokens(removals: Iterable[Removal]) -> tuple[GalleyToken, ...]:
    return tuple(
        token for removal in removals for token in _fixed(removal.text, None, None)
    )
