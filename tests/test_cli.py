from __future__ import annotations

import json
from pathlib import Path

import pytest
import responses as rsps_lib

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


def test_backup_dry_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _seed_backup_state(tmp_path, monkeypatch)

    assert main(["backup", "--destination", str(tmp_path / "backups"), "--dry-run", "--all"]) == 0
    assert "Plan:" in capsys.readouterr().out


def test_backup_dry_run_no_destination(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["backup", "--dry-run"]) == 2
    assert "destination is required" in capsys.readouterr().err


def test_backup_missing_cache(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    assert main(["backup", "--destination", str(tmp_path), "--all", "--yes"]) == 1
    assert "gog refresh" in capsys.readouterr().err


def test_backup_selector_flags_parse(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _seed_backup_state(tmp_path, monkeypatch)

    assert (
        main(
            [
                "backup",
                "--destination",
                str(tmp_path / "backups"),
                "--dry-run",
                "--game",
                "cyberpunk_2077",
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


def test_backup_selected_game_does_not_require_unselected_download_cache(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_home(monkeypatch, tmp_path)
    _seed_library_cache(
        tmp_path,
        [
            {"product_id": 1111, "title": "Witcher 3", "slug": "witcher_3", "platforms": []},
            {
                "product_id": 2222,
                "title": "Cyberpunk 2077",
                "slug": "cyberpunk_2077",
                "platforms": [],
            },
        ],
    )
    _seed_download_cache(tmp_path, 1111, [_download_entry("setup_witcher", product_id=1111)])

    assert (
        main(
            [
                "backup",
                "--destination",
                str(tmp_path / "backups"),
                "--dry-run",
                "--game",
                "witcher_3",
            ]
        )
        == 0
    )


def test_backup_all_flag_parses(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_backup_state(tmp_path, monkeypatch)

    assert main(["backup", "--destination", str(tmp_path / "backups"), "--dry-run", "--all"]) == 0


def test_sync_dry_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    destination = tmp_path / "backups"
    _seed_backup_state(tmp_path, monkeypatch)
    _seed_manifest(destination, [_manifest_game(version="1.0")])

    assert main(["sync", "--destination", str(destination), "--dry-run", "--all"]) == 0
    assert "Plan:" in capsys.readouterr().out


def test_sync_missing_manifest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _seed_backup_state(tmp_path, monkeypatch)

    assert main(["sync", "--destination", str(tmp_path / "backups"), "--all", "--yes"]) == 1
    assert "gog backup" in capsys.readouterr().err


def test_sync_selector_flags_parse(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    destination = tmp_path / "backups"
    _seed_backup_state(tmp_path, monkeypatch)
    _seed_manifest(destination, [_manifest_game(version="1.0")])

    assert (
        main(
            [
                "sync",
                "--destination",
                str(destination),
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
    assert main(["backup", "--dry-run", "--no-interactive", "--game", "witcher-3"]) == 2


@rsps_lib.activate
def test_backup_all_yes_downloads_and_writes_manifest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    destination = tmp_path / "backups"
    _seed_backup_state(tmp_path, monkeypatch)
    _seed_session(tmp_path)
    _mock_download("https://api.gog.com/products/1111/downlink/installer/setup_witcher")
    _mock_download("https://api.gog.com/products/2222/downlink/installer/setup_cyberpunk")

    assert main(["backup", "--destination", str(destination), "--all", "--yes"]) == 0

    backed_up = destination / "games" / "witcher_3" / "installers" / "setup_witcher"
    assert backed_up.read_bytes() == b"data"
    manifest = json.loads(BackupLayout(destination).manifest_file.read_text())
    assert manifest["games"][0]["files"][0]["status"] == "verified"
    assert "https://cdn.gog.com" not in BackupLayout(destination).manifest_file.read_text()


@rsps_lib.activate
def test_sync_all_yes_downloads_only_stale_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    destination = tmp_path / "backups"
    _set_home(monkeypatch, tmp_path)
    _seed_session(tmp_path)
    _seed_library_cache(
        tmp_path,
        [{"product_id": 1111, "title": "Witcher 3", "slug": "witcher_3", "platforms": []}],
    )
    _seed_download_cache(
        tmp_path,
        1111,
        [
            _download_entry("setup_current", version="1.0"),
            _download_entry("setup_stale", version="2.0"),
        ],
    )
    _seed_manifest(
        destination,
        [
            _manifest_game(source_id="setup_current", version="1.0"),
            _manifest_game(source_id="setup_stale", version="1.0"),
        ],
    )
    _mock_download("https://api.gog.com/products/1111/downlink/installer/setup_stale")

    assert main(["sync", "--destination", str(destination), "--all", "--yes"]) == 0

    assert not (destination / "games" / "witcher_3" / "installers" / "setup_current").exists()
    stale_file = destination / "games" / "witcher_3" / "installers" / "setup_stale"
    assert stale_file.read_bytes() == b"data"


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


def _seed_download_cache(home: Path, product_id: int, installers: list[dict]) -> None:
    paths = resolve_app_paths({"HOME": str(home)})
    write_json_file_atomic(
        paths.download_cache(str(product_id)),
        {
            "fetched_at": "2026-06-26T10:00:00Z",
            "product_id": product_id,
            "data": {
                "id": product_id,
                "downloads": {
                    "installers": installers,
                    "patches": [],
                    "language_packs": [],
                    "bonus_content": [],
                },
            },
        },
    )


def _seed_manifest(destination: Path, games: list[dict], *, schema_version: int = 1) -> None:
    layout = BackupLayout(destination)
    write_json_file_atomic(layout.manifest_file, {"schema_version": schema_version, "games": games})


def _set_home(monkeypatch: pytest.MonkeyPatch, home: Path) -> None:
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)


def _seed_backup_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _set_home(monkeypatch, tmp_path)
    _seed_library_cache(
        tmp_path,
        [
            {"product_id": 1111, "title": "Witcher 3", "slug": "witcher_3", "platforms": []},
            {
                "product_id": 2222,
                "title": "Cyberpunk 2077",
                "slug": "cyberpunk_2077",
                "platforms": [],
            },
        ],
    )
    _seed_download_cache(tmp_path, 1111, [_download_entry("setup_witcher", product_id=1111)])
    _seed_download_cache(tmp_path, 2222, [_download_entry("setup_cyberpunk", product_id=2222)])


def _seed_session(home: Path) -> None:
    paths = resolve_app_paths({"HOME": str(home)})
    write_json_file_atomic(
        paths.session_state,
        {
            "access_token": "access",
            "refresh_token": "refresh",
            "expires_at": "2099-01-01T00:00:00+00:00",
        },
    )


def _download_entry(source_id: str, *, product_id: int = 1111, version: str = "1.0") -> dict:
    return {
        "id": f"installer_{source_id}",
        "name": source_id,
        "os": "windows",
        "language": "en",
        "version": version,
        "files": [
            {
                "id": source_id,
                "size": 4,
                "downlink": f"https://api.gog.com/products/{product_id}/downlink/installer/{source_id}",
            }
        ],
    }


def _manifest_game(source_id: str = "setup_witcher", *, version: str = "1.0") -> dict:
    return {
        "product_id": 1111,
        "title": "Witcher 3",
        "slug": "witcher_3",
        "directory": "games/witcher_3",
        "status": "current",
        "files": [
            {
                "file_id": f"installer:windows:en:{source_id}",
                "role": "installer",
                "source_id": source_id,
                "name": source_id,
                "relative_path": f"games/witcher_3/installers/{source_id}",
                "expected_size": 4,
                "expected_md5": None,
                "version": version,
                "platform": "windows",
                "language": "en",
                "status": "verified",
            }
        ],
    }


def _mock_download(downlink_url: str) -> None:
    rsps_lib.add(
        rsps_lib.GET,
        downlink_url,
        json={"downlink": "https://cdn.gog.com/setup.exe?token=secret", "checksum": ""},
    )
    rsps_lib.add(rsps_lib.GET, "https://cdn.gog.com/setup.exe?token=secret", body=b"data")
