from __future__ import annotations

import json
from pathlib import Path

import pytest
import responses as rsps_lib

from gog_cli.cli import main
from gog_cli.errors import ExitCode
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
    out = capsys.readouterr().out
    # W and L columns should show sizes (8 B total from two 4-byte installers)
    assert "8 B" in out   # Total = windows 4 B + linux 4 B


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


def test_list_purchased_shows_size_columns(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _set_home(monkeypatch, tmp_path)
    _seed_library_cache(
        tmp_path,
        [
            {"product_id": 1111, "title": "Witcher 3", "slug": "witcher_3", "platforms": []},
            {"product_id": 2222, "title": "Linux Only", "slug": "linux_only", "platforms": []},
        ],
    )
    _seed_download_cache_with_bonus(
        tmp_path,
        1111,
        installers=[
            _sized_installer("setup_win", product_id=1111, os_name="windows", size=1073741824),
            _sized_installer("setup_mac", product_id=1111, os_name="osx", size=536870912),
        ],
        bonus_content=[_bonus_entry("art_book", size=1048576)],
    )
    _seed_download_cache_with_bonus(
        tmp_path,
        2222,
        installers=[_sized_installer("setup_lin", product_id=2222, os_name="linux", size=1073741824)],
    )

    assert main(["list", "purchased"]) == 0
    out = capsys.readouterr().out
    assert "W" in out
    assert "M" in out
    assert "L" in out
    assert "Extras" in out
    assert "Total" in out
    assert "Platforms" not in out
    assert "1.0 GB" in out
    assert "512.0 MB" in out
    assert "1.0 MB" in out


def test_list_purchased_shows_dash_for_missing_sizes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _set_home(monkeypatch, tmp_path)
    _seed_library_cache(
        tmp_path,
        [{"product_id": 1111, "title": "Witcher 3", "slug": "witcher_3", "platforms": []}],
    )

    assert main(["list", "purchased"]) == 0
    out = capsys.readouterr().out
    assert "W" in out
    assert out.count("-") >= 4


def test_list_purchased_size_fields_in_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _set_home(monkeypatch, tmp_path)
    _seed_library_cache(
        tmp_path,
        [{"product_id": 1111, "title": "Witcher 3", "slug": "witcher_3", "platforms": []}],
    )
    _seed_download_cache_with_bonus(
        tmp_path,
        1111,
        installers=[_sized_installer("setup_win", product_id=1111, os_name="windows", size=1073741824)],
        bonus_content=[_bonus_entry("art_book", size=1048576)],
    )

    assert main(["list", "purchased", "--format", "json"]) == 0
    parsed = json.loads(capsys.readouterr().out)
    game = parsed["data"][0]
    assert game["installer_sizes"] == {"windows": 1073741824}
    assert game["extras_size"] == 1048576


def test_list_purchased_sort_title(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _set_home(monkeypatch, tmp_path)
    _seed_library_cache(
        tmp_path,
        [
            {"product_id": 1111, "title": "Zelda", "slug": "zelda"},
            {"product_id": 2222, "title": "Arcanum", "slug": "arcanum"},
            {"product_id": 3333, "title": "Morrowind", "slug": "morrowind"},
        ],
    )

    assert main(["list", "purchased", "--sort", "title"]) == 0
    out = capsys.readouterr().out
    assert out.index("Arcanum") < out.index("Morrowind") < out.index("Zelda")


def test_list_purchased_sort_year(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _set_home(monkeypatch, tmp_path)
    _seed_library_cache(
        tmp_path,
        [
            {"product_id": 1111, "title": "New Game", "slug": "new_game", "release_year": 2020},
            {"product_id": 2222, "title": "Old Game", "slug": "old_game", "release_year": 1998},
            {"product_id": 3333, "title": "No Year", "slug": "no_year"},
        ],
    )

    assert main(["list", "purchased", "--sort", "year"]) == 0
    out = capsys.readouterr().out
    assert out.index("Old Game") < out.index("New Game") < out.index("No Year")


def test_list_purchased_sort_size(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _set_home(monkeypatch, tmp_path)
    _seed_library_cache(
        tmp_path,
        [
            {"product_id": 1111, "title": "Small Game", "slug": "small"},
            {"product_id": 2222, "title": "Big Game", "slug": "big"},
        ],
    )
    _seed_download_cache_with_bonus(tmp_path, 1111, installers=[
        _sized_installer("s1", product_id=1111, os_name="windows", size=1073741824),
    ])
    _seed_download_cache_with_bonus(tmp_path, 2222, installers=[
        _sized_installer("b1", product_id=2222, os_name="windows", size=10737418240),
    ])

    assert main(["list", "purchased", "--sort", "size"]) == 0
    out = capsys.readouterr().out
    assert out.index("Big Game") < out.index("Small Game")


def test_list_backed_up_sort_title(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    destination = tmp_path / "backups"
    _seed_manifest(
        destination,
        [
            {"product_id": 1111, "title": "Zelda", "directory": "zelda", "status": "current", "files": []},
            {"product_id": 2222, "title": "Arcanum", "directory": "arcanum", "status": "current", "files": []},
        ],
    )

    assert main(["list", "backup", "--destination", str(destination), "--sort", "title"]) == 0
    out = capsys.readouterr().out
    assert out.index("Arcanum") < out.index("Zelda")


def test_list_backed_up_sort_size(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    destination = tmp_path / "backups"
    _seed_manifest(
        destination,
        [
            {
                "product_id": 1111,
                "title": "Small Game",
                "directory": "small",
                "status": "current",
                "files": [{"status": "verified", "expected_size": 1073741824}],
            },
            {
                "product_id": 2222,
                "title": "Big Game",
                "directory": "big",
                "status": "current",
                "files": [{"status": "verified", "expected_size": 10737418240}],
            },
        ],
    )

    assert main(["list", "backup", "--destination", str(destination), "--sort", "size"]) == 0
    out = capsys.readouterr().out
    assert out.index("Big Game") < out.index("Small Game")


def test_list_backed_up_requires_destination(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _set_home(monkeypatch, tmp_path)

    assert main(["list", "backup"]) == ExitCode.USAGE
    assert "destination is required" in capsys.readouterr().err


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

    assert main(["list", "backup", "--destination", str(destination)]) == 0
    out = capsys.readouterr()
    assert "Witcher 3" in out.out
    assert "Cyberpunk 2077" in out.out
    assert "current" in out.out
    assert "partial" in out.out
    assert "Size" in out.out


def test_list_backed_up_shows_total_size(
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
                    {"status": "verified", "expected_size": 536870912},
                    {"status": "verified", "expected_size": 536870912},
                ],
            },
            {
                "product_id": 2222,
                "title": "No Size Game",
                "directory": "no_size",
                "status": "current",
                "files": [{"status": "verified"}],
            },
        ],
    )

    assert main(["list", "backup", "--destination", str(destination)]) == 0
    out = capsys.readouterr().out
    assert "1.0 GB" in out
    assert "-" in out


def test_list_backed_up_size_in_json(
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
                "files": [{"status": "verified", "expected_size": 1073741824}],
            }
        ],
    )

    assert main(["list", "backup", "--destination", str(destination), "--format", "json"]) == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["data"][0]["total_size_bytes"] == 1073741824


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

    assert main(["list", "backup", "--destination", str(destination), "--format", "json"]) == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["command"] == "list backup"
    assert parsed["data"][0]["status"] == "current"


def test_list_backed_up_missing_manifest(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    destination = tmp_path / "backups"

    assert main(["list", "backup", "--destination", str(destination)]) == 1
    assert "Run `gog backup`" in capsys.readouterr().err


def test_list_backed_up_unsupported_schema(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    destination = tmp_path / "backups"
    _seed_manifest(destination, [], schema_version=2)

    assert main(["list", "backup", "--destination", str(destination)]) == 7
    assert "unsupported manifest schema" in capsys.readouterr().err


def test_backup_dry_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _seed_backup_state(tmp_path, monkeypatch)

    assert main(["backup", "--destination", str(tmp_path / "backups"), "--dry-run", "--all"]) == 0
    assert "Backup plan" in capsys.readouterr().out


def test_backup_dry_run_no_destination(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _set_home(monkeypatch, tmp_path)

    assert main(["backup", "--dry-run"]) == 2
    assert "destination is required" in capsys.readouterr().err


def test_backup_missing_cache(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_home(monkeypatch, tmp_path)

    assert main(["backup", "--destination", str(tmp_path), "--all", "--yes"]) == ExitCode.CACHE
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
        == ExitCode.USAGE
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


def test_backup_without_yes_is_implicit_dry_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _seed_backup_state(tmp_path, monkeypatch)

    assert main(["backup", "--destination", str(tmp_path / "backups"), "--all"]) == 0
    out = capsys.readouterr().out
    assert "Backup plan" in out
    assert "Dry run" in out
    assert not (tmp_path / "backups" / "games").exists()


def test_sync_without_yes_is_implicit_dry_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    destination = tmp_path / "backups"
    _seed_backup_state(tmp_path, monkeypatch)
    _seed_manifest(destination, [_manifest_game(version="1.0")])

    assert main(["sync", "--destination", str(destination), "--all"]) == 0
    out = capsys.readouterr().out
    assert "Plan:" in out
    assert "Dry run" in out


def test_sync_missing_manifest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _seed_backup_state(tmp_path, monkeypatch)

    assert (
        main(["sync", "--destination", str(tmp_path / "backups"), "--all", "--yes"])
        == ExitCode.FILESYSTEM
    )
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


def test_backup_auth_failure_returns_auth_exit_code(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    destination = tmp_path / "backups"
    _seed_backup_state(tmp_path, monkeypatch)

    assert (
        main(["backup", "--destination", str(destination), "--game", "witcher_3", "--yes"])
        == ExitCode.AUTH
    )
    assert "Authentication failed" in capsys.readouterr().err


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
    assert main(["list", "backup", "--destination", str(destination)]) == 0

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


_CATALOG_SEARCH_URL = "https://catalog.gog.com/v1/catalog"


def _catalog_product(
    product_id: int = 1207658924,
    title: str = "The Witcher: Enhanced Edition",
    slug: str = "the_witcher",
    *,
    release_date: str = "2007.04.26",
    genres: list[str] | None = None,
    operating_systems: list[str] | None = None,
    available: bool = True,
    price_amount: str = "9.99",
    is_free: bool = False,
) -> dict:
    genre_list = [
        {"name": g, "slug": g.lower()} for g in (genres if genres is not None else ["RPG"])
    ]
    final_amount = "0.00" if is_free else price_amount
    return {
        "id": str(product_id),
        "title": title,
        "slug": slug,
        "releaseDate": release_date,
        "genres": genre_list,
        "operatingSystems": operating_systems if operating_systems is not None else ["windows"],
        "productState": "default" if available else "coming-soon",
        "price": {"finalMoney": {"amount": final_amount, "currency": "USD"}},
    }


def _stub_catalog(products: list[dict]) -> None:
    rsps_lib.add(
        rsps_lib.GET,
        _CATALOG_SEARCH_URL,
        json={"products": products, "pages": 1, "productCount": len(products)},
    )


@rsps_lib.activate
def test_search_catalog_human(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _set_home(monkeypatch, tmp_path)
    _stub_catalog([_catalog_product()])

    assert main(["search", "witcher"]) == 0
    out = capsys.readouterr().out
    assert "The Witcher: Enhanced Edition" in out
    assert "1207658924" in out
    assert "2007" in out
    assert "RPG" in out
    assert "windows" in out
    assert "Owned" in out
    assert "1 result(s)" in out


@rsps_lib.activate
def test_search_catalog_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _set_home(monkeypatch, tmp_path)
    _stub_catalog([_catalog_product()])

    assert main(["search", "witcher", "--format", "json"]) == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["command"] == "search"
    game = parsed["data"][0]
    assert game["product_id"] == 1207658924
    assert game["title"] == "The Witcher: Enhanced Edition"
    assert game["release_year"] == 2007
    assert "windows" in game["platforms"]
    assert "RPG" in game["genres"]
    assert "price" in game
    assert "is_available" in game


@rsps_lib.activate
def test_search_catalog_owned_annotation_when_library_cache_exists(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _set_home(monkeypatch, tmp_path)
    _seed_library_cache(
        tmp_path,
        [
            {
                "product_id": 1207658924,
                "title": "The Witcher",
                "slug": "the_witcher",
                "platforms": [],
            },
        ],
    )
    _stub_catalog([
        _catalog_product(1207658924, "The Witcher: Enhanced Edition"),
        _catalog_product(9999999, "Some Other Game", "some_other_game"),
    ])

    assert main(["search", "witcher", "--format", "json"]) == 0
    parsed = json.loads(capsys.readouterr().out)
    data = {g["product_id"]: g for g in parsed["data"]}
    assert data[1207658924]["owned"] is True
    assert data[9999999]["owned"] is False


@rsps_lib.activate
def test_search_catalog_owned_is_null_when_no_library_cache(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _set_home(monkeypatch, tmp_path)
    _stub_catalog([_catalog_product()])

    assert main(["search", "witcher", "--format", "json"]) == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["data"][0]["owned"] is None


@rsps_lib.activate
def test_search_catalog_human_shows_ownership_column(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _set_home(monkeypatch, tmp_path)
    _seed_library_cache(
        tmp_path,
        [
            {
                "product_id": 1207658924,
                "title": "The Witcher",
                "slug": "the_witcher",
                "platforms": [],
            },
        ],
    )
    _stub_catalog([
        _catalog_product(1207658924, "The Witcher: Enhanced Edition"),
        _catalog_product(9999999, "Some Other Game", "some_other_game"),
    ])

    assert main(["search", "witcher"]) == 0
    out = capsys.readouterr().out
    assert "yes" in out
    assert "no" in out


@rsps_lib.activate
def test_search_catalog_empty_results(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _set_home(monkeypatch, tmp_path)
    rsps_lib.add(
        rsps_lib.GET,
        _CATALOG_SEARCH_URL,
        json={"products": [], "pages": 0, "productCount": 0},
    )

    assert main(["search", "xyznonexistent"]) == 0
    out = capsys.readouterr().out
    assert "No results" in out


@rsps_lib.activate
def test_search_catalog_network_error_returns_exit_code_4(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _set_home(monkeypatch, tmp_path)
    rsps_lib.add(rsps_lib.GET, _CATALOG_SEARCH_URL, body=ConnectionError("no route"))

    assert main(["search", "witcher"]) == 4
    assert capsys.readouterr().err != ""


@rsps_lib.activate
def test_search_catalog_http_error_returns_exit_code_4(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _set_home(monkeypatch, tmp_path)
    rsps_lib.add(rsps_lib.GET, _CATALOG_SEARCH_URL, status=503)

    assert main(["search", "witcher"]) == 4


@rsps_lib.activate
def test_search_catalog_platform_filter(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _set_home(monkeypatch, tmp_path)
    _stub_catalog([
        _catalog_product(1, "Windows Game", operating_systems=["windows"]),
        _catalog_product(2, "Linux Game", "linux_game", operating_systems=["linux"]),
    ])

    assert main(["search", "game", "--platform", "linux", "--format", "json"]) == 0
    parsed = json.loads(capsys.readouterr().out)
    assert len(parsed["data"]) == 1
    assert parsed["data"][0]["product_id"] == 2


@rsps_lib.activate
def test_search_catalog_year_filter(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _set_home(monkeypatch, tmp_path)
    _stub_catalog([
        _catalog_product(1, "Old Game", release_date="1995.06.15"),
        _catalog_product(2, "New Game", "new_game", release_date="2020.01.01"),
    ])

    assert main(["search", "game", "--year", "2000..", "--format", "json"]) == 0
    parsed = json.loads(capsys.readouterr().out)
    assert len(parsed["data"]) == 1
    assert parsed["data"][0]["product_id"] == 2


@rsps_lib.activate
def test_search_catalog_genre_filter(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _set_home(monkeypatch, tmp_path)
    _stub_catalog([
        _catalog_product(1, "RPG Game", genres=["RPG"]),
        _catalog_product(2, "Strategy Game", "strategy_game", genres=["Strategy"]),
    ])

    assert main(["search", "game", "--genre", "strategy", "--format", "json"]) == 0
    parsed = json.loads(capsys.readouterr().out)
    assert len(parsed["data"]) == 1
    assert parsed["data"][0]["product_id"] == 2


@rsps_lib.activate
def test_search_catalog_free_game_price(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _set_home(monkeypatch, tmp_path)
    _stub_catalog([_catalog_product(is_free=True, price_amount="0.00")])

    assert main(["search", "witcher", "--format", "json"]) == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["data"][0]["price"] == "free"


def _seed_library_cache(
    home: Path,
    games: list[dict],
    *,
    fetched_at: str = "2099-01-01T00:00:00Z",
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


# --- TASK-0040: disk space check ---


def test_backup_check_free_space_fails_when_insufficient(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import shutil

    _seed_backup_state(tmp_path, monkeypatch)
    destination = tmp_path / "backups"
    destination.mkdir(parents=True, exist_ok=True)

    fake_usage = type("du", (), {"free": 1, "used": 999, "total": 1000})()
    monkeypatch.setattr(shutil, "disk_usage", lambda path: fake_usage)

    result = main(["backup", "--destination", str(destination), "--all", "--check-free-space"])
    assert result == ExitCode.FILESYSTEM
    assert "Insufficient disk space" in capsys.readouterr().err


def test_backup_storage_flag_shows_disk_section(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _seed_backup_state(tmp_path, monkeypatch)
    destination = tmp_path / "backups"
    destination.mkdir(parents=True, exist_ok=True)

    assert main(["backup", "--destination", str(destination), "--all", "--storage"]) == 0
    assert "Disk:" in capsys.readouterr().out


# --- TASK-0041: rich plan output ---


def test_backup_plan_rich_output_sections(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _seed_backup_state(tmp_path, monkeypatch)

    assert (
        main(["backup", "--destination", str(tmp_path / "backups"), "--dry-run", "--all"]) == 0
    )
    out = capsys.readouterr().out
    assert "Backup plan" in out
    assert "Downloads:" in out
    assert "Local state:" in out
    assert "Dry run" in out


def test_backup_plan_summary_flag_omits_per_game_detail(
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
                "--summary",
            ]
        )
        == 0
    )
    out = capsys.readouterr().out
    assert "Backup plan" in out
    assert "witcher_3" not in out


def test_backup_plan_changed_only_omits_complete_games(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _seed_backup_state(tmp_path, monkeypatch)
    destination = tmp_path / "backups"
    # Pre-create witcher_3 file so it shows as complete
    witcher_file = destination / "games" / "witcher_3" / "installers" / "setup_witcher"
    witcher_file.parent.mkdir(parents=True, exist_ok=True)
    witcher_file.write_text("data")

    assert (
        main(
            [
                "backup",
                "--destination",
                str(destination),
                "--dry-run",
                "--game",
                "witcher_3",
                "--changed-only",
            ]
        )
        == 0
    )
    out = capsys.readouterr().out
    assert "witcher_3" not in out


def test_backup_plan_explain_skips_shows_reason(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _set_home(monkeypatch, tmp_path)
    _seed_library_cache(
        tmp_path,
        [{"product_id": 1111, "title": "Witcher 3", "slug": "witcher_3", "platforms": []}],
    )
    en_entry = _download_entry("en_setup", product_id=1111)
    de_entry = {**_download_entry("de_setup", product_id=1111), "language": "de"}
    _seed_download_cache(tmp_path, 1111, [en_entry, de_entry])

    assert (
        main(
            [
                "backup",
                "--destination",
                str(tmp_path / "backups"),
                "--dry-run",
                "--game",
                "witcher_3",
                "--language",
                "en",
                "--explain-skips",
            ]
        )
        == 0
    )
    out = capsys.readouterr().out
    assert "language_not_selected" in out


# --- TASK-0043: JSON plan output ---


def test_backup_dry_run_json_format(
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
                "--format",
                "json",
            ]
        )
        == 0
    )
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["command"] == "backup plan"
    assert parsed["data"]["mode"] == "dry_run"
    assert "summary" in parsed["data"]
    assert "disk" in parsed["data"]
    assert "actions" in parsed["data"]
    assert "skipped" in parsed["data"]
    assert parsed["data"]["summary"]["selected_games"] == 2


# --- TASK-0045: plan subcommand ---


def test_plan_matches_backup_dry_run_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _seed_backup_state(tmp_path, monkeypatch)
    destination = tmp_path / "backups"

    assert main(["backup", "--destination", str(destination), "--dry-run", "--all"]) == 0
    backup_out = capsys.readouterr().out

    assert main(["plan", "--destination", str(destination), "--all"]) == 0
    plan_out = capsys.readouterr().out

    assert plan_out == backup_out


def test_plan_positional_selector(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _set_home(monkeypatch, tmp_path)
    _seed_library_cache(
        tmp_path,
        [
            {
                "product_id": 2222,
                "title": "Cyberpunk 2077",
                "slug": "cyberpunk-2077",
                "platforms": [],
            }
        ],
    )
    _seed_download_cache(tmp_path, 2222, [_download_entry("setup_cyberpunk", product_id=2222)])

    assert main(["plan", "--destination", str(tmp_path / "backups"), "cyberpunk-2077"]) == 0
    out = capsys.readouterr().out
    assert "cyberpunk-2077" in out
    assert "Cyberpunk 2077" in out


def test_plan_summary_flag_omits_per_game_detail(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _seed_backup_state(tmp_path, monkeypatch)

    assert main(["plan", "--destination", str(tmp_path / "backups"), "--all", "--summary"]) == 0
    out = capsys.readouterr().out
    assert "Backup plan" in out
    assert "witcher_3" not in out


def test_plan_json_format(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _seed_backup_state(tmp_path, monkeypatch)

    assert (
        main(["plan", "--destination", str(tmp_path / "backups"), "--all", "--format", "json"])
        == 0
    )
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["command"] == "backup plan"
    assert parsed["data"]["mode"] == "dry_run"
    assert parsed["data"]["summary"]["selected_games"] == 2


def test_plan_check_free_space_fails_when_insufficient(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import shutil

    _seed_backup_state(tmp_path, monkeypatch)
    destination = tmp_path / "backups"
    destination.mkdir(parents=True, exist_ok=True)

    fake_usage = type("du", (), {"free": 1, "used": 999, "total": 1000})()
    monkeypatch.setattr(shutil, "disk_usage", lambda path: fake_usage)

    assert (
        main(["plan", "--destination", str(destination), "--all", "--check-free-space"])
        == ExitCode.FILESYSTEM
    )
    assert "Insufficient disk space" in capsys.readouterr().err


def test_plan_changed_only_omits_complete_games(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _seed_backup_state(tmp_path, monkeypatch)
    destination = tmp_path / "backups"
    witcher_file = destination / "games" / "witcher_3" / "installers" / "setup_witcher"
    witcher_file.parent.mkdir(parents=True, exist_ok=True)
    witcher_file.write_text("data")

    assert main(["plan", "--destination", str(destination), "--all", "--changed-only"]) == 0
    out = capsys.readouterr().out
    assert "witcher_3" not in out
    assert "cyberpunk_2077" in out


def test_plan_help_lists_plan_flags(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["plan", "--help"])

    assert exc_info.value.code == 0
    out = capsys.readouterr().out
    assert "--changed-only" in out
    assert "--check-free-space" in out
    assert "GAME" in out


# --- TASK-0048: rich CLI help ---


def _help_text(argv: list[str], capsys: pytest.CaptureFixture[str]) -> str:
    with pytest.raises(SystemExit) as exc_info:
        main([*argv, "--help"])

    assert exc_info.value.code == 0
    return capsys.readouterr().out


def test_top_level_help_includes_common_workflow_examples(
    capsys: pytest.CaptureFixture[str],
) -> None:
    out = _help_text([], capsys)

    assert "{auth,refresh,list,search,plan,backup,sync}" in out
    assert "gog auth login" in out
    assert "gog plan --destination /backups/gog --all --storage" in out
    assert "gog backup --destination /backups/gog --games-from games.txt" in out


@pytest.mark.parametrize(
    ("argv", "expected"),
    [
        (["auth"], "gog auth status"),
        (["auth", "login"], "gog auth login"),
        (["auth", "status"], "gog auth status"),
        (["auth", "logout"], "gog auth logout"),
        (["refresh"], "gog refresh --force"),
        (["list"], "gog list backup --destination /backups/gog"),
        (["list", "purchased"], "gog list purchased --search witcher"),
        (["list", "backup"], "gog list backup --destination /backups/gog --format json"),
        (["search"], "gog search rpg --genre"),
        (["plan"], "gog plan --destination /backups/gog --games-from games.txt --summary"),
        (["backup"], "gog backup --destination /backups/gog --games-from games.txt"),
        (["sync"], "gog sync --destination /backups/gog --games-from games.txt --yes"),
    ],
)
def test_subcommand_help_includes_examples(
    argv: list[str],
    expected: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    out = _help_text(argv, capsys)

    assert "examples:" in out
    assert expected in out


def test_selector_command_help_mentions_games_from(
    capsys: pytest.CaptureFixture[str],
) -> None:
    for argv in (["plan"], ["backup"], ["sync"]):
        out = _help_text(argv, capsys)
        assert "--games-from PATH" in out
        assert "UTF-8 text file" in out
        assert "line. Repeatable." in out


def test_backup_help_mentions_dry_run_and_aria2c(
    capsys: pytest.CaptureFixture[str],
) -> None:
    out = _help_text(["backup"], capsys)

    assert "Without --yes" in out
    assert "dry-run plan" in out
    assert "--downloader {direct,aria2c}" in out
    assert "--downloader aria2c --yes" in out


def test_plan_help_mentions_non_destructive_planning(
    capsys: pytest.CaptureFixture[str],
) -> None:
    out = _help_text(["plan"], capsys)

    assert "non-destructive backup plan" in out
    assert "does not download files" in out
    assert "gog plan --destination /backups/gog --all --format json" in out


def test_plan_invalid_args_return_usage_exit_code(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _seed_backup_state(tmp_path, monkeypatch)

    result = main(["plan", "--destination", str(tmp_path / "backups"), "--all", "witcher_3"])

    assert result == ExitCode.USAGE
    assert "--all and --game" in capsys.readouterr().err


def test_plan_missing_library_cache_returns_cache_exit_code(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _set_home(monkeypatch, tmp_path)

    assert main(["plan", "--destination", str(tmp_path / "backups"), "--all"]) == ExitCode.CACHE
    assert "gog refresh" in capsys.readouterr().err


def test_plan_missing_download_cache_returns_cache_exit_code(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _set_home(monkeypatch, tmp_path)
    _seed_library_cache(
        tmp_path,
        [{"product_id": 1111, "title": "Witcher 3", "slug": "witcher_3", "platforms": []}],
    )

    assert (
        main(["plan", "--destination", str(tmp_path / "backups"), "--game", "witcher_3"])
        == ExitCode.CACHE
    )
    assert "Download metadata cache is missing" in capsys.readouterr().err


# --- TASK-0047: selector files ---


def test_plan_games_from_file_selects_listed_games(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _seed_backup_state(tmp_path, monkeypatch)
    games_file = tmp_path / "games.txt"
    games_file.write_text(
        """
        # fit this subset first
        witcher_3

        cyberpunk_2077
        """,
        encoding="utf-8",
    )

    assert (
        main(["plan", "--destination", str(tmp_path / "backups"), "--games-from", str(games_file)])
        == 0
    )
    out = capsys.readouterr().out
    assert "Scope: 2 owned | 2 selected" in out
    assert "witcher_3" in out
    assert "cyberpunk_2077" in out


def test_backup_dry_run_games_from_file_selects_listed_games(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _seed_backup_state(tmp_path, monkeypatch)
    games_file = tmp_path / "games.txt"
    games_file.write_text("witcher_3\n", encoding="utf-8")

    assert (
        main(
            [
                "backup",
                "--destination",
                str(tmp_path / "backups"),
                "--dry-run",
                "--games-from",
                str(games_file),
            ]
        )
        == 0
    )
    out = capsys.readouterr().out
    assert "Scope: 2 owned | 1 selected" in out
    assert "witcher_3" in out
    assert "cyberpunk_2077" not in out


def test_games_from_multiple_files_are_combined(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _seed_backup_state(tmp_path, monkeypatch)
    first = tmp_path / "first.txt"
    second = tmp_path / "second.txt"
    first.write_text("witcher_3\n", encoding="utf-8")
    second.write_text("cyberpunk_2077\n", encoding="utf-8")

    assert (
        main(
            [
                "plan",
                "--destination",
                str(tmp_path / "backups"),
                "--games-from",
                str(first),
                "--games-from",
                str(second),
                "--summary",
            ]
        )
        == 0
    )
    assert "Scope: 2 owned | 2 selected" in capsys.readouterr().out


def test_games_from_missing_file_returns_usage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _seed_backup_state(tmp_path, monkeypatch)
    missing = tmp_path / "missing.txt"

    assert (
        main(["plan", "--destination", str(tmp_path / "backups"), "--games-from", str(missing)])
        == ExitCode.USAGE
    )
    assert "Game selector file does not exist" in capsys.readouterr().err


def test_games_from_conflicts_with_all(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _seed_backup_state(tmp_path, monkeypatch)
    games_file = tmp_path / "games.txt"
    games_file.write_text("witcher_3\n", encoding="utf-8")

    assert (
        main(
            [
                "plan",
                "--destination",
                str(tmp_path / "backups"),
                "--all",
                "--games-from",
                str(games_file),
            ]
        )
        == ExitCode.USAGE
    )
    assert "--all and --game" in capsys.readouterr().err


def _sized_installer(
    source_id: str,
    *,
    product_id: int,
    os_name: str,
    size: int,
) -> dict:
    return {
        "id": f"installer_{source_id}",
        "os": os_name,
        "language": "en",
        "version": "1.0",
        "files": [
            {
                "id": source_id,
                "size": size,
                "downlink": f"https://api.gog.com/products/{product_id}/downlink/installer/{source_id}",
            }
        ],
    }


def _bonus_entry(source_id: str, *, size: int) -> dict:
    return {
        "id": f"bonus_{source_id}",
        "files": [
            {
                "id": source_id,
                "size": size,
                "downlink": f"https://api.gog.com/products/1111/downlink/bonus/{source_id}",
            }
        ],
    }


def _seed_download_cache_with_bonus(
    home: Path,
    product_id: int,
    installers: list[dict],
    bonus_content: list[dict] | None = None,
) -> None:
    data = {
        "id": product_id,
        "downloads": {
            "installers": installers,
            "patches": [],
            "language_packs": [],
            "bonus_content": bonus_content or [],
        },
    }
    paths = resolve_app_paths({"HOME": str(home)})
    write_json_file_atomic(
        paths.download_cache(str(product_id)),
        {"fetched_at": "2026-06-26T10:00:00Z", "product_id": product_id, "data": data},
    )


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
