"""Tests of the printed table of contents in galley.structure
(docs/specs/structure.md, sections 30 and 32).

The unit tests write their lines by hand, in the layouts section 30's
table gives for Haynes', Turney's, Stubbs', Domesday's and Mariéjol's
contents; of the owner's books no more than a few words of a title are
used.
"""

from galley.model import Box, Line, RemovalReason, Word
from galley.structure._contents import (
    ContentsEntry,
    ContentsTitle,
    contents_entries,
    contents_title,
)
from galley.structure._lines import PlacedLine
from galley.structure._measures import Edges

_CHAR_PT = 5.0
_WORD_HEIGHT_PT = 10.0
_PITCH_PT = 14.0
_LEFT_PT = 60.0
_RIGHT_PT = 340.0
_EDGES = Edges(_LEFT_PT, _RIGHT_PT)


def _line(
    text: str, x0: float, top: float, x1: float | None = None, page_index: int = 0
) -> PlacedLine:
    """A line of `text` whose left side is `x0` and top `top`, its words 5
    pt a character with one character between them; its last word moved to
    end at `x1` when given, as a page number set at the column's edge."""
    words = []
    left = x0
    for part in text.split(" "):
        right = left + _CHAR_PT * len(part)
        words.append(Word(part, Box(left, top, right, top + _WORD_HEIGHT_PT), None))
        left = right + _CHAR_PT
    if x1 is not None:
        last = words[-1]
        width = last.box.x1 - last.box.x0
        words[-1] = Word(last.text, Box(x1 - width, top, x1, last.box.bottom), None)
    box = Box(x0, top, words[-1].box.x1, top + _WORD_HEIGHT_PT)
    return PlacedLine(page_index, Line(box, tuple(words)), _EDGES, _EDGES)


def _centred(text: str, top: float) -> PlacedLine:
    width = _CHAR_PT * len(text)
    return _line(text, (_LEFT_PT + _RIGHT_PT - width) / 2, top)


def _lines(*made: tuple[str, float, float | None]) -> tuple[PlacedLine, ...]:
    """Lines a pitch apart from top 100, each given by its text, left side
    and right side (None for its words' own)."""
    return tuple(
        _line(text, x0, 100 + number * _PITCH_PT, x1)
        for number, (text, x0, x1) in enumerate(made)
    )


def _summary(
    entries: tuple[ContentsEntry, ...],
) -> tuple[tuple[str | None, str, str | None, int], ...]:
    """Each entry's label, title, page number and depth."""
    return tuple(
        (
            entry.label,
            " ".join(word.text for line in entry.title for word in line.line.words),
            entry.page_number,
            entry.level,
        )
        for entry in entries
    )


def test_run_title_is_its_first_line_with_a_letter_after_stray_marks() -> None:
    # Stubbs' page 14: a speck read "—" above "CONTENTS".
    lines = (_centred("—", 80), _centred("CONTENTS", 100), _line("PREFACE", 60, 120))
    assert contents_title(lines) == ContentsTitle(stray_marks=(0,), title=1)


def test_first_line_that_ends_with_a_page_number_or_is_a_lone_label_is_no_title() -> (
    None
):
    with_number = (_line("Acknowledgments ix", 100, 100),)
    lone_label = (_centred("CHAPTER IX.", 100), _centred("THE REIGN OF JOHN.", 114))
    assert contents_title(with_number) == ContentsTitle(stray_marks=(), title=None)
    assert contents_title(lone_label) == ContentsTitle(stray_marks=(), title=None)


def test_haynes_layout_gives_one_line_entries_with_labels_and_page_numbers() -> None:
    # Haynes' page 8's layout, its titles made up: the numbers
    # right-aligned in a column of their own, the page number a space
    # after the title; the front and back matter have no number; a pencil
    # mark glued to a title; "3x3" a misread page number.
    lines = _lines(
        ("Acknowledgments ix", 100, None),
        ("Introduction 1", 100, None),
        ("(TjDark Chemists and Master Wagner 9", 92, None),
        ("2. Carver's New Engineers 23", 85, None),
        ("10. A Later Chapter 150", 80, None),
        ("Consequences 3x3", 100, None),
        ("Notes 317", 100, None),
    )
    assert _summary(contents_entries(lines)) == (
        (None, "Acknowledgments", "ix", 1),
        (None, "Introduction", "1", 1),
        (None, "(TjDark Chemists and Master Wagner", "9", 1),
        ("2.", "Carver's New Engineers", "23", 1),
        ("10.", "A Later Chapter", "150", 1),
        (None, "Consequences 3x3", None, 1),
        (None, "Notes", "317", 1),
    )


def test_turney_layout_runs_a_title_on_to_its_indented_second_line() -> None:
    # Turney's page 10: a spelled number, the title 42 pt to its right,
    # where its second line goes on.
    lines = _lines(
        ("One The Growth of Practical", 60, None),
        ("Geology 43", 102, None),
        ("Two A Second Title 61", 60, None),
    )
    assert _summary(contents_entries(lines)) == (
        ("One", "The Growth of Practical Geology", "43", 1),
        ("Two", "A Second Title", "61", 1),
    )


