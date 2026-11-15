"""Tests of galley_eval.align: the alignment key, the anchored pass, the
three passes, and the states and subkinds of the tokens (spec section 1,
"Alignment key", and section 5, "Alignment" and "Differences")."""

import random

from galley_eval.align import (
    Alignment,
    AlignmentPass,
    GalleyStream,
    GalleyToken,
    Operation,
    Pairing,
    State,
    Stretch,
    Subkind,
    align,
    alignment_key,
    anchor_pairs,
    anchored_pass,
    changed_subkind,
    equal_key_share,
    reference_places,
    reference_states,
)
from galley_eval.reader import (
    Gap,
    NoteReference,
    ReferenceBlock,
    ReferenceKind,
    ReferenceNote,
    ReferenceText,
    ReferenceToken,
    Stream,
)


def _words(text: str, *, marked: bool = False) -> tuple[ReferenceToken, ...]:
    return tuple(
        ReferenceToken(word, marked_correction=marked) for word in text.split()
    )


def _reference(
    *blocks: ReferenceBlock, notes: tuple[ReferenceNote, ...] = ()
) -> ReferenceText:
    return ReferenceText(
        blocks=blocks,
        notes=notes,
        note_references=tuple(
            NoteReference(note.note_id, Gap(Stream.BODY, 0)) for note in notes
        ),
        page_anchors=(),
        anchors_in_notes=(),
    )


def _paragraph(text: str) -> ReferenceBlock:
    return ReferenceBlock(ReferenceKind.PARAGRAPH, _words(text))


def _galley(
    text: str, *, page_index: int = 0, stream: GalleyStream = GalleyStream.BODY
) -> tuple[GalleyToken, ...]:
    return tuple(
        GalleyToken(
            text=word,
            page_index=page_index,
            stream=stream,
            edge_of_page=False,
            block_id=None,
        )
        for word in text.split()
    )


def _align(
    reference: ReferenceText, galley: tuple[GalleyToken, ...]
) -> tuple[Alignment, tuple[Pairing, ...]]:
    alignment = align(reference, galley)
    return alignment, alignment.pairings


def _pairing_of_reference(alignment: Alignment, index: int) -> Pairing:
    return alignment.pairings[alignment.reference_pairing[index]]


def _pairing_of_galley(alignment: Alignment, index: int) -> Pairing:
    return alignment.pairings[alignment.galley_pairing[index]]


# The alignment key


def test_alignment_key_drops_punctuation_and_case() -> None:
    assert alignment_key("Pamphlets,") == alignment_key("pamphlets") == "pamphlets"


def test_alignment_key_spells_ligature_letters_and_drops_accents() -> None:
    assert alignment_key("Æthelred") == alignment_key("AEthelred") == "aethelred"
    assert alignment_key("Œuvre") == "oeuvre"
    assert alignment_key("ðorn") == "dorn"
    assert alignment_key("þegn") == "thegn"
    assert alignment_key("Médicis") == "medicis"


def test_alignment_key_of_glued_words_is_another_key() -> None:
    assert alignment_key("pamphletspublishedon") != alignment_key("pamphlets")


# The anchored pass


def test_anchored_pass_aligns_stretches_between_anchors() -> None:
    reference = ("the", "king", "of", "the", "normans")
    galley = ("the", "kinq", "of", "the", "normans")
    assert anchored_pass(reference, galley) == (
        Stretch(Operation.EQUAL, 0, 1, 0, 1),
        Stretch(Operation.REPLACE, 1, 2, 1, 2),
        Stretch(Operation.EQUAL, 2, 3, 2, 3),
        Stretch(Operation.EQUAL, 3, 4, 3, 4),
        Stretch(Operation.EQUAL, 4, 5, 4, 5),
    )


def test_anchored_pass_keeps_the_longest_run_of_anchors_in_order() -> None:
    # "alpha" and "omega" are unique on both sides but in the other order
    # in galley; only one of them can be an anchor with "beta" and "gamma".
    reference = ("alpha", "beta", "gamma", "omega")
    galley = ("omega", "beta", "gamma", "alpha")
    stretches = anchored_pass(reference, galley)
    equal = tuple(
        stretch for stretch in stretches if stretch.operation is Operation.EQUAL
    )
    assert tuple((s.reference_start, s.galley_start) for s in equal) == (
        (1, 1),
        (2, 2),
    )


