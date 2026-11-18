"""Tests of galley_eval.evaluate: the comparison of one book, from its
reference and galley's side to the differences and scores (spec sections
5 to 7)."""

import dataclasses

import pytest

from galley.config import Language
from galley.model import (
    BlockKind,
    Box,
    NoteKind,
    PageWords,
    Removal,
    RemovalReason,
    TextSource,
    Word,
    WordsFile,
)
from galley_eval.align import GalleyStream, GalleyToken, State, Subkind
from galley_eval.books import EvaluationBook, ExpectedCounts
from galley_eval.errors import AlignmentError, BooksFileError
from galley_eval.evaluate import (
    Apart,
    Cause,
    Difference,
    Evaluation,
    OutputScores,
    evaluation_of,
)
from galley_eval.galley_side import GalleyBlock, GalleyNoteReference, GalleySide
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
from galley_eval.rules import DEFAULT_RULES
from galley_eval.scores import GalleyKind, HeadingScores, NoteScores, Part
from galley_eval.stages import StageOutput


def _book(
    exclude_pages: tuple[int, ...] = (),
    not_in_reference: tuple[int, ...] = (),
    *,
    margin_notes_moved: bool = False,
    body_pages: tuple[int, int] = (0, 0),
) -> EvaluationBook:
    return EvaluationBook(
        name="test",
        gutenberg_number=1,
        archive_id="test00",
        title="Test",
        authors=("Nobody",),
        language=Language.EN,
        exclude_pages=exclude_pages,
        contents_pages=(),
        plate_pages=(),
        not_in_reference=not_in_reference,
        reference_ends_at=None,
        margin_notes_moved=margin_notes_moved,
        body_pages=body_pages,
        html_sha256="0" * 64,
        expected_counts=ExpectedCounts(
            notes=0,
            margin_notes=0,
            note_references=0,
            page_anchors=0,
            headings=0,
            first_tokens=(),
        ),
        rules=DEFAULT_RULES,
    )


_REFERENCE = ReferenceText(
    blocks=(
        ReferenceBlock(
            ReferenceKind.PARAGRAPH,
            tuple(
                ReferenceToken(word, marked_correction=False)
                for word in [
                    "We",
                    "must",
                    "replicate",
                    "the",
                    "work",
                    "of",
                    "the",
                    "Normans",
                ]
            ),
        ),
    ),
    notes=(),
    note_references=(),
    page_anchors=(),
    anchors_in_notes=(),
)


def _tokens(
    text: str,
    *,
    page_index: int = 0,
    edge_of_page: bool = False,
    block_id: str | None = None,
) -> tuple[GalleyToken, ...]:
    return tuple(
        GalleyToken(
            text=word,
            page_index=page_index,
            stream=GalleyStream.BODY,
            edge_of_page=edge_of_page,
            block_id=block_id,
        )
        for word in text.split()
    )


def _side(
    words: tuple[GalleyToken, ...],
    blocks: tuple[GalleyToken, ...],
    markdown: tuple[GalleyToken, ...],
) -> GalleySide:
    return GalleySide(
        words=words,
        lines=words,
        blocks=blocks,
        markdown=markdown,
        galley_blocks=frozendict(
            {
                "b1": GalleyBlock(
                    kind=BlockKind.PARAGRAPH, stream=GalleyStream.BODY, note_id=None
                )
            }
        ),
        note_references=(),
        words_file=WordsFile(
            source_pdf_sha256="0" * 64,
            pages=(
                PageWords(
                    index=0,
                    text_source=TextSource.TEXT_LAYER,
                    words=tuple(
                        Word(token.text, Box(0.0, 0.0, 1.0, 1.0), None)
                        for token in words
                    ),
                    figures=(),
                ),
            ),
            removals=(),
        ),
    )


# A running head that no stage removes, and a hyphen at a line end that
# structure joins: the two examples of spec section 5.
_WORDS = _tokens("RUNNING HEAD", edge_of_page=True) + _tokens(
    "We must repli- cate the work of the Normans"
)
_BLOCKS = _tokens(
    "RUNNING HEAD We must replicate the work of the Normans", block_id="b1"
)


def _evaluation(markdown: tuple[GalleyToken, ...] = _BLOCKS) -> Evaluation:
    return evaluation_of(
        _book(), _REFERENCE, _side(_WORDS, _BLOCKS, markdown), frozenset(("we",))
    )


def test_running_head_never_removed_is_a_difference_of_words_on_the_edge() -> None:
    extras = tuple(
        (difference.stage, difference.galley, difference.edge_of_page)
        for difference in _evaluation().differences
        if difference.state is State.EXTRA
    )
    assert extras == (
        (StageOutput.WORDS, ("RUNNING",), True),
        (StageOutput.WORDS, ("HEAD",), True),
    )


def test_hyphen_joined_by_structure_is_repaired_and_no_difference() -> None:
    evaluation = _evaluation()
    assert all(
        difference.reference != ("replicate",) for difference in evaluation.differences
    )
    text = {
        scores.output: scores.text[Part.BODY] for scores in evaluation.scorecard.outputs
    }
    assert (text[StageOutput.WORDS].split, text[StageOutput.BLOCKS].split) == (1, 0)
    assert text[StageOutput.WORDS].repaired is None
    assert (text[StageOutput.LINES].repaired, text[StageOutput.BLOCKS].repaired) == (
        0,
        1,
    )
    assert text[StageOutput.WORDS].edge_of_page_extra == 2


