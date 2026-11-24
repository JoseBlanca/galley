"""Note links from the model's reading of a page (docs/specs/correct.md,
section 9b): the references it marks and its note lines, the galley word
and note each goes to, and the link edits they become."""

import logging
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from collections.abc import Set as AbstractSet
from dataclasses import dataclass
from enum import StrEnum

from galley.correct._merge import AUTHOR, Change
from galley.correct._reading import GalleyToken, Place
from galley.correct._tokens import alike, tokens
from galley.model import (
    Block,
    BlocksFile,
    Edit,
    Note,
    block_sha256,
    every_block,
    only_occurrence,
)

_logger = logging.getLogger(__name__)

REASON = "vision_note_link"

_SUPERSCRIPTS = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹", "0123456789")
# A reference the model marks: [x], <sup>x</sup>, or superscript digits.
_MARK = re.compile(r"\[([^\]\s]{1,4})\]|<sup>([^<\s]{1,4})</sup>|([⁰¹²³⁴⁵⁶⁷⁸⁹]+)")
# A note line, in the forms the model writes it: "NOTE 4 | Campagne de",
# "NOTE, 4, Campagne", or the note copied whole, "100 Abu Simbel: ...".
_NOTE_LINE = re.compile(
    r"^\s*(?:NOTE[\s,:|]*)?([0-9⁰¹²³⁴⁵⁶⁷⁸⁹]{1,3}|[*†‡])[\s,.:|]+(\S.*)$"
)
# What a reference the model marks reads as: a number or a sign; the
# model also brackets other things ("[at]" on Kadesh page 27).
_REFERENCE_TEXT = re.compile(r"[0-9]{1,3}|[*†‡]{1,2}")
# The words before a reference the model gives, and the words of a note
# line compared with a note's first words.
_WORDS_BEFORE = 3
_NOTE_WORDS = 3
# Measured on the twelve reference pages, 19 November 2026 (section 9b).
_LEAST_CANDIDATE = 0.75
_LEAST_LEAD = 0.5
_LEAST_NOTE = 0.6
_LEAST_NOTE_LEAD = 0.1
# Review of 19 November 2026: the model's "order" placed on galley's
# "ordered" (Kadesh page 45); a misread word keeps its length within one.
_MOST_LENGTH_DIFFERENCE = 1
# A misread reference left in galley's word: 1 to 3 of these characters.
_MISREAD_LONGEST = 3
_MISREAD_CHARACTERS = frozenset("0123456789'\"‘’“”*†‡™®^%")
_QUOTE_CHARACTERS = frozenset("'\"‘’“”")
_STRAIGHT = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"'})
# The signs the OCR gives for a raised number that a link may take out of
# galley's core: every core of the seven books that ends in one is a
# misread reference or noise (section 9b, 21 November 2026).
_RAISED_SIGNS = frozenset("™®^")
# What is no letter or digit at the end of a core: section 6 keeps a sign
# such as "™" in the core, and the punctuation before it ("soldiers;™").
_CORE_END = re.compile(r"[\W_]+$")


@dataclass(frozen=True, slots=True)
class MarkedReference:
    """A reference the model marks: its text, the words before it in its
    line (the last three) and the word after it."""

    text: str
    before: tuple[str, ...]
    after: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class LinkAnswer:
    """The model's answer to the prompt of section 9b: the references it
    marks, in order, and the first words of each note line, by number."""

    references: tuple[MarkedReference, ...]
    notes: Mapping[str, str]