def test_anchored_pass_of_empty_sides_gives_inserts_and_deletes() -> None:
    assert anchored_pass((), ("a", "b")) == (Stretch(Operation.INSERT, 0, 0, 0, 2),)
    assert anchored_pass(("a",), ()) == (Stretch(Operation.DELETE, 0, 1, 0, 0),)
    assert anchored_pass((), ()) == ()


# The states


def test_same_text_is_matched() -> None:
    alignment, _ = _align(_reference(_paragraph("the Normans")), _galley("the Normans"))
    assert reference_states(alignment) == (State.MATCHED, State.MATCHED)


def test_same_key_other_text_is_changed() -> None:
    alignment, _ = _align(
        _reference(_paragraph("the Normans,")), _galley("the Normans")
    )
    pairing = _pairing_of_reference(alignment, 1)
    assert pairing.state is State.CHANGED
    assert pairing.subkind is Subkind.PUNCTUATION
    assert pairing.galley_indices == (1,)


def test_replaced_token_is_paired_as_changed() -> None:
    alignment, _ = _align(
        _reference(_paragraph("the Normans in Sicily")),
        _galley("the Norrnans in Sicily"),
    )
    pairing = _pairing_of_reference(alignment, 1)
    assert pairing.state is State.CHANGED
    assert pairing.subkind is Subkind.LETTERS
    assert pairing.reference_indices == (1,)
    assert pairing.galley_indices == (1,)


def test_hyphenated_word_is_a_split_of_two() -> None:
    alignment, _ = _align(
        _reference(_paragraph("to replicate the text")),
        _galley("to repli- cate the text"),
    )
    pairing = _pairing_of_reference(alignment, 1)
    assert pairing.state is State.SPLIT
    assert pairing.reference_indices == (1,)
    assert pairing.galley_indices == (1, 2)
    assert _pairing_of_galley(alignment, 2) == pairing


def test_words_without_spaces_are_glued_of_three() -> None:
    alignment, _ = _align(
        _reference(_paragraph("many pamphlets published on it")),
        _galley("many pamphletspublishedon it"),
    )
    pairing = _pairing_of_reference(alignment, 2)
    assert pairing.state is State.GLUED
    assert pairing.reference_indices == (1, 2, 3)
    assert pairing.galley_indices == (1,)
    assert reference_states(alignment) == (
        State.MATCHED,
        State.GLUED,
        State.GLUED,
        State.GLUED,
        State.MATCHED,
    )


def test_split_is_found_after_a_changed_token_in_the_same_stretch() -> None:
    alignment, _ = _align(
        _reference(_paragraph("one alpha replicate two")),
        _galley("one alqha repli- cate two"),
    )
    assert reference_states(alignment) == (
        State.MATCHED,
        State.CHANGED,
        State.SPLIT,
        State.MATCHED,
    )


def test_reference_token_with_no_galley_token_is_missing() -> None:
    alignment, _ = _align(
        _reference(_paragraph("the Normans in Sicily")), _galley("the Normans Sicily")
    )
    pairing = _pairing_of_reference(alignment, 2)
    assert pairing.state is State.MISSING
    assert pairing.galley_indices == ()
    assert pairing.found_in is None


def test_galley_token_with_no_reference_token_is_extra() -> None:
    alignment, _ = _align(
        _reference(_paragraph("the Normans in Sicily")),
        _galley("HISTORY 199 the Normans in Sicily"),
    )
    assert tuple(_pairing_of_galley(alignment, index).state for index in range(2)) == (
        State.EXTRA,
        State.EXTRA,
    )
    assert reference_states(alignment) == (State.MATCHED,) * 4


def test_longer_side_of_a_replaced_stretch_leaves_extra_tokens() -> None:
    alignment, _ = _align(
        _reference(_paragraph("one alpha two")), _galley("one alqha xx yy two")
    )
    states = tuple(_pairing_of_galley(alignment, index).state for index in range(5))
    assert states == (
        State.MATCHED,
        State.CHANGED,
        State.EXTRA,
        State.EXTRA,
        State.MATCHED,
    )


# The subkinds


def test_quotes_dashes_and_ligatures_are_convention() -> None:
    reference = ReferenceToken("’Tis—", marked_correction=False)
    assert changed_subkind(reference, "'Tis--") is Subkind.CONVENTION
    assert changed_subkind(
        ReferenceToken("“ﬁne”", marked_correction=False), '"fine"'
    ) is (Subkind.CONVENTION)


