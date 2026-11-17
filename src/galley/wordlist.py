"""The words of a language's dictionary, taken from Tesseract's language data.

Tesseract ships a dictionary of each language inside its `.traineddata`
file, as a DAWG, a compact graph of words. `word_list` unpacks it with
Tesseract's `combine_tessdata -u` and turns it into plain text with
`dawg2wordlist`, once per language, and keeps the text, one word per line,
in a cache folder (`~/.cache/galley/wordlist/` by default); later calls
read that file. The words are as the dictionary gives them, with their
case and accents ("Médicis"). A word of the book is looked up by its key,
`word_key`, the form structure's hyphen rule compares (structure spec
section 5); `is_known_word` says whether a word counts as known on a
plate (plates spec section 2), against the list in lower case that
`lower_case_word_list` gives.

Adapted from `setup.sh` of the owner's ocr_lab
(`~/devel/tomato_history_web_site/tools/ocr_lab/setup.sh`), which runs the
same two tools.

On Tesseract 5.5.4 (Homebrew, 15 November 2026) the English dictionary
holds 338,080 words and the French one 74,068.
"""

import functools
import logging
import os
import re
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path

from galley.config import Language, tesseract_language
from galley.errors import ExternalProgramError, InputFileError

_LOGGER = logging.getLogger(__name__)

DEFAULT_CACHE_DIR = Path.home() / ".cache" / "galley" / "wordlist"

# Guessed, not measured: each tool takes under a second on the English data
# (0.2 s for both on an M5 Pro, 15 November 2026), so a minute means a hang.
_TIMEOUT_S = 60

# Two threads that find no cache at once would both extract; the lock makes
# the second wait and then read what the first wrote. Separate processes
# are kept apart by the rename in _extract, which is atomic.
_EXTRACTION_LOCK = threading.Lock()

_LIST_LANGS_HEADER = re.compile(r'List of available languages in "(.+)" \(\d+\):')

_DELETE_CACHE = "delete it to extract it again"

# Structure spec section 5: the apostrophes a word's key keeps, and after
# which a French elision's word is looked up.
APOSTROPHES = ("'", "’")
# Plates spec section 2: a known word's key has at least 2 letters ("a" and
# stray marks of one letter are not known).
_KNOWN_WORD_MIN_LETTERS = 2


def is_cached(language: Language, cache_dir: Path = DEFAULT_CACHE_DIR) -> bool:
    """Whether the word list of `language` is in `cache_dir`, so that
    `word_list` reads it without running Tesseract's tools."""
    return _cache_file(language, cache_dir).exists()


# The programs word_list runs to extract a word list that is not cached.
WORD_LIST_TOOLS = ("tesseract", "combine_tessdata", "dawg2wordlist")


def missing_tools(
    language: Language, cache_dir: Path = DEFAULT_CACHE_DIR
) -> tuple[str, ...]:
    """The programs of WORD_LIST_TOOLS that are not on the PATH and that
    `word_list` would need for `language`: none when its list is cached
    in `cache_dir`."""
    if is_cached(language, cache_dir):
        return ()
    return tuple(tool for tool in WORD_LIST_TOOLS if shutil.which(tool) is None)


def _cache_file(language: Language, cache_dir: Path) -> Path:
    """The cached list of `language`, named by Tesseract's code for it."""
    return cache_dir / f"{tesseract_language(language)}.txt"


def word_list(
    language: Language, cache_dir: Path = DEFAULT_CACHE_DIR
) -> frozenset[str]:
    """The words of Tesseract's dictionary of `language`.

    The first call for a language extracts the list with Tesseract's tools
    and writes it to `cache_dir`; later calls, also from other threads and
    processes, read the file there. Raises ExternalProgramError when
    Tesseract or its tools are missing, have no data for the language, or
    fail, and InputFileError when the cached list is empty or not UTF-8.
    """
    tesseract_code = tesseract_language(language)
    cache_file = _cache_file(language, cache_dir)
    with _EXTRACTION_LOCK:
        if not cache_file.exists():
            _extract(tesseract_code, cache_file)
    try:
        text = cache_file.read_text(encoding="utf-8")
    except UnicodeDecodeError as err:
        msg = f"the cached word list {cache_file} is not UTF-8; {_DELETE_CACHE}"
        raise InputFileError(msg) from err
    words = words_of_list(text)
    if not words:
        msg = f"the cached word list {cache_file} is empty; {_DELETE_CACHE}"
        raise InputFileError(msg)
    return words


@functools.cache
def lower_case_word_list(
    language: Language, cache_dir: Path = DEFAULT_CACHE_DIR
) -> frozenset[str]:
    """The words of `word_list(language, cache_dir)` in lower case, the form
    `is_known_word` and structure's hyphen rule compare keys with. Made once
    per language and folder in a process; raises as `word_list` does."""
    return frozenset(word.lower() for word in word_list(language, cache_dir))


def words_of_list(text: str) -> frozenset[str]:
    """The words of a word list written by dawg2wordlist, one per line."""
    return frozenset(line for line in text.split("\n") if line != "")


