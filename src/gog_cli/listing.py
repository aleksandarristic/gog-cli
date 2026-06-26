"""List commands for purchased and backed-up games."""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from gog_cli.backup import BackupLayout
from gog_cli.errors import ExitCode
from gog_cli.metadata import extract_download_platforms
from gog_cli.output import (
    GAME_CURRENT,
    GAME_ERROR,
    GAME_MISSING,
    GAME_PARTIAL,
    GAME_STALE,
    GAME_UNVERIFIED,
    JsonEnvelope,
    OutputFormat,
    print_human,
    print_json,
)
from gog_cli.state import (
    StateFileCorruptError,
    StateFileInvalidError,
    StateFileMissingError,
    read_json_file,
    resolve_app_paths,
)

_CACHE_MAX_AGE = timedelta(hours=24)
_SUPPORTED_MANIFEST_SCHEMA = 1


def handle_list_purchased(args: argparse.Namespace) -> int:
    paths = resolve_app_paths()
    try:
        cache = _load_library_cache(paths.library_cache)
    except StateFileMissingError:
        print("Purchased library cache is missing. Run `gog refresh`.", file=sys.stderr)
        return ExitCode.FAILURE
    except (StateFileCorruptError, StateFileInvalidError) as exc:
        print(f"Purchased library cache is unreadable: {exc}", file=sys.stderr)
        return ExitCode.PARSER

    games = [_enrich_game_platforms(game, paths) for game in cache["games"]]
    fetched_at = cache.get("fetched_at", "")
    output_format = OutputFormat(getattr(args, "output_format", "human"))

    if output_format == OutputFormat.JSON:
        print_json(JsonEnvelope(command="list purchased", data=games))
        return ExitCode.SUCCESS

    lines: list[str] = [
        f"{'ID':>10}  {'Title':<35}  Platforms",
        f"{'-' * 10}  {'-' * 35}  {'-' * 25}",
    ]
    for game in games:
        lines.append(
            f"{str(game.get('product_id', '')):>10}  "
            f"{str(game.get('title', '')):<35.35}  "
            f"{_format_platforms(game.get('platforms', []))}"
        )

    cache_age = _format_cache_age(fetched_at)
    lines.append(f"{len(games)} games. Cache age: {cache_age}.")

    print_human(lines)

    age = _parse_timestamp(fetched_at)
    if age is None or datetime.now(UTC) - age > _CACHE_MAX_AGE:
        warning = "Purchased library cache is older than 24h. Run `gog refresh`."
        if age is None:
            warning = "Purchased library cache age is unknown. Run `gog refresh`."
        print(warning, file=sys.stderr)

    return ExitCode.SUCCESS


def handle_list_backed_up(args: argparse.Namespace) -> int:
    layout = BackupLayout(Path(args.destination))
    try:
        manifest = _load_manifest(layout.manifest_file)
    except StateFileMissingError:
        print(
            f"No backup manifest exists at {layout.manifest_file}. Run `gog backup`.",
            file=sys.stderr,
        )
        return ExitCode.FAILURE
    except (StateFileCorruptError, StateFileInvalidError) as exc:
        print(f"Backup manifest is unreadable: {exc}", file=sys.stderr)
        return ExitCode.PARSER

    output_format = OutputFormat(getattr(args, "output_format", "human"))
    games = [_normalize_manifest_game(game) for game in manifest["games"]]

    if output_format == OutputFormat.JSON:
        print_json(JsonEnvelope(command="list backed-up", data=games))
        return ExitCode.SUCCESS

    lines: list[str] = [
        f"{'ID':>10}  {'Title':<28}  {'Game Dir':<20}  {'Files':>5}  Status",
        f"{'-' * 10}  {'-' * 28}  {'-' * 20}  {'-' * 5}  {'-' * 6}",
    ]
    for game in games:
        lines.append(
            f"{str(game.get('product_id', '')):>10}  "
            f"{str(game.get('title', '')):<28.28}  "
            f"{str(game.get('directory_display', '')):<20.20}  "
            f"{int(game.get('files', 0)):>5}  "
            f"{game.get('status', GAME_MISSING)}"
        )

    lines.append(f"{len(games)} games backed up to {layout.root}.")
    print_human(lines)
    return ExitCode.SUCCESS


