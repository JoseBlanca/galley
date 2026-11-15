"""Tests of galley_eval.evaluate: the comparison of one book, from its
reference and galley's side to the differences and scores (spec sections
5 to 7)."""

import pytest

from galley.config import Language
from galley.model import BlockKind, Box, PageWords, TextSource, Word, WordsFile
from galley_eval.align import GalleyStream, GalleyToken, State
from galley_eval.books import EvaluationBook, ExpectedCounts
from galley_eval.errors import AlignmentError
from galley_eval.evaluate import Apart, Evaluation, evaluation_of
from galley_eval.galley_side import GalleyBlock, GalleySide
from galley_eval.reader import (
    ReferenceBlock,
    ReferenceKind,
    ReferenceText,
    ReferenceToken,
)
from galley_eval.rules import DEFAULT_RULES
from galley_eval.scores import Part
from galley_eval.stages import StageOutput


def _book(exclude_pages: tuple[int, ...] = ()) -> EvaluationBook:
    return EvaluationBook(
        name="test",
        gutenberg_number=1,
        archive_id="test00",
        title="Test",
        authors=("Nobody",),
        language=Language.EN,
        exclude_pages=exclude_pages,
        not_in_reference=(),
        margin_notes_moved=False,
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
