"""Backup planning and game selection."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from gog_cli.errors import UsageError
from gog_cli.layout import BackupLayout, sanitize_filename

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
    estimated_bytes: int

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


def plan_backup(
    destination: Path,
    games: list[dict],
    downloads: dict[str, list[FileSpec]],
    layout: BackupLayout,
    *,
    platforms: list[str] | None = None,
    languages: list[str] | None = None,
    file_roles: list[str] | None = None,
) -> BackupPlan:
    planned: list[PlannedFile] = []
    product_ids: list[str] = []
    estimated_bytes = 0

    for game in games:
        product_id = str(game["id"])
        slug = sanitize_filename(game.get("slug") or product_id)
        game_dir = layout.game_dir(slug)
        product_ids.append(product_id)

        specs = downloads.get(product_id, [])
        for spec in specs:
            if platforms and spec.platform and spec.platform not in platforms:
                continue
            if languages and spec.language and spec.language not in languages:
                continue
            if file_roles and spec.role not in file_roles:
                continue

            dest_dir = _role_dir(layout, game_dir, spec.role)
            dest = dest_dir / sanitize_filename(spec.source_id)

            if dest.exists():
                planned.append(
                    PlannedFile(spec=spec, dest=dest, action="skip", skip_reason="already_exists")
                )
            else:
                planned.append(PlannedFile(spec=spec, dest=dest, action="download"))
                if spec.expected_size:
                    estimated_bytes += spec.expected_size

    return BackupPlan(
        destination=destination,
        games=product_ids,
        planned=planned,
        estimated_bytes=estimated_bytes,
    )


def _match_game(game: dict, selector: str) -> bool:
    if str(game.get("id", "")) == selector:
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
) -> list[dict]:
    if all_games and game_selectors:
        raise UsageError("--all and --game cannot be used together")

    if all_games:
        selected = list(library)
    elif game_selectors:
        selected = []
        for selector in game_selectors:
            matches = [g for g in library if _match_game(g, selector)]
            if not matches:
                raise UsageError(f"No game found matching {selector!r}")
            if len(matches) > 1:
                titles = ", ".join(str(g.get("title", g.get("id"))) for g in matches)
                raise UsageError(f"Selector {selector!r} matches multiple games: {titles}")
            selected.append(matches[0])
    else:
        selected = []

    if exclude:
        for selector in exclude:
            selected = [g for g in selected if not _match_game(g, selector)]

    return selected