def _load_library_cache(path: Path) -> dict[str, Any]:
    data = read_json_file(path)
    if not isinstance(data, dict):
        raise StateFileInvalidError(f"library cache must contain an object: {path}")
    games = data.get("games")
    if not isinstance(games, list):
        raise StateFileInvalidError(f"library cache must contain a games list: {path}")
    return data


def _load_manifest(path: Path) -> dict[str, Any]:
    data = read_json_file(path)
    if not isinstance(data, dict):
        raise StateFileInvalidError(f"manifest must contain an object: {path}")
    schema_version = data.get("schema_version")
    if schema_version != _SUPPORTED_MANIFEST_SCHEMA:
        raise StateFileInvalidError(f"unsupported manifest schema: {schema_version!r}")
    games = data.get("games")
    if not isinstance(games, list):
        raise StateFileInvalidError(f"manifest must contain a games list: {path}")
    return data


def _enrich_game_platforms(game: dict[str, Any], paths: Any) -> dict[str, Any]:
    if game.get("platforms"):
        return game
    product_id = game.get("product_id")
    if product_id is None:
        return game
    try:
        download_cache = read_json_file(paths.download_cache(str(product_id)))
    except (StateFileMissingError, StateFileCorruptError, StateFileInvalidError):
        return game
    platforms = extract_download_platforms(download_cache)
    if not platforms:
        return game
    return {**game, "platforms": platforms}


def _normalize_manifest_game(game: dict[str, Any]) -> dict[str, Any]:
    files = game.get("files", [])
    status = _normalize_game_status(game.get("status"), files)
    directory = str(game.get("directory", game.get("slug", "")) or "")
    if directory and not directory.endswith("/"):
        directory_display = f"{directory}/"
    else:
        directory_display = directory or "-"
    return {
        "product_id": game.get("product_id", ""),
        "title": game.get("title", ""),
        "directory": directory,
        "directory_display": directory_display,
        "files": len(files) if isinstance(files, list) else 0,
        "status": status,
    }


def _normalize_game_status(status: Any, files: Any) -> str:
    if status in {
        GAME_CURRENT,
        GAME_PARTIAL,
        GAME_STALE,
        GAME_MISSING,
        GAME_UNVERIFIED,
        GAME_ERROR,
    }:
        return str(status)

    if not isinstance(files, list) or not files:
        return GAME_MISSING

    file_statuses = {file.get("status") for file in files if isinstance(file, dict)}
    if "failed" in file_statuses:
        return GAME_ERROR
    if "partial" in file_statuses:
        return GAME_PARTIAL
    if "stale" in file_statuses:
        return GAME_STALE
    if "downloaded" in file_statuses:
        return GAME_UNVERIFIED
    if file_statuses <= {"verified"}:
        return GAME_CURRENT
    return GAME_MISSING


def _format_platforms(platforms: Any) -> str:
    if not isinstance(platforms, list) or not platforms:
        return "-"
    return ", ".join(str(platform) for platform in platforms)


def _parse_timestamp(value: str) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _format_cache_age(fetched_at: str) -> str:
    parsed = _parse_timestamp(fetched_at)
    if parsed is None:
        return "unknown"

    delta = datetime.now(UTC) - parsed
    if delta.total_seconds() < 60:
        return "just now"
    total_minutes = int(delta.total_seconds() // 60)
    days, rem_minutes = divmod(total_minutes, 60 * 24)
    hours, minutes = divmod(rem_minutes, 60)
    if days:
        return f"{days}d {hours}h"
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"
