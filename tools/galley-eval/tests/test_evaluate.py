"""Tests of galley_eval.evaluate: the comparison of one book, from its
reference and galley's side to the differences and scores (spec sections
5 to 7)."""

import pytest

from galley.config import Language
from galley.model import BlockKind, Box, PageWords, TextSource, Word, WordsFile
from galley_eval.align import GalleyStream, GalleyToken, State, Subkind
from galley_eval.books import EvaluationBook, ExpectedCounts
from galley_eval.errors import AlignmentError
from galley_eval.evaluate import Apart, Difference, Evaluation, evaluation_of
from galley_eval.galley_side import GalleyBlock, GalleySide
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
from galley_eval.scores import Part
from galley_eval.stages import StageOutput


def _book(
    exclude_pages: tuple[int, ...] = (),
    not_in_reference: tuple[int, ...] = (),
    *,
    margin_notes_moved: bool = False,
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
        margin_notes_moved=margin_notes_moved,
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
