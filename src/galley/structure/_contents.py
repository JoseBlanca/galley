"""The printed table of contents (spec section 30, rules 1 to 8): the
title of a contents run, and the run's body stream cut into entries, each
with its label, title, page number, leader dots and depth.

Positions are PDF points, origin at the top left of the page."""

import re
from collections.abc import Sequence
from dataclasses import dataclass, replace
from difflib import SequenceMatcher
from fractions import Fraction

from galley.contents_labels import inferred_labels
from galley.model import (
    Block,
    ChangeReason,
    Removal,
    RemovalReason,
    Span,
    Word,
    WordChange,
    block_text,
)
from galley.structure._headings import OCR_ROMAN_LABEL
from galley.structure._heads import starts_with_chapter_label_word
from galley.structure._lines import (
    PlacedLine,
    is_centred,
    line_texts,
    starts_paragraph,
    with_words,
)
from galley.structure._measures import (
    box_of,
    has_letter_or_digit,
    is_page_number_form,
    line_has_letter_or_digit,
    words_removal,
)
from galley.structure._summaries import dash_count

# Spec section 30, rule 4: an entry runs on to its next line only when that
# line lies at least 5 pt right of the left side of the entry's first line
# (the indent of section 6, rule 1, and of the index).
_RUN_ON_MIN_PT = 5.0
# Spec section 30, rule 3: an analytical summary has at least 2 lines and
# 2 inline page references, and at least one for every five of its lines.
# Measured on 18 November 2026 on Gierke's pages 52 to 60, whose
# references often end a line or read "(n)" for "(11)": one for every two
# lines cut 2 of their 34 summaries into an entry per line (72 entries
# instead of 52); four cut some too; five keeps all, and changes no other
# book (structure spec section 30, "The thresholds").
_SUMMARY_MIN_LINES = 2
_SUMMARY_MIN_REFERENCES = 2
_SUMMARY_LINES_PER_REFERENCE = 5
# Spec section 30, rule 8: a topics entry of at least 2 lines holds at
# least 2 dashes (the test of a chapter summary, section 15, rule 4).
_TOPICS_MIN_LINES = 2
_TOPICS_MIN_DASHES = 2
# Spec section 30, rule 8: a chapter's depth, and that of a centred entry
# under a chapter's.
_CHAPTER_DEPTH = 1
_SECTION_DEPTH = 2

# Spec section 30, "Terms": an inline page reference, 1 to 3 digits with
# any of "(", ")", "." and "," around them.
_INLINE_REFERENCE = re.compile(r"[(),.]*[0-9]{1,3}[(),.]*")
# A range of two page-number forms joined by a dash, in one word ("26—36.")
# or in three ("107" "—" "128.").
_RANGE_DASHES = frozenset("-–—")
_RANGE_WORD = re.compile(
    r"(?P<first>[0-9]{1,3}|[ivxlcdm]+)[-–—](?P<second>[0-9]{1,3}[.,]?|[ivxlcdm]+[.,]?)"
)
_PAGES_WORDS = frozenset({"pp.", "p."})
# Leader dots are words made only of these.
_LEADER_CHARACTERS = frozenset(".•·…")
# Spec section 30, rule 7: a number of 1 or 2 digits with ".", and the
# English number words.
_NUMBER_LABEL = re.compile(r"[0-9]{1,2}\.")
_NUMBER_WORDS = frozenset(
    {
        "one",
        "two",
        "three",
        "four",
        "five",
        "six",
        "seven",
        "eight",
        "nine",
        "ten",
        "eleven",
        "twelve",
        "thirteen",
        "fourteen",
        "fifteen",
        "sixteen",
        "seventeen",
        "eighteen",
        "nineteen",
        "twenty",
    }
)
_SECTION_SIGN = "§"


# Spec section 30, "Terms": a lone label is a chapter label word and at
# most one word more ("CHAPTER II.").
_LONE_LABEL_MAX_WORDS = 2


