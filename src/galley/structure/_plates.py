"""Plates (spec section 18): a plate page's running head, its caption
lines and its stray words, and the figure block placed as side text of
its page.

A plate page is a page with a figure (`docs/specs/plates.md`). Its lines
never reach the body stream: section 3 removes its running head as on any
page; its topmost line is a running head too when it is alike to the
topmost line of another plate page or to a running head of the book; of
the other lines, those with known words are its caption and the rest are
removed as `plate_text`.
"""

from collections.abc import Sequence
from dataclasses import dataclass, replace

from galley.body_measures import rows_of
from galley.errors import InputFileError
from galley.model import (
    BlockKind,
    LinesFile,
    Origin,
    PageLayout,
    Removal,
    RemovalReason,
)
from galley.structure._foot import LinePlace, line_at
from galley.structure._lines import Piece, PlacedLine
from galley.structure._measures import (
    Edges,
    is_roman_form,
    letters,
    words_removal,
    words_text,
)
from galley.structure._paragraphs import PageFigure, PageParts
from galley.structure._removals import head_removals, running_head_place
from galley.structure._survey import BookSurvey, alike_to_a_head
from galley.structure._unnumbered import Unnumbered, first_page, joined
from galley.wordlist import is_known_word

# Spec section 18, rule 2: a caption line has at least 2 known words, or
# at least half of its words known (the second research, 24 lines kept and
# 26 removed on the 14 plate pages with a text layer of the six books).
_CAPTION_MIN_KNOWN_WORDS = 2
_CAPTION_MIN_KNOWN_SHARE = 0.5


@dataclass(frozen=True, slots=True)
class PlateSurvey:
    """What rule 1 compares a plate's topmost line with: the words of the
    topmost line of each plate page, by page index, and the letters of the
    book's running heads (spec section 3)."""

    topmost_words: frozendict[int, tuple[str, ...]]
    running_head_letters: tuple[str, ...]


def _topmost(page: PageLayout) -> LinePlace | None:
    """The page's line whose top is highest, in any region, the first in
    layout's order on a tie; None on a page without lines."""
    places = tuple(
        (region_number, line_number)
        for region_number, region in enumerate(page.regions)
        for line_number in range(len(region.lines))
    )
    return min(places, key=lambda place: line_at(page, place).box.top, default=None)


def _running_head_letters(page: PageLayout, survey: BookSurvey) -> str | None:
    """The letters of the line section 3 makes the page's running head,
    None when it has none."""
    place = running_head_place(page, survey)
    return None if place is None else letters(words_text(line_at(page, place).words))


def plate_survey(lines: LinesFile, survey: BookSurvey) -> PlateSurvey:
    """The topmost line of each plate page and the book's running heads, as
    letters (spec section 18, rule 1)."""
    topmost = {
        page.index: tuple(word.text for word in line_at(page, place).words)
        for page in lines.pages
        if page.figures and (place := _topmost(page)) is not None
    }
    heads = {
        head
        for page in lines.pages
        if (head := _running_head_letters(page, survey)) is not None
    }
    return PlateSurvey(frozendict(topmost), tuple(sorted(heads)))


def _is_numeral(text: str) -> bool:
    """Whether `text` is a numeral, arabic or roman in either case, with a
    "." or "," after it ("II", "iv.", "16")."""
    bare = text.rstrip(".,")
    return bool(bare) and (bare.isdigit() or is_roman_form(bare.lower()))


def _differ_only_in_numerals(words: Sequence[str], other: Sequence[str]) -> bool:
    """Whether two lines' words differ, but only in numerals, word by word
    ("PLATE II" and "PLATE III"; spec section 18, rule 1)."""
    return (
        len(words) == len(other)
        and tuple(words) != tuple(other)
        and all(
            word == other_word or (_is_numeral(word) and _is_numeral(other_word))
            for word, other_word in zip(words, other, strict=True)
        )
    )


