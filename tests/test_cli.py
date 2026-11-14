"""Tests of galley.cli, the galley2epub command (spec section 9, "cli.py"
and "Other tests of this work package").

The tests that need the files of analyze or extract copy them from the
session fixture `excerpt_books` into a folder of their own, so that no
test runs a stage on an excerpt that the fixture has run already.
"""

import logging
import shutil
import subprocess
import sys
from importlib.metadata import entry_points
from pathlib import Path

import pytest

from galley.book_folder import BookFolder
from galley.cli import main
from galley.errors import ConfigError, ExternalProgramError, InputFileError

KADESH = "kadesh_8-17"
GIERKE = "gierke_86-93_270-271"


def _book(root: Path, book_toml: str) -> BookFolder:
    folder = BookFolder(root)
    folder.book_toml.write_text(book_toml, encoding="utf-8")
    return folder


# The entry point


def test_galley2epub_is_an_entry_point_of_the_installed_package() -> None:
    (entry_point,) = entry_points(group="console_scripts", name="galley2epub")
    assert entry_point.value == "galley.cli:main"


# Starts a Python process; the 8-thread run would start it 8 times.
@pytest.mark.thread_unsafe
def test_the_installed_script_runs_help_with_exit_code_0() -> None:
    script = Path(sys.executable).parent / "galley2epub"

    completed = subprocess.run(
        [str(script), "--help"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        timeout=60,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.startswith("usage: galley2epub")
    for command in ("run", "analyze", "extract", "layout", "structure", "markdown"):
        assert command in completed.stdout


# The stages one by one


# Runs every stage on an excerpt in a folder of its own.
@pytest.mark.thread_unsafe
def test_the_stages_one_by_one_write_the_same_bytes_as_run(
    tmp_path: Path,
    excerpt_book_toml: frozendict[str, str],
    excerpt_books: frozendict[str, BookFolder],
) -> None:
    folder = _book(tmp_path, excerpt_book_toml[KADESH])

    for stage in ("analyze", "extract", "layout", "structure", "markdown", "epub"):
        main([stage, str(folder.root)])

    by_run = excerpt_books[KADESH]
    for written, written_by_run in (
        (folder.pages_json, by_run.pages_json),
        (folder.words_json, by_run.words_json),
        (folder.cover_png, by_run.cover_png),
        (folder.lines_json, by_run.lines_json),
        (folder.blocks_json, by_run.blocks_json),
        (folder.book_md, by_run.book_md),
    ):
        assert written.read_bytes() == written_by_run.read_bytes(), written.name
    assert folder.book_epub.is_file()


# The arguments argparse rejects


@pytest.mark.parametrize("command", ["correct", "edits-from"])
def test_a_subcommand_the_skeleton_lacks_is_rejected_by_argparse(
    command: str, tmp_path: Path
) -> None:
    with pytest.raises(SystemExit) as raised:
        main([command, str(tmp_path)])
    assert raised.value.code == 2


@pytest.mark.parametrize("workers", ["0", "-1", "two"])
def test_workers_that_are_not_a_whole_number_of_at_least_1_are_rejected(
    workers: str, tmp_path: Path
) -> None:
    with pytest.raises(SystemExit) as raised:
        main(["run", str(tmp_path), "--workers", workers])
    assert raised.value.code == 2


# The errors of spec section 9


def test_layout_without_words_json_raises_naming_extract(
    tmp_path: Path,
    excerpt_book_toml: frozendict[str, str],
    excerpt_books: frozendict[str, BookFolder],
) -> None:
    folder = _book(tmp_path, excerpt_book_toml[KADESH])
    shutil.copy(excerpt_books[KADESH].pages_json, folder.pages_json)

    with pytest.raises(InputFileError, match=r"words\.json.*galley2epub extract"):
        main(["layout", str(folder.root)])

    assert not folder.lines_json.exists()


def test_run_with_correct_true_raises_config_error_before_pages_json_exists(
    tmp_path: Path, excerpt_book_toml: frozendict[str, str]
) -> None:
    folder = _book(tmp_path, excerpt_book_toml[KADESH] + "correct = true\n")

    with pytest.raises(ConfigError, match="correct = true"):
        main(["run", str(folder.root)])

    assert sorted(tmp_path.iterdir()) == [folder.book_toml]


def test_a_words_json_of_the_other_excerpt_raises_naming_extract(
    tmp_path: Path,
    excerpt_book_toml: frozendict[str, str],
    excerpt_books: frozendict[str, BookFolder],
) -> None:
    folder = _book(tmp_path, excerpt_book_toml[KADESH])
    shutil.copy(excerpt_books[KADESH].pages_json, folder.pages_json)
    shutil.copy(excerpt_books[GIERKE].words_json, folder.words_json)

    with pytest.raises(InputFileError, match=r"words\.json.*galley2epub extract"):
        main(["layout", str(folder.root)])

    assert not folder.lines_json.exists()


# caplog holds the records of every thread of the 8-thread run.
@pytest.mark.thread_unsafe
def test_an_error_is_logged_and_raised_again_unchanged(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    folder = BookFolder(tmp_path)

    with (
        caplog.at_level(logging.ERROR, logger="galley.cli"),
        pytest.raises(ConfigError) as raised,
    ):
        main(["analyze", str(folder.root)])

    (record,) = caplog.records
    assert record.levelno == logging.ERROR
    assert record.getMessage() == f"galley2epub analyze failed: {raised.value}"
    assert "book.toml does not exist" in str(raised.value)


# Empties PATH for the whole process.
@pytest.mark.thread_unsafe
@pytest.mark.parametrize("command", ["run", "markdown", "epub"])
def test_a_command_that_needs_pandoc_stops_before_any_stage_without_it(
    command: str,
    tmp_path: Path,
    excerpt_book_toml: frozendict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    folder = _book(tmp_path, excerpt_book_toml[KADESH])
    monkeypatch.setenv("PATH", "")

    # markdown and epub would otherwise raise InputFileError: their input
    # files are missing.
    with pytest.raises(ExternalProgramError, match="brew install pandoc"):
        main([command, str(folder.root)])

    assert sorted(tmp_path.iterdir()) == [folder.book_toml]
