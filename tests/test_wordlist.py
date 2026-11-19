"""Tests of galley.wordlist: the words of Tesseract's dictionaries
(architecture section 12; evaluation plan, work package 2), the key of a
word (structure spec section 5) and which words count as known (plates
spec sections 2 and 6).

Every test gives `word_list` a cache folder under its own temporary
folder, so that none writes to ~/.cache. Under --parallel-threads=8 the
threads of one test share its tmp_path, so a test that needs a folder of
its own makes one per thread.
"""

import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from galley import wordlist
from galley.config import Language
from galley.errors import ExternalProgramError, InputFileError
from galley.wordlist import (
    WORD_LIST_TOOLS,
    is_cached,
    is_known_word,
    is_word_of_list,
    lower_case_word_list,
    missing_tools,
    tessdata_dir_and_languages,
    word_key,
    word_list,
    words_of_list,
)

# The sizes the research measured on Tesseract 5.5.4 were 338,080 English and
# 74,068 French words (evaluation plan, work package 2); the bounds leave
# room for another release of the language data.
_ENGLISH_SIZE = range(300_000, 400_001)
_FRENCH_SIZE = range(60_000, 90_001)


def _own_folder(tmp_path: Path) -> Path:
    """A folder for this thread alone, inside the test's tmp_path."""
    folder = tmp_path / f"thread-{threading.get_ident()}"
    folder.mkdir()
    return folder


@pytest.mark.tesseract
def test_english_list_has_its_size_and_holds_replicate(tmp_path: Path) -> None:
    words = word_list(Language.EN, cache_dir=_own_folder(tmp_path))
    assert len(words) in _ENGLISH_SIZE
    assert "replicate" in words


@pytest.mark.tesseract
def test_french_list_has_its_size_and_holds_words_with_accents(tmp_path: Path) -> None:
    words = word_list(Language.FR, cache_dir=_own_folder(tmp_path))
    assert len(words) in _FRENCH_SIZE
    assert "Médicis" in words
    assert "été" in words


@pytest.mark.tesseract
def test_second_call_reads_the_cache_without_extracting(tmp_path: Path) -> None:
    cache_dir = _own_folder(tmp_path)
    first = word_list(Language.FR, cache_dir=cache_dir)
    (cache_file,) = cache_dir.glob("*.txt")
    assert words_of_list(cache_file.read_text(encoding="utf-8")) == first
    # A word no dictionary holds: only a call that reads the cache returns it.
    cache_file.write_text("galleycachemarker\n", encoding="utf-8")
    assert word_list(Language.FR, cache_dir=cache_dir) == frozenset(
        {"galleycachemarker"}
    )


@pytest.mark.tesseract
@pytest.mark.thread_unsafe(reason="replaces a function of galley.wordlist")
def test_threads_calling_at_once_extract_the_list_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache_dir = tmp_path / "cache"
    thread_count = 4
    barrier = threading.Barrier(thread_count)
    extractions: list[str] = []
    extract = wordlist._extract

    def counted_extract(tesseract_code: str, cache_file: Path) -> None:
        extractions.append(tesseract_code)
        extract(tesseract_code, cache_file)

    monkeypatch.setattr(wordlist, "_extract", counted_extract)

    def call(_: int) -> frozenset[str]:
        barrier.wait()
        return word_list(Language.FR, cache_dir=cache_dir)

    with ThreadPoolExecutor(thread_count) as pool:
        results = tuple(pool.map(call, range(thread_count)))
    assert extractions == ["fra"]
    assert len(results[0]) in _FRENCH_SIZE
    assert all(result == results[0] for result in results)
    assert [path.name for path in cache_dir.iterdir()] == ["fra.txt"]


def test_cached_list_that_is_not_utf8_is_an_error(tmp_path: Path) -> None:
    cache_dir = _own_folder(tmp_path)
    (cache_dir / "eng.txt").write_bytes(b"caf\xe9\n")
    with pytest.raises(InputFileError, match="eng.txt is not UTF-8; delete it"):
        word_list(Language.EN, cache_dir=cache_dir)


def test_failed_write_of_the_cache_leaves_no_partial_file(tmp_path: Path) -> None:
    cache_dir = _own_folder(tmp_path)
    # A lone surrogate cannot be encoded as UTF-8, so the write fails.
    with pytest.raises(UnicodeEncodeError):
        wordlist._write_atomically("word\ud800\n", cache_dir / "eng.txt")
    assert list(cache_dir.iterdir()) == []


def test_empty_cached_list_is_an_error(tmp_path: Path) -> None:
    cache_dir = _own_folder(tmp_path)
    (cache_dir / "eng.txt").write_text("", encoding="utf-8")
    with pytest.raises(InputFileError, match="empty"):
        word_list(Language.EN, cache_dir=cache_dir)


@pytest.mark.thread_unsafe(reason="changes PATH, which every thread shares")
def test_missing_tesseract_is_an_external_program_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PATH", str(tmp_path))
    with pytest.raises(ExternalProgramError, match="tesseract is not installed"):
        word_list(Language.EN, cache_dir=tmp_path / "cache")


def test_words_of_list_keeps_case_and_accents_and_drops_empty_lines() -> None:
    assert words_of_list("Médicis\nété\n\nreplicate\n") == frozenset(
        {"Médicis", "été", "replicate"}
    )