def test_en_dash_between_digits_is_a_hyphen_by_convention() -> None:
    reference = ReferenceToken("541–90", marked_correction=False)
    assert changed_subkind(reference, "541-90") is Subkind.CONVENTION
    assert changed_subkind(ReferenceToken("a–b", marked_correction=False), "a--b") is (
        Subkind.CONVENTION
    )


def test_case_only_is_case() -> None:
    reference = ReferenceToken("Normans", marked_correction=False)
    assert changed_subkind(reference, "NORMANS") is Subkind.CASE


def test_case_is_judged_after_convention() -> None:
    reference = ReferenceToken("’Tis", marked_correction=False)
    assert changed_subkind(reference, "'TIS") is Subkind.CASE


def test_pair_differing_only_in_punctuation_is_punctuation_not_diacritic() -> None:
    reference = ReferenceToken("Normans,", marked_correction=False)
    assert changed_subkind(reference, "Normans.") is Subkind.PUNCTUATION


def test_lost_accent_is_diacritic() -> None:
    reference = ReferenceToken("Médicis", marked_correction=False)
    assert changed_subkind(reference, "Medicis") is Subkind.DIACRITIC
    assert changed_subkind(
        ReferenceToken("Æthelred", marked_correction=False), "AEthelred"
    ) is (Subkind.DIACRITIC)


def test_other_letters_are_letters() -> None:
    reference = ReferenceToken("Normans", marked_correction=False)
    assert changed_subkind(reference, "Norrnans") is Subkind.LETTERS


def test_marked_correction_is_reference_correction() -> None:
    reference = ReferenceToken("Normans", marked_correction=True)
    assert changed_subkind(reference, "Norrnans") is Subkind.REFERENCE_CORRECTION


def test_missing_marked_correction_is_reference_correction() -> None:
    reference = _reference(
        ReferenceBlock(
            ReferenceKind.PARAGRAPH,
            _words("the") + _words("corrected", marked=True) + _words("word"),
        )
    )
    alignment, _ = _align(reference, _galley("the word"))
    pairing = _pairing_of_reference(alignment, 1)
    assert pairing.state is State.MISSING
    assert pairing.subkind is Subkind.REFERENCE_CORRECTION


# The three passes


def test_body_tokens_are_aligned_by_the_body_pass() -> None:
    alignment, _ = _align(_reference(_paragraph("the Normans")), _galley("the Normans"))
    assert _pairing_of_reference(alignment, 0).found_in is AlignmentPass.BODY


def test_note_moved_to_the_end_is_found_by_the_notes_pass() -> None:
    # galley keeps the note at the foot of its page, among the body's words;
    # Gutenberg gathers it at the end of the book.
    reference = _reference(
        _paragraph("the duke landed in Sicily and took Palermo"),
        notes=(ReferenceNote("Footnote_1", (_paragraph("Amatus, ii. 8."),)),),
    )
    galley = _galley("the duke landed in Sicily Amatus, ii. 8. and took Palermo")
    alignment, _ = _align(reference, galley)
    note_tokens = range(8, 11)
    assert (
        tuple(_pairing_of_reference(alignment, index).found_in for index in note_tokens)
        == (AlignmentPass.NOTES,) * 3
    )
    assert tuple(
        _pairing_of_reference(alignment, index).galley_indices for index in note_tokens
    ) == (
        (5,),
        (6,),
        (7,),
    )
    assert set(reference_states(alignment)) == {State.MATCHED}


def test_margin_note_is_left_to_the_margin_notes_pass() -> None:
    reference = _reference(
        ReferenceBlock(ReferenceKind.MARGIN_NOTE, _words("Danegeld")),
        _paragraph("the tax was levied"),
    )
    alignment, _ = _align(reference, _galley("the tax Danegeld was levied"))
    assert _pairing_of_reference(alignment, 0).found_in is AlignmentPass.MARGIN_NOTES
    assert _pairing_of_reference(alignment, 0).galley_indices == (2,)


