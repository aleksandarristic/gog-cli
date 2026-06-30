"""Configuration loading with TOML file, env vars, and built-in defaults."""

from __future__ import annotations

import os
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from gog_cli.errors import UsageError
from gog_cli.state import AppPaths

_VALID_DOWNLOADERS = frozenset({"direct", "aria2c"})
_VALID_FORMATS = frozenset({"human", "json"})
_VALID_ARIA2C_POLICIES = frozenset({"auto", "conservative", "aggressive"})
_KNOWN_DEFAULTS_KEYS = frozenset(
    {
        "aria2c_policy",
        "destination",
        "downloader",
        "file_roles",
        "format",
        "interactive",
        "languages",
        "platforms",
    }
)


@dataclass
class Config:
    destination: Path | None = None
    downloader: str = "direct"
    aria2c_policy: str = "auto"
    platforms: list[str] = field(default_factory=list)
    languages: list[str] = field(default_factory=list)
    file_roles: list[str] = field(default_factory=list)
    output_format: str = "human"
    interactive: bool = True


def load_config(paths: AppPaths, env: Mapping[str, str] | None = None) -> Config:
    config = Config()
    _apply_toml(config, paths.config_file)
    _apply_env(config, os.environ if env is None else env)
    _validate(config)
    return config


def _apply_toml(config: Config, path: Path) -> None:
    try:
        with path.open("rb") as fh:
            data = tomllib.load(fh)
    except FileNotFoundError:
        return
    except tomllib.TOMLDecodeError as exc:
        raise UsageError(f"Invalid config file {path}: {exc}") from exc

    unknown_top = set(data) - {"defaults"}
    if unknown_top:
        raise UsageError(f"Unknown top-level keys in {path}: {', '.join(sorted(unknown_top))}")

    defaults = data.get("defaults", {})
    if not isinstance(defaults, dict):
        raise UsageError(f"[defaults] in {path} must be a TOML table")

    unknown = set(defaults) - _KNOWN_DEFAULTS_KEYS
    if unknown:
        raise UsageError(f"Unknown config keys in {path}: {', '.join(sorted(unknown))}")

    if "destination" in defaults:
        config.destination = Path(str(defaults["destination"]))
    if "downloader" in defaults:
        config.downloader = str(defaults["downloader"])
    if "aria2c_policy" in defaults:
        config.aria2c_policy = str(defaults["aria2c_policy"])
    if "platforms" in defaults:
        config.platforms = [str(v) for v in defaults["platforms"]]
    if "languages" in defaults:
        config.languages = [str(v) for v in defaults["languages"]]
    if "file_roles" in defaults:
        config.file_roles = [str(v) for v in defaults["file_roles"]]
    if "format" in defaults:
        config.output_format = str(defaults["format"])
    if "interactive" in defaults:
        config.interactive = bool(defaults["interactive"])


def _apply_env(config: Config, env: Mapping[str, str]) -> None:
    if dest := env.get("GOG_CLI_DESTINATION"):
        config.destination = Path(dest)
    if downloader := env.get("GOG_CLI_DOWNLOADER"):
        config.downloader = downloader
    if aria2c_policy := env.get("GOG_CLI_ARIA2C_POLICY"):
        config.aria2c_policy = aria2c_policy
    if platforms := env.get("GOG_CLI_PLATFORMS"):
        config.platforms = [p.strip() for p in platforms.split(",") if p.strip()]
    if languages := env.get("GOG_CLI_LANGUAGES"):
        config.languages = [la.strip() for la in languages.split(",") if la.strip()]
    if roles := env.get("GOG_CLI_FILE_ROLES"):
        config.file_roles = [r.strip() for r in roles.split(",") if r.strip()]
    if fmt := env.get("GOG_CLI_FORMAT"):
        config.output_format = fmt
    if interactive_val := env.get("GOG_CLI_INTERACTIVE"):
        config.interactive = _parse_bool(interactive_val, "GOG_CLI_INTERACTIVE")


def _parse_bool(value: str, name: str) -> bool:
    if value.lower() in ("1", "true", "yes"):
        return True
    if value.lower() in ("0", "false", "no"):
        return False
    raise UsageError(f"Invalid boolean value for {name}: {value!r}")


def _validate(config: Config) -> None:
    if config.downloader not in _VALID_DOWNLOADERS:
        raise UsageError(
            f"Invalid downloader {config.downloader!r}."
            f" Must be one of: {', '.join(sorted(_VALID_DOWNLOADERS))}"
        )
    if config.output_format not in _VALID_FORMATS:
        raise UsageError(
            f"Invalid format {config.output_format!r}."
            f" Must be one of: {', '.join(sorted(_VALID_FORMATS))}"
        )
    if config.aria2c_policy not in _VALID_ARIA2C_POLICIES:
        raise UsageError(
            f"Invalid aria2c_policy {config.aria2c_policy!r}."
            f" Must be one of: {', '.join(sorted(_VALID_ARIA2C_POLICIES))}"
        )
