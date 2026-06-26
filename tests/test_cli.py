from __future__ import annotations

import json
from pathlib import Path

import pytest
import responses as rsps_lib

from gog_cli.cli import main
from gog_cli.layout import BackupLayout
from gog_cli.state import resolve_app_paths, write_json_file_atomic

_LIBRARY_URL = "https://embed.gog.com/account/getFilteredProducts"
_PRODUCT_URL_1111 = "https://api.gog.com/products/1111"


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
                "release_year": 2015,
                "genres": ["Role-playing"],
                "is_installable": True,
            },
            {
                "product_id": 2222,
                "title": "Cyberpunk 2077",
                "slug": "cyberpunk_2077",
                "platforms": ["windows"],
                "release_year": 2020,
                "genres": ["RPG"],
                "is_installable": True,
            },
        ],
        fetched_at="2026-06-26T10:00:00Z",
    )

    assert main(["list", "purchased"]) == 0
    out = capsys.readouterr()
    assert "Witcher 3" in out.out
    assert "Cyberpunk 2077" in out.out
    assert "Year" in out.out
    assert "Genre" in out.out
    assert "Install" not in out.out
    assert "2015" in out.out
    assert "Role-playing" in out.out
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
    assert parsed["data"][0]["owned"] is True


def test_list_purchased_enriches_platforms_from_download_cache(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _set_home(monkeypatch, tmp_path)
    _seed_library_cache(
        tmp_path,
        [{"product_id": 1111, "title": "Witcher 3", "slug": "witcher_3", "platforms": []}],
    )
    _seed_download_cache(
        tmp_path,
        1111,
        [
            _download_entry("setup_witcher_windows", product_id=1111),
            {
                **_download_entry("setup_witcher_linux", product_id=1111),
                "os": "linux",
            },
        ],
    )

    assert main(["list", "purchased"]) == 0
    assert "windows, linux" in capsys.readouterr().out


def test_list_purchased_keeps_download_installable_in_json_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _set_home(monkeypatch, tmp_path)
    _seed_library_cache(
        tmp_path,
        [{"product_id": 1111, "title": "Witcher 3", "slug": "witcher_3", "platforms": []}],
    )
    _seed_download_cache(
        tmp_path,
        1111,
        [_download_entry("setup_witcher", product_id=1111)],
        release_date="2015-05-18T00:00:00+0300",
        is_installable=True,
    )

    assert main(["list", "purchased"]) == 0
    out = capsys.readouterr().out
    assert "2015" in out
    assert "Install" not in out

    assert main(["list", "purchased", "--format", "json"]) == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["data"][0]["is_installable"] is True


def test_list_purchased_ignores_implausible_download_year_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _set_home(monkeypatch, tmp_path)
    _seed_library_cache(
        tmp_path,
        [{"product_id": 1111, "title": "Witcher 2", "slug": "witcher_2", "platforms": []}],
    )
    _seed_download_cache(
        tmp_path,
        1111,
        [_download_entry("setup_witcher_2", product_id=1111)],
        release_date="1991-12-25T00:00:00+0200",
    )

    assert main(["list", "purchased"]) == 0
    out = capsys.readouterr().out
    assert "1991" not in out
    assert "Witcher 2" in out


def test_list_purchased_filters_platform_year_and_genre(
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
                "release_year": 2015,
                "genres": ["Role-playing"],
            },
            {
                "product_id": 2222,
                "title": "Cyberpunk 2077",
                "slug": "cyberpunk_2077",
                "platforms": ["windows"],
                "release_year": 2020,
                "genres": ["RPG"],
            },
            {
                "product_id": 3333,
                "title": "FTL",
                "slug": "ftl",
                "platforms": ["linux"],
                "release_year": 2012,
                "genres": ["Strategy"],
            },
        ],
    )

    assert (
        main(
            [
                "list",
                "purchased",
                "--platform",
                "windows",
                "--year",
                "2010..2018",
                "--genre",
                "role-playing",
            ]
        )
        == 0
    )
    out = capsys.readouterr().out
    assert "Witcher 3" in out
    assert "Cyberpunk 2077" not in out
    assert "FTL" not in out
    assert "1 games." in out


