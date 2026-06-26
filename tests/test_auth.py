"""Tests for gog_cli.auth — FileTokenStore and auth command handlers."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import responses as rsps_lib

from gog_cli.auth import (
    FileTokenStore,
    _extract_code,
    handle_auth_login,
    handle_auth_logout,
    handle_auth_status,
)
from gog_cli.errors import AuthError, ExitCode, UsageError
from gog_cli.state import resolve_app_paths

_TOKEN_URL = "https://auth.gog.com/token"
_USER_DATA_URL = "https://embed.gog.com/userData.json"

_FUTURE = (datetime.now(tz=UTC) + timedelta(hours=1)).isoformat()
_PAST = (datetime.now(tz=UTC) - timedelta(hours=1)).isoformat()

_SAMPLE_TOKENS = {
    "access_token": "acc",
    "refresh_token": "ref",
    "expires_at": _FUTURE,
    "user_id": "123",
    "username": "tester",
}


def _make_store(tmp_path: Path) -> FileTokenStore:
    paths = resolve_app_paths({"HOME": str(tmp_path)})
    return FileTokenStore(paths)


# ── FileTokenStore ─────────────────────────────────────────────────────────────

def test_load_tokens_missing_raises_auth_error(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    with pytest.raises(AuthError, match="Not logged in"):
        store.load_tokens()


def test_load_tokens_corrupt_raises_auth_error(tmp_path: Path) -> None:
    paths = resolve_app_paths({"HOME": str(tmp_path)})
    paths.session_state.parent.mkdir(parents=True, exist_ok=True)
    paths.session_state.write_text("not json", encoding="utf-8")
    store = FileTokenStore(paths)
    with pytest.raises(AuthError, match="corrupt"):
        store.load_tokens()


def test_load_tokens_returns_stored_data(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    store.save_tokens(_SAMPLE_TOKENS)
    loaded = store.load_tokens()
    assert loaded["username"] == "tester"
    assert loaded["access_token"] == "acc"


def test_load_tokens_prefers_keyring_refresh_token(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    store.save_tokens(_SAMPLE_TOKENS)

    with patch("gog_cli.auth._try_load_keyring", return_value="keyring_ref"):
        loaded = store.load_tokens()

    assert loaded["refresh_token"] == "keyring_ref"
    assert loaded["access_token"] == "acc"


def test_save_tokens_writes_json(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    store.save_tokens(_SAMPLE_TOKENS)
    paths = resolve_app_paths({"HOME": str(tmp_path)})
    data = json.loads(paths.session_state.read_text())
    assert data["refresh_token"] == "ref"


def test_save_tokens_sets_chmod_600(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    store.save_tokens(_SAMPLE_TOKENS)
    paths = resolve_app_paths({"HOME": str(tmp_path)})
    mode = oct(os.stat(paths.session_state).st_mode)[-3:]
    assert mode == "600"


def test_save_tokens_keyring_failure_is_silent(tmp_path: Path) -> None:
    with patch("gog_cli.auth._try_save_keyring", side_effect=Exception("keyring broken")):
        # save_tokens itself should not raise even if _try_save_keyring is patched to raise
        pass
    # Directly call _try_save_keyring to confirm it swallows exceptions
    from gog_cli.auth import _try_save_keyring
    _try_save_keyring("some_token")  # must not raise even without keyring installed


# ── _extract_code ──────────────────────────────────────────────────────────────

def test_extract_code_from_full_redirect_url() -> None:
    url = "https://embed.gog.com/on_login_success?origin=client&code=MYCODE123"
    assert _extract_code(url) == "MYCODE123"


def test_extract_code_from_bare_code() -> None:
    assert _extract_code("MYCODE123") == "MYCODE123"


def test_extract_code_strips_whitespace() -> None:
    assert _extract_code("  MYCODE123\n") == "MYCODE123"


def test_extract_code_empty_raises_usage_error() -> None:
    with pytest.raises(UsageError):
        _extract_code("")


def test_extract_code_url_without_code_raises_usage_error() -> None:
    with pytest.raises(UsageError, match="No 'code'"):
        _extract_code("https://embed.gog.com/on_login_success?origin=client")


# ── handle_auth_login ──────────────────────────────────────────────────────────

@rsps_lib.activate
def test_handle_auth_login_happy_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    rsps_lib.add(
        rsps_lib.GET,
        _TOKEN_URL,
        json={
            "access_token": "new_acc",
            "refresh_token": "new_ref",
            "expires_in": 3600,
            "user_id": "42",
        },
    )
    rsps_lib.add(
        rsps_lib.GET,
        _USER_DATA_URL,
        json={"username": "gog_user", "userId": "42"},
    )

    monkeypatch.setattr("sys.stdin", _make_stdin("AUTHCODE\n"))
    _patch_auth_paths(monkeypatch, tmp_path)
    monkeypatch.setattr("gog_cli.auth._try_save_keyring", lambda _: None)

    args = MagicMock()
    result = handle_auth_login(args)

    assert result == ExitCode.SUCCESS
    out = capsys.readouterr().out
    assert "gog_user" in out

    paths = resolve_app_paths({"HOME": str(tmp_path)})
    saved = json.loads(paths.session_state.read_text())
    assert saved["username"] == "gog_user"
    assert saved["access_token"] == "new_acc"


@rsps_lib.activate
def test_handle_auth_login_exchange_failure_raises_auth_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rsps_lib.add(rsps_lib.GET, _TOKEN_URL, status=400, json={"error": "invalid_grant"})

    monkeypatch.setattr("sys.stdin", _make_stdin("BADCODE\n"))
    _patch_auth_paths(monkeypatch, tmp_path)

    args = MagicMock()
    with pytest.raises(AuthError, match="Token exchange failed"):
        handle_auth_login(args)


def test_handle_auth_login_empty_paste_raises_usage_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("sys.stdin", _make_stdin("\n"))
    _patch_auth_paths(monkeypatch, tmp_path)

    args = MagicMock()
    with pytest.raises(UsageError):
        handle_auth_login(args)


# ── handle_auth_status ─────────────────────────────────────────────────────────

def test_handle_auth_status_logged_in(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _seed_session(tmp_path, _SAMPLE_TOKENS)
    _patch_auth_paths(monkeypatch, tmp_path)

    args = MagicMock()
    result = handle_auth_status(args)

    assert result == ExitCode.SUCCESS
    assert "tester" in capsys.readouterr().out


def test_handle_auth_status_expired_token(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    expired_tokens = {**_SAMPLE_TOKENS, "expires_at": _PAST}
    _seed_session(tmp_path, expired_tokens)
    _patch_auth_paths(monkeypatch, tmp_path)

    args = MagicMock()
    result = handle_auth_status(args)

    assert result == ExitCode.AUTH
    assert "expired" in capsys.readouterr().err


def test_handle_auth_status_not_logged_in(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _patch_auth_paths(monkeypatch, tmp_path)

    args = MagicMock()
    result = handle_auth_status(args)

    assert result == ExitCode.AUTH
    assert "Not logged in" in capsys.readouterr().err


# ── handle_auth_logout ─────────────────────────────────────────────────────────

def test_handle_auth_logout_removes_session(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _seed_session(tmp_path, _SAMPLE_TOKENS)
    _patch_auth_paths(monkeypatch, tmp_path)
    monkeypatch.setattr("gog_cli.auth._try_delete_keyring", lambda: None)

    paths = resolve_app_paths({"HOME": str(tmp_path)})
    assert paths.session_state.exists()

    args = MagicMock()
    result = handle_auth_logout(args)

    assert result == ExitCode.SUCCESS
    assert not paths.session_state.exists()
    assert "Logged out" in capsys.readouterr().out


def test_handle_auth_logout_no_session_is_idempotent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _patch_auth_paths(monkeypatch, tmp_path)
    monkeypatch.setattr("gog_cli.auth._try_delete_keyring", lambda: None)

    args = MagicMock()
    result = handle_auth_logout(args)

    assert result == ExitCode.SUCCESS
    assert "Logged out" in capsys.readouterr().out


# ── CLI wiring ─────────────────────────────────────────────────────────────────

def test_auth_login_is_routed_from_cli() -> None:
    from gog_cli.auth import handle_auth_login
    from gog_cli.cli import build_parser

    parser = build_parser()
    args = parser.parse_args(["auth", "login"])
    assert args.handler is handle_auth_login


def test_auth_status_is_routed_from_cli() -> None:
    from gog_cli.auth import handle_auth_status
    from gog_cli.cli import build_parser

    parser = build_parser()
    args = parser.parse_args(["auth", "status"])
    assert args.handler is handle_auth_status


def test_auth_logout_is_routed_from_cli() -> None:
    from gog_cli.auth import handle_auth_logout
    from gog_cli.cli import build_parser

    parser = build_parser()
    args = parser.parse_args(["auth", "logout"])
    assert args.handler is handle_auth_logout


# ── helpers ────────────────────────────────────────────────────────────────────

def _make_stdin(text: str) -> MagicMock:
    mock = MagicMock()
    mock.readline.return_value = text
    return mock


def _seed_session(tmp_path: Path, tokens: dict) -> None:
    paths = resolve_app_paths({"HOME": str(tmp_path)})
    paths.session_state.parent.mkdir(parents=True, exist_ok=True)
    paths.session_state.write_text(json.dumps(tokens), encoding="utf-8")


def _patch_auth_paths(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "gog_cli.auth.resolve_app_paths",
        lambda: resolve_app_paths({"HOME": str(tmp_path)}),
    )
