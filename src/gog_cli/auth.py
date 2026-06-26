"""Auth commands and FileTokenStore implementation."""

from __future__ import annotations

import argparse
import os
import sys
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlparse

import requests

from gog_cli import log
from gog_cli.errors import AuthError, ExitCode, FilesystemError, UsageError
from gog_cli.state import (
    AppPaths,
    StateFileCorruptError,
    StateFileMissingError,
    read_json_file,
    resolve_app_paths,
    write_json_file_atomic,
)

_log = log.get_logger(__name__)

_CLIENT_ID = "46899977096215655"
_CLIENT_SECRET = "9d85c43b1482497dbbce61f6e4aa173a433796eeae2ca8c5f6129f2dc4de46d9"  # noqa: S105 - Public GOG Galaxy OAuth client credential.
_REDIRECT_URI = "https://embed.gog.com/on_login_success?origin=client"
_TOKEN_URL = "https://auth.gog.com/token"  # noqa: S105 - URL constant, not a secret.
_USER_DATA_URL = "https://embed.gog.com/userData.json"
_LOGIN_URL = (
    "https://auth.gog.com/auth"
    "?client_id=46899977096215655"
    "&redirect_uri=https%3A%2F%2Fembed.gog.com%2Fon_login_success%3Forigin%3Dclient"
    "&response_type=code"
    "&layout=client2"
)


class FileTokenStore:
    """Implements TokenStore Protocol using session.json + optional OS keyring."""

    def __init__(self, paths: AppPaths) -> None:
        self._paths = paths
        self._keyring_checked = False
        self._keyring_refresh_token: str | None = None

    def load_tokens(self) -> dict:
        try:
            tokens = read_json_file(self._paths.session_state)
        except StateFileMissingError:
            raise AuthError("Not logged in. Run: gog auth login") from None
        except StateFileCorruptError as exc:
            raise AuthError(f"Session file is corrupt: {exc}") from exc
        if not self._keyring_checked:
            self._keyring_refresh_token = _try_load_keyring()
            self._keyring_checked = True
        if self._keyring_refresh_token:
            tokens["refresh_token"] = self._keyring_refresh_token
        return tokens

    def save_tokens(self, tokens: dict) -> None:
        try:
            write_json_file_atomic(self._paths.session_state, tokens)
            os.chmod(self._paths.session_state, 0o600)
        except OSError as exc:
            raise FilesystemError(f"Failed to write session: {exc}") from exc
        self._keyring_checked = True
        self._keyring_refresh_token = tokens.get("refresh_token") or None
        _try_save_keyring(tokens.get("refresh_token", ""))


def _try_save_keyring(refresh_token: str) -> None:
    try:
        import keyring  # noqa: PLC0415
        keyring.set_password("gog-cli", "refresh_token", refresh_token)
    except Exception:  # noqa: BLE001
        _log.warning("keyring write failed — using file-only token storage")


def _try_load_keyring() -> str | None:
    try:
        import keyring  # noqa: PLC0415

        return keyring.get_password("gog-cli", "refresh_token")
    except Exception:  # noqa: BLE001
        _log.warning("keyring read failed — using file token storage")
        return None


def _try_delete_keyring() -> None:
    try:
        import keyring  # noqa: PLC0415
        keyring.delete_password("gog-cli", "refresh_token")
    except Exception:  # noqa: BLE001
        _log.debug("keyring delete failed or token was already absent")


def _extract_code(pasted: str) -> str:
    """Return code= value from a redirect URL, or the raw string if no URL scheme."""
    pasted = pasted.strip()
    if not pasted:
        raise UsageError("No input provided")
    if pasted.startswith("http"):
        params = parse_qs(urlparse(pasted).query)
        codes = params.get("code")
        if not codes:
            raise UsageError("No 'code' parameter found in the pasted URL")
        return codes[0]
    return pasted


def _exchange_code(code: str) -> dict:
    try:
        resp = requests.get(
            _TOKEN_URL,
            params={
                "client_id": _CLIENT_ID,
                "client_secret": _CLIENT_SECRET,
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": _REDIRECT_URI,
            },
            timeout=30,
        )
        resp.raise_for_status()
    except requests.HTTPError as exc:
        raise AuthError(f"Token exchange failed: {exc}") from exc
    except (requests.ConnectionError, requests.Timeout) as exc:
        raise AuthError(f"Token exchange network error: {exc}") from exc
    return resp.json()


def _fetch_username(access_token: str) -> str:
    try:
        resp = requests.get(
            _USER_DATA_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=30,
        )
        resp.raise_for_status()
    except (requests.HTTPError, requests.ConnectionError, requests.Timeout) as exc:
        raise AuthError(f"Failed to fetch user info: {exc}") from exc
    return resp.json().get("username", "")


def handle_auth_login(_args: argparse.Namespace) -> int:
    paths = resolve_app_paths()
    print(f"\nOpen this URL in your browser and log in:\n\n  {_LOGIN_URL}\n")
    print("After logging in, paste the full redirect URL (or just the code value):")
    print("> ", end="", flush=True)
    try:
        pasted = sys.stdin.readline()
    except (EOFError, KeyboardInterrupt) as exc:
        raise UsageError("Login cancelled") from exc

    code = _extract_code(pasted)
    token_data = _exchange_code(code)

    access_token = token_data["access_token"]
    refresh_token = token_data["refresh_token"]
    expires_in = int(token_data.get("expires_in", 3600))
    user_id = str(token_data.get("user_id", ""))

    expires_at = datetime.fromtimestamp(
        datetime.now(tz=UTC).timestamp() + expires_in,
        tz=UTC,
    ).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    username = _fetch_username(access_token)

    store = FileTokenStore(paths)
    store.save_tokens(
        {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_at": expires_at,
            "user_id": user_id,
            "username": username,
        }
    )

    print(f"Logged in as {username}.")
    return ExitCode.SUCCESS


def handle_auth_status(_args: argparse.Namespace) -> int:
    paths = resolve_app_paths()
    store = FileTokenStore(paths)
    try:
        tokens = store.load_tokens()
    except AuthError as exc:
        print(str(exc), file=sys.stderr)
        return ExitCode.AUTH

    expires_at_str = tokens.get("expires_at", "")
    try:
        expires_at = datetime.fromisoformat(expires_at_str.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        expires_at = None

    if expires_at is not None and datetime.now(tz=UTC) > expires_at:
        print("Token expired. Run: gog auth login", file=sys.stderr)
        return ExitCode.AUTH

    username = tokens.get("username", "unknown")
    print(f"Logged in as {username}. Token expires {expires_at_str}.")
    return ExitCode.SUCCESS


def handle_auth_logout(_args: argparse.Namespace) -> int:
    paths = resolve_app_paths()
    try:
        paths.session_state.unlink(missing_ok=True)
    except OSError as exc:
        raise FilesystemError(f"Failed to remove session: {exc}") from exc
    _try_delete_keyring()
    print("Logged out.")
    return ExitCode.SUCCESS