def link_answer(raw: str) -> LinkAnswer:
    """The references and note lines of the model's answer (section 9b).
    Only the first note line of a number is kept, and only the numbers
    some reference has."""
    references = []
    note_lines: dict[str, str] = {}
    for line in raw.splitlines():
        marks = [
            MarkedReference(
                text=next(group for group in mark.groups() if group)
                .translate(_SUPERSCRIPTS)
                .strip(),
                before=tuple(
                    _MARK.sub("", line[: mark.start()]).split()[-_WORDS_BEFORE:]
                ),
                after=tuple(_MARK.sub("", line[mark.end() :]).split()[:1]),
            )
            for mark in _MARK.finditer(line)
        ]
        placed = [
            mark
            for mark in marks
            if mark.before and _REFERENCE_TEXT.fullmatch(mark.text) is not None
        ]
        if placed:
            references.extend(placed)
            continue
        if (note := _NOTE_LINE.match(line)) is not None:
            number = note.group(1).translate(_SUPERSCRIPTS)
            note_lines.setdefault(number, note.group(2).replace("|", " ").strip())
    numbers = {reference.text for reference in references}
    return LinkAnswer(
        tuple(references),
        frozendict({k: v for k, v in note_lines.items() if k in numbers}),
    )


def _forms(text: str) -> tuple[str, ...]:
    return tuple(token.form for token in tokens(text))


def reference_place(
    body: Sequence[GalleyToken], reference: MarkedReference
) -> int | None:
    """The position in `body`, galley's body tokens of the page, of the
    token the reference follows (section 9b): the best candidate when it
    scores 0.5 more than the second; None otherwise or when it is fixed."""
    wanted = _forms(" ".join(reference.before))
    if not wanted:
        return None
    after = _forms(" ".join(reference.after))
    forms = [token.form for token in body]

    def score(position: int) -> float:
        total = sum(
            alike(forms[position - back], word)
            for back, word in enumerate(reversed(wanted))
            if position - back >= 0
        )
        following = next(
            (
                index
                for index in range(position + 1, len(body))
                if body[index].place is not None
            ),
            None,
        )
        if following is not None and after:
            total += alike(forms[following], after[0])
        return total

    candidates = sorted(
        (
            position
            for position, form in enumerate(forms)
            if alike(form, wanted[-1]) >= _LEAST_CANDIDATE
        ),
        key=score,
        reverse=True,
    )
    if not candidates:
        return None
    if (
        len(candidates) > 1
        and score(candidates[0]) - score(candidates[1]) < _LEAST_LEAD
    ):
        return None
    best = candidates[0]
    if (
        body[best].place is None
        or abs(len(forms[best]) - len(wanted[-1])) > _MOST_LENGTH_DIFFERENCE
    ):
        return None
    return best


def _first_words(text: str) -> str:
    return "".join(_forms(" ".join(text.split()[:_NOTE_WORDS])))


def note_of(notes: Sequence[Note], first_words: str) -> str | None:
    """The id of the note, among `notes`, whose first three words are most
    alike `first_words`' (section 9b): 0.6 alike at least and 0.1 more than
    any other; None otherwise."""
    wanted = _first_words(first_words)
    scored = sorted(
        (
            (
                alike(
                    _first_words(
                        " ".join(
                            span.text for block in note.blocks for span in block.spans
                        )
                    ),
                    wanted,
                ),
                note.id,
            )
            for note in notes
        ),
        reverse=True,
    )
    if not scored or scored[0][0] < _LEAST_NOTE:
        return None
    if len(scored) > 1 and scored[0][0] - scored[1][0] < _LEAST_NOTE_LEAD:
        return None
    return scored[0][1]


@dataclass(frozen=True, slots=True, kw_only=True)
class Link:
    """A link the model's answer gives on page `page_index`: after the
    galley word that holds `place`, a reference to the note `note_id`;
    `text` is the reference as the model read it, `model_word` the word
    the model printed before it, and `rank` how many references the model
    marked on the page before it."""

    page_index: int
    place: Place
    note_id: str
    text: str
    model_word: str
    rank: int = 0


@dataclass(frozen=True, slots=True, kw_only=True)
class _Placed:
    """A reference of the answer placed after a galley word: its rank as
    `Link` has it, the note its note line names (None when it names none),
    and whether galley's own reference follows the word."""

    rank: int
    reference: MarkedReference
    place: Place
    note_id: str | None
    at_galley_reference: bool


