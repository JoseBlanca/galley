"""The words the correct stage compares (docs/specs/correct.md, section 6):
a text cut into tokens, each with its core and its comparison form."""

import difflib
import re
import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Token:
    """One token of a text: its core is `text[start:end]`, and `form` the
    comparison form of the core, never empty."""

    start: int
    end: int
    form: str


# Step 3: the ordinary punctuation taken off a word's ends.
_ORDINARY = ".,;:!?'\"()[]‘’“”„«»…"
# A note marker glued after a word of two letters or more and its
# ordinary punctuation ("Greece,1", "Kadesh,12", "him.”’!7"; not "A1"), as the measurement's
# common.tokens cuts it.
_GLUED_AFTER = re.compile(rf"^([^\W\d_].*?[^\W\d_][{re.escape(_ORDINARY)}]*)[\d*†‡]+$")
# One to three digits or signs glued before a capital and another letter
# ("3There"); not before a lone letter, as in "1X" for "IX".
_GLUED_BEFORE = re.compile(r"^[\d*†‡]{1,3}(?=[^\W\d_]{2})")
# Step 2: the dashes a word is split at: an em dash and a double hyphen.
_DASH = re.compile(r"—|--")
_QUOTES = str.maketrans(
    {
        "‘": "'",
        "’": "'",
        "“": '"',
        "”": '"',
        "„": '"',
        "«": '"',
        "»": '"',
        "`": "'",
        "´": "'",
    }
)
_LIGATURES = (
    ("ﬁ", "fi"),
    ("ﬂ", "fl"),
    ("ﬀ", "ff"),
    ("æ", "ae"),
    ("Æ", "Ae"),
    ("œ", "oe"),
    ("Œ", "Oe"),
)
_SUPERSCRIPT_DIGITS = "⁰¹²³⁴⁵⁶⁷⁸⁹"
_EDGES = re.compile(r"^[\W_]+|[\W_]+$")
_INNER_DASHES = re.compile("[-–]")


def comparison_form(core: str) -> str:
    """The form in which two cores are compared: NFC, quotes straight,
    ligatures written out, accents and superscript digits dropped, what is
    not a letter or digit at the ends dropped, hyphens and en dashes
    inside dropped, case folded. Empty when nothing is left."""
    text = unicodedata.normalize("NFC", core).translate(_QUOTES)
    for ligature, letters in _LIGATURES:
        text = text.replace(ligature, letters)
    text = "".join(
        character
        for character in unicodedata.normalize("NFD", text)
        if unicodedata.category(character) != "Mn"
        and character not in _SUPERSCRIPT_DIGITS
    )
    text = _EDGES.sub("", text)
    return _INNER_DASHES.sub("", text).casefold()


def _core(piece: str) -> tuple[int, int] | None:
    """The start and end of the core in `piece`, or None when it has no
    letter or digit (step 3)."""
    start, end = _strip(piece, 0, len(piece))
    if (after := _GLUED_AFTER.match(piece[start:end])) is not None:
        start, end = _strip(piece, start, start + len(after.group(1)))
    if (before := _GLUED_BEFORE.match(piece[start:end])) is not None and piece[
        start + before.end()
    ].isupper():
        start, end = _strip(piece, start + before.end(), end)
    if not any(character.isalnum() for character in piece[start:end]):
        return None
    return start, end


def _strip(piece: str, start: int, end: int) -> tuple[int, int]:
    while start < end and piece[start] in _ORDINARY:
        start += 1
    while end > start and piece[end - 1] in _ORDINARY:
        end -= 1
    return start, end


def tokens(text: str) -> tuple[Token, ...]:
    """The tokens of `text`, in order: split at white space, at em dashes
    and double hyphens; each piece's core and comparison form. A piece
    with no letter or digit, or an empty form, makes no token."""
    found = []
    for word in re.finditer(r"\S+", text):
        position = word.start()
        for piece in _DASH.split(word.group()):
            bounds = _core(piece)
            if bounds is not None:
                start, end = bounds
                form = comparison_form(piece[start:end])
                if form:
                    found.append(Token(position + start, position + end, form))
            position += len(piece) + _dash_length(text, position + len(piece))
    return tuple(found)


def _dash_length(text: str, position: int) -> int:
    """The length of the dash at `position` of `text`, 0 at a word's end."""
    if text.startswith("--", position):
        return 2
    if text.startswith("—", position):
        return 1
    return 0


# Step 1: markdown's marks and anything between angle brackets, as the
# measurement's score_vision.clean took them out.
_MARKDOWN = re.compile(r"<[^>]*>|[*_#`|]")
# A word broken at a line end, joined before a lower-case letter, or in
# capitals before a capital; never before anything else (correct spec,
# section 6: "com-" at the end of a page's body before its first note).
_LINE_END_HYPHEN = re.compile(r"([^\W\d_])[-¬][ \t]*\n[ \t]*(?=[^\W\d_])")


@dataclass(frozen=True, slots=True)
class LineEndJoin:
    """Where the cleaned answer joined a word broken at a line end: the
    offset in the cleaned text where the second half starts, and whether
    both halves were in capitals ("DINDORF-" and "MÜLLER")."""

    offset: int
    capitals: bool


def clean_answer(text: str) -> str:
    """The model's answer ready to be cut into tokens: markdown's marks taken
    out and the words broken at a line end joined (step 1). Superscript
    digits are dropped, since the model writes note markers so."""
    return cleaned_answer(text)[0]


def cleaned_answer(text: str) -> tuple[str, tuple[LineEndJoin, ...]]:
    """The cleaned answer, as clean_answer gives it, and where it joined
    the words broken at a line end."""
    text = _MARKDOWN.sub(" ", text)
    text = "".join(
        character for character in text if character not in _SUPERSCRIPT_DIGITS
    )
    pieces = []
    joins = []
    length = 0
    previous = 0
    for match in _LINE_END_HYPHEN.finditer(text):
        kept = text[previous : match.start()]
        pieces.append(kept)
        length += len(kept)
        joined = _join(match)
        pieces.append(joined)
        length += len(joined)
        if joined != match.group():
            joins.append(LineEndJoin(length, capitals=not text[match.end()].islower()))
        previous = match.end()
    pieces.append(text[previous:])
    return "".join(pieces), tuple(joins)


def _join(match: re.Match[str]) -> str:
    before = match.string[match.start(1) : match.end(1)]
    after = match.string[match.end()]
    word_start = match.string.rfind("\n", 0, match.start()) + 1
    head = re.split(r"\s", match.string[word_start : match.start() + 1])[-1]
    if after.islower() or (head.isupper() and after.isupper()):
        return before
    return match.string[match.start() : match.end()]


def alike(first: str, second: str) -> float:
    """How alike two comparison forms are, by difflib's ratio, 0 to 1."""
    return difflib.SequenceMatcher(None, first, second, autojunk=False).ratio()
