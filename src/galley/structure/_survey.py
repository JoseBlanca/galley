"""The survey of the whole book that comes before the per-page work (spec
sections 2 and 3): which head lines are running heads, the offset between
page index and printed page number, the body word height and line pitch,
and the book's own words."""

import statistics
from collections import Counter
from dataclasses import dataclass
from difflib import SequenceMatcher

from galley.body_measures import body_measures, group_rows, median_word_height
from galley.model import Line, LinesFile, PageLayout
from galley.parallel import DEFAULT_WORKERS, map_pages
from galley.structure._foot import line_at, line_below_head, signature_candidate
from galley.structure._heads import (
    EndNumber,
    arabic_number,
    end_numbers,
    is_confirmed,
    is_roman_number,
    without,
)
from galley.structure._index import index_pages
from galley.structure._measures import (
    is_hyphen_first_part,
    is_number_before_word,
    letters,
    words_text,
)
from galley.structure._regions import head_line, region_kinds
from galley.wordlist import word_key

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
# Spec section 4: a signature line's words left of its page number hold at
# least 4 letters, at least 0.5 alike to another page's (Mariéjol's were
# 0.54 to 0.73 alike).
_SIGNATURE_ALIKE_RATIO = 0.5
_SIGNATURE_MIN_LETTERS = 4


@dataclass(frozen=True, slots=True, kw_only=True)
class BookSurvey:
    """What structure learns from the whole book before the per-page work.

    `running_heads` are the page indices whose head line is a running head;
    `head_page_offset` the commonest page index minus printed number of the
    arabic page numbers of the running heads, None when there is none;
    `first_arabic_page` the first page index whose running head has one;
    `body_word_height` and `body_line_pitch` in points; `book_words` the
    keys of the words printed whole (spec section 5); `signature_lines`
    the page indices whose lowest line is a signature line (section 4);
    `heads_below_specks` the page indices whose head line is a speck and
    the line below it a running head (section 3); `index_pages` the page
    indices of the printed indexes (section 17).
    """

    running_heads: frozenset[int]
    head_page_offset: int | None
    first_arabic_page: int | None
    body_word_height: float
    body_line_pitch: float
    book_words: frozenset[str]
    signature_lines: frozenset[int]
    heads_below_specks: frozenset[int]
    index_pages: frozenset[int] = frozenset()


@dataclass(frozen=True, slots=True)
class _PageMeasures:
    """What the survey takes from one page: its head line's text line, the
    median word height of each line, the rows of all its words
    (`body_measures.group_rows`), and the keys of its words printed
    whole."""

    head: Line | None
    below_head: Line | None
    line_heights: tuple[float, ...]
    rows: tuple[Line, ...]
    words: frozenset[str]


def _words_printed_whole(page: PageLayout) -> frozenset[str]:
    """The keys of the page's words, except the last word of a line that
    ends with a hyphen and the first word of the line after it, in the
    same region (spec section 5)."""
    keys: set[str] = set()
    for region in page.regions:
        lines = tuple(tuple(word.text for word in line.words) for line in region.lines)
        split_after = False
        for texts, next_texts in zip(lines, (*lines[1:], ()), strict=True):
            split_here = (
                bool(texts)
                and is_hyphen_first_part(texts[-1])
                and not (
                    bool(next_texts) and is_number_before_word(texts[-1], next_texts[0])
                )
            )
            start = 1 if split_after else 0
            end = len(texts) - 1 if split_here else len(texts)
            keys.update(word_key(text) for text in texts[start:end])
            split_after = split_here
    keys.discard("")
    return frozenset(keys)


def _page_measures(page: PageLayout) -> _PageMeasures:
    head = head_line(page)
    rows = group_rows(
        tuple(
            word
            for region in page.regions
            for line in region.lines
            for word in line.words
        )
    )
    return _PageMeasures(
        head=head.lines[-1] if head is not None else None,
        below_head=line_at(page, below)
        if head is not None and (below := line_below_head(page)) is not None
        else None,
        line_heights=tuple(
            median_word_height(line.words)
            for region in page.regions
            for line in region.lines
            if line.words
        ),
        rows=rows,
        words=_words_printed_whole(page),
    )


