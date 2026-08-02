"""Backup planning and game selection."""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from gog_cli.errors import UsageError
from gog_cli.fuzzy import title_search_score
from gog_cli.layout import BackupLayout, sanitize_directory_name, sanitize_filename
from gog_cli.prompt import numbered_prompt

ActionType = Literal["download", "skip", "verify", "conflict"]


@dataclass
class FileSpec:
    """A file to be downloaded as part of a backup."""

    source_id: str
    role: str
    platform: str | None
    language: str | None
    version: str | None
    expected_size: int | None
    expected_md5: str | None
    downlink_url: str
    checksum_url: str | None
    filename: str | None = None


@dataclass
class PlannedFile:
    """One file in a backup plan."""

    spec: FileSpec
    dest: Path
    action: ActionType
    skip_reason: str | None = None


@dataclass
class BackupPlan:
    """Full plan for a backup run."""

    destination: Path
    games: list[str]
    planned: list[PlannedFile]
    disk_required_bytes: int
    disk_free_bytes: int | None = None
    orphaned_local_files: list[Path] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def downloads(self) -> list[PlannedFile]:
        return [p for p in self.planned if p.action == "download"]

    @property
    def skips(self) -> list[PlannedFile]:
        return [p for p in self.planned if p.action == "skip"]


_ROLE_DIR = {
    "installer": "installers",
    "patch": "patches",
    "extra": "extras",
    "language_pack": "language-packs",
    "manual": "manuals",
}


def _role_dir(layout: BackupLayout, game_dir: Path, role: str) -> Path:
    subdir = _ROLE_DIR.get(role, "other")
    return game_dir / subdir


def build_game_directory_names(
    games: list[dict],
    *,
    existing: dict[str, str] | None = None,
) -> dict[str, str]:
    """Return stable directory names, disambiguating sanitized slug collisions."""
    bases: dict[str, list[str]] = {}
    game_bases: dict[str, str] = {}
    for game in games:
        product_id = _game_product_id(game)
        base = sanitize_filename(str(game.get("slug") or product_id))
        game_bases[product_id] = base
        bases.setdefault(base, []).append(product_id)

    names = {
        product_id: (
            sanitize_directory_name(base, product_id)
            if len(bases[base]) > 1
            else base
        )
        for product_id, base in game_bases.items()
    }
    for product_id, directory_name in (existing or {}).items():
        if product_id in names:
            names[product_id] = directory_name
    return names


def _game_directory_name(game: dict, game_directories: dict[str, str] | None) -> str:
    product_id = _game_product_id(game)
    if game_directories and product_id in game_directories:
        return game_directories[product_id]
    return build_game_directory_names([game])[product_id]


def _claim_destination(
    owners: dict[Path, FileSpec],
    dest: Path,
    spec: FileSpec,
) -> None:
    previous = owners.get(dest)
    if previous is not None:
        raise UsageError(
            "Multiple source files map to the same backup path "
            f"{dest}: {previous.source_id!r} and {spec.source_id!r}"
        )
    owners[dest] = spec