def _is_lone_label(line: PlacedLine) -> bool:
    """Spec section 30, "Terms": the line's first word is a chapter label
    word and it has at most one more word ("CHAPTER II.", "ESSAY I."), or
    it is a roman numeral alone as the OCR reads one (section 14)."""
    texts = line_texts(line)
    if starts_with_chapter_label_word(texts):
        return len(texts) <= _LONE_LABEL_MAX_WORDS
    return len(texts) == 1 and OCR_ROMAN_LABEL.fullmatch(texts[0]) is not None


def _marks(texts: Sequence[str]) -> int:
    """How many of the first words of `texts` hold no letter or digit."""
    marks = 0
    while marks < len(texts) and not has_letter_or_digit(texts[marks]):
        marks += 1
    return marks


# Spec section 30, "Terms": a range of page numbers in three words.
_RANGE_WORDS = 3
# Spec section 30, "Terms": a page number is set apart by a space of 11 to
# 20 pt before it (Haynes 11.5 to 12.5 pt, Turney 13.4 to 14.9; the other
# spaces of Turney's entries reach 10.2), or ends within 4 pt of the
# right side of the longest contents line of its page (Haskins, Stubbs and
# Gierke within 1.2 pt, Domesday 3.7). Measured on 18 November 2026.
_APART_MIN_PT = 11.0
_APART_MAX_PT = 20.0
_RIGHT_EDGE_PT = 4.0


def _number_form_length(texts: Sequence[str]) -> tuple[int, bool]:
    """How many of the last words of `texts` have a page number's form
    (spec section 30, "Terms"): a page-number form, a range of two in one
    word or in three, with "pp." or "p." before it; 0 when the last word
    is none; and whether it is a range or has "pp." or "p." before it."""
    if not texts:
        return 0, False
    if (
        len(texts) >= _RANGE_WORDS
        and texts[-2] in _RANGE_DASHES
        and is_page_number_form(texts[-3])
        and is_page_number_form(texts[-1])
    ):
        length, ranged = _RANGE_WORDS, True
    elif _RANGE_WORD.fullmatch(texts[-1]):
        length, ranged = 1, True
    elif is_page_number_form(texts[-1]):
        length, ranged = 1, False
    else:
        return 0, False
    if len(texts) > length and texts[-length - 1] in _PAGES_WORDS:
        return length + 1, True
    return length, ranged


def _page_number_length(words: Sequence[Word], right_edge: float) -> int:
    """How many of the last words of `words`, an entry's or a line's, are
    its page number (spec section 30, "Terms"): words of a page number's
    form that are a range or have "pp." or "p." before them, or that are
    set apart, by leader dots before them, by a space of 11 to 20 pt, or
    by ending within 4 pt of `right_edge`, the right side of the longest
    contents line of their page, in points; 0 otherwise."""
    texts = tuple(word.text for word in words)
    length, ranged = _number_form_length(texts)
    if not length:
        return 0
    first, last = words[-length], words[-1]
    before = words[-length - 1] if len(words) > length else None
    apart = (
        ranged
        or right_edge - last.box.x1 <= _RIGHT_EDGE_PT
        or (
            before is not None
            and (
                _is_leader_dots(before.text)
                or _APART_MIN_PT <= first.box.x0 - before.box.x1 <= _APART_MAX_PT
            )
        )
    )
    return length if apart else 0


def _right_edges(lines: Sequence[PlacedLine]) -> frozendict[int, float]:
    """The right side of the longest of `lines` on each page, by page
    index, in points."""
    edges: dict[int, float] = {}
    for line in lines:
        edges[line.page_index] = max(
            edges.get(line.page_index, line.line.box.x1), line.line.box.x1
        )
    return frozendict(edges)


def _is_leader_dots(text: str) -> bool:
    return bool(text) and all(character in _LEADER_CHARACTERS for character in text)


def _is_inline_reference(text: str) -> bool:
    return _INLINE_REFERENCE.fullmatch(text) is not None


