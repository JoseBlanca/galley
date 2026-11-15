"""Tests of galley_eval.pages: the page of each reference token, unplaced
tokens and anchor mismatches (spec section 5, "Pages")."""

from galley_eval.align import (
    GalleyStream,
    GalleyToken,
    align,
)
from galley_eval.pages import AnchorPage, printed_page_number, reference_pages
from galley_eval.reader import (
    Gap,
    NoteReference,
    PageAnchor,
    ReferenceBlock,
    ReferenceKind,
    ReferenceNote,
    ReferenceText,
    ReferenceToken,
    Stream,
)

NO_EXCLUDED_PAGES: frozenset[int] = frozenset()


def _block(text: str, kind: ReferenceKind = ReferenceKind.PARAGRAPH) -> ReferenceBlock:
    return ReferenceBlock(
        kind,
        tuple(ReferenceToken(word, marked_correction=False) for word in text.split()),
    )


def _reference(
    *blocks: ReferenceBlock,
    anchors: tuple[tuple[str, int], ...] = (),
    notes: tuple[ReferenceNote, ...] = (),
    note_references: tuple[NoteReference, ...] = (),
) -> ReferenceText:
    return ReferenceText(
        blocks=blocks,
        notes=notes,
        note_references=note_references,
        page_anchors=tuple(
            PageAnchor(printed, Gap(Stream.BODY, index)) for printed, index in anchors
        ),
        anchors_in_notes=(),
    )


def _galley(*pages: tuple[int, str]) -> tuple[GalleyToken, ...]:
    return tuple(
        GalleyToken(
            text=word,
            page_index=page_index,
            stream=GalleyStream.BODY,
            edge_of_page=False,
            block_id=None,
        )
        for page_index, text in pages
        for word in text.split()
    )


def _pages(
    reference: ReferenceText,
    galley: tuple[GalleyToken, ...],
    exclude_pages: frozenset[int] = NO_EXCLUDED_PAGES,
) -> tuple[tuple[int | None, ...], tuple[AnchorPage, ...]]:
    found = reference_pages(reference, align(reference, galley), galley, exclude_pages)
    return found.page_indices, found.anchors


def test_aligned_token_takes_the_page_of_its_galley_token() -> None:
    pages, _ = _pages(
        _reference(_block("alpha beta gamma")), _galley((3, "alpha beta"), (4, "gamma"))
    )
    assert pages == (3, 3, 4)


def test_printed_page_number_reads_arabic_and_roman_numbers() -> None:
    assert printed_page_number("199") == 199
    assert printed_page_number("vii") == 7
    assert printed_page_number("XIV") == 14
    assert printed_page_number("Plate") is None


def test_unaligned_body_token_takes_the_page_of_the_anchor_before_it() -> None:
    # Printed page 11 starts at "delta"; "delta" is lost. Its anchor's
    # offset is the median of 16 - 11 over the tokens after it: 5, so
    # "delta" is on page 16, not on page 15 of "gamma" before it.
    reference = _reference(
        _block("alpha beta gamma delta epsilon zeta"), anchors=(("10", 0), ("11", 3))
    )
    galley = _galley((15, "alpha beta gamma"), (16, "epsilon zeta"))
    pages, anchors = _pages(reference, galley)
    assert pages[3] == 16
    assert tuple((anchor.offset, anchor.page_index) for anchor in anchors) == (
        (5, 15),
        (5, 16),
    )


def test_anchor_offset_is_the_median_over_its_tokens() -> None:
    # The first word after the anchor aligned to a word of the page before
    # (spec section 2): the median of 4, 5 and 5 is still 5.
    reference = _reference(_block("alpha beta gamma delta"), anchors=(("11", 1),))
    galley = _galley((15, "alpha beta"), (16, "gamma delta"))
    _, anchors = _pages(reference, galley)
    assert anchors[0].offset == 5
    assert anchors[0].page_index == 16


