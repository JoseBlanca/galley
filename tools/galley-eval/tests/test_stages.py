"""Tests of galley_eval.stages: the stage output a difference belongs to,
the tokens a stage repaired, and the extra tokens followed through the
outputs (spec section 5, "The stage a difference belongs to")."""

from galley_eval.align import (
    GalleyStream,
    GalleyToken,
    State,
    align,
    extra_tokens,
    reference_states,
)
from galley_eval.reader import (
    ReferenceBlock,
    ReferenceKind,
    ReferenceText,
    ReferenceToken,
)
from galley_eval.stages import StageOutput, TokenFate, token_fate, trace_extras


def _reference(text: str) -> ReferenceText:
    block = ReferenceBlock(
        ReferenceKind.PARAGRAPH,
        tuple(ReferenceToken(word, marked_correction=False) for word in text.split()),
    )
    return ReferenceText(
        blocks=(block,),
        notes=(),
        note_references=(),
        page_anchors=(),
        anchors_in_notes=(),
    )


def _tokens(
    page_index: int,
    text: str,
    *,
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


# The stage of a reference token's difference


def test_token_matched_at_every_output_has_no_difference() -> None:
    states = (State.MATCHED, State.MATCHED, State.MATCHED, State.MATCHED)
    assert token_fate(states) == TokenFate(difference_stage=None, repaired_by=None)


def test_difference_belongs_to_the_first_stage_of_the_last_unmatched_run() -> None:
    states = (State.CHANGED, State.MATCHED, State.CHANGED, State.MISSING)
    assert token_fate(states) == TokenFate(
        difference_stage=StageOutput.BLOCKS, repaired_by=None
    )


def test_difference_never_matched_belongs_to_words() -> None:
    states = (State.MISSING, State.MISSING, State.MISSING, State.MISSING)
    assert token_fate(states).difference_stage is StageOutput.WORDS


def test_token_matched_again_at_markdown_is_repaired_where_the_last_match_starts() -> (
    None
):
    states = (State.MATCHED, State.SPLIT, State.CHANGED, State.MATCHED)
    assert token_fate(states) == TokenFate(
        difference_stage=None, repaired_by=StageOutput.MARKDOWN
    )


def test_hyphenated_word_joined_by_structure_is_repaired_by_blocks() -> None:
    # Spec section 5: "repli-" "cate" at words and lines, which structure
    # joins into "replicate".
    reference = _reference("to replicate the text")
    hyphenated = _tokens(40, "to repli- cate the text")
    joined = _tokens(40, "to replicate the text", block_id="b-p0040-001")
    states = tuple(
        reference_states(align(reference, output))[1]
        for output in (hyphenated, hyphenated, joined, joined)
    )
    assert states == (State.SPLIT, State.SPLIT, State.MATCHED, State.MATCHED)
    assert token_fate((states[0], states[1], states[2], states[3])) == TokenFate(
        difference_stage=None, repaired_by=StageOutput.BLOCKS
    )


def test_hyphenated_word_broken_again_by_markdown_is_a_markdown_difference() -> None:
    states = (State.SPLIT, State.SPLIT, State.MATCHED, State.SPLIT)
    assert token_fate(states) == TokenFate(
        difference_stage=StageOutput.MARKDOWN, repaired_by=None
    )


# The extra tokens


def test_running_head_never_removed_is_extra_from_words() -> None:
    # Spec section 5: the first line of Haskins' page index 214, through a
    # galley that does not yet remove running heads.
    reference = _reference("Robert Guiscard had been conquered")
    page_213 = _tokens(213, "Robert Guiscard")
    head = "THE NORMANS IN THE SOUTH 199"
    words = (
        page_213
        + _tokens(214, head, edge_of_page=True)
        + _tokens(214, "had been conquered")
    )
    lines = words
    blocks = (
        _tokens(213, "Robert Guiscard", block_id="b-p0213-004")
        + _tokens(214, head, block_id="b-p0213-004")
        + _tokens(214, "had been conquered", block_id="b-p0213-004")
    )
    markdown = blocks
    extras = tuple(
        extra_tokens(align(reference, output), output)
        for output in (words, lines, blocks, markdown)
    )
    traced = trace_extras((extras[0], extras[1], extras[2], extras[3]))
    assert tuple(extra.token.text for extra in traced) == tuple(head.split())
    assert {extra.stage for extra in traced} == {StageOutput.WORDS}
    assert all(extra.origin.edge_of_page for extra in traced)
    assert all(extra.origin.page_index == 214 for extra in traced)


def test_running_head_removed_by_structure_is_no_difference() -> None:
    head = _tokens(214, "THE NORMANS IN THE SOUTH 199", edge_of_page=True)
    assert trace_extras((head, head, (), ())) == ()


def test_extra_is_traced_to_the_start_of_its_unbroken_run() -> None:
    star = _tokens(10, "*")
    assert tuple(extra.stage for extra in trace_extras((star, (), star, star))) == (
        StageOutput.BLOCKS,
    )


def test_extras_are_followed_as_a_multiset_of_page_and_text() -> None:
    # Two "199" on page 5 at markdown: one there from words on, the second
    # only from blocks. A "199" of page 6 is another extra.
    one = _tokens(5, "199")
    two = _tokens(5, "199 199")
    other_page = _tokens(6, "199")
    traced = trace_extras((one + other_page, one, two, two))
    assert tuple(extra.stage for extra in traced) == (
        StageOutput.WORDS,
        StageOutput.BLOCKS,
    )