def _is_caption_row(texts: Sequence[str], lower_case_words: frozenset[str]) -> bool:
    """Whether a row of a plate's lines whose words are `texts` is made of
    caption lines (spec section 18, rule 2)."""
    known = sum(is_known_word(text, lower_case_words) for text in texts)
    return known >= _CAPTION_MIN_KNOWN_WORDS or known >= _CAPTION_MIN_KNOWN_SHARE * len(
        texts
    )


def plate_parts(
    page: PageLayout,
    survey: BookSurvey,
    plates: PlateSurvey,
    lower_case_words: frozenset[str],
) -> PageParts:
    """The per-page work on a plate page, one with a figure (spec section
    18): section 3's running head removed; the topmost line removed as a
    running head when its letters are alike to the topmost line of another
    plate page or to a running head of the book; the other lines taken
    from the top down in rows, each from the left, the lines of a row
    caption lines when the row's words are known enough, else each
    removed as `plate_text`. The
    page has no body stream and no side text but its figure.
    `lower_case_words` is the word list in lower case. Raises
    InputFileError for a page with more than one figure."""
    if len(page.figures) != 1:
        message = (
            f"lines.json: page {page.index} has {len(page.figures)} figures; a "
            "plate page has one (plates spec section 3)"
        )
        raise InputFileError(message)
    (figure,) = page.figures
    head = head_removals(page, survey)
    topmost = _topmost(page)
    topmost_words = (
        tuple(word.text for word in line_at(page, topmost).words)
        if topmost is not None
        else ()
    )
    other_plate_letters = tuple(
        letters(" ".join(words))
        for index, words in plates.topmost_words.items()
        if index != page.index and not _differ_only_in_numerals(words, topmost_words)
    )
    rule_1_head = (
        topmost is not None
        and topmost not in head.lines
        and alike_to_a_head(
            letters(" ".join(topmost_words)),
            (*other_plate_letters, *plates.running_head_letters),
        )
    )
    removed: list[Removal] = list(head.removals)
    if rule_1_head:
        assert topmost is not None
        removed.append(
            words_removal(
                page.index, line_at(page, topmost).words, RemovalReason.RUNNING_HEAD
            )
        )
    plate_lines = tuple(
        ((region_number, line_number), PlacedLine(page.index, line, edges, edges))
        for region_number, region in enumerate(page.regions)
        for edges in (Edges(region.box.x0, region.box.x1),)
        for line_number, line in enumerate(region.lines)
        if (region_number, line_number) not in head.lines
        and not (rule_1_head and (region_number, line_number) == topmost)
    )
    caption: list[PlacedLine] = []
    for row in rows_of(plate_lines, lambda placed: placed[1].line.box):
        if _is_caption_row(
            tuple(word.text for _, line in row for word in line.line.words),
            lower_case_words,
        ):
            caption.extend(line for _, line in row)
        else:
            removed.extend(
                words_removal(
                    page.index, line_at(page, place).words, RemovalReason.PLATE_TEXT
                )
                for place, _ in row
            )
    return PageParts(
        index=page.index,
        removals=tuple(removed),
        page_numbers=head.page_numbers,
        body=(),
        margin_notes=(),
        band_regions=(),
        band_blocks=(),
        figure=PageFigure(
            figure.image,
            figure.box,
            Piece(tuple(caption)),
        ),
    )


def _figure_block(
    page_index: int,
    figure: PageFigure,
    book_words: frozenset[str],
    lower_case_words: frozenset[str],
) -> Unnumbered:
    """The figure block of a plate page: its caption with its hyphens
    joined, its image, and its figure's box as its origin."""
    return replace(
        joined(figure.caption, BlockKind.FIGURE, book_words, lower_case_words),
        origin=(Origin(page_index, figure.box),),
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
            if (
                block.kind not in {BlockKind.MARGIN_NOTE, BlockKind.FIGURE}
                and first_page(block.origin) < page.index
            ):
                position = number + 1
        while (
            position < len(result)
            and result[position].kind in {BlockKind.MARGIN_NOTE, BlockKind.FIGURE}
            and first_page(result[position].origin) <= page.index
        ):
            position += 1
        result.insert(position, figure)
    return tuple(result)