@dataclass(frozen=True, slots=True)
class ContentsTitle:
    """The start of a contents run (spec section 30, rule 1): the positions
    of the lines before its first line with a letter or a digit, removed as
    stray marks, and the position of its title, None when the first such
    line ends with a page number or is a lone label, or there is none."""

    stray_marks: tuple[int, ...]
    title: int | None


def contents_title(lines: Sequence[PlacedLine]) -> ContentsTitle:
    """The stray marks and the title of a contents run whose body stream
    starts with `lines`, the first page's (spec section 30, rule 1)."""
    first = next(
        (
            number
            for number, line in enumerate(lines)
            if line_has_letter_or_digit(line.line)
        ),
        None,
    )
    if first is None:
        return ContentsTitle(tuple(range(len(lines))), None)
    line = lines[first]
    edge = _right_edges(lines)[line.page_index]
    title = (
        None
        if _page_number_length(line.line.words, edge) or _is_lone_label(line)
        else first
    )
    return ContentsTitle(tuple(range(first)), title)


@dataclass(frozen=True, slots=True, kw_only=True)
class ContentsEntry:
    """One entry of a printed contents (spec section 30): `lines` all its
    lines, for its origin; `title` the lines of its title, each with only
    its title's words, none when the title is empty; `label` its number as
    printed before the title, its words joined by single spaces, None when
    it has none; `page_number` likewise; `level` its depth, from 1; and
    `leader_dots` the removals of the leader dots before its page number,
    one per line; `stray_marks` the removals of the marks before its
    label, one per line (rule 7); `topics` whether it is a topics entry
    (rule 8), which is never linked to a heading (rule 9); and
    `label_inferred` whether its label was inferred, not read (rule
    12)."""

    lines: tuple[PlacedLine, ...]
    title: tuple[PlacedLine, ...]
    label: str | None
    page_number: str | None
    level: int
    leader_dots: tuple[Removal, ...]
    stray_marks: tuple[Removal, ...]
    topics: bool
    label_inferred: bool = False


def _pieces(lines: Sequence[PlacedLine]) -> tuple[tuple[PlacedLine, ...], ...]:
    """The lines cut into pieces where section 6's rule 1 or 2 starts a
    paragraph and before each lone label (spec section 30, rule 2); rule 3
    has no text edge on a contents page."""
    pieces: list[list[PlacedLine]] = []
    before: PlacedLine | None = None
    for line in lines:
        if not pieces or starts_paragraph(line, before) or _is_lone_label(line):
            pieces.append([])
        pieces[-1].append(line)
        before = line
    return tuple(tuple(piece) for piece in pieces)


def _is_analytical_summary(piece: Sequence[PlacedLine]) -> bool:
    """Spec section 30, rule 3: at least 2 lines, at least 2 inline page
    references, and at least one for every five lines. An inline page
    reference is neither the first nor the last word of its line."""
    references = sum(
        1
        for line in piece
        for word in line.line.words[1:-1]
        if _is_inline_reference(word.text)
    )
    return (
        len(piece) >= _SUMMARY_MIN_LINES
        and references >= _SUMMARY_MIN_REFERENCES
        and references * _SUMMARY_LINES_PER_REFERENCE >= len(piece)
    )


@dataclass(frozen=True, slots=True)
class _Raw:
    """An entry before its parts are taken: the lines of its lone label
    (none or one), its other lines, and whether it is an analytical
    summary."""

    label_lines: tuple[PlacedLine, ...]
    lines: tuple[PlacedLine, ...]
    summary: bool


