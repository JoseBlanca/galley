"""Tests of the rules of docs/specs/correct.md, section 7, that the judged
edits of 25 November 2026 made (plan misread-words, work package 3), on
synthetic pages and the model's answers written for them. The owner's
books' cases are described in the spec in words; the words here are made
up or from public-domain books."""

import pytest

from galley.correct import edits_of, token_cores
from galley.correct._merge import WordList, answer, page_changes
from galley.correct._reading import page_reading
from galley.model import (
    Block,
    BlockKind,
    BlocksFile,
    Box,
    Emphasis,
    Note,
    NoteKind,
    Origin,
    Span,
)

MODEL = "qwen/qwen3.6-35b-a3b"
_BODY = (Origin(1, Box(60, 100, 460, 300)),)
_NOTES = (Origin(1, Box(60, 400, 460, 500)),)


def _block(
    block_id: str,
    *spans: Span,
    kind: BlockKind = BlockKind.PARAGRAPH,
    origin: tuple[Origin, ...] = _BODY,
) -> Block:
    return Block(
        id=block_id,
        kind=kind,
        level=None,
        label=None,
        spans=spans,
        figure=None,
        origin=origin,
    )


def _text(text: str, note_ref: str | None = None) -> Span:
    return Span(text, Emphasis.NONE, note_ref)


def _page(*blocks: Block, notes: tuple[Note, ...] = ()) -> BlocksFile:
    return BlocksFile(
        source_pdf_sha256="a" * 64,
        blocks=blocks,
        notes=notes,
        removals=(),
        word_changes=(),
        page_numbers=(),
    )


# A few words of a word list, in the list's case, for the guards of a merge.
_WORDS = WordList.of(
    frozenset(
        {
            "I",
            "i",
            "a",
            "x",
            "It",
            "it",
            "the",
            "body",
            "elected",
            "of",
            "there",
            "by",
            "thereby",
        }
    )
)


def _edits(
    blocks: BlocksFile, raw: str, words: WordList = _WORDS
) -> list[tuple[str, str]]:
    reading = page_reading(blocks, 1, {})
    changes = page_changes(
        1, reading, answer(raw), token_cores(blocks, reading), known_words=words
    )
    return [(edit.old, edit.new) for edit in edits_of(blocks, changes, MODEL)]


# An index entry (section 7).


def _index(*entries: str) -> BlocksFile:
    return _page(
        *(
            _block(
                f"b-p0001-{position:03d}",
                _text(entry),
                kind=BlockKind.INDEX_ENTRY,
                origin=(
                    Origin(1, Box(60, 100 + 12 * position, 260, 110 + 12 * position)),
                ),
            )
            for position, entry in enumerate(entries, 1)
        )
    )


@pytest.mark.parametrize(
    ("entries", "raw", "expected"),
    [
        # A name of another line, 0.43 alike: an edit in a paragraph.
        (("Kheta, 12, 40", "Khattusil, 7"), "Khattusil, 12, 40 Kheta, 7", []),
        # A page number of another line, a digit changed.
        (("Kadesh, 125, 130",), "Kadesh, 115, 130", []),
        # A misread "n." and an "o" read for a zero: galley's digits kept.
        (
            ("Kadesh, 12on., 37*.",),
            "Kadesh, 120n., 37n.",
            [
                ("12on.,", "120n.,"),
                ("37*.", "37n."),
            ],
        ),
        # A misread letter, 0.8 alike.
        (("Rarnses II, 4",), "Ramses II, 4", [("Rarnses", "Ramses")]),
    ],
    ids=["name", "number", "kept_digits", "letter"],
)
def test_an_index_entry_takes_only_close_edits_that_keep_its_digits(
    entries: tuple[str, ...], raw: str, expected: list[tuple[str, str]]
) -> None:
    assert _edits(_index(*entries), raw) == expected


def test_the_same_pairs_in_a_paragraph_are_edited() -> None:
    blocks = _page(_block("b-p0001-001", _text("Kheta, 125, 130")))
    assert _edits(blocks, "Khattusil, 115, 130") == [
        ("Kheta,", "Khattusil,"),
        ("125,", "115,"),
    ]


# A neighbour's word repeated (section 7).


