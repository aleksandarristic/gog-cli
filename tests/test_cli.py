from __future__ import annotations

import pytest

from gog_cli.cli import main


def test_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["--version"])

    assert exc_info.value.code == 0
    assert "gog 0.1.0" in capsys.readouterr().out


def test_list_purchased_not_implemented(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["list", "purchased"]) == 1
    assert "not implemented" in capsys.readouterr().err


def test_list_purchased_format_json(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["list", "purchased", "--format", "json"]) == 1


def test_list_backed_up_requires_destination() -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["list", "backed-up"])
    assert exc_info.value.code == 2


def test_list_backed_up_not_implemented(
    capsys: pytest.CaptureFixture[str], tmp_path: pytest.TempPathFactory
) -> None:
    assert main(["list", "backed-up", "--destination", str(tmp_path)]) == 1
    assert "not implemented" in capsys.readouterr().err


def test_backup_dry_run(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["backup", "--destination", "/tmp/gog-backups", "--dry-run"]) == 0
    assert "Dry run" in capsys.readouterr().out


def test_backup_dry_run_no_destination(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["backup", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "Dry run" in out
    assert "<configured destination>" in out


def test_backup_not_implemented(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["backup", "--destination", "/tmp/gog-backups"]) == 1
    assert "not implemented" in capsys.readouterr().err


def test_backup_selector_flags_parse(capsys: pytest.CaptureFixture[str]) -> None:
    assert (
        main(
            [
                "backup",
                "--destination",
                "/tmp/gog-backups",
                "--dry-run",
                "--game",
                "cyberpunk-2077",
                "--exclude",
                "witcher-3",
                "--platform",
                "linux",
                "--language",
                "en",
                "--yes",
            ]
        )
        == 0
    )


def test_backup_all_flag_parses(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["backup", "--destination", "/tmp/gog-backups", "--dry-run", "--all"]) == 0


def test_sync_dry_run(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["sync", "--destination", "/tmp/gog-backups", "--dry-run"]) == 0
    assert "Dry run" in capsys.readouterr().out


def test_sync_not_implemented(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["sync", "--destination", "/tmp/gog-backups"]) == 1
    assert "not implemented" in capsys.readouterr().err


def test_sync_selector_flags_parse(capsys: pytest.CaptureFixture[str]) -> None:
    assert (
        main(
            [
                "sync",
                "--destination",
                "/tmp/gog-backups",
                "--dry-run",
                "--all",
                "--yes",
                "--downloader",
                "aria2c",
            ]
        )
        == 0
    )


def test_no_interactive_flag_parses(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["backup", "--dry-run", "--no-interactive", "--game", "witcher-3"]) == 0
