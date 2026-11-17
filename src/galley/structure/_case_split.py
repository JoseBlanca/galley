"""Words glued at a case change (spec section 24): a word the OCR gave as
two, "theAvre", is split at its capital, as a recorded word change, when
the word list knows the left part, the book prints it often, and the book
prints the right part whole."""

from dataclasses import replace

from galley.model import ChangeReason, WordChange
from galley.structure._unnumbered import Unnumbered
from galley.wordlist import is_known_word

# Spec section 24: the left part has at least 2 letters ("aWilliam" stays).
_MIN_LEFT_LETTERS = 2
# Spec section 24: the capital is followed by at least 2 lower-case letters.
_MIN_RIGHT_LOWER_LETTERS = 2
# Spec section 24: the capitals the OCR gives for "li" ("poUtique",
# "estabHshed"), at which a word is never split.
_MISREAD_CAPITALS = frozenset("UH")


def _letters_span(word: str) -> tuple[int, int]:
    """The start and end of `word` without the characters that are not
    letters at its ends."""
    start = 0
    end = len(word)
    while start < end and not word[start].isalpha():
        start += 1
    while end > start and not word[end - 1].isalpha():
        end -= 1
    return start, end


def _capital_position(core: str) -> int | None:
    """The position of the capital in `core` when it is a run of lower-case
    letters, one capital and at least 2 lower-case letters, and nothing
    else; None otherwise."""
    capitals = [position for position, letter in enumerate(core) if letter.isupper()]
    if len(capitals) != 1:
        return None
    capital = capitals[0]
    left = core[:capital]
    right = core[capital + 1 :]
    if (
        len(left) >= _MIN_LEFT_LETTERS
        and len(right) >= _MIN_RIGHT_LOWER_LETTERS
        and all(letter.isalpha() and letter.islower() for letter in left + right)
    ):
        return capital
    return None


def split_at_case(
    word: str,
    lower_case_words: frozenset[str],
    book_words: frozenset[str],
    common_inner_words: frozenset[str],
) -> tuple[str, str] | None:
    """The two words a word glued at a lower-to-upper case change makes,
    the punctuation at each end going with its side: "theAvre" gives
    ("the", "Avre"), "ofWilliam," gives ("of", "William,") (spec section
    24). None unless all of these hold: the word without the punctuation
    at its ends is lower-case letters, one capital and at least 2
    lower-case letters; the capital is not "U" or "H"; the left part has
    at least 2 letters, is a known word of `lower_case_words`, the word
    list in lower case, and is among `common_inner_words`
    (`BookSurvey.common_inner_words`); the right part's key is among
    `book_words`, the keys of the words the book prints whole; and the
    whole word is not a known word."""
    start, end = _letters_span(word)
    core = word[start:end]
    capital = _capital_position(core)
    if capital is None or core[capital] in _MISREAD_CAPITALS:
        return None
    left = core[:capital]
    right = core[capital:]
    if (
        is_known_word(left, lower_case_words)
        and left in common_inner_words
        and right.lower() in book_words
        and not is_known_word(core, lower_case_words)
    ):
        cut = start + capital
        return word[:cut], word[cut:]
    return None


def split_glued_words(
    block: Unnumbered,
    lower_case_words: frozenset[str],
    book_words: frozenset[str],
    common_inner_words: frozenset[str],
) -> Unnumbered:
    """`block` with each word glued at a case change split in two, as
    `split_at_case` gives against `lower_case_words`, `book_words` and
    `common_inner_words`
    (spec section 24). Each split is a `case_split` change on the word's
    page, placed at the position of the first part; both parts are on the
    word's page, and the positions of the block's changes and line starts
    are moved to the words they were on. Run once hyphens are joined and
    before references are looked for: a block with note references is a
    ValueError."""
    if block.links:
        message = (
            f"glued words are split before references are looked for; "
            f"a block on page {block.word_pages[0]} has {len(block.links)}"
        )
        raise ValueError(message)
    words: list[str] = []
    pages: list[int] = []
    moved: dict[int, int] = {}
    splits: list[tuple[int, WordChange]] = []
    for position, (word, page) in enumerate(
        zip(block.words, block.word_pages, strict=True)
    ):
        moved[position] = len(words)
        parts = split_at_case(word, lower_case_words, book_words, common_inner_words)
        if parts is None:
            words.append(word)
            pages.append(page)
            continue
        splits.append(
            (
                len(words),
                WordChange(
                    page_index=page,
                    before=(word,),
                    after=parts,
                    reason=ChangeReason.CASE_SPLIT,
                ),
            )
        )
        words.extend(parts)
        pages.extend((page, page))
    if not splits:
        return block
    return replace(
        block,
        words=tuple(words),
        word_pages=tuple(pages),
        changes=(
            *((moved.get(at, at), change) for at, change in block.changes),
            *splits,
        ),
        line_starts=frozenset(moved[start] for start in block.line_starts),
    )
