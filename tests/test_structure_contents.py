"""Tests of the printed table of contents in galley.structure
(docs/specs/structure.md, sections 30 and 32).

The unit tests write their lines by hand, in the layouts section 30's
table gives for Haynes', Turney's, Stubbs', Domesday's and Mariéjol's
contents; of the owner's books no more than a few words of a title are
used.
"""

from collections.abc import Callable

import pytest

from galley.book_folder import BookFolder
from galley.errors import FidelityBoundary
from galley.fidelity import check_stage
from galley.model import (
    BlockKind,
    Box,
    Line,
    LinesFile,
    Origin,
    PageLayout,
    Region,
    RemovalReason,
    Word,
    block_text,
    read_blocks,
)
from galley.structure import make_blocks
from galley.structure._contents import (
    ContentsEntry,
    ContentsTitle,
    contents_entries,
    contents_title,
    is_link_candidate,
    run_links,
)
from galley.structure._lines import PlacedLine
from galley.structure._linking import body_candidates
from galley.structure._measures import Edges
from galley.structure._unnumbered import Unnumbered

_CHAR_PT = 5.0
_WORD_HEIGHT_PT = 10.0
_PITCH_PT = 14.0
_LEFT_PT = 60.0
_RIGHT_PT = 340.0
_EDGES = Edges(_LEFT_PT, _RIGHT_PT)


def _line(
    text: str,
    x0: float,
    top: float,
    x1: float | None = None,
    page_index: int = 0,
    apart: float = _CHAR_PT,
) -> PlacedLine:
    """A line of `text` whose left side is `x0` and top `top`, its words 5
    pt a character with one character between them, but `apart` pt before
    the last; its last word moved to end at `x1` when given, as a page
    number set at the column's edge."""
    words = []
    left = x0
    parts = text.split(" ")
    for number, part in enumerate(parts):
        if number == len(parts) - 1 and number > 0:
            left += apart - _CHAR_PT
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


