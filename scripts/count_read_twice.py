"""Count the printed words that re-reading leaves read twice in a book.

A word is counted read twice (reocr spec, section 4, "A pairing by letters
wins over a word under it whose letters are unlike") when it is a word of
the text layer that layout left in lines.json, whose middle lies inside the
box of a kept `Reread` of its page widened by 4 pt, and whose letters and
digits, case-folded, equal those of one of that record's Tesseract words
whose middle lies within 16 pt above or below its own, or, for a word of 3
letters or more, whose letters are alike to that word's by difflib's ratio
of 0.6 or more: the layer's own reading of a word Tesseract's reading
already holds.

    uv run python scripts/count_read_twice.py <book folder>...

Each folder holds the words.json and lines.json of a run of galley. The
script prints each word counted, with its page and the Tesseract word, and
the count of each folder.
"""

import argparse
import difflib
import sys
from collections.abc import Iterable
from pathlib import Path

from galley.model import (
    Box,
    LinesFile,
    Reread,
    Word,
    WordsFile,
    folded_letters_and_digits,
    read_lines,
    read_words,
    take_out_once,
    word_middle,
)

# The definition of the count, as reocr section 4 gives it.
_NEAR_RECORD_PT = 4.0
_SAME_TEXT_REACH_PT = 16.0
_ALIKE_LEAST_LETTERS = 3
_ALIKE_LEAST_RATIO = 0.6


def _letters(text: str) -> str:
    return "".join(character for character in text if character.isalpha()).casefold()


def _reads_letters_of(word: Word, ocr_word: Word) -> bool:
    """Whether the letters and digits of `word` equal those of `ocr_word`,
    or, for 3 letters or more, its letters are alike to its own."""
    folded = folded_letters_and_digits(word.text)
    if folded and folded == folded_letters_and_digits(ocr_word.text):
        return True
    letters = _letters(word.text)
    return (
        len(letters) >= _ALIKE_LEAST_LETTERS
        and difflib.SequenceMatcher(None, letters, _letters(ocr_word.text)).ratio()
        >= _ALIKE_LEAST_RATIO
    )


def _near(word: Word, box: Box) -> bool:
    x, y = word_middle(word)
    return (
        box.x0 - _NEAR_RECORD_PT <= x <= box.x1 + _NEAR_RECORD_PT
        and box.top - _NEAR_RECORD_PT <= y <= box.bottom + _NEAR_RECORD_PT
    )


def read_twice(
    words: WordsFile, lines: LinesFile
) -> tuple[tuple[int, Word, Word], ...]:
    """The words of the layer read twice, by the definition above, each
    once, with its page index and the first Tesseract word of a record
    near it that reads its letters, in page order."""
    kept: dict[int, list[Reread]] = {}
    for reread in lines.rereads:
        if reread.kept:
            kept.setdefault(reread.page_index, []).append(reread)
    pages = {page.index: page.words for page in words.pages}
    found = []
    for page_index, records in sorted(kept.items()):
        replaced = (word for record in records for word in record.layer_words)
        (left,) = take_out_once((pages[page_index],), replaced)
        for word in left:
            readings = tuple(
                reading
                for record in records
                if _near(word, record.box)
                for reading in _readings(word, record.ocr_words)
            )
            if readings:
                found.append((page_index, word, readings[0]))
    return tuple(found)


def _readings(word: Word, ocr_words: Iterable[Word]) -> tuple[Word, ...]:
    return tuple(
        ocr_word
        for ocr_word in ocr_words
        if abs(word_middle(ocr_word)[1] - word_middle(word)[1]) <= _SAME_TEXT_REACH_PT
        and _reads_letters_of(word, ocr_word)
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("folders", nargs="+", type=Path)
    for folder in parser.parse_args().folders:
        found = read_twice(
            read_words(folder / "words.json"), read_lines(folder / "lines.json")
        )
        report = [
            f"{folder.name} page {page_index}: {word.text!r} beside {ocr_word.text!r}"
            for page_index, word, ocr_word in found
        ]
        report.append(f"{folder.name}: {len(found)} words read twice")
        sys.stdout.write("\n".join(report) + "\n")


if __name__ == "__main__":
    main()