def test_list_langs_output_gives_the_data_folder_and_languages() -> None:
    output = (
        'List of available languages in "/opt/homebrew/share/tessdata/" (3):\n'
        "eng\nfra\nosd\n"
    )
    assert tessdata_dir_and_languages(output) == (
        Path("/opt/homebrew/share/tessdata/"),
        frozenset({"eng", "fra", "osd"}),
    )


def test_list_langs_output_of_another_form_is_an_error() -> None:
    with pytest.raises(ExternalProgramError, match="unexpected first line"):
        tessdata_dir_and_languages("eng\nfra\n")


def test_list_langs_header_without_quotes_is_an_error() -> None:
    with pytest.raises(ExternalProgramError, match="List of available languages in /x"):
        tessdata_dir_and_languages("List of available languages in /x (1):\neng\n")


def test_is_cached_once_the_language_has_its_file_in_the_cache_folder(
    tmp_path: Path,
) -> None:
    cache_dir = _own_folder(tmp_path)
    assert not is_cached(Language.EN, cache_dir)
    (cache_dir / "eng.txt").write_text("replicate\n", encoding="utf-8")
    assert is_cached(Language.EN, cache_dir)
    assert not is_cached(Language.FR, cache_dir)
    assert word_list(Language.EN, cache_dir=cache_dir) == frozenset({"replicate"})


# Empties PATH for the whole process.
@pytest.mark.thread_unsafe
def test_missing_tools_are_none_once_the_list_is_cached(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PATH", "")
    cache_dir = _own_folder(tmp_path)
    assert missing_tools(Language.EN, cache_dir) == WORD_LIST_TOOLS
    (cache_dir / "eng.txt").write_text("replicate\n", encoding="utf-8")
    assert missing_tools(Language.EN, cache_dir) == ()


# word_key (structure spec section 5)


def test_word_key_is_lower_case_without_punctuation_at_its_ends() -> None:
    assert word_key("(Normandy),") == "normandy"


def test_word_key_keeps_hyphens_apostrophes_and_inner_punctuation() -> None:
    assert word_key("\u201cd'in-") == "d'in-"
    assert word_key("’tis.") == "’tis"
    assert word_key("57;in") == "57;in"


def test_word_key_of_punctuation_alone_is_empty() -> None:
    assert word_key("—;") == ""


# is_known_word (plates spec sections 2 and 6)


def test_known_word_in_the_list_in_another_case() -> None:
    assert is_known_word("Kadesh", frozenset({"kadesh"}))


def test_known_word_with_punctuation_around_it() -> None:
    assert is_known_word("(Kadesh),", frozenset({"kadesh"}))


def test_known_word_is_a_number_with_a_bracket_after_it() -> None:
    assert is_known_word("17]", frozenset())


def test_known_word_is_a_number_alone() -> None:
    assert is_known_word("16", frozenset())


def test_known_word_is_not_a_key_with_other_characters_inside() -> None:
    # The key is "u;l", which the list holds, but ";" is not a letter.
    assert not is_known_word("^U;L", frozenset({"u;l"}))


def test_known_word_has_at_least_2_letters() -> None:
    assert not is_known_word("a", frozenset({"a"}))


def test_known_word_is_not_a_word_absent_from_the_list() -> None:
    assert not is_known_word("Fir", frozenset({"fire"}))


def test_known_word_may_hold_a_hyphen_and_an_apostrophe() -> None:
    word_list = frozenset({"vice-regent", "d'insignes"})
    assert is_known_word("Vice-Regent,", word_list)
    assert is_known_word("d'insignes", word_list)


def test_known_word_is_not_a_number_with_a_letter() -> None:
    assert not is_known_word("17th", frozenset())


def test_known_word_is_a_number_with_a_hyphen_after_it() -> None:
    # Plates spec section 2: a number with punctuation around it.
    assert is_known_word("1066-", frozenset())
    assert is_known_word("(1066)-", frozenset())


def test_known_word_of_2_letters_in_the_list() -> None:
    assert is_known_word("of", frozenset({"of"}))


def test_known_word_is_not_a_digit_outside_ascii() -> None:
    # "²" is a digit to Python, not a number of the book.
    assert not is_known_word("\u00b2", frozenset())


# is_word_of_list (plates spec section 2b)


@pytest.mark.parametrize("word", ["Kadesh", "(of),", "Vice-Regent,"])
def test_word_of_list_is_a_known_word_of_2_letters_or_more(word: str) -> None:
    assert is_word_of_list(word, frozenset({"kadesh", "of", "vice-regent"}))


@pytest.mark.parametrize("word", ["16", "17]", "(1066)-", ".", "a", "Fir"])
def test_word_of_list_is_not_a_number_punctuation_or_a_word_absent(
    word: str,
) -> None:
    assert not is_word_of_list(word, frozenset({"a", "fire"}))


# lower_case_word_list


def test_lower_case_word_list_is_the_list_in_lower_case(tmp_path: Path) -> None:
    cache_dir = _own_folder(tmp_path)
    (cache_dir / "eng.txt").write_text(
        "Normandy\nreplicate\nGLOUCESTER\n", encoding="utf-8"
    )

    assert lower_case_word_list(Language.EN, cache_dir) == frozenset(
        {"normandy", "replicate", "gloucester"}
    )
