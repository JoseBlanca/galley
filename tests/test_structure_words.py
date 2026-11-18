"""Tests of spaced punctuation and of words glued at a case change
(docs/specs/structure.md, sections 23 and 24; the spaced-signs and
case-split bullets of section 26).

Every value is written by hand. The passes run on a block before
references are looked for; through `make_blocks`, on pages written in
the test, a sign attached to "hides4" gives the reference "4" linked to
its note, and a French book a no-break space.
"""

from collections.abc import Callable

import pytest

from galley.book_folder import BookFolder
from galley.config import Language
from galley.errors import FidelityBoundary
from galley.fidelity import check_stage
from galley.model import (
    BlockKind,
    BlocksFile,
    Box,
    ChangeReason,
    Line,
    LinesFile,
    Origin,
    PageLayout,
    Region,
    Word,
    WordChange,
    read_blocks,
)
from galley.structure import (
    attach_spaced_sign,
    make_blocks,
    reference_candidate,
    split_at_case,
)
from galley.structure._case_split import split_glued_words
from galley.structure._markers import Reference, ReferenceForm
from galley.structure._spaced import attach_spaced_signs, no_break_positions
from galley.structure._unnumbered import Unnumbered

_ORIGIN = (Origin(4, Box(72.0, 100.0, 400.0, 160.0)),)


def _block(
    words: tuple[str, ...],
    *,
    kind: BlockKind = BlockKind.PARAGRAPH,
    pages: tuple[int, ...] | None = None,
    changes: tuple[tuple[int, WordChange], ...] = (),
    line_starts: frozenset[int] = frozenset(),
) -> Unnumbered:
    return Unnumbered(
        kind,
        words,
        pages if pages is not None else tuple(4 for _ in words),
        _ORIGIN,
        changes,
        line_starts=line_starts,
    )


# attach_spaced_sign


@pytest.mark.parametrize(
    ("before", "word", "attached"),
    [
        ("subjection", ";", "subjection;"),
        ("pursued", "?", "pursued?"),
        ("follows", ":", "follows:"),
        ("alas", "!", "alas!"),
        ("hides4", ";", "hides4;"),
        ("(1)", ";", "(1);"),
        ("[sic]", ":", "[sic]:"),
        ("subjection", ";^", "subjection;^"),
        ("he", "?'", "he?'"),
    ],
)
def test_spaced_sign_after_a_letter_digit_or_bracket_is_attached(
    before: str, word: str, attached: str
) -> None:
    assert attach_spaced_sign(before, word) == attached


@pytest.mark.parametrize(
    ("before", "word"),
    [
        ("—", ";"),
        ("'", "?"),
        ("said’", ";"),
        ('said"', ":"),
        ("dit»", "!"),
        ("etc.", ";"),
        ("subjection", "and"),
        ("subjection", ","),
        # Kadesh page 10, "(Nos. 1, 2, 13, 14) ;13": the sign holds the
        # reference 13, which "14);13" would not.
        ("14)", ";13"),
        ("1854", ";7"),
        # A speck the OCR read as a sign before a word: Gierke page 29's
        # "universitas ;is," and Stubbs' "on ?uer" print no sign there.
        ("universitas", ";is,"),
        ("on", "?uer"),
        ("m", ";s."),
    ],
)
def test_sign_after_a_dash_or_quotation_mark_or_a_word_not_a_sign_stays(
    before: str, word: str
) -> None:
    assert attach_spaced_sign(before, word) is None


# attach_spaced_signs


def test_spaced_sign_in_a_block_is_attached_with_its_change() -> None:
    hyphen = WordChange(
        page_index=4,
        before=("re-", "plied"),
        after=("replied",),
        reason=ChangeReason.HYPHEN_JOIN,
    )
    later = WordChange(
        page_index=5,
        before=("con-", "quest"),
        after=("conquest",),
        reason=ChangeReason.HYPHEN_JOIN,
    )
    block = _block(
        ("He", "replied", ";", "the", "conquest", "ended"),
        pages=(4, 4, 4, 5, 5, 5),
        changes=((1, hyphen), (4, later)),
        line_starts=frozenset({3}),
    )

    attached = attach_spaced_signs(block)

    assert attached.words == ("He", "replied;", "the", "conquest", "ended")
    assert attached.word_pages == (4, 4, 5, 5, 5)
    assert attached.line_starts == frozenset({2})
    assert attached.changes == (
        (1, hyphen),
        (3, later),
        (
            1,
            WordChange(
                page_index=4,
                before=("replied", ";"),
                after=("replied;",),
                reason=ChangeReason.PUNCTUATION_ATTACHED,
            ),
        ),
    )


