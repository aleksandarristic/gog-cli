from __future__ import annotations

from pathlib import Path

import pytest

from gog_cli.backup import BackupPlan, FileSpec, PlannedFile, plan_backup, select_games
from gog_cli.errors import UsageError
from gog_cli.layout import BackupLayout

LIBRARY = [
    {"id": 1111, "title": "Witcher 3", "slug": "witcher_3"},
    {"id": 2222, "title": "Cyberpunk 2077", "slug": "cyberpunk_2077"},
    {"id": 3333, "title": "Disco Elysium", "slug": "disco_elysium"},
]


def make_spec(
    source_id: str = "en1installer1",
    role: str = "installer",
    platform: str = "windows",
    language: str = "en",
    size: int = 1000,
) -> FileSpec:
    return FileSpec(
        source_id=source_id,
        role=role,
        platform=platform,
        language=language,
        version="1.0",
        expected_size=size,
        expected_md5=None,
        downlink_url="https://api.gog.com/products/1111/downlink/installer/en1installer1",
        checksum_url=None,
    )


# --- select_games ---


def test_select_by_product_id() -> None:
    result = select_games(LIBRARY, game_selectors=["1111"])
    assert len(result) == 1
    assert result[0]["slug"] == "witcher_3"


def test_select_by_slug() -> None:
    result = select_games(LIBRARY, game_selectors=["cyberpunk_2077"])
    assert result[0]["id"] == 2222


def test_select_by_title_case_insensitive() -> None:
    result = select_games(LIBRARY, game_selectors=["disco elysium"])
    assert result[0]["id"] == 3333


def test_select_all() -> None:
    result = select_games(LIBRARY, all_games=True)
    assert len(result) == 3


def test_select_all_with_exclude() -> None:
    result = select_games(LIBRARY, all_games=True, exclude=["witcher_3"])
    assert len(result) == 2
    assert all(g["slug"] != "witcher_3" for g in result)


def test_select_no_match_raises() -> None:
    with pytest.raises(UsageError, match="No game found"):
        select_games(LIBRARY, game_selectors=["unknown_game"])


def test_select_all_and_game_raises() -> None:
    with pytest.raises(UsageError, match="--all and --game"):
        select_games(LIBRARY, all_games=True, game_selectors=["witcher_3"])


def test_select_no_selectors_returns_empty() -> None:
    result = select_games(LIBRARY)
    assert result == []


# --- plan_backup ---


def test_plan_backup_download(tmp_path: Path) -> None:
    layout = BackupLayout(root=tmp_path)
    games = [{"id": 1111, "title": "Witcher 3", "slug": "witcher_3"}]
    specs = {"1111": [make_spec()]}

    plan = plan_backup(tmp_path, games, specs, layout)

    assert len(plan.downloads) == 1
    assert plan.downloads[0].action == "download"
    assert plan.disk_required_bytes == 1000


def test_plan_backup_skip_existing(tmp_path: Path) -> None:
    layout = BackupLayout(root=tmp_path)
    games = [{"id": 1111, "title": "Witcher 3", "slug": "witcher_3"}]
    spec = make_spec()
    specs = {"1111": [spec]}

    # Pre-create the dest file
    dest = layout.game_dir("witcher_3") / "installers" / "en1installer1"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("existing")

    plan = plan_backup(tmp_path, games, specs, layout)

    assert len(plan.skips) == 1
    assert plan.skips[0].skip_reason == "already_exists"
    assert plan.disk_required_bytes == 0


def test_plan_backup_platform_filter(tmp_path: Path) -> None:
    layout = BackupLayout(root=tmp_path)
    games = [{"id": 1111, "title": "Witcher 3", "slug": "witcher_3"}]
    specs = {
        "1111": [
            make_spec(source_id="win_inst", platform="windows"),
            make_spec(source_id="lin_inst", platform="linux"),
        ]
    }

    plan = plan_backup(tmp_path, games, specs, layout, platforms=["linux"])

    assert len(plan.downloads) == 1
    assert plan.downloads[0].spec.source_id == "lin_inst"


def test_plan_backup_role_filter(tmp_path: Path) -> None:
    layout = BackupLayout(root=tmp_path)
    games = [{"id": 1111, "title": "Witcher 3", "slug": "witcher_3"}]
    specs = {
        "1111": [
            make_spec(source_id="inst1", role="installer"),
            make_spec(source_id="extra1", role="extra"),
        ]
    }

    plan = plan_backup(tmp_path, games, specs, layout, file_roles=["installer"])

    assert len(plan.downloads) == 1
    assert plan.downloads[0].spec.role == "installer"


def test_plan_backup_platform_filter_records_skip(tmp_path: Path) -> None:
    layout = BackupLayout(root=tmp_path)
    games = [{"id": 1111, "title": "Witcher 3", "slug": "witcher_3"}]
    specs = {
        "1111": [
            make_spec(source_id="win_inst", platform="windows"),
            make_spec(source_id="lin_inst", platform="linux"),
        ]
    }

    plan = plan_backup(tmp_path, games, specs, layout, platforms=["linux"])

    assert len(plan.skips) == 1
    assert plan.skips[0].spec.source_id == "win_inst"
    assert plan.skips[0].skip_reason == "platform_not_selected"


def test_plan_backup_language_filter_records_skip(tmp_path: Path) -> None:
    layout = BackupLayout(root=tmp_path)
    games = [{"id": 1111, "title": "Witcher 3", "slug": "witcher_3"}]
    specs = {
        "1111": [
            make_spec(source_id="en_inst", language="en"),
            make_spec(source_id="de_inst", language="de"),
        ]
    }

    plan = plan_backup(tmp_path, games, specs, layout, languages=["en"])

    assert len(plan.downloads) == 1
    assert plan.downloads[0].spec.source_id == "en_inst"
    assert len(plan.skips) == 1
    assert plan.skips[0].spec.source_id == "de_inst"
    assert plan.skips[0].skip_reason == "language_not_selected"


