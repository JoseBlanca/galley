"""The figure blocks (structure spec section 18; figures spec section 5):
a plate's, placed as side text of its page, and an in-page figure's,
placed after the block that holds the body line printed above it.

Each figure block's text is its caption, its hyphens joined, its `figure`
the path of its image, and its origin the box that holds the figure and
its caption.
"""

from collections.abc import Sequence
from dataclasses import replace

from galley.model import BlockKind, Box, Origin, box_holds
from galley.structure._figures import PageFigure
from galley.structure._lines import PlacedLine
from galley.structure._paragraphs import PageParts
from galley.structure._unnumbered import Unnumbered, first_page, joined

# Side text, which a figure block is placed among and never after as
# after a paragraph (structure spec sections 6 and 18).
_SIDE_KINDS = frozenset({BlockKind.MARGIN_NOTE, BlockKind.FIGURE})


def _figure_block(
    page_index: int,
    figure: PageFigure,
    book_words: frozenset[str],
    lower_case_words: frozenset[str],
) -> Unnumbered:
    """The figure block of `figure`, on `page_index`: its caption with its
    hyphens joined, its image, and as its origin the box that holds the
    figure and its caption."""
    return replace(
        joined(figure.caption, BlockKind.FIGURE, book_words, lower_case_words),
        origin=(Origin(page_index, figure.origin_box),),
        figure=figure.image,
    )


def with_figures(
    body: Sequence[Unnumbered],
    parts: Sequence[PageParts],
    book_words: frozenset[str],
    lower_case_words: frozenset[str],
) -> tuple[Unnumbered, ...]:
    """The book's body blocks with the figure block of each plate page of
    `parts` placed as side text of its page (spec sections 6 and 18): after
    the last block that starts on an earlier page and is neither a margin
    note nor a figure, the paragraph in which the body before the plate
    ends, and after the margin notes and figures that follow it and start
    on the plate's page or earlier; first when no block starts earlier."""
    result = list(body)
    for page in parts:
        if page.figure is None:
            continue
        figure = _figure_block(page.index, page.figure, book_words, lower_case_words)
        position = 0
        for number, block in enumerate(result):
            if block.kind not in _SIDE_KINDS and first_page(block.origin) < page.index:
                position = number + 1
        while (
            position < len(result)
            and result[position].kind in _SIDE_KINDS
            and first_page(result[position].origin) <= page.index
        ):
            position += 1
        result.insert(position, figure)
    return tuple(result)


def _beside(line: PlacedLine, box: Box) -> bool:
    """Whether `line` lies wholly left or right of the figure of `box`,
    its top between the figure's top and bottom."""
    line_box = line.line.box
    return (line_box.x1 <= box.x0 or line_box.x0 >= box.x1) and (
        box.top <= line_box.top <= box.bottom
    )


def _above(
    body: Sequence[PlacedLine], box: Box, body_line_pitch: float
) -> tuple[bool, ...]:
    """For each line of a page's `body`, whether it is printed above the
    figure of `box`: its top lies above the figure's, or it is the only
    line of `body` beside the figure (`_beside`) and its top lies less
    than one body line pitch below the figure's top."""
    beside = tuple(_beside(line, box) for line in body)
    alone = sum(beside) == 1
    return tuple(
        line.line.box.top < box.top
        or (alone and is_beside and line.line.box.top < box.top + body_line_pitch)
        for line, is_beside in zip(body, beside, strict=True)
    )


def place_line(
    pages_body: Sequence[tuple[int, tuple[PlacedLine, ...]]],
    page_index: int,
    box: Box,
    body_line_pitch: float,
) -> PlacedLine | None:
    """The body line after whose block the figure of `box` on `page_index`
    goes (figures spec section 5, "structure: where the figure block
    goes"): the last line of the page's body stream, in reading order,
    printed above the figure (`_above`), or, when the page has none, the
    last body line of the pages before; None when there is none.
    `pages_body` are the book's pages, each its index and body stream, in
    page order; `body_line_pitch` is in points."""
    on_page = next(
        (
            line
            for index, body in pages_body
            if index == page_index
            for line, above in reversed(
                tuple(zip(body, _above(body, box, body_line_pitch), strict=True))
            )
            if above
        ),
        None,
    )
    if on_page is not None:
        return on_page
    return next(
        (
            body[-1]
            for index, body in reversed(pages_body)
            if index < page_index and body
        ),
        None,
    )


# The runs a figure block never cuts: a list's items and a contents run's
# entries (figures spec section 5).
_RUN_KINDS = frozenset({BlockKind.LIST_ITEM, BlockKind.CONTENTS_ENTRY})


def figure_position(
    kinds: Sequence[BlockKind],
    origins: Sequence[Sequence[Origin]],
    line: PlacedLine | None,
) -> int:
    """The position among blocks of `kinds` and `origins`, in order, at which
    a figure block goes whose place is after the block that holds `line`
    (`place_line`): after that block, after the whole list or contents run
    when it is a list item or a contents entry, and after the figure blocks
    placed there before it; first, after the figure blocks already there,
    when `line` is None. When no block but side text holds `line`, the
    block that holds it is the last that starts on its page or before."""
    holder = (
        None
        if line is None
        else next(
            (
                number
                for number, (kind, origin) in enumerate(
                    zip(kinds, origins, strict=True)
                )
                if kind not in _SIDE_KINDS
                and any(
                    entry.page_index == line.page_index
                    and box_holds(entry.box, line.line.box)
                    for entry in origin
                )
            ),
            None,
        )
    )
    if holder is None and line is not None:
        # A line no body block holds, as one of the endnote section's:
        # after the last block that starts on its page or before.
        holder = max(
            (
                number
                for number, (kind, origin) in enumerate(
                    zip(kinds, origins, strict=True)
                )
                if kind not in _SIDE_KINDS
                and min(entry.page_index for entry in origin) <= line.page_index
            ),
            default=None,
        )
    position = 0 if holder is None else holder + 1
    if holder is not None and kinds[holder] in _RUN_KINDS:
        while position < len(kinds) and kinds[position] is kinds[holder]:
            position += 1
    while position < len(kinds) and kinds[position] is BlockKind.FIGURE:
        position += 1
    return position


def with_in_page_figures(
    body: Sequence[Unnumbered],
    parts: Sequence[PageParts],
    book_words: frozenset[str],
    lower_case_words: frozenset[str],
    body_line_pitch: float,
) -> tuple[Unnumbered, ...]:
    """The book's body blocks with the figure block of each in-page figure
    of `parts`, in page order and on a page in the order of pages.json,
    placed after the block that holds the last body line printed above it,
    after the whole list or contents run that block is in, and before the
    side text placed after it (`docs/specs/figures.md` §5, "structure:
    where the figure block goes"); `body_line_pitch` is in points."""
    result = list(body)
    pages_body = tuple((page.index, page.body) for page in parts)
    for page in parts:
        for figure in page.in_page_figures:
            position = figure_position(
                tuple(block.kind for block in result),
                tuple(block.origin for block in result),
                place_line(pages_body, page.index, figure.box, body_line_pitch),
            )
            result.insert(
                position,
                _figure_block(page.index, figure, book_words, lower_case_words),
            )
    return tuple(result)