def test_anchor_with_no_aligned_token_borrows_the_offset_before_it() -> None:
    reference = _reference(
        _block("alpha beta lost words gamma"), anchors=(("10", 0), ("11", 2), ("12", 4))
    )
    galley = _galley((15, "alpha beta"), (17, "gamma"))
    pages, anchors = _pages(reference, galley)
    assert anchors[1].offset is None
    assert anchors[1].page_index == 16
    assert pages[2:4] == (16, 16)


def test_unaligned_note_token_takes_the_page_of_its_note() -> None:
    reference = _reference(
        _block("the duke landed"),
        notes=(
            ReferenceNote("Footnote_1", (_block("Amatus, ii. 8."),)),
            ReferenceNote("Footnote_2", (_block("Malaterra, i. 3."),)),
        ),
        note_references=(
            NoteReference("Footnote_1", Gap(Stream.BODY, 2)),
            NoteReference("Footnote_2", Gap(Stream.BODY, 3)),
        ),
        anchors=(("1", 0),),
    )
    # galley read the body on page 5 and the first note at its foot on
    # page 6, with "ii." lost; it did not read the second note at all.
    galley = _galley((5, "the duke landed"), (6, "Amatus, 8."))
    pages, _ = _pages(reference, galley)
    assert pages[3:6] == (6, 6, 6)
    # The second note takes the page of its reference, after "landed".
    assert pages[6:9] == (5, 5, 5)


def test_unaligned_margin_note_token_takes_the_page_of_its_margin_note() -> None:
    reference = _reference(
        _block("Danegeld levied", ReferenceKind.MARGIN_NOTE),
        _block("the tax was due"),
        anchors=(("1", 0),),
    )
    galley = _galley((8, "Danegeld"), (7, "the tax was due"))
    pages, _ = _pages(reference, galley)
    assert pages[:2] == (8, 8)


def test_token_between_anchors_with_an_excluded_page_between_them_is_unplaced() -> None:
    # Stubbs: a map on excluded pages 52-55 between printed pages 34 and 35,
    # its caption in the reference and nowhere in galley's words.
    reference = _reference(
        _block("alpha beta Map of Anjou gamma delta"), anchors=(("34", 0), ("35", 5))
    )
    galley = _galley((51, "alpha beta"), (56, "gamma delta"))
    pages, _ = _pages(reference, galley, frozenset((52, 53, 54, 55)))
    assert pages == (51, 51, None, None, None, 56, 56)


def test_token_between_anchors_with_no_excluded_page_between_them_is_placed() -> None:
    reference = _reference(
        _block("alpha beta Map of Anjou gamma delta"), anchors=(("34", 0), ("35", 5))
    )
    galley = _galley((51, "alpha beta"), (56, "gamma delta"))
    pages, _ = _pages(reference, galley, frozenset((50, 57)))
    assert pages == (51, 51, 51, 51, 51, 56, 56)


def test_anchor_whose_offset_differs_from_both_neighbours_is_a_mismatch() -> None:
    reference = _reference(
        _block("a1 a2 b1 b2 c1 c2 d1 d2 e1 e2"),
        anchors=(("1", 0), ("2", 2), ("3", 4), ("4", 6), ("5", 8)),
    )
    # Printed page 3 aligned two pages off; at printed page 4 the offset
    # steps from 20 to 24, as at inserted plates, which is no mismatch.
    galley = _galley(
        (21, "a1 a2"), (22, "b1 b2"), (25, "c1 c2"), (28, "d1 d2"), (29, "e1 e2")
    )
    _, anchors = _pages(reference, galley)
    assert tuple(anchor.offset for anchor in anchors) == (20, 20, 22, 24, 24)
    assert tuple(anchor.anchor_mismatch for anchor in anchors) == (
        False,
        False,
        True,
        False,
        False,
    )


def test_unaligned_body_token_in_a_book_without_anchors_takes_the_page_before() -> None:
    reference = _reference(_block("alpha beta gamma delta"))
    galley = _galley((3, "alpha beta"), (4, "delta"))
    pages, anchors = _pages(reference, galley)
    assert pages == (3, 3, 3, 4)
    assert anchors == ()


