"""Tests of galley_eval.cli, the galley-eval command (spec section 9)."""

import pytest

from galley_eval.cli import main


def test_help_lists_the_three_subcommands_and_exits_with_code_0(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as raised:
        main(["--help"])
    assert raised.value.code == 0
    assert "{run,compare,summary}" in capsys.readouterr().out


@pytest.mark.parametrize("argv", [["run", "haskins"], ["compare"], ["summary"]])
def test_subcommand_not_built_yet_exits_with_code_1(
    argv: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as raised:
        main(argv)
    assert raised.value.code == 1
    assert "not built yet" in capsys.readouterr().err


def test_unknown_subcommand_exits_with_code_2() -> None:
    with pytest.raises(SystemExit) as raised:
        main(["score"])
    assert raised.value.code == 2