def _note(note_id: str, marker: str, text: str, top: float) -> Note:
    origin = (Origin(1, Box(60, top, 460, top + 10)),)
    return Note(
        id=note_id,
        kind=NoteKind.FOOTNOTE,
        marker=marker,
        blocks=(_block(f"b-{note_id}", _text(text), origin=origin),),
        origin=origin,
        referenced=False,
    )


@pytest.mark.parametrize(
    ("spans", "raw"),
    [
        # Kadesh page 27: "wavy-" ends the line, the model printed it again
        # before the whole word.
        ((_text("the wavy- lined bands"),), "the wavy\nwavy-\nlined bands"),
        # An em dash read as a hyphen: the word after it, then before it.
        ((_text("the city—Kadesh lay"),), "the city-Kadesh lay"),
        ((_text("the city—Kadesh lay"),), "the cxty-Kadesh lay"),
        # The end of a page range printed again after itself.
        ((_text("see pp. 36\u20147. here"),), "see pp. 36\u20137\u20147. here"),
        # A number printed again before itself.
        ((_text("vol. 12: 125 here"),), "vol. 12: 12:125 here"),
        # A note reference glued to the number before it.
        (
            (_text("in 1885,"), _text("13", "n-p0001-001"), _text(" the war")),
            "in 1885,13 the war",
        ),
    ],
    ids=[
        "line_end_half",
        "after_dash",
        "before_dash",
        "range_end",
        "number",
        "note_reference",
    ],
)
def test_a_replacement_that_repeats_a_neighbouring_word_is_refused(
    spans: tuple[Span, ...], raw: str
) -> None:
    assert _edits(_page(_block("b-p0001-001", *spans)), raw) == []


def test_a_replacement_beside_an_unrepeated_neighbour_is_made() -> None:
    blocks = _page(_block("b-p0001-001", _text("the city—Kadcsh lay")))
    assert _edits(blocks, "the city—Kadesh lay") == [("city—Kadcsh", "city—Kadesh")]


def test_letters_the_word_beside_already_holds_are_not_put_in() -> None:
    notes = (
        _note(
            "n-p0001-001", "1", "Called K\u00b7A\u00b7D\u00b7E\u00b7S\u00b7H. here", 400
        ),
        _note("n-p0001-002", "2", "Struggle of Nations.", 420),
    )
    blocks = _page(_block("b-p0001-001", _text("The poem")), notes=notes)
    raw = "The poem\n1 Called K\u00b7A\u00b7D\u00b7E\u00b7S\u00b7H. E S H here\n2 Struggle of the Nations."
    assert _edits(blocks, raw) == [("of", "of the")]


def test_one_letter_the_word_beside_holds_is_put_in() -> None:
    # The excerpt kadesh_redo, page 1: "à" after "appartenant".
    notes = (
        _note("n-p0001-001", "1", "un nom appartenant le roi", 400),
        _note("n-p0001-002", "2", "Struggle of Nations.", 420),
    )
    blocks = _page(_block("b-p0001-001", _text("The poem")), notes=notes)
    raw = "The poem\n1 un nom appartenant \u00e0 le roi\n2 Struggle of Nations."
    assert _edits(blocks, raw) == [("appartenant", "appartenant \u00e0")]


# A piece of galley's word (section 7).


@pytest.mark.parametrize(
    ("galley", "raw"),
    [
        # Kadesh page 8: the word without its last letters.
        ("of orientalists and", "of orientalis and"),
        # A first half the answer did not join: its next line starts with
        # no lower-case letter.
        ("the publication. Then", "the publi-\nThen"),
        # A second half alone, at a column break.
        ("the habitation was", "the tation was"),
    ],
    ids=["last_letters", "first_half", "second_half"],
)
def test_a_model_word_that_is_a_piece_of_galleys_is_refused(
    galley: str, raw: str
) -> None:
    assert _edits(_page(_block("b-p0001-001", _text(galley))), raw) == []


@pytest.mark.parametrize(
    ("galley", "raw", "expected"),
    [
        ("of Rarnses and", "of Ramses and", ("Rarnses", "Ramses")),
        # A stray letter before a word (the excerpt kadesh_redo, page 7).
        ("as tof the", "as of the", ("tof", "of")),
    ],
    ids=["not_a_piece", "one_character_shorter"],
)
def test_a_model_word_that_is_no_piece_is_made(
    galley: str, raw: str, expected: tuple[str, str]
) -> None:
    blocks = _page(_block("b-p0001-001", _text(galley)))
    assert _edits(blocks, raw) == [expected]