def page_links(
    page_index: int,
    reading: Sequence[GalleyToken],
    notes: Sequence[Note],
    answer: LinkAnswer,
    galley_references: Mapping[Place, str] = frozendict(),
) -> tuple[Link, ...]:
    """The links of one page (section 9b): each reference of the answer
    placed after a word of galley's body and matched to one of `notes`, the
    notes that start on the page, through its note line, less the links
    that break the order of the page's notes; then the references whose
    note line names no note, or a note another reference names too, placed
    by that order between two links. A reference whose number the model
    marks twice on the page gives no link. `galley_references` gives, by the
    place of a token, the note galley's own reference right after its word
    refers to; a reference the model marks there that gives no link, or
    one to that note, counts once in the numbers of the page, and so does
    a reference with no place whose note galley references."""
    body = [
        token
        for token in reading
        if token.note_id is None and token.block_id is not None
    ]
    repeated = _repeated(answer.references)
    placed = []
    marked: set[str] = set()
    unresolved = set()
    for rank, reference in enumerate(answer.references):
        position = reference_place(body, reference)
        first_words = answer.notes.get(reference.text)
        # A number marked twice names no note: which of its references the
        # note line belongs to is not known.
        note_id = (
            None
            if first_words is None or reference.text in repeated
            else note_of(notes, first_words)
        )
        place = None if position is None else body[position].place
        galley_note_id = None if place is None else galley_references.get(place)
        if galley_note_id is not None and note_id in (None, galley_note_id):
            marked.add(galley_note_id)
        elif place is None and note_id is not None:
            marked.add(note_id)
        elif place is None or note_id is None:
            unresolved.add(rank)
        if place is not None and reference.text not in repeated:
            placed.append(
                _Placed(
                    rank=rank,
                    reference=reference,
                    place=place,
                    note_id=note_id,
                    at_galley_reference=galley_note_id is not None,
                )
            )
    links = tuple(
        _link(page_index, item, item.note_id)
        for item in placed
        if item.note_id is not None
    )
    if repeated:
        _logger.info(
            "page %d: the model marks %s more than once; no link from them",
            page_index,
            ", ".join(sorted(repeated)),
        )
    kept = links_in_order(links, notes, frozenset(marked), frozenset(unresolved))
    for link in links:
        if link not in kept:
            _logger.info(
                "page %d: the link of reference %s to note %s breaks the order "
                "of the page's notes; not proposed",
                page_index,
                link.text,
                link.note_id,
            )
    twice = _named_twice(links)
    by_order = _links_by_order(
        page_index,
        tuple(
            item
            for item in placed
            if not item.at_galley_reference
            and (item.note_id is None or item.note_id in twice)
        ),
        kept,
        notes,
        _uncounted(links, frozenset(marked)),
        frozenset(link.note_id for link in links) - twice,
        frozenset(unresolved),
    )
    return tuple(sorted(kept + by_order, key=lambda link: link.rank))


def _link(page_index: int, item: _Placed, note_id: str) -> Link:
    return Link(
        page_index=page_index,
        place=item.place,
        note_id=note_id,
        text=item.reference.text.replace("[", "").replace("]", ""),
        model_word=item.reference.before[-1],
        rank=item.rank,
    )


def _repeated(references: Sequence[MarkedReference]) -> frozenset[str]:
    """The numbers or signs the model marks more than once on a page,
    placed or not (section 9b)."""
    counts = Counter(reference.text for reference in references)
    return frozenset(text for text, count in counts.items() if count > 1)


