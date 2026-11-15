"""The words of a language's dictionary, taken from Tesseract's language data.

Tesseract ships a dictionary of each language inside its `.traineddata`
file, as a DAWG, a compact graph of words. `word_list` unpacks it with
Tesseract's `combine_tessdata -u` and turns it into plain text with
`dawg2wordlist`, once per language, and keeps the text, one word per line,
in a cache folder (`~/.cache/galley/wordlist/` by default); later calls
read that file. The words are as the dictionary gives them, with their
case and accents ("Médicis"); how a word of the book is looked up in them
is the caller's choice.

Adapted from `setup.sh` of the owner's ocr_lab
(`~/devel/tomato_history_web_site/tools/ocr_lab/setup.sh`), which runs the
same two tools.

On Tesseract 5.5.4 (Homebrew, 15 November 2026) the English dictionary
holds 338,080 words and the French one 74,068.
"""

import logging
import os
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path

from galley.config import Language, tesseract_language
from galley.errors import ConfigError, ExternalProgramError, InputFileError

_LOGGER = logging.getLogger(__name__)

DEFAULT_CACHE_DIR = Path.home() / ".cache" / "galley" / "wordlist"

# Guessed, not measured: each tool takes under a second on the English data
# (0.2 s for both on an M5 Pro, 15 November 2026), so a minute means a hang.
_TIMEOUT_S = 60

# Two threads that find no cache at once would both extract; the lock makes
# the second wait and then read what the first wrote. Separate processes
# are kept apart by the rename in _extract, which is atomic.
_EXTRACTION_LOCK = threading.Lock()

_LIST_LANGS_HEADER = "List of available languages in "


def word_list(language: str, cache_dir: Path = DEFAULT_CACHE_DIR) -> frozenset[str]:
    """The words of Tesseract's dictionary of `language`, an ISO 639-1 code
    of architecture section 6 (`en`, `es`, `fr`, `de`, `it`).

    The first call for a language extracts the list with Tesseract's tools
    and writes it to `cache_dir`; later calls, also from other threads and
    processes, read the file there. Raises ConfigError for a language galley
    does not know, and ExternalProgramError when Tesseract or its tools are
    missing, have no data for the language, or fail.
    """
    tesseract_code = tesseract_language(_known_language(language))
    cache_file = cache_dir / f"{tesseract_code}.txt"
    with _EXTRACTION_LOCK:
        if not cache_file.exists():
            _extract(tesseract_code, cache_file)
    words = words_of_list(cache_file.read_text(encoding="utf-8"))
    if not words:
        msg = (
            f"the cached word list {cache_file} is empty; delete it to extract it again"
        )
        raise InputFileError(msg)
    return words


def words_of_list(text: str) -> frozenset[str]:
    """The words of a word list written by dawg2wordlist, one per line."""
    return frozenset(line for line in text.split("\n") if line != "")


def tessdata_dir_and_languages(list_langs_output: str) -> tuple[Path, frozenset[str]]:
    """The folder of Tesseract's language data and the languages in it, read
    from the output of `tesseract --list-langs`, whose first line is
    `List of available languages in "<folder>" (<count>):`."""
    header, *languages = list_langs_output.strip().split("\n")
    if not header.startswith(_LIST_LANGS_HEADER):
        msg = (
            "`tesseract --list-langs` printed an unexpected first line, "
            f"{header!r}, where galley expected the folder of the language data"
        )
        raise ExternalProgramError(msg)
    folder = header.removeprefix(_LIST_LANGS_HEADER).split('"')[1]
    return Path(folder), frozenset(language.strip() for language in languages)


def _known_language(language: str) -> Language:
    try:
        return Language(language)
    except ValueError as err:
        known = ", ".join(member.value for member in Language)
        msg = f"galley has no word list for the language {language!r}; it knows {known}"
        raise ConfigError(msg) from err


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
    descriptor, partial = tempfile.mkstemp(
        dir=cache_file.parent, prefix=f".{cache_file.name}.", suffix=".partial"
    )
    with os.fdopen(descriptor, "w", encoding="utf-8") as partial_file:
        partial_file.write(text)
    Path(partial).replace(cache_file)


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
