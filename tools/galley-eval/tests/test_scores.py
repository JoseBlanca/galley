"""Tests of galley_eval.scores: the text and structure scores of one stage
output (spec section 6), on hand-made blocks."""

from galley.model import BlockKind
from galley_eval.align import GalleyStream, GalleyToken, align, reference_places
from galley_eval.galley_side import GalleyBlock, GalleyNoteReference
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
from galley_eval.scores import (
    BoundaryScores,
    GalleyKind,
    KindCount,
    MarginNoteScores,
    NoteScores,
    Part,
    Placement,
    block_kinds,
    galley_parts,
    margin_note_scores,
    note_scores,
    page_parts,
    paragraph_boundaries,
    reference_part,
    text_scores,
)


def _block(kind: ReferenceKind, text: str) -> ReferenceBlock:
    return ReferenceBlock(
        kind,
        tuple(ReferenceToken(word, marked_correction=False) for word in text.split()),
    )


def _paragraph(text: str) -> ReferenceBlock:
    return _block(ReferenceKind.PARAGRAPH, text)


def _reference(
    *blocks: ReferenceBlock,
    notes: tuple[ReferenceNote, ...] = (),
    note_references: tuple[NoteReference, ...] = (),
) -> ReferenceText:
    return ReferenceText(
        blocks=blocks,
        notes=notes,
        note_references=note_references,
        page_anchors=(),
        anchors_in_notes=(),
    )


def _tokens(
    text: str,
    block_id: str | None = None,
    *,
    page_index: int = 0,
    stream: GalleyStream = GalleyStream.BODY,
    edge_of_page: bool = False,
) -> tuple[GalleyToken, ...]:
    return tuple(
        GalleyToken(
            text=word,
            page_index=page_index,
            stream=stream,
            edge_of_page=edge_of_page,
            block_id=block_id,
        )
        for word in text.split()
    )


# Text scores


def test_token_error_rate_counts_errors_but_not_conventions() -> None:
    reference = _reference(_paragraph("“Yes,” the king went to York in 1066"))
    galley = _tokens('"Yes," the kinq went York in 1066') + _tokens(
        "7", edge_of_page=True
    )
    alignment = align(reference, galley)
    scores = text_scores(
        alignment,
        galley,
        parts=(Part.BODY,) * 8,
        placements=(Placement.SCORED,) * 8,
        galley_part=(Part.BODY,) * len(galley),
        galley_scored=(True,) * len(galley),
        repaired=None,
    )[Part.BODY]
    assert (
        scores.reference_tokens,
        scores.matched,
        scores.changed_convention,
        scores.changed_letters,
        scores.missing,
        scores.extra,
        scores.edge_of_page_extra,
        scores.repaired,
    ) == (8, 5, 1, 1, 1, 1, 1, None)
    # kinq, to and 7: three errors in eight reference tokens.
    assert scores.token_error_rate == 3 / 8


def test_unplaced_and_unscored_tokens_are_left_out_of_the_rate() -> None:
    reference = _reference(_paragraph("one two three four"))
    galley = _tokens("one two")
    scores = text_scores(
        align(reference, galley),
        galley,
        parts=(Part.BODY,) * 4,
        placements=(
            Placement.SCORED,
            Placement.SCORED,
            Placement.UNPLACED,
            Placement.NOT_SCORED,
        ),
        galley_part=(Part.BODY, Part.BODY),
        galley_scored=(True, True),
        repaired=(False, True, False, False),
    )[Part.BODY]
    assert (scores.reference_tokens, scores.unplaced, scores.missing) == (2, 1, 0)
    assert scores.repaired == 1
    assert scores.token_error_rate == 0.0


def test_extra_token_takes_the_part_of_most_of_its_page() -> None:
    reference = _reference(
        _paragraph("the text of the book"),
        _block(ReferenceKind.INDEX_ENTRY, "Rollo, 12"),
        _block(ReferenceKind.INDEX_ENTRY, "Rouen, 14"),
    )
    places = reference_places(reference)
    # The body on page 0, the index on page 1, with one body token there.
    page_indices = (0, 0, 0, 0, 1, 1, 1, 1, 1)
    parts_of_pages = page_parts(places, page_indices)
    assert parts_of_pages == {0: Part.BODY, 1: Part.INDEX}
    galley = _tokens("the text of the", page_index=0) + _tokens(
        "book Rollo, 12 Rouen, 14 INDEX", page_index=1
    )
    scores = text_scores(
        align(reference, galley),
        galley,
        parts=tuple(reference_part(place) for place in places),
        placements=(Placement.SCORED,) * len(places),
        galley_part=galley_parts(galley, parts_of_pages),
        galley_scored=(True,) * len(galley),
        repaired=None,
    )
    assert scores[Part.INDEX].extra == 1
    assert scores[Part.BODY].extra == 0
    assert scores[Part.INDEX].reference_tokens == 4