def test_spaced_sign_on_the_next_line_of_a_paragraph_is_attached() -> None:
    block = _block(
        ("of", "subjection", ";", "and"),
        pages=(4, 4, 5, 5),
        line_starts=frozenset({2}),
    )

    attached = attach_spaced_signs(block)

    assert attached.words == ("of", "subjection;", "and")
    assert attached.word_pages == (4, 4, 5)
    assert attached.line_starts == frozenset()
    assert attached.changes[0][1].page_index == 4


def test_sign_that_starts_a_block_or_follows_a_dash_stays() -> None:
    block = _block((";", "the", "—", ";", "'", "?"))

    assert attach_spaced_signs(block) == block


def test_sign_after_a_line_feed_of_verse_stays() -> None:
    block = _block(
        ("O", "Death", "?", "where"),
        kind=BlockKind.VERSE,
        line_starts=frozenset({2}),
    )

    assert attach_spaced_signs(block) == block


def test_sign_holding_a_reference_is_attached_when_the_word_made_holds_it() -> None:
    assert attach_spaced_sign("land", ";13") == "land;13"
    assert reference_candidate("land;13") == Reference(
        "land;", "13", "", ReferenceForm.GLUED, 13
    )


def test_sign_after_a_line_feed_of_a_verse_epigraph_stays() -> None:
    block = _block(
        ("O", "Death", "?", "where"),
        kind=BlockKind.EPIGRAPH,
        line_starts=frozenset({2}),
    )

    assert attach_spaced_signs(block) == block
    assert no_break_positions(block) == frozenset()


def test_sign_attached_to_a_glued_reference_gives_the_reference_and_the_sign() -> None:
    attached = attach_spaced_signs(_block(("five", "hides4", ";", "and")))

    assert attached.words[1] == "hides4;"
    assert reference_candidate(attached.words[1]) == Reference(
        "hides", "4", ";", ReferenceForm.GLUED, 4
    )


def test_sign_glued_to_a_sign_reference_becomes_a_candidate() -> None:
    assert reference_candidate(";^") is None

    attached = attach_spaced_signs(_block(("of", "subjection", ";^")))

    assert attached.words == ("of", "subjection;^")
    assert reference_candidate(attached.words[1]) == Reference(
        "subjection;", "^", "", ReferenceForm.SIGN, None
    )


# no_break_positions, for a French book


def test_spaced_sign_in_french_takes_a_no_break_space_and_no_change() -> None:
    block = _block(
        ("complète", ";", "(1)", ":", "—", "?", "hides4", "!"),
        line_starts=frozenset({3}),
    )

    assert no_break_positions(block) == frozenset({1, 3, 7})


def test_no_break_space_is_not_put_before_a_sign_followed_by_letters() -> None:
    # Mariéjol's "landgrave !e": a speck read as a sign, glued to a word.
    block = _block(("landgrave", "!e", "duc", ";"))

    assert no_break_positions(block) == frozenset({3})


def test_no_break_space_is_not_put_at_a_line_feed_of_verse_or_a_block_start() -> None:
    block = _block(
        ("?", "mort", "!", "vie"),
        kind=BlockKind.VERSE,
        line_starts=frozenset({2}),
    )

    assert no_break_positions(block) == frozenset()


# split_at_case

_LOWER_CASE_WORDS = frozenset({"the", "of", "in", "de", "le", "guin", "ab", "po", "ji"})
_BOOK_WORDS = frozenset(
    {"avre", "william", "ab", "guin", "out", "utique", "ethelbert", "hit"}
)
# The book's common inner words: "po" and "ji" are known words of the
# list but not printed often in the book.
_COMMON_INNER_WORDS = frozenset({"the", "of", "in", "de", "le", "a", "xy"})


