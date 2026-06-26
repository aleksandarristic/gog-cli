"""Application state paths and JSON file helpers."""

from __future__ import annotations

import json
import os
from contextlib import suppress
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Literal

APP_DIR_NAME = "gog-dl"

CacheStatus = Literal["fresh", "stale"]


class StateError(Exception):
    """Base class for application state errors."""


class StateFileMissingError(StateError):
    """Raised when an expected state/cache file does not exist."""


class StateFileCorruptError(StateError):
    """Raised when a JSON state/cache file cannot be decoded."""


class StateFileInvalidError(StateError):
    """Raised when a state/cache file has an unsupported shape."""


@dataclass(frozen=True)
class AppRoots:
    """Root directories owned by the application."""

    config: Path
    cache: Path
    state: Path


@dataclass(frozen=True)
class AppPaths:
    """Expected application-owned files and directories."""

    roots: AppRoots
    config_file: Path
    library_cache: Path
    downloads_cache_dir: Path
    session_state: Path
    cookies_file: Path
    schema_file: Path
    locks_dir: Path

    def download_cache(self, product_id: str) -> Path:
        """Return the per-game download-metadata cache path."""
        if not product_id or "/" in product_id or "\x00" in product_id:
            raise ValueError("product_id must be a non-empty path segment")
        return self.downloads_cache_dir / f"{product_id}.json"


@dataclass(frozen=True)
class CacheReadResult:
    """Read cache data plus freshness status."""

    data: Mapping[str, Any]
    status: CacheStatus


def resolve_app_roots(env: Mapping[str, str] | None = None) -> AppRoots:
    """Resolve app config/cache/state roots using Linux/XDG conventions."""
    values = os.environ if env is None else env
    home = Path(values.get("HOME") or str(Path.home())).expanduser()
    config_base = _base_dir(values, "XDG_CONFIG_HOME", home / ".config")
    cache_base = _base_dir(values, "XDG_CACHE_HOME", home / ".cache")
    state_base = _base_dir(values, "XDG_DATA_HOME", home / ".local" / "share")
    return AppRoots(
        config=config_base / APP_DIR_NAME,
        cache=cache_base / APP_DIR_NAME,
        state=state_base / APP_DIR_NAME,
    )


def resolve_app_paths(env: Mapping[str, str] | None = None) -> AppPaths:
    """Resolve expected application-owned paths."""
    roots = resolve_app_roots(env)
    return AppPaths(
        roots=roots,
        config_file=roots.config / "config.toml",
        library_cache=roots.cache / "library.json",
        downloads_cache_dir=roots.cache / "downloads",
        session_state=roots.state / "session.json",
        cookies_file=roots.state / "auth" / "cookies.txt",
        schema_file=roots.state / "schema.json",
        locks_dir=roots.state / "locks",
    )


def read_json_file(path: Path) -> Any:
    """Read a JSON file, raising typed errors for missing or corrupt state."""
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError as exc:
        raise StateFileMissingError(f"state file is missing: {path}") from exc
    except json.JSONDecodeError as exc:
        raise StateFileCorruptError(f"state file is corrupt JSON: {path}") from exc


def write_json_file_atomic(path: Path, data: Any) -> None:
    """Write JSON atomically by replacing through a temp file in the same dir."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_name = ""
    try:
        with NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temp_name = handle.name
            json.dump(data, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        if temp_name:
            with suppress(FileNotFoundError):
                os.unlink(temp_name)


def read_cache_file(
    path: Path,
    *,
    max_age: timedelta | None = None,
    now: datetime | None = None,
) -> CacheReadResult:
    """Read a JSON cache file and classify it as fresh or stale."""
    data = read_json_file(path)
    if not isinstance(data, Mapping):
        raise StateFileInvalidError(f"cache file must contain a JSON object: {path}")
    return CacheReadResult(
        data=data,
        status=_cache_status(data, max_age=max_age, now=now),
    )


def utc_timestamp() -> str:
    """Return a UTC timestamp suitable for cache metadata."""
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _base_dir(env: Mapping[str, str], key: str, fallback: Path) -> Path:
    value = env.get(key)
    if not value:
        return fallback.expanduser()
    return Path(value).expanduser()


def _cache_status(
    data: Mapping[str, Any],
    *,
    max_age: timedelta | None,
    now: datetime | None,
) -> CacheStatus:
    if max_age is None:
        return "fresh"
    updated_at = data.get("updated_at")
    if not isinstance(updated_at, str):
        return "stale"
    updated = _parse_timestamp(updated_at)
    if updated is None:
        return "stale"
    reference = now or datetime.now(UTC)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=UTC)
    return "stale" if reference - updated > max_age else "fresh"


def _parse_timestamp(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)