def _raw_entries(
    lines: Sequence[PlacedLine], edges: frozendict[int, float]
) -> tuple[_Raw, ...]:
    """The run's lines cut into entries (spec section 30, rules 2 to 5),
    each lone label joined to the entry after it; a lone label at the end
    of the run is an entry of its own with no other line."""
    raws: list[_Raw] = []
    label: tuple[PlacedLine, ...] = ()
    for piece in _pieces(lines):
        if _is_lone_label(piece[0]):
            if label:
                raws.append(_Raw(label, (), summary=False))
            label = (piece[0],)
            piece = piece[1:]
            if not piece:
                continue
        if _is_analytical_summary(piece):
            raws.append(_Raw(label, piece, summary=True))
            label = ()
            continue
        current: list[PlacedLine] = []
        for position, line in enumerate(piece):
            if (
                not line_has_letter_or_digit(line.line)
                and not current
                and not label
                and raws
            ):
                # A line with no letter or digit joins the entry before it.
                last = raws[-1]
                raws[-1] = _Raw(last.label_lines, (*last.lines, line), last.summary)
                continue
            current.append(line)
            after = piece[position + 1] if position + 1 < len(piece) else None
            if (
                after is None
                or _page_number_length(line.line.words, edges[line.page_index]) > 0
                or (
                    after.line.box.x0 - current[0].line.box.x0 < _RUN_ON_MIN_PT
                    and line_has_letter_or_digit(after.line)
                )
            ):
                raws.append(_Raw(label, tuple(current), summary=False))
                label = ()
                current = []
    if label:
        raws.append(_Raw(label, (), summary=False))
    return tuple(raws)


@dataclass(frozen=True, slots=True)
class _Placed:
    """A word of an entry with the line it is on, by the line's position in
    the entry."""

    line: int
    word: Word


def _label_length(texts: Sequence[str]) -> tuple[int, int]:
    """How many of the first words of `texts` are marks before an entry's
    label by rule 7 of spec section 30, words with no letter or digit but
    a "§" that is part of the label, and how many after them are the
    label; (0, 0) when it has none or no word follows it."""
    marks = _marks(texts)
    if marks and texts[marks - 1] == _SECTION_SIGN:
        marks -= 1
    rest = texts[marks:]
    if not rest:
        return 0, 0
    first = rest[0]
    if (
        _NUMBER_LABEL.fullmatch(first)
        or (OCR_ROMAN_LABEL.fullmatch(first) and first.endswith("."))
        or first.rstrip(".").lower() in _NUMBER_WORDS
    ):
        length = 1
    elif starts_with_chapter_label_word(rest) or first == _SECTION_SIGN:
        length = 2
    else:
        return 0, 0
    return (marks, length) if len(rest) > length else (0, 0)


def _topics(raw: _Raw, title: Sequence[str]) -> bool:
    """Spec section 30, rule 8: an analytical summary, or an entry of at
    least 2 lines whose title holds at least 2 dashes."""
    return raw.summary or (
        len(raw.lines) >= _TOPICS_MIN_LINES and dash_count(title) >= _TOPICS_MIN_DASHES
    )


@dataclass(frozen=True, slots=True, kw_only=True)
class _Parts:
    """An entry's label, title words, page number, leader-dot removals and
    removals of the marks before its label (spec section 30, rules 5 to
    7)."""

    label: str | None
    placed: tuple[_Placed, ...]
    page_number: str | None
    leader_dots: tuple[Removal, ...]
    stray_marks: tuple[Removal, ...]


def _removals(
    raw: _Raw, placed: Sequence[_Placed], reason: RemovalReason
) -> tuple[Removal, ...]:
    """One removal of the words of `placed` on each line of the entry."""
    return tuple(
        words_removal(
            raw.lines[number].page_index,
            tuple(item.word for item in placed if item.line == number),
            reason,
        )
        for number in sorted({item.line for item in placed})
    )