@pytest.mark.parametrize(
    ("entry", "raw"),
    [
        # Haskins' index (normansineuropea00hask, pages 268 to 273).
        ("Sicily, 73, 90", "Sicily, 72-83, 90"),
        ("Sicily, 116, 90", "Sicily, 11-16, 90"),
        ("Sicily, 10. here", "Sicily, 160. here"),
    ],
    ids=["range_for_number", "range_for_digits", "digit_added"],
)
def test_an_index_entry_takes_no_edit_that_adds_digits(entry: str, raw: str) -> None:
    assert _edits(_index(entry), raw) == []


# Two of galley's words for one printed word (section 7).


@pytest.mark.parametrize(
    ("galley", "raw", "expected"),
    [
        # Domesday page 29: the page prints "It,".
        (
            "colibertus, hospes. I i, is not in twenty years",
            "colibertus, hospes. It, is not in twenty years",
            [("I i,", "It,")],
        ),
        # A word split at a gap in its letters.
        ("of Ram ses, the", "of Ramses, the", [("Ram ses,", "Ramses,")]),
        ("of Rarn ses, the", "of Ramses, the", []),
        # A stray "a" beside a misread word: "a" may be a printed word.
        ("in a hous here", "in house here", [("hous", "house")]),
    ],
    ids=["two_letters", "joined", "joined_unlike", "stray_letter"],
)
def test_two_galley_words_for_one_printed_word_are_replaced_together(
    galley: str, raw: str, expected: list[tuple[str, str]]
) -> None:
    assert _edits(_page(_block("b-p0001-001", _text(galley))), raw) == expected


# An insertion's tokens without a letter (section 7).


def test_an_insertion_leaves_out_tokens_without_a_letter() -> None:
    # Kadesh page 33: "4:G" got "1/2" after it.
    notes = (
        _note("n-p0001-001", "1", "At 4:G the march", 400),
        _note("n-p0001-002", "2", "Struggle of Nations.", 420),
    )
    blocks = _page(_block("b-p0001-001", _text("The poem")), notes=notes)
    raw = "The poem\n1 At 4:G 1/2 the march\n2 Struggle of the Nations."
    assert _edits(blocks, raw) == [("of", "of the")]


# A word of another line (section 7).


@pytest.mark.parametrize(
    ("galley", "raw", "expected"),
    [
        # Stubbs page 87: "Chancellor" is printed on the line below.
        (
            "on his accession, he was made Chancellor of the realm",
            "on his Chancellor, he was made Chancellor of the realm",
            [],
        ),
        # The same pair with the long word printed nowhere near: kept.
        (
            "on his accession, he was made keeper of the realm",
            "on his Chancellor, he was made keeper of the realm",
            [("accession,", "Chancellor,")],
        ),
        # A short word printed nearby (Stubbs: "foe" for "the").
        (
            "and foe king was the lord",
            "and the king was the lord",
            [("foe", "the")],
        ),
    ],
    ids=["long_word_nearby", "long_word_elsewhere", "short_word_nearby"],
)
def test_a_long_word_of_a_nearby_line_is_refused(
    galley: str, raw: str, expected: list[tuple[str, str]]
) -> None:
    assert _edits(_page(_block("b-p0001-001", _text(galley))), raw) == expected


@pytest.mark.parametrize(
    ("galley", "raw", "expected"),
    [
        # Two one-letter words: "a" would be lost.
        ("hospes. I a, is not", "hospes. It, is not", []),
        # Stubbs page 167: a dash at a line end read as a hyphen.
        ("of the body elected the", "of the body-\nelected the", []),
        # Two words whose join is a word: merged.
        ("and there by the", "and there-\nby the", [("there by", "thereby")]),
        # A half that is no word: merged.
        (
            "was recog nized the",
            "was recog-\nnized the",
            [("recog nized", "recognized")],
        ),
        # A word printed elsewhere in the book, missing from the list.
        (
            "the per ishing kings",
            "the per-\nishing kings",
            [("per ishing", "perishing")],
        ),
        # Not joined at a line end: the second guard does not apply.
        (
            "of the body elected the",
            "of the bodyelected the",
            [("body elected", "bodyelected")],
        ),
    ],
    ids=[
        "one_letter_words",
        "line_end_words",
        "joined_word",
        "broken_word",
        "printed_elsewhere",
        "no_line_end",
    ],
)
def test_a_merge_does_not_glue_two_printed_words(
    galley: str, raw: str, expected: list[tuple[str, str]]
) -> None:
    assert _edits(_page(_block("b-p0001-001", _text(galley))), raw) == expected


