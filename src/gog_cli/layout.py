"""Backup destination directory layout and filename safety."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")
_UNSAFE_RE = re.compile(r'[<>:"|?*\\/]')
_MAX_FILENAME_LEN = 200


def sanitize_filename(name: str) -> str:
    name = _CONTROL_RE.sub("", name)
    name = _UNSAFE_RE.sub("_", name)
    name = name.strip().rstrip(".")
    name = name[:_MAX_FILENAME_LEN]
    name = name.strip().rstrip(".")
    return name or "_"


def sanitize_directory_name(name: str, product_id: str | None = None) -> str:
    sanitized = sanitize_filename(name)
    if product_id:
        return f"{sanitized}_{product_id}"
    return sanitized


@dataclass(frozen=True)
class BackupLayout:
    root: Path

    @property
    def metadata_dir(self) -> Path:
        return self.root / "metadata"

    @property
    def manifest_file(self) -> Path:
        return self.metadata_dir / "manifest.json"

    @property
    def library_snapshot(self) -> Path:
        return self.metadata_dir / "library.json"

    @property
    def games_dir(self) -> Path:
        return self.root / "games"

    def game_dir(self, slug_or_id: str) -> Path:
        return self.games_dir / slug_or_id

    def game_metadata(self, slug_or_id: str) -> Path:
        return self.game_dir(slug_or_id) / "metadata.json"

    def installers_dir(self, game_dir: Path) -> Path:
        return game_dir / "installers"

    def patches_dir(self, game_dir: Path) -> Path:
        return game_dir / "patches"

    def extras_dir(self, game_dir: Path) -> Path:
        return game_dir / "extras"

    def language_packs_dir(self, game_dir: Path) -> Path:
        return game_dir / "language-packs"

    def manuals_dir(self, game_dir: Path) -> Path:
        return game_dir / "manuals"

    def other_dir(self, game_dir: Path) -> Path:
        return game_dir / "other"