def _parts(raw: _Raw, edges: frozendict[int, float]) -> _Parts:
    """An entry's parts (spec section 30, rules 5 to 7)."""
    placed = tuple(
        _Placed(number, word)
        for number, line in enumerate(raw.lines)
        for word in line.line.words
    )
    if raw.summary:
        label = _joined(raw.label_lines) if raw.label_lines else None
        return _Parts(
            label=label,
            placed=placed,
            page_number=None,
            leader_dots=(),
            stray_marks=(),
        )
    texts = tuple(item.word.text for item in placed)
    number_length = (
        _page_number_length(
            tuple(item.word for item in placed),
            edges[raw.lines[placed[-1].line].page_index],
        )
        if placed
        else 0
    )
    page_number = None
    dots: tuple[_Placed, ...] = ()
    words_before = len(placed) - number_length
    leading = words_before
    while leading > 0 and _is_leader_dots(texts[leading - 1]):
        leading -= 1
    if number_length and leading > 0:
        page_number = " ".join(texts[words_before:])
        dots = placed[leading:words_before]
        placed = placed[:leading]
    marks: tuple[_Placed, ...] = ()
    if raw.label_lines:
        label: str | None = _joined(raw.label_lines)
    else:
        mark_count, length = _label_length(tuple(item.word.text for item in placed))
        marks = placed[:mark_count]
        label = (
            " ".join(item.word.text for item in placed[mark_count:][:length]) or None
        )
        placed = placed[mark_count + length :]
    return _Parts(
        label=label,
        placed=placed,
        page_number=page_number,
        leader_dots=_removals(raw, dots, RemovalReason.LEADER_DOTS),
        stray_marks=_removals(raw, marks, RemovalReason.STRAY_MARK),
    )


def _joined(lines: Sequence[PlacedLine]) -> str:
    return " ".join(word.text for line in lines for word in line.line.words)


def contents_entries(lines: Sequence[PlacedLine]) -> tuple[ContentsEntry, ...]:
    """The entries of a contents run whose body stream, its pages' in page
    order, after its title and stray marks, is `lines` (spec section 30,
    rules 2 to 8)."""
    entries: list[ContentsEntry] = []
    # The depth of the nearest entry before that is not a topics entry, and
    # whether an entry of the run has a label that starts with a chapter
    # label word.
    nearest: int | None = None
    chapters_seen = False
    edges = _right_edges(lines)
    for raw in _raw_entries(lines, edges):
        parts = _parts(raw, edges)
        label, placed = parts.label, parts.placed
        title_texts = tuple(item.word.text for item in placed)
        chapter = label is not None and starts_with_chapter_label_word(
            tuple(label.split(" ")[_marks(label.split(" ")) :])
        )
        first = (raw.label_lines + raw.lines)[0]
        topics = _topics(raw, title_texts)
        if topics:
            level = nearest + 1 if nearest is not None else _CHAPTER_DEPTH
        elif chapter:
            level = _CHAPTER_DEPTH
        elif chapters_seen and is_centred(raw.lines[0] if raw.lines else first):
            level = _SECTION_DEPTH
        else:
            level = _CHAPTER_DEPTH
        if not topics:
            nearest = level
        chapters_seen = chapters_seen or chapter
        entries.append(
            ContentsEntry(
                lines=raw.label_lines + raw.lines,
                title=tuple(
                    with_words(
                        raw.lines[number],
                        tuple(item.word for item in placed if item.line == number),
                    )
                    for number in sorted({item.line for item in placed})
                ),
                label=label,
                page_number=parts.page_number,
                level=level,
                leader_dots=parts.leader_dots,
                stray_marks=parts.stray_marks,
                topics=topics,
            )
        )
    return _with_labels_inferred(entries)


def _with_labels_inferred(
    entries: Sequence[ContentsEntry],
) -> tuple[ContentsEntry, ...]:
    """`entries`, a contents run's, with the labels rule 12 of spec
    section 30 infers by their labels and depths, marked inferred."""
    inferred = inferred_labels(
        tuple(entry.label for entry in entries), tuple(entry.level for entry in entries)
    )
    return tuple(
        replace(entry, label=inferred[position], label_inferred=True)
        if position in inferred
        else entry
        for position, entry in enumerate(entries)
    )


# Spec section 30, rule 9: a candidate's title holds at least 4 letters; two
# plain texts match when SequenceMatcher's ratio is at least 0.7, measured
# on the candidates of the seven books with contents pages (section 30,
# "The thresholds").
_CANDIDATE_MIN_LETTERS = 4
_MATCH_MIN_RATIO = Fraction(7, 10)