def test_extra_token_on_an_unscored_page_is_not_counted() -> None:
    reference = _reference(_paragraph("one two"))
    galley = _tokens("one two") + _tokens("stray", page_index=5)
    scores = text_scores(
        align(reference, galley),
        galley,
        parts=(Part.BODY, Part.BODY),
        placements=(Placement.SCORED, Placement.SCORED),
        galley_part=(Part.BODY,) * 3,
        galley_scored=(True, True, False),
        repaired=None,
    )
    assert scores[Part.BODY].extra == 0


# Paragraph boundaries

# Three paragraphs and, between the first two, a margin note.
_PARAGRAPHS = _reference(
    _paragraph("alpha beta gamma"),
    _block(ReferenceKind.MARGIN_NOTE, "side words"),
    _paragraph("delta epsilon zeta"),
    _paragraph("eta theta iota"),
)


def test_boundaries_right_and_wrong_give_precision_and_recall() -> None:
    galley = (
        _tokens("alpha beta gamma", "b1")
        + _tokens("side words", "m1", stream=GalleyStream.MARGIN_NOTES)
        + _tokens("delta epsilon", "b2")
        + _tokens("zeta eta theta iota", "b3")
    )
    places = reference_places(_PARAGRAPHS)
    scores = paragraph_boundaries(
        align(_PARAGRAPHS, galley), places, galley, (Part.BODY,) * len(places)
    )
    # b1|b2 is right (the margin note between makes no boundary);
    # b2|b3 falls inside "delta epsilon zeta"; eta's boundary is missed.
    assert scores[Part.BODY] == BoundaryScores(
        galley_boundaries=2,
        right=1,
        reference_boundaries=2,
        found=1,
        precision=0.5,
        recall=0.5,
    )


def test_boundary_with_extra_tokens_maps_to_the_next_aligned_token() -> None:
    galley = (
        _tokens("alpha beta gamma", "b1")
        + _tokens("HEAD 12 delta epsilon zeta", "b2")
        + _tokens("eta theta iota", "b3")
        + _tokens("side words", "m1", stream=GalleyStream.MARGIN_NOTES)
    )
    places = reference_places(_PARAGRAPHS)
    scores = paragraph_boundaries(
        align(_PARAGRAPHS, galley), places, galley, (Part.BODY,) * len(places)
    )
    assert (scores[Part.BODY].precision, scores[Part.BODY].recall) == (1.0, 1.0)


# Block kinds


def test_block_kind_is_that_of_the_galley_block_holding_most_tokens() -> None:
    reference = _reference(
        _block(ReferenceKind.HEADING, "CHAPTER ONE"),
        _paragraph("words of the chapter"),
    )
    galley = _tokens("CHAPTER", "h1") + _tokens("ONE words of the chapter", "p1")
    galley_blocks = frozendict(
        {
            "h1": GalleyBlock(
                kind=BlockKind.HEADING, stream=GalleyStream.BODY, note_id=None
            ),
            "p1": GalleyBlock(
                kind=BlockKind.PARAGRAPH, stream=GalleyStream.BODY, note_id=None
            ),
        }
    )
    places = reference_places(reference)
    kinds = block_kinds(
        align(reference, galley),
        places,
        galley,
        galley_blocks,
        (Part.BODY,) * len(places),
    )
    # The heading has one token in h1 and one in p1: the first wins a tie.
    assert kinds[Part.BODY] == (
        KindCount(ReferenceKind.HEADING, GalleyKind.HEADING, 1),
        KindCount(ReferenceKind.PARAGRAPH, GalleyKind.PARAGRAPH, 1),
    )


def test_block_with_no_aligned_token_has_kind_none() -> None:
    reference = _reference(_paragraph("present here"), _paragraph("lost entirely"))
    galley = _tokens("present here", "p1")
    galley_blocks = frozendict(
        {
            "p1": GalleyBlock(
                kind=BlockKind.PARAGRAPH, stream=GalleyStream.BODY, note_id=None
            )
        }
    )
    places = reference_places(reference)
    kinds = block_kinds(
        align(reference, galley), places, galley, galley_blocks, (Part.BODY,) * 4
    )
    assert KindCount(ReferenceKind.PARAGRAPH, GalleyKind.NONE, 1) in kinds[Part.BODY]