def galley_references(
    blocks: BlocksFile, reading: Sequence[GalleyToken]
) -> frozendict[Place, str]:
    """By the place of each changeable token of `reading`, the note that
    galley's reference span right after the token's word refers to: the
    word ends its span, and the next span is a reference (section 9b)."""
    spans = {block.id: block.spans for block in every_block(blocks)}
    found = {}
    for token in reading:
        place = token.place
        if place is None:
            continue
        block_spans = spans[place.block_id]
        rest = block_spans[place.span_index].text[place.end :]
        if any(c.isspace() for c in rest) or place.span_index + 1 >= len(block_spans):
            continue
        note_ref = block_spans[place.span_index + 1].note_ref
        if note_ref is not None:
            found[place] = note_ref
    return frozendict(found)


def _number(text: str) -> int | None:
    digits = text.rstrip(".")
    return int(digits) if digits.isdigit() else None


def _named_twice(links: Sequence[Link]) -> frozenset[str]:
    counts = Counter(link.note_id for link in links)
    return frozenset(note_id for note_id, count in counts.items() if count > 1)


def _uncounted(links: Sequence[Link], marked: AbstractSet[str]) -> frozenset[str]:
    """The notes that do not count as marked when galley references them:
    those a link goes to, and those of `marked`, whose galley reference
    the model marked already (section 9b)."""
    return frozenset({link.note_id for link in links} | marked)


def _slot(index: int, notes: Sequence[Note], uncounted: AbstractSet[str]) -> int:
    """How many of the model's references come before the footnote `index`
    of the page when its order holds: the footnotes before it, less those
    galley references and that are not in `uncounted`, which the model
    need not mark (section 9b)."""
    return index - sum(
        1 for note in notes[:index] if note.referenced and note.id not in uncounted
    )


def _fits(
    index: int,
    rank: int,
    notes: Sequence[Note],
    uncounted: AbstractSet[str],
    unresolved: AbstractSet[int],
) -> bool:
    """Whether the footnote `index` is the one the reference of `rank` goes
    to in the page's order (section 9b). Not when a footnote before it
    counts as marked by galley's reference and a reference before it, of
    the ranks `unresolved`, gives no note: that reference may be the one
    to galley's note, and the count is not known."""
    slot = _slot(index, notes, uncounted)
    return slot == rank and (
        slot == index or not any(other < rank for other in unresolved)
    )


def links_in_order(
    links: Sequence[Link],
    notes: Sequence[Note],
    marked: AbstractSet[str] = frozenset(),
    unresolved: AbstractSet[int] = frozenset(),
) -> tuple[Link, ...]:
    """The links of a page that keep the order of its notes (section 9b),
    in the order of `links`, the model's answer: those to a note no other
    link goes to; of these, those whose note is the k-th footnote of the
    page when its reference is the k-th the model marked on it, counted
    from 0; and of these, those out of order with no other: none comes
    before it in the answer with its note or its number at or after the
    link's, and none after it with its note or its number at or before
    the link's (numbers compared only when both are digits). A link is
    dropped with every link it is out of order with. The footnotes before
    a link's note that galley references, that no link goes to and that are not in
    `marked`, whose galley reference the model marked already, count as
    marked too (the heading's "*" on Kadesh's page 8, which the model
    does not bracket), and a link after a reference of the ranks
    `unresolved`, which gives no note, is then dropped. The numbers are not compared with galley's
    markers: the model misreads the tens of every number on Kadesh's pages
    26 and 53, and their links are right."""
    order = {note.id: index for index, note in enumerate(notes)}
    twice = _named_twice(links)
    uncounted = _uncounted(links, marked)
    fitting = [
        link
        for link in links
        if link.note_id not in twice
        and _fits(order[link.note_id], link.rank, notes, uncounted, unresolved)
    ]

    def before(first: Link, second: Link) -> bool:
        first_number = _number(first.text)
        second_number = _number(second.text)
        return order[first.note_id] < order[second.note_id] and (
            first_number is None
            or second_number is None
            or first_number < second_number
        )

    return tuple(
        link
        for position, link in enumerate(fitting)
        if all(before(other, link) for other in fitting[:position])
        and all(before(link, other) for other in fitting[position + 1 :])
    )


