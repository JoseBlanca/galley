"""The table of pages, from which a detector of bad OCR is chosen (spec
section 8).

Each row is one page of `words.json`. Two columns measure the page's OCR
against the reference, at words: `ocr_recall`, the share of its
reference tokens read right, and `ocr_precision`, the share of its galley
tokens that are words of the reference. The others are statistics galley
can compute from its own words, with no reference.

How the spec is read here, where it leaves a choice:

- The tokens flagged `edge_of_page` are left out of `ocr_precision`. The
  reference tokens of a page are all counted in `ocr_recall`, since none
  is flagged.
- The candidate statistics are computed over every token of the page,
  those on its first and last lines included, as analyze, which runs
  before layout finds the lines, would compute them.
- A token is stripped of every character other than a letter or a digit
  at both ends, and lowered. The word list is looked up lowered too, so
  that "Paris" in the list finds "PARIS" in the book.
- For `inner_symbol_share`, a token that is only digits once stripped,
  such as a date, is not a symbol: it is counted as a token, never as one
  with a symbol. Any other character inside the stripped token that is
  neither a letter nor a hyphen between two letters makes it one, an
  apostrophe included.
- `ocr_precision` counts the galley tokens of a split as precise, as the
  spec now says: "repli-" and "cate" are read right.
- A share is empty (None) when it has nothing to divide by: a page with
  no reference token has no `ocr_recall`.
"""

from collections import Counter
from dataclasses import dataclass
from statistics import fmean

from galley.config import Language
from galley.model import TextSource, WordsFile
from galley_eval.align import (
    Alignment,
    GalleyToken,
    ReferencePlace,
    State,
    Subkind,
    alignment_key,
)
from galley_eval.scores import Part, share

__all__ = [
    "PageRow",
    "inner_symbol_share",
    "page_rows",
    "single_letter_share",
    "stripped",
    "wordlist_share",
]


@dataclass(frozen=True, slots=True, kw_only=True)
class PageRow:
    """One row of `pages.tsv`."""

    page_index: int
    printed_page: str | None
    text_source: TextSource
    part: Part
    tokens: int
    ocr_recall: float | None
    ocr_precision: float | None
    wordlist_share: float | None
    single_letter_share: float | None
    inner_symbol_share: float | None
    ocr_confidence_mean: float | None


# The words of one letter of each language, left out of
# single_letter_share. English and French are the spec's; the others are
# the common ones of their language, not measured.
_ONE_LETTER_WORDS = frozendict(
    {
        Language.EN: frozenset("aio"),
        Language.FR: frozenset("aày"),
        Language.ES: frozenset("aeouy"),
        Language.IT: frozenset("aeio"),
        Language.DE: frozenset(),
    }
)

_READ = frozenset((Subkind.CONVENTION, Subkind.CASE, Subkind.PUNCTUATION))


def stripped(text: str) -> str:
    """A token lowered and stripped of everything but letters and digits
    at both ends: "“Serfs,”" is "serfs"."""
    start, end = 0, len(text)
    while start < end and not text[start].isalnum():
        start += 1
    while end > start and not text[end - 1].isalnum():
        end -= 1
    return text[start:end].lower()


def wordlist_share(texts: tuple[str, ...], word_list: frozenset[str]) -> float | None:
    """The share of the alphabetic tokens of `texts`, letters only once
    stripped, that are in `word_list`, a set of lowered words."""
    alphabetic = tuple(word for text in texts if (word := stripped(text)).isalpha())
    if not alphabetic:
        return None
    return sum(1 for word in alphabetic if word in word_list) / len(alphabetic)


def single_letter_share(texts: tuple[str, ...], language: Language) -> float | None:
    """The share of `texts` that are one letter once stripped, other than
    the words of one letter of `language`."""
    if not texts:
        return None
    words = _ONE_LETTER_WORDS[language]
    return sum(
        1
        for text in texts
        if len(word := stripped(text)) == 1 and word.isalpha() and word not in words
    ) / len(texts)


def _has_inner_symbol(word: str) -> bool:
    if word.isdigit():
        return False
    return any(
        not char.isalpha()
        and not (
            char == "-"
            and 0 < position < len(word) - 1
            and word[position - 1].isalpha()
            and word[position + 1].isalpha()
        )
        for position, char in enumerate(word)
    )


def inner_symbol_share(texts: tuple[str, ...]) -> float | None:
    """The share of `texts` that hold, once stripped, a character that is
    neither a letter nor a hyphen between two letters, as "t*e"; a number
    of digits only does not."""
    if not texts:
        return None
    return sum(1 for text in texts if _has_inner_symbol(stripped(text))) / len(texts)


def page_rows(
    words_file: WordsFile,
    galley: tuple[GalleyToken, ...],
    alignment: Alignment,
    places: tuple[ReferencePlace, ...],
    *,
    page_indices: tuple[int | None, ...],
    parts_of_pages: frozendict[int, Part],
    printed_pages: frozendict[int, str],
    word_list: frozenset[str],
    language: Language,
) -> tuple[PageRow, ...]:
    """One row for each page of `words_file`, from galley's words `galley`
    aligned with the reference by `alignment`. `page_indices` is the page
    of each reference token, None when unplaced; `word_list` holds the
    lowered words of the book's language."""
    read: Counter[int] = Counter()
    reference_counts: Counter[int] = Counter()
    for index, page in enumerate(page_indices):
        if page is None:
            continue  # an unplaced token is on no page
        reference_counts[page] += 1
        pairing = alignment.pairings[alignment.reference_pairing[index]]
        if pairing.state in {State.MATCHED, State.SPLIT} or (
            pairing.state is State.CHANGED and pairing.subkind in _READ
        ):
            read[page] += 1
    texts: dict[int, list[str]] = {}
    precise: Counter[int] = Counter()
    inside: Counter[int] = Counter()
    for index, token in enumerate(galley):
        texts.setdefault(token.page_index, []).append(token.text)
        if token.edge_of_page:
            continue  # left out of ocr_precision
        inside[token.page_index] += 1
        pairing = alignment.pairings[alignment.galley_pairing[index]]
        if pairing.state is State.SPLIT or (
            pairing.state in {State.MATCHED, State.CHANGED}
            and alignment_key(token.text)
            == alignment_key(places[pairing.reference_indices[0]].token.text)
        ):
            precise[token.page_index] += 1
    rows: list[PageRow] = []
    for page in words_file.pages:
        page_texts = tuple(texts.get(page.index, ()))
        confidences = tuple(
            word.ocr_confidence
            for word in page.words
            if word.ocr_confidence is not None
        )
        rows.append(
            PageRow(
                page_index=page.index,
                printed_page=printed_pages.get(page.index),
                text_source=page.text_source,
                part=parts_of_pages.get(page.index, Part.BODY),
                tokens=len(page_texts),
                ocr_recall=share(read[page.index], reference_counts[page.index]),
                ocr_precision=share(precise[page.index], inside[page.index]),
                wordlist_share=wordlist_share(page_texts, word_list),
                single_letter_share=single_letter_share(page_texts, language),
                inner_symbol_share=inner_symbol_share(page_texts),
                ocr_confidence_mean=fmean(confidences)
                if page.text_source is TextSource.OCR and confidences
                else None,
            )
        )
    return tuple(rows)