def _plain(text: str) -> str:
    """`text` made plain (spec section 30, rule 9): case-folded, every
    character that is not a letter made a space, the spaces collapsed to
    one and stripped."""
    return " ".join("".join(c if c.isalpha() else " " for c in text.casefold()).split())


def is_link_candidate(title: str) -> bool:
    """Whether a contents entry that is not a topics entry, of title
    `title`, is a candidate for a link: its title holds at least 4
    letters (spec section 30, rule 9)."""
    return sum(c.isalpha() for c in title) >= _CANDIDATE_MIN_LETTERS


def _match_ratio(first: str, second: str) -> Fraction | None:
    """SequenceMatcher's ratio of two plain texts, exact, when they match:
    when it is at least 0.7; None otherwise."""
    min_ratio = _MATCH_MIN_RATIO
    matcher = SequenceMatcher(None, first, second, autojunk=False)
    if matcher.real_quick_ratio() < min_ratio or matcher.quick_ratio() < min_ratio:
        return None
    total = len(first) + len(second)
    if total == 0:
        return None
    matched = sum(block.size for block in matcher.get_matching_blocks())
    ratio = Fraction(2 * matched, total)
    return ratio if ratio >= min_ratio else None


def run_links(
    candidates: Sequence[str], headings: Sequence[str]
) -> tuple[tuple[int, int], ...]:
    """The links of one contents run (spec section 30, rule 9), as pairs of
    a position in `candidates`, the candidates' titles in the run's order,
    and a position in `headings`, the texts of the book's heading blocks
    without their labels, in the book's order: the largest set of
    matching pairs in which candidates and headings come in the same
    order, each in one pair at most; among those, the one whose ratios add
    up to the most, and then the one in which the first candidate whose
    pairing differs has the earlier heading."""
    plain_candidates = tuple(_plain(text) for text in candidates)
    plain_headings = tuple(_plain(text) for text in headings)
    ratios = {
        (i, j): ratio
        for i, candidate in enumerate(plain_candidates)
        for j, heading in enumerate(plain_headings)
        if (ratio := _match_ratio(candidate, heading)) is not None
    }
    rows, columns = len(candidates), len(headings)
    zero = (0, Fraction(0))
    # best[i][j]: the most links, and the largest sum of ratios, of the
    # candidates from i and the headings from j.
    best = [[zero] * (columns + 1) for _ in range(rows + 1)]
    for i in reversed(range(rows)):
        for j in reversed(range(columns)):
            value = max(best[i + 1][j], best[i][j + 1])
            ratio = ratios.get((i, j))
            if ratio is not None:
                count, total = best[i + 1][j + 1]
                value = max(value, (count + 1, total + ratio))
            best[i][j] = value
    links: list[tuple[int, int]] = []
    j = 0
    for i in range(rows):
        target = best[i][j]
        paired = next(
            (
                k
                for k in range(j, columns)
                if (i, k) in ratios
                and (best[i + 1][k + 1][0] + 1, best[i + 1][k + 1][1] + ratios[i, k])
                == target
            ),
            None,
        )
        if paired is not None:
            links.append((i, paired))
            j = paired + 1
    return tuple(links)


@dataclass(frozen=True, slots=True)
class TitleJunk:
    """The junk at the start and at the end of a contents entry's title
    (spec section 30, rule 11), "" for none."""

    start: str
    end: str


# Spec section 30, rule 11: a piece of junk is at most 5 characters long,
# spaces not counted, which hold a label of 2 digits in a pen circle,
# "(12)", or a page number of 3 digits with a sign, "290."; chosen, not
# measured (section 30, "The thresholds").
_JUNK_MAX_CHARACTERS = 5
_QUOTATION_MARKS = frozenset("\"'“”‘’«»")
# A piece at the end may be "p" or "pp" with one sign after it: "pp,".
_PAGES_ABBREVIATION = re.compile(r"pp?[^\w\s]")


