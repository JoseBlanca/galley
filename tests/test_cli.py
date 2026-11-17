"""Tests of galley.cli, the galley2epub command (spec section 9, "cli.py"
and "Other tests of this work package").

The tests that need the files of analyze or extract copy them from the
session fixture `excerpt_books` into a folder of their own, so that no
test runs a stage on an excerpt that the fixture has run already.
"""

import logging
import re
import shutil
import subprocess
import sys
import zipfile
from collections.abc import Callable
from dataclasses import replace
from importlib.metadata import entry_points
from pathlib import Path

import pytest

from galley import cli, wordlist
from galley.book_folder import BookFolder
from galley.cli import main
from galley.config import BookConfig
from galley.errors import ConfigError, ExternalProgramError, InputFileError
from galley.model import read_lines
from galley.parallel import DEFAULT_WORKERS

KADESH = "kadesh_8-17"
GIERKE = "gierke_86-93_270-271"
HASKINS = "haskins_eval"


STAGES = ("analyze", "extract", "layout", "structure", "markdown", "epub")
# The names each stage adds to the book folder (spec section 3).
STAGE_FILES = frozendict(
    {
        "analyze": ("pages.json",),
        "extract": ("words.json", "images"),
        "layout": ("lines.json",),
        "structure": ("blocks.json",),
        "markdown": ("book.md",),
        "epub": ("book.epub",),
    }
)


def _book(root: Path, book_toml: str) -> BookFolder:
    folder = BookFolder(root)
    folder.book_toml.write_text(book_toml, encoding="utf-8")
    return folder


def _copy_of_run(tmp_path: Path, run_folder: BookFolder) -> BookFolder:
    """A copy of a folder of the session fixture, which a test may change."""
    return BookFolder(shutil.copytree(run_folder.root, tmp_path / "book"))


def _names(folder: BookFolder) -> list[str]:
    return sorted(path.name for path in folder.root.iterdir())


def _files_up_to(stage: str | None) -> list[str]:
    """The names in a book folder once every stage up to `stage` has run;
    None for no stage."""
    count = 0 if stage is None else STAGES.index(stage) + 1
    return sorted(
        ["book.toml", *(name for done in STAGES[:count] for name in STAGE_FILES[done])]
    )


def _chapter(folder: BookFolder) -> bytes:
    with zipfile.ZipFile(folder.book_epub) as epub:
        return epub.read("EPUB/text/ch001.xhtml")


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
    usage = completed.stdout.split("\n\n", 1)[0]
    subcommands = re.search(r"\{([a-z,-]+)\}", usage)
    assert subcommands is not None, usage
    assert tuple(subcommands.group(1).split(",")) == ("run", *STAGES)


