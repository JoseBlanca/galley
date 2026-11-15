"""The survey of the whole book that comes before the per-page work (spec
sections 2 and 3): which head lines are running heads, the offset between
page index and printed page number, the body word height and line pitch,
and the book's own words."""

import itertools
import statistics
from collections import Counter
from dataclasses import dataclass
from difflib import SequenceMatcher

from galley.model import Line, LinesFile, PageLayout
from galley.parallel import DEFAULT_WORKERS, map_pages
from galley.structure._measures import (
    arabic_value,
    is_hyphen_first_part,
    is_page_number_form,
    letters,
    word_height,
    word_key,
    words_text,
)
from galley.structure._regions import head_line

# Spec section 2: the pitch is measured on the regions of 5 lines or more.
_LINES_FOR_PITCH = 5
# Spec section 3: a running head lies at most 2 pitches below the median top
# of the head lines (Haskins' title page 16 is 2.85 below; Kadesh's article
# title on page 8 about 2.7).
_HEAD_PITCHES = 2.0
# Spec section 3: heads alike by at least 0.75 of their letters, which are
# at least 4; heads whose letters differ in length by more than 8 are not
# compared (spec section 9, for speed).
_HEAD_ALIKE_RATIO = 0.75
_HEAD_MIN_LETTERS = 4
_HEAD_LENGTH_DIFFERENCE = 8


@dataclass(frozen=True, slots=True, kw_only=True)
class BookSurvey:
    """What structure learns from the whole book before the per-page work.

    `running_heads` are the page indices whose head line is a running head;
    `head_page_offset` the commonest page index minus printed number of the
    arabic page numbers of the running heads, None when there is none;
    `first_arabic_page` the first page index whose running head has one;
    `body_word_height` and `body_line_pitch` in points; `book_words` the
    keys of the words printed whole (spec section 5); `signature_lines`
    the page indices whose lowest line is a signature line (section 4).
    """

    running_heads: frozenset[int]
    head_page_offset: int | None
    first_arabic_page: int | None
    body_word_height: float
    body_line_pitch: float
    book_words: frozenset[str]
    signature_lines: frozenset[int]


@dataclass(frozen=True, slots=True)
class _PageMeasures:
    """What the survey takes from one page: its head line's text line, the
    median word height of each line, the pitches of its regions (those of
    5 lines or more, and all), and the keys of its words printed whole."""

    head: Line | None
    line_heights: tuple[float, ...]
    long_region_pitches: tuple[float, ...]
    pitches: tuple[float, ...]
    words: frozenset[str]


def _pitches(lines: tuple[Line, ...]) -> tuple[float, ...]:
    return tuple(
        after.box.top - before.box.top for before, after in itertools.pairwise(lines)
    )


def _words_printed_whole(page: PageLayout) -> frozenset[str]:
    """The keys of the page's words, except the last word of a line that
    ends with a hyphen and the first word of the line after it, in the
    same region (spec section 5)."""
    keys: set[str] = set()
    for region in page.regions:
        split_after = False
        for line in region.lines:
            texts = tuple(word.text for word in line.words)
            split_here = bool(texts) and is_hyphen_first_part(texts[-1])
            start = 1 if split_after else 0
            end = len(texts) - 1 if split_here else len(texts)
            keys.update(word_key(text) for text in texts[start:end])
            split_after = split_here
    keys.discard("")
    return frozenset(keys)


def _page_measures(page: PageLayout) -> _PageMeasures:
    head = head_line(page)
    return _PageMeasures(
        head=head.lines[-1] if head is not None else None,
        line_heights=tuple(
            statistics.median(word_height(word) for word in line.words)
            for region in page.regions
            for line in region.lines
            if line.words
        ),
        long_region_pitches=tuple(
            pitch
            for region in page.regions
            if len(region.lines) >= _LINES_FOR_PITCH
            for pitch in _pitches(region.lines)
        ),
        pitches=tuple(
            pitch for region in page.regions for pitch in _pitches(region.lines)
        ),
        words=_words_printed_whole(page),
    )


def _end_words(line: Line) -> tuple[str, ...]:
    """The first and last word of a line, once when it has one word."""
    texts = tuple(word.text for word in line.words)
    return texts[:1] if len(texts) == 1 else (texts[0], texts[-1])