def _core(word: str) -> str:
    """A word case-folded, the characters that are not a letter or a digit
    taken off its end (spec section 30, rule 11)."""
    folded = word.casefold()
    end = len(folded)
    while end > 0 and not folded[end - 1].isalnum():
        end -= 1
    return folded[:end]


def _agreement(first: str, second: str) -> Fraction:
    """How much two words agree: SequenceMatcher's ratio of their cores,
    exact (spec section 30, rule 11)."""
    a, b = _core(first), _core(second)
    if not a and not b:
        return Fraction(0)
    matcher = SequenceMatcher(None, a, b, autojunk=False)
    matched = sum(block.size for block in matcher.get_matching_blocks())
    return Fraction(2 * matched, len(a) + len(b))


def _is_piece_shape(piece: str, *, at_end: bool) -> bool:
    """Whether `piece` has the shape of junk (spec section 30, rule 11): at
    most 5 characters, spaces not counted, made only of signs or holding a
    character other than a letter once the signs at its end are taken
    off, and not only quotation marks;
    at the end of a title, also "p" or "pp" with a sign."""
    characters = piece.replace(" ", "")
    if not characters or len(characters) > _JUNK_MAX_CHARACTERS:
        return False
    if all(character in _QUOTATION_MARKS for character in characters):
        return False
    if at_end and _PAGES_ABBREVIATION.fullmatch(characters):
        return True
    core = characters
    while core and not core[-1].isalnum():
        core = core[:-1]
    return not core or any(not character.isalpha() for character in core)


def _start_junk(title: str, heading_word: str) -> str:
    """The junk at the start of `title`, whose words are joined by single
    spaces, against the heading's first word; "" for none."""
    best = (_agreement(title.split(" ")[0], heading_word), 0)
    for cut in range(1, len(title)):
        piece, rest = title[:cut], title[cut:]
        if len(piece.replace(" ", "")) > _JUNK_MAX_CHARACTERS:
            break
        if rest.startswith(" "):
            continue
        glued = not piece.endswith(" ")
        if glued and not rest[0].isupper():
            continue
        if not _is_piece_shape(piece.strip(), at_end=False):
            continue
        agreement = _agreement(rest.split(" ")[0], heading_word)
        if agreement > best[0]:
            best = (agreement, cut)
    agreement, cut = best
    return title[:cut].strip() if cut and agreement >= _MATCH_MIN_RATIO else ""


def _end_junk(title: str, heading_word: str) -> str:
    """The junk at the end of `title`, whose words are joined by single
    spaces, against the heading's last word; "" for none."""
    best = (_agreement(title.split(" ")[-1], heading_word), len(title))
    for cut in range(len(title) - 1, 0, -1):
        rest, piece = title[:cut], title[cut:]
        if len(piece.replace(" ", "")) > _JUNK_MAX_CHARACTERS:
            break
        if piece.startswith(" "):
            continue
        glued = not rest.endswith(" ")
        if glued and not piece[0].isupper():
            continue
        if not _is_piece_shape(piece, at_end=True):
            continue
        agreement = _agreement(rest.rstrip(" ").split(" ")[-1], heading_word)
        # The shortest of equally good pieces: the loop goes from short to
        # long, so only a better one replaces it.
        if agreement > best[0]:
            best = (agreement, cut)
    agreement, cut = best
    return (
        title[cut:].strip()
        if cut < len(title) and agreement >= _MATCH_MIN_RATIO
        else ""
    )


def title_junk(title: str, heading: str) -> TitleJunk:
    """The junk at the start and at the end of a linked contents entry's
    `title`, against its heading's text `heading` without its label (spec
    section 30, rule 11): at most 5 characters with a mark or a digit
    inside, after which, or before which, the title's word agrees best
    with the heading's first, or last, word, at 0.7 at least. Junk at the
    start may end inside a word whose rest starts with a capital; junk at
    the end may start inside a word with a capital."""
    title_words = title.split()
    heading_words = heading.split()
    if not title_words or not heading_words:
        return TitleJunk("", "")
    joined = " ".join(title_words)
    start = _start_junk(joined, heading_words[0])
    rest = joined[len(start) :].lstrip(" ") if start else joined
    end = _end_junk(rest, heading_words[-1]) if rest else ""
    return TitleJunk(start, end)