def _lines(
    *made: tuple[str, float, float | None], apart: float = _CHAR_PT
) -> tuple[PlacedLine, ...]:
    """Lines a pitch apart from top 100, each given by its text, left side
    and right side (None for its words' own), `apart` pt before the last
    word of each."""
    return tuple(
        _line(text, x0, 100 + number * _PITCH_PT, x1, apart=apart)
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
        apart=12.0,
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


def test_number_ending_a_title_at_a_word_space_is_no_page_number() -> None:
    # Spec section 30, "Terms": a number at an ordinary space, short of the
    # column's edge, ends the title ("Psalm 23", "Maldon, 991", "mix").
    lines = _lines(
        ("The Battle of Maldon, 991 12", 60, _RIGHT_PT),
        ("Psalm 23", 60, None),
        ("A short title to mix", 60, None),
        ("The longest line of the page, set to its edge 40", 60, _RIGHT_PT),
    )
    assert tuple(
        (entry.page_number, " ".join(w.text for l in entry.title for w in l.line.words))
        for entry in contents_entries(lines)
    ) == (
        ("12", "The Battle of Maldon, 991"),
        (None, "Psalm 23"),
        (None, "A short title to mix"),
        ("40", "The longest line of the page, set to its edge"),
    )


def test_number_far_from_its_word_and_short_of_the_edge_is_no_page_number() -> None:
    # Gierke's page 54: a signature line "M. d", the "d" 254 pt right of
    # "M." and 18 pt short of the column's edge.
    lines = (
        _line("A topic of the summary that fills its line", 60, 100, _RIGHT_PT),
        _line("M. d", 60, 114, _RIGHT_PT - 18),
    )
    assert all(entry.page_number is None for entry in contents_entries(lines))


def test_number_after_leader_dots_is_a_page_number_wherever_it_ends() -> None:
    lines = (
        _line("PREFACE . . . . v", 60, 100),
        _line("The longest line of the page, set to its edge 1", 60, 114, _RIGHT_PT),
    )
    assert contents_entries(lines)[0].page_number == "v"


def test_turney_layout_runs_a_title_on_to_its_indented_second_line() -> None:
    # Turney's page 10: a spelled number, the title 42 pt to its right,
    # where its second line goes on.
    lines = _lines(
        ("One The Growth of Practical", 60, None),
        ("Geology 43", 102, None),
        ("Two A Second Title 61", 60, None),
        apart=14.0,
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


def test_summary_whose_references_mostly_end_their_lines_is_kept_whole() -> None:
    # Gierke's page 53: six lines, two inline references, the others at a
    # line's end or read "(n)"; one for every five lines makes a summary.
    lines = _lines(
        ("The postulate of an external unity of Mankind (10). Mankind", 60, 340),
        ("as a mystical body, Ecclesia universalis (10).", 60, 340),
        ("The divinely appointed severance of this body into two", 60, 340),
        ("the Spiritual and the Temporal (10). Each of these a", 60, 340),
        ("external realm (n). This dualism cannot be final, but", 60, 340),
        ("ciliation in some higher unity (n).", 60, None),
    )
    entries = contents_entries(lines)
    assert len(entries) == 1
    assert entries[0].topics
    assert entries[0].page_number is None


def test_chapitre_11_over_a_title_is_one_entry_with_that_label_and_no_page() -> None:
    # Mariéjol's page 450: "CHAPITRE II", read "CHAPITRE 11", over its title.
    lines = (_centred("CHAPITRE 11", 100), _centred("DAUPHINE ET REINE", 114))
    assert _summary(contents_entries(lines)) == (
        ("CHAPITRE 11", "DAUPHINE ET REINE", None, 1),
    )


def test_lone_label_at_the_end_of_a_run_is_an_entry_with_an_empty_title() -> None:
    lines = (_line("PREFACE 1", 60, 100, apart=12.0), _centred("CHAPTER XII.", 128))
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


# The links (spec section 30, rule 9).


def test_titles_are_compared_case_folded_as_letters_with_single_spaces() -> None:
    # Spec section 30, rule 9: the plain texts are equal.
    assert run_links(
        (" (TjDark Chemists,  and-Master ",), ("tjdark CHEMISTS and master",)
    ) == ((0, 0),)


def test_entries_link_to_their_headings_in_order() -> None:
    assert run_links(
        ("(TjDark Chemists and Master Wagner", "EDWARD I.", "EDWARD II."),
        ("DARK CHEMISTS AMD MASTER WAGNER", "EDWARD I.", "EDWARD II."),
    ) == ((0, 0), (1, 1), (2, 2))


def test_entry_with_no_heading_alike_has_no_link() -> None:
    assert run_links(
        ("EDWARD I.", "STATISTICAL TABLES", "EDWARD II."),
        ("EDWARD I.", "EDWARD II."),
    ) == ((0, 0), (2, 1))


def test_two_entries_in_the_order_opposite_to_their_headings_give_one_link() -> None:
    links = run_links(
        ("THE CHURCH AND THE STATE", "THE NORMAN CONQUEST"),
        ("THE NORMAN CONQUEST", "THE CHURCH AND THE STATE"),
    )
    assert len(links) == 1


def test_link_goes_to_the_earlier_of_two_headings_alike() -> None:
    # Among sets of one size and sum, the first candidate whose pairing
    # differs takes the earlier heading.
    assert run_links(("INDEX",), ("INDEX", "INDEX")) == ((0, 0),)


def test_ratio_below_the_threshold_gives_no_link() -> None:
    # "TRANSLATOR'S INTRODUCTION" against "INTRODUCTION." is 0.65.
    assert run_links(("TRANSLATOR'S INTRODUCTION",), ("INTRODUCTION.",)) == ()


# The blocks (spec section 30, rule 10), through make_blocks.

_NO_WORDS: frozenset[str] = frozenset()


def _region_of(*lines: PlacedLine) -> Region:
    raw = tuple(line.line for line in lines)
    return Region(
        Box(
            min(line.box.x0 for line in raw),
            min(line.box.top for line in raw),
            max(line.box.x1 for line in raw),
            max(line.box.bottom for line in raw),
        ),
        raw,
    )


def _text_page(index: int, heading: str) -> PageLayout:
    """A chapter's first page: its centred heading and five full lines."""
    return PageLayout(
        index,
        (
            _region_of(
                _centred(heading, 100),
                *(
                    _line(f"Text of the chapter {n} goes on", 60, 140 + 14 * n, 340)
                    for n in range(5)
                ),
            ),
        ),
        (),
    )


def _contents_book() -> LinesFile:
    contents = PageLayout(
        0,
        (
            _region_of(
                _centred("CONTENTS", 60),
                _line("PREFACE . . . . . . . v", 60, 100, _RIGHT_PT),
                _line("I. THE NORMAN CONQUEST . . . 1", 60, 114, _RIGHT_PT),
                _line("II. THE CHURCH AND THE STATE . . 23", 60, 128, _RIGHT_PT),
                _line("INDEX . . . . . . . . . 301", 60, 142, _RIGHT_PT),
            ),
        ),
        (),
    )
    return LinesFile(
        source_pdf_sha256="0" * 64,
        rereads=(),
        pages=(
            contents,
            _text_page(1, "THE NORMAN CONQUEST."),
            _text_page(2, "THE CHURCH AND THE STATE."),
        ),
    )


def test_contents_page_gives_its_title_a_heading_and_entries_linked() -> None:
    lines = _contents_book()
    blocks = make_blocks(lines, _NO_WORDS, contents_pages=frozenset({0}), workers=1)
    headings = {
        block.id: block_text(block)
        for block in blocks.blocks
        if block.kind is BlockKind.HEADING
    }
    assert tuple(
        (
            block.kind.value,
            block.level,
            block.label,
            block_text(block),
            block.page_number,
            headings.get(block.heading_ref or ""),
        )
        for block in blocks.blocks
        if block.origin[0].page_index == 0
    ) == (
        ("heading", 1, None, "CONTENTS", None, None),
        ("contents_entry", 1, None, "PREFACE", "v", None),
        ("contents_entry", 1, "I.", "THE NORMAN CONQUEST", "1", "THE NORMAN CONQUEST."),
        (
            "contents_entry",
            1,
            "II.",
            "THE CHURCH AND THE STATE",
            "23",
            "THE CHURCH AND THE STATE.",
        ),
        ("contents_entry", 1, None, "INDEX", "301", None),
    )
    assert (
        sum(removal.reason is RemovalReason.LEADER_DOTS for removal in blocks.removals)
        == 4
    )
    check_stage(FidelityBoundary.STRUCTURE, lines, blocks)


def test_paragraph_after_a_contents_page_starts_a_block() -> None:
    blocks = make_blocks(
        _contents_book(), _NO_WORDS, contents_pages=frozenset({0}), workers=1
    )
    assert blocks.blocks[5].origin[0].page_index == 1
    assert blocks.blocks[5].kind is BlockKind.HEADING


# The whole books (spec section 32, "Whole-book tests"): contents entries
# linked to a heading, as section 30's table gives them at 0.7 (Gierke's
# two runs 5 and 10).
_LINKED = {
    "normansineuropea00hask": 9,
    "earlyplantagenet01stub": 13,
    "domesdaybook00maituoft": 24,
    "politicaltheorie00gieruoft": 15,
}


@pytest.mark.whole_book
@pytest.mark.timeout(900)
@pytest.mark.parametrize("book", list(_LINKED))
def test_whole_book_contents_entries_linked_to_headings(
    whole_book_run: Callable[[str], BookFolder], book: str
) -> None:
    blocks = read_blocks(whole_book_run(book).blocks_json)
    headings = frozenset(b.id for b in blocks.blocks if b.kind is BlockKind.HEADING)
    refs = tuple(
        block.heading_ref
        for block in blocks.blocks
        if block.kind is BlockKind.CONTENTS_ENTRY and block.heading_ref is not None
    )
    assert len(refs) == _LINKED[book]
    assert all(ref in headings for ref in refs)


# The excerpts (spec section 32, "Excerpt tests").


def _contents_of(
    excerpt_books: frozendict[str, BookFolder], name: str, page: int
) -> tuple[tuple[str, int | None, str | None, str, str | None, str | None], ...]:
    """The headings and contents entries that start on excerpt page `page`:
    kind, level, label, text, page number and the text of the heading the
    entry is linked to."""
    blocks = read_blocks(excerpt_books[name].blocks_json)
    texts = {block.id: block_text(block) for block in blocks.blocks}
    return tuple(
        (
            block.kind.value,
            block.level,
            block.label,
            block_text(block),
            block.page_number,
            texts[block.heading_ref] if block.heading_ref is not None else None,
        )
        for block in blocks.blocks
        if block.origin[0].page_index == page
        and block.kind in {BlockKind.HEADING, BlockKind.CONTENTS_ENTRY}
    )


def test_haskins_front_contents_title_and_nine_entries(
    excerpt_books: frozendict[str, BookFolder],
) -> None:
    # Excerpt page 7 is the book's page 14. None is linked: chapter I's
    # heading holds the half-title in the excerpt (spec section 32).
    assert _contents_of(excerpt_books, "haskins_front", 7) == (
        ("heading", 1, None, "CONTENTS", None, None),
        _entry(1, None, "-^1. NORMANDY AND ITS PLACE IN HISTORY", "i"),
        _entry(1, None, "_ II, THE COMING OF THE NORTHMEN", "26"),
        _entry(1, None, '"HI. NORMANDY AND ENGLAND', "52"),
        _entry(1, "IV.", "THE NORMAN EMPIRE", "85"),
        _entry(1, "V.", "NORMANDY AND FRANCE", "116"),
        _entry(1, "^ VI.", "NORMAN LIFE AND CULTURE", "148"),
        _entry(1, "VII.", "THE NORMANS IN THE SOUTH", "192"),
        _entry(1, "VIII.", "THE NORMAN KINGDOM OF SICILY", "218"),
        _entry(1, None, "INDEX", "251"),
    )


def _entry(
    level: int,
    label: str | None,
    title: str,
    page_number: str | None,
    heading: str | None = None,
) -> tuple[str, int | None, str | None, str, str | None, str | None]:
    return ("contents_entry", level, label, title, page_number, heading)


def test_stubbs_summaries_contents_chapters_topics_and_index_linked(
    excerpt_books: frozendict[str, BookFolder],
) -> None:
    # The title is page 16's running head, which the excerpt keeps.
    assert _contents_of(excerpt_books, "stubbs_summaries_index", 0) == (
        ("heading", 1, None, "Contents. vn", None, None),
        _entry(1, "CHAPTER IX.", "SIMON DE MONTFORT.", None),
        _entry(
            2,
            None,
            "Ltelay of the Crisis — Simon de Montfort — Parliament of 1258 "
            "Provisions of Oxford — Political troubles — Award of St. Lewis — "
            "Battle of Lewes — Baronial government — Battle of Evesham —Closing "
            "years . Page",
            "189",
        ),
        _entry(1, "CHAPTER X.", "EDWARD I.", None),
        _entry(
            2,
            None,
            "Position and character of Edward — The Crusade — The accession — "
            "The conquest of Wales — Edward's legal reforms — Financial system "
            "— Growth of Parliament",
            "212",
        ),
        _entry(1, "CHAPTER XI.", "THE CONFIRMATION OF THE CHARTERS.", None),
        _entry(
            2,
            None,
            "Punishment of the Judges — Banishment of the Jews — Scottish "
            "succession — The French quarrel — The Ecclesiastical quarrel — The "
            "Constitutional crisis — The Confirmation of the Charters — "
            "Parliament of Lincoln — Its sequel — War of Scottish Independence "
            "— Edward's death",
            "238",
        ),
        _entry(1, "CHAPTER XII.", "EDWARD II.", None),
        _entry(
            2,
            None,
            "Character of Edward II. — Piers Gaveston — The Ordinances — Thomas "
            "of Lancaster — The Despensers — The King's ruin anil death.",
            "263",
        ),
        _entry(1, None, "Index", "291", "INDEX."),
    )


def test_domesday_headings_contents_essay_sections_and_their_topics(
    excerpt_books: frozendict[str, BookFolder],
) -> None:
    assert _contents_of(excerpt_books, "domesday_headings_quotes", 0) == (
        ("heading", 1, None, "CONTENTS,", None, None),
        _entry(1, None, "PAGE", None),
        _entry(1, None, "PREFACE *.", "v"),
        _entry(1, None, "TABLE OF CONTEXTS", "vii"),
        _entry(1, None, "LIST OF ABBREVIATIONS", "xiv"),
        _entry(1, "ESSAY I.", "DOMESDAY BOOK.", None, "DOMESDAY BOOK."),
        _entry(
            2,
            None,
            "Domesday Book and its satellites, 1. Domesday and legal history, 2. "
            "Domesday a geld book,. 3. The danegeld, 3. The inquest and the geld "
            "system, 5. Importance of the geld, 7. Unstable terminology of the "
            "record, 8. The legal ideas of century xi. 9.",
            None,
        ),
        _entry(
            2, "§ 1.", "Plan of the Survey,", "pp. 9 — 26.", "§ 1. Plan of the Survey."
        ),
        _entry(
            3,
            None,
            "The geographical basis, 9. The vill as the unit, 10. Modern and "
            "ancient vills, 12. Omission of vills, 13. Fission of vills, 14. The "
            "nucleated village and the vill of scattered steads, 15. Illustration "
            "by maps, 16. Size of the vill, 17. Population of the vill, 19. "
            "Contrasts between east and west, 20. Small vills, 20. Importance of "
            "the east, 21. Manorial and non-manorial vills, 22. Distribution of "
            "free men and serfs, 23. The classification of men, 23. The classes "
            "of men and the geld system, 24. Our course, 25.",
            None,
        ),
        _entry(2, "§ 2.", "The Serfs,", "pp. 26—36."),
        _entry(
            3,
            None,
            "The servus of Domesday, 26. Legal position of the serf, 27. Degrees "
            "of serfdom, 27. Predial element in serfdom, 28. The serf and "
            "criminal law, 29. Serf and villein, 30. The serf of the Leges, 30. "
            "Return to the servus of Domesday, 33. Disappearance of servi, 35.",
            None,
        ),
        _entry(2, "§ 3.", "The Villeins,", "pp. 36—66."),
        _entry(
            3,
            None,
            "The boors or coliberts, 36. The continental colibert, 37. The "
            "English boor, 37. Villani, bordarii, cotarii, 38. The villein's "
            "tenement, 40. Villeins and cottiers, 41. Freedom and unfreedom of "
            "the villani, 41. Meaning of freedom, 42. The villein as free, 43. "
            "The villein as",
            None,
        ),
    )


def test_gierke_front_contents_page_numbers_taken_and_misread_ones_left(
    excerpt_books: frozendict[str, BookFolder],
) -> None:
    # Excerpt page 5 is the book's page 10: the misread page numbers stay in
    # their titles with their dots, and no entry is linked.
    assert _contents_of(excerpt_books, "gierke_front_flow", 5) == (
        ("heading", 1, None, "CONTENTS.", None, None),
        _entry(1, None, "PA'.R", None),
        _entry(1, None, "TRANSLATOR'S INTRODUCTION", "vii"),
        _entry(1, None, "ANALYTICAL SUMMARY", "xlvii"),
        _entry(1, None, "SUBJECT MATTER OF THE NOTES . .... Ivi", None),
        _entry(1, None, "LIST OF AUTHORITIES ... .... Ixiii", None),
        _entry(1, None, "INDEX TO LIST OF AUTHORITIES Ixxviii", None),
        _entry(1, None, "POLITICAL THEORIES OF THE MIDDLE AGE", "i"),
        _entry(1, None, "NOTES . . • lor", None),
    )


def test_contents_entry_is_not_searched_for_note_references() -> None:
    # Spec section 30, rule 10, as an index entry (section 17, rule 4): a
    # pencil mark glued to a title is no note reference.
    def block(kind: BlockKind) -> Unnumbered:
        return Unnumbered(
            kind=kind,
            words=("NORMANDY,^", "AND", "FRANCE"),
            word_pages=(0, 0, 0),
            origin=(Origin(0, Box(50, 300, 300, 307)),),
            changes=(),
            level=1 if kind is BlockKind.CONTENTS_ENTRY else None,
        )

    assert len(body_candidates((block(BlockKind.PARAGRAPH),))) == 1
    assert body_candidates((block(BlockKind.CONTENTS_ENTRY),)) == ()


def test_titles_alike_at_a_ratio_between_0_7_and_0_8_are_linked() -> None:
    # Mariéjol's misread title against its heading, 0.75.
    assert run_links(
        ("I A jeuiMaM d« Catherine de Médid». .",),
        ("LA JEUNESSE DE CATHERINE DE MÉDICIS",),
    ) == ((0, 0),)


def test_title_of_fewer_than_4_letters_is_no_candidate() -> None:
    assert not is_link_candidate("A B C")
    assert is_link_candidate("A B C D")


def test_topics_entry_is_never_linked_though_a_heading_reads_alike() -> None:
    topics = "THE KING — THE CHURCH — THE STATE"
    contents = PageLayout(
        0,
        (
            _region_of(
                _centred("CONTENTS", 60),
                _line("THE KING — THE CHURCH — THE", 60, 100, _RIGHT_PT),
                _line("STATE . . . . . . . . . 5", 73, 114, _RIGHT_PT),
            ),
        ),
        (),
    )
    lines = LinesFile(
        source_pdf_sha256="0" * 64,
        rereads=(),
        pages=(contents, _text_page(1, topics)),
    )
    blocks = make_blocks(lines, _NO_WORDS, contents_pages=frozenset({0}), workers=1)
    (entry,) = (b for b in blocks.blocks if b.kind is BlockKind.CONTENTS_ENTRY)
    assert block_text(entry) == topics
    assert entry.level == 1
    assert any(
        b.kind is BlockKind.HEADING and block_text(b) == topics for b in blocks.blocks
    )
    assert entry.heading_ref is None


def test_entry_of_fewer_than_4_letters_is_not_linked_to_a_heading_alike() -> None:
    # "IND" and "INDE" match at 0.86, but a candidate needs 4 letters.
    contents = PageLayout(
        0,
        (
            _region_of(
                _centred("CONTENTS", 60),
                _line("IND . . . . . . . . . . . 5", 60, 100, _RIGHT_PT),
                _line("SECOND ENTRY . . . . . . 9", 60, 114, _RIGHT_PT),
            ),
        ),
        (),
    )
    lines = LinesFile(
        source_pdf_sha256="0" * 64,
        rereads=(),
        pages=(contents, _text_page(1, "INDE")),
    )
    blocks = make_blocks(lines, _NO_WORDS, contents_pages=frozenset({0}), workers=1)
    entry = next(b for b in blocks.blocks if b.kind is BlockKind.CONTENTS_ENTRY)
    assert block_text(entry) == "IND"
    assert any(
        b.kind is BlockKind.HEADING and block_text(b) == "INDE" for b in blocks.blocks
    )
    assert entry.heading_ref is None
