from __future__ import annotations

import io

import pytest

from gog_cli.errors import UsageError
from gog_cli.prompt import is_interactive, numbered_prompt


def test_is_interactive_non_tty() -> None:
    # pytest runs with stdin not a TTY
    assert is_interactive() is False


def test_numbered_prompt_select_all(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO("all\n"))
    result = numbered_prompt(["Game A", "Game B", "Game C"])
    assert result == [0, 1, 2]


def test_numbered_prompt_select_all_uppercase(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO("ALL\n"))
    result = numbered_prompt(["Game A", "Game B"])
    assert result == [0, 1]


def test_numbered_prompt_single(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO("2\n"))
    result = numbered_prompt(["Game A", "Game B", "Game C"])
    assert result == [1]


def test_numbered_prompt_comma_separated(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO("1,3\n"))
    result = numbered_prompt(["Game A", "Game B", "Game C"])
    assert result == [0, 2]


def test_numbered_prompt_with_spaces(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO("1, 3\n"))
    result = numbered_prompt(["Game A", "Game B", "Game C"])
    assert result == [0, 2]


def test_numbered_prompt_invalid_text(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO("abc\n"))
    with pytest.raises(UsageError, match="Invalid selection"):
        numbered_prompt(["Game A", "Game B"])


def test_numbered_prompt_out_of_range_high(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO("5\n"))
    with pytest.raises(UsageError, match="out of range"):
        numbered_prompt(["Game A", "Game B"])


def test_numbered_prompt_out_of_range_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO("0\n"))
    with pytest.raises(UsageError, match="out of range"):
        numbered_prompt(["Game A", "Game B"])


def test_numbered_prompt_empty_input(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO("\n"))
    with pytest.raises(UsageError, match="No selection"):
        numbered_prompt(["Game A", "Game B"])


def test_numbered_prompt_empty_items() -> None:
    with pytest.raises(UsageError, match="No items"):
        numbered_prompt([])


def test_numbered_prompt_custom_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO("1\n"))
    result = numbered_prompt(["Only Game"], prompt="Pick one:")
    assert result == [0]