def test_margin_note_out_of_order_among_galley_notes_is_found_by_the_last_pass() -> (
    None
):
    # galley put the first margin note of a page among the page's notes, so
    # that in book order it comes after the second; the margin notes pass
    # can align only one of them in order, the last pass finds the other.
    reference = _reference(
        ReferenceBlock(ReferenceKind.MARGIN_NOTE, _words("Danegeld levied")),
        _paragraph("the tax"),
        ReferenceBlock(ReferenceKind.MARGIN_NOTE, _words("Hidage assessed")),
        _paragraph("the hide"),
    )
    galley = (
        _galley("the tax", page_index=2)
        + _galley("Hidage assessed", page_index=2, stream=GalleyStream.MARGIN_NOTES)
        + _galley("the hide", page_index=2)
        + _galley("Danegeld levied", page_index=2, stream=GalleyStream.NOTES)
    )
    alignment, _ = _align(reference, galley)
    passes = {
        _pairing_of_reference(alignment, 0).found_in,
        _pairing_of_reference(alignment, 4).found_in,
    }
    assert passes == {AlignmentPass.MARGIN_NOTES, AlignmentPass.REMAINDER}
    assert set(reference_states(alignment)) == {State.MATCHED}


def test_galley_tokens_of_other_streams_wait_for_the_later_passes() -> None:
    # A note galley found is not offered to the body pass, even where its
    # words would fit the body.
    reference = _reference(_paragraph("the duke landed"))
    galley = _galley("the duke") + _galley("landed", stream=GalleyStream.NOTES)
    alignment, _ = _align(reference, galley)
    assert _pairing_of_reference(alignment, 2).found_in is AlignmentPass.REMAINDER


# The share of reference tokens aligned to an equal key


def test_equal_key_share_counts_matched_and_changed_with_equal_keys() -> None:
    reference = _reference(_paragraph("the Normans, in Sicilv"))
    places = reference_places(reference)
    galley = _galley("the Normans in Sicily")
    alignment = align(reference, galley)
    # "the", "Normans," and "in" have equal keys; "Sicilv" does not.
    assert equal_key_share(alignment, places, galley) == 0.75


# Every token in exactly one pairing


def test_margin_note_block_inside_a_note_is_aligned_once() -> None:
    # The reader gives a note block of kind margin_note when an element
    # inside a note matches the margin_note rule; it belongs to the notes.
    reference = _reference(
        _paragraph("the duke landed"),
        notes=(
            ReferenceNote(
                "Footnote_1",
                (ReferenceBlock(ReferenceKind.MARGIN_NOTE, _words("Amatus ii")),),
            ),
        ),
    )
    # galley read the note twice; the second copy must stay extra.
    alignment, pairings = _align(
        reference, _galley("the duke landed Amatus ii Amatus ii")
    )
    assert sorted(
        index for pairing in pairings for index in pairing.reference_indices
    ) == list(range(5))
    assert sorted(
        index for pairing in pairings for index in pairing.galley_indices
    ) == list(range(7))
    assert _pairing_of_reference(alignment, 3).found_in is AlignmentPass.NOTES


_VOCABULARY = ("the", "duke", "Normans,", "—", "*", "repli-", "cate", "replicate", "of")


def test_every_token_is_in_exactly_one_pairing_whatever_the_input() -> None:
    generator = random.Random(1915)
    for _ in range(300):

        def text(length: int) -> str:
            return " ".join(generator.choice(_VOCABULARY) for _ in range(length))

        kinds = (ReferenceKind.PARAGRAPH, ReferenceKind.MARGIN_NOTE)
        reference = _reference(
            *(
                ReferenceBlock(
                    generator.choice(kinds), _words(text(generator.randint(1, 8)))
                )
                for _ in range(generator.randint(0, 4))
            ),
            notes=tuple(
                ReferenceNote(
                    f"Footnote_{number}",
                    (
                        ReferenceBlock(
                            generator.choice(kinds),
                            _words(text(generator.randint(1, 5))),
                        ),
                    ),
                )
                for number in range(generator.randint(0, 2))
            ),
        )
        galley = tuple(
            token
            for _ in range(generator.randint(0, 5))
            for token in _galley(
                text(generator.randint(1, 8)),
                page_index=generator.randint(0, 3),
                stream=generator.choice(tuple(GalleyStream)),
            )
        )
        alignment, pairings = _align(reference, galley)
        reference_count = len(reference_places(reference))
        assert sorted(
            i for pairing in pairings for i in pairing.reference_indices
        ) == list(range(reference_count))
        assert sorted(
            i for pairing in pairings for i in pairing.galley_indices
        ) == list(range(len(galley)))
        assert len(alignment.reference_pairing) == reference_count


# The anchors


