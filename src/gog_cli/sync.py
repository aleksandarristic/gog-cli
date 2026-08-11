"""Sync planning and stale-backup detection."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from gog_cli.backup import (
    FileSpec,
    PlannedFile,
    _claim_destination,
    _game_directory_name,
    _game_product_id,
    _role_dir,
    build_game_directory_names,
)
from gog_cli.layout import BackupLayout, sanitize_filename

ComparisonStatus = Literal["current", "stale", "missing", "partial", "unverified"]


@dataclass
class FileComparison:
    source_id: str
    role: str
    platform: str | None
    language: str | None
    status: ComparisonStatus
    stale_reason: str | None = None


@dataclass
class SyncPlan:
    destination: Path
    comparisons: list[FileComparison]
    to_download: list[PlannedFile]
    to_verify: list[PlannedFile]
    current: list[FileComparison]
    estimated_bytes: int


def compare_file(spec: FileSpec, manifest_record: dict | None) -> FileComparison:
    base = FileComparison(
        source_id=spec.source_id,
        role=spec.role,
        platform=spec.platform,
        language=spec.language,
        status="missing",
    )

    if manifest_record is None:
        return base

    rec_status = manifest_record.get("status", "")
    if rec_status == "partial":
        return FileComparison(**{**base.__dict__, "status": "partial"})
    if rec_status == "downloaded":
        return FileComparison(**{**base.__dict__, "status": "unverified"})
    if rec_status != "verified":
        return FileComparison(
            **{
                **base.__dict__,
                "status": "stale",
                "stale_reason": "previous_operation_failed",
            }
        )

    # Check staleness
    if manifest_record.get("source_id") != spec.source_id:
        return FileComparison(**{**base.__dict__, "status": "stale", "stale_reason": "id_changed"})
    if manifest_record.get("version") != spec.version:
        return FileComparison(
            **{**base.__dict__, "status": "stale", "stale_reason": "version_changed"}
        )
    if manifest_record.get("expected_size") != spec.expected_size:
        return FileComparison(
            **{**base.__dict__, "status": "stale", "stale_reason": "size_changed"}
        )
    record_md5 = _record_md5(manifest_record)
    # Download metadata does not include a checksum until its downlink is resolved.
    # An unknown current checksum must not look like an explicit checksum removal.
    if spec.expected_md5 is not None and record_md5 != spec.expected_md5:
        return FileComparison(
            **{**base.__dict__, "status": "stale", "stale_reason": "checksum_changed"}
        )

    return FileComparison(**{**base.__dict__, "status": "current"})


def plan_sync(
    destination: Path,
    games: list[dict],
    download_specs: dict[str, list[FileSpec]],
    manifest: dict,
    layout: BackupLayout,
    *,
    platforms: list[str] | None = None,
    languages: list[str] | None = None,
    file_roles: list[str] | None = None,
    game_directories: dict[str, str] | None = None,
) -> SyncPlan:
    manifest_games: dict[str, dict] = {}
    for g in manifest.get("games", []):
        for f in g.get("files", []):
            key = _file_key(f.get("role"), f.get("platform"), f.get("language"), f.get("source_id"))
            manifest_games.setdefault(str(g.get("product_id", "")), {})[key] = f

    comparisons: list[FileComparison] = []
    to_download: list[PlannedFile] = []
    to_verify: list[PlannedFile] = []
    current: list[FileComparison] = []
    estimated_bytes = 0
    destination_owners: dict[Path, FileSpec] = {}

    if game_directories is None:
        game_directories = build_game_directory_names(games)

    for game in games:
        product_id = _game_product_id(game)
        game_dir = layout.game_dir(_game_directory_name(game, game_directories))
        game_manifest = manifest_games.get(product_id, {})

        for spec in download_specs.get(product_id, []):
            if platforms and spec.platform and spec.platform not in platforms:
                continue
            if languages and spec.language and spec.language not in languages:
                continue
            if file_roles and spec.role not in file_roles:
                continue

            key = _file_key(spec.role, spec.platform, spec.language, spec.source_id)
            record = game_manifest.get(key)
            dest_dir = _role_dir(layout, game_dir, spec.role)
            default_dest = dest_dir / sanitize_filename(spec.filename or spec.source_id)
            dest = default_dest
            comparison = compare_file(spec, record)
            if comparison.status in {"current", "unverified"}:
                recorded_dest = _recorded_destination(layout, record)
                existing_dest = recorded_dest or default_dest
                if not existing_dest.is_file():
                    comparison = FileComparison(
                        source_id=spec.source_id,
                        role=spec.role,
                        platform=spec.platform,
                        language=spec.language,
                        status="missing",
                        stale_reason="local_file_missing",
                    )
                else:
                    dest = existing_dest
                    if spec.filename is None:
                        spec.filename = dest.name

            comparisons.append(comparison)
            _claim_destination(destination_owners, dest, spec)

            if comparison.status in ("missing", "stale", "partial"):
                to_download.append(PlannedFile(spec=spec, dest=dest, action="download"))
                if spec.expected_size:
                    estimated_bytes += spec.expected_size
            elif comparison.status == "unverified":
                if spec.expected_md5 is None:
                    spec.expected_md5 = _record_md5(record)
                to_verify.append(PlannedFile(spec=spec, dest=dest, action="verify"))
            elif comparison.status == "current":
                current.append(comparison)

    return SyncPlan(
        destination=destination,
        comparisons=comparisons,
        to_download=to_download,
        to_verify=to_verify,
        current=current,
        estimated_bytes=estimated_bytes,
    )


def _record_md5(manifest_record: dict | None) -> str | None:
    if manifest_record is None:
        return None
    checksum = manifest_record.get("checksum")
    if isinstance(checksum, dict):
        value = checksum.get("value")
        return value if isinstance(value, str) else None
    value = manifest_record.get("expected_md5")
    return value if isinstance(value, str) else None


def _recorded_destination(layout: BackupLayout, manifest_record: dict | None) -> Path | None:
    if manifest_record is None:
        return None
    relative_path = manifest_record.get("relative_path")
    if not isinstance(relative_path, str) or not relative_path:
        return None
    candidate = Path(relative_path)
    if candidate.is_absolute() or ".." in candidate.parts:
        return None
    return layout.root / candidate


def _file_key(
    role: str | None,
    platform: str | None,
    language: str | None,
    source_id: str | None,
) -> str:
    return f"{role}:{platform}:{language}:{source_id}"
