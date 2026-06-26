"""gog refresh — fetch library and download-metadata caches from GOG API."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from gog_cli import log
from gog_cli.api import GogApiClient
from gog_cli.auth import FileTokenStore
from gog_cli.errors import ExitCode, NetworkError
from gog_cli.metadata import (
    extract_download_summary,
    normalize_genres,
    normalize_platforms,
    normalize_release_date,
    release_year,
)
from gog_cli.output import JsonEnvelope, OutputFormat, print_human, print_json
from gog_cli.state import (
    StateFileMissingError,
    read_json_file,
    resolve_app_paths,
    utc_timestamp,
    write_json_file_atomic,
)

_log = log.get_logger(__name__)


def _normalize_game(product: dict) -> dict:
    platforms = normalize_platforms(product.get("worksOn", {}))
    release_date = normalize_release_date(product.get("releaseDate"))
    return {
        "product_id": product["id"],
        "title": product.get("title", ""),
        "slug": product.get("slug", ""),
        "platforms": platforms,
        "release_date": release_date,
        "release_year": release_year(release_date),
        "category": str(product.get("category") or ""),
        "genres": normalize_genres(product.get("category"), product.get("tags", [])),
        "image_url": product.get("image", ""),
        "is_pre_order": bool(product.get("isComingSoon", False)),
        "is_game": bool(product.get("isGame", True)),
        "is_movie": bool(product.get("isMovie", False)),
        "is_galaxy_compatible": bool(product.get("isGalaxyCompatible", False)),
    }


def _fetch_library(client: GogApiClient, *, progress: bool = False) -> list[dict]:
    page = 1
    games: list[dict] = []
    total_pages: int | None = None
    while True:
        page_label = f"{page}/{total_pages}" if total_pages else str(page)
        _print_progress(progress, f"Fetching library page {page_label}...")
        data = client.get_library_page(page)
        total_pages = int(data.get("totalPages", 1))
        for product in data.get("products", []):
            games.append(_normalize_game(product))
        if page >= total_pages:
            break
        page += 1
    _print_progress(progress, f"Fetched {len(games)} library entries.")
    return games


def _compute_delta(
    old_games: list[dict], new_games: list[dict]
) -> tuple[int, int, int]:
    old_by_id = {g["product_id"]: g for g in old_games}
    new_by_id = {g["product_id"]: g for g in new_games}
    added = sum(1 for pid in new_by_id if pid not in old_by_id)
    removed = sum(1 for pid in old_by_id if pid not in new_by_id)
    changed = sum(
        1
        for pid, g in new_by_id.items()
        if pid in old_by_id
        and (
            g["title"] != old_by_id[pid]["title"]
            or g["slug"] != old_by_id[pid]["slug"]
        )
    )
    return added, removed, changed


def _load_old_games(library_cache: Path) -> list[dict]:
    try:
        data = read_json_file(library_cache)
        return data.get("games", [])
    except (StateFileMissingError, Exception):
        return []


def handle_refresh(args: argparse.Namespace) -> int:
    paths = resolve_app_paths()
    store = FileTokenStore(paths)
    client = GogApiClient(store)

    # load tokens early so AuthError surfaces before any network calls
    store.load_tokens()

    output_format = OutputFormat(getattr(args, "output_format", "human"))
    force = getattr(args, "force", False)

    old_games = _load_old_games(paths.library_cache)

    progress = output_format == OutputFormat.HUMAN
    games = _fetch_library(client, progress=progress)

    failures: list[str] = []
    fetched_at = utc_timestamp()
    total_games = len(games)
    _print_progress(progress, f"Refreshing download metadata for {total_games} games...")

    for index, game in enumerate(games, start=1):
        product_id = game["product_id"]
        cache_path = paths.download_cache(str(product_id))
        title = str(game.get("title") or product_id)

        if not force and cache_path.exists():
            _enrich_game_from_download_cache(game, cache_path)
            _print_metadata_progress(progress, index, total_games, title, cached=True)
            continue

        try:
            download_data = client.get_product_downloads(product_id)
        except (NetworkError, Exception) as exc:  # noqa: BLE001
            failures.append(f"{game['title']} ({product_id}): {exc}")
            _log.warning("download fetch failed for %s: %s", product_id, exc)
            _print_metadata_progress(progress, index, total_games, title, failed=True)
            continue

        _enrich_game_from_download_data(game, download_data)
        _print_metadata_progress(progress, index, total_games, title)

        write_json_file_atomic(
            cache_path,
            {
                "fetched_at": fetched_at,
                "product_id": product_id,
                "data": download_data,
            },
        )

    write_json_file_atomic(
        paths.library_cache,
        {"fetched_at": fetched_at, "games": games},
    )

    added, removed, changed = _compute_delta(old_games, games)
    total = len(games)

    if output_format == OutputFormat.JSON:
        print_json(
            JsonEnvelope(
                command="refresh",
                data={
                    "total": total,
                    "added": added,
                    "removed": removed,
                    "changed": changed,
                    "failures": failures,
                },
            )
        )
    else:
        print_human(
            [
                (
                    f"Refreshed {total} games  "
                    f"(+{added} added, -{removed} removed, ~{changed} changed)."
                )
            ]
        )
        for msg in failures:
            print(f"  warning: {msg}", file=sys.stderr)

    if failures:
        return ExitCode.NETWORK
    return ExitCode.SUCCESS


def _print_progress(enabled: bool, message: str) -> None:
    if enabled:
        print(message, file=sys.stderr, flush=True)


def _print_metadata_progress(
    enabled: bool,
    index: int,
    total: int,
    title: str,
    *,
    cached: bool = False,
    failed: bool = False,
) -> None:
    if not enabled:
        return
    if index != 1 and index != total and index % 10 != 0 and not failed:
        return
    status = "cached" if cached else "fetched"
    if failed:
        status = "failed"
    print(
        f"Download metadata {index}/{total}: {status} {title}",
        file=sys.stderr,
        flush=True,
    )


def _enrich_game_from_download_cache(game: dict, cache_path: Path) -> None:
    try:
        cache = read_json_file(cache_path)
    except Exception:  # noqa: BLE001
        return
    if isinstance(cache, dict):
        _enrich_game_from_download_data(game, cache)


def _enrich_game_from_download_data(game: dict, download_data: dict) -> None:
    summary = extract_download_summary(download_data)
    platforms = summary.get("platforms")
    if platforms:
        game["platforms"] = platforms
    for key in ("is_installable", "download_type"):
        value = summary.get(key)
        if value not in (None, ""):
            game[key] = value