def test_a_merge_never_takes_tokens_of_two_blocks() -> None:
    # A paragraph runs from page 0 to page 1; on page 1 its first token
    # follows the last token of another block in galley's reading. The
    # two are not one printed word: a merge across them deleted words.
    running = _block(
        "b-p0000-001",
        _text("the great Ram ses was here"),
        origin=(Origin(0, Box(60, 600, 460, 700)), Origin(1, Box(60, 100, 460, 200))),
    )
    heading = _block(
        "b-p0001-002", _text("in Egypt Ram"), origin=(Origin(1, Box(60, 50, 460, 60)),)
    )
    blocks = _page(running, heading)
    reading = page_reading(blocks, 1, {"b-p0000-001": (3, 3)})
    assert [token.form for token in reading] == [
        "in",
        "egypt",
        "ram",
        "ses",
        "was",
        "here",
    ]
    changes = page_changes(
        1,
        reading,
        answer("in Egypt Ramses was here"),
        token_cores(blocks, reading),
        known_words=_WORDS,
    )
    assert [(edit.old, edit.new) for edit in edits_of(blocks, changes, MODEL)] == []


def test_a_token_is_merged_once() -> None:
    # Two merges could each take the middle token: the first one wins.
    blocks = _page(_block("b-p0001-001", _text("of Ram ses tes here")))
    assert _edits(blocks, "of Ramses sestes here") == [("Ram ses", "Ramses")]


# The limits of the rules, each at its edge.


@pytest.mark.parametrize(
    ("entry", "raw", "expected"),
    [
        # 0.6 alike: kept.
        ("Tyrxq, 4", "Tyrus, 4", [("Tyrxq,", "Tyrus,")]),
        # 0.57 alike: refused.
        ("Sex, 4", "Sesh, 4", []),
    ],
    ids=["at_limit", "below_limit"],
)
def test_an_index_entry_takes_edits_0_6_alike_or_more(
    entry: str, raw: str, expected: list[tuple[str, str]]
) -> None:
    assert _edits(_index(entry), raw) == expected


def test_a_merge_in_an_index_entry_is_checked_on_both_cores() -> None:
    # Haskins' "11 56" in an index entry: the two cores joined keep their
    # digits; the second alone would have digits added.
    assert _edits(_index("Bohemond, 11 56, 90"), "Bohemond, 1156, 90") == [
        ("11 56,", "1156,")
    ]


@pytest.mark.parametrize(
    ("galley", "raw", "expected"),
    [
        # A neighbour of two letters before galley's word, beyond a dash.
        ("we go—to here", "we go-to here", []),
        # One letter after galley's word is no neighbour repeated.
        ("the II I here", "the III I here", [("II", "III")]),
        # Nor one letter before it.
        ("the I II here", "the I III here", [("II", "III")]),
    ],
    ids=["two_letters_before", "one_letter_after", "one_letter_before"],
)
def test_a_neighbour_repeated_is_two_characters_or_more(
    galley: str, raw: str, expected: list[tuple[str, str]]
) -> None:
    assert _edits(_page(_block("b-p0001-001", _text(galley))), raw) == expected


def test_the_second_half_of_a_line_end_word_is_no_neighbour_repeated() -> None:
    # The first half is covered by the replacement: the rule of a
    # neighbour repeated does not apply to it.
    blocks = _page(_block("b-p0001-001", _text("such cam- paigns was")))
    assert _edits(blocks, "such cam-\npaigns was") == [("cam- paigns", "campaigns")]


def test_a_merge_takes_no_token_the_model_pairs() -> None:
    # "Ram" pairs with the model's "Ram": "ses" alone pairs with "Ramses",
    # which repeats its neighbour.
    blocks = _page(_block("b-p0001-001", _text("of Ram ses here")))
    assert _edits(blocks, "of Ram Ramses here") == []