# Notes


def _note(note_id: str, text: str) -> ReferenceNote:
    return ReferenceNote(note_id, (_paragraph(text),))


_NOTES_REFERENCE = _reference(
    _paragraph("first second third fourth fifth sixth seventh eighth ninth tenth"),
    notes=(
        _note("Footnote_1", "Ibid. page forty"),
        _note("Footnote_2", "See Freeman volume two"),
        _note("Footnote_3", "Quoted by Orderic"),
    ),
    note_references=(
        NoteReference("Footnote_1", Gap(Stream.BODY, 2)),
        NoteReference("Footnote_2", Gap(Stream.BODY, 6)),
        NoteReference("Footnote_3", Gap(Stream.BODY, 9)),
    ),
)

_NOTE_BLOCKS = frozendict(
    {
        "p1": GalleyBlock(
            kind=BlockKind.PARAGRAPH, stream=GalleyStream.BODY, note_id=None
        ),
        "n1": GalleyBlock(
            kind=BlockKind.PARAGRAPH, stream=GalleyStream.NOTES, note_id="n-p0000-001"
        ),
    }
)


def _notes_galley(
    tokens_before: int,
) -> tuple[tuple[GalleyToken, ...], tuple[GalleyNoteReference, ...]]:
    # Note 1 as a note, note 2 left in the body, note 3 lost.
    galley = _tokens(
        "first second third fourth fifth sixth See Freeman volume two "
        "seventh eighth ninth tenth",
        "p1",
    ) + _tokens("Ibid. page forty", "n1", stream=GalleyStream.NOTES)
    return galley, (
        GalleyNoteReference(
            note_id="n-p0000-001", block_id="p1", tokens_before=tokens_before
        ),
    )


def test_notes_are_found_as_notes_in_the_body_or_missing() -> None:
    galley, references = _notes_galley(tokens_before=2)
    places = reference_places(_NOTES_REFERENCE)
    scores = note_scores(
        _NOTES_REFERENCE,
        align(_NOTES_REFERENCE, galley),
        places,
        galley,
        _NOTE_BLOCKS,
        references,
    )
    assert scores == NoteScores(as_note=1, in_body=1, missing=1, reference_right=1)


def test_note_reference_more_than_three_tokens_away_is_wrong() -> None:
    # Before "seventh" (gap 6 of the reference), 4 tokens after gap 2.
    galley, references = _notes_galley(tokens_before=10)
    places = reference_places(_NOTES_REFERENCE)
    scores = note_scores(
        _NOTES_REFERENCE,
        align(_NOTES_REFERENCE, galley),
        places,
        galley,
        _NOTE_BLOCKS,
        references,
    )
    assert scores.reference_right == 0


def test_note_reference_three_tokens_away_is_right() -> None:
    # Before "sixth": gap 5, three tokens after Gutenberg's gap 2.
    galley, references = _notes_galley(tokens_before=5)
    places = reference_places(_NOTES_REFERENCE)
    scores = note_scores(
        _NOTES_REFERENCE,
        align(_NOTES_REFERENCE, galley),
        places,
        galley,
        _NOTE_BLOCKS,
        references,
    )
    assert scores.reference_right == 1


# Margin notes

_MARGIN_REFERENCE = _reference(
    _paragraph("opening words here"),
    _block(ReferenceKind.MARGIN_NOTE, "Becket exiled"),
    _paragraph("the archbishop left England"),
    _block(ReferenceKind.MARGIN_NOTE, "Henry returns"),
    _paragraph("the king came back"),
    _block(ReferenceKind.MARGIN_NOTE, "Lost margin note"),
)


def _margin_scores(galley: tuple[GalleyToken, ...]) -> MarginNoteScores:
    return margin_note_scores(
        align(_MARGIN_REFERENCE, galley), reference_places(_MARGIN_REFERENCE), galley
    )


# "Becket exiled" just before its paragraph; "Henry returns" one block
# late, after the paragraph it precedes in the reference; the third lost.
_MARGIN_GALLEY = (
    _tokens("opening words here", "p1")
    + _tokens("Becket exiled", "m1", stream=GalleyStream.MARGIN_NOTES)
    + _tokens("the archbishop left England", "p2")
    + _tokens("the king came back", "p3")
    + _tokens("Henry returns", "m2", stream=GalleyStream.MARGIN_NOTES)
)