def _links_by_order(
    page_index: int,
    placed: Sequence[_Placed],
    kept: Sequence[Link],
    notes: Sequence[Note],
    uncounted: AbstractSet[str],
    named: AbstractSet[str],
    unresolved: AbstractSet[int],
) -> tuple[Link, ...]:
    """The links of `placed`, references whose note line names no note of
    the page or one another reference names too, by the order of the page
    (section 9b): the footnote as many places before the note of the next
    link of `kept` as the reference's number is below that link's, when
    the link before it in `kept`, if any, has as many numbers below the
    next link's as notes, the footnote is the k-th as `links_in_order`
    counts, galley references none of it and no link of `named` goes to
    it. The k-th count also gives what section 9b asks besides: the link
    before has a smaller number than the reference (else the note found
    would be at or before that link's, whose count is smaller), and no
    two references find one note (their ranks differ, so their counts
    do)."""
    order = {note.id: index for index, note in enumerate(notes)}
    found = []
    for item in placed:
        number = _number(item.reference.text)
        if number is None:
            continue
        after = next((link for link in kept if link.rank > item.rank), None)
        before = next((link for link in reversed(kept) if link.rank < item.rank), None)
        if after is None or (after_number := _number(after.text)) is None:
            continue
        index = order[after.note_id] - (after_number - number)
        if index < 0 or number >= after_number:
            continue
        if before is not None:
            before_number = _number(before.text)
            if (
                before_number is None
                or after_number - before_number
                != order[after.note_id] - order[before.note_id]
            ):
                continue
        note = notes[index]
        if (
            note.referenced
            or note.id in named
            or not _fits(index, item.rank, notes, uncounted, unresolved)
        ):
            continue
        found.append(_link(page_index, item, note.id))
    placed_links = tuple(found)
    if placed_links:
        _logger.info(
            "page %d: %d links placed by the order of the page's notes",
            page_index,
            len(placed_links),
        )
    return placed_links


# The edits.


@dataclass(frozen=True, slots=True)
class _Word:
    start: int
    end: int


def _words(text: str) -> tuple[_Word, ...]:
    return tuple(
        _Word(match.start(), match.end()) for match in re.finditer(r"\S+", text)
    )


def _bare_end(core: str) -> int:
    """The length of `core` less what is no letter or digit at its end
    (section 9b); the whole core when nothing else is left."""
    found = _CORE_END.search(core)
    return len(core) if found is None or found.start() == 0 else found.start()


def misread_reference(
    galley_core: str, galley_after: str, model_word: str, number: str
) -> str | None:
    """The misread reference at the end of a galley word, which a link
    takes the place of (section 9b): `galley_core` is the core of the
    word's token the link follows and `galley_after` what follows it in
    the word; `model_word` is the word the model printed before the
    reference `number`. Both cores are cut of what is no letter or digit
    at their end; the characters galley has past those the model has
    there are the misread reference when they are 1 to 3 digits or signs,
    empty otherwise. When they hold `number`, the quotes before it stay
    in the word ("soldiers.”37" has the misread reference "37"). None, no
    link, when galley's core keeps past the model's a character other
    than "™", "®" or "^", or one that the misread reference leaves in the
    word ("50%" against the model's "50")."""
    model_tokens = tokens(model_word)
    model_after = ""
    if model_tokens:
        model_core = model_word[model_tokens[-1].start : model_tokens[-1].end]
        model_after = (
            model_core[_bare_end(model_core) :] + model_word[model_tokens[-1].end :]
        )
    galley_cut = galley_core[_bare_end(galley_core) :]
    signs = galley_cut[len(model_after) :]
    if any(c not in _RAISED_SIGNS for c in signs):
        return None
    after = galley_cut + galley_after
    if not after.translate(_STRAIGHT).startswith(model_after.translate(_STRAIGHT)):
        return None if signs else ""
    tail = after[len(model_after) :]
    misread = tail
    if len(tail) > _MISREAD_LONGEST or any(c not in _MISREAD_CHARACTERS for c in tail):
        misread = ""
    elif (found := tail.find(number) if number else -1) > 0 and all(
        c in _QUOTE_CHARACTERS for c in tail[:found]
    ):
        misread = tail[found:]
    if signs and not misread.startswith(signs):
        return None
    return misread