def _stubbs_lines() -> tuple[PlacedLine, ...]:
    """Stubbs' layout: "CHAPTER IX." and its title centred, then its
    topics separated by dashes with a hanging indent of 13 pt and the
    page number after leader dots at the column's edge; "Index" last."""
    return (
        _centred("CHAPTER IX.", 100),
        _centred("THE REIGN OF JOHN.", 114),
        _line("The loss of Normandy — the interdict — the", 60, 128, _RIGHT_PT),
        _line("charter — the war . . . . . 189", 73, 142, _RIGHT_PT),
        _centred("CHAPTER X.", 170),
        _centred("HENRY THE THIRD.", 184),
        _line("Index . . . . . . . . . . 291", 60, 212, _RIGHT_PT),
    )


def test_stubbs_layout_gives_chapters_of_depth_1_and_their_topics_of_depth_2() -> None:
    entries = contents_entries(_stubbs_lines())
    assert _summary(entries) == (
        ("CHAPTER IX.", "THE REIGN OF JOHN.", None, 1),
        (
            None,
            "The loss of Normandy — the interdict — the charter — the war",
            "189",
            2,
        ),
        ("CHAPTER X.", "HENRY THE THIRD.", None, 1),
        (None, "Index", "291", 1),
    )


def test_leader_dots_before_a_page_number_are_removed_one_removal_per_line() -> None:
    entries = contents_entries(_stubbs_lines())
    assert tuple(
        (removal.text, removal.reason)
        for entry in entries
        for removal in entry.leader_dots
    ) == (
        (". . . . .", RemovalReason.LEADER_DOTS),
        (". . . . . . . . . .", RemovalReason.LEADER_DOTS),
    )


def test_domesday_layout_gives_depths_1_to_3_and_keeps_a_summary_whole() -> None:
    # Domesday's pages 14 to 20: "ESSAY I." and its title centred, the
    # essay's topics as a paragraph with a page number after each topic,
    # each section centred with its range of pages, then its topics.
    lines = (
        _centred("ESSAY I.", 100),
        _centred("DOMESDAY BOOK.", 114),
        _line("Domesday Book and its satellites, 1. The Survey, 2.", 60, 128, 340),
        _line("The geld, 3. The hide and its parts, 5. The", 60, 142, 340),
        _line("manor, 7.", 60, 156),
        _centred("§ 1. Plan of the Survey, pp. 9 — 26.", 180),
        _line("The vill, 9. The hundred, 11. Free men,", 60, 194, 340),
        _line("13. Sokemen, 15.", 60, 208),
    )
    assert _summary(contents_entries(lines)) == (
        ("ESSAY I.", "DOMESDAY BOOK.", None, 1),
        (
            None,
            (
                "Domesday Book and its satellites, 1. The Survey, 2. The geld, 3. "
                "The hide and its parts, 5. The manor, 7."
            ),
            None,
            2,
        ),
        ("§ 1.", "Plan of the Survey,", "pp. 9 — 26.", 2),
        (None, "The vill, 9. The hundred, 11. Free men, 13. Sokemen, 15.", None, 3),
    )


def test_chapitre_11_over_a_title_is_one_entry_with_that_label_and_no_page() -> None:
    # Mariéjol's page 450: "CHAPITRE II", read "CHAPITRE 11", over its title.
    lines = (_centred("CHAPITRE 11", 100), _centred("DAUPHINE ET REINE", 114))
    assert _summary(contents_entries(lines)) == (
        ("CHAPITRE 11", "DAUPHINE ET REINE", None, 1),
    )


def test_lone_label_at_the_end_of_a_run_is_an_entry_with_an_empty_title() -> None:
    lines = (_line("PREFACE 1", 60, 100), _centred("CHAPTER XII.", 128))
    entries = contents_entries(lines)
    assert _summary(entries) == (
        (None, "PREFACE", "1", 1),
        ("CHAPTER XII.", "", None, 1),
    )
    assert entries[1].title == ()


def test_label_takes_the_marks_before_it_and_needs_a_word_after_it() -> None:
    # Haskins' page 14: "^ VI." with a pencil mark; "_ II," read with a
    # comma is no label.
    lines = _lines(
        ("^ VI. SICILY 189", 60, _RIGHT_PT),
        ("_ II, ENGLAND 23", 60, _RIGHT_PT),
        ("VII. 200", 60, _RIGHT_PT),
    )
    assert _summary(contents_entries(lines)) == (
        ("^ VI.", "SICILY", "189", 1),
        (None, "_ II, ENGLAND", "23", 1),
        (None, "VII.", "200", 1),
    )


def test_entry_keeps_every_line_for_its_origin_with_its_label_line() -> None:
    lines = (_centred("CHAPTER IX.", 100), _centred("THE REIGN OF JOHN.", 114))
    (entry,) = contents_entries(lines)
    assert entry.lines == lines