def plan_backup(
    destination: Path,
    games: list[dict],
    downloads: dict[str, list[FileSpec]],
    layout: BackupLayout,
    *,
    platforms: list[str] | None = None,
    languages: list[str] | None = None,
    file_roles: list[str] | None = None,
    game_directories: dict[str, str] | None = None,
) -> BackupPlan:
    planned: list[PlannedFile] = []
    product_ids: list[str] = []
    game_dirs: list[Path] = []
    disk_required_bytes = 0
    destination_owners: dict[Path, FileSpec] = {}

    if game_directories is None:
        game_directories = build_game_directory_names(games)

    for game in games:
        product_id = _game_product_id(game)
        game_dir = layout.game_dir(_game_directory_name(game, game_directories))
        product_ids.append(product_id)
        game_dirs.append(game_dir)

        specs = downloads.get(product_id, [])
        for spec in specs:
            dest_dir = _role_dir(layout, game_dir, spec.role)
            dest = dest_dir / sanitize_filename(spec.filename or spec.source_id)

            if platforms and spec.platform and spec.platform not in platforms:
                planned.append(PlannedFile(
                    spec=spec, dest=dest, action="skip", skip_reason="platform_not_selected"
                ))
                continue
            if languages and spec.language and spec.language not in languages:
                planned.append(PlannedFile(
                    spec=spec, dest=dest, action="skip", skip_reason="language_not_selected"
                ))
                continue
            if file_roles and spec.role not in file_roles:
                planned.append(PlannedFile(
                    spec=spec, dest=dest, action="skip", skip_reason="role_not_selected"
                ))
                continue

            _claim_destination(destination_owners, dest, spec)

            if dest.exists():
                planned.append(
                    PlannedFile(spec=spec, dest=dest, action="skip", skip_reason="already_exists")
                )
            else:
                planned.append(PlannedFile(spec=spec, dest=dest, action="download"))
                if spec.expected_size:
                    disk_required_bytes += spec.expected_size

    planned_dests = {pf.dest for pf in planned}
    orphaned_local_files: list[Path] = []
    for game_dir in game_dirs:
        if not game_dir.exists():
            continue
        for path in game_dir.rglob("*"):
            if not path.is_file():
                continue
            if path.name == "manifest.json" or path.suffix == ".tmp":
                continue
            if path not in planned_dests:
                orphaned_local_files.append(path)

    disk_free_bytes: int | None = None
    if destination.exists():
        disk_free_bytes = shutil.disk_usage(destination).free

    return BackupPlan(
        destination=destination,
        games=product_ids,
        planned=planned,
        disk_required_bytes=disk_required_bytes,
        disk_free_bytes=disk_free_bytes,
        orphaned_local_files=orphaned_local_files,
    )


def _game_product_id(game: dict) -> str:
    return str(game.get("product_id", game.get("id", "")))


def _match_game(game: dict, selector: str) -> bool:
    if _game_product_id(game) == selector:
        return True
    if game.get("slug", "") == selector:
        return True
    return (game.get("title", "") or "").lower() == selector.lower()


def select_games(
    library: list[dict],
    *,
    game_selectors: list[str] | None = None,
    exclude: list[str] | None = None,
    all_games: bool = False,
    interactive: bool = False,
) -> list[dict]:
    if all_games and game_selectors:
        raise UsageError("--all and --game cannot be used together")

    if all_games:
        selected = list(library)
    elif game_selectors:
        selected = []
        for selector in game_selectors:
            matches = [g for g in library if _match_game(g, selector)]
            if len(matches) > 1:
                titles = ", ".join(str(g.get("title", g.get("id"))) for g in matches)
                raise UsageError(f"Selector {selector!r} matches multiple games: {titles}")
            if not matches:
                matches = _resolve_fuzzy(library, selector, interactive=interactive)
            selected.extend(matches)
    else:
        selected = []

    if exclude:
        for selector in exclude:
            selected = [g for g in selected if not _match_game(g, selector)]

    return selected


def _fuzzy_candidates(library: list[dict], selector: str) -> list[dict]:
    scored = [(score, g) for g in library if (score := title_search_score(selector, g)) > 0]
    scored.sort(key=lambda item: (-item[0], str(item[1].get("title", "")).casefold()))
    return [g for _, g in scored]


def _resolve_fuzzy(library: list[dict], selector: str, *, interactive: bool) -> list[dict]:
    candidates = _fuzzy_candidates(library, selector)
    if not candidates:
        raise UsageError(f"No game found matching {selector!r}")
    if len(candidates) == 1:
        return candidates
    if not interactive:
        titles = ", ".join(
            f"{g.get('title', g.get('id'))!r} ({_game_product_id(g)})" for g in candidates
        )
        raise UsageError(
            f"{selector!r} matches multiple games: {titles}. "
            "Use an exact id or slug, or run this interactively to pick one."
        )
    labels = [
        f"{g.get('title', '')} ({_game_product_id(g)}, {g.get('slug', '')})" for g in candidates
    ]
    indices = numbered_prompt(labels, f"Multiple games match {selector!r} — select:")
    return [candidates[i] for i in indices]