@pytest.mark.parametrize(
    ("word", "parts"),
    [
        ("theAvre", ("the", "Avre")),
        ("ofWilliam,", ("of", "William,")),
        ("(theAvre).", ("(the", "Avre).")),
    ],
)
def test_word_glued_at_a_case_change_is_split_when_the_book_prints_the_right_part(
    word: str, parts: tuple[str, str]
) -> None:
    assert (
        split_at_case(word, _LOWER_CASE_WORDS, _BOOK_WORDS, _COMMON_INNER_WORDS)
        == parts
    )


@pytest.mark.parametrize(
    ("word", "book_words", "lower_case_words"),
    [
        ("theAvre", frozenset({"william"}), _LOWER_CASE_WORDS),
        ("LeGuin", _BOOK_WORDS, _LOWER_CASE_WORDS),
        ("deUver", _BOOK_WORDS, _LOWER_CASE_WORDS),
        ("ofAb", _BOOK_WORDS, _LOWER_CASE_WORDS),
        # Domesday page 339 prints the Old English "forðon", which the OCR
        # reads "forSon": a capital followed by 2 lower-case letters.
        ("ofSon", _BOOK_WORDS | {"son"}, _LOWER_CASE_WORDS),
        ("aWilliam", _BOOK_WORDS, _LOWER_CASE_WORDS | {"a"}),
        ("xyWilliam", _BOOK_WORDS, _LOWER_CASE_WORDS),
        ("theAvre", _BOOK_WORDS, _LOWER_CASE_WORDS | {"theavre"}),
        ("ofWilliAm", _BOOK_WORDS, _LOWER_CASE_WORDS),
        ("of-William", _BOOK_WORDS, _LOWER_CASE_WORDS),
        ("ofWilliam's", _BOOK_WORDS, _LOWER_CASE_WORDS),
        ("theavre", _BOOK_WORDS, _LOWER_CASE_WORDS),
        ("poUtique", _BOOK_WORDS, _LOWER_CASE_WORDS),
        ("jiEthelbert", _BOOK_WORDS, _LOWER_CASE_WORDS),
        ("ofUtique", _BOOK_WORDS, _LOWER_CASE_WORDS),
        # "Hits" has 3 letters after its capital, so only the H rule refuses it.
        ("theHits", _BOOK_WORDS | {"hits"}, _LOWER_CASE_WORDS),
    ],
)
def test_word_not_glued_at_a_case_change_or_without_evidence_stays(
    word: str, book_words: frozenset[str], lower_case_words: frozenset[str]
) -> None:
    assert (
        split_at_case(word, lower_case_words, book_words, _COMMON_INNER_WORDS) is None
    )


# split_glued_words


def test_glued_word_in_a_block_is_split_with_its_change() -> None:
    hyphen = WordChange(
        page_index=4,
        before=("Wil-", "liam"),
        after=("William",),
        reason=ChangeReason.HYPHEN_JOIN,
    )
    later = WordChange(
        page_index=5,
        before=("Nor-", "mandy"),
        after=("Normandy",),
        reason=ChangeReason.HYPHEN_JOIN,
    )
    joined = WordChange(
        page_index=4,
        before=("ofWil-", "liam,"),
        after=("ofWilliam,",),
        reason=ChangeReason.HYPHEN_JOIN,
    )
    block = _block(
        ("William", "came", "ofWilliam,", "to", "Normandy"),
        pages=(4, 4, 4, 5, 5),
        changes=((0, hyphen), (2, joined), (4, later)),
        line_starts=frozenset({3}),
    )

    split = split_glued_words(
        block, _LOWER_CASE_WORDS, _BOOK_WORDS, _COMMON_INNER_WORDS
    )

    assert split.words == ("William", "came", "of", "William,", "to", "Normandy")
    assert split.word_pages == (4, 4, 4, 4, 5, 5)
    assert split.line_starts == frozenset({4})
    assert split.changes == (
        (0, hyphen),
        (2, joined),
        (5, later),
        (
            2,
            WordChange(
                page_index=4,
                before=("ofWilliam,",),
                after=("of", "William,"),
                reason=ChangeReason.CASE_SPLIT,
            ),
        ),
    )


def test_block_without_glued_words_is_unchanged() -> None:
    block = _block(("the", "Avre", "deUver", "LeGuin"))

    assert (
        split_glued_words(block, _LOWER_CASE_WORDS, _BOOK_WORDS, _COMMON_INNER_WORDS)
        == block
    )