# Starts a Python process; the 8-thread run would start it 8 times.
@pytest.mark.thread_unsafe
def test_the_installed_script_logs_each_stage_and_the_error_on_stderr(
    tmp_path: Path, excerpt_book_toml: frozendict[str, str]
) -> None:
    # A cover page past the end of the 10 pages: analyze stops at once.
    folder = _book(
        tmp_path,
        excerpt_book_toml[KADESH].replace("cover_page = 0", "cover_page = 10"),
    )
    script = Path(sys.executable).parent / "galley2epub"

    completed = subprocess.run(
        [str(script), "run", str(folder.root)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        timeout=60,
    )

    assert completed.returncode == 1
    lines = completed.stderr.splitlines()
    assert lines[0] == f"INFO galley.cli: running analyze on {folder.root}"
    assert any(
        line.startswith("ERROR galley.cli: galley2epub run failed in analyze: ")
        and "cover_page" in line
        for line in lines
    ), completed.stderr


# The stages one by one


# Runs every stage on an excerpt in a folder of its own.
@pytest.mark.thread_unsafe
def test_the_stages_one_by_one_write_the_same_bytes_as_run(
    tmp_path: Path,
    excerpt_book_toml: frozendict[str, str],
    excerpt_books: frozendict[str, BookFolder],
) -> None:
    folder = _book(tmp_path, excerpt_book_toml[KADESH])

    for stage in STAGES:
        main([stage, str(folder.root)])
        assert _names(folder) == _files_up_to(stage), stage

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
    assert _chapter(folder) == _chapter(by_run)


# The workers


# Replaces the stages of the module for the whole process.
@pytest.mark.thread_unsafe
@pytest.mark.pandoc
@pytest.mark.parametrize(
    ("arguments", "workers"), [(["--workers", "3"], 3), ([], DEFAULT_WORKERS)]
)
def test_workers_reaches_every_stage_and_defaults_to_default_workers(
    arguments: list[str],
    workers: int,
    tmp_path: Path,
    excerpt_book_toml: frozendict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    folder = _book(tmp_path, excerpt_book_toml[KADESH])
    calls: list[tuple[str, int]] = []

    def recorder(name: str) -> Callable[..., None]:
        def record(folder: BookFolder, config: BookConfig, *, workers: int = 0) -> None:
            del folder, config
            calls.append((name, workers))

        return record

    monkeypatch.setattr(
        cli,
        "_STAGES",
        tuple(replace(stage, run=recorder(stage.name)) for stage in cli._STAGES),
    )
    main(["run", str(folder.root), *arguments])

    assert calls == [(stage, workers) for stage in STAGES]


# Every stage deletes its file and every later stage's file (spec section 3)


@pytest.mark.parametrize("stage", STAGES[:-1])
def test_a_stage_that_fails_leaves_no_file_of_its_own_or_a_later_stage(
    stage: str,
    tmp_path: Path,
    excerpt_books: frozendict[str, BookFolder],
    excerpt_pdf: frozendict[str, Path],
) -> None:
    folder = _copy_of_run(tmp_path, excerpt_books[KADESH])
    folder.edits_dir.mkdir()
    (folder.edits_dir / "owner.jsonl").write_text("", encoding="utf-8")
    (folder.root / "notes.txt").write_text("the owner's", encoding="utf-8")
    # The Gierke PDF: analyze fails on the cover page, past its 10 pages;
    # every later stage on pages.json, made from the Kadesh PDF.
    book_toml = folder.book_toml.read_text(encoding="utf-8")
    folder.book_toml.write_text(
        book_toml.replace(str(excerpt_pdf[KADESH]), str(excerpt_pdf[GIERKE])).replace(
            "cover_page = 0", "cover_page = 10"
        ),
        encoding="utf-8",
    )

    with pytest.raises((ConfigError, InputFileError)):
        main([stage, str(folder.root)])

    earlier = STAGES[: STAGES.index(stage)]
    assert _names(folder) == sorted(
        [
            "book.toml",
            "edits",
            "notes.txt",
            *(name for done in earlier for name in STAGE_FILES[done]),
        ]
    )
    assert [path.name for path in folder.edits_dir.iterdir()] == ["owner.jsonl"]


# Runs extract on an excerpt in a folder of its own: Haskins', whose extract
# takes 0.06 s where Kadesh's analyze and extract took 1 s (16 November 2026).
@pytest.mark.thread_unsafe
def test_markdown_after_a_new_extract_names_structure_and_leaves_no_book(
    tmp_path: Path, excerpt_books: frozendict[str, BookFolder]
) -> None:
    folder = _copy_of_run(tmp_path, excerpt_books[HASKINS])
    main(["extract", str(folder.root)])

    with pytest.raises(
        InputFileError, match=r"blocks\.json does not exist.*galley2epub structure"
    ):
        main(["markdown", str(folder.root)])
    with pytest.raises(
        InputFileError, match=r"book\.md does not exist.*galley2epub markdown"
    ):
        main(["epub", str(folder.root)])

    assert _names(folder) == _files_up_to("extract")


# Runs Pandoc; the 8-thread run would run it 8 times.
@pytest.mark.thread_unsafe
def test_structure_and_markdown_run_again_on_the_same_inputs_write_the_same_bytes(
    tmp_path: Path, excerpt_books: frozendict[str, BookFolder]
) -> None:
    by_run = excerpt_books[KADESH]
    folder = _copy_of_run(tmp_path, by_run)

    main(["structure", str(folder.root)])
    main(["markdown", str(folder.root)])

    assert _names(folder) == _files_up_to("markdown")
    assert folder.blocks_json.read_bytes() == by_run.blocks_json.read_bytes()
    assert folder.book_md.read_bytes() == by_run.book_md.read_bytes()


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


# Empties PATH for the whole process.
@pytest.mark.thread_unsafe
def test_run_with_correct_true_raises_config_error_before_pages_json_exists(
    tmp_path: Path,
    excerpt_book_toml: frozendict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    folder = _book(tmp_path, excerpt_book_toml[KADESH] + "correct = true\n")
    # The config is refused before Pandoc is looked for.
    monkeypatch.setenv("PATH", "")

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


def test_a_folder_argument_that_is_a_file_raises_config_error(
    tmp_path: Path, excerpt_book_toml: frozendict[str, str]
) -> None:
    folder = _book(tmp_path, excerpt_book_toml[KADESH])

    with pytest.raises(ConfigError, match="must be the book folder"):
        main(["analyze", str(folder.book_toml)])


# Replaces the stages of the module for the whole process; caplog holds
# the records of every thread.
@pytest.mark.thread_unsafe
@pytest.mark.pandoc
def test_under_run_the_logged_error_names_the_stage_that_failed(
    tmp_path: Path,
    excerpt_book_toml: frozendict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    folder = _book(tmp_path, excerpt_book_toml[KADESH])

    def succeed(folder: BookFolder, config: BookConfig, *, workers: int = 0) -> None:
        del folder, config, workers

    def fail(folder: BookFolder, config: BookConfig, *, workers: int = 0) -> None:
        del config, workers
        message = f"{folder.lines_json} does not exist"
        raise InputFileError(message)

    monkeypatch.setattr(
        cli,
        "_STAGES",
        tuple(
            replace(stage, run=fail if stage.name == "structure" else succeed)
            for stage in cli._STAGES
        ),
    )
    with (
        caplog.at_level(logging.ERROR, logger="galley.cli"),
        pytest.raises(InputFileError) as raised,
    ):
        main(["run", str(folder.root)])

    (record,) = caplog.records
    assert record.getMessage() == (
        f"galley2epub run failed in structure: {raised.value}"
    )


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
    excerpt_books: frozendict[str, BookFolder],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    folder = _copy_of_run(tmp_path, excerpt_books[KADESH])
    monkeypatch.setenv("PATH", "")

    with pytest.raises(ExternalProgramError) as raised:
        main([command, str(folder.root)])

    assert str(raised.value) == (
        "pandoc is not installed; install it with `brew install pandoc`"
    )
    # No stage ran: each would have deleted its own file first.
    assert _names(folder) == _files_up_to("epub")


def _path_with_pandoc_only(tmp_path: Path) -> str:
    """A PATH whose one folder holds a link to pandoc, so that Tesseract and
    its tools are missing."""
    pandoc = shutil.which("pandoc")
    assert pandoc is not None
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "pandoc").symlink_to(pandoc)
    return str(bin_dir)


# Changes PATH and the word list's cache folder for the whole process.
@pytest.mark.thread_unsafe
@pytest.mark.pandoc
@pytest.mark.parametrize(
    ("command", "first_stage"),
    [("run", "analyze"), ("analyze", "analyze"), ("structure", "structure")],
)
def test_a_command_running_analyze_or_structure_stops_without_tesseract_or_a_cached_word_list(
    command: str,
    first_stage: str,
    tmp_path: Path,
    excerpt_books: frozendict[str, BookFolder],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    folder = _copy_of_run(tmp_path, excerpt_books[KADESH])
    monkeypatch.setenv("PATH", _path_with_pandoc_only(tmp_path))
    monkeypatch.setattr(wordlist, "DEFAULT_CACHE_DIR", tmp_path / "no-cache")

    with pytest.raises(ExternalProgramError) as raised:
        main([command, str(folder.root)])

    assert str(raised.value) == (
        "tesseract, combine_tessdata and dawg2wordlist are not installed; "
        f"{first_stage} needs them once to extract the word list of eng from "
        "Tesseract's data: install them with `brew install tesseract`"
    )
    # No stage ran: each would have deleted its own file first.
    assert _names(folder) == _files_up_to("epub")


# Changes PATH and the word list's cache folder for the whole process.
@pytest.mark.thread_unsafe
@pytest.mark.pandoc
def test_a_command_without_analyze_or_structure_runs_without_tesseract(
    tmp_path: Path,
    excerpt_books: frozendict[str, BookFolder],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    folder = _copy_of_run(tmp_path, excerpt_books[KADESH])
    monkeypatch.setenv("PATH", _path_with_pandoc_only(tmp_path))
    monkeypatch.setattr(wordlist, "DEFAULT_CACHE_DIR", tmp_path / "no-cache")

    main(["markdown", str(folder.root)])

    assert _names(folder) == _files_up_to("markdown")


# Changes PATH and the word list's cache folder for the whole process.
@pytest.mark.thread_unsafe
@pytest.mark.pandoc
def test_structure_runs_without_tesseract_when_the_word_list_is_cached(
    tmp_path: Path,
    excerpt_books: frozendict[str, BookFolder],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    folder = _copy_of_run(tmp_path, excerpt_books[KADESH])
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    (cache_dir / "eng.txt").write_text("the\nbattle\n", encoding="utf-8")
    monkeypatch.setenv("PATH", _path_with_pandoc_only(tmp_path))
    monkeypatch.setattr(wordlist, "DEFAULT_CACHE_DIR", cache_dir)

    main(["structure", str(folder.root)])

    assert _names(folder) == _files_up_to("structure")


def _cached_word_list(tmp_path: Path) -> Path:
    """A word list's cache folder holding a stand-in English list, so that
    no stage needs Tesseract's tools to extract it."""
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    (cache_dir / "eng.txt").write_text("the\nbattle\n", encoding="utf-8")
    return cache_dir


# Changes PATH and the word list's cache folder for the whole process.
@pytest.mark.thread_unsafe
@pytest.mark.pandoc
@pytest.mark.parametrize("ocr", ["verify", "redo"])
@pytest.mark.parametrize("command", ["run", "layout"])
def test_a_command_running_layout_that_rereads_stops_without_tesseract(
    command: str,
    ocr: str,
    tmp_path: Path,
    excerpt_books: frozendict[str, BookFolder],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # docs/specs/reocr.md, section 3: layout re-reads small print with
    # Tesseract unless ocr is "trust", so the command checks for it first.
    folder = _copy_of_run(tmp_path, excerpt_books[KADESH])
    with folder.book_toml.open("a", encoding="utf-8") as toml:
        toml.write(f'ocr = "{ocr}"\n')
    monkeypatch.setenv("PATH", _path_with_pandoc_only(tmp_path))
    monkeypatch.setattr(wordlist, "DEFAULT_CACHE_DIR", _cached_word_list(tmp_path))

    with pytest.raises(ExternalProgramError) as raised:
        main([command, str(folder.root)])

    assert str(raised.value) == (
        "tesseract is not installed; layout reads small print with it unless "
        'the config has ocr = "trust": install it with `brew install tesseract`'
    )
    # No stage ran: each would have deleted its own file first.
    assert _names(folder) == _files_up_to("epub")


# Changes PATH and the word list's cache folder for the whole process.
@pytest.mark.thread_unsafe
@pytest.mark.pandoc
def test_layout_that_rereads_stops_without_the_tools_of_a_word_list_not_cached(
    tmp_path: Path,
    excerpt_books: frozendict[str, BookFolder],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    folder = _copy_of_run(tmp_path, excerpt_books[KADESH])
    monkeypatch.setenv("PATH", _path_with_pandoc_only(tmp_path))
    monkeypatch.setattr(wordlist, "DEFAULT_CACHE_DIR", tmp_path / "no-cache")

    with pytest.raises(ExternalProgramError) as raised:
        main(["layout", str(folder.root)])

    assert str(raised.value) == (
        "tesseract, combine_tessdata and dawg2wordlist are not installed; "
        "layout needs them once to extract the word list of eng from "
        "Tesseract's data: install them with `brew install tesseract`"
    )
    assert _names(folder) == _files_up_to("epub")


# Changes PATH and the word list's cache folder for the whole process.
@pytest.mark.thread_unsafe
@pytest.mark.pandoc
def test_layout_with_ocr_trust_rereads_nothing_and_runs_without_tesseract(
    tmp_path: Path,
    excerpt_books: frozendict[str, BookFolder],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    folder = _copy_of_run(tmp_path, excerpt_books[KADESH])
    with folder.book_toml.open("a", encoding="utf-8") as toml:
        toml.write('ocr = "trust"\n')
    monkeypatch.setenv("PATH", _path_with_pandoc_only(tmp_path))
    monkeypatch.setattr(wordlist, "DEFAULT_CACHE_DIR", tmp_path / "no-cache")

    main(["layout", str(folder.root)])

    assert _names(folder) == _files_up_to("layout")
    assert read_lines(folder.lines_json).rereads == ()