def test_list_purchased_year_open_ranges_and_comma_genres(
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
                "title": "Arcade Oldie",
                "slug": "arcade_oldie",
                "platforms": ["windows"],
                "release_year": 1998,
                "genres": ["Arcade"],
            },
            {
                "product_id": 2222,
                "title": "Modern RTS",
                "slug": "modern_rts",
                "platforms": ["windows"],
                "release_year": 2020,
                "genres": ["RTS"],
            },
        ],
    )

    assert main(["list", "purchased", "--year", "..2000", "--genre", "arcade,rts"]) == 0
    out = capsys.readouterr().out
    assert "Arcade Oldie" in out
    assert "Modern RTS" not in out


def test_list_purchased_genre_filter_omits_unknown_genres_by_default(
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
                "title": "Known Strategy",
                "slug": "known_strategy",
                "genres": ["Strategy"],
            },
            {"product_id": 2222, "title": "Unknown Genre", "slug": "unknown_genre"},
        ],
    )

    assert main(["list", "purchased", "--genre", "strategy"]) == 0
    out = capsys.readouterr().out
    assert "Known Strategy" in out
    assert "Unknown Genre" not in out


def test_list_purchased_genre_filter_can_include_unknown_genres(
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
                "title": "Known Strategy",
                "slug": "known_strategy",
                "genres": ["Strategy"],
            },
            {"product_id": 2222, "title": "Unknown Genre", "slug": "unknown_genre"},
        ],
    )

    assert (
        main(
            [
                "list",
                "purchased",
                "--genre",
                "strategy",
                "--include-unknown-genre",
            ]
        )
        == 0
    )
    out = capsys.readouterr().out
    assert "Known Strategy" in out
    assert "Unknown Genre" in out


def test_list_purchased_fuzzy_search_ranks_exact_before_fuzzy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _set_home(monkeypatch, tmp_path)
    _seed_library_cache(
        tmp_path,
        [
            {"product_id": 1111, "title": "The Witcher 3", "slug": "the_witcher_3"},
            {"product_id": 2222, "title": "Witchcraft Academy", "slug": "witchcraft"},
            {"product_id": 3333, "title": "Cyberpunk 2077", "slug": "cyberpunk_2077"},
            {"product_id": 4444, "title": "Butcher", "slug": "butcher"},
        ],
    )

    assert main(["list", "purchased", "--search", "witcher"]) == 0
    lines = capsys.readouterr().out.splitlines()
    game_lines = [line for line in lines if "Witch" in line]
    assert game_lines[0].find("The Witcher 3") > -1
    assert "Cyberpunk 2077" not in "\n".join(lines)
    assert "Butcher" not in "\n".join(lines)


def test_list_purchased_empty_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _set_home(monkeypatch, tmp_path)
    _seed_library_cache(
        tmp_path,
        [{"product_id": 1111, "title": "Witcher 3", "slug": "witcher_3", "platforms": ["windows"]}],
    )

    assert main(["list", "purchased", "--platform", "linux"]) == 0
    assert "0 games." in capsys.readouterr().out