# make_blocks: the passes wired into structure (spec section 2, the
# paragraph after the steps). A word is 5 pt wide per character, the body
# 10 pt high, the band 7 pt, the lines 15 pt apart.

_HASH = "0" * 64
_CHAR_PT = 5.0
_BODY_HEIGHT_PT = 10.0
_BAND_HEIGHT_PT = 7.0
_PITCH_PT = 15.0
_LEFT_PT = 50.0
_TOP_PT = 100.0


def _line(text: str, top: float, height: float = _BODY_HEIGHT_PT) -> Line:
    words = []
    left = _LEFT_PT
    for part in text.split(" "):
        right = left + _CHAR_PT * len(part)
        words.append(Word(part, Box(left, top, right, top + height), None))
        left = right + _CHAR_PT
    return Line(Box(_LEFT_PT, top, words[-1].box.x1, top + height), tuple(words))


def _region(*lines: Line) -> Region:
    return Region(
        Box(
            min(line.box.x0 for line in lines),
            lines[0].box.top,
            max(line.box.x1 for line in lines),
            lines[-1].box.bottom,
        ),
        lines,
    )


def _body(*texts: str) -> Region:
    return _region(
        *(_line(text, _TOP_PT + _PITCH_PT * row) for row, text in enumerate(texts))
    )


def _page(index: int, *regions: Region) -> PageLayout:
    return PageLayout(index, regions, ())


def _lines_of(*pages: PageLayout) -> LinesFile:
    return LinesFile(source_pdf_sha256=_HASH, pages=pages, rereads=())


# The same width on every line, so that no line ends short of the column.
_HIDES_LINES = (
    "the land was five hides4 ; and",
    "the rest of it was held by",
    "the abbot of the old house.",
)


def _hides_page() -> LinesFile:
    band = _region(_line("4 See the survey.", _TOP_PT + _PITCH_PT * 4, _BAND_HEIGHT_PT))
    return _lines_of(_page(0, _body(*_HIDES_LINES), band))


def _texts(blocks: BlocksFile) -> tuple[str, ...]:
    return tuple("".join(span.text for span in block.spans) for block in blocks.blocks)


def _changes(blocks: BlocksFile, reason: ChangeReason) -> tuple[WordChange, ...]:
    return tuple(change for change in blocks.word_changes if change.reason is reason)


def test_make_blocks_attaches_a_sign_after_a_reference_which_is_then_linked() -> None:
    lines = _hides_page()

    blocks = make_blocks(lines, frozenset(), workers=1)

    (paragraph,) = blocks.blocks
    (note,) = blocks.notes
    assert _texts(blocks)[0].startswith("the land was five hides4; and the rest")
    assert [(span.text, span.note_ref) for span in paragraph.spans[:3]] == [
        ("the land was five hides", None),
        ("4", note.id),
        ("; and the rest of it was held by the abbot of the old house.", None),
    ]
    assert _changes(blocks, ChangeReason.PUNCTUATION_ATTACHED) == (
        WordChange(
            page_index=0,
            before=("hides4", ";"),
            after=("hides4;",),
            reason=ChangeReason.PUNCTUATION_ATTACHED,
        ),
    )
    assert WordChange(
        page_index=0,
        before=("hides4;",),
        after=("hides", "4", ";"),
        reason=ChangeReason.NOTE_MARKER,
    ) in _changes(blocks, ChangeReason.NOTE_MARKER)
    check_stage(FidelityBoundary.STRUCTURE, lines, blocks)


def test_make_blocks_in_french_puts_a_no_break_space_before_the_sign() -> None:
    lines = _hides_page()

    blocks = make_blocks(lines, frozenset(), language=Language.FR, workers=1)

    (paragraph,) = blocks.blocks
    assert [span.text for span in paragraph.spans[:3]] == [
        "the land was five hides",
        "4",
        "\u00a0; and the rest of it was held by the abbot of the old house.",
    ]
    assert _changes(blocks, ChangeReason.PUNCTUATION_ATTACHED) == ()
    assert WordChange(
        page_index=0,
        before=("hides4",),
        after=("hides", "4"),
        reason=ChangeReason.NOTE_MARKER,
    ) in _changes(blocks, ChangeReason.NOTE_MARKER)
    check_stage(FidelityBoundary.STRUCTURE, lines, blocks)


