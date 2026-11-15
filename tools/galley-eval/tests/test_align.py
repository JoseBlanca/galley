"""Tests of galley_eval.align: the alignment key, the anchored pass, the
three passes, and the states and subkinds of the tokens (spec section 1,
"Alignment key", and section 5, "Alignment" and "Differences")."""

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
    alignment = align(reference_places(reference), galley)
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
    assert pairing.galley == (1,)


def test_replaced_token_is_paired_as_changed() -> None:
    alignment, _ = _align(
        _reference(_paragraph("the Normans in Sicily")),
        _galley("the Norrnans in Sicily"),
    )
    pairing = _pairing_of_reference(alignment, 1)
    assert pairing.state is State.CHANGED
    assert pairing.subkind is Subkind.LETTERS
    assert pairing.reference == (1,)
    assert pairing.galley == (1,)


def test_hyphenated_word_is_a_split_of_two() -> None:
    alignment, _ = _align(
        _reference(_paragraph("to replicate the text")),
        _galley("to repli- cate the text"),
    )
    pairing = _pairing_of_reference(alignment, 1)
    assert pairing.state is State.SPLIT
    assert pairing.reference == (1,)
    assert pairing.galley == (1, 2)
    assert _pairing_of_galley(alignment, 2) == pairing


def test_words_without_spaces_are_glued_of_three() -> None:
    alignment, _ = _align(
        _reference(_paragraph("many pamphlets published on it")),
        _galley("many pamphletspublishedon it"),
    )
    pairing = _pairing_of_reference(alignment, 2)
    assert pairing.state is State.GLUED
    assert pairing.reference == (1, 2, 3)
    assert pairing.galley == (1,)
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
    assert pairing.galley == ()
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
        _pairing_of_reference(alignment, index).galley for index in note_tokens
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
    assert _pairing_of_reference(alignment, 0).galley == (2,)


def test_margin_note_out_of_order_among_galley_notes_is_found_by_the_last_pass() -> (
    None
):
    # galley put the first margin note among the notes of a later page, so
    # that in book order it comes after the second; the margin notes pass
    # can align only one of them in order, the last pass finds the other.
    reference = _reference(
        ReferenceBlock(ReferenceKind.MARGIN_NOTE, _words("Danegeld levied")),
        _paragraph("the tax"),
        ReferenceBlock(ReferenceKind.MARGIN_NOTE, _words("Hidage assessed")),
        _paragraph("the hide"),
    )
    galley = (
        _galley("the tax", page_index=1)
        + _galley("Hidage assessed", page_index=2, stream=GalleyStream.MARGIN_NOTE)
        + _galley("the hide", page_index=2)
        + _galley("Danegeld levied", page_index=3, stream=GalleyStream.NOTE)
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
    galley = _galley("the duke") + _galley("landed", stream=GalleyStream.NOTE)
    alignment, _ = _align(reference, galley)
    assert _pairing_of_reference(alignment, 2).found_in is AlignmentPass.REMAINDER


# The share of reference tokens aligned to an equal key


def test_equal_key_share_counts_matched_and_changed_with_equal_keys() -> None:
    places = reference_places(_reference(_paragraph("the Normans, in Sicilv")))
    galley = _galley("the Normans in Sicily")
    alignment = align(places, galley)
    # "the", "Normans," and "in" have equal keys; "Sicilv" does not.
    assert equal_key_share(alignment, places, galley) == 0.75
