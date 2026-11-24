"""Tests of the plan wrong-links, work package 4: the wrong links of a book
whose footnotes are numbered through, Kadesh (docs/specs/structure.md,
section 11, "Matching", "A one-digit value" and "A sign at the head of a
page").

The unit tests make up a page's notes and candidates. The excerpt tests
run on the Kadesh excerpts read with `ocr = "redo"`; each link's printed
numbers, of its reference and of its note, are those of
tests/fixtures/expected/kadesh_reference/note_references.json, read from
the page images.
"""

import difflib
import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from galley.book_folder import BookFolder
from galley.model import every_block, read_blocks
from galley.structure._lone_references import lone_links
from galley.structure._markers import Reference, ReferenceForm
from galley.structure._references import (
    BodyWord,
    Candidate,
    Link,
    NoteMark,
    NoteToMatch,
    match_footnotes,
    note_score,
    pair_score,
    sure_through,
    through_score,
    without_one_digit_values,
)

_REFERENCE = (
    Path(__file__).parent
    / "fixtures"
    / "expected"
    / "kadesh_reference"
    / "note_references.json"
)
# The excerpts read with `ocr = "redo"` and the whole book's page index of
# each one's first page.
_EXCERPT_FIRST_PAGES = frozendict(
    {"kadesh_redo": 8, "kadesh_29-38": 29, "kadesh_59-68": 59}
)


def _sign(before: str = "") -> Reference:
    return Reference(before, "*", "", ReferenceForm.SIGN, None)


def _glued(word: str, digits: str) -> Reference:
    return Reference(word, digits, "", ReferenceForm.GLUED, int(digits))


def _candidates(references: tuple[Reference, ...]) -> tuple[Candidate, ...]:
    return tuple(
        Candidate(0, word, 14, reference) for word, reference in enumerate(references)
    )


def test_a_sign_scores_less_against_a_note_whose_marker_stood_for_a_number() -> None:
    assert pair_score(_sign("enemy;"), None, NoteMark.SIGN) == 2
    assert pair_score(_sign("enemy;"), None, NoteMark.NUMBER) == 1
    assert pair_score(_sign("enemy;"), 34, NoteMark.NUMBER) == 1


def test_a_sign_skips_a_note_whose_marker_stood_for_a_number() -> None:
    # Made up after Kadesh's page 15: the reference to its first note,
    # whose marker reads "%", is lost, and the sign after "2,052" is the
    # second note's.
    notes = (
        NoteToMatch(0, 14, None, NoteMark.NUMBER),
        NoteToMatch(1, 14, None, NoteMark.SIGN),
        NoteToMatch(2, 14, None, NoteMark.SIGN),
    )
    links = match_footnotes(notes, _candidates((_sign("2,052"),)), note_score)
    assert [link.note for link in links] == [1]


def test_through_a_book_a_number_one_off_is_no_confused_reading() -> None:
    note = NoteToMatch(0, 60, 156, NoteMark.NUMBER)
    assert through_score(_glued("bottom", "155"), note) == 0
    assert note_score(_glued("bottom", "155"), note) == 2
    # Kadesh's page 40: "»aten108" is the reference to note 103.
    assert (
        through_score(_glued("»aten", "108"), NoteToMatch(0, 40, 103, NoteMark.SIGN))
        == 2
    )
    assert through_score(_glued("bottom", "156"), note) == 3


def test_through_a_book_a_reference_one_off_is_left_unlinked() -> None:
    # Made up after Kadesh's page 60: notes 154 to 157 read "184", "18",
    # "156" and "181"; "bottom155" is the reference to note 155.
    notes = tuple(
        NoteToMatch(place, 60, value, NoteMark.NUMBER)
        for place, value in enumerate((184, 18, 156, 181))
    )
    candidates = _candidates((_glued("bottom", "155"),))
    assert match_footnotes(notes, candidates, through_score) == ()


def _values(pages_and_values: tuple[tuple[int, int], ...]) -> tuple[NoteToMatch, ...]:
    return tuple(
        NoteToMatch(place, page, value, NoteMark.NUMBER)
        for place, (page, value) in enumerate(pages_and_values)
    )