@pytest.mark.parametrize(
    ("note", "raw", "expected"),
    [
        # Two one-letter words the word beside holds: not put in.
        ("Called K·A·D. here", "Called K·A·D. A D here", []),
        # Words of two letters or more are put in, held or not.
        (
            "Called thisisin here",
            "Called thisisin is in here",
            [("thisisin", "thisisin is in")],
        ),
        # One-letter words the word beside does not hold: put in.
        ("Called K·A·D. here", "Called K·A·D. X Y here", [("K·A·D.", "K·A·D. X Y")]),
    ],
    ids=["two_letters_held", "longer_words_held", "letters_not_held"],
)
def test_an_insertion_of_letters_is_refused_only_when_the_word_holds_them(
    note: str, raw: str, expected: list[tuple[str, str]]
) -> None:
    notes = (
        _note("n-p0001-001", "1", note, 400),
        _note("n-p0001-002", "2", "Struggle of Nations.", 420),
    )
    blocks = _page(_block("b-p0001-001", _text("The poem")), notes=notes)
    edits = _edits(blocks, f"The poem\n1 {raw}\n2 Struggle of Nations.")
    assert edits == expected


@pytest.mark.parametrize(
    ("galley", "raw", "expected"),
    [
        # Six characters, printed before galley's word: refused.
        (
            "the canons of the realm was his accession here",
            "the canons of the realm was his canons here",
            [],
        ),
        # Five characters, printed nearby: kept.
        (
            "the realm was his raxyz here and the realm",
            "the realm was his realm here and the realm",
            [("raxyz", "realm")],
        ),
    ],
    ids=["six_before", "five_after"],
)
def test_a_word_of_another_line_is_six_characters_or_more(
    galley: str, raw: str, expected: list[tuple[str, str]]
) -> None:
    assert _edits(_page(_block("b-p0001-001", _text(galley))), raw) == expected


def _contents(*entries: str) -> BlocksFile:
    return _page(
        *(
            _block(
                f"b-p0001-{position:03d}",
                _text(entry),
                kind=BlockKind.CONTENTS_ENTRY,
                origin=(
                    Origin(1, Box(60, 100 + 12 * position, 260, 110 + 12 * position)),
                ),
            )
            for position, entry in enumerate(entries, 1)
        )
    )


@pytest.mark.parametrize(
    ("entry", "raw", "expected"),
    [
        # Gierke's contents: a page number of another entry.
        ("The Catholic Concordance 76", "The Catholic Concordance 68", []),
        # A short word of another entry, 0.4 alike.
        ("Election in Councils 168", "Election his Councils 168", []),
        # A misread letter, kept: "ins" for "ius".
        ("The ins civile 76", "The ius civile 76", [("ins", "ius")]),
    ],
    ids=["page_number", "short_word", "letter"],
)
def test_a_contents_entry_takes_only_close_edits_that_keep_its_digits(
    entry: str, raw: str, expected: list[tuple[str, str]]
) -> None:
    assert _edits(_contents(entry), raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # Gierke: a margin note's word read into the note beside it.
        ("1 by the rules Majorities that dealt", []),
        # A word no margin note holds: put in.
        ("1 by the rules in force that dealt", [("rules", "rules in force")]),
    ],
    ids=["margin_word", "other_word"],
)
def test_an_insertion_of_margin_note_words_is_refused(
    raw: str, expected: list[tuple[str, str]]
) -> None:
    margin = _block(
        "b-p0001-002",
        _text("Majorities."),
        kind=BlockKind.MARGIN_NOTE,
        origin=(Origin(1, Box(10, 400, 50, 410)),),
    )
    notes = (
        _note("n-p0001-001", "1", "by the rules that dealt", 400),
        _note("n-p0001-002", "2", "Struggle of Nations.", 420),
    )
    blocks = _page(_block("b-p0001-001", _text("The poem")), margin, notes=notes)
    edits = _edits(blocks, f"The poem\n{raw}\n2 Struggle of Nations.")
    assert edits == expected


@pytest.mark.parametrize(
    ("times", "expected"),
    [
        # Stubbs page 291: "obtained" is printed 22 times in the book.
        (22, []),
        (2, []),
        # A word galley glued, held once: split.
        (1, [("obtained", "of tained")]),
    ],
    ids=["many", "twice", "once"],
)
def test_a_word_galley_holds_twice_is_not_split(
    times: int, expected: list[tuple[str, str]]
) -> None:
    words = WordList.of(frozenset({"the", "king"}), frozendict({"obtained": times}))
    blocks = _page(_block("b-p0001-001", _text("the king obtained the land")))
    assert _edits(blocks, "the king of tained the land", words) == expected


