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
    assert plan.estimated_bytes == 1000


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
    assert plan.estimated_bytes == 0


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
    plan = BackupPlan(destination=dest, games=["1111"], planned=planned, estimated_bytes=1000)
    assert len(plan.downloads) == 1
    assert len(plan.skips) == 1