def tessdata_dir_and_languages(list_langs_output: str) -> tuple[Path, frozenset[str]]:
    """The folder of Tesseract's language data and the languages in it, read
    from the output of `tesseract --list-langs`, whose first line is
    `List of available languages in "<folder>" (<count>):`."""
    header, *languages = list_langs_output.strip().split("\n")
    match = _LIST_LANGS_HEADER.fullmatch(header.strip())
    if match is None:
        msg = (
            "`tesseract --list-langs` printed an unexpected first line, "
            f"{header!r}, where galley expected the folder of the language data"
        )
        raise ExternalProgramError(msg)
    return Path(match.group(1)), frozenset(language.strip() for language in languages)


def _extract(tesseract_code: str, cache_file: Path) -> None:
    """Writes the word list of `tesseract_code` to `cache_file`, through a
    temporary file in the same folder renamed into place, so that no
    reader ever sees half a list."""
    listing = _run("tesseract", "--list-langs")
    tessdata_dir, installed = tessdata_dir_and_languages(listing)
    if tesseract_code not in installed:
        msg = (
            f"Tesseract has no data for the language {tesseract_code!r} in "
            f"{tessdata_dir}; install it with `brew install tesseract-lang`"
        )
        raise ExternalProgramError(msg)
    _LOGGER.info("extracting the word list of %s from Tesseract's data", tesseract_code)
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as work:
        prefix = Path(work) / tesseract_code
        _run(
            "combine_tessdata",
            "-u",
            str(tessdata_dir / f"{tesseract_code}.traineddata"),
            f"{prefix}.",
        )
        dictionary = Path(f"{prefix}.lstm-word-dawg")
        if not dictionary.exists():
            msg = (
                f"Tesseract's data for {tesseract_code!r} in {tessdata_dir} "
                "has no dictionary (no lstm-word-dawg)"
            )
            raise ExternalProgramError(msg)
        extracted = Path(work) / "words.txt"
        _run(
            "dawg2wordlist",
            f"{prefix}.lstm-unicharset",
            str(dictionary),
            str(extracted),
        )
        text = extracted.read_text(encoding="utf-8")
    if not words_of_list(text):
        msg = f"dawg2wordlist wrote no words for {tesseract_code!r}"
        raise ExternalProgramError(msg)
    _write_atomically(text, cache_file)


def _write_atomically(text: str, cache_file: Path) -> None:
    """Writes `text` to a temporary file beside `cache_file` and renames it
    into place; a failed write removes the temporary file."""
    descriptor, partial_name = tempfile.mkstemp(
        dir=cache_file.parent, prefix=f".{cache_file.name}.", suffix=".partial"
    )
    partial = Path(partial_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as partial_file:
            partial_file.write(text)
        partial.replace(cache_file)
    except BaseException:
        partial.unlink(missing_ok=True)
        raise


def _run(program: str, *arguments: str) -> str:
    """The standard output of `program` run with `arguments`."""
    executable = shutil.which(program)
    if executable is None:
        msg = (
            f"{program} is not installed; it comes with Tesseract "
            "(`brew install tesseract`)"
        )
        raise ExternalProgramError(msg)
    command = [executable, *arguments]
    try:
        completed = subprocess.run(
            command, capture_output=True, text=True, check=True, timeout=_TIMEOUT_S
        )
    except subprocess.CalledProcessError as err:
        msg = f"{' '.join(command)} failed with exit status {err.returncode}: {err.stderr}"
        raise ExternalProgramError(msg) from err
    except subprocess.TimeoutExpired as err:
        msg = f"{' '.join(command)} did not finish in {_TIMEOUT_S} s"
        raise ExternalProgramError(msg) from err
    return completed.stdout


def _kept_in_key(character: str) -> bool:
    return character.isalnum() or character == "-" or character in APOSTROPHES


def word_key(text: str) -> str:
    """The key of a word (structure spec section 5): lower case, with the
    characters that are not letters, digits, hyphens or apostrophes
    stripped from both ends. "(Normandy)," gives "normandy"; punctuation
    alone gives the empty string."""
    lowered = text.lower()
    start = 0
    end = len(lowered)
    while start < end and not _kept_in_key(lowered[start]):
        start += 1
    while end > start and not _kept_in_key(lowered[end - 1]):
        end -= 1
    return lowered[start:end]


def is_known_word(word: str, lower_case_words: frozenset[str]) -> bool:
    """Whether `word` counts as known on a plate (plates spec section 2).

    It is known when its key (`word_key`) has at least 2 letters, holds
    nothing but letters, apostrophes and hyphens, and is in
    `lower_case_words`, the word list as `lower_case_word_list` gives it;
    or when it is ASCII digits with brackets, hyphens or other punctuation
    around them ("16", "17]", "1066-").
    """
    number = _without_punctuation_around(word)
    if number.isascii() and number.isdigit():
        return True
    key = word_key(word)
    return (
        sum(character.isalpha() for character in key) >= _KNOWN_WORD_MIN_LETTERS
        and all(
            character.isalpha() or character == "-" or character in APOSTROPHES
            for character in key
        )
        and key in lower_case_words
    )


def _without_punctuation_around(text: str) -> str:
    """`text` without the characters that are not letters or digits at its
    ends: "(1066)-" gives "1066"."""
    start = 0
    end = len(text)
    while start < end and not text[start].isalnum():
        start += 1
    while end > start and not text[end - 1].isalnum():
        end -= 1
    return text[start:end]
