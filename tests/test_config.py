from __future__ import annotations

from pathlib import Path

import pytest

from gog_cli.config import load_config
from gog_cli.errors import UsageError
from gog_cli.state import resolve_app_paths


def test_defaults(tmp_path: Path) -> None:
    paths = resolve_app_paths({"HOME": str(tmp_path)})
    config = load_config(paths, env={})

    assert config.destination is None
    assert config.downloader == "direct"
    assert config.platforms == []
    assert config.languages == []
    assert config.file_roles == []
    assert config.output_format == "human"
    assert config.interactive is True


def test_toml_destination_and_downloader(tmp_path: Path) -> None:
    config_dir = tmp_path / ".config" / "gog-cli"
    config_dir.mkdir(parents=True)
    (config_dir / "config.toml").write_text(
        '[defaults]\ndestination = "/mnt/backups"\ndownloader = "aria2c"\n'
    )

    paths = resolve_app_paths({"HOME": str(tmp_path)})
    config = load_config(paths, env={})

    assert config.destination == Path("/mnt/backups")
    assert config.downloader == "aria2c"


def test_toml_list_fields(tmp_path: Path) -> None:
    config_dir = tmp_path / ".config" / "gog-cli"
    config_dir.mkdir(parents=True)
    (config_dir / "config.toml").write_text(
        '[defaults]\nplatforms = ["linux", "windows"]\nlanguages = ["en", "fr"]\n'
    )

    paths = resolve_app_paths({"HOME": str(tmp_path)})
    config = load_config(paths, env={})

    assert config.platforms == ["linux", "windows"]
    assert config.languages == ["en", "fr"]


def test_missing_config_file_uses_defaults(tmp_path: Path) -> None:
    paths = resolve_app_paths({"HOME": str(tmp_path)})
    config = load_config(paths, env={})

    assert config.downloader == "direct"
    assert config.output_format == "human"


def test_env_destination_and_downloader(tmp_path: Path) -> None:
    paths = resolve_app_paths({"HOME": str(tmp_path)})
    config = load_config(
        paths, env={"GOG_CLI_DESTINATION": "/mnt/env", "GOG_CLI_DOWNLOADER": "aria2c"}
    )

    assert config.destination == Path("/mnt/env")
    assert config.downloader == "aria2c"


def test_env_list_fields(tmp_path: Path) -> None:
    paths = resolve_app_paths({"HOME": str(tmp_path)})
    config = load_config(
        paths,
        env={"GOG_CLI_PLATFORMS": "linux,windows", "GOG_CLI_LANGUAGES": "en, fr "},
    )

    assert config.platforms == ["linux", "windows"]
    assert config.languages == ["en", "fr"]


def test_env_format_and_interactive(tmp_path: Path) -> None:
    paths = resolve_app_paths({"HOME": str(tmp_path)})
    config = load_config(paths, env={"GOG_CLI_FORMAT": "json", "GOG_CLI_INTERACTIVE": "false"})

    assert config.output_format == "json"
    assert config.interactive is False


def test_env_overrides_toml(tmp_path: Path) -> None:
    config_dir = tmp_path / ".config" / "gog-cli"
    config_dir.mkdir(parents=True)
    (config_dir / "config.toml").write_text('[defaults]\ndownloader = "direct"\n')

    paths = resolve_app_paths({"HOME": str(tmp_path)})
    config = load_config(paths, env={"GOG_CLI_DOWNLOADER": "aria2c"})

    assert config.downloader == "aria2c"


def test_unknown_toml_key_raises_usage_error(tmp_path: Path) -> None:
    config_dir = tmp_path / ".config" / "gog-cli"
    config_dir.mkdir(parents=True)
    (config_dir / "config.toml").write_text('[defaults]\nunknown_key = "value"\n')

    paths = resolve_app_paths({"HOME": str(tmp_path)})
    with pytest.raises(UsageError, match="Unknown config keys"):
        load_config(paths, env={})


def test_unknown_top_level_toml_key_raises_usage_error(tmp_path: Path) -> None:
    config_dir = tmp_path / ".config" / "gog-cli"
    config_dir.mkdir(parents=True)
    (config_dir / "config.toml").write_text('foo = "bar"\n')

    paths = resolve_app_paths({"HOME": str(tmp_path)})
    with pytest.raises(UsageError, match="Unknown top-level keys"):
        load_config(paths, env={})


def test_invalid_toml_raises_usage_error(tmp_path: Path) -> None:
    config_dir = tmp_path / ".config" / "gog-cli"
    config_dir.mkdir(parents=True)
    (config_dir / "config.toml").write_text("not valid toml ][[\n")

    paths = resolve_app_paths({"HOME": str(tmp_path)})
    with pytest.raises(UsageError, match="Invalid config file"):
        load_config(paths, env={})


def test_invalid_downloader_raises_usage_error(tmp_path: Path) -> None:
    paths = resolve_app_paths({"HOME": str(tmp_path)})
    with pytest.raises(UsageError, match="Invalid downloader"):
        load_config(paths, env={"GOG_CLI_DOWNLOADER": "wget"})


def test_invalid_format_raises_usage_error(tmp_path: Path) -> None:
    paths = resolve_app_paths({"HOME": str(tmp_path)})
    with pytest.raises(UsageError, match="Invalid format"):
        load_config(paths, env={"GOG_CLI_FORMAT": "yaml"})


def test_invalid_bool_env_var_raises_usage_error(tmp_path: Path) -> None:
    paths = resolve_app_paths({"HOME": str(tmp_path)})
    with pytest.raises(UsageError, match="Invalid boolean"):
        load_config(paths, env={"GOG_CLI_INTERACTIVE": "maybe"})


@pytest.mark.parametrize("value", ["1", "true", "yes", "True", "YES"])
def test_bool_env_true_variants(tmp_path: Path, value: str) -> None:
    paths = resolve_app_paths({"HOME": str(tmp_path)})
    config = load_config(paths, env={"GOG_CLI_INTERACTIVE": value})
    assert config.interactive is True


@pytest.mark.parametrize("value", ["0", "false", "no", "False", "NO"])
def test_bool_env_false_variants(tmp_path: Path, value: str) -> None:
    paths = resolve_app_paths({"HOME": str(tmp_path)})
    config = load_config(paths, env={"GOG_CLI_INTERACTIVE": value})
    assert config.interactive is False