def test_plan_backup_role_filter_records_skip(tmp_path: Path) -> None:
    layout = BackupLayout(root=tmp_path)
    games = [{"id": 1111, "title": "Witcher 3", "slug": "witcher_3"}]
    specs = {
        "1111": [
            make_spec(source_id="inst1", role="installer"),
            make_spec(source_id="extra1", role="extra"),
        ]
    }

    plan = plan_backup(tmp_path, games, specs, layout, file_roles=["installer"])

    assert len(plan.downloads) == 1
    assert len(plan.skips) == 1
    assert plan.skips[0].spec.source_id == "extra1"
    assert plan.skips[0].skip_reason == "role_not_selected"


def test_backup_plan_properties() -> None:
    dest = Path("/fake")
    spec = make_spec()
    planned = [
        PlannedFile(spec=spec, dest=dest / "a", action="download"),
        PlannedFile(spec=spec, dest=dest / "b", action="skip", skip_reason="already_exists"),
    ]
    plan = BackupPlan(destination=dest, games=["1111"], planned=planned, disk_required_bytes=1000)
    assert len(plan.downloads) == 1
    assert len(plan.skips) == 1


def test_plan_backup_disk_free_bytes_when_destination_exists(tmp_path: Path) -> None:
    layout = BackupLayout(root=tmp_path)
    games = [{"id": 1111, "title": "Witcher 3", "slug": "witcher_3"}]
    specs = {"1111": [make_spec()]}

    plan = plan_backup(tmp_path, games, specs, layout)

    assert plan.disk_free_bytes is not None
    assert plan.disk_free_bytes > 0


def test_plan_backup_disk_free_bytes_none_when_destination_missing(tmp_path: Path) -> None:
    destination = tmp_path / "nonexistent"
    layout = BackupLayout(root=destination)
    games = [{"id": 1111, "title": "Witcher 3", "slug": "witcher_3"}]
    specs = {"1111": [make_spec()]}

    plan = plan_backup(destination, games, specs, layout)

    assert plan.disk_free_bytes is None


def test_plan_backup_new_fields_default_empty(tmp_path: Path) -> None:
    layout = BackupLayout(root=tmp_path)
    games = [{"id": 1111, "title": "Witcher 3", "slug": "witcher_3"}]
    specs = {"1111": [make_spec()]}

    plan = plan_backup(tmp_path, games, specs, layout)

    assert plan.orphaned_local_files == []
    assert plan.warnings == []


# --- orphaned file detection (TASK-0039) ---


def test_plan_backup_detects_orphaned_files(tmp_path: Path) -> None:
    layout = BackupLayout(root=tmp_path)
    games = [{"id": 1111, "title": "Witcher 3", "slug": "witcher_3"}]
    spec = make_spec(source_id="en1installer1")
    specs = {"1111": [spec]}

    # Known planned file
    planned_dest = layout.game_dir("witcher_3") / "installers" / "en1installer1"
    planned_dest.parent.mkdir(parents=True, exist_ok=True)
    planned_dest.write_text("game data")

    # Orphaned file not in any spec
    orphan = layout.game_dir("witcher_3") / "installers" / "old_installer.exe"
    orphan.write_text("stale data")

    plan = plan_backup(tmp_path, games, specs, layout)

    assert orphan in plan.orphaned_local_files
    assert planned_dest not in plan.orphaned_local_files


def test_plan_backup_orphan_excludes_tmp_files(tmp_path: Path) -> None:
    layout = BackupLayout(root=tmp_path)
    games = [{"id": 1111, "title": "Witcher 3", "slug": "witcher_3"}]
    specs = {"1111": [make_spec()]}

    game_dir = layout.game_dir("witcher_3")
    game_dir.mkdir(parents=True, exist_ok=True)
    tmp_file = game_dir / "installers" / "partial.tmp"
    tmp_file.parent.mkdir(parents=True, exist_ok=True)
    tmp_file.write_text("partial download")

    plan = plan_backup(tmp_path, games, specs, layout)

    assert tmp_file not in plan.orphaned_local_files


def test_plan_backup_orphan_excludes_manifest_json(tmp_path: Path) -> None:
    layout = BackupLayout(root=tmp_path)
    games = [{"id": 1111, "title": "Witcher 3", "slug": "witcher_3"}]
    specs = {"1111": [make_spec()]}

    game_dir = layout.game_dir("witcher_3")
    game_dir.mkdir(parents=True, exist_ok=True)
    manifest = game_dir / "manifest.json"
    manifest.write_text("{}")

    plan = plan_backup(tmp_path, games, specs, layout)

    assert manifest not in plan.orphaned_local_files


def test_plan_backup_orphan_only_scans_selected_games(tmp_path: Path) -> None:
    layout = BackupLayout(root=tmp_path)
    # Only select witcher_3
    games = [{"id": 1111, "title": "Witcher 3", "slug": "witcher_3"}]
    specs = {"1111": [make_spec()]}

    # File in a different game's dir (not selected)
    other_dir = layout.game_dir("cyberpunk_2077") / "installers"
    other_dir.mkdir(parents=True, exist_ok=True)
    (other_dir / "cyber.exe").write_text("data")

    plan = plan_backup(tmp_path, games, specs, layout)

    orphan_paths = [str(p) for p in plan.orphaned_local_files]
    assert not any("cyberpunk" in p for p in orphan_paths)