@pytest.mark.parametrize(
    ("galley", "raw", "expected"),
    [
        # Domesday's margin note: "to" would be lost.
        ("The right towitesand here", "The right wites and here", []),
        # Domesday's table: a digit of galley's would be lost.
        ("Nordlege 909 here", "Nordlege 0 9 here", []),
        ("Nordlege 1800 here", "Nordlege 140 360 here", []),
        # Stubbs: a line-end half of the model's, not galley's word.
        ("was discontented here", "was discon-\nHenry here", []),
        # A glued word whose halves join to galley's: split.
        ("the shouldbe here", "the should be here", [("shouldbe", "should be")]),
        ("the 1121 here", "the 112 1 here", [("1121", "112 1")]),
    ],
    ids=[
        "piece",
        "digit_lost",
        "digits_of_other_rows",
        "line_end_half",
        "glued",
        "digits_kept",
    ],
)
def test_a_split_of_galleys_word_keeps_what_galley_read(
    galley: str, raw: str, expected: list[tuple[str, str]]
) -> None:
    assert _edits(_page(_block("b-p0001-001", _text(galley))), raw) == expected


def test_a_refused_split_puts_none_of_its_words_in_a_note() -> None:
    # Domesday page 154: "4v=120A." against "V = 120. A" loses the "4";
    # the model's "A", galley's too, is not put in after it.
    notes = (
        _note("n-p0001-001", "1", "see 4v=120A. here", 400),
        _note("n-p0001-002", "2", "Struggle of Nations.", 420),
    )
    blocks = _page(_block("b-p0001-001", _text("The poem")), notes=notes)
    raw = "The poem\n1 see V = 120. A here\n2 Struggle of Nations."
    assert _edits(blocks, raw) == []


@pytest.mark.parametrize(
    ("galley", "raw", "expected"),
    [
        # Domesday page 428: "18" is a number of another row.
        ("Hamtune 0 8 0 here", "Hamtune 0 18 here", []),
        # Two digits that join to the model's: merged.
        ("Hamtune 1 8 here", "Hamtune 18 here", [("1 8", "18")]),
    ],
    ids=["other_number", "own_join"],
)
def test_two_digits_merge_only_into_their_own_join(
    galley: str, raw: str, expected: list[tuple[str, str]]
) -> None:
    assert _edits(_page(_block("b-p0001-001", _text(galley))), raw) == expected


def test_a_name_galley_holds_twice_is_not_split() -> None:
    # Domesday page 129: "Brungar", printed twice, became "Brun gar".
    words = WordList.of(frozenset({"of", "the"}), frozendict({"brungar": 2}))
    blocks = _page(_block("b-p0001-001", _text("of Brungar the")))
    assert _edits(blocks, "of Brun gar the", words) == []


def test_an_insertion_that_repeats_the_next_word_is_refused() -> None:
    # Domesday page 37: "-by" read in again before galley's "-by,".
    notes = (
        _note("n-p0001-001", "1", "names in -uam, -by, -thorp here", 400),
        _note("n-p0001-002", "2", "Struggle of Nations.", 420),
    )
    blocks = _page(_block("b-p0001-001", _text("The poem")), notes=notes)
    raw = "The poem\n1 names in -ham, -by Illustrations -by, -thorp here\n2 Struggle of Nations."
    assert _edits(blocks, raw) == [("-uam,", "-ham,")]


def test_a_split_with_a_line_end_word_galley_holds_in_halves_is_refused() -> None:
    # Stubbs page 72: galley holds "how" glued to "find" and "ever,"
    # further on; the model joined "how-" and "ever," at its line end.
    blocks = _page(_block("b-p0001-001", _text("We do not, howfind, that ever, he")))
    assert _edits(blocks, "We do not, how-\never, find, that he") == []


def test_a_split_whose_added_half_galley_holds_glued_is_refused() -> None:
    # Stubbs page 202: galley's "marand" and, further on, "augriage".
    blocks = _page(
        _block("b-p0001-001", _text("The marand quarrel served to augriage it"))
    )
    assert _edits(blocks, "The marriage and quarrel served to aug it") == []
