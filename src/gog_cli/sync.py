"""Sync planning and stale-backup detection."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from gog_cli.backup import FileSpec, PlannedFile, _role_dir
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
    if manifest_record.get("expected_md5") != spec.expected_md5:
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
) -> SyncPlan:
    manifest_games: dict[str, dict] = {}
    for g in manifest.get("games", []):
        for f in g.get("files", []):
            key = _file_key(f.get("role"), f.get("platform"), f.get("language"))
            manifest_games.setdefault(str(g.get("product_id", "")), {})[key] = f

    comparisons: list[FileComparison] = []
    to_download: list[PlannedFile] = []
    to_verify: list[PlannedFile] = []
    current: list[FileComparison] = []
    estimated_bytes = 0

    for game in games:
        product_id = str(game["id"])
        slug = sanitize_filename(game.get("slug") or product_id)
        game_dir = layout.game_dir(slug)
        game_manifest = manifest_games.get(product_id, {})

        for spec in download_specs.get(product_id, []):
            if platforms and spec.platform and spec.platform not in platforms:
                continue
            if languages and spec.language and spec.language not in languages:
                continue
            if file_roles and spec.role not in file_roles:
                continue

            key = _file_key(spec.role, spec.platform, spec.language)
            record = game_manifest.get(key)
            comparison = compare_file(spec, record)
            comparisons.append(comparison)

            dest_dir = _role_dir(layout, game_dir, spec.role)
            dest = dest_dir / sanitize_filename(spec.source_id)

            if comparison.status in ("missing", "stale"):
                to_download.append(PlannedFile(spec=spec, dest=dest, action="download"))
                if spec.expected_size:
                    estimated_bytes += spec.expected_size
            elif comparison.status == "unverified":
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


def _file_key(role: str | None, platform: str | None, language: str | None) -> str:
    return f"{role}:{platform}:{language}"
