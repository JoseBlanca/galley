"""Tests of galley.wordlist: the words of Tesseract's dictionaries
(architecture section 12; evaluation plan, work package 2).

Every test gives `word_list` a cache folder under its own temporary
folder, so that none writes to ~/.cache. Under --parallel-threads=8 the
threads of one test share its tmp_path, so a test that needs a folder of
its own makes one per thread.
"""

import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from galley.errors import ConfigError, ExternalProgramError, InputFileError
from galley.wordlist import tessdata_dir_and_languages, word_list, words_of_list

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
    words = word_list("en", cache_dir=_own_folder(tmp_path))
    assert len(words) in _ENGLISH_SIZE
    assert "replicate" in words


@pytest.mark.tesseract
def test_french_list_has_its_size_and_holds_words_with_accents(tmp_path: Path) -> None:
    words = word_list("fr", cache_dir=_own_folder(tmp_path))
    assert len(words) in _FRENCH_SIZE
    assert "Médicis" in words
    assert "été" in words


@pytest.mark.tesseract
def test_second_call_reads_the_cache_without_extracting(tmp_path: Path) -> None:
    cache_dir = _own_folder(tmp_path)
    first = word_list("fr", cache_dir=cache_dir)
    (cache_file,) = cache_dir.glob("*.txt")
    assert words_of_list(cache_file.read_text(encoding="utf-8")) == first
    # A word no dictionary holds: only a call that reads the cache returns it.
    cache_file.write_text("galleycachemarker\n", encoding="utf-8")
    assert word_list("fr", cache_dir=cache_dir) == frozenset({"galleycachemarker"})


@pytest.mark.tesseract
def test_threads_calling_at_once_extract_one_list_they_all_get(tmp_path: Path) -> None:
    cache_dir = _own_folder(tmp_path)
    thread_count = 4
    barrier = threading.Barrier(thread_count)

    def call(_: int) -> frozenset[str]:
        barrier.wait()
        return word_list("fr", cache_dir=cache_dir)

    with ThreadPoolExecutor(thread_count) as pool:
        results = tuple(pool.map(call, range(thread_count)))
    assert len(results[0]) in _FRENCH_SIZE
    assert all(result == results[0] for result in results)
    assert [path.name for path in cache_dir.iterdir()] == ["fra.txt"]


def test_unknown_language_is_a_config_error(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="'xx'"):
        word_list("xx", cache_dir=tmp_path)


def test_empty_cached_list_is_an_error(tmp_path: Path) -> None:
    cache_dir = _own_folder(tmp_path)
    (cache_dir / "eng.txt").write_text("", encoding="utf-8")
    with pytest.raises(InputFileError, match="empty"):
        word_list("en", cache_dir=cache_dir)


@pytest.mark.thread_unsafe(reason="changes PATH, which every thread shares")
def test_missing_tesseract_is_an_external_program_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PATH", str(tmp_path))
    with pytest.raises(ExternalProgramError, match="tesseract is not installed"):
        word_list("en", cache_dir=tmp_path / "cache")


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
