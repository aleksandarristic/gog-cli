"""Backup and sync command execution."""

from __future__ import annotations

import argparse
import hashlib
import sys
from dataclasses import dataclass
from email.message import Message
from pathlib import Path
from typing import Any
from uuid import uuid4

import requests

from gog_cli import __version__, log
from gog_cli.api import GogApiClient
from gog_cli.aria2c import check_aria2c, download_via_aria2c
from gog_cli.auth import FileTokenStore
from gog_cli.backup import (
    FileSpec,
    PlannedFile,
    _game_product_id,
    plan_backup,
    select_games,
)
from gog_cli.config import load_config
from gog_cli.downloader import Downloader, DownloadResult, fetch_checksum_xml
from gog_cli.errors import (
    AuthError,
    ExitCode,
    GogError,
    NetworkError,
    ParserError,
    UsageError,
)
from gog_cli.layout import BackupLayout, sanitize_filename
from gog_cli.output import JsonEnvelope, OutputFormat, print_human, print_json
from gog_cli.prompt import is_interactive, numbered_prompt
from gog_cli.state import (
    StateFileCorruptError,
    StateFileMissingError,
    read_json_file,
    resolve_app_paths,
    utc_timestamp,
    write_json_file_atomic,
)
from gog_cli.sync import SyncPlan, plan_sync

_log = log.get_logger(__name__)

_SUPPORTED_MANIFEST_SCHEMA = 1
_ROLE_MAP = {
    "installers": "installer",
    "patches": "patch",
    "language_packs": "language_pack",
    "bonus_content": "extra",
    "manuals": "manual",
}


@dataclass(frozen=True)
class ExecutionResult:
    file: PlannedFile
    game: dict[str, Any]
    result: DownloadResult


def handle_backup(args: argparse.Namespace) -> int:
    context = _load_context(args, require_manifest=False)
    selected = _select_games(context.library, args)
    context.download_specs = _load_download_specs(context.paths, selected)
    _validate_filters(context, selected)
    plan = plan_backup(
        context.destination,
        selected,
        context.download_specs,
        context.layout,
        platforms=context.platforms,
        languages=context.languages,
        file_roles=context.file_roles,
    )
    files_to_process = [
        file for file in plan.planned if file.action in ("download", "verify", "skip")
    ]
    _print_backup_plan(plan, len(files_to_process))

    if args.dry_run:
        return ExitCode.SUCCESS

    _confirm_if_needed(args, files_to_process)
    return _execute_files("backup", context, selected, files_to_process)


def handle_sync(args: argparse.Namespace) -> int:
    context = _load_context(args, require_manifest=True)
    selected = _select_games(context.library, args)
    context.download_specs = _load_download_specs(context.paths, selected)
    _validate_filters(context, selected)
    plan = plan_sync(
        context.destination,
        selected,
        context.download_specs,
        context.manifest,
        context.layout,
        platforms=context.platforms,
        languages=context.languages,
        file_roles=context.file_roles,
    )
    files_to_process = [*plan.to_download, *plan.to_verify]
    _print_sync_plan(plan, len(files_to_process))

    if args.dry_run:
        return ExitCode.SUCCESS

    _confirm_if_needed(args, files_to_process)
    return _execute_files("sync", context, selected, files_to_process)


@dataclass
class _ExecutionContext:
    paths: Any
    destination: Path
    layout: BackupLayout
    library: list[dict[str, Any]]
    download_specs: dict[str, list[FileSpec]]
    manifest: dict[str, Any]
    output_format: OutputFormat
    downloader: str
    platforms: list[str]
    languages: list[str]
    file_roles: list[str]
    client: GogApiClient


