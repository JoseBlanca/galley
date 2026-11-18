"""Spaced punctuation (spec section 23): a "?", ";", ":" or "!" that the
printer set apart from its word is attached to it, as a recorded word
change, in a book not in French, and takes a no-break space before it in
a French one."""

from dataclasses import replace

from galley.config import Language
from galley.model import BlockKind, ChangeReason, WordChange
from galley.structure._markers import reference_candidate
from galley.structure._unnumbered import Unnumbered

# Spec section 23: the signs a nineteenth-century printer set apart.
_SPACED_SIGNS = frozenset("?;:!")
# Spec section 23: a word before a sign may end with a closing bracket
# ("(1) ;") as well as a letter or a digit.
_CLOSING_BRACKETS = frozenset(")]")
# The kinds whose printed lines are kept, a line feed between them,
# across which a sign stays as it is (spec section 23): a verse block,
# and a verse epigraph, whose line starts are kept (a prose epigraph has
# none; section 22, "The block").
_LINE_FEED_KINDS = frozenset({BlockKind.VERSE, BlockKind.EPIGRAPH})


def attach_spaced_sign(before: str, word: str) -> str | None:
    """The word made of `before` and `word` when `word` is a spaced sign,
    a word that starts with "?", ";", ":" or "!" ("?", ";^", "?'"), and
    `before` ends with a letter, a digit, ")" or "]": "subjection" and ";"
    give "subjection;" (spec section 23). None when the sign stays apart,
    after a dash, a quotation mark or other punctuation; when `word` holds
    a note reference and the word made would hold none ("14)" and ";13");
    and when `word` is not a spaced sign."""
    if not (word[:1] in _SPACED_SIGNS and before):
        return None
    last = before[-1]
    if not (last.isalnum() or last in _CLOSING_BRACKETS):
        return None
    attached = before + word
    # Spec section 23, "After a note reference": a sign that holds a
    # reference (";13") is not attached where the word it makes holds none
    # ("14);13"), so that its note stays linked.
    if reference_candidate(word) is not None and reference_candidate(attached) is None:
        return None
    return attached


def _follows_on_its_line(block: Unnumbered, position: int) -> bool:
    """Whether the word at `position` follows a word of `block` with a
    space between them, not a line feed of verse (spec section 23)."""
    return position > 0 and not (
        block.kind in _LINE_FEED_KINDS and position in block.line_starts
    )


def _not_linked(block: Unnumbered) -> None:
    if block.links:
        message = (
            f"spaced signs are attached before references are looked for; "
            f"a block on page {block.word_pages[0]} has {len(block.links)}"
        )
        raise ValueError(message)


def attach_spaced_signs(block: Unnumbered) -> Unnumbered:
    """`block` with each spaced sign attached to the word before it, as
    `attach_spaced_sign` gives, in a book not in French (spec section 23).
    Each attachment is a `punctuation_attached` change on the page of the
    first word, placed at the position of the word it gave; the positions
    of the block's changes and line starts are moved to the words they
    were on. The block has no note references yet: a block with any is a
    ValueError."""
    _not_linked(block)
    words: list[str] = []
    pages: list[int] = []
    moved: dict[int, int] = {}
    line_starts: set[int] = set()
    attachments: list[tuple[int, WordChange]] = []
    for position, word in enumerate(block.words):
        attached = (
            attach_spaced_sign(words[-1], word)
            if _follows_on_its_line(block, position)
            else None
        )
        if attached is not None:
            change = WordChange(
                page_index=pages[-1],
                before=(words[-1], word),
                after=(attached,),
                reason=ChangeReason.PUNCTUATION_ATTACHED,
            )
            attachments.append((len(words) - 1, change))
            words[-1] = attached
            moved[position] = len(words) - 1
            continue
        if position in block.line_starts:
            line_starts.add(len(words))
        moved[position] = len(words)
        words.append(word)
        pages.append(block.word_pages[position])
    if not attachments:
        return block
    return replace(
        block,
        words=tuple(words),
        word_pages=tuple(pages),
        changes=(
            *((moved.get(at, at), change) for at, change in block.changes),
            *attachments,
        ),
        line_starts=frozenset(line_starts),
    )


def no_break_positions(block: Unnumbered) -> frozenset[int]:
    """The positions of the words of `block` that take a no-break space,
    U+00A0, before them instead of a space, in a French book: each spaced
    sign that `attach_spaced_sign` would attach (spec section 23). No word
    changes."""
    return frozenset(
        position
        for position, word in enumerate(block.words)
        if _follows_on_its_line(block, position)
        and attach_spaced_sign(block.words[position - 1], word) is not None
    )


def with_spaced_signs(block: Unnumbered, language: Language) -> Unnumbered:
    """`block` with its spaced signs (spec section 23): in a book whose
    `language` is French, its words as they are and the positions of the
    signs in `no_break`; in any other, the signs attached
    (`attach_spaced_signs`)."""
    if language is Language.FR:
        _not_linked(block)
        return replace(block, no_break=no_break_positions(block))
    return attach_spaced_signs(block)
