"""Tests of galley.cli, the galley2epub command (spec section 9, "cli.py"
and "Other tests of this work package").

The tests that need the files of analyze or extract copy them from the
session fixture `excerpt_books` into a folder of their own, so that no
test runs a stage on an excerpt that the fixture has run already.
"""

import logging
import re
import shutil
import socket
import subprocess
import sys
import tomllib
import zipfile
from collections.abc import Callable
from dataclasses import replace
from importlib.metadata import entry_points
from pathlib import Path

import pytest

from galley import cli, wordlist
from galley.book_folder import BookFolder
from galley.cli import main
from galley.config import BookConfig, Language, read_config
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


def _contents(folder: BookFolder) -> dict[Path, bytes]:
    """Every file of the book folder, its subfolders' too, with its bytes."""
    return {
        path: path.read_bytes() for path in folder.root.rglob("*") if path.is_file()
    }


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
    assert tuple(subcommands.group(1).split(",")) == (
        "run",
        *STAGES[:4],
        "correct",
        *STAGES[4:],
    )


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


@pytest.mark.parametrize("command", ["edits-from"])
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


def _closed_port() -> int:
    """A port of this machine on which nothing listens, for a moment."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def test_run_with_correct_true_and_no_lm_studio_stops_before_analyze(
    tmp_path: Path, excerpt_book_toml: frozendict[str, str]
) -> None:
    # Correct spec, section 4: run stops before the first stage.
    server = f"http://127.0.0.1:{_closed_port()}"
    folder = _book(
        tmp_path,
        excerpt_book_toml[KADESH] + f'correct = true\ncorrect_server = "{server}"\n',
    )

    with pytest.raises(ExternalProgramError, match="LM Studio's server is not running"):
        main(["run", str(folder.root)])

    assert sorted(tmp_path.iterdir()) == [folder.book_toml]


def test_run_runs_correct_only_with_correct_true(
    tmp_path: Path, excerpt_book_toml: frozendict[str, str]
) -> None:
    folder = _book(tmp_path, excerpt_book_toml[KADESH])
    config = read_config(folder.book_toml)

    def names(command: str, config: BookConfig) -> list[str]:
        return [stage.name for stage in cli._stages_of(command, config)]

    assert "correct" not in names("run", config)
    assert names("run", replace(config, correct=True)) == [
        "analyze",
        "extract",
        "layout",
        "structure",
        "correct",
        "markdown",
        "epub",
    ]
    assert names("correct", config) == ["correct"]


def _recorded_run(
    folder: BookFolder, arguments: list[str], monkeypatch: pytest.MonkeyPatch
) -> list[tuple[str, bool]]:
    """The stages `galley2epub run` calls on `folder` with `arguments`, each
    with the config's `correct` it receives; no stage does any work."""
    calls: list[tuple[str, bool]] = []

    def recorder(name: str) -> Callable[..., None]:
        def record(folder: BookFolder, config: BookConfig, *, workers: int = 0) -> None:
            del folder, workers
            calls.append((name, config.correct))

        return record

    monkeypatch.setattr(
        cli,
        "_STAGES",
        tuple(replace(stage, run=recorder(stage.name)) for stage in cli._STAGES),
    )
    main(["run", str(folder.root), *arguments])
    return calls


