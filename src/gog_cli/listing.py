"""List commands for purchased and backed-up games, and public catalog search."""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime, timedelta
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from gog_cli.api import search_catalog
from gog_cli.backup import BackupLayout
from gog_cli.config import load_config
from gog_cli.errors import ExitCode, UsageError
from gog_cli.metadata import (
    extract_download_summary,
    extract_size_summary,
    normalize_genres,
    normalize_platforms,
)
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
_PLATFORM_COLS: list[tuple[str, str]] = [("windows", "W"), ("mac", "M"), ("linux", "L")]


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

    games = [_enrich_game_metadata(game, paths) for game in cache["games"]]
    games = _apply_purchased_filters(games, args)
    games = _sort_purchased(games, getattr(args, "sort", None))
    fetched_at = cache.get("fetched_at", "")
    output_format = OutputFormat(getattr(args, "output_format", "human"))

    if output_format == OutputFormat.JSON:
        print_json(JsonEnvelope(command="list purchased", data=games))
        return ExitCode.SUCCESS

    active_platforms = normalize_platforms(getattr(args, "platforms", []))
    plat_cols: list[tuple[str, str]] = [
        (k, h) for k, h in _PLATFORM_COLS
        if not active_platforms or k in active_platforms
    ]

    plat_header = "  ".join(f"{h:>9}" for _, h in plat_cols)
    plat_sep = "  ".join(f"{'-' * 9}" for _ in plat_cols)
    header = (
        f"{'ID':>10}  {'Title':<34}  {'Year':>4}  {'Genre':<18}"
        f"  {plat_header}  {'Extras':>9}  {'Total':>9}"
    )
    sep = f"{'-' * 10}  {'-' * 34}  {'-' * 4}  {'-' * 18}  {plat_sep}  {'-' * 9}  {'-' * 9}"
    lines: list[str] = [header, sep]

    for game in games:
        inst = game.get("installer_sizes") or {}
        extras = game.get("extras_size") or 0
        plat_total = sum(inst.get(k) or 0 for k, _ in plat_cols)
        total = plat_total + extras
        plat_cells = "  ".join(f"{_format_size(inst.get(k)):>9}" for k, _ in plat_cols)
        lines.append(
            f"{str(game.get('product_id', '')):>10}  "
            f"{str(game.get('title', '')):<34.34}  "
            f"{_format_year(game.get('release_year')):>4}  "
            f"{_format_genres(game.get('genres', [])):<18.18}  "
            f"{plat_cells}  "
            f"{_format_size(extras or None):>9}  "
            f"{_format_size(total or None):>9}"
        )

    totals_by_plat = {
        k: sum((g.get("installer_sizes") or {}).get(k) or 0 for g in games)
        for k, _ in plat_cols
    }
    total_e = sum(game.get("extras_size") or 0 for game in games)
    grand_total = sum(totals_by_plat.values()) + total_e
    plat_total_cells = "  ".join(
        f"{_format_size(totals_by_plat[k] or None):>9}" for k, _ in plat_cols
    )
    lines.append(sep)
    lines.append(
        f"{'Totals':<72}  "
        f"{plat_total_cells}  "
        f"{_format_size(total_e or None):>9}  "
        f"{_format_size(grand_total or None):>9}"
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
    paths = resolve_app_paths()
    config = load_config(paths)
    destination = getattr(args, "destination", None) or config.destination
    if destination is None:
        raise UsageError(
            "Backup destination is required. Use --destination or set it in config."
        )
    layout = BackupLayout(Path(destination).expanduser())
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
    games = _sort_backed_up(games, getattr(args, "sort", None))

    if output_format == OutputFormat.JSON:
        print_json(JsonEnvelope(command="list backup", data=games))
        return ExitCode.SUCCESS

    lines: list[str] = [
        f"{'ID':>10}  {'Title':<28}  {'Game Dir':<20}  {'Files':>5}  {'Size':>8}  Status",
        f"{'-' * 10}  {'-' * 28}  {'-' * 20}  {'-' * 5}  {'-' * 8}  {'-' * 6}",
    ]
    for game in games:
        lines.append(
            f"{str(game.get('product_id', '')):>10}  "
            f"{str(game.get('title', '')):<28.28}  "
            f"{str(game.get('directory_display', '')):<20.20}  "
            f"{int(game.get('files', 0)):>5}  "
            f"{_format_size(game.get('total_size_bytes')):>8}  "
            f"{game.get('status', GAME_MISSING)}"
        )

    total_files = sum(game.get("files") or 0 for game in games)
    total_size = sum(game.get("total_size_bytes") or 0 for game in games)
    lines.append(f"{'-' * 10}  {'-' * 28}  {'-' * 20}  {'-' * 5}  {'-' * 8}  {'-' * 6}")
    lines.append(
        f"{'Totals':<62}  "
        f"{total_files:>5}  "
        f"{_format_size(total_size or None):>8}"
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


def _enrich_game_metadata(game: dict[str, Any], paths: Any) -> dict[str, Any]:
    enriched = {
        **game,
        "owned": True,
        "platforms": normalize_platforms(game.get("platforms", [])),
        "genres": normalize_genres(game.get("genres", []), game.get("category", "")),
    }
    product_id = game.get("product_id")
    if product_id is None:
        return enriched
    try:
        download_cache = read_json_file(paths.download_cache(str(product_id)))
    except (StateFileMissingError, StateFileCorruptError, StateFileInvalidError):
        return enriched

    summary = extract_download_summary(download_cache)
    size_summary = extract_size_summary(download_cache)
    if summary.get("platforms") and not enriched.get("platforms"):
        enriched["platforms"] = summary["platforms"]
    for key in ("release_date", "release_year", "is_installable", "download_type"):
        value = summary.get(key)
        if value not in (None, "") and enriched.get(key) in (None, ""):
            enriched[key] = value
    enriched["installer_sizes"] = size_summary.get("installer_sizes")
    enriched["extras_size"] = size_summary.get("extras_size")
    return enriched


def _apply_purchased_filters(
    games: list[dict[str, Any]],
    args: argparse.Namespace,
) -> list[dict[str, Any]]:
    platforms = normalize_platforms(_split_filter_values(getattr(args, "platforms", [])))
    genres = [
        value.casefold()
        for value in _split_filter_values(getattr(args, "genres", []))
        if value
    ]
    include_unknown_genre = bool(getattr(args, "include_unknown_genre", False))
    year_range = _parse_year_range(getattr(args, "year", None))
    include_unknown_year = bool(getattr(args, "include_unknown_year", False))
    search = str(getattr(args, "search", "") or "").strip()

    filtered = [
        game
        for game in games
        if _matches_platforms(game, platforms)
        and _matches_year(game, year_range, include_unknown=include_unknown_year)
        and _matches_genres(game, genres, include_unknown=include_unknown_genre)
    ]

    if not search:
        return filtered

    scored = [
        (score, game)
        for game in filtered
        if (score := _title_search_score(search, game)) > 0
    ]
    scored.sort(
        key=lambda item: (
            -item[0],
            str(item[1].get("title", "")).casefold(),
            str(item[1].get("product_id", "")),
        )
    )
    return [game for _, game in scored]


def _split_filter_values(values: Any) -> list[str]:
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, list | tuple | set):
        return []
    result: list[str] = []
    for value in values:
        for part in str(value).split(","):
            normalized = part.strip()
            if normalized:
                result.append(normalized)
    return result


def _parse_year_range(value: Any) -> tuple[int | None, int | None] | None:
    if value in (None, ""):
        return None
    raw = str(value).strip()
    if ".." not in raw:
        if raw.isdigit() and len(raw) == 4:
            year = int(raw)
            return year, year
        raise UsageError("Year filter must be YYYY or START..END")

    start_raw, end_raw = raw.split("..", 1)
    if ".." in end_raw:
        raise UsageError("Year filter must contain only one '..' range separator")
    start = _parse_optional_year(start_raw, "start")
    end = _parse_optional_year(end_raw, "end")
    if start is None and end is None:
        raise UsageError("Year filter must include a start or end year")
    if start is not None and end is not None and start > end:
        raise UsageError("Year filter start must be before end")
    return start, end


def _parse_optional_year(value: str, label: str) -> int | None:
    raw = value.strip()
    if not raw:
        return None
    if not raw.isdigit() or len(raw) != 4:
        raise UsageError(f"Year filter {label} must be a four-digit year")
    return int(raw)


def _matches_platforms(game: dict[str, Any], platforms: list[str]) -> bool:
    if not platforms:
        return True
    game_platforms = set(normalize_platforms(game.get("platforms", [])))
    return any(platform in game_platforms for platform in platforms)


def _matches_year(
    game: dict[str, Any],
    year_range: tuple[int | None, int | None] | None,
    *,
    include_unknown: bool,
) -> bool:
    if year_range is None:
        return True
    year = game.get("release_year")
    if not isinstance(year, int):
        return include_unknown
    start, end = year_range
    if start is not None and year < start:
        return False
    return not (end is not None and year > end)


def _matches_genres(
    game: dict[str, Any],
    genres: list[str],
    *,
    include_unknown: bool,
) -> bool:
    if not genres:
        return True
    game_genres = {str(genre).casefold() for genre in game.get("genres", [])}
    if not game_genres:
        return include_unknown
    return any(genre in game_genres for genre in genres)


def _title_search_score(query: str, game: dict[str, Any]) -> int:
    normalized_query = _search_key(query)
    if not normalized_query:
        return 0

    title = _search_key(game.get("title", ""))
    slug = _search_key(str(game.get("slug", "")).replace("_", " ").replace("-", " "))
    candidates = [candidate for candidate in (title, slug) if candidate]
    if not candidates:
        return 0

    scores: list[int] = []
    for candidate in candidates:
        if candidate == normalized_query:
            scores.append(1000)
        elif candidate.startswith(normalized_query):
            scores.append(900 - min(len(candidate) - len(normalized_query), 100))
        elif normalized_query in candidate:
            scores.append(800 - min(candidate.index(normalized_query), 100))
        else:
            ratio = _best_fuzzy_ratio(normalized_query, candidate)
            if ratio >= 0.78:
                scores.append(int(ratio * 700))
    return max(scores, default=0)


def _search_key(value: Any) -> str:
    return " ".join(str(value).casefold().split())


def _best_fuzzy_ratio(query: str, candidate: str) -> float:
    choices = [candidate, *candidate.split()]
    words = candidate.split()
    if len(words) > 1:
        choices.extend(
            f"{left} {right}" for left, right in zip(words, words[1:], strict=False)
        )
    return max(SequenceMatcher(None, query, choice).ratio() for choice in choices)


def _sort_purchased(games: list[dict[str, Any]], key: str | None) -> list[dict[str, Any]]:
    if key == "title":
        return sorted(games, key=lambda g: str(g.get("title", "")).casefold())
    if key == "year":
        return sorted(games, key=lambda g: (
            g.get("release_year") is None, g.get("release_year") or 0
        ))
    if key == "size":
        def _total(g: dict[str, Any]) -> int:
            inst = g.get("installer_sizes") or {}
            return sum(inst.values()) + (g.get("extras_size") or 0)
        return sorted(games, key=_total, reverse=True)
    return games


def _sort_backed_up(games: list[dict[str, Any]], key: str | None) -> list[dict[str, Any]]:
    if key == "title":
        return sorted(games, key=lambda g: str(g.get("title", "")).casefold())
    if key == "size":
        return sorted(games, key=lambda g: g.get("total_size_bytes") or 0, reverse=True)
    if key == "status":
        return sorted(games, key=lambda g: str(g.get("status", "")))
    if key == "files":
        return sorted(games, key=lambda g: int(g.get("files", 0)), reverse=True)
    return games


def _normalize_manifest_game(game: dict[str, Any]) -> dict[str, Any]:
    files = game.get("files", [])
    status = _normalize_game_status(game.get("status"), files)
    directory = str(game.get("directory", game.get("slug", "")) or "")
    if directory and not directory.endswith("/"):
        directory_display = f"{directory}/"
    else:
        directory_display = directory or "-"
    total_size_bytes = sum(
        int(f.get("expected_size") or f.get("size_bytes") or 0)
        for f in files
        if isinstance(f, dict)
    )
    return {
        "product_id": game.get("product_id", ""),
        "title": game.get("title", ""),
        "directory": directory,
        "directory_display": directory_display,
        "files": len(files) if isinstance(files, list) else 0,
        "total_size_bytes": total_size_bytes or None,
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


def _format_size(n: int | None) -> str:
    if not n:
        return "-"
    units = ("B", "KB", "MB", "GB", "TB")
    x = float(n)
    for unit in units[:-1]:
        if x < 1024:
            if unit == "B":
                return f"{int(x)} B"
            return f"{x:.1f} {unit}"
        x /= 1024
    return f"{x:.2f} {units[-1]}"


def _format_platforms(platforms: Any) -> str:
    if not isinstance(platforms, list) or not platforms:
        return "-"
    return ", ".join(str(platform) for platform in platforms)


def _format_genres(genres: Any) -> str:
    if not isinstance(genres, list) or not genres:
        return "-"
    return ", ".join(str(genre) for genre in genres)


def _format_year(year: Any) -> str:
    if isinstance(year, int):
        return str(year)
    return "-"


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


def handle_search_catalog(args: argparse.Namespace) -> int:
    query = str(getattr(args, "query", "") or "").strip()

    paths = resolve_app_paths()
    owned_ids: set[int] | None = None
    try:
        cache = _load_library_cache(paths.library_cache)
        owned_ids = {
            int(g["product_id"])
            for g in cache["games"]
            if g.get("product_id") is not None
        }
    except (StateFileMissingError, StateFileCorruptError, StateFileInvalidError):
        pass

    raw = search_catalog(query)
    games = [_normalize_catalog_result(p, owned_ids) for p in raw.get("products", [])]
    games = _apply_catalog_filters(games, args)

    output_format = OutputFormat(getattr(args, "output_format", "human"))
    if output_format == OutputFormat.JSON:
        print_json(JsonEnvelope(command="search", data=games))
        return ExitCode.SUCCESS

    if not games:
        print_human([f'No results for "{query}".'])
        return ExitCode.SUCCESS

    lines: list[str] = [
        f"{'ID':>10}  {'Title':<34}  {'Year':>4}  {'Genre':<18}  {'Platforms':<25}  Owned",
        f"{'-' * 10}  {'-' * 34}  {'-' * 4}  {'-' * 18}  {'-' * 25}  {'-' * 5}",
    ]
    for game in games:
        lines.append(
            f"{str(game.get('product_id', '') or ''):>10}  "
            f"{str(game.get('title', '')):<34.34}  "
            f"{_format_year(game.get('release_year')):>4}  "
            f"{_format_genres(game.get('genres', [])):<18.18}  "
            f"{_format_platforms(game.get('platforms', [])):<25.25}  "
            f"{_format_owned(game.get('owned'))}"
        )
    lines.append(f'{len(games)} result(s) for "{query}".')
    print_human(lines)
    return ExitCode.SUCCESS


def _normalize_catalog_result(
    product: dict[str, Any], owned_ids: set[int] | None
) -> dict[str, Any]:
    # catalog.gog.com/v1 returns id as a string
    product_id_raw = product.get("id")
    if isinstance(product_id_raw, str) and product_id_raw.isdigit():
        product_id: int | None = int(product_id_raw)
    elif isinstance(product_id_raw, int):
        product_id = product_id_raw
    else:
        product_id = None

    # releaseDate is "YYYY.MM.DD" in v1 catalog
    release_year_val: int | None = None
    release_date_raw = product.get("releaseDate") or ""
    if (
        isinstance(release_date_raw, str)
        and len(release_date_raw) >= 4
        and release_date_raw[:4].isdigit()
    ):
        release_year_val = int(release_date_raw[:4])

    platforms = normalize_platforms(product.get("operatingSystems", []))
    # genres is a list of {"name": ..., "slug": ...} dicts in v1
    genres = normalize_genres(product.get("genres", []))

    # price in v1: {"finalMoney": {"amount": "4.99", ...}, ...}
    price: str | None = None
    price_data = product.get("price") or {}
    final_money = price_data.get("finalMoney") or {}
    amount = final_money.get("amount")
    if amount is not None:
        price = "free" if str(amount) in ("0", "0.00") else str(amount)

    if owned_ids is None:
        owned: bool | None = None
    elif product_id is not None:
        owned = product_id in owned_ids
    else:
        owned = False

    return {
        "product_id": product_id,
        "title": product.get("title", ""),
        "slug": product.get("slug", ""),
        "release_year": release_year_val,
        "platforms": platforms,
        "genres": genres,
        "price": price,
        "is_available": product.get("productState") == "default",
        "owned": owned,
    }


def _apply_catalog_filters(
    games: list[dict[str, Any]],
    args: argparse.Namespace,
) -> list[dict[str, Any]]:
    platforms = normalize_platforms(_split_filter_values(getattr(args, "platforms", [])))
    genres = [
        value.casefold()
        for value in _split_filter_values(getattr(args, "genres", []))
        if value
    ]
    year_range = _parse_year_range(getattr(args, "year", None))
    return [
        game
        for game in games
        if _matches_platforms(game, platforms)
        and _matches_year(game, year_range, include_unknown=False)
        and _matches_genres(game, genres, include_unknown=False)
    ]


def _format_owned(owned: bool | None) -> str:
    if owned is True:
        return "yes"
    if owned is False:
        return "no"
    return "-"


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
