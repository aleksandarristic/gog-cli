from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from gog_dl.state import (
    StateFileCorruptError,
    StateFileInvalidError,
    StateFileMissingError,
    read_cache_file,
    read_json_file,
    resolve_app_paths,
    resolve_app_roots,
    utc_timestamp,
    write_json_file_atomic,
)


def test_resolve_app_roots_defaults_to_home_relative_paths() -> None:
    roots = resolve_app_roots({"HOME": "/home/alice"})

    assert roots.config.as_posix() == "/home/alice/.config/gog-dl"
    assert roots.cache.as_posix() == "/home/alice/.cache/gog-dl"
    assert roots.state.as_posix() == "/home/alice/.local/share/gog-dl"


def test_resolve_app_roots_uses_xdg_base_dir_overrides() -> None:
    roots = resolve_app_roots(
        {
            "HOME": "/home/alice",
            "XDG_CONFIG_HOME": "/tmp/config",
            "XDG_CACHE_HOME": "/tmp/cache",
            "XDG_DATA_HOME": "/tmp/data",
        }
    )

    assert roots.config.as_posix() == "/tmp/config/gog-dl"
    assert roots.cache.as_posix() == "/tmp/cache/gog-dl"
    assert roots.state.as_posix() == "/tmp/data/gog-dl"


def test_resolve_app_paths_names_expected_files() -> None:
    paths = resolve_app_paths({"HOME": "/home/alice"})

    assert paths.config_file.as_posix() == "/home/alice/.config/gog-dl/config.toml"
    assert paths.library_cache.as_posix() == "/home/alice/.cache/gog-dl/library.json"
    assert paths.download_cache("12345").as_posix() == "/home/alice/.cache/gog-dl/downloads/12345.json"
    assert paths.session_state.as_posix() == "/home/alice/.local/share/gog-dl/session.json"
    assert paths.cookies_file.as_posix() == "/home/alice/.local/share/gog-dl/auth/cookies.txt"
    assert paths.schema_file.as_posix() == "/home/alice/.local/share/gog-dl/schema.json"
    assert paths.locks_dir.as_posix() == "/home/alice/.local/share/gog-dl/locks"


def test_download_cache_rejects_invalid_product_id() -> None:
    paths = resolve_app_paths({"HOME": "/home/alice"})

    with pytest.raises(ValueError):
        paths.download_cache("")
    with pytest.raises(ValueError):
        paths.download_cache("../escape")


def test_write_json_file_atomic_creates_parent_and_round_trips(tmp_path) -> None:
    target = tmp_path / "cache" / "library.json"
    write_json_file_atomic(target, {"schema_version": 1, "games": []})

    assert read_json_file(target) == {"schema_version": 1, "games": []}


def test_read_json_file_reports_missing_file(tmp_path) -> None:
    with pytest.raises(StateFileMissingError):
        read_json_file(tmp_path / "missing.json")


def test_read_json_file_reports_corrupt_json(tmp_path) -> None:
    target = tmp_path / "library.json"
    target.write_text("{not json", encoding="utf-8")

    with pytest.raises(StateFileCorruptError):
        read_json_file(target)


def test_read_cache_file_reports_invalid_top_level_shape(tmp_path) -> None:
    target = tmp_path / "library.json"
    write_json_file_atomic(target, [])

    with pytest.raises(StateFileInvalidError):
        read_cache_file(target)


def test_read_cache_file_marks_recent_cache_fresh(tmp_path) -> None:
    target = tmp_path / "library.json"
    now = datetime(2026, 6, 25, 12, 0, tzinfo=UTC)
    write_json_file_atomic(target, {"updated_at": "2026-06-25T11:30:00Z"})

    result = read_cache_file(target, max_age=timedelta(hours=1), now=now)

    assert result.status == "fresh"
    assert result.data["updated_at"] == "2026-06-25T11:30:00Z"


def test_read_cache_file_marks_old_or_unknown_cache_stale(tmp_path) -> None:
    now = datetime(2026, 6, 25, 12, 0, tzinfo=UTC)
    old_cache = tmp_path / "old.json"
    unknown_cache = tmp_path / "unknown.json"
    write_json_file_atomic(old_cache, {"updated_at": "2026-06-25T10:00:00Z"})
    write_json_file_atomic(unknown_cache, {"schema_version": 1})

    assert read_cache_file(old_cache, max_age=timedelta(hours=1), now=now).status == "stale"
    assert read_cache_file(unknown_cache, max_age=timedelta(hours=1), now=now).status == "stale"


def test_utc_timestamp_uses_z_suffix() -> None:
    assert utc_timestamp().endswith("Z")