def test_make_blocks_attaches_a_sign_at_the_top_of_a_page_to_the_page_before() -> None:
    lines = _lines_of(
        _page(
            0, _body("the abbot held the land in", "the time of his long subjection")
        ),
        _page(
            1, _body("; and the rest of it was held", "by the king of the old land.")
        ),
    )

    blocks = make_blocks(lines, frozenset(), workers=1)

    assert _texts(blocks) == (
        (
            "the abbot held the land in the time of his long subjection; and the "
            "rest of it was held by the king of the old land."
        ),
    )
    assert _changes(blocks, ChangeReason.PUNCTUATION_ATTACHED) == (
        WordChange(
            page_index=0,
            before=("subjection", ";"),
            after=("subjection;",),
            reason=ChangeReason.PUNCTUATION_ATTACHED,
        ),
    )
    check_stage(FidelityBoundary.STRUCTURE, lines, blocks)


def test_make_blocks_splits_a_word_glued_at_a_case_change() -> None:
    # "the" is printed after a line's first word more than 8 times, and the
    # book prints "Avre" whole.
    texts = tuple(f"by the river {row} and" for row in range(10))
    lines = _lines_of(_page(0, _body(*texts, "the Avre and theAvre.")))

    blocks = make_blocks(lines, frozenset({"the", "by", "and", "river"}), workers=1)

    assert _texts(blocks)[0].endswith("the Avre and the Avre.")
    assert _changes(blocks, ChangeReason.CASE_SPLIT) == (
        WordChange(
            page_index=0,
            before=("theAvre.",),
            after=("the", "Avre."),
            reason=ChangeReason.CASE_SPLIT,
        ),
    )
    check_stage(FidelityBoundary.STRUCTURE, lines, blocks)


# Whole books: no sign attached in Mariéjol, a French book, and some in each
# English one (spec section 26, deliverable 3 of the plan's work package 5).
_MARIEJOL = "catherinedemedic00mariuoft"
_ENGLISH_BOOKS = (
    "normansineuropea00hask",
    "earlyplantagenet01stub",
    "domesdaybook00maituoft",
    "battleofkadeshst00breauoft",
    "politicaltheorie00gieruoft",
)


@pytest.mark.whole_book
@pytest.mark.thread_unsafe
@pytest.mark.timeout(900)
@pytest.mark.parametrize("book", [_MARIEJOL, *_ENGLISH_BOOKS])
def test_whole_book_attaches_spaced_signs_in_english_and_none_in_french(
    whole_book_run: Callable[[str], BookFolder], book: str
) -> None:
    blocks = read_blocks(whole_book_run(book).blocks_json)
    attached = len(_changes(blocks, ChangeReason.PUNCTUATION_ATTACHED))
    no_break = sum(
        "\u00a0" in span.text
        for block in (
            *blocks.blocks,
            *(block for note in blocks.notes for block in note.blocks),
        )
        for span in block.spans
    )
    if book == _MARIEJOL:
        assert (attached, no_break > 0) == (0, True)
    else:
        assert (attached > 0, no_break) == (True, 0)


@pytest.mark.whole_book
@pytest.mark.thread_unsafe
@pytest.mark.timeout(900)
def test_whole_book_haskins_splits_the_avre_and_domesday_keeps_the_old_english(
    whole_book_run: Callable[[str], BookFolder],
) -> None:
    # Haskins page 22 prints "the Avre", which the whole book prints whole
    # elsewhere ("Avre,"); Domesday page 339 prints "forðon" and "forðan",
    # which the OCR reads "forSon" and "forSan" (spec section 24).
    haskins = read_blocks(whole_book_run("normansineuropea00hask").blocks_json)
    domesday = read_blocks(whole_book_run("domesdaybook00maituoft").blocks_json)
    assert WordChange(
        page_index=22,
        before=("theAvre",),
        after=("the", "Avre"),
        reason=ChangeReason.CASE_SPLIT,
    ) in _changes(haskins, ChangeReason.CASE_SPLIT)
    assert [
        change.before for change in _changes(domesday, ChangeReason.CASE_SPLIT)
    ] == [("ofChatteris",)]