def test_margin_notes_found_and_their_position_scored() -> None:
    assert _margin_scores(_MARGIN_GALLEY) == (
        MarginNoteScores(as_margin_note=2, in_body=0, missing=1, position_right=1)
    )


def test_margin_note_in_a_paragraph_is_in_the_body() -> None:
    galley = (
        _tokens("opening words here", "p1")
        + _tokens("Becket exiled the archbishop left England", "p2")
        + _tokens("Henry returns", "m2", stream=GalleyStream.MARGIN_NOTES)
        + _tokens("the king came back", "p3")
    )
    assert _margin_scores(galley) == MarginNoteScores(
        as_margin_note=1, in_body=1, missing=1, position_right=1
    )


def test_boundary_inside_a_split_word_is_wrong() -> None:
    reference = _reference(_paragraph("alpha beta replicate"), _paragraph("delta"))
    galley = _tokens("alpha beta repli-", "b1") + _tokens("cate delta", "b2")
    places = reference_places(reference)
    scores = paragraph_boundaries(
        align(reference, galley), places, galley, (Part.BODY,) * len(places)
    )
    assert (scores[Part.BODY].right, scores[Part.BODY].galley_boundaries) == (0, 1)


def test_margin_notes_one_after_another_both_precede_their_paragraph() -> None:
    reference = _reference(
        _paragraph("opening words here"),
        _block(ReferenceKind.MARGIN_NOTE, "Becket exiled"),
        _block(ReferenceKind.MARGIN_NOTE, "Henry returns"),
        _paragraph("the archbishop left England"),
    )
    galley = (
        _tokens("opening words here", "p1")
        + _tokens("Becket exiled", "m1", stream=GalleyStream.MARGIN_NOTES)
        + _tokens("Henry returns", "m2", stream=GalleyStream.MARGIN_NOTES)
        + _tokens("the archbishop left England", "p2")
    )
    scores = margin_note_scores(
        align(reference, galley),
        reference_places(reference),
        galley,
    )
    assert scores.position_right == 2


# Every term of the error rate, on one literal stretch


def test_every_state_and_subkind_is_counted_once_and_corrections_apart() -> None:
    reference = _reference(
        ReferenceBlock(
            ReferenceKind.PARAGRAPH,
            tuple(
                ReferenceToken(word, marked_correction=False)
                for word in [
                    "aaa",
                    "one",
                    "bbb",
                    "“two”",
                    "ccc",
                    "Three",
                    "ddd",
                    "four,",
                    "eee",
                    "Léon",
                    "fff",
                    "house",
                    "ggg",
                    "replicate",
                    "hhh",
                    "of",
                    "these",
                    "iii",
                    "lost",
                    "jjj",
                ]
            )
            + (ReferenceToken("Corrected", marked_correction=True),)
            + (ReferenceToken("kkk", marked_correction=False),),
        )
    )
    galley = _tokens(
        'aaa one bbb "two" ccc THREE ddd four eee Leon fff honse ggg repli- cate '
        "hhh ofthese iii jjj Corected stray kkk"
    )
    count = len(reference_places(reference))
    scores = text_scores(
        align(reference, galley),
        galley,
        parts=(Part.BODY,) * count,
        placements=(Placement.SCORED,) * count,
        galley_part=(Part.BODY,) * len(galley),
        galley_scored=(True,) * len(galley),
        repaired=None,
    )[Part.BODY]
    assert (
        scores.reference_tokens,
        scores.matched,
        scores.changed_convention,
        scores.changed_case,
        scores.changed_punctuation,
        scores.changed_diacritic,
        scores.changed_letters,
        scores.split,
        scores.glued,
        scores.missing,
        scores.extra,
        scores.reference_correction,
        scores.galley_tokens,
    ) == (22, 12, 1, 1, 1, 1, 1, 1, 2, 1, 1, 1, len(galley))
    # case, punctuation, diacritic, letters, split, 2 glued, missing,
    # extra; not the convention nor the correction.
    assert scores.token_error_rate == 9 / 22


def test_not_scored_and_unplaced_add_up_with_the_scored_tokens() -> None:
    reference = _reference(_paragraph("one two three four"))
    galley = _tokens("one two three four") + _tokens("plate", page_index=9)
    scores = text_scores(
        align(reference, galley),
        galley,
        parts=(Part.BODY,) * 4,
        placements=(
            Placement.SCORED,
            Placement.NOT_SCORED,
            Placement.UNPLACED,
            Placement.SCORED,
        ),
        galley_part=(Part.BODY,) * 5,
        galley_scored=(True, True, True, True, False),
        repaired=None,
    )[Part.BODY]
    assert (
        scores.reference_tokens,
        scores.not_scored,
        scores.unplaced,
        scores.extra,
        scores.galley_tokens,
    ) == (2, 1, 1, 0, 5)