def test_anchor_pairs_are_keys_unique_on_both_sides() -> None:
    # "a" is twice in the reference, "b" twice in galley's words.
    assert anchor_pairs(("a", "b", "a", "c"), ("a", "c", "b")) == ((3, 1),)
    assert anchor_pairs(("b", "c"), ("b", "c", "b")) == ((1, 1),)


def test_empty_key_is_never_an_anchor() -> None:
    assert anchor_pairs(("", "alpha"), ("", "alpha")) == ((1, 1),)


def test_anchored_pass_turns_off_difflib_automatic_junk() -> None:
    # With automatic junk, a key above 1% of a stretch of 200 tokens or
    # more is junk and never matched.
    keys = ("the",) * 300
    assert anchored_pass(keys, keys) == (Stretch(Operation.EQUAL, 0, 300, 0, 300),)


# Walking a replaced stretch


def test_word_unlike_the_one_across_is_missing_and_extra() -> None:
    alignment, _ = _align(
        _reference(_paragraph("il dit son nom")), _galley("il dit ' nom")
    )
    assert _pairing_of_reference(alignment, 2).state is State.MISSING
    assert _pairing_of_galley(alignment, 2).state is State.EXTRA


def test_running_head_before_a_misread_word_stays_extra() -> None:
    alignment, _ = _align(
        _reference(_paragraph("one alpha two")), _galley("one HISTORY 199 alqha two")
    )
    assert tuple(
        _pairing_of_galley(alignment, index).state for index in range(1, 4)
    ) == (
        State.EXTRA,
        State.EXTRA,
        State.CHANGED,
    )


def test_empty_keys_pair_only_with_empty_keys() -> None:
    alignment, _ = _align(_reference(_paragraph("one — two")), _galley("one x two"))
    assert _pairing_of_reference(alignment, 1).state is State.MISSING
    alignment, _ = _align(_reference(_paragraph("one — two")), _galley("one * two"))
    assert _pairing_of_reference(alignment, 1).state is State.CHANGED


def test_split_is_looked_for_only_at_the_current_position() -> None:
    # By the time the walk reaches "p" "our" in galley, it has passed "pour"
    # in the reference: no split.
    alignment, _ = _align(
        _reference(_paragraph("one pour xx yy two")), _galley("one zzzz qqqq p our two")
    )
    assert _pairing_of_reference(alignment, 1).state is State.MISSING


def test_split_joins_up_to_four_tokens() -> None:
    alignment, _ = _align(
        _reference(_paragraph("one interesting two")), _galley("one in ter est ing two")
    )
    assert _pairing_of_reference(alignment, 1).state is State.SPLIT
    assert _pairing_of_reference(alignment, 1).galley_indices == (1, 2, 3, 4)
    alignment, _ = _align(
        _reference(_paragraph("one interestingly two")),
        _galley("one in ter est ing ly two"),
    )
    assert _pairing_of_reference(alignment, 1).state is not State.SPLIT


def test_glued_joins_up_to_four_tokens() -> None:
    alignment, _ = _align(
        _reference(_paragraph("one a b c d two")), _galley("one abcd two")
    )
    assert _pairing_of_reference(alignment, 1).state is State.GLUED
    alignment, _ = _align(
        _reference(_paragraph("one a b c d e two")), _galley("one abcde two")
    )
    assert _pairing_of_reference(alignment, 1).state is not State.GLUED


def test_split_never_joins_a_token_with_an_empty_key() -> None:
    alignment, _ = _align(
        _reference(_paragraph("one replicate two")), _galley("one repli- — cate two")
    )
    assert _pairing_of_reference(alignment, 1).state is State.CHANGED


def test_split_of_a_marked_correction_is_reference_correction() -> None:
    reference = _reference(
        ReferenceBlock(
            ReferenceKind.PARAGRAPH,
            _words("to") + _words("replicate", marked=True) + _words("the"),
        )
    )
    alignment, _ = _align(reference, _galley("to repli- cate the"))
    pairing = _pairing_of_reference(alignment, 1)
    assert pairing.state is State.SPLIT
    assert pairing.subkind is Subkind.REFERENCE_CORRECTION


def test_glued_with_a_marked_correction_is_reference_correction() -> None:
    reference = _reference(
        ReferenceBlock(
            ReferenceKind.PARAGRAPH,
            _words("to") + _words("re", marked=True) + _words("plicate the"),
        )
    )
    alignment, _ = _align(reference, _galley("to replicate the"))
    pairing = _pairing_of_reference(alignment, 1)
    assert pairing.state is State.GLUED
    assert pairing.subkind is Subkind.REFERENCE_CORRECTION