def test_word_broken_at_markdown_is_a_difference_of_markdown_with_context() -> None:
    markdown = _tokens(
        "RUNNING HEAD We must replicate the wark of the Normans", block_id="b1"
    )
    (changed,) = tuple(
        difference
        for difference in _evaluation(markdown).differences
        if difference.state is State.CHANGED
    )
    assert (changed.stage, changed.reference, changed.galley) == (
        StageOutput.MARKDOWN,
        ("work",),
        ("wark",),
    )
    assert changed.context_before == ("We", "must", "replicate", "the")
    assert changed.context_after == ("of", "the", "Normans")
    assert (changed.page_index, changed.block_id, changed.apart) == (0, "b1", None)
    assert changed.edge_of_page is False


def test_scores_have_structure_only_at_blocks_and_markdown() -> None:
    outputs = _evaluation().scorecard.outputs
    assert tuple(scores.paragraph_boundaries is None for scores in outputs) == (
        True,
        True,
        False,
        False,
    )
    assert len(_evaluation().pages) == 1


def test_difference_on_an_excluded_page_is_listed_apart() -> None:
    words = _WORDS + _tokens("plate caption", page_index=3)
    blocks = _BLOCKS + _tokens("plate caption", page_index=3, block_id="b1")
    evaluation = evaluation_of(
        _book(exclude_pages=(3,)),
        _REFERENCE,
        _side(words, blocks, blocks),
        frozenset(),
    )
    apart = tuple(
        (difference.galley, difference.apart)
        for difference in evaluation.differences
        if difference.page_index == 3
    )
    assert apart == (
        (("plate",), Apart.EXCLUDED_PAGE),
        (("caption",), Apart.EXCLUDED_PAGE),
    )
    body = evaluation.scorecard.outputs[-1].text[Part.BODY]
    assert body.extra == 2  # the running head only


def test_words_that_align_less_than_half_the_reference_stop_the_book() -> None:
    words = _tokens("Quite another book altogether here")
    with pytest.raises(AlignmentError, match=r"0\.0%"):
        evaluation_of(_book(), _REFERENCE, _side(words, words, words), frozenset())


def test_words_that_align_half_the_reference_go_on() -> None:
    words = _tokens("We must replicate the")
    evaluation = evaluation_of(
        _book(), _REFERENCE, _side(words, words, words), frozenset()
    )
    assert evaluation.scorecard.equal_key_share == 0.5


def test_words_that_align_three_eighths_of_the_reference_stop() -> None:
    words = _tokens("We must replicate")
    with pytest.raises(AlignmentError, match=r"37\.5%"):
        evaluation_of(_book(), _REFERENCE, _side(words, words, words), frozenset())


# A book of five pages: printed pages 5, 6 and 7 on page indices 0, 1 and
# 3, page 2 excluded, page 4 not in the reference; a note on page 0.

_BOOK_REFERENCE = ReferenceText(
    blocks=(
        ReferenceBlock(
            ReferenceKind.PARAGRAPH,
            tuple(
                ReferenceToken(word, marked_correction=False)
                for word in ("alpha", "beta", "gamma", "delta")
            ),
        ),
        ReferenceBlock(
            ReferenceKind.PARAGRAPH,
            tuple(
                ReferenceToken(word, marked_correction=False)
                for word in ("epsilon", "zeta", "eta", "theta")
            ),
        ),
        ReferenceBlock(
            ReferenceKind.PARAGRAPH,
            tuple(
                ReferenceToken(word, marked_correction=False)
                for word in ("iota", "kappa")
            ),
        ),
    ),
    notes=(
        ReferenceNote(
            "Footnote_1",
            (
                ReferenceBlock(
                    ReferenceKind.PARAGRAPH,
                    tuple(
                        ReferenceToken(word, marked_correction=False)
                        for word in ("Ibid.", "page", "forty")
                    ),
                ),
            ),
        ),
    ),
    note_references=(NoteReference("Footnote_1", Gap(Stream.BODY, 2)),),
    page_anchors=(
        PageAnchor("5", Gap(Stream.BODY, 0)),
        PageAnchor("6", Gap(Stream.BODY, 4)),
        PageAnchor("7", Gap(Stream.BODY, 8)),
    ),
    anchors_in_notes=(),
)


