"""Tests for gog_cli.refresh."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import responses as rsps_lib

from gog_cli.errors import AuthError, ExitCode
from gog_cli.refresh import _compute_delta, _fetch_library, _normalize_game, handle_refresh
from gog_cli.state import resolve_app_paths

_LIBRARY_URL = "https://embed.gog.com/account/getFilteredProducts"
_PRODUCT_URL_1 = "https://api.gog.com/products/1"
_PRODUCT_URL_2 = "https://api.gog.com/products/2"

_PRODUCT_1 = {
    "id": 1,
    "title": "Alpha Game",
    "slug": "alpha-game",
    "image": "//cdn.gog.com/alpha.jpg",
    "worksOn": {"Windows": True, "Mac": False, "Linux": True},
    "isComingSoon": False,
    "releaseDate": {"date": "2019-05-28 00:00:00.000000", "timezone": "+03:00"},
    "category": "Strategy",
    "tags": [],
    "isGame": True,
    "isMovie": False,
    "isGalaxyCompatible": True,
}
_PRODUCT_2 = {
    "id": 2,
    "title": "Beta Game",
    "slug": "beta-game",
    "image": "//cdn.gog.com/beta.jpg",
    "worksOn": {"Windows": True, "Mac": False, "Linux": False},
    "isComingSoon": False,
}
_DOWNLOADS_1 = {"id": 1, "downloads": {"installers": [{"id": "en1"}]}}
_DOWNLOADS_2 = {"id": 2, "downloads": {"installers": [{"id": "en2"}]}}
_DOWNLOADS_WITH_PLATFORMS = {
    "id": 1,
    "content_system_compatibility": {"windows": True, "osx": True, "linux": False},
    "release_date": "2019-05-28T15:55:00+0300",
    "is_installable": True,
    "game_type": "game",
    "downloads": {
        "installers": [
            {
                "id": "installer_windows_en",
                "os": "windows",
                "files": [{"id": "en1installer0", "downlink": "https://example.test", "size": 1}],
            },
            {
                "id": "installer_linux_en",
                "os": "linux",
                "files": [{"id": "en2installer0", "downlink": "https://example.test", "size": 1}],
            },
        ]
    },
}


# ── _normalize_game ────────────────────────────────────────────────────────────

def test_normalize_game_extracts_platforms() -> None:
    result = _normalize_game(_PRODUCT_1)
    assert result["platforms"] == ["windows", "linux"]


def test_normalize_game_fields() -> None:
    result = _normalize_game(_PRODUCT_1)
    assert result["product_id"] == 1
    assert result["title"] == "Alpha Game"
    assert result["slug"] == "alpha-game"
    assert result["image_url"] == "//cdn.gog.com/alpha.jpg"
    assert result["is_pre_order"] is False
    assert result["release_date"] == "2019-05-28"
    assert result["release_year"] == 2019
    assert result["genres"] == ["Strategy"]
    assert result["is_game"] is True
    assert result["is_movie"] is False
    assert result["is_galaxy_compatible"] is True


def test_normalize_game_no_works_on() -> None:
    result = _normalize_game({"id": 99, "title": "X", "slug": "x"})
    assert result["platforms"] == []


def test_normalize_game_handles_all_false_works_on() -> None:
    result = _normalize_game(
        {
            "id": 99,
            "title": "X",
            "slug": "x",
            "worksOn": {"Windows": False, "Mac": False, "Linux": False},
        }
    )
    assert result["platforms"] == []


def test_normalize_game_is_pre_order() -> None:
    product = {**_PRODUCT_1, "isComingSoon": True}
    assert _normalize_game(product)["is_pre_order"] is True


# ── _fetch_library ─────────────────────────────────────────────────────────────

@rsps_lib.activate
def test_fetch_library_single_page() -> None:
    rsps_lib.add(
        rsps_lib.GET,
        _LIBRARY_URL,
        json={"page": 1, "totalPages": 1, "products": [_PRODUCT_1]},
    )
    client = _make_mock_client_with_responses()
    games = _fetch_library(client)
    assert len(games) == 1
    assert games[0]["title"] == "Alpha Game"


@rsps_lib.activate
def test_fetch_library_multiple_pages() -> None:
    rsps_lib.add(
        rsps_lib.GET,
        _LIBRARY_URL,
        json={"page": 1, "totalPages": 2, "products": [_PRODUCT_1]},
    )
    rsps_lib.add(
        rsps_lib.GET,
        _LIBRARY_URL,
        json={"page": 2, "totalPages": 2, "products": [_PRODUCT_2]},
    )
    client = _make_mock_client_with_responses()
    games = _fetch_library(client)
    assert len(games) == 2
    assert {g["product_id"] for g in games} == {1, 2}


# ── _compute_delta ─────────────────────────────────────────────────────────────

def test_compute_delta_all_new() -> None:
    added, removed, changed = _compute_delta([], [_normalize_game(_PRODUCT_1)])
    assert added == 1
    assert removed == 0
    assert changed == 0


def test_compute_delta_removed() -> None:
    old = [_normalize_game(_PRODUCT_1), _normalize_game(_PRODUCT_2)]
    added, removed, changed = _compute_delta(old, [_normalize_game(_PRODUCT_1)])
    assert added == 0
    assert removed == 1
    assert changed == 0


def test_compute_delta_changed_title() -> None:
    old = [_normalize_game(_PRODUCT_1)]
    new_product = {**_PRODUCT_1, "title": "Alpha Game Renamed"}
    added, removed, changed = _compute_delta(old, [_normalize_game(new_product)])
    assert added == 0
    assert removed == 0
    assert changed == 1


def test_compute_delta_no_change() -> None:
    games = [_normalize_game(_PRODUCT_1)]
    added, removed, changed = _compute_delta(games, games)
    assert added == removed == changed == 0


# ── handle_refresh ─────────────────────────────────────────────────────────────

@rsps_lib.activate
def test_handle_refresh_happy_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _mock_library_and_downloads(tmp_path, monkeypatch)

    args = _make_args()
    result = handle_refresh(args)

    assert result == ExitCode.SUCCESS
    captured = capsys.readouterr()
    assert "2 games" in captured.out
    assert "Fetching library page" in captured.err
    assert "Refreshing download metadata for 2 games" in captured.err

    paths = resolve_app_paths({"HOME": str(tmp_path)})
    library = json.loads(paths.library_cache.read_text())
    assert len(library["games"]) == 2

    dl1 = json.loads(paths.download_cache("1").read_text())
    assert dl1["product_id"] == 1


@rsps_lib.activate
def test_handle_refresh_writes_download_caches(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_library_and_downloads(tmp_path, monkeypatch)

    result = handle_refresh(_make_args())

    assert result == ExitCode.SUCCESS
    paths = resolve_app_paths({"HOME": str(tmp_path)})
    assert paths.download_cache("1").exists()
    assert paths.download_cache("2").exists()


@rsps_lib.activate
def test_handle_refresh_enriches_platforms_from_download_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    product = {
        **_PRODUCT_1,
        "worksOn": {"Windows": False, "Mac": False, "Linux": False},
    }
    _register_library([product])
    rsps_lib.add(rsps_lib.GET, _PRODUCT_URL_1, json=_DOWNLOADS_WITH_PLATFORMS)
    _patch_paths(tmp_path, monkeypatch)
    _seed_session(tmp_path)

    result = handle_refresh(_make_args())

    assert result == ExitCode.SUCCESS
    paths = resolve_app_paths({"HOME": str(tmp_path)})
    library = json.loads(paths.library_cache.read_text())
    assert library["games"][0]["platforms"] == ["windows", "mac", "linux"]
    assert library["games"][0]["release_year"] == 2019
    assert library["games"][0]["release_date"] == "2019-05-28"
    assert library["games"][0]["is_installable"] is True


@rsps_lib.activate
def test_handle_refresh_skips_existing_download_cache(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_library_and_downloads(tmp_path, monkeypatch, downloads_called=[True, False])

    paths = resolve_app_paths({"HOME": str(tmp_path)})
    paths.downloads_cache_dir.mkdir(parents=True, exist_ok=True)
    paths.download_cache("1").write_text('{"product_id":1}', encoding="utf-8")

    result = handle_refresh(_make_args(force=False))
    assert result == ExitCode.SUCCESS


@rsps_lib.activate
def test_handle_refresh_force_refetches_existing_cache(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_library_and_downloads(tmp_path, monkeypatch)

    paths = resolve_app_paths({"HOME": str(tmp_path)})
    paths.downloads_cache_dir.mkdir(parents=True, exist_ok=True)
    paths.download_cache("1").write_text('{"product_id":1}', encoding="utf-8")

    result = handle_refresh(_make_args(force=True))
    assert result == ExitCode.SUCCESS
    dl1 = json.loads(paths.download_cache("1").read_text())
    assert "fetched_at" in dl1


@rsps_lib.activate
def test_handle_refresh_partial_failure_exits_network(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _register_library([_PRODUCT_1, _PRODUCT_2])
    rsps_lib.add(rsps_lib.GET, _PRODUCT_URL_1, json=_DOWNLOADS_1)
    rsps_lib.add(rsps_lib.GET, _PRODUCT_URL_2, status=500)

    _patch_paths(tmp_path, monkeypatch)
    _seed_session(tmp_path)

    result = handle_refresh(_make_args())
    assert result == ExitCode.NETWORK
    err = capsys.readouterr().err
    assert "Beta Game" in err or "2" in err


def test_handle_refresh_not_authenticated_raises_auth_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_paths(tmp_path, monkeypatch)

    with pytest.raises(AuthError, match="Not logged in"):
        handle_refresh(_make_args())


@rsps_lib.activate
def test_handle_refresh_json_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _mock_library_and_downloads(tmp_path, monkeypatch)

    result = handle_refresh(_make_args(output_format="json"))
    assert result == ExitCode.SUCCESS

    captured = capsys.readouterr()
    out = json.loads(captured.out)
    assert out["command"] == "refresh"
    assert out["data"]["total"] == 2
    assert "Fetching library page" not in captured.err


@rsps_lib.activate
def test_handle_refresh_delta_reporting(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    paths = resolve_app_paths({"HOME": str(tmp_path)})
    _seed_library(paths, [_normalize_game(_PRODUCT_1)])

    _register_library([_PRODUCT_1, _PRODUCT_2])
    rsps_lib.add(rsps_lib.GET, _PRODUCT_URL_1, json=_DOWNLOADS_1)
    rsps_lib.add(rsps_lib.GET, _PRODUCT_URL_2, json=_DOWNLOADS_2)
    _patch_paths(tmp_path, monkeypatch)
    _seed_session(tmp_path)

    result = handle_refresh(_make_args())
    assert result == ExitCode.SUCCESS
    out = capsys.readouterr().out
    assert "+1 added" in out


# ── CLI wiring ─────────────────────────────────────────────────────────────────

def test_refresh_is_routed_from_cli() -> None:
    from gog_cli.cli import build_parser
    from gog_cli.refresh import handle_refresh

    args = build_parser().parse_args(["refresh"])
    assert args.handler is handle_refresh


def test_refresh_force_flag_parses() -> None:
    from gog_cli.cli import build_parser

    args = build_parser().parse_args(["refresh", "--force"])
    assert args.force is True


def test_refresh_format_flag_parses() -> None:
    from gog_cli.cli import build_parser

    args = build_parser().parse_args(["refresh", "--format", "json"])
    assert args.output_format == "json"


# ── helpers ────────────────────────────────────────────────────────────────────

def _make_args(*, force: bool = False, output_format: str = "human") -> MagicMock:
    args = MagicMock()
    args.force = force
    args.output_format = output_format
    return args


def _make_mock_client_with_responses() -> object:
    """Return a real GogApiClient pointing at a fake token store."""
    from gog_cli.api import GogApiClient

    class _FakeStore:
        def load_tokens(self) -> dict:
            return {
                "access_token": "tok",
                "refresh_token": "ref",
                "expires_at": "2099-01-01T00:00:00+00:00",
            }

        def save_tokens(self, tokens: dict) -> None:
            pass

    return GogApiClient(_FakeStore())


def _register_library(products: list[dict], total_pages: int = 1) -> None:
    rsps_lib.add(
        rsps_lib.GET,
        _LIBRARY_URL,
        json={"page": 1, "totalPages": total_pages, "products": products},
    )


def _patch_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "gog_cli.refresh.resolve_app_paths",
        lambda: resolve_app_paths({"HOME": str(tmp_path)}),
    )


def _seed_session(tmp_path: Path) -> None:
    paths = resolve_app_paths({"HOME": str(tmp_path)})
    paths.session_state.parent.mkdir(parents=True, exist_ok=True)
    paths.session_state.write_text(
        json.dumps({
            "access_token": "tok",
            "refresh_token": "ref",
            "expires_at": "2099-01-01T00:00:00+00:00",
            "user_id": "1",
            "username": "tester",
        }),
        encoding="utf-8",
    )


def _seed_library(paths: object, games: list[dict]) -> None:
    from gog_cli.state import write_json_file_atomic

    write_json_file_atomic(
        paths.library_cache,  # type: ignore[attr-defined]
        {"fetched_at": "2026-01-01T00:00:00Z", "games": games},
    )


def _mock_library_and_downloads(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    downloads_called: list[bool] | None = None,
) -> None:
    _register_library([_PRODUCT_1, _PRODUCT_2])
    rsps_lib.add(rsps_lib.GET, _PRODUCT_URL_1, json=_DOWNLOADS_1)
    rsps_lib.add(rsps_lib.GET, _PRODUCT_URL_2, json=_DOWNLOADS_2)
    _patch_paths(tmp_path, monkeypatch)
    _seed_session(tmp_path)
