from __future__ import annotations

import pytest

from gog_dl.cli import main


def test_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["--version"])

    assert exc_info.value.code == 0
    assert "gog 0.1.0" in capsys.readouterr().out


def test_list_games_placeholder(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["list"]) == 1
    assert capsys.readouterr().out == "Listing games is not implemented yet.\n"


def test_backup_dry_run(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["backup", "--destination", "/tmp/gog-backups", "--dry-run"]) == 0
    assert capsys.readouterr().out == "Would back up owned games to /tmp/gog-backups.\n"


def test_backup_requires_destination(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["backup"])

    assert exc_info.value.code == 2
    assert "--destination" in capsys.readouterr().err