# Parts


def test_reference_part_of_notes_tables_figures_and_headings() -> None:
    reference = _reference(
        _block(ReferenceKind.HEADING, "Title"),
        _block(ReferenceKind.TABLE, "cell"),
        _block(ReferenceKind.FIGURE, "caption"),
        _block(ReferenceKind.QUOTE, "verse"),
        notes=(_note("Footnote_1", "Ibid."),),
    )
    assert tuple(reference_part(place) for place in reference_places(reference)) == (
        Part.BODY,
        Part.TABLES,
        Part.FIGURES,
        Part.BODY,
        Part.NOTES,
    )


def test_page_part_on_a_tie_is_the_first_in_part_order() -> None:
    reference = _reference(
        _block(ReferenceKind.INDEX_ENTRY, "Rollo"),
        _block(ReferenceKind.TABLE, "cell"),
        _paragraph("text"),
        notes=(_note("Footnote_1", "Ibid."),),
    )
    places = reference_places(reference)
    # Page 0: an index token and a table token; page 1: body and notes.
    assert page_parts(places, (0, 0, 1, 1)) == {0: Part.INDEX, 1: Part.BODY}


def test_galley_token_on_a_page_with_no_reference_token_is_in_the_body() -> None:
    galley = _tokens("one", page_index=0) + _tokens("two", page_index=7)
    assert galley_parts(galley, frozendict({0: Part.INDEX})) == (
        Part.INDEX,
        Part.BODY,
    )


def test_boundaries_and_kinds_are_counted_in_the_part_of_the_block() -> None:
    reference = _reference(
        _paragraph("alpha beta"),
        _block(ReferenceKind.INDEX_ENTRY, "Rollo, 12"),
        _block(ReferenceKind.INDEX_ENTRY, "Rouen, 14"),
    )
    galley = _tokens("alpha beta", "b1") + _tokens("Rollo, 12 Rouen, 14", "b2")
    places = reference_places(reference)
    parts = tuple(reference_part(place) for place in places)
    alignment = align(reference, galley)
    boundaries = paragraph_boundaries(alignment, places, galley, parts)
    assert (
        boundaries[Part.INDEX].reference_boundaries,
        boundaries[Part.INDEX].right,
    ) == (
        2,
        1,
    )
    assert boundaries[Part.BODY].reference_boundaries == 0
    galley_blocks = frozendict(
        {
            "b1": GalleyBlock(
                kind=BlockKind.PARAGRAPH, stream=GalleyStream.BODY, note_id=None
            ),
            "b2": GalleyBlock(
                kind=BlockKind.INDEX_ENTRY, stream=GalleyStream.BODY, note_id=None
            ),
        }
    )
    kinds = block_kinds(alignment, places, galley, galley_blocks, parts)
    assert kinds[Part.INDEX] == (
        KindCount(ReferenceKind.INDEX_ENTRY, GalleyKind.INDEX_ENTRY, 2),
    )
    assert kinds[Part.BODY] == (
        KindCount(ReferenceKind.PARAGRAPH, GalleyKind.PARAGRAPH, 1),
    )


# Boundaries: claimed gaps, no token after, glued


def test_two_galley_boundaries_on_one_gap_are_one_right_and_one_wrong() -> None:
    reference = _reference(_paragraph("alpha beta"), _paragraph("gamma delta"))
    # An extra-only block "HEAD" between: both its boundaries map before
    # "gamma".
    galley = (
        _tokens("alpha beta", "b1")
        + _tokens("HEAD", "b2")
        + _tokens("gamma delta", "b3")
    )
    places = reference_places(reference)
    scores = paragraph_boundaries(
        align(reference, galley), places, galley, (Part.BODY,) * 4
    )[Part.BODY]
    assert (scores.galley_boundaries, scores.right, scores.found) == (2, 1, 1)