def _alike_to_another(
    head_letters: str, counts: Counter[str], distinct: tuple[str, ...]
) -> bool:
    """Whether a head's letters are at least 4 and at least 0.75 alike to
    those of another page's head line (spec section 3)."""
    if len(head_letters) < _HEAD_MIN_LETTERS:
        return False
    if counts[head_letters] > 1:
        return True
    matcher = SequenceMatcher(None, autojunk=False)
    matcher.set_seq2(head_letters)
    for other in distinct:
        if (
            other == head_letters
            or abs(len(other) - len(head_letters)) > _HEAD_LENGTH_DIFFERENCE
        ):
            continue
        matcher.set_seq1(other)
        if (
            matcher.real_quick_ratio() >= _HEAD_ALIKE_RATIO
            and matcher.quick_ratio() >= _HEAD_ALIKE_RATIO
            and matcher.ratio() >= _HEAD_ALIKE_RATIO
        ):
            return True
    return False


def _running_heads(
    heads: tuple[tuple[int, Line], ...], pitch: float, workers: int
) -> frozenset[int]:
    """The pages whose head line is a running head (spec section 3)."""
    if not heads:
        return frozenset()
    median_top = statistics.median(line.box.top for _, line in heads)
    near = tuple(
        (page_index, line)
        for page_index, line in heads
        if line.box.top - median_top <= _HEAD_PITCHES * pitch
    )
    head_letters = tuple(letters(words_text(line.words)) for _, line in near)
    counts = Counter(head_letters)
    distinct = tuple(sorted(counts))
    alike = dict(
        zip(
            distinct,
            map_pages(
                lambda text: _alike_to_another(text, counts, distinct),
                distinct,
                workers,
            ),
            strict=True,
        )
    )
    return frozenset(
        page_index
        for (page_index, line), text in zip(near, head_letters, strict=True)
        if alike[text] or any(is_page_number_form(end) for end in _end_words(line))
    )


def _arabic_head_numbers(
    heads: tuple[tuple[int, Line], ...], running_heads: frozenset[int]
) -> tuple[tuple[int, int], ...]:
    """(page index, printed number) of each arabic page-number form at the
    first or last word of a running head."""
    return tuple(
        (page_index, value)
        for page_index, line in heads
        if page_index in running_heads
        for end in _end_words(line)
        if (value := arabic_value(end)) is not None
    )


def _commonest_offset(numbers: tuple[tuple[int, int], ...]) -> int | None:
    """The commonest page index minus printed number, the smaller on a tie."""
    counts = Counter(page_index - value for page_index, value in numbers)
    if not counts:
        return None
    return min(counts, key=lambda offset: (-counts[offset], offset))


def survey_book(lines: LinesFile, *, workers: int = DEFAULT_WORKERS) -> BookSurvey:
    """What structure learns from the whole book before the per-page work
    (spec sections 2 and 3), the pages measured in a pool of `workers`
    threads. The result does not depend on `workers`."""
    measures = map_pages(_page_measures, lines.pages, workers)
    line_heights = tuple(height for page in measures for height in page.line_heights)
    long_pitches = tuple(
        pitch for page in measures for pitch in page.long_region_pitches
    )
    pitches = long_pitches or tuple(
        pitch for page in measures for pitch in page.pitches
    )
    pitch = statistics.median(pitches) if pitches else 0.0
    heads = tuple(
        (page.index, measured.head)
        for page, measured in zip(lines.pages, measures, strict=True)
        if measured.head is not None
    )
    running_heads = _running_heads(heads, pitch, workers)
    arabic_numbers = _arabic_head_numbers(heads, running_heads)
    return BookSurvey(
        running_heads=running_heads,
        head_page_offset=_commonest_offset(arabic_numbers),
        first_arabic_page=min(
            (page_index for page_index, _ in arabic_numbers), default=None
        ),
        body_word_height=statistics.median(line_heights) if line_heights else 0.0,
        body_line_pitch=pitch,
        book_words=frozenset().union(*(page.words for page in measures)),
        signature_lines=frozenset(),
    )