def test_past_note_9_a_one_digit_value_is_dropped() -> None:
    # Made up after Kadesh: "1" and "2" on its first page of notes, "13"
    # on its third, then "4" for 14 after it, and "7" for note 78 and
    # "79" on a later page.
    notes = (
        NoteToMatch(0, 8, 1, NoteMark.SIGN),
        NoteToMatch(1, 8, 2, NoteMark.SIGN),
        NoteToMatch(2, 10, 13, NoteMark.SIGN),
        NoteToMatch(3, 10, 4, NoteMark.SIGN),
        NoteToMatch(4, 31, 7, NoteMark.SIGN),
        NoteToMatch(5, 31, 79, NoteMark.SIGN),
    )
    assert tuple(note.value for note in without_one_digit_values(notes)) == (
        1,
        2,
        13,
        None,
        None,
        79,
    )


def test_one_digit_values_stay_when_the_notes_start_again_each_chapter() -> None:
    # Made up: three chapters numbered 1 to 12 each, by marker, four notes
    # a page; the values of two digits rise in each chapter only.
    chapter = tuple(range(1, 13))
    notes = _values(
        tuple(
            (page, value)
            for start in (0, 3, 6)
            for page, value in zip(
                (start + place // 4 for place in range(12)), chapter, strict=True
            )
        )
    )
    assert without_one_digit_values(notes) == notes


def test_one_digit_values_stay_after_a_value_misread_early() -> None:
    # Made up: note 3 read "17" on the first page, the book's values
    # rising from 10 on its fourth.
    notes = _values(
        ((0, 1), (0, 2), (0, 17), (1, 4), (1, 5), (2, 6), (2, 7), (3, 8))
        + ((3, 9), (3, 10), (4, 11), (4, 12), (5, 13), (5, 14))
    )
    assert without_one_digit_values(notes) == notes
    # A one-digit value past the page where the rise starts is dropped.
    later = _values(((0, 1), (0, 2), (0, 17), (3, 10), (4, 11), (5, 7), (5, 13)))
    assert tuple(note.value for note in without_one_digit_values(later)) == (
        1,
        2,
        17,
        10,
        11,
        None,
        13,
    )


def _link(note: int, reference: Reference) -> Link:
    return Link(Candidate(0, note, 37, reference), note)


def test_a_sign_at_a_page_head_needs_the_second_note_linked() -> None:
    # Made up after Kadesh's page 37: the reference to note 90 is lost,
    # and the sign of note 91 took note 90.
    notes = tuple(NoteToMatch(place, 37, None, NoteMark.SIGN) for place in range(3))
    assert sure_through(notes, (_link(0, _sign("Amon?);")),)) == ()
    # Page 9: the signs of notes 4 and 5 confirm each other.
    both = (_link(0, _sign("Salvolini")), _link(1, _sign("Lenormant,")))
    assert sure_through(notes, both) == both
    # A page's only note keeps its sign; a glued number at the head stays.
    only = (NoteToMatch(0, 25, None, NoteMark.SIGN),)
    assert sure_through(only, (_link(0, _sign("made.")),)) == (
        _link(0, _sign("made.")),
    )
    glued = (_link(0, _glued("Kadesh,", "12")),)
    assert sure_through(notes, glued) == glued


def test_a_note_whose_head_sign_is_unlinked_may_take_a_lone_number() -> None:
    # Made up: the sign at the head of page 37 is unlinked, its second
    # note having no link; the lone "12." after "river" reads the first
    # note's value and links it, on the number read.
    notes = tuple(
        NoteToMatch(place, 37, value, NoteMark.NUMBER)
        for place, value in enumerate((12, 13))
    )
    links = sure_through(notes, (_link(0, _sign("Amon?);")),))
    assert links == ()
    words = (
        BodyWord(0, 0, 37, "the", "", "river"),
        BodyWord(0, 1, 37, "river", "the", "12."),
        BodyWord(0, 2, 37, "12.", "river", "Then"),
        BodyWord(0, 3, 37, "Then", "12.", ""),
    )
    assert [
        (link.note, link.candidate.word) for link in lone_links(notes, words, links)
    ] == [(0, 2)]


def _alphanumeric(text: str) -> str:
    return re.sub(r"\W", "", text).casefold()


def _alike(first: str, second: str) -> float:
    return difflib.SequenceMatcher(None, first, second).ratio()


# How alike galley's note opening must be to a note's opening in the
# reference transcription to be that note: galley's OCR misreads some
# ("Gox., Ham." for "Gol., Ham."); guessed, as in test_correct_links.py.
_LEAST_ALIKE = 0.6


def _printed(
    page: Mapping[str, Any], words_before: str, note_text: str
) -> tuple[str, str | None]:
    """The printed numbers of the reference whose words before it are most
    alike `words_before`, and of the note whose opening is most alike
    `note_text`, on a page of the reference transcription; None for the
    note when no opening is alike enough: galley's note is a piece of one,
    not its start."""
    by_context = {
        item["number"]: _alike(
            _alphanumeric(
                " ".join(words_before.split()[-len(item["context"].split()) :])
            ),
            _alphanumeric(item["context"]),
        )
        for item in page["references"]
    }
    by_note = {
        note["marker"]: _alike(
            _alphanumeric(note_text)[: len(_alphanumeric(note["starts"]))],
            _alphanumeric(note["starts"]),
        )
        for note in page["notes"]
    }
    reference = max(by_context, key=by_context.__getitem__)
    # Of openings equally alike ("LD., II, 138c" and "LD., II, 137c" against
    # "LD., Il, 13i¢"), the reference's own note when it is one of them.
    best = max(by_note.values())
    alike = [number for number, ratio in by_note.items() if ratio == best]
    note = reference if reference in alike else alike[0]
    return (str(reference), str(note) if best >= _LEAST_ALIKE else None)


def _links_on(
    folders: Mapping[str, BookFolder], book_page: int
) -> list[tuple[str, str | None]]:
    """The links to the footnotes that start on the whole book's page index
    `book_page`, each as the printed numbers of its reference and of its
    note."""
    name, first = next(
        (name, first)
        for name, first in sorted(
            _EXCERPT_FIRST_PAGES.items(), key=lambda item: -item[1]
        )
        if first <= book_page
    )
    blocks = read_blocks(folders[name].blocks_json)
    page = next(
        page
        for page in json.loads(_REFERENCE.read_text(encoding="utf-8"))["pages"]
        if page["page_index"] == book_page
    )
    notes = {
        note.id: " ".join(span.text for block in note.blocks for span in block.spans)
        for note in blocks.notes
        if note.origin[0].page_index == book_page - first
    }
    found = []
    for block in every_block(blocks):
        for place, span in enumerate(block.spans):
            if span.note_ref in notes:
                before = "".join(other.text for other in block.spans[:place])
                found.append(_printed(page, before, notes[span.note_ref]))
    return sorted(found, key=lambda pair: int(pair[0]))


@pytest.mark.tesseract
@pytest.mark.parametrize(
    ("book_page", "links"),
    [
        # The marker of note 31 read "1" took the page's order away: the
        # sign after "5,000.”" (32) went to note 30, and "gendarmes.80"
        # and "Sinai.31" to no note. The excerpt's layout cuts note 32's
        # second column into two notes of no marker, and the two signs go
        # to these, a part of note 32 and not the start of a note.
        (
            14,
            [
                ("27", "27"),
                ("28", "28"),
                ("30", "30"),
                ("31", "31"),
                ("32", None),
                ("33", None),
            ],
        ),
        # Note 34's reference is read "enemy;™", no candidate; the sign
        # after "2,052" went to note 34, whose marker reads "%".
        (15, [("35", "35")]),
        # "bottom155" went to note 156, one confused digit away.
        (60, []),
        # Notes 159 and 160 both read "1", and "Luxor1"" (163) went to
        # note 159.
        (61, [("165", "165")]),
        # Notes 4 to 6 by their signs, each confirmed by the next.
        (9, [("4", "4"), ("5", "5"), ("6", "6")]),
        # "river,"7*" (79) went to note 78, marked "7".
        (31, []),
        # The sign of note 91 went to note 90, whose reference "iter" is
        # lost.
        (37, []),
        # "Luxor."1" (172) went to note 173, marked "1".
        (63, []),
    ],
    ids=[
        "page_14",
        "page_15",
        "page_60",
        "page_61",
        "page_9",
        "page_31",
        "page_37",
        "page_63",
    ],
)
def test_kadesh_links_go_to_the_notes_their_references_print(
    kadesh_link_excerpts: frozendict[str, BookFolder],
    book_page: int,
    links: list[tuple[str, str | None]],
) -> None:
    assert _links_on(kadesh_link_excerpts, book_page) == links
