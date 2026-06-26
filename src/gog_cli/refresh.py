"""gog refresh — fetch library and download-metadata caches from GOG API."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from gog_cli import log
from gog_cli.api import GogApiClient
from gog_cli.auth import FileTokenStore
from gog_cli.errors import ExitCode, NetworkError
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
    works_on = product.get("worksOn", {})
    platforms = [p.lower() for p, enabled in works_on.items() if enabled]
    return {
        "product_id": product["id"],
        "title": product.get("title", ""),
        "slug": product.get("slug", ""),
        "platforms": platforms,
        "image_url": product.get("image", ""),
        "is_pre_order": bool(product.get("isComingSoon", False)),
    }


def _fetch_library(client: GogApiClient) -> list[dict]:
    page = 1
    games: list[dict] = []
    while True:
        data = client.get_library_page(page)
        for product in data.get("products", []):
            games.append(_normalize_game(product))
        if page >= data.get("totalPages", 1):
            break
        page += 1
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

    games = _fetch_library(client)

    failures: list[str] = []
    fetched_at = utc_timestamp()

    for game in games:
        product_id = game["product_id"]
        cache_path = paths.download_cache(str(product_id))

        if not force and cache_path.exists():
            continue

        try:
            download_data = client.get_product_downloads(product_id)
        except (NetworkError, Exception) as exc:  # noqa: BLE001
            failures.append(f"{game['title']} ({product_id}): {exc}")
            _log.warning("download fetch failed for %s: %s", product_id, exc)
            continue

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
