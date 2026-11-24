"""Tests of galley_eval.note_links: the wrong note links and the joined
notes (spec section 6, "Wrong note links and joined notes"), on made-up
notes."""

from galley.model import BlockKind
from galley_eval.align import GalleyStream, GalleyToken, align, reference_places
from galley_eval.galley_side import GalleyBlock, GalleyNoteReference
from galley_eval.note_links import (
    JoinedNote,
    LinkFault,
    NoteLinks,
    WrongLink,
    begins_as,
    note_links,
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

_BODY = "alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu nu xi"


def _paragraph(text: str) -> ReferenceBlock:
    return ReferenceBlock(
        ReferenceKind.PARAGRAPH,
        tuple(ReferenceToken(word, marked_correction=False) for word in text.split()),
    )


def _reference(notes: tuple[tuple[str, int], ...], *texts: str) -> ReferenceText:
    """The body _BODY, and a note of each text, referenced at the body
    gap given in `notes` beside its id."""
    return ReferenceText(
        blocks=(_paragraph(_BODY),),
        notes=tuple(
            ReferenceNote(f"Footnote_{number}", (_paragraph(text),))
            for number, text in enumerate(texts, start=1)
        ),
        note_references=tuple(
            NoteReference(note_id, Gap(Stream.BODY, gap)) for note_id, gap in notes
        ),
        page_anchors=(),
        anchors_in_notes=(),
    )


def _tokens(
    text: str, block_id: str, *, page_index: int, stream: GalleyStream
) -> tuple[GalleyToken, ...]:
    return tuple(
        GalleyToken(
            text=word,
            page_index=page_index,
            stream=stream,
            edge_of_page=False,
            block_id=block_id,
        )
        for word in text.split()
    )


def _galley(
    *notes: str, page_index: int = 7
) -> tuple[tuple[GalleyToken, ...], frozendict[str, GalleyBlock]]:
    """The body _BODY in block "p1", and one galley note n-p0007-00k in block
    "nk" for each text."""
    tokens = _tokens(_BODY, "p1", page_index=page_index, stream=GalleyStream.BODY)
    blocks = {
        "p1": GalleyBlock(
            kind=BlockKind.PARAGRAPH, stream=GalleyStream.BODY, note_id=None
        )
    }
    for number, text in enumerate(notes, start=1):
        tokens += _tokens(
            text, f"n{number}", page_index=page_index, stream=GalleyStream.NOTES
        )
        blocks[f"n{number}"] = GalleyBlock(
            kind=BlockKind.PARAGRAPH,
            stream=GalleyStream.NOTES,
            note_id=f"n-p0007-{number:03d}",
        )
    return tokens, frozendict(blocks)


def _link(note: int, tokens_before: int) -> GalleyNoteReference:
    return GalleyNoteReference(
        note_id=f"n-p0007-{note:03d}", block_id="p1", tokens_before=tokens_before
    )


def _links(
    reference: ReferenceText,
    galley: tuple[GalleyToken, ...],
    blocks: frozendict[str, GalleyBlock],
    *references: GalleyNoteReference,
) -> NoteLinks:
    return note_links(
        reference,
        align(reference, galley),
        reference_places(reference),
        galley,
        blocks,
        references,
    )


_FREEMAN = "Freeman, Norman Conquest, vol. ii. p. 40."
_STUBBS = "Stubbs, Constitutional History, i. 210."


def test_link_to_the_note_before_gutenbergs_is_wrong_with_another_note() -> None:
    reference = _reference((("Footnote_1", 2), ("Footnote_2", 10)), _FREEMAN, _STUBBS)
    galley, blocks = _galley(_FREEMAN, _STUBBS)
    found = _links(reference, galley, blocks, _link(1, 2), _link(1, 10))
    assert found.wrong_links == (
        WrongLink(
            page_index=7,
            note_id="n-p0007-001",
            block_id="p1",
            fault=LinkFault.OTHER_NOTE,
            reference_notes=("Footnote_2",),
        ),
    )


def test_link_where_gutenberg_has_no_reference_is_wrong_with_no_reference() -> None:
    # Gap 6 is 4 gaps from both of Gutenberg's references.
    reference = _reference((("Footnote_1", 2), ("Footnote_2", 10)), _FREEMAN, _STUBBS)
    galley, blocks = _galley(_FREEMAN, _STUBBS)
    found = _links(reference, galley, blocks, _link(2, 6))
    assert found.wrong_links == (
        WrongLink(
            page_index=7,
            note_id="n-p0007-002",
            block_id="p1",
            fault=LinkFault.NO_REFERENCE,
            reference_notes=(),
        ),
    )


def test_link_three_gaps_from_gutenbergs_reference_is_right() -> None:
    reference = _reference((("Footnote_1", 2), ("Footnote_2", 10)), _FREEMAN, _STUBBS)
    galley, blocks = _galley(_FREEMAN, _STUBBS)
    assert _links(reference, galley, blocks, _link(1, 5)).wrong_links == ()


def test_link_to_the_first_part_of_a_note_cut_in_two_is_right() -> None:
    # Most of the reference note's tokens are in the second galley note.
    whole = (
        "Freeman, Norman Conquest, vol. ii. p. 40, where the charters of the "
        "abbey of Ely are printed and their witnesses named one by one."
    )
    reference = _reference((("Footnote_1", 2),), whole)
    galley, blocks = _galley(
        "Freeman, Norman Conquest,",
        "vol. ii. p. 40, where the charters of the abbey of Ely are printed "
        "and their witnesses named one by one.",
    )
    assert _links(reference, galley, blocks, _link(1, 2)).wrong_links == ()


def test_links_to_short_notes_that_begin_alike_are_right() -> None:
    reference = _reference(
        (("Footnote_1", 2), ("Footnote_2", 6), ("Footnote_3", 10)),
        "D. B. i. 336 b.",
        "D. B. i. 336 b.",
        "D. B. i. 298.",
    )
    galley, blocks = _galley("D. B. i. 336 b.", "D. B. i. 336 b.", "D. B. i. 298.")
    found = _links(reference, galley, blocks, _link(1, 2), _link(2, 6), _link(3, 10))
    assert found.wrong_links == ()


def test_link_to_a_note_whose_marker_is_a_token_leaves_the_marker_out() -> None:
    # With "12" kept, "12dbi2" against "dbi2", cut to 4, is a ratio of 0.5.
    reference = _reference((("Footnote_1", 2),), "D. B. i. 2.")
    galley, blocks = _galley("12 D. B. i. 2.")
    marked = frozendict(
        blocks
        | {
            "n1": GalleyBlock(
                kind=BlockKind.PARAGRAPH,
                stream=GalleyStream.NOTES,
                note_id="n-p0007-001",
                marker_tokens=1,
            )
        }
    )
    assert _links(reference, galley, marked, _link(1, 2)).wrong_links == ()
    assert _links(reference, galley, blocks, _link(1, 2)).wrong_links != ()


def test_galley_note_that_holds_the_next_notes_start_is_joined() -> None:
    reference = _reference((("Footnote_1", 2), ("Footnote_2", 10)), _FREEMAN, _STUBBS)
    galley, blocks = _galley(f"{_FREEMAN} 2 {_STUBBS}", page_index=31)
    assert _links(reference, galley, blocks).joined_notes == (
        JoinedNote(
            page_index=31,
            note_id="n-p0007-001",
            reference_note="Footnote_1",
            next_reference_note="Footnote_2",
        ),
    )


def test_galley_note_a_few_characters_longer_than_its_note_is_not_joined() -> None:
    # "ab" begins as "abbotsamson", but is under 4 characters.
    reference = _reference(
        (("Footnote_1", 2), ("Footnote_2", 10)), _FREEMAN, "Abbot Samson, i. 4."
    )
    galley, blocks = _galley(f"{_FREEMAN} Ab")
    assert _links(reference, galley, blocks).joined_notes == ()


def test_texts_begin_alike_by_their_first_characters() -> None:
    assert begins_as("jjistenglawii457", "histenglawii457")
    assert not begins_as("dbi27percinges", "dbi284baettune")
    assert not begins_as("", "dbi2")
