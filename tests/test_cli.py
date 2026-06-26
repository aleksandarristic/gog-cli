from __future__ import annotations

import json
from pathlib import Path

import pytest

from gog_cli.cli import main
from gog_cli.layout import BackupLayout
from gog_cli.state import resolve_app_paths, write_json_file_atomic


def test_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["--version"])

    assert exc_info.value.code == 0
    assert "gog 0.1.0" in capsys.readouterr().out


def test_list_purchased_human(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _set_home(monkeypatch, tmp_path)
    _seed_library_cache(
        tmp_path,
        [
            {
                "product_id": 1111,
                "title": "Witcher 3",
                "slug": "witcher_3",
                "platforms": ["windows", "linux"],
            },
            {
                "product_id": 2222,
                "title": "Cyberpunk 2077",
                "slug": "cyberpunk_2077",
                "platforms": ["windows"],
            },
        ],
        fetched_at="2026-06-26T10:00:00Z",
    )

    assert main(["list", "purchased"]) == 0
    out = capsys.readouterr()
    assert "Witcher 3" in out.out
    assert "Cyberpunk 2077" in out.out
    assert "2 games. Cache age:" in out.out
    assert out.err == ""


def test_list_purchased_format_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _set_home(monkeypatch, tmp_path)
    _seed_library_cache(
        tmp_path,
        [
            {"product_id": 1111, "title": "Witcher 3", "slug": "witcher_3", "platforms": []},
        ],
    )

    assert main(["list", "purchased", "--format", "json"]) == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["command"] == "list purchased"
    assert parsed["data"][0]["product_id"] == 1111


def test_list_backed_up_requires_destination() -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["list", "backed-up"])
    assert exc_info.value.code == 2


def test_list_backed_up_human(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    destination = tmp_path / "backups"
    _seed_manifest(
        destination,
        [
            {
                "product_id": 1111,
                "title": "Witcher 3",
                "directory": "witcher_3",
                "status": "current",
                "files": [
                    {"status": "verified"},
                    {"status": "verified"},
                ],
            },
            {
                "product_id": 2222,
                "title": "Cyberpunk 2077",
                "directory": "cyberpunk_2077",
                "status": "partial",
                "files": [
                    {"status": "verified"},
                    {"status": "partial"},
                ],
            },
        ],
    )

    assert main(["list", "backed-up", "--destination", str(destination)]) == 0
    out = capsys.readouterr()
    assert "Witcher 3" in out.out
    assert "Cyberpunk 2077" in out.out
    assert "current" in out.out
    assert "partial" in out.out


def test_list_backed_up_format_json(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    destination = tmp_path / "backups"
    _seed_manifest(
        destination,
        [
            {
                "product_id": 1111,
                "title": "Witcher 3",
                "directory": "witcher_3",
                "status": "current",
                "files": [{"status": "verified"}],
            }
        ],
    )

    assert main(["list", "backed-up", "--destination", str(destination), "--format", "json"]) == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["command"] == "list backed-up"
    assert parsed["data"][0]["status"] == "current"


def test_list_backed_up_missing_manifest(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    destination = tmp_path / "backups"

    assert main(["list", "backed-up", "--destination", str(destination)]) == 1
    assert "Run `gog backup`" in capsys.readouterr().err


def test_list_backed_up_unsupported_schema(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    destination = tmp_path / "backups"
    _seed_manifest(destination, [], schema_version=2)

    assert main(["list", "backed-up", "--destination", str(destination)]) == 7
    assert "unsupported manifest schema" in capsys.readouterr().err


def test_backup_dry_run(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["backup", "--destination", "/tmp/gog-backups", "--dry-run"]) == 0
    assert "Dry run" in capsys.readouterr().out


def test_backup_dry_run_no_destination(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["backup", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "Dry run" in out
    assert "<configured destination>" in out


def test_backup_not_implemented(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["backup", "--destination", "/tmp/gog-backups"]) == 1
    assert "not implemented" in capsys.readouterr().err


def test_backup_selector_flags_parse(capsys: pytest.CaptureFixture[str]) -> None:
    assert (
        main(
            [
                "backup",
                "--destination",
                "/tmp/gog-backups",
                "--dry-run",
                "--game",
                "cyberpunk-2077",
                "--exclude",
                "witcher-3",
                "--platform",
                "linux",
                "--language",
                "en",
                "--yes",
            ]
        )
        == 0
    )


def test_backup_all_flag_parses(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["backup", "--destination", "/tmp/gog-backups", "--dry-run", "--all"]) == 0


def test_sync_dry_run(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["sync", "--destination", "/tmp/gog-backups", "--dry-run"]) == 0
    assert "Dry run" in capsys.readouterr().out


def test_sync_not_implemented(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["sync", "--destination", "/tmp/gog-backups"]) == 1
    assert "not implemented" in capsys.readouterr().err


def test_sync_selector_flags_parse(capsys: pytest.CaptureFixture[str]) -> None:
    assert (
        main(
            [
                "sync",
                "--destination",
                "/tmp/gog-backups",
                "--dry-run",
                "--all",
                "--yes",
                "--downloader",
                "aria2c",
            ]
        )
        == 0
    )


def test_no_interactive_flag_parses(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["backup", "--dry-run", "--no-interactive", "--game", "witcher-3"]) == 0


def test_list_purchased_missing_cache(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _set_home(monkeypatch, tmp_path)

    assert main(["list", "purchased"]) == 1
    assert "Run `gog refresh`" in capsys.readouterr().err


def test_list_purchased_stale_cache_warns(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _set_home(monkeypatch, tmp_path)
    _seed_library_cache(
        tmp_path,
        [{"product_id": 1111, "title": "Witcher 3", "slug": "witcher_3", "platforms": []}],
        fetched_at="2026-06-20T10:00:00Z",
    )

    assert main(["list", "purchased"]) == 0
    assert "older than 24h" in capsys.readouterr().err


def _seed_library_cache(
    home: Path,
    games: list[dict],
    *,
    fetched_at: str = "2026-06-26T10:00:00Z",
) -> None:
    paths = resolve_app_paths({"HOME": str(home)})
    write_json_file_atomic(paths.library_cache, {"fetched_at": fetched_at, "games": games})


def _seed_manifest(destination: Path, games: list[dict], *, schema_version: int = 1) -> None:
    layout = BackupLayout(destination)
    write_json_file_atomic(layout.manifest_file, {"schema_version": schema_version, "games": games})


def _set_home(monkeypatch: pytest.MonkeyPatch, home: Path) -> None:
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