def _changed_offsets(changes: Sequence[Change]) -> dict[tuple[str, int], list[int]]:
    found: dict[tuple[str, int], list[int]] = {}
    for change in changes:
        found.setdefault((change.place.block_id, change.place.span_index), []).append(
            change.place.start
        )
    return found


def _edited_text(block: Block, edits: Sequence[Edit]) -> str:
    """The block's text with the stage's word edits of it made."""
    text = "".join(span.text for span in block.spans)
    for edit in edits:
        start = only_occurrence(text, edit.old)
        if start is not None:
            text = text[:start] + edit.new + text[start + len(edit.old) :]
    return text


class _Follow(StrEnum):
    """What follows a galley word when it is no reference to a note."""

    NOTHING = "nothing"
    AFTER_SPACE = "a reference after white space"


def _following_reference(block: Block, span_index: int, word: _Word) -> str | _Follow:
    """The note a reference span directly after the word refers to; or
    whether a reference follows it only after white space, or none does."""
    text = block.spans[span_index].text
    rest = text[word.end :]
    if rest.strip() or span_index + 1 >= len(block.spans):
        return _Follow.NOTHING
    note_ref = block.spans[span_index + 1].note_ref
    if note_ref is None:
        return _Follow.NOTHING
    return note_ref if rest == "" else _Follow.AFTER_SPACE


def _context(
    text: str,
    words: Sequence[_Word],
    position: int,
    changed: Sequence[int],
    texts: tuple[str, str],
) -> int | None:
    """The first word of `old`: the word at `position` with words before it
    added one at a time, never one another edit changes, until `old`
    occurs once in each of `texts`; None when it never does."""
    end = words[position].end
    for low in range(position, -1, -1):
        word = words[low]
        if low != position and any(
            word.start <= offset < word.end for offset in changed
        ):
            return None
        old = text[word.start : end]
        if all(only_occurrence(block_text, old) is not None for block_text in texts):
            return low
    return None


def _link_edit(
    block: Block,
    link: Link,
    words: Sequence[_Word],
    position: int,
    changed: Sequence[int],
    texts: tuple[str, str],
    model: str,
) -> Edit | None:
    text = block.spans[link.place.span_index].text
    word = words[position]
    misread = misread_reference(
        text[link.place.start : link.place.end],
        text[link.place.end : word.end],
        link.model_word,
        link.text,
    )
    if misread is None:
        _logger.info(
            "page %d, block %s: %r ends in a sign that may be printed; no link to %s",
            link.page_index,
            block.id,
            text[word.start : word.end],
            link.note_id,
        )
        return None
    low = _context(text, words, position, changed, texts)
    if low is None:
        _logger.info(
            "page %d, block %s: %r occurs more than once however widened; no "
            "link to %s",
            link.page_index,
            block.id,
            text[word.start : word.end],
            link.note_id,
        )
        return None
    old = text[words[low].start : word.end]
    # The model's number is the reference's text; a misread reference
    # taken out of galley's word is kept only in `old` (section 9b).
    new = old[: len(old) - len(misread)] + f"[{link.text}](#{link.note_id})"
    return Edit(
        block_id=block.id,
        block_sha256=block_sha256(block),
        old=old,
        new=new,
        author=AUTHOR,
        reason=REASON,
        page_index=link.page_index,
        model=model,
        second_reading=None,
    )


