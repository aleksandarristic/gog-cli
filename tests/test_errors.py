from __future__ import annotations

import pytest

import gog_cli.cli as cli_module
from gog_cli.cli import main
from gog_cli.errors import (
    AuthError,
    ExitCode,
    FilesystemError,
    GogError,
    NetworkError,
    ParserError,
    UsageError,
    VerificationError,
)


def test_exit_code_values() -> None:
    assert ExitCode.SUCCESS == 0
    assert ExitCode.FAILURE == 1
    assert ExitCode.USAGE == 2
    assert ExitCode.AUTH == 3
    assert ExitCode.NETWORK == 4
    assert ExitCode.VERIFICATION == 5
    assert ExitCode.FILESYSTEM == 6
    assert ExitCode.PARSER == 7


def test_each_error_has_correct_exit_code() -> None:
    assert GogError().exit_code == ExitCode.FAILURE
    assert UsageError().exit_code == ExitCode.USAGE
    assert AuthError().exit_code == ExitCode.AUTH
    assert NetworkError().exit_code == ExitCode.NETWORK
    assert VerificationError().exit_code == ExitCode.VERIFICATION
    assert FilesystemError().exit_code == ExitCode.FILESYSTEM
    assert ParserError().exit_code == ExitCode.PARSER


def test_gog_errors_are_exceptions() -> None:
    for cls in (
        GogError,
        UsageError,
        AuthError,
        NetworkError,
        VerificationError,
        FilesystemError,
        ParserError,
    ):
        assert issubclass(cls, Exception)
        assert issubclass(cls, GogError)


def test_gog_error_caught_in_main(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def raise_auth_error(_args: object) -> int:
        raise AuthError("session expired")

    monkeypatch.setattr(cli_module, "handle_list_purchased", raise_auth_error)
    result = main(["list", "purchased"])

    assert result == ExitCode.AUTH
    assert "session expired" in capsys.readouterr().err


def test_gog_error_message_goes_to_stderr(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def raise_parser_error(_args: object) -> int:
        raise ParserError("unexpected response shape")

    monkeypatch.setattr(cli_module, "handle_list_purchased", raise_parser_error)
    main(["list", "purchased"])

    captured = capsys.readouterr()
    assert "unexpected response shape" in captured.err
    assert captured.out == ""