def _galley(
    text: str,
    page_index: int,
    block_id: str | None = None,
    *,
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


def _book_side() -> GalleySide:
    words = (
        _galley("NORMANS 5 alpba", 0, edge_of_page=True)
        + _galley("beta gamma delta lbid. page fortv", 0)
        + _galley("epsilon zcta eta", 1)
        + _galley("iota kappa", 3)
        + _galley("stray", 4)
    )
    blocks = (
        _galley("NORMANS 5 alpba beta gamma delta", 0, "b-p0000-001")
        + _galley("epsilon zetaeta", 1, "b-p0001-001")
        + _galley("iota kappa", 3, "b-p0003-001")
        + _galley("stray", 4, "b-p0004-001")
        + _galley("lbid. page fortv", 0, "b-p0000-002", stream=GalleyStream.NOTES)
    )
    paragraph = GalleyBlock(
        kind=BlockKind.PARAGRAPH, stream=GalleyStream.BODY, note_id=None
    )
    return GalleySide(
        words=words,
        lines=words,
        blocks=blocks,
        markdown=blocks,
        galley_blocks=frozendict(
            {
                "b-p0000-001": paragraph,
                "b-p0001-001": paragraph,
                "b-p0003-001": paragraph,
                "b-p0004-001": paragraph,
                "b-p0000-002": GalleyBlock(
                    kind=BlockKind.PARAGRAPH,
                    stream=GalleyStream.NOTES,
                    note_id="n-p0000-001",
                ),
            }
        ),
        note_references=(),
        words_file=WordsFile(
            source_pdf_sha256="0" * 64,
            pages=tuple(
                PageWords(
                    index=page,
                    text_source=TextSource.TEXT_LAYER,
                    words=tuple(
                        Word(token.text, Box(0.0, 0.0, 1.0, 1.0), None)
                        for token in words
                        if token.page_index == page
                    ),
                    figures=(),
                )
                for page in (0, 1, 3, 4)
            ),
            removals=(),
        ),
    )


def _book_differences() -> dict[tuple[str, ...], Difference]:
    evaluation = evaluation_of(
        _book(exclude_pages=(2,), not_in_reference=(4,)),
        _BOOK_REFERENCE,
        _book_side(),
        frozenset(),
    )
    return {
        difference.reference or difference.galley: difference
        for difference in evaluation.differences
    }


def test_difference_of_words_on_the_page_edge_has_its_printed_page() -> None:
    alpha = _book_differences()[("alpha",)]
    assert (alpha.stage, alpha.state, alpha.subkind) == (
        StageOutput.WORDS,
        State.CHANGED,
        Subkind.LETTERS,
    )
    assert (alpha.page_index, alpha.printed_page, alpha.edge_of_page) == (0, "5", True)
    assert alpha.context_after == (
        "beta",
        "gamma",
        "delta",
        "epsilon",
        "zeta",
        "eta",
        "theta",
        "iota",
    )


def test_difference_in_a_note_has_its_note_and_no_context_of_the_body() -> None:
    ibid = _book_differences()[("Ibid.",)]
    assert (ibid.note_id, ibid.block_id, ibid.part) == (
        "n-p0000-001",
        "b-p0000-002",
        Part.NOTES,
    )
    assert ibid.context_before == ()
    assert ibid.context_after == ("page", "forty")


def test_glued_takes_the_latest_stage_of_its_tokens() -> None:
    # "zeta" is misread from words on, "eta" matched until blocks glued it.
    glued = _book_differences()[("zeta", "eta")]
    assert (glued.stage, glued.state, glued.state_at_stage) == (
        StageOutput.BLOCKS,
        State.GLUED,
        State.GLUED,
    )
    assert (glued.galley, glued.printed_page, glued.edge_of_page) == (
        ("zetaeta",),
        "6",
        False,
    )


def test_difference_between_anchors_around_an_excluded_page_is_unplaced() -> None:
    theta = _book_differences()[("theta",)]
    assert (theta.state, theta.page_index, theta.apart) == (
        State.MISSING,
        None,
        Apart.UNPLACED,
    )


def test_extra_on_a_page_not_in_the_reference_is_apart_with_its_page_context() -> None:
    differences = _book_differences()
    stray = differences[("stray",)]
    assert (stray.page_index, stray.apart, stray.stage) == (
        4,
        Apart.NOT_IN_REFERENCE,
        StageOutput.WORDS,
    )
    head = differences[("NORMANS",)]
    assert (head.edge_of_page, head.apart, head.state_at_stage) == (
        True,
        None,
        State.EXTRA,
    )
    # galley's tokens of its page, not the reference's.
    assert head.context_after[:3] == ("5", "alpba", "beta")
    assert head.context_before == ()


def test_margin_note_position_is_not_scored_when_gutenberg_moved_them() -> None:
    evaluation = evaluation_of(
        _book(margin_notes_moved=True),
        _REFERENCE,
        _side(_WORDS, _BLOCKS, _BLOCKS),
        frozenset(),
    )
    margin = evaluation.scorecard.outputs[-1].margin_notes
    assert margin is not None
    assert margin.position_right is None
    evaluation = evaluation_of(
        _book(), _REFERENCE, _side(_WORDS, _BLOCKS, _BLOCKS), frozenset()
    )
    margin = evaluation.scorecard.outputs[-1].margin_notes
    assert margin is not None
    assert margin.position_right == 0


def test_difference_records_its_state_at_its_stage_and_at_markdown() -> None:
    # Split at words and lines, misjoined by structure as "replicat".
    blocks = _tokens(
        "RUNNING HEAD We must replicat the work of the Normans", block_id="b1"
    )
    evaluation = evaluation_of(
        _book(), _REFERENCE, _side(_WORDS, blocks, blocks), frozenset()
    )
    (replicate,) = (
        difference
        for difference in evaluation.differences
        if difference.reference == ("replicate",)
    )
    assert (
        replicate.stage,
        replicate.state_at_stage,
        replicate.state,
        replicate.subkind,
    ) == (StageOutput.WORDS, State.SPLIT, State.CHANGED, Subkind.LETTERS)


# blocks.json version 2 (spec sections 5 and 6): verse, chapter summaries,
# headings with a label, and endnotes, on galley tokens made by hand.


def _reference_block(kind: ReferenceKind, text: str) -> ReferenceBlock:
    return ReferenceBlock(
        kind,
        tuple(ReferenceToken(word, marked_correction=False) for word in text.split()),
    )


def _v2_tokens(
    text: str,
    block_id: str,
    *,
    page_index: int = 0,
    stream: GalleyStream = GalleyStream.BODY,
    label_words: int = 0,
    near_page: int | None = None,
) -> tuple[GalleyToken, ...]:
    return tuple(
        GalleyToken(
            text=word,
            page_index=page_index,
            stream=stream,
            edge_of_page=False,
            block_id=block_id,
            in_label=position < label_words,
            near_page=near_page,
        )
        for position, word in enumerate(text.split())
    )


def _words_of(tokens: tuple[GalleyToken, ...]) -> tuple[GalleyToken, ...]:
    """`tokens` as words.json would have them: body words with no block."""
    return tuple(
        GalleyToken(
            text=token.text,
            page_index=token.page_index,
            stream=GalleyStream.BODY,
            edge_of_page=False,
            block_id=None,
        )
        for token in sorted(tokens, key=lambda token: token.page_index)
    )


def _side_of(
    words: tuple[GalleyToken, ...],
    blocks: tuple[GalleyToken, ...],
    galley_blocks: dict[str, GalleyBlock],
    note_references: tuple[GalleyNoteReference, ...] = (),
) -> GalleySide:
    # The PDF ends with a blank page after the last with words.
    pages = range(max(token.page_index for token in words) + 2)
    return GalleySide(
        words=words,
        lines=words,
        blocks=blocks,
        markdown=blocks,
        galley_blocks=frozendict(galley_blocks),
        note_references=note_references,
        words_file=WordsFile(
            source_pdf_sha256="0" * 64,
            pages=tuple(
                PageWords(
                    index=page,
                    text_source=TextSource.TEXT_LAYER,
                    words=tuple(
                        Word(token.text, Box(0.0, 0.0, 1.0, 1.0), None)
                        for token in words
                        if token.page_index == page
                    ),
                    figures=(),
                )
                for page in pages
            ),
            removals=(),
        ),
    )


def _body_block(kind: BlockKind, *, label: bool = False) -> GalleyBlock:
    return GalleyBlock(
        kind=kind,
        stream=GalleyStream.BODY,
        note_id=None,
        has_label=label,
        first_page=0,
    )


# Stubbs' chapter III: its reference text makes two headings of the label
# and the title, and a quote of the summary.
_CHAPTER = ReferenceText(
    blocks=(
        _reference_block(ReferenceKind.HEADING, "CHAPTER III."),
        _reference_block(ReferenceKind.HEADING, "THE EARLY YEARS OF HENRY II."),
        _reference_block(
            ReferenceKind.CHAPTER_SUMMARY, "Terms of accession \u2014 His character"
        ),
        _reference_block(ReferenceKind.QUOTE, "prose quoted from a chronicle"),
        _reference_block(ReferenceKind.VERSE, "O Roma nobilis orbis et domina"),
        _reference_block(ReferenceKind.PARAGRAPH, "Very few epochs indeed"),
    ),
    notes=(),
    note_references=(),
    page_anchors=(),
    anchors_in_notes=(),
)


def _chapter(
    *,
    label: bool,
    body_pages: tuple[int, int] = (0, 0),
    label_words: int = 2,
    quote_held_by: BlockKind = BlockKind.VERSE,
) -> Evaluation:
    """Stubbs' chapter III against galley's blocks: one heading, with a
    label of `label_words` words when `label`, a chapter summary, the
    prose quote held by a block of kind `quote_held_by`, verse and a
    paragraph; and a heading among the notes, which is not counted."""
    blocks = (
        _v2_tokens(
            "CHAPTER III. THE EARLY YEARS OF HENRY II.",
            "h",
            label_words=label_words if label else 0,
        )
        + _v2_tokens("Terms of accession \u2014 His character", "s")
        + _v2_tokens("prose quoted from a chronicle", "q")
        + _v2_tokens("O Roma nobilis orbis et domina", "v")
        + _v2_tokens("Very few epochs indeed", "p")
    )
    side = _side_of(
        _words_of(blocks),
        blocks,
        {
            "h": _body_block(BlockKind.HEADING, label=label),
            "s": _body_block(BlockKind.CHAPTER_SUMMARY),
            "q": _body_block(quote_held_by),
            "v": _body_block(BlockKind.VERSE),
            "p": _body_block(BlockKind.PARAGRAPH),
            # Only the body's headings are galley's headings.
            "nh": GalleyBlock(
                kind=BlockKind.HEADING,
                stream=GalleyStream.NOTES,
                note_id="n-p0000-001",
                first_page=0,
            ),
        },
    )
    return evaluation_of(_book(body_pages=body_pages), _CHAPTER, side, frozenset())


def _at_markdown(evaluation: Evaluation) -> OutputScores:
    return evaluation.scorecard.outputs[-1]


@pytest.mark.parametrize(
    ("held_by", "galley_kind"),
    [
        (BlockKind.VERSE, GalleyKind.VERSE),
        (BlockKind.CHAPTER_SUMMARY, GalleyKind.CHAPTER_SUMMARY),
    ],
)
def test_verse_and_chapter_summary_are_right_only_on_their_own_kind(
    held_by: BlockKind, galley_kind: GalleyKind
) -> None:
    scores = _at_markdown(_chapter(label=True, quote_held_by=held_by))
    assert scores.kinds_right is not None
    # The two headings, the summary, the verse and the paragraph; not the
    # prose quote held by a verse or a chapter summary block.
    assert scores.kinds_right[Part.BODY] == 5
    assert scores.block_kinds is not None
    pairs = {
        (count.reference, count.galley): count.count
        for count in scores.block_kinds[Part.BODY]
    }
    assert pairs[ReferenceKind.QUOTE, galley_kind] == 1
    assert pairs[ReferenceKind.CHAPTER_SUMMARY, GalleyKind.CHAPTER_SUMMARY] == 1


def test_heading_label_and_title_against_two_reference_headings_miss_no_boundary() -> (
    None
):
    scores = _at_markdown(_chapter(label=True))
    assert scores.headings == HeadingScores(
        reference_headings=2,
        in_heading_blocks=2,
        galley_headings=1,
        galley_headings_right=1,
    )
    assert scores.paragraph_boundaries is not None
    body = scores.paragraph_boundaries[Part.BODY]
    assert (body.reference_boundaries, body.found, body.right) == (4, 4, 4)
    assert (body.precision, body.recall) == (1.0, 1.0)


def test_heading_with_no_label_holding_two_reference_headings_misses_a_boundary() -> (
    None
):
    # Mariéjol's "APPENDICE" and its title, made one heading with no label.
    scores = _at_markdown(_chapter(label=False))
    assert scores.paragraph_boundaries is not None
    body = scores.paragraph_boundaries[Part.BODY]
    assert (body.reference_boundaries, body.found) == (5, 4)
    assert scores.headings is not None
    assert scores.headings.in_heading_blocks == 2


@pytest.mark.parametrize(
    "label_words",
    [
        # "CHAPTER" alone in the label: half of the first heading's words.
        1,
        # "CHAPTER III. THE EARLY YEARS OF" in the label: most of the second's.
        6,
    ],
)
def test_label_that_does_not_hold_the_first_heading_alone_misses_the_boundary(
    label_words: int,
) -> None:
    scores = _at_markdown(_chapter(label=True, label_words=label_words))
    assert scores.paragraph_boundaries is not None
    body = scores.paragraph_boundaries[Part.BODY]
    assert (body.reference_boundaries, body.found) == (5, 4)


def test_heading_outside_the_body_range_is_not_counted() -> None:
    scores = _at_markdown(_chapter(label=True, body_pages=(1, 1)))
    assert scores.headings == HeadingScores(
        reference_headings=0,
        in_heading_blocks=0,
        galley_headings=0,
        galley_headings_right=0,
    )


def test_body_range_after_the_last_page_of_the_pdf_is_an_error() -> None:
    # The chapter's PDF has pages 0 and 1, the last blank.
    _chapter(label=True, body_pages=(0, 1))
    with pytest.raises(
        BooksFileError, match="evaluation/books.toml: .* body_pages = \\[0, 2\\]"
    ):
        _chapter(label=True, body_pages=(0, 2))


# Gierke's "Law1" on page 0 refers to endnote 1, printed on page 10.
def _endnote_reference(note_text: str) -> ReferenceText:
    return dataclasses.replace(
        _ENDNOTE_REFERENCE,
        notes=(
            ReferenceNote(
                "note1", (_reference_block(ReferenceKind.PARAGRAPH, note_text),)
            ),
        ),
    )


_ENDNOTE_REFERENCE = ReferenceText(
    blocks=(
        _reference_block(ReferenceKind.PARAGRAPH, "the Law of the land"),
        _reference_block(ReferenceKind.PARAGRAPH, "another Law in another realm"),
    ),
    notes=(
        ReferenceNote(
            "note1",
            (_reference_block(ReferenceKind.PARAGRAPH, "See Bracton on this point"),),
        ),
    ),
    note_references=(NoteReference("note1", Gap(Stream.BODY, 2)),),
    page_anchors=(),
    anchors_in_notes=(),
)


def _endnote_evaluation(
    *,
    reference_on_page: int,
    endnote_text: str = "1. See Bracton on this point",
    note_text: str = "See Bracton on this point",
) -> Evaluation:
    """galley's endnote on page 10 linked from "Law" on `reference_on_page`,
    0 where the reference text has it, or another page, where galley put
    the link by mistake."""
    other_page = reference_on_page if reference_on_page != 0 else 20
    blocks = (
        _v2_tokens("the Law of the land", "b0")
        + _v2_tokens("another Law in another realm", "b20", page_index=other_page)
        + _v2_tokens(
            endnote_text,
            "e1",
            page_index=10,
            stream=GalleyStream.NOTES,
            near_page=reference_on_page,
        )
    )
    linked_block = "b0" if reference_on_page == 0 else "b20"
    side = _side_of(
        _words_of(blocks),
        blocks,
        {
            "b0": _body_block(BlockKind.PARAGRAPH),
            "b20": GalleyBlock(
                kind=BlockKind.PARAGRAPH,
                stream=GalleyStream.BODY,
                note_id=None,
                first_page=other_page,
            ),
            "e1": GalleyBlock(
                kind=BlockKind.PARAGRAPH,
                stream=GalleyStream.NOTES,
                note_id="n-p0010-001",
                note_kind=NoteKind.ENDNOTE,
                first_page=10,
            ),
        },
        (
            GalleyNoteReference(
                note_id="n-p0010-001", block_id=linked_block, tokens_before=2
            ),
        ),
    )
    return evaluation_of(_book(), _endnote_reference(note_text), side, frozenset())


def test_endnote_ten_pages_after_its_reference_is_found_with_its_reference_right() -> (
    None
):
    evaluation = _endnote_evaluation(reference_on_page=0)
    scores = {score.output: score for score in evaluation.scorecard.outputs}
    for output in (StageOutput.BLOCKS, StageOutput.MARKDOWN):
        assert scores[output].notes == NoteScores(
            as_note=1, in_body=0, missing=0, reference_right=1
        )
    # At words the endnote's words lie on page 10, out of the window of
    # its reference on page 0: they are not scored there, and blocks is
    # not credited with them.
    words_notes = scores[StageOutput.WORDS].text[Part.NOTES]
    assert (words_notes.missing, words_notes.not_scored) == (0, 5)
    assert scores[StageOutput.BLOCKS].text[Part.NOTES].repaired == 0
    assert scores[StageOutput.BLOCKS].text[Part.NOTES].matched == 5
    assert not any(difference.reference for difference in evaluation.differences)


def test_endnote_linked_ten_pages_from_its_reference_is_missing_with_its_cause() -> (
    None
):
    evaluation = _endnote_evaluation(reference_on_page=20)
    markdown = _at_markdown(evaluation)
    assert markdown.notes is not None
    assert (markdown.notes.as_note, markdown.notes.reference_right) == (0, 0)
    missing = tuple(
        difference
        for difference in evaluation.differences
        if difference.state is State.MISSING and difference.part is Part.NOTES
    )
    assert missing
    assert {difference.cause for difference in missing} == {Cause.ENDNOTE_REFERENCE_FAR}
    extra_in_endnote = tuple(
        difference
        for difference in evaluation.differences
        if difference.state is State.EXTRA and difference.note_id == "n-p0010-001"
    )
    assert extra_in_endnote
    assert {difference.cause for difference in extra_in_endnote} == {
        Cause.ENDNOTE_REFERENCE_FAR
    }
    assert {
        difference
        for difference in evaluation.differences
        if difference.cause is not None
    } == set(missing + extra_in_endnote)


def test_endnote_linked_one_page_from_its_reference_is_found_with_no_cause() -> None:
    evaluation = _endnote_evaluation(reference_on_page=1)
    markdown = _at_markdown(evaluation)
    assert markdown.notes is not None
    assert markdown.notes.as_note == 1
    assert all(difference.cause is None for difference in evaluation.differences)


def test_endnote_linked_two_pages_from_its_reference_has_the_cause() -> None:
    evaluation = _endnote_evaluation(reference_on_page=2)
    markdown = _at_markdown(evaluation)
    assert markdown.notes is not None
    assert markdown.notes.missing == 1
    assert {
        difference.cause
        for difference in evaluation.differences
        if difference.part is Part.NOTES
    } == {Cause.ENDNOTE_REFERENCE_FAR}


@pytest.mark.parametrize(
    ("note_text", "endnote_text", "cause"),
    [
        # Two of the note's five keyed tokens have their key in the
        # endnote: under half.
        ("See Bracton on this point", "1. See Glanvill on other matters", None),
        # Three of five, each "law" of the note counted although the
        # endnote has it once (spec section 7).
        (
            "law law law of Bracton",
            "1. The law Glanvill wrote",
            Cause.ENDNOTE_REFERENCE_FAR,
        ),
    ],
)
def test_endnote_sharing_under_half_of_the_notes_keys_gives_no_cause(
    note_text: str, endnote_text: str, cause: Cause | None
) -> None:
    evaluation = _endnote_evaluation(
        reference_on_page=20, endnote_text=endnote_text, note_text=note_text
    )
    assert {
        difference.cause
        for difference in evaluation.differences
        if difference.state is State.MISSING and difference.part is Part.NOTES
    } == {cause}


# Front matter (spec section 5, "Pages")


def _front_matter_removals(page_index: int, text: str) -> tuple[Removal, ...]:
    return tuple(
        Removal(
            page_index=page_index,
            box=Box(0.0, 0.0, 1.0, 1.0),
            text=word,
            reason=RemovalReason.FRONT_MATTER,
        )
        for word in text.split()
    )


# The reference's title page, a preface word galley lost, and the text that
# galley reads on page 1, after the front-matter page 0 it dropped.
_TITLE_REFERENCE = ReferenceText(
    blocks=(
        ReferenceBlock(
            ReferenceKind.HEADING,
            tuple(
                ReferenceToken(word, marked_correction=False)
                for word in ("CATHERINE", "DE", "MÉDICIS")
            ),
        ),
        ReferenceBlock(
            ReferenceKind.PARAGRAPH,
            tuple(
                ReferenceToken(word, marked_correction=False)
                for word in [
                    "Preface",
                    "The",
                    "queen",
                    "came",
                    "to",
                    "Paris",
                    "in",
                    "1533",
                ]
            ),
        ),
    ),
    notes=(),
    note_references=(),
    page_anchors=(),
    anchors_in_notes=(),
)


def _front_matter_evaluation(reference: ReferenceText = _TITLE_REFERENCE) -> Evaluation:
    words = _galley("The queen came to Paris in 1533", 1)
    blocks = _galley("The queen came to Paris in 1533", 1, "b1")
    side = dataclasses.replace(
        _side(words, blocks, blocks),
        words_file=WordsFile(
            source_pdf_sha256="0" * 64,
            pages=(
                PageWords(index=0, text_source=TextSource.NONE, words=(), figures=()),
                PageWords(
                    index=1,
                    text_source=TextSource.TEXT_LAYER,
                    words=tuple(
                        Word(token.text, Box(0.0, 0.0, 1.0, 1.0), None)
                        for token in words
                    ),
                    figures=(),
                ),
            ),
            removals=_front_matter_removals(0, "CATHERINE DE MEDICIS 1920"),
        ),
    )
    return evaluation_of(_book(body_pages=(1, 1)), reference, side, frozenset())


def test_reference_title_page_galley_dropped_as_front_matter_is_not_scored() -> None:
    evaluation = _front_matter_evaluation()
    for scores in evaluation.scorecard.outputs:
        body = scores.text[Part.BODY]
        assert (body.front_matter_not_scored, body.not_scored) == (3, 3)
        # "Preface", before the first aligned token, is not a word galley
        # removed as front matter: it counts as missing.
        assert (body.reference_tokens, body.missing, body.matched) == (8, 1, 7)
    assert evaluation.scorecard.front_matter_not_scored == 3


def test_front_matter_tokens_are_listed_apart_as_front_matter() -> None:
    apart = tuple(
        (difference.reference, difference.apart)
        for difference in _front_matter_evaluation().differences
    )
    assert apart == (
        (("CATHERINE",), Apart.FRONT_MATTER),
        (("DE",), Apart.FRONT_MATTER),
        (("MÉDICIS",), Apart.FRONT_MATTER),
        (("Preface",), None),
    )


def test_token_after_the_first_aligned_one_with_a_front_matter_key_is_scored() -> None:
    # "1920", the date of the title page galley dropped, closes the preface
    # here, after the first aligned token, and galley lost it.
    (title, preface) = _TITLE_REFERENCE.blocks
    reference = dataclasses.replace(
        _TITLE_REFERENCE,
        blocks=(
            title,
            ReferenceBlock(
                ReferenceKind.PARAGRAPH,
                (*preface.tokens, ReferenceToken("1920", marked_correction=False)),
            ),
        ),
    )
    evaluation = _front_matter_evaluation(reference)
    assert evaluation.scorecard.front_matter_not_scored == 3
    body = evaluation.scorecard.outputs[0].text[Part.BODY]
    assert (body.reference_tokens, body.missing) == (9, 2)


_PREFACE = "The queen came to Paris in 1533 and the king met her there"


def _series_evaluation(
    closing: str,
    removed: str = "CATHERINE DE MEDICIS 1920 Epochs of Modern History edited by",
    galley_text: str = _PREFACE,
) -> Evaluation:
    """The title page, the preface, which galley reads on page 1, and a
    closing paragraph, `closing`, which galley's words lack: as Stubbs'
    series list ("Epochs of Modern History"), printed on a page galley
    dropped, `removed`, and placed by the reference after the first
    aligned token."""
    reference = dataclasses.replace(
        _TITLE_REFERENCE,
        blocks=tuple(
            ReferenceBlock(
                kind,
                tuple(
                    ReferenceToken(word, marked_correction=False)
                    for word in words.split()
                ),
            )
            for kind, words in (
                (ReferenceKind.HEADING, "CATHERINE DE MÉDICIS"),
                (ReferenceKind.PARAGRAPH, _PREFACE),
                (ReferenceKind.PARAGRAPH, closing),
            )
        ),
    )
    words = _galley(galley_text, 1)
    blocks = _galley(galley_text, 1, "b1")
    side = dataclasses.replace(
        _side(words, blocks, blocks),
        words_file=WordsFile(
            source_pdf_sha256="0" * 64,
            pages=(
                PageWords(index=0, text_source=TextSource.NONE, words=(), figures=()),
                PageWords(
                    index=1,
                    text_source=TextSource.TEXT_LAYER,
                    words=tuple(
                        Word(token.text, Box(0.0, 0.0, 1.0, 1.0), None)
                        for token in words
                    ),
                    figures=(),
                ),
            ),
            removals=_front_matter_removals(0, removed),
        ),
    )
    return evaluation_of(_book(body_pages=(1, 1)), reference, side, frozenset())


def test_four_missing_tokens_printed_on_a_dropped_page_are_front_matter() -> None:
    evaluation = _series_evaluation("EPOCHS OF MODERN HISTORY. — Edited")
    # The title's 3 tokens, and the 6 of the list, "—" among them.
    assert evaluation.scorecard.front_matter_not_scored == 9
    body = evaluation.scorecard.outputs[0].text[Part.BODY]
    assert (body.reference_tokens, body.missing) == (13, 0)


def test_three_missing_tokens_printed_on_a_dropped_page_are_scored() -> None:
    evaluation = _series_evaluation("of Modern History")
    assert evaluation.scorecard.front_matter_not_scored == 3
    body = evaluation.scorecard.outputs[0].text[Part.BODY]
    assert (body.reference_tokens, body.missing) == (16, 3)


def test_dropped_words_out_of_their_order_are_scored() -> None:
    evaluation = _series_evaluation("Epochs of History Modern")
    assert evaluation.scorecard.front_matter_not_scored == 3


def test_an_aligned_token_breaks_a_run_of_dropped_words() -> None:
    # The closing "queen" aligns with galley's last word, so that neither
    # side of it holds 4 consecutive unaligned tokens.
    evaluation = _series_evaluation(
        "Epochs of Modern queen History edited by",
        galley_text=f"{_PREFACE} queen",
    )
    assert evaluation.scorecard.front_matter_not_scored == 3
    body = evaluation.scorecard.outputs[0].text[Part.BODY]
    assert body.missing == 6


def test_reference_tokens_placed_on_a_front_matter_page_are_front_matter() -> None:
    # As _book_differences, with page 1, "epsilon zcta eta", dropped as
    # front matter and page 2 not excluded: the anchor of printed page 6
    # places "epsilon", "zeta", "eta" and "theta" on page 1. Three
    # misreadings are mended, so that half of the reference still aligns.
    mended = {"alpba": "alpha", "lbid.": "Ibid.", "fortv": "forty"}
    side = _book_side()
    side = dataclasses.replace(
        side,
        words=tuple(
            dataclasses.replace(token, text=mended.get(token.text, token.text))
            for token in side.words
            if token.page_index != 1
        ),
        words_file=dataclasses.replace(
            side.words_file,
            pages=tuple(page for page in side.words_file.pages if page.index != 1),
            removals=_front_matter_removals(1, "SECOND TITLE"),
        ),
    )
    evaluation = evaluation_of(
        _book(not_in_reference=(4,)), _BOOK_REFERENCE, side, frozenset()
    )
    assert evaluation.scorecard.front_matter_not_scored == 4


def test_front_matter_page_between_anchors_makes_a_token_unplaced() -> None:
    # As test_difference_between_anchors_around_an_excluded_page_is_unplaced,
    # with page 2 dropped as front matter instead of excluded.
    side = _book_side()
    side = dataclasses.replace(
        side,
        words_file=dataclasses.replace(
            side.words_file, removals=_front_matter_removals(2, "A MAP")
        ),
    )
    evaluation = evaluation_of(
        _book(not_in_reference=(4,)), _BOOK_REFERENCE, side, frozenset()
    )
    (theta,) = (
        difference
        for difference in evaluation.differences
        if difference.reference == ("theta",)
    )
    assert (theta.page_index, theta.apart) == (None, Apart.UNPLACED)


def test_book_without_front_matter_has_none_not_scored_as_front_matter() -> None:
    evaluation = _evaluation()
    assert evaluation.scorecard.front_matter_not_scored == 0
    assert all(
        text.front_matter_not_scored == 0
        for scores in evaluation.scorecard.outputs
        for text in scores.text.values()
    )


# The margin notes' part (spec section 6)


_MARGIN_REFERENCE = ReferenceText(
    blocks=(
        ReferenceBlock(
            ReferenceKind.MARGIN_NOTE,
            tuple(
                ReferenceToken(word, marked_correction=False)
                for word in ("Norman", "barons.")
            ),
        ),
        ReferenceBlock(
            ReferenceKind.PARAGRAPH,
            tuple(
                ReferenceToken(word, marked_correction=False)
                for word in ["The", "barons", "held", "their", "lands"]
            ),
        ),
    ),
    notes=(),
    note_references=(),
    page_anchors=(),
    anchors_in_notes=(),
)


def _margin_side() -> GalleySide:
    """galley's side of _MARGIN_REFERENCE: the margin note misread "Normam"."""
    words = _galley("Normam barons. The barons held their lands", 0)
    blocks = _galley(
        "Normam barons.", 0, "m1", stream=GalleyStream.MARGIN_NOTES
    ) + _galley("The barons held their lands", 0, "b1")
    return dataclasses.replace(
        _side(words, blocks, blocks),
        galley_blocks=frozendict(
            {
                "m1": GalleyBlock(
                    kind=BlockKind.MARGIN_NOTE,
                    stream=GalleyStream.MARGIN_NOTES,
                    note_id=None,
                ),
                "b1": GalleyBlock(
                    kind=BlockKind.PARAGRAPH, stream=GalleyStream.BODY, note_id=None
                ),
            }
        ),
    )


def test_margin_notes_part_holds_the_margin_notes_words_apart_from_the_body() -> None:
    evaluation = evaluation_of(_book(), _MARGIN_REFERENCE, _margin_side(), frozenset())
    markdown = evaluation.scorecard.outputs[-1]
    margin = markdown.text[Part.MARGIN_NOTES]
    body = markdown.text[Part.BODY]
    assert (margin.reference_tokens, margin.changed_letters, margin.matched) == (
        2,
        1,
        1,
    )
    assert margin.token_error_rate == 0.5
    assert (body.reference_tokens, body.matched, body.token_error_rate) == (5, 5, 0.0)
    assert markdown.kinds_right is not None
    assert markdown.kinds_right[Part.MARGIN_NOTES] == 1
    (normam,) = (
        difference
        for difference in evaluation.differences
        if difference.reference == ("Norman",)
    )
    assert normam.part is Part.MARGIN_NOTES


def test_margin_notes_part_has_no_paragraph_boundaries() -> None:
    # A boundary between the margin note and the body is the body's; the
    # margin notes, like the notes, get no boundary scores of their own.
    evaluation = evaluation_of(_book(), _MARGIN_REFERENCE, _margin_side(), frozenset())
    boundaries = evaluation.scorecard.outputs[-1].paragraph_boundaries
    assert boundaries is not None
    assert Part.MARGIN_NOTES not in boundaries
    assert Part.NOTES not in boundaries