def test_case_and_punctuation_together_are_punctuation() -> None:
    reference = ReferenceToken("Serfs.", marked_correction=False)
    assert changed_subkind(reference, "serfs") is Subkind.PUNCTUATION


def test_equal_keys_without_different_accents_are_letters() -> None:
    # The long s decomposes to s, so the keys are equal, but no accent
    # differs.
    reference = ReferenceToken("ſerfs", marked_correction=False)
    assert changed_subkind(reference, "serfs") is Subkind.LETTERS


def test_margin_note_whose_words_fit_the_body_waits_for_its_pass() -> None:
    reference = _reference(
        ReferenceBlock(ReferenceKind.MARGIN_NOTE, _words("Danegeld")),
        _paragraph("the tax"),
    )
    alignment, _ = _align(reference, _galley("Danegeld the tax"))
    assert _pairing_of_reference(alignment, 0).found_in is AlignmentPass.MARGIN_NOTES


# Passes 2 and 3 near the page


def test_leftover_is_not_paired_with_a_token_pages_away() -> None:
    # "including" was lost on page 9; a stray "includinq" on page 1 is not
    # its partner.
    reference = _reference(_paragraph("one two three including four"))
    galley = _galley("one includinq two", page_index=1) + _galley(
        "three four", page_index=9
    )
    alignment, _ = _align(reference, galley)
    assert _pairing_of_reference(alignment, 3).state is State.MISSING
    assert _pairing_of_galley(alignment, 1).state is State.EXTRA


def test_leftover_is_paired_with_a_token_on_the_next_page() -> None:
    reference = _reference(_paragraph("one two three including four"))
    galley = (
        _galley("one two three", page_index=8)
        + _galley("four", page_index=9)
        + _galley("including", page_index=9, stream=GalleyStream.NOTES)
    )
    alignment, _ = _align(reference, galley)
    assert _pairing_of_reference(alignment, 3).galley_indices == (4,)


def test_note_is_looked_for_near_the_page_of_its_reference() -> None:
    reference = ReferenceText(
        blocks=(_paragraph("the duke landed"), _paragraph("and took Palermo")),
        notes=(ReferenceNote("Footnote_1", (_paragraph("Amatus"),)),),
        note_references=(NoteReference("Footnote_1", Gap(Stream.BODY, 3)),),
        page_anchors=(),
        anchors_in_notes=(),
    )
    near = _galley("the duke landed Amatus", page_index=5) + _galley(
        "and took Palermo", page_index=9
    )
    alignment, _ = _align(reference, near)
    assert _pairing_of_reference(alignment, 6).state is State.MATCHED
    far = (
        _galley("the duke landed", page_index=5)
        + _galley("and took Palermo", page_index=9)
        + _galley("Amatus", page_index=9, stream=GalleyStream.NOTES)
    )
    alignment, _ = _align(reference, far)
    assert _pairing_of_reference(alignment, 6).state is State.MISSING


def test_margin_note_is_looked_for_near_the_paragraph_it_precedes() -> None:
    reference = _reference(
        _paragraph("alpha beta"),
        ReferenceBlock(ReferenceKind.MARGIN_NOTE, _words("Danegeld")),
        _paragraph("the tax"),
    )
    galley = _galley("alpha beta", page_index=1) + _galley(
        "Danegeld the tax", page_index=5
    )
    alignment, _ = _align(reference, galley)
    assert _pairing_of_reference(alignment, 2).state is State.MATCHED


def test_leftovers_are_taken_in_book_order() -> None:
    # galley lists its body before its notes, but its note "Amatus" is on
    # page 4, before the body's stray "Amatus" on page 5.
    reference = ReferenceText(
        blocks=(_paragraph("the duke"),),
        notes=(ReferenceNote("Footnote_1", (_paragraph("Amatus"),)),),
        note_references=(NoteReference("Footnote_1", Gap(Stream.BODY, 2)),),
        page_anchors=(),
        anchors_in_notes=(),
    )
    galley = (
        _galley("the duke", page_index=4)
        + _galley("Amatus", page_index=5)
        + _galley("Amatus", page_index=4, stream=GalleyStream.NOTES)
    )
    alignment, _ = _align(reference, galley)
    assert _pairing_of_reference(alignment, 2).galley_indices == (3,)