def _load_context(args: argparse.Namespace, *, require_manifest: bool) -> _ExecutionContext:
    paths = resolve_app_paths()
    config = load_config(paths)
    destination = (args.destination or config.destination)
    if destination is None:
        raise UsageError(
            "Backup destination is required. Use --destination or GOG_CLI_DESTINATION."
        )
    destination = Path(destination).expanduser()
    layout = BackupLayout(destination)

    library_cache = _load_library_cache(paths.library_cache)
    library = [_normalize_game(game) for game in library_cache["games"]]

    if require_manifest:
        manifest = _read_manifest(layout.manifest_file)
    else:
        manifest = _read_manifest(layout.manifest_file, missing_ok=True)

    downloader = args.downloader or config.downloader

    return _ExecutionContext(
        paths=paths,
        destination=destination,
        layout=layout,
        library=library,
        download_specs={},
        manifest=manifest,
        output_format=OutputFormat(config.output_format),
        downloader=downloader,
        platforms=args.platforms or config.platforms,
        languages=args.languages or config.languages,
        file_roles=config.file_roles,
        client=GogApiClient(FileTokenStore(paths)),
    )


def _load_library_cache(path: Path) -> dict[str, Any]:
    try:
        data = read_json_file(path)
    except StateFileMissingError:
        raise GogError("Purchased library cache is missing. Run `gog refresh`.") from None
    except StateFileCorruptError as exc:
        raise ParserError(f"Purchased library cache is corrupt: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("games"), list):
        raise ParserError(f"Purchased library cache has unsupported shape: {path}")
    return data


def _load_download_specs(paths: Any, library: list[dict[str, Any]]) -> dict[str, list[FileSpec]]:
    specs: dict[str, list[FileSpec]] = {}
    for game in library:
        product_id = _game_product_id(game)
        cache_path = paths.download_cache(product_id)
        try:
            data = read_json_file(cache_path)
        except StateFileMissingError:
            raise GogError(
                f"Download metadata cache is missing for {game.get('title', product_id)}. "
                "Run `gog refresh`."
            ) from None
        except StateFileCorruptError as exc:
            raise ParserError(
                f"Download metadata cache is corrupt for {product_id}: {exc}"
            ) from exc
        specs[product_id] = parse_download_specs(data)
    return specs


def parse_download_specs(cache: dict[str, Any]) -> list[FileSpec]:
    product = cache.get("data", cache)
    downloads = product.get("downloads")
    if not isinstance(downloads, dict):
        raise ParserError("Download metadata is missing a downloads object")

    specs: list[FileSpec] = []
    for key, role in _ROLE_MAP.items():
        entries = downloads.get(key, [])
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            files = entry.get("files", [])
            if not isinstance(files, list):
                continue
            for file_entry in files:
                if not isinstance(file_entry, dict):
                    continue
                source_id = str(file_entry.get("id") or entry.get("id") or "")
                downlink_url = str(file_entry.get("downlink") or "")
                if not source_id or not downlink_url:
                    continue
                filename = _download_filename(file_entry, entry, source_id)
                specs.append(
                    FileSpec(
                        source_id=source_id,
                        role=role,
                        platform=_optional_str(entry.get("os")),
                        language=_optional_str(entry.get("language")),
                        version=_optional_str(entry.get("version")),
                        expected_size=_optional_int(
                            file_entry.get("size", entry.get("total_size"))
                        ),
                        expected_md5=None,
                        downlink_url=downlink_url,
                        checksum_url=None,
                        filename=filename,
                    )
                )
    if downloads and not specs:
        raise ParserError("Download metadata did not contain any supported file entries")
    return specs


def _select_games(library: list[dict[str, Any]], args: argparse.Namespace) -> list[dict[str, Any]]:
    if args.all_games or args.games:
        selected = select_games(
            library,
            game_selectors=args.games,
            exclude=args.exclude,
            all_games=args.all_games,
        )
    else:
        if args.no_interactive or not is_interactive():
            raise UsageError("No games selected. Use --all or --game.")
        labels = [
            f"{game.get('title', '')} ({_game_product_id(game)}, {game.get('slug', '')})"
            for game in library
        ]
        indices = numbered_prompt(labels, "Select games to process:")
        selected = [library[index] for index in indices]
        if args.exclude:
            selected = select_games(selected, exclude=args.exclude, all_games=True)

    if not selected:
        raise UsageError("No games selected after applying filters.")
    return selected


def _confirm_if_needed(args: argparse.Namespace, files_to_process: list[PlannedFile]) -> None:
    if not files_to_process:
        return
    if args.yes:
        return
    if args.no_interactive or not is_interactive():
        raise UsageError("Refusing to modify backups without confirmation. Re-run with --yes.")

    print("Proceed? [y/N] ", end="", file=sys.stderr)
    sys.stderr.flush()
    answer = sys.stdin.readline().strip().lower()
    if answer not in {"y", "yes"}:
        raise UsageError("Backup operation cancelled.")


def _execute_files(
    command: str,
    context: _ExecutionContext,
    selected_games: list[dict[str, Any]],
    files_to_process: list[PlannedFile],
) -> int:
    session = requests.Session()
    downloader = Downloader(session)
    file_to_game = _map_files_to_games(context.layout, selected_games, context.download_specs)
    results: list[ExecutionResult] = []
    auth_failed = False

    context.destination.mkdir(parents=True, exist_ok=True)
    if context.downloader == "aria2c" and files_to_process:
        check_aria2c()

    for planned in files_to_process:
        game = file_to_game.get(str(planned.dest), {})
        if planned.action in {"skip", "verify"}:
            result = _verify_existing(planned)
            results.append(_record_and_report(context, command, game, planned, result))
            continue

        try:
            signed_url, checksum_url = context.client.resolve_downlink_url(
                planned.spec.downlink_url
            )
        except AuthError as exc:
            print(
                f"Authentication failed while resolving {planned.spec.source_id}: {exc}",
                file=sys.stderr,
            )
            auth_failed = True
            break
        except NetworkError as exc:
            result = DownloadResult(
                status="failed",
                path=planned.dest,
                expected_size=planned.spec.expected_size,
                failure_code="resolve_failed",
                failure_message=str(exc),
            )
            results.append(_record_and_report(context, command, game, planned, result))
            continue

        _apply_header_filename(session, signed_url, planned, context.layout, game)
        expected_md5, expected_size = _resolve_checksum(session, checksum_url, planned.spec)
        planned.spec.expected_md5 = expected_md5
        planned.spec.expected_size = expected_size
        result = _download(
            context.downloader,
            signed_url,
            planned.dest,
            expected_size,
            expected_md5,
            downloader,
        )
        signed_url = ""
        results.append(_record_and_report(context, command, game, planned, result))

    if context.output_format == OutputFormat.JSON:
        print_json(JsonEnvelope(command=command, data=[_result_to_json(item) for item in results]))
    else:
        _print_execution_summary(results, auth_failed=auth_failed)

    if auth_failed:
        return ExitCode.AUTH
    if not results:
        return ExitCode.SUCCESS
    failed = [item for item in results if item.result.status in {"failed", "partial"}]
    if failed:
        return ExitCode.FAILURE
    return ExitCode.SUCCESS


def _verify_existing(planned: PlannedFile) -> DownloadResult:
    if not planned.dest.exists():
        return DownloadResult(
            status="failed",
            path=planned.dest,
            expected_size=planned.spec.expected_size,
            failure_code="missing_file",
            failure_message="Expected file is missing",
        )
    if (
        planned.spec.expected_size is not None
        and planned.dest.stat().st_size != planned.spec.expected_size
    ):
        return DownloadResult(
            status="failed",
            path=planned.dest,
            expected_size=planned.spec.expected_size,
            failure_code="size_mismatch",
            failure_message=(
                f"Expected {planned.spec.expected_size} bytes, got {planned.dest.stat().st_size}"
            ),
        )
    if (
        planned.spec.expected_md5 is not None
        and _md5_file(planned.dest) != planned.spec.expected_md5.lower()
    ):
        return DownloadResult(
            status="failed",
            path=planned.dest,
            expected_size=planned.spec.expected_size,
            failure_code="checksum_mismatch",
            failure_message="MD5 checksum did not match expected value",
        )
    return DownloadResult(
        status="verified",
        path=planned.dest,
        bytes_downloaded=planned.dest.stat().st_size,
        expected_size=planned.spec.expected_size,
        checksum_verified=planned.spec.expected_md5 is not None,
    )


def _download(
    downloader_name: str,
    signed_url: str,
    dest: Path,
    expected_size: int | None,
    expected_md5: str | None,
    downloader: Downloader,
) -> DownloadResult:
    if downloader_name == "aria2c":
        return download_via_aria2c(
            signed_url,
            dest,
            expected_size=expected_size,
            expected_md5=expected_md5,
        )
    return downloader.download(
        signed_url,
        dest,
        expected_size=expected_size,
        expected_md5=expected_md5,
    )


def _record_and_report(
    context: _ExecutionContext,
    command: str,
    game: dict[str, Any],
    planned: PlannedFile,
    result: DownloadResult,
) -> ExecutionResult:
    item = ExecutionResult(file=planned, game=game, result=result)
    _update_manifest(context.manifest, context.layout, game, planned, result)
    write_json_file_atomic(context.layout.manifest_file, context.manifest)
    if context.output_format == OutputFormat.HUMAN:
        title = game.get("title", _game_product_id(game))
        line = f"{result.status}  {title} / {planned.spec.role} / {planned.spec.platform or '-'}"
        if result.status in {"failed", "partial"} and result.failure_message:
            line += f" — {result.failure_code}: {result.failure_message}"
        print(line)
    _log.debug("%s recorded %s for %s", command, result.status, planned.spec.source_id)
    return item


def _update_manifest(
    manifest: dict[str, Any],
    layout: BackupLayout,
    game: dict[str, Any],
    planned: PlannedFile,
    result: DownloadResult,
) -> None:
    now = utc_timestamp()
    manifest.setdefault("schema_version", _SUPPORTED_MANIFEST_SCHEMA)
    manifest.setdefault("created_at", now)
    manifest["updated_at"] = now
    manifest.setdefault("tool", {"name": "gog-cli", "version": __version__})
    manifest.setdefault("backup_root_marker", f"gog-cli-backup:{uuid4()}")
    games = manifest.setdefault("games", [])

    product_id = _game_product_id(game)
    game_record = next((g for g in games if str(g.get("product_id")) == product_id), None)
    if game_record is None:
        slug = sanitize_filename(str(game.get("slug") or product_id))
        game_record = {
            "product_id": product_id,
            "title": game.get("title", ""),
            "slug": game.get("slug", ""),
            "directory": f"games/{slug}",
            "files": [],
        }
        games.append(game_record)

    game_record["last_backed_up_at"] = now
    game_record["status"] = _game_status_from_files(game_record.get("files", []))
    files = game_record.setdefault("files", [])

    relative_path = _relative_to_root(planned.dest, layout.root)
    temp_relative_path = (
        _relative_to_root(result.temp_path, layout.root) if result.temp_path is not None else None
    )
    file_id = _file_id(planned.spec)
    file_status = "verified" if result.status == "skipped" else result.status
    file_record = {
        "file_id": file_id,
        "role": planned.spec.role,
        "source_id": planned.spec.source_id,
        "name": planned.dest.name,
        "relative_path": relative_path,
        "temp_relative_path": temp_relative_path,
        "size_bytes": result.expected_size or planned.spec.expected_size,
        "expected_size": result.expected_size or planned.spec.expected_size,
        "expected_md5": planned.spec.expected_md5,
        "checksum": _checksum_record(planned.spec.expected_md5),
        "version": planned.spec.version,
        "build_id": None,
        "platform": planned.spec.platform,
        "language": planned.spec.language,
        "status": file_status,
        "download_started_at": now if file_status in {"downloaded", "verified"} else None,
        "downloaded_at": now if file_status in {"downloaded", "verified"} else None,
        "verified_at": now if file_status == "verified" else None,
        "source_metadata_updated_at": None,
        "failure": _failure_record(result),
    }

    existing = next((f for f in files if f.get("file_id") == file_id), None)
    if existing is None:
        files.append(file_record)
    else:
        existing.update(file_record)
    game_record["status"] = _game_status_from_files(files)


def _read_manifest(path: Path, *, missing_ok: bool = False) -> dict[str, Any]:
    try:
        data = read_json_file(path)
    except StateFileMissingError:
        if missing_ok:
            return _new_manifest()
        raise GogError("Backup manifest is missing. Run `gog backup` first.") from None
    except StateFileCorruptError as exc:
        raise ParserError(f"Backup manifest is corrupt: {exc}") from exc
    if not isinstance(data, dict):
        raise ParserError(f"Backup manifest has unsupported shape: {path}")
    if data.get("schema_version") != _SUPPORTED_MANIFEST_SCHEMA:
        raise ParserError(f"Unsupported backup manifest schema: {data.get('schema_version')!r}")
    if not isinstance(data.get("games", []), list):
        raise ParserError(f"Backup manifest games field is invalid: {path}")
    return data


def _new_manifest() -> dict[str, Any]:
    now = utc_timestamp()
    return {
        "schema_version": _SUPPORTED_MANIFEST_SCHEMA,
        "created_at": now,
        "updated_at": now,
        "tool": {"name": "gog-cli", "version": __version__},
        "backup_root_marker": f"gog-cli-backup:{uuid4()}",
        "games": [],
    }


def _map_files_to_games(
    layout: BackupLayout,
    selected_games: list[dict[str, Any]],
    download_specs: dict[str, list[FileSpec]],
) -> dict[str, dict[str, Any]]:
    mapping: dict[str, dict[str, Any]] = {}
    for game in selected_games:
        product_id = _game_product_id(game)
        slug = sanitize_filename(str(game.get("slug") or product_id))
        game_dir = layout.game_dir(slug)
        for spec in download_specs.get(product_id, []):
            dest = (
                game_dir
                / _role_subdir(spec.role)
                / sanitize_filename(spec.filename or spec.source_id)
            )
            mapping[str(dest)] = game
    return mapping


def _role_subdir(role: str) -> str:
    return {
        "installer": "installers",
        "patch": "patches",
        "extra": "extras",
        "language_pack": "language-packs",
        "manual": "manuals",
    }.get(role, "other")


def _resolve_checksum(
    session: requests.Session,
    checksum_url: str,
    spec: FileSpec,
) -> tuple[str | None, int | None]:
    expected_md5 = spec.expected_md5
    expected_size = spec.expected_size
    if checksum_url:
        checksum_md5, checksum_size = fetch_checksum_xml(session, checksum_url)
        expected_md5 = checksum_md5 or expected_md5
        expected_size = checksum_size or expected_size
    return expected_md5, expected_size


def _apply_header_filename(
    session: requests.Session,
    signed_url: str,
    planned: PlannedFile,
    layout: BackupLayout,
    game: dict[str, Any],
) -> None:
    if planned.spec.filename:
        return
    filename = _filename_from_headers(session, signed_url)
    if not filename:
        return
    planned.spec.filename = filename
    product_id = _game_product_id(game)
    slug = sanitize_filename(str(game.get("slug") or product_id))
    planned.dest = (
        layout.game_dir(slug)
        / _role_subdir(planned.spec.role)
        / sanitize_filename(filename)
    )


def _filename_from_headers(session: requests.Session, signed_url: str) -> str | None:
    try:
        response = session.head(signed_url, allow_redirects=True, timeout=15)
        response.raise_for_status()
    except requests.RequestException:
        return None
    header = response.headers.get("Content-Disposition", "")
    if not header:
        return None
    message = Message()
    message["content-disposition"] = header
    filename = message.get_filename()
    if not filename:
        return None
    return Path(filename).name


def _human_size(n: int | None) -> str:
    if n is None:
        return "?"
    units = ("B", "KiB", "MiB", "GiB", "TiB")
    x = float(n)
    for unit in units[:-1]:
        if x < 1024:
            return f"{x:.1f} {unit}"
        x /= 1024
    return f"{x:.1f} {units[-1]}"


def _print_backup_plan(plan: Any, files_to_process: int) -> None:
    print_human([f"Plan: {files_to_process} files to download, {len(plan.skips)} already present."])
    for pf in plan.downloads:
        name = pf.spec.filename or pf.spec.source_id
        role = pf.spec.role
        platform = pf.spec.platform or "-"
        size = _human_size(pf.spec.expected_size)
        print(f"  {name:<55} {role:<12} {platform:<10} {size:>10}")
    print_human([f"Estimated total: {_human_size(plan.estimated_bytes)}."])


def _print_sync_plan(plan: SyncPlan, files_to_process: int) -> None:
    print_human(
        [
            f"Plan: {len(plan.to_download)} files to download, {len(plan.to_verify)} to verify.",
            f"{len(plan.current)} files current. {files_to_process} files need work.",
            f"Estimated bytes: {plan.estimated_bytes}.",
        ]
    )


def _print_execution_summary(results: list[ExecutionResult], *, auth_failed: bool) -> None:
    failed = sum(1 for item in results if item.result.status in {"failed", "partial"})
    succeeded = len(results) - failed
    print(f"Summary: {succeeded} succeeded, {failed} failed.")
    if auth_failed:
        print("Stopped because authentication failed.", file=sys.stderr)


def _result_to_json(item: ExecutionResult) -> dict[str, Any]:
    return {
        "product_id": _game_product_id(item.game),
        "title": item.game.get("title", ""),
        "source_id": item.file.spec.source_id,
        "name": item.file.dest.name,
        "role": item.file.spec.role,
        "platform": item.file.spec.platform,
        "language": item.file.spec.language,
        "status": item.result.status,
        "path": str(item.result.path or item.file.dest),
        "failure_code": item.result.failure_code,
        "failure_message": item.result.failure_message,
    }


def _normalize_game(game: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(game)
    normalized["id"] = _game_product_id(game)
    normalized["product_id"] = _game_product_id(game)
    return normalized


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _download_filename(
    file_entry: dict[str, Any],
    entry: dict[str, Any],
    _source_id: str,
) -> str | None:
    for value in (
        file_entry.get("name"),
        file_entry.get("filename"),
        file_entry.get("title"),
        entry.get("filename"),
        entry.get("name"),
    ):
        if isinstance(value, str) and value.strip():
            return Path(value.strip()).name
    return None


def _relative_to_root(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _failure_record(result: DownloadResult) -> dict[str, str | None] | None:
    if result.failure_code is None and result.failure_message is None:
        return None
    return {"code": result.failure_code, "message": result.failure_message}


def _checksum_record(expected_md5: str | None) -> dict[str, str] | None:
    if not expected_md5:
        return None
    return {"algorithm": "md5", "value": expected_md5}


def _file_id(spec: FileSpec) -> str:
    return ":".join(
        [
            spec.role,
            spec.platform or "",
            spec.language or "",
            spec.source_id,
        ]
    )


def _game_status_from_files(files: list[dict[str, Any]]) -> str:
    statuses = {file.get("status") for file in files if isinstance(file, dict)}
    if not statuses:
        return "missing"
    if "failed" in statuses:
        return "error"
    if "partial" in statuses:
        return "partial"
    if "stale" in statuses:
        return "stale"
    if "downloaded" in statuses:
        return "unverified"
    if statuses <= {"verified"}:
        return "current"
    return "missing"


def _md5_file(path: Path) -> str:
    h = hashlib.md5()  # noqa: S324 - MD5 is used for GOG file integrity metadata.
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _validate_filters(context: _ExecutionContext, selected: list[dict[str, Any]]) -> None:
    specs = [
        spec
        for game in selected
        for spec in context.download_specs.get(_game_product_id(game), [])
    ]
    if context.platforms:
        available = {spec.platform for spec in specs if spec.platform}
        missing = sorted(set(context.platforms) - available)
        if missing:
            raise UsageError(f"Unknown platform filter: {', '.join(missing)}")
    if context.languages:
        available = {spec.language for spec in specs if spec.language}
        missing = sorted(set(context.languages) - available)
        if missing:
            raise UsageError(f"Unknown language filter: {', '.join(missing)}")
