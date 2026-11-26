"""Tests of galley_eval.cli, the galley-eval command (spec section 9)."""

import logging
import shutil
from collections.abc import Callable
from pathlib import Path

import pytest

import galley_eval.cli
from galley.book_folder import BookFolder
from galley.config import read_config
from galley_eval.books import EvaluationBook
from galley_eval.cli import (
    book_toml,
    compare_books,
    galley_error_lines,
    main,
    run_galley,
)
from galley_eval.errors import AlignmentInvariantError, GalleyRunError
from galley_eval.evaluate import Evaluation

type SmallEvaluation = Callable[[EvaluationBook | None], Evaluation]

_REPOSITORY = Path(__file__).resolve().parents[3]


def test_help_lists_the_six_subcommands_and_exits_with_code_0(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as raised:
        main(["--help"])
    assert raised.value.code == 0
    assert (
        "{run,compare,summary,edits,edits-score,edits-compare}"
        in capsys.readouterr().out
    )


def test_unknown_subcommand_exits_with_code_2() -> None:
    with pytest.raises(SystemExit) as raised:
        main(["score"])
    assert raised.value.code == 2


def test_unknown_book_exits_with_code_2_names_it_and_makes_no_folder(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A repository of its own, whose runs/evaluation/ must not be made.
    (tmp_path / "evaluation").mkdir()
    shutil.copy(
        _REPOSITORY / "evaluation" / "books.toml",
        tmp_path / "evaluation" / "books.toml",
    )
    repository = galley_eval.cli._repository()
    monkeypatch.setattr(
        galley_eval.cli,
        "_repository",
        lambda: type(repository)(git=repository.git, root=tmp_path, commit="abc123"),
    )
    with pytest.raises(SystemExit) as raised:
        main(["compare", "nosuchbook"])
    assert raised.value.code == 2
    assert "nosuchbook" in capsys.readouterr().err
    assert not (tmp_path / "runs").exists()


def test_book_toml_is_read_by_galley_with_every_field(
    tmp_path: Path, small_book: Callable[[str], EvaluationBook]
) -> None:
    pdf = tmp_path / "a \\ book\n.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    book = small_book("small")
    config_path = tmp_path / "book.toml"
    config_path.write_text(book_toml(book, pdf), encoding="utf-8")
    config = read_config(config_path)
    assert config.pdf == pdf.resolve()
    # The title has curly quotes, an author straight ones.
    assert (config.title, config.authors) == (book.title, book.authors)
    assert config.language is book.language
    assert config.exclude_pages == book.exclude_pages
    assert config.contents_pages == book.contents_pages
    assert config.plate_pages == book.plate_pages


def test_galley_error_lines_are_those_naming_the_stage() -> None:
    stderr = (
        "INFO galley.cli: running analyze on x\n"
        "ERROR galley.cli: galley2epub run failed in extract: bad page\n"
        "Traceback (most recent call last):\n"
        "galley.errors.InputFileError: bad page\n"
    )
    assert galley_error_lines(stderr) == (
        "ERROR galley.cli: galley2epub run failed in extract: bad page"
    )
    assert galley_error_lines("one\nlast line\n") == "last line"


@pytest.mark.timeout(60)
def test_galley_run_on_a_folder_made_to_fail_raises_with_galley_error(
    tmp_path: Path, small_book: Callable[[str], EvaluationBook]
) -> None:
    program = shutil.which("galley2epub")
    assert program is not None  # installed with the workspace
    folder = BookFolder(tmp_path)
    folder.book_toml.write_text(
        book_toml(small_book("small"), tmp_path / "missing.pdf"), encoding="utf-8"
    )
    with pytest.raises(GalleyRunError, match=r"exited with 1: ERROR .*missing\.pdf"):
        run_galley(program, folder)


def test_one_failing_book_is_reported_and_the_others_go_on(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    small_book: Callable[[str], EvaluationBook],
    small_evaluation: SmallEvaluation,
) -> None:
    books = (small_book("broken"), small_book("fine"))
    ran: list[str] = []

    def galley(folder: BookFolder) -> None:
        ran.append(folder.root.name)
        if folder.root.name == "broken":
            message = "galley2epub run broken exited with 1: ERROR bad pdf"
            raise GalleyRunError(message)

    def compare(book: EvaluationBook, folder: BookFolder, html: Path) -> Evaluation:
        assert html.name == "pg42-images.html"
        assert folder.book_toml.exists()
        return small_evaluation(book)

    with caplog.at_level(logging.INFO):
        failed = compare_books(
            books,
            runs_dir=tmp_path,
            samples_dir=tmp_path / "samples",
            commit="abc123",
            galley=galley,
            compare=compare,
        )
    assert failed == ("broken",)
    assert ran == ["broken", "fine"]
    assert "broken: failed: galley2epub run broken exited with 1" in caplog.text
    assert "fine: galley " in caplog.text
    assert (tmp_path / "fine" / "evaluation" / "scorecard.json").exists()
    assert (tmp_path / "fine" / "galley-commit.txt").read_text(
        encoding="utf-8"
    ) == "abc123\n"
    assert (
        (tmp_path / "broken" / "evaluation" / "failed.txt")
        .read_text(encoding="utf-8")
        .startswith("galley2epub run broken exited with 1")
    )
    assert "samples/public_domain/broken00.pdf" in (
        tmp_path / "broken" / "book.toml"
    ).read_text(encoding="utf-8")


def test_compare_of_a_book_never_run_is_reported(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    small_book: Callable[[str], EvaluationBook],
    small_evaluation: SmallEvaluation,
) -> None:
    def compare(book: EvaluationBook, folder: BookFolder, html: Path) -> Evaluation:
        del folder, html
        return small_evaluation(book)

    failed = compare_books(
        (small_book("never"),),
        runs_dir=tmp_path,
        samples_dir=tmp_path,
        commit="abc123",
        galley=None,
        compare=compare,
    )
    assert failed == ("never",)
    assert "galley-eval run never" in caplog.text


def test_compare_of_a_folder_without_its_galley_commit_fails(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    small_book: Callable[[str], EvaluationBook],
    small_evaluation: SmallEvaluation,
) -> None:
    (tmp_path / "old").mkdir()

    def compare(book: EvaluationBook, folder: BookFolder, html: Path) -> Evaluation:
        del folder, html
        return small_evaluation(book)

    failed = compare_books(
        (small_book("old"),),
        runs_dir=tmp_path,
        samples_dir=tmp_path,
        commit="abc123",
        galley=None,
        compare=compare,
    )
    assert failed == ("old",)
    assert "galley-commit.txt does not exist" in caplog.text


def _no_galley(folder: BookFolder) -> None:
    del folder


def test_a_fault_of_the_alignment_stops_the_command(
    tmp_path: Path, small_book: Callable[[str], EvaluationBook]
) -> None:
    def compare(book: EvaluationBook, folder: BookFolder, html: Path) -> Evaluation:
        del book, folder, html
        message = "galley token 3 is in pairings 1 and 2"
        raise AlignmentInvariantError(message)

    with pytest.raises(AlignmentInvariantError):
        compare_books(
            (small_book("first"), small_book("second")),
            runs_dir=tmp_path,
            samples_dir=tmp_path,
            commit="abc123",
            galley=_no_galley,
            compare=compare,
        )


@pytest.mark.thread_unsafe
def test_main_exits_with_1_after_a_failed_book_and_shows_it_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A repository of its own, so that the real runs/ is not touched; the
    # book was never run there.
    (tmp_path / "evaluation").mkdir()
    shutil.copy(
        _REPOSITORY / "evaluation" / "books.toml",
        tmp_path / "evaluation" / "books.toml",
    )
    repository = galley_eval.cli._repository()
    monkeypatch.setattr(
        galley_eval.cli,
        "_repository",
        lambda: type(repository)(git=repository.git, root=tmp_path, commit="abc123"),
    )
    monkeypatch.setenv("GALLEY_SAMPLES", str(tmp_path / "samples"))
    with pytest.raises(SystemExit) as raised:
        main(["compare", "haskins"])
    assert raised.value.code == 1
    summary = (tmp_path / "runs" / "evaluation" / "summary.md").read_text(
        encoding="utf-8"
    )
    assert "| haskins | failed: " in summary
    assert "| stubbs" not in summary