def test_list_purchased_year_filter_omits_unknown_years(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _set_home(monkeypatch, tmp_path)
    _seed_library_cache(
        tmp_path,
        [
            {"product_id": 1111, "title": "Known", "slug": "known", "release_year": 2001},
            {"product_id": 2222, "title": "Unknown", "slug": "unknown"},
        ],
    )

    assert main(["list", "purchased", "--year", "2000..2002"]) == 0
    out = capsys.readouterr().out
    assert "Known" in out
    assert "Unknown" not in out


def test_list_purchased_year_filter_can_include_unknown_years(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _set_home(monkeypatch, tmp_path)
    _seed_library_cache(
        tmp_path,
        [
            {"product_id": 1111, "title": "Known", "slug": "known", "release_year": 2001},
            {"product_id": 2222, "title": "Unknown", "slug": "unknown"},
        ],
    )

    assert (
        main(
            [
                "list",
                "purchased",
                "--year",
                "2000..2002",
                "--include-unknown-year",
            ]
        )
        == 0
    )
    out = capsys.readouterr().out
    assert "Known" in out
    assert "Unknown" in out


def test_list_purchased_invalid_year_range_returns_usage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _set_home(monkeypatch, tmp_path)
    _seed_library_cache(
        tmp_path,
        [{"product_id": 1111, "title": "Witcher 3", "slug": "witcher_3"}],
    )

    assert main(["list", "purchased", "--year", "2020..1990"]) == 2
    assert "Year filter start" in capsys.readouterr().err


def test_list_purchased_help_includes_filter_examples(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["list", "purchased", "--help"])

    assert exc_info.value.code == 0
    out = capsys.readouterr().out
    assert "gog list purchased --search witcher" in out
    assert "--include-unknown-genre" in out


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


def test_backup_missing_cache(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_home(monkeypatch, tmp_path)

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
                "windows",
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


def test_backup_invalid_platform_filter_fails(
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
                "--all",
                "--platform",
                "windwos",
            ]
        )
        == 2
    )
    assert "Unknown platform" in capsys.readouterr().err


def test_backup_malformed_download_metadata_fails_parser(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _set_home(monkeypatch, tmp_path)
    _seed_library_cache(
        tmp_path,
        [{"product_id": 1111, "title": "Witcher 3", "slug": "witcher_3", "platforms": []}],
    )
    paths = resolve_app_paths({"HOME": str(tmp_path)})
    write_json_file_atomic(
        paths.download_cache("1111"),
        {"data": {"downloads": {"installers": [{"id": "broken", "files": []}]}}},
    )

    assert main(["backup", "--destination", str(tmp_path / "backups"), "--dry-run", "--all"]) == 7
    assert "supported file entries" in capsys.readouterr().err


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
    assert manifest["backup_root_marker"].startswith("gog-cli-backup:")
    assert "checksum" in manifest["games"][0]["files"][0]
    assert "https://cdn.gog.com" not in BackupLayout(destination).manifest_file.read_text()


@rsps_lib.activate
def test_backup_uses_metadata_filename(
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
        [_download_entry("setup_witcher", product_id=1111, name="setup_witcher_1.0.exe")],
    )
    _mock_download("https://api.gog.com/products/1111/downlink/installer/setup_witcher")

    assert main(["backup", "--destination", str(destination), "--all", "--yes"]) == 0

    backed_up = destination / "games" / "witcher_3" / "installers" / "setup_witcher_1.0.exe"
    assert backed_up.exists()
    manifest = json.loads(BackupLayout(destination).manifest_file.read_text())
    assert manifest["games"][0]["files"][0]["source_id"] == "setup_witcher"
    assert manifest["games"][0]["files"][0]["name"] == "setup_witcher_1.0.exe"


@rsps_lib.activate
def test_backup_falls_back_to_header_filename(
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
        [_download_entry("setup_witcher", product_id=1111, name=None)],
    )
    _mock_download(
        "https://api.gog.com/products/1111/downlink/installer/setup_witcher",
        header_filename="setup_from_header.exe",
    )

    assert main(["backup", "--destination", str(destination), "--all", "--yes"]) == 0
    assert (destination / "games" / "witcher_3" / "installers" / "setup_from_header.exe").exists()


def test_backup_adopts_existing_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    destination = tmp_path / "backups"
    _seed_backup_state(tmp_path, monkeypatch)
    _seed_session(tmp_path)
    existing = destination / "games" / "witcher_3" / "installers" / "setup_witcher"
    existing.parent.mkdir(parents=True)
    existing.write_bytes(b"data")

    assert main(["backup", "--destination", str(destination), "--game", "witcher_3", "--yes"]) == 0
    manifest = json.loads(BackupLayout(destination).manifest_file.read_text())
    assert manifest["games"][0]["files"][0]["status"] == "verified"


def test_backup_existing_file_size_mismatch_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    destination = tmp_path / "backups"
    _seed_backup_state(tmp_path, monkeypatch)
    _seed_session(tmp_path)
    existing = destination / "games" / "witcher_3" / "installers" / "setup_witcher"
    existing.parent.mkdir(parents=True)
    existing.write_bytes(b"wrong-size")

    assert main(["backup", "--destination", str(destination), "--game", "witcher_3", "--yes"]) == 1
    manifest = json.loads(BackupLayout(destination).manifest_file.read_text())
    assert manifest["games"][0]["files"][0]["failure"]["code"] == "size_mismatch"


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


def test_sync_verifies_unverified_existing_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    destination = tmp_path / "backups"
    _seed_backup_state(tmp_path, monkeypatch)
    _seed_session(tmp_path)
    _seed_manifest(destination, [_manifest_game(status="downloaded")])
    existing = destination / "games" / "witcher_3" / "installers" / "setup_witcher"
    existing.parent.mkdir(parents=True)
    existing.write_bytes(b"data")

    assert main(["sync", "--destination", str(destination), "--game", "witcher_3", "--yes"]) == 0
    manifest = json.loads(BackupLayout(destination).manifest_file.read_text())
    assert manifest["games"][0]["files"][0]["status"] == "verified"


@rsps_lib.activate
def test_full_refresh_backup_list_backed_up_workflow(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    destination = tmp_path / "backups"
    _set_home(monkeypatch, tmp_path)
    _seed_session(tmp_path)
    rsps_lib.add(
        rsps_lib.GET,
        _LIBRARY_URL,
        json={
            "page": 1,
            "totalPages": 1,
            "products": [
                {
                    "id": 1111,
                    "title": "Witcher 3",
                    "slug": "witcher_3",
                    "worksOn": {"Windows": True},
                }
            ],
        },
    )
    rsps_lib.add(
        rsps_lib.GET,
        _PRODUCT_URL_1111,
        json={
            "id": 1111,
            "downloads": {
                "installers": [_download_entry("setup_witcher", product_id=1111)],
                "patches": [],
                "language_packs": [],
                "bonus_content": [],
            },
        },
    )
    _mock_download("https://api.gog.com/products/1111/downlink/installer/setup_witcher")

    assert main(["refresh"]) == 0
    assert main(["backup", "--destination", str(destination), "--all", "--yes"]) == 0
    assert main(["list", "backed-up", "--destination", str(destination)]) == 0

    output = capsys.readouterr().out
    assert "Witcher 3" in output
    manifest_text = BackupLayout(destination).manifest_file.read_text()
    assert "https://cdn.gog.com" not in manifest_text


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


def _seed_download_cache(
    home: Path,
    product_id: int,
    installers: list[dict],
    *,
    release_date: str = "",
    is_installable: bool | None = None,
) -> None:
    data = {
        "id": product_id,
        "downloads": {
            "installers": installers,
            "patches": [],
            "language_packs": [],
            "bonus_content": [],
        },
    }
    if release_date:
        data["release_date"] = release_date
    if is_installable is not None:
        data["is_installable"] = is_installable
    paths = resolve_app_paths({"HOME": str(home)})
    write_json_file_atomic(
        paths.download_cache(str(product_id)),
        {
            "fetched_at": "2026-06-26T10:00:00Z",
            "product_id": product_id,
            "data": data,
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


def _download_entry(
    source_id: str,
    *,
    product_id: int = 1111,
    version: str = "1.0",
    name: str | None = "",
) -> dict:
    entry = {
        "id": f"installer_{source_id}",
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
    if name is not None:
        entry["name"] = name or source_id
    return entry


def _manifest_game(
    source_id: str = "setup_witcher",
    *,
    version: str = "1.0",
    status: str = "verified",
) -> dict:
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
                "status": status,
            }
        ],
    }


def _mock_download(downlink_url: str, *, header_filename: str | None = None) -> None:
    headers = {}
    if header_filename:
        headers["Content-Disposition"] = f'attachment; filename="{header_filename}"'
    rsps_lib.add(
        rsps_lib.GET,
        downlink_url,
        json={"downlink": "https://cdn.gog.com/setup.exe?token=secret", "checksum": ""},
    )
    if header_filename:
        rsps_lib.add(
            rsps_lib.HEAD,
            "https://cdn.gog.com/setup.exe?token=secret",
            headers=headers,
        )
    rsps_lib.add(rsps_lib.GET, "https://cdn.gog.com/setup.exe?token=secret", body=b"data")