@dataclass(frozen=True, slots=True, kw_only=True)
class _Alike:
    """When the letters of a line are alike to another page's: they are at
    least `min_letters`, and their difflib ratio is at least `ratio` to
    letters whose length differs by at most `max_length_difference`."""

    min_letters: int
    ratio: float
    max_length_difference: int | None


_HEADS_ALIKE = _Alike(
    min_letters=_HEAD_MIN_LETTERS,
    ratio=_HEAD_ALIKE_RATIO,
    max_length_difference=_HEAD_LENGTH_DIFFERENCE,
)
_SIGNATURES_ALIKE = _Alike(
    min_letters=_SIGNATURE_MIN_LETTERS,
    ratio=_SIGNATURE_ALIKE_RATIO,
    max_length_difference=None,
)


def _alike_to_any(line_letters: str, others: tuple[str, ...], alike: _Alike) -> bool:
    """Whether `line_letters`, the letters of one line, are alike to any of
    `others`, the letters of lines of other pages."""
    if len(line_letters) < alike.min_letters:
        return False
    matcher = SequenceMatcher(None, autojunk=False)
    matcher.set_seq2(line_letters)
    for other in others:
        if (
            alike.max_length_difference is not None
            and abs(len(other) - len(line_letters)) > alike.max_length_difference
        ):
            continue
        matcher.set_seq1(other)
        if (
            matcher.real_quick_ratio() >= alike.ratio
            and matcher.quick_ratio() >= alike.ratio
            and matcher.ratio() >= alike.ratio
        ):
            return True
    return False


def _alike_pages(
    page_letters: tuple[tuple[int, str], ...], alike: _Alike, workers: int
) -> frozenset[int]:
    """The pages of `page_letters`, (page index, letters of a line), whose
    letters are alike to another page's, compared in `workers` threads.
    Letters found on two pages are alike without being compared."""
    counts = frozendict(Counter(text for _, text in page_letters))
    distinct = tuple(sorted(counts))

    def alike_to_another(text: str) -> bool:
        if len(text) < alike.min_letters:
            return False
        others = tuple(other for other in distinct if other != text)
        return counts[text] > 1 or _alike_to_any(text, others, alike)

    alike_letters = dict(
        zip(distinct, map_pages(alike_to_another, distinct, workers), strict=True)
    )
    return frozenset(
        page_index for page_index, text in page_letters if alike_letters[text]
    )


@dataclass(frozen=True, slots=True)
class _HeadSurvey:
    """What the survey finds of the head lines (spec section 3)."""

    running_heads: frozenset[int]
    offset: int | None
    first_arabic_page: int | None
    heads_below_specks: frozenset[int]


def _texts(line: Line) -> tuple[str, ...]:
    return tuple(word.text for word in line.words)


def _line_letters(line: Line) -> str:
    return letters(words_text(line.words))


def number_candidates(
    page_index: int, line: Line, first_arabic_page: int | None
) -> tuple[EndNumber, ...]:
    """The page-number forms at the ends of a head line, a roman one only
    before the first confirmed arabic head number (spec section 3)."""
    roman_allowed = first_arabic_page is None or page_index < first_arabic_page
    return tuple(
        candidate
        for candidate in end_numbers(_texts(line))
        if arabic_number(candidate) is not None
        or (roman_allowed and is_roman_number(candidate))
    )


