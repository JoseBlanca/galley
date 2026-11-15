"""Tests of galley_eval.cli, the galley-eval command (spec section 9)."""

import logging
from collections.abc import Callable
from pathlib import Path

import pytest

from galley.book_folder import BookFolder
from galley.config import read_config
from galley_eval.books import EvaluationBook
from galley_eval.cli import book_toml, compare_books, main, run_galley
from galley_eval.errors import GalleyRunError
from galley_eval.evaluate import Evaluation
from galley_eval.output import RunInfo

type SmallEvaluation = Callable[[EvaluationBook | None], Evaluation]

_RUN = RunInfo(galley_commit="abc123", date="2026-11-15", tool_version="0.1.0")


def test_help_lists_the_three_subcommands_and_exits_with_code_0(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as raised:
        main(["--help"])
    assert raised.value.code == 0
    assert "{run,compare,summary}" in capsys.readouterr().out


def test_unknown_subcommand_exits_with_code_2() -> None:
    with pytest.raises(SystemExit) as raised:
        main(["score"])
    assert raised.value.code == 2


def test_unknown_book_exits_with_code_2_and_names_it(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as raised:
        main(["compare", "nosuchbook"])
    assert raised.value.code == 2
    assert "nosuchbook" in capsys.readouterr().err


def test_book_toml_is_read_by_galley_with_every_field(
    tmp_path: Path, small_book: Callable[[str], EvaluationBook]
) -> None:
    pdf = tmp_path / "a book.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    book = small_book("small")
    config_path = tmp_path / "book.toml"
    config_path.write_text(book_toml(book, pdf), encoding="utf-8")
    config = read_config(config_path)
    assert config.pdf == pdf.resolve()
    assert (config.title, config.authors) == (book.title, book.authors)
    assert config.language is book.language
    assert config.exclude_pages == book.exclude_pages


@pytest.mark.timeout(60)
def test_galley_run_on_a_folder_made_to_fail_raises_with_galley_error(
    tmp_path: Path, small_book: Callable[[str], EvaluationBook]
) -> None:
    folder = BookFolder(tmp_path)
    folder.book_toml.write_text(
        book_toml(small_book("small"), tmp_path / "missing.pdf"), encoding="utf-8"
    )
    with pytest.raises(GalleyRunError, match=r"exited with 1:(.|\n)*missing\.pdf"):
        run_galley(folder)


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
            message = "galley2epub run broken exited with 1:\nConfigError: bad pdf"
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
            run=_RUN,
            galley=galley,
            compare=compare,
        )
    assert failed == ("broken",)
    assert ran == ["broken", "fine"]
    assert "broken: failed: galley2epub run broken exited with 1" in caplog.text
    assert "fine: galley " in caplog.text
    assert (tmp_path / "fine" / "evaluation" / "scorecard.json").exists()
    assert not (tmp_path / "broken" / "evaluation").exists()
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
        run=_RUN,
        galley=None,
        compare=compare,
    )
    assert failed == ("never",)
    assert "galley-eval run never" in caplog.text
