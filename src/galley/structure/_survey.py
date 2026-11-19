"""The survey of the whole book that comes before the per-page work (spec
sections 2 and 3): which head lines are running heads, the offset between
page index and printed page number, the body word height and line pitch,
and the book's own words."""

import statistics
from collections import Counter
from dataclasses import dataclass, replace
from difflib import SequenceMatcher

from galley.body_measures import body_measures, group_rows, median_word_height
from galley.model import Line, LinesFile, PageLayout
from galley.parallel import DEFAULT_WORKERS, map_pages
from galley.structure._figures import text_page
from galley.structure._foot import line_at, line_below_head, signature_candidate
from galley.structure._fragments import LetterFragments, letter_fragments
from galley.structure._heads import (
    EndNumber,
    arabic_number,
    end_numbers,
    is_confirmed,
    is_number_like,
    is_roman_number,
    starts_with_chapter_label_word,
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


def in_head_band(top: float, median_head_top: float, pitch: float) -> bool:
    """Whether a line whose top is `top`, in points, lies in the band where
    running heads are looked for (spec section 3): at most 2 pitches of
    `pitch` below `median_head_top`, the median top of the book's head
    lines, or anywhere above it."""
    return top - median_head_top <= _HEAD_PITCHES * pitch


# Spec section 3: heads alike by at least 0.70 of their letters, which are
# at least 4; heads whose letters differ in length by more than 14 are not
# compared (spec sections 3, "Heads of different lengths", and 9). 0.70,
# not 0.75 (17 November 2026): it takes 13 more running heads on the six
# books, Gierke's damaged 72 and 78 among them, and no line of text. 14,
# not 8 (18 November 2026, measured on the eight books at main a0a1675):
# it takes Gierke's damaged heads of pages 16 and 84 and Mariéjol's 158,
# and no other line.
_HEAD_ALIKE_RATIO = 0.70
_HEAD_MIN_LETTERS = 4
_HEAD_LENGTH_DIFFERENCE = 14
# Spec section 3, the head of a short section: its likeness is to the
# topmost line of one of the 2 pages before it, not 1, so that a blank page
# or a plate between does not hide the heading (a guess: on the six books
# the heading is always on the page just before).
_SHORT_SECTION_PAGES_BACK = 2
# Spec section 4: a signature line's words left of its page number hold at
# least 4 letters, at least 0.5 alike to another page's (Mariéjol's were
# 0.54 to 0.73 alike).
_SIGNATURE_ALIKE_RATIO = 0.5
_SIGNATURE_MIN_LETTERS = 4
# Spec section 5: a word printed after the first word of a line more than
# this many times in the book is printed whole, no fragment of a word whose
# hyphen was lost. Measured on whole Stubbs, Domesday and Gierke on 17
# November 2026: the right joins in margin notes have fragments printed so
# 0 to 5 times ("al") and 9 ("wise."); the first wrong one 11 ("defined").
_INNER_WORD_MOST_TIMES = 8


@dataclass(frozen=True, slots=True, kw_only=True)
class BookSurvey:
    """What structure learns from the whole book before the per-page work.

    `running_heads` are the page indices whose head line is a running head,
    the head of a short section among them;
    `head_page_offset` the commonest page index minus printed number of the
    arabic page numbers of the running heads, None when there is none;
    `first_arabic_page` the first page index whose running head has one;
    `body_word_height` and `body_line_pitch` in points; `book_words` the
    keys of the words printed whole (spec section 5); `common_inner_words`
    the keys printed after the first word of a line more than
    `_INNER_WORD_MOST_TIMES` times, no fragment of a word (section 5); `signature_lines`
    the page indices whose lowest line is a signature line (section 4);
    `heads_below_specks` the page indices whose head line is a speck and
    the line below it a running head (section 3); `index_pages` the page
    indices of the printed indexes (section 17); `head_numbers` the arabic
    page number of each page whose running head has one, by page index
    (section 4, the local offset); `median_head_top` the median top of the
    book's head lines, in points, None when it has none (section 3);
    `running_head_letters` the letters of each line removed as a running
    head, each once, sorted (section 14); `letter_fragments` whether the
    book has letter fragments (section 35).
    """

    running_heads: frozenset[int]
    head_page_offset: int | None
    first_arabic_page: int | None
    body_word_height: float
    body_line_pitch: float
    book_words: frozenset[str]
    common_inner_words: frozenset[str]
    signature_lines: frozenset[int]
    heads_below_specks: frozenset[int]
    index_pages: frozenset[int]
    head_numbers: frozendict[int, int]
    median_head_top: float | None
    running_head_letters: tuple[str, ...]
    letter_fragments: LetterFragments


@dataclass(frozen=True, slots=True)
class _PageMeasures:
    """What the survey takes from one page: its head line's text line, the
    median word height of each line, the rows of all its words
    (`body_measures.group_rows`), and the keys of its words printed
    whole and of its words after the first of a line."""

    head: Line | None
    below_head: Line | None
    line_heights: tuple[float, ...]
    rows: tuple[Line, ...]
    words: frozenset[str]
    inner_words: tuple[str, ...]


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
        head=head.line if head is not None else None,
        below_head=line_at(page, below)
        if head is not None
        and (below := line_below_head(page, head.region_numbers)) is not None
        else None,
        line_heights=tuple(
            median_word_height(line.words)
            for region in page.regions
            for line in region.lines
            if line.words
        ),
        rows=rows,
        words=_words_printed_whole(page),
        inner_words=tuple(
            key
            for region in page.regions
            for line in region.lines
            for word in line.words[1:]
            if (key := word_key(word.text))
        ),
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


# Spec sections 3, 14 and 18: the tests of a line alike to a head other
# than the survey's own head lines (a line like a running head, the head of
# a short section, a plate's topmost line) compare letters only within 8
# of each other, the limit of section 3 before it was raised to 14 on 18
# November 2026 for the survey's head lines alone; they were not measured
# at 14.
_NOT_SURVEY_HEAD_LENGTH_DIFFERENCE = 8
# Spec section 14: a line in the head band at least 0.6 alike to a running
# head is never a heading (Domesday's page 159, Kadesh's 38).
_LIKE_A_HEAD_RATIO = 0.6
_LIKE_A_HEAD = _Alike(
    min_letters=_HEAD_MIN_LETTERS,
    ratio=_LIKE_A_HEAD_RATIO,
    max_length_difference=_NOT_SURVEY_HEAD_LENGTH_DIFFERENCE,
)


def like_a_running_head(line_letters: str, running_letters: tuple[str, ...]) -> bool:
    """Whether `line_letters`, the letters of a line, are at least 0.6 alike
    to the letters of one of the book's running heads, `running_letters`,
    with at least 4 letters (spec section 14)."""
    return _alike_to_any(line_letters, running_letters, _LIKE_A_HEAD)


# Spec section 3: the head of a short section and a plate's topmost line
# (section 18, rule 1), within `_NOT_SURVEY_HEAD_LENGTH_DIFFERENCE`.
_OTHER_HEADS_ALIKE = _Alike(
    min_letters=_HEAD_MIN_LETTERS,
    ratio=_HEAD_ALIKE_RATIO,
    max_length_difference=_NOT_SURVEY_HEAD_LENGTH_DIFFERENCE,
)


def alike_to_a_head(line_letters: str, others: tuple[str, ...]) -> bool:
    """Whether `line_letters`, the letters of a line, are alike to any of
    `others` by section 3's rule for running heads: at least 4 letters,
    0.70 alike, compared only with letters at most 8 more or fewer, as the
    head of a short section and a plate's topmost line are."""
    return _alike_to_any(line_letters, others, _OTHER_HEADS_ALIKE)


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
    """What the survey finds of the head lines (spec section 3), and the
    arabic page number of each running head that has one (section 4)."""

    running_heads: frozenset[int]
    offset: int | None
    first_arabic_page: int | None
    heads_below_specks: frozenset[int]
    head_numbers: frozendict[int, int]
    median_top: float | None
    running_letters: tuple[str, ...]


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


def _topmost_line(page: PageLayout) -> Line | None:
    """The line of the page whose top is highest, the first in the order of
    the regions on a tie; None on a page with no line."""
    lines = tuple(line for region in page.regions for line in region.lines)
    return min(lines, key=lambda line: line.box.top, default=None)


def _is_short_section_head(
    page_index: int, line: Line, top_letters: frozendict[int, str]
) -> bool:
    """Whether a head line near the median head top, left in the text by
    the other rules, is the head of a short section (spec section 3): its
    first or last word number-like, and the rest of the line alike to the
    topmost line of one of the 2 pages before it, `top_letters` holding the
    letters of each page's topmost line."""
    texts = _texts(line)
    rests = tuple(
        rest
        for number_like, rest in (
            (texts[:1], texts[1:]),
            (texts[-1:], texts[:-1]),
        )
        if number_like and is_number_like(number_like[0])
    )
    before = tuple(
        top_letters[back]
        for back in range(page_index - _SHORT_SECTION_PAGES_BACK, page_index)
        if back in top_letters
    )
    return any(alike_to_a_head(letters("".join(rest)), before) for rest in rests)


def _head_survey(
    heads: tuple[tuple[int, Line, Line | None], ...],
    pitch: float,
    top_letters: frozendict[int, str],
    workers: int,
) -> _HeadSurvey:
    """Running heads, the offset and the first arabic head number from the
    head lines, (page index, head line, line below it), and `top_letters`,
    the letters of each page's topmost line (spec section 3)."""
    if not heads:
        return _HeadSurvey(frozenset(), None, None, frozenset(), frozendict(), None, ())
    median_top = statistics.median(line.box.top for _, line, _ in heads)
    near = tuple(
        (page_index, line)
        for page_index, line, _ in heads
        if in_head_band(line.box.top, median_top, pitch)
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
    # A chapter label is never a running head, whatever the rules find.
    labels = frozenset(
        page_index
        for page_index, line, _ in heads
        if starts_with_chapter_label_word(_texts(line))
    )
    running = (alike_whole | confirmed | alike_without_number) - labels
    alike_head_letters = tuple(
        sorted({_line_letters(line) for page, line in near if page in running})
    )
    below_specks = frozenset(
        page_index
        for page_index, line, below in heads
        if page_index not in running
        and below is not None
        and len(_line_letters(line)) < _HEAD_MIN_LETTERS
        and in_head_band(below.box.top, median_top, pitch)
        and not starts_with_chapter_label_word(_texts(below))
        and _alike_to_any(_line_letters(below), alike_head_letters, _HEADS_ALIKE)
    )
    short_sections = frozenset(
        page_index
        for page_index, line in near
        # The speck above a head of below_specks never passes the rule: its
        # line has fewer than 4 letters, so the rest of it has fewer still.
        if page_index not in running
        and page_index not in labels
        and _is_short_section_head(page_index, line, top_letters)
    )
    # The line removed as each page's running head: its head line, or the
    # line below a speck.
    removed_heads = tuple(
        (page_index, line)
        for page_index, line, _ in heads
        if page_index in running | short_sections
    ) + tuple(
        (page_index, below)
        for page_index, _, below in heads
        if page_index in below_specks and below is not None
    )
    head_numbers = frozendict(
        {
            page_index: value
            for page_index, line in removed_heads
            if (number := head_page_number(page_index, line, first_arabic_page, offset))
            is not None
            and (value := arabic_number(number)) is not None
        }
    )
    return _HeadSurvey(
        running | short_sections,
        offset,
        first_arabic_page,
        below_specks,
        head_numbers,
        median_top,
        tuple(sorted({_line_letters(line) for _, line in removed_heads})),
    )


def head_page_number(
    page_index: int, line: Line, first_arabic_page: int | None, offset: int | None
) -> EndNumber | None:
    """A running head's page number, or None (spec section 3): a
    page-number form at the start or end of its `line`, a run of digit
    words joined, a roman one only before `first_arabic_page`; of two, the
    one `offset` puts within 2 of the page index, else the first."""
    candidates = number_candidates(page_index, line, first_arabic_page)
    if not candidates:
        return None
    return next(
        (
            candidate
            for candidate in candidates
            if is_confirmed(page_index, arabic_number(candidate), offset)
        ),
        candidates[0],
    )


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
    threads. The result does not depend on `workers`. The regions of the
    in-page figures take no part in it (`docs/specs/figures.md` §5)."""
    lines = replace(lines, pages=tuple(text_page(page) for page in lines.pages))
    measures = map_pages(_page_measures, lines.pages, workers)
    body_word_height, pitch = _body_height_and_pitch(measures)
    heads = tuple(
        (page.index, measured.head, measured.below_head)
        for page, measured in zip(lines.pages, measures, strict=True)
        if measured.head is not None
    )
    top_letters = frozendict(
        {
            page.index: _line_letters(top)
            for page in lines.pages
            if (top := _topmost_line(page)) is not None
        }
    )
    head_survey = _head_survey(heads, pitch, top_letters, workers)
    running_heads = head_survey.running_heads
    kinds = map_pages(
        lambda page: region_kinds(page, body_word_height, running_heads),
        lines.pages,
        workers,
    )
    indexes = index_pages(lines.pages, kinds)
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
        common_inner_words=frozenset(
            key
            for key, count in Counter(
                key for page in measures for key in page.inner_words
            ).items()
            if count > _INNER_WORD_MOST_TIMES
        ),
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
        index_pages=indexes,
        head_numbers=head_survey.head_numbers,
        median_head_top=head_survey.median_top,
        running_head_letters=head_survey.running_letters,
        letter_fragments=letter_fragments(lines.pages, indexes),
    )