def test_run_with_correct_flag_runs_correct_although_the_config_has_correct_false(
    tmp_path: Path,
    excerpt_book_toml: frozendict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Architecture section 14. Kept answers leave the server check to the
    # stage, which is recorded here, so no model is asked.
    folder = _book(tmp_path, excerpt_book_toml[KADESH] + "correct = false\n")
    folder.answers_dir.mkdir()

    calls = _recorded_run(folder, ["--correct"], monkeypatch)

    assert calls == [
        ("analyze", True),
        ("extract", True),
        ("layout", True),
        ("structure", True),
        ("correct", True),
        ("markdown", True),
        ("epub", True),
    ]


def test_run_with_no_correct_flag_skips_correct_although_the_config_has_correct_true(
    tmp_path: Path,
    excerpt_book_toml: frozendict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    folder = _book(tmp_path, excerpt_book_toml[KADESH] + "correct = true\n")
    folder.answers_dir.mkdir()

    calls = _recorded_run(folder, ["--no-correct"], monkeypatch)

    assert calls == [(stage, False) for stage in STAGES]


@pytest.mark.parametrize(
    ("correct", "expected_stages"),
    [
        ("false", STAGES),
        ("true", (*STAGES[:4], "correct", *STAGES[4:])),
    ],
)
def test_run_without_a_correct_flag_runs_correct_as_the_config_says(
    correct: str,
    expected_stages: tuple[str, ...],
    tmp_path: Path,
    excerpt_book_toml: frozendict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    folder = _book(tmp_path, excerpt_book_toml[KADESH] + f"correct = {correct}\n")
    folder.answers_dir.mkdir()

    calls = _recorded_run(folder, [], monkeypatch)

    assert cli._parser().parse_args(["run", str(folder.root)]).correct is None
    assert calls == [(stage, correct == "true") for stage in expected_stages]


def test_run_with_no_correct_and_correct_true_does_not_check_lm_studio(
    tmp_path: Path,
    excerpt_book_toml: frozendict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # No answers/, so with correct = true the command would check the
    # server, on a port where nothing listens, before analyze.
    folder = _book(
        tmp_path,
        excerpt_book_toml[KADESH]
        + 'correct = true\ncorrect_server = "http://localhost:9"\n',
    )

    calls = _recorded_run(folder, ["--no-correct"], monkeypatch)

    assert [stage for stage, _ in calls] == list(STAGES)


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
def test_structure_stops_without_tesseracts_tools_or_a_cached_word_list(
    tmp_path: Path,
    excerpt_books: frozendict[str, BookFolder],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    folder = _copy_of_run(tmp_path, excerpt_books[KADESH])
    monkeypatch.setenv("PATH", _path_with_pandoc_only(tmp_path))
    monkeypatch.setattr(wordlist, "DEFAULT_CACHE_DIR", tmp_path / "no-cache")

    with pytest.raises(ExternalProgramError) as raised:
        main(["structure", str(folder.root)])

    assert str(raised.value) == (
        "tesseract, combine_tessdata and dawg2wordlist are not installed; "
        "structure needs them once to extract the word list of eng from "
        "Tesseract's data: install them with `brew install tesseract`"
    )
    # No stage ran: each would have deleted its own file first.
    assert _names(folder) == _files_up_to("epub")


# Changes PATH and the word list's cache folder for the whole process.
@pytest.mark.thread_unsafe
@pytest.mark.pandoc
@pytest.mark.parametrize("command", ["run", "analyze"])
@pytest.mark.parametrize("ocr", ["verify", "trust", "redo"])
@pytest.mark.parametrize("word_list", ["cached", "not cached"])
def test_a_command_running_analyze_stops_without_tesseract_which_reads_blank_pages(
    command: str,
    ocr: str,
    word_list: str,
    tmp_path: Path,
    excerpt_books: frozendict[str, BookFolder],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # docs/specs/analyze.md, section 7: analyze reads the pages without a
    # text layer with Tesseract under every `ocr`, and the command looks for
    # it before any other check for Tesseract or its tools.
    folder = _copy_of_run(tmp_path, excerpt_books[KADESH])
    with folder.book_toml.open("a", encoding="utf-8") as toml:
        toml.write(f'ocr = "{ocr}"\n')
    monkeypatch.setenv("PATH", _path_with_pandoc_only(tmp_path))
    monkeypatch.setattr(
        wordlist,
        "DEFAULT_CACHE_DIR",
        _cached_word_list(tmp_path) if word_list == "cached" else tmp_path / "no-cache",
    )
    before = _contents(folder)

    with pytest.raises(ExternalProgramError) as raised:
        main([command, str(folder.root)])

    assert str(raised.value) == (
        "tesseract is not installed; analyze reads the pages without a text "
        "layer with it: install it with `brew install tesseract`"
    )
    # No stage ran: each would have deleted or written its own file first.
    assert _contents(folder) == before


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
def test_layout_that_rereads_stops_without_tesseract(
    tmp_path: Path,
    excerpt_books: frozendict[str, BookFolder],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # docs/specs/reocr.md, section 3: layout re-reads small print with
    # Tesseract under ocr = "verify", the default, so the command checks
    # for it first. Under run, analyze's check names analyze first (analyze
    # spec section 7).
    folder = _copy_of_run(tmp_path, excerpt_books[KADESH])
    monkeypatch.setenv("PATH", _path_with_pandoc_only(tmp_path))
    monkeypatch.setattr(wordlist, "DEFAULT_CACHE_DIR", _cached_word_list(tmp_path))

    with pytest.raises(ExternalProgramError) as raised:
        main(["layout", str(folder.root)])

    assert str(raised.value) == (
        "tesseract is not installed; layout reads small print with it when "
        'the config has ocr = "verify", the default: install it with '
        "`brew install tesseract`"
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
def test_extract_under_redo_stops_without_tesseract(
    tmp_path: Path,
    excerpt_books: frozendict[str, BookFolder],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Architecture section 7b: under ocr = "redo" extract reads every text
    # page with Tesseract, and the command looks for it before extract
    # starts; when analyze runs, its own check names analyze (analyze spec
    # section 7).
    folder = _copy_of_run(tmp_path, excerpt_books[KADESH])
    with folder.book_toml.open("a", encoding="utf-8") as toml:
        toml.write('ocr = "redo"\n')
    monkeypatch.setenv("PATH", _path_with_pandoc_only(tmp_path))
    monkeypatch.setattr(wordlist, "DEFAULT_CACHE_DIR", _cached_word_list(tmp_path))

    with pytest.raises(ExternalProgramError) as raised:
        main(["extract", str(folder.root)])

    assert str(raised.value) == (
        'tesseract is not installed; with ocr = "redo" extract needs it, '
        "as extract reads every text page with it: install it with "
        "`brew install tesseract`"
    )
    assert _names(folder) == _files_up_to("epub")


# Changes PATH and the word list's cache folder for the whole process.
@pytest.mark.thread_unsafe
@pytest.mark.pandoc
@pytest.mark.parametrize("ocr", ["trust", "redo"])
def test_layout_with_ocr_trust_or_redo_rereads_nothing_and_runs_without_tesseract(
    ocr: str,
    tmp_path: Path,
    excerpt_books: frozendict[str, BookFolder],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # docs/specs/reocr.md, section 3: under "redo" every page is already
    # Tesseract's and layout re-reads nothing.
    folder = _copy_of_run(tmp_path, excerpt_books[KADESH])
    with folder.book_toml.open("a", encoding="utf-8") as toml:
        toml.write(f'ocr = "{ocr}"\n')
    monkeypatch.setenv("PATH", _path_with_pandoc_only(tmp_path))
    monkeypatch.setattr(wordlist, "DEFAULT_CACHE_DIR", tmp_path / "no-cache")

    main(["layout", str(folder.root)])

    assert _names(folder) == _files_up_to("layout")
    assert read_lines(folder.lines_json).rereads == ()


def test_correct_on_a_folder_with_kept_answers_leaves_the_server_check_to_the_stage(
    tmp_path: Path, excerpt_book_toml: frozendict[str, str]
) -> None:
    # Correct spec, section 4: the stage checks LM Studio before its first
    # request only, so that a book is rebuilt from its kept answers without it.
    server = f"http://127.0.0.1:{_closed_port()}"
    folder = _book(
        tmp_path,
        excerpt_book_toml[KADESH] + f'correct = true\ncorrect_server = "{server}"\n',
    )
    config = read_config(folder.book_toml)
    stages = cli._stages_of("correct", config)
    with pytest.raises(ExternalProgramError, match="LM Studio's server is not running"):
        cli._check_before_any_stage(stages, config, folder)
    folder.answers_dir.mkdir()
    cli._check_before_any_stage(stages, config, folder)


# run on a PDF (architecture section 14)

# A small excerpt: the stages are stand-ins, so only its being a file matters.
SMALL_PDF = "haskins_endpapers"
PDF_OPTIONS = ("--title", "A Title", "--author", "An Author", "--language", "en")


def _pdf_in(tmp_path: Path, excerpt_pdf: frozendict[str, Path], name: str) -> Path:
    """A copy of a small excerpt PDF in `tmp_path`, named `name`."""
    return Path(shutil.copy(excerpt_pdf[SMALL_PDF], tmp_path / name))


def _recorded_stages(
    path: Path, arguments: list[str], monkeypatch: pytest.MonkeyPatch
) -> list[tuple[str, Path, BookConfig]]:
    """The stages `galley2epub run` calls on `path` with `arguments`, each
    with the book folder and the config it receives; no stage does any work."""
    calls: list[tuple[str, Path, BookConfig]] = []

    def recorder(name: str) -> Callable[..., None]:
        def record(folder: BookFolder, config: BookConfig, *, workers: int = 0) -> None:
            del workers
            calls.append((name, folder.root, config))

        return record

    monkeypatch.setattr(
        cli,
        "_STAGES",
        tuple(replace(stage, run=recorder(stage.name)) for stage in cli._STAGES),
    )
    main(["run", str(path), *arguments])
    return calls


def test_run_on_a_pdf_writes_book_toml_beside_it_and_runs_every_stage_there(
    tmp_path: Path,
    excerpt_pdf: frozendict[str, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pdf = _pdf_in(tmp_path, excerpt_pdf, "haskins.pdf")

    calls = _recorded_stages(
        pdf,
        ["--title", "The Normans", "--author", "C. H. Haskins", "--language", "fr"],
        monkeypatch,
    )

    book_toml = tmp_path / "haskins" / "book.toml"
    with book_toml.open("rb") as toml:
        assert tomllib.load(toml) == {
            "pdf": "../haskins.pdf",
            "title": "The Normans",
            "authors": ["C. H. Haskins"],
            "language": "fr",
        }
    expected = BookConfig(
        pdf=pdf.resolve(),
        title="The Normans",
        authors=("C. H. Haskins",),
        language=Language.FR,
    )
    assert read_config(book_toml) == expected
    assert calls == [(stage, tmp_path / "haskins", expected) for stage in STAGES]


def test_run_on_a_pdf_keeps_the_order_of_repeated_authors_and_takes_upper_case_pdf(
    tmp_path: Path,
    excerpt_pdf: frozendict[str, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pdf = _pdf_in(tmp_path, excerpt_pdf, "Book.PDF")
    authors = ("Zoe Zed", "Adam Ant", "Mia Em")

    calls = _recorded_stages(
        pdf,
        ["--title", "T", "--language", "en"]
        + [option for author in authors for option in ("--author", author)],
        monkeypatch,
    )

    assert read_config(tmp_path / "Book" / "book.toml").authors == authors
    assert {config.authors for _, _, config in calls} == {authors}


def test_run_on_a_pdf_writes_a_title_with_quotes_backslashes_and_accents_that_reads_back(
    tmp_path: Path,
    excerpt_pdf: frozendict[str, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    title = 'The "Book" of C:\\dos\\ \'\'\' and """ é Ñandú 東京\tend'
    author = 'O\'Brien "the \\ Elder"'
    pdf = _pdf_in(tmp_path, excerpt_pdf, 'odd "name" \\ é.pdf')

    _recorded_stages(
        pdf,
        ["--title", title, "--author", author, "--language", "es"],
        monkeypatch,
    )

    config = read_config(tmp_path / 'odd "name" \\ é' / "book.toml")
    assert (config.pdf, config.title, config.authors) == (
        pdf.resolve(),
        title,
        (author,),
    )


@pytest.mark.parametrize("missing", ["--title", "--author", "--language"])
def test_run_on_a_pdf_without_an_option_raises_config_error_naming_it(
    missing: str,
    tmp_path: Path,
    excerpt_pdf: frozendict[str, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pdf = _pdf_in(tmp_path, excerpt_pdf, "book.pdf")
    position = PDF_OPTIONS.index(missing)
    options = [*PDF_OPTIONS[:position], *PDF_OPTIONS[position + 2 :]]

    with pytest.raises(ConfigError, match=f"{missing} is missing"):
        _recorded_stages(pdf, options, monkeypatch)

    assert not (tmp_path / "book").exists()


@pytest.mark.parametrize("empty", ["--title", "--author"])
def test_run_on_a_pdf_with_an_empty_title_or_author_raises_config_error(
    empty: str,
    tmp_path: Path,
    excerpt_pdf: frozendict[str, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pdf = _pdf_in(tmp_path, excerpt_pdf, "book.pdf")
    position = PDF_OPTIONS.index(empty)
    options = [*PDF_OPTIONS[: position + 1], "", *PDF_OPTIONS[position + 2 :]]

    with pytest.raises(ConfigError, match=f"{empty} must not be empty"):
        _recorded_stages(pdf, options, monkeypatch)

    assert not (tmp_path / "book").exists()


@pytest.mark.parametrize("option", ["--title", "--author", "--language"])
def test_run_on_a_folder_with_a_pdf_option_raises_config_error(
    option: str,
    tmp_path: Path,
    excerpt_book_toml: frozendict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    folder = _book(tmp_path, excerpt_book_toml[KADESH])
    value = PDF_OPTIONS[PDF_OPTIONS.index(option) + 1]

    with pytest.raises(ConfigError, match=f"{option} is taken only with a PDF"):
        _recorded_stages(folder.root, [option, value], monkeypatch)


def test_run_on_a_pdf_reuses_an_equal_book_toml_and_leaves_it_unchanged(
    tmp_path: Path,
    excerpt_pdf: frozendict[str, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pdf = _pdf_in(tmp_path, excerpt_pdf, "book.pdf")
    folder = BookFolder(tmp_path / "book")
    folder.root.mkdir()
    # Other text, the same values: keys reordered, a default written out,
    # and the PDF given by its absolute path.
    own_toml = (
        '# my book\nlanguage = "en"\nocr = "verify"\nauthors = ["An Author"]\n'
        f"title = 'A Title'\npdf = '{pdf}'\n"
    ).encode()
    folder.book_toml.write_bytes(own_toml)

    calls = _recorded_stages(pdf, list(PDF_OPTIONS), monkeypatch)

    assert [stage for stage, _, _ in calls] == list(STAGES)
    assert folder.book_toml.read_bytes() == own_toml


def test_run_on_a_pdf_whose_folder_holds_a_different_book_toml_raises_and_keeps_it(
    tmp_path: Path,
    excerpt_pdf: frozendict[str, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pdf = _pdf_in(tmp_path, excerpt_pdf, "book.pdf")
    folder = BookFolder(tmp_path / "book")
    folder.root.mkdir()
    own_toml = (
        b'pdf = "../book.pdf"\ntitle = "A Title"\nauthors = ["An Author"]\n'
        b'language = "en"\ncover_page = 0\n'
    )
    folder.book_toml.write_bytes(own_toml)

    with pytest.raises(ConfigError, match="already holds a different book.toml"):
        _recorded_stages(pdf, list(PDF_OPTIONS), monkeypatch)

    assert folder.book_toml.read_bytes() == own_toml
    assert _names(folder) == ["book.toml"]


def test_run_on_a_pdf_whose_folder_name_is_a_file_raises_config_error(
    tmp_path: Path,
    excerpt_pdf: frozendict[str, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pdf = _pdf_in(tmp_path, excerpt_pdf, "book.pdf")
    (tmp_path / "book").write_text("not a folder", encoding="utf-8")

    with pytest.raises(ConfigError, match="is a file, not the book folder"):
        _recorded_stages(pdf, list(PDF_OPTIONS), monkeypatch)

    assert (tmp_path / "book").read_text(encoding="utf-8") == "not a folder"


@pytest.mark.parametrize(
    ("flag", "expected_stages"),
    [
        ("--no-correct", STAGES),
        ("--correct", (*STAGES[:4], "correct", *STAGES[4:])),
    ],
)
def test_run_on_a_pdf_takes_correct_and_no_correct(
    flag: str,
    expected_stages: tuple[str, ...],
    tmp_path: Path,
    excerpt_pdf: frozendict[str, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pdf = _pdf_in(tmp_path, excerpt_pdf, "book.pdf")
    # A folder made beforehand, without book.toml, is used. Its kept
    # answers leave the server check to the stage, a stand-in here.
    (tmp_path / "book" / "answers").mkdir(parents=True)

    calls = _recorded_stages(pdf, [*PDF_OPTIONS, flag], monkeypatch)

    assert [(stage, config.correct) for stage, _, config in calls] == [
        (stage, flag == "--correct") for stage in expected_stages
    ]


@pytest.mark.parametrize("name", ["notes.txt", "missing.pdf"])
def test_run_on_a_file_not_a_pdf_or_a_missing_pdf_raises_naming_both_forms(
    name: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / name
    if name.endswith(".txt"):
        path.write_text("text", encoding="utf-8")

    with pytest.raises(ConfigError, match="the book's PDF or its book folder"):
        _recorded_stages(path, list(PDF_OPTIONS), monkeypatch)