def test_token_before_every_anchor_and_aligned_token_takes_the_page_after() -> None:
    reference = _reference(_block("Contents alpha beta"), anchors=(("1", 1),))
    galley = _galley((9, "alpha beta"))
    pages, _ = _pages(reference, galley)
    assert pages == (9, 9, 9)


def test_unaligned_token_before_the_first_anchor_takes_the_page_before_it() -> None:
    reference = _reference(_block("Title lost Preface alpha"), anchors=(("1", 3),))
    galley = _galley((2, "Title"), (4, "Preface"), (9, "alpha"))
    pages, _ = _pages(reference, galley)
    assert pages == (2, 2, 4, 9)


def test_unaligned_note_token_takes_the_nearest_aligned_token_after_it() -> None:
    # "here" is nearer "Malaterra", read at the top of page 7, than "Amatus".
    reference = _reference(
        _block("the duke"),
        notes=(
            ReferenceNote("Footnote_1", (_block("Amatus lost words here Malaterra"),)),
        ),
        note_references=(NoteReference("Footnote_1", Gap(Stream.BODY, 2)),),
    )
    galley = _galley((6, "the duke")) + tuple(
        GalleyToken(
            text=text,
            page_index=page_index,
            stream=GalleyStream.NOTES,
            edge_of_page=False,
            block_id=None,
        )
        for page_index, text in ((6, "Amatus"), (7, "Malaterra"))
    )
    pages, _ = _pages(reference, galley)
    assert pages == (6, 6, 6, 6, 6, 7, 7)


def test_split_takes_the_page_of_its_first_galley_token() -> None:
    reference = _reference(_block("alpha replicate"))
    galley = _galley((39, "alpha"), (40, "repli-"), (41, "cate"))
    pages, _ = _pages(reference, galley)
    assert pages == (39, 40)


def test_glued_tokens_take_the_page_of_their_galley_token() -> None:
    reference = _reference(_block("alpha pamphlets published"))
    galley = _galley((39, "alpha"), (40, "pamphletspublished"))
    pages, _ = _pages(reference, galley)
    assert pages == (39, 40, 40)


def test_anchor_offset_is_the_lower_median() -> None:
    # Page index minus printed page 11 is 4 for "beta" and 5 for "gamma".
    reference = _reference(_block("beta gamma"), anchors=(("11", 0),))
    _, anchors = _pages(reference, _galley((15, "beta"), (16, "gamma")))
    assert anchors[0].offset == 4


def test_excluded_page_equal_to_an_anchor_page_is_not_between() -> None:
    reference = _reference(
        _block("alpha beta Map of Anjou gamma delta"), anchors=(("34", 0), ("35", 5))
    )
    galley = _galley((51, "alpha beta"), (56, "gamma delta"))
    for excluded in (frozenset((51,)), frozenset((56,))):
        pages, _ = _pages(reference, galley, excluded)
        assert pages[2:5] == (51, 51, 51)


def test_unread_note_takes_the_page_of_the_token_before_its_reference() -> None:
    def note_pages(reference_at: int) -> tuple[int | None, ...]:
        reference = _reference(
            _block("alpha beta"),
            notes=(ReferenceNote("Footnote_1", (_block("lost"),)),),
            note_references=(
                NoteReference("Footnote_1", Gap(Stream.BODY, reference_at)),
            ),
        )
        pages, _ = _pages(reference, _galley((3, "alpha"), (4, "beta")))
        return pages[2:]

    # Before the first token, the first token's page; at the end, the last's.
    assert note_pages(0) == (3,)
    assert note_pages(1) == (3,)
    assert note_pages(2) == (4,)


def test_note_with_no_aligned_token_and_no_reference_is_unplaced() -> None:
    reference = _reference(
        _block("alpha beta"), notes=(ReferenceNote("Footnote_1", (_block("lost"),)),)
    )
    pages, _ = _pages(reference, _galley((3, "alpha beta")))
    assert pages == (3, 3, None)
