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
        KindCount("heading", "heading", 1),
        KindCount("paragraph", "paragraph", 1),
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
    assert KindCount("paragraph", "none", 1) in kinds[Part.BODY]


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


def _margin_scores(
    galley: tuple[GalleyToken, ...], *, margin_notes_moved: bool
) -> MarginNoteScores:
    return margin_note_scores(
        align(_MARGIN_REFERENCE, galley),
        reference_places(_MARGIN_REFERENCE),
        galley,
        margin_notes_moved=margin_notes_moved,
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
    assert _margin_scores(_MARGIN_GALLEY, margin_notes_moved=False) == (
        MarginNoteScores(as_margin_note=2, in_body=0, missing=1, position_right=1)
    )


def test_margin_notes_moved_by_gutenberg_have_no_position_score() -> None:
    assert _margin_scores(_MARGIN_GALLEY, margin_notes_moved=True) == (
        MarginNoteScores(as_margin_note=2, in_body=0, missing=1, position_right=None)
    )


def test_margin_note_in_a_paragraph_is_in_the_body() -> None:
    galley = (
        _tokens("opening words here", "p1")
        + _tokens("Becket exiled the archbishop left England", "p2")
        + _tokens("Henry returns", "m2", stream=GalleyStream.MARGIN_NOTES)
        + _tokens("the king came back", "p3")
    )
    assert _margin_scores(galley, margin_notes_moved=False) == MarginNoteScores(
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
        margin_notes_moved=False,
    )
    assert scores.position_right == 2