@dataclass(frozen=True, slots=True)
class JunkTaken:
    """A linked contents entry's block without the junk of rule 11 of spec
    section 30, the removals of that junk and the word changes that split
    junk glued to a word."""

    block: Block
    removals: tuple[Removal, ...]
    changes: tuple[WordChange, ...]


def _end_reason(junk: str) -> RemovalReason:
    """Junk at a title's end is a page number when it holds a digit or is
    "p" or "pp" with a sign, a stray mark otherwise (rule 11)."""
    if any(character.isdigit() for character in junk) or _PAGES_ABBREVIATION.fullmatch(
        junk
    ):
        return RemovalReason.PAGE_NUMBER
    return RemovalReason.STRAY_MARK


def _taken(
    junk: str,
    reason: RemovalReason,
    words: Sequence[Word],
    expected: Sequence[str],
    split: tuple[str, str] | None,
    line: PlacedLine,
) -> tuple[Removal, tuple[WordChange, ...]]:
    """The removal of `junk`, on the page of `line`, with the box of
    `words`, the title's words it was read in, when their texts are
    `expected`, else the line's box; and, when the junk is glued to a
    word, the change that splits that word into `split`."""
    box = (
        box_of(tuple(word.box for word in words))
        if words and tuple(word.text for word in words) == tuple(expected)
        else line.line.box
    )
    removal = Removal(page_index=line.page_index, box=box, text=junk, reason=reason)
    if split is None:
        return removal, ()
    return removal, (
        WordChange(
            page_index=line.page_index,
            before=("".join(split),),
            after=split,
            reason=ChangeReason.CASE_SPLIT,
        ),
    )


def without_junk(block: Block, entry: ContentsEntry, heading: Block) -> JunkTaken:
    """`block`, the contents entry `entry` linked to `heading`, without the
    text at the start and end of its title that is not the heading's (spec
    section 30, rule 11), with the removals of that text, from the words
    of the entry's title, and the word changes that split it off a word it
    was glued to. Junk at the start is taken only from the first span, at
    the end only from the last."""
    junk = title_junk(block_text(block), block_text(heading))
    if not block.spans or not entry.title or junk == TitleJunk("", ""):
        return JunkTaken(block, (), ())
    spans = list(block.spans)
    title_words = tuple(word for line in entry.title for word in line.line.words)
    removals: list[Removal] = []
    changes: list[WordChange] = []
    first = spans[0].text.lstrip()
    if junk.start and first.startswith(junk.start):
        rest = first[len(junk.start) :]
        parts = junk.start.split(" ")
        split = None if rest.startswith(" ") else (parts[-1], rest.split(" ")[0])
        expected = (*parts[:-1], "".join(split)) if split else parts
        removal, change = _taken(
            junk.start,
            RemovalReason.STRAY_MARK,
            title_words[: len(parts)],
            expected,
            split,
            entry.title[0],
        )
        removals.append(removal)
        changes.extend(change)
        spans[0] = _with_text(spans[0], rest.lstrip())
    last = spans[-1].text.rstrip()
    if junk.end and last.endswith(junk.end):
        rest = last[: -len(junk.end)]
        parts = junk.end.split(" ")
        split = None if rest.endswith(" ") else (rest.split(" ")[-1], parts[0])
        expected = ("".join(split), *parts[1:]) if split else parts
        removal, change = _taken(
            junk.end,
            _end_reason(junk.end),
            title_words[-len(parts) :],
            expected,
            split,
            entry.title[-1],
        )
        removals.append(removal)
        changes.extend(change)
        spans[-1] = _with_text(spans[-1], rest.rstrip())
    return JunkTaken(
        replace(block, spans=tuple(spans)), tuple(removals), tuple(changes)
    )


def _with_text(span: Span, text: str) -> Span:
    return replace(span, text=text)