def _head_survey(
    heads: tuple[tuple[int, Line, Line | None], ...], pitch: float, workers: int
) -> _HeadSurvey:
    """Running heads, the offset and the first arabic head number from the
    head lines, (page index, head line, line below it) (spec section 3)."""
    if not heads:
        return _HeadSurvey(frozenset(), None, None, frozenset())
    median_top = statistics.median(line.box.top for _, line, _ in heads)
    limit = _HEAD_PITCHES * pitch
    near = tuple(
        (page_index, line)
        for page_index, line, _ in heads
        if line.box.top - median_top <= limit
    )
    offset = _commonest_offset(
        tuple(
            (page_index, value)
            for page_index, line in near
            for candidate in end_numbers(_texts(line))
            if (value := arabic_number(candidate)) is not None
        )
    )
    confirmed = frozenset(
        page_index
        for page_index, line in near
        if any(
            is_confirmed(page_index, arabic_number(candidate), offset)
            for candidate in end_numbers(_texts(line))
        )
    )
    first_arabic_page = min(confirmed, default=None)
    numbered = tuple(
        (page_index, line, candidates)
        for page_index, line in near
        if (candidates := number_candidates(page_index, line, first_arabic_page))
    )
    alike_whole = _alike_pages(
        tuple((page_index, _line_letters(line)) for page_index, line in near),
        _HEADS_ALIKE,
        workers,
    )
    alike_without_number = _alike_pages(
        tuple(
            (page_index, letters("".join(without(candidates[0], _texts(line)))))
            for page_index, line, candidates in numbered
        ),
        _HEADS_ALIKE,
        workers,
    )
    running = alike_whole | confirmed | alike_without_number
    running_letters = tuple(
        sorted({_line_letters(line) for page, line in near if page in running})
    )
    below_specks = frozenset(
        page_index
        for page_index, line, below in heads
        if page_index not in running
        and below is not None
        and len(_line_letters(line)) < _HEAD_MIN_LETTERS
        and below.box.top - median_top <= limit
        and _alike_to_any(_line_letters(below), running_letters, _HEADS_ALIKE)
    )
    return _HeadSurvey(running, offset, first_arabic_page, below_specks)


def _commonest_offset(numbers: tuple[tuple[int, int], ...]) -> int | None:
    """The commonest page index minus printed number, the smaller on a tie."""
    counts = Counter(page_index - value for page_index, value in numbers)
    if not counts:
        return None
    return min(counts, key=lambda offset: (-counts[offset], offset))


def _body_height_and_pitch(
    measures: tuple[_PageMeasures, ...],
) -> tuple[float, float]:
    """The body word height and body line pitch, in points (spec section 2):
    as layout takes them, by `body_measures.body_measures`; for a book with
    no page of 3 rows, the median height of all its lines, 0 without words,
    and a pitch of 0."""
    measured = body_measures(tuple(page.rows for page in measures))
    if measured is not None:
        return measured.body_word_height, measured.body_line_pitch
    line_heights = tuple(height for page in measures for height in page.line_heights)
    return (statistics.median(line_heights) if line_heights else 0.0), 0.0


def survey_book(lines: LinesFile, *, workers: int = DEFAULT_WORKERS) -> BookSurvey:
    """What structure learns from the whole book before the per-page work
    (spec sections 2 and 3), the pages measured in a pool of `workers`
    threads. The result does not depend on `workers`."""
    measures = map_pages(_page_measures, lines.pages, workers)
    body_word_height, pitch = _body_height_and_pitch(measures)
    heads = tuple(
        (page.index, measured.head, measured.below_head)
        for page, measured in zip(lines.pages, measures, strict=True)
        if measured.head is not None
    )
    head_survey = _head_survey(heads, pitch, workers)
    running_heads = head_survey.running_heads
    kinds = map_pages(
        lambda page: region_kinds(page, body_word_height, running_heads),
        lines.pages,
        workers,
    )
    candidates = tuple(
        signature_candidate(page, page_kinds)
        for page, page_kinds in zip(lines.pages, kinds, strict=True)
    )
    return BookSurvey(
        running_heads=running_heads,
        head_page_offset=head_survey.offset,
        first_arabic_page=head_survey.first_arabic_page,
        body_word_height=body_word_height,
        body_line_pitch=pitch,
        book_words=frozenset().union(*(page.words for page in measures)),
        signature_lines=_alike_pages(
            tuple(
                (page.index, candidate)
                for page, candidate in zip(lines.pages, candidates, strict=True)
                if candidate is not None
            ),
            _SIGNATURES_ALIKE,
            workers,
        ),
        heads_below_specks=head_survey.heads_below_specks,
        index_pages=index_pages(lines.pages, kinds),
    )