def test_boundary_with_no_aligned_token_after_maps_after_the_last() -> None:
    reference = _reference(_paragraph("alpha beta"), _paragraph("gamma"))
    # galley ends with a block of extra tokens, whose boundary maps after
    # "gamma", the end of the reference: no boundary there.
    galley = (
        _tokens("alpha beta", "b1") + _tokens("gamma", "b2") + _tokens("12 HEAD", "b3")
    )
    places = reference_places(reference)
    scores = paragraph_boundaries(
        align(reference, galley), places, galley, (Part.BODY,) * 3
    )[Part.BODY]
    assert (scores.galley_boundaries, scores.right) == (2, 1)


def test_boundary_before_a_glued_token_maps_before_its_first_word() -> None:
    reference = _reference(_paragraph("alpha beta"), _paragraph("of these words"))
    galley = _tokens("alpha beta", "b1") + _tokens("ofthese words", "b2")
    places = reference_places(reference)
    scores = paragraph_boundaries(
        align(reference, galley), places, galley, (Part.BODY,) * 5
    )[Part.BODY]
    assert scores.right == 1


# Notes and margin notes at exactly half


def test_note_with_half_its_tokens_in_a_galley_note_is_found_as_a_note() -> None:
    reference = _reference(
        _paragraph("first second third fourth"),
        notes=(_note("Footnote_1", "Ibid. page forty two"),),
        note_references=(NoteReference("Footnote_1", Gap(Stream.BODY, 4)),),
    )
    galley = _tokens("first second third fourth page forty", "p1") + _tokens(
        "Ibid. two", "n1", stream=GalleyStream.NOTES
    )
    scores = note_scores(
        reference,
        align(reference, galley),
        reference_places(reference),
        galley,
        _NOTE_BLOCKS,
        (
            # At the end of its block, after "forty".
            GalleyNoteReference(note_id="n-p0000-001", block_id="p1", tokens_before=6),
        ),
    )
    assert (scores.as_note, scores.in_body, scores.missing) == (1, 0, 0)
    # The reference after the last token of p1 maps after "fourth": gap 4.
    assert scores.reference_right == 1


def test_note_with_half_in_the_body_and_the_rest_lost_is_in_the_body() -> None:
    reference = _reference(
        _paragraph("first second third fourth"),
        notes=(_note("Footnote_1", "Ibid. page forty two"),),
        note_references=(NoteReference("Footnote_1", Gap(Stream.BODY, 4)),),
    )
    galley = _tokens("first second third fourth page forty", "p1")
    scores = note_scores(
        reference,
        align(reference, galley),
        reference_places(reference),
        galley,
        _NOTE_BLOCKS,
        (),
    )
    # Two of its four tokens are aligned, both in the body: all its
    # aligned tokens, so more than half.
    assert (scores.as_note, scores.in_body, scores.missing) == (0, 1, 0)


def test_margin_note_with_half_its_tokens_in_a_margin_note_is_found() -> None:
    reference = _reference(
        _paragraph("opening words here"),
        _block(ReferenceKind.MARGIN_NOTE, "Becket exiled abroad again"),
        _paragraph("the archbishop left England"),
    )
    galley = (
        _tokens("opening words here", "p1")
        + _tokens("Becket exiled", "m1", stream=GalleyStream.MARGIN_NOTES)
        + _tokens("abroad again the archbishop left England", "p2")
    )
    scores = margin_note_scores(
        align(reference, galley), reference_places(reference), galley
    )
    assert (scores.as_margin_note, scores.in_body) == (1, 0)


def test_note_reference_at_the_end_of_its_block_is_after_its_last_token() -> None:
    reference = _reference(
        _paragraph("first second third fourth fifth sixth seventh eighth"),
        notes=(_note("Footnote_1", "Ibid. page forty"),),
        note_references=(NoteReference("Footnote_1", Gap(Stream.BODY, 7)),),
    )
    galley = (
        _tokens("first second third fourth", "p1")
        + _tokens("fifth sixth seventh eighth", "p2")
        + _tokens("Ibid. page forty", "n1", stream=GalleyStream.NOTES)
    )
    scores = note_scores(
        reference,
        align(reference, galley),
        reference_places(reference),
        galley,
        _NOTE_BLOCKS,
        (GalleyNoteReference(note_id="n-p0000-001", block_id="p1", tokens_before=4),),
    )
    # After "fourth" is gap 4, three tokens from Gutenberg's 7; before
    # "fourth" would be 3, four tokens away.
    assert scores.reference_right == 1


def test_galley_kinds_are_galleys_block_kinds_and_none() -> None:
    # A galley block's kind is read into a GalleyKind by its value.
    assert {kind.value for kind in GalleyKind} == {kind.value for kind in BlockKind} | {
        "none"
    }