def _word_of(by_id: Mapping[str, Block], link: Link) -> tuple[str, int, int]:
    """The galley word a link follows: its block, span and start."""
    words = _words(by_id[link.place.block_id].spans[link.place.span_index].text)
    start = next(
        word.start for word in words if word.start <= link.place.start < word.end
    )
    return link.place.block_id, link.place.span_index, start


def link_edits(
    blocks: BlocksFile,
    links: Sequence[Link],
    changes: Sequence[Change],
    word_edits: Sequence[Edit],
    model: str,
) -> tuple[Edit, ...]:
    """The link edits of `links` (section 9b), in their order, less those
    refused and logged: two links to one note or after one word, a word the word edits
    change, a reference after white space, a note galley references
    elsewhere that no link takes the place of, no `old` that occurs once."""
    by_id = {block.id: block for block in every_block(blocks)}
    counts = Counter(link.note_id for link in links)
    after_word = Counter(_word_of(by_id, link) for link in links)
    changed = _changed_offsets(changes)
    prepared = []
    for link in links:
        if counts[link.note_id] > 1:
            _logger.info(
                "page %d: two links to note %s; neither is proposed",
                link.page_index,
                link.note_id,
            )
            continue
        if after_word[_word_of(by_id, link)] > 1:
            _logger.info(
                "page %d: two links after one word, one to note %s; neither "
                "is proposed",
                link.page_index,
                link.note_id,
            )
            continue
        block = by_id[link.place.block_id]
        words = _words(block.spans[link.place.span_index].text)
        position = next(
            index
            for index, word in enumerate(words)
            if word.start <= link.place.start < word.end
        )
        word = words[position]
        offsets = changed.get((block.id, link.place.span_index), [])
        if any(word.start <= offset < word.end for offset in offsets):
            _logger.info(
                "page %d: another edit changes the word before the reference "
                "to %s; no link",
                link.page_index,
                link.note_id,
            )
            continue
        following = _following_reference(block, link.place.span_index, word)
        if following is _Follow.AFTER_SPACE:
            _logger.info(
                "page %d: a reference follows the word only after white space; "
                "no link to %s",
                link.page_index,
                link.note_id,
            )
            continue
        if following is not _Follow.NOTHING and following == link.note_id:
            continue
        prepared.append(
            (
                link,
                block,
                words,
                position,
                offsets,
                None if following is _Follow.NOTHING else following,
            )
        )
    edits_by_block: dict[str, list[Edit]] = {}
    for edit in word_edits:
        edits_by_block.setdefault(edit.block_id, []).append(edit)
    made = []
    for link, block, words, position, offsets, replacing in prepared:
        texts = (
            "".join(span.text for span in block.spans),
            _edited_text(block, edits_by_block.get(block.id, [])),
        )
        edit = _link_edit(block, link, words, position, offsets, texts, model)
        if edit is not None:
            made.append((link, edit, replacing))
    return tuple(edit for _, edit, _ in _without_double_references(blocks, made))


def _without_double_references(
    blocks: BlocksFile, made: Sequence[tuple[Link, Edit, str | None]]
) -> tuple[tuple[Link, Edit, str | None], ...]:
    """The link edits less those whose note galley references at a place no
    kept link takes; refusing one link can bring back galley's reference
    it replaced, so this is repeated until none is refused."""
    referenced = {
        span.note_ref
        for block in every_block(blocks)
        for span in block.spans
        if span.note_ref is not None
    }
    replaced = {replacing for _, _, replacing in made if replacing is not None}
    refused = tuple(item for item in made if item[0].note_id in referenced - replaced)
    for link, _, _ in refused:
        _logger.info(
            "page %d: galley references note %s elsewhere; no link",
            link.page_index,
            link.note_id,
        )
    if not refused:
        return tuple(made)
    return _without_double_references(
        blocks, tuple(item for item in made if item not in refused)
    )
