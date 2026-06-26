"""Tests for machine-readable output contracts."""

from __future__ import annotations

import io
import json

from gog_cli.output import (
    CACHE_CORRUPT,
    CACHE_FRESH,
    CACHE_MISSING,
    CACHE_STALE,
    CACHE_UNSUPPORTED,
    FILE_DOWNLOADED,
    FILE_DOWNLOADING,
    FILE_FAILED,
    FILE_MISSING,
    FILE_PARTIAL,
    FILE_PLANNED,
    FILE_STALE,
    FILE_VERIFIED,
    GAME_CURRENT,
    GAME_ERROR,
    GAME_MISSING,
    GAME_PARTIAL,
    GAME_STALE,
    GAME_UNVERIFIED,
    JsonEnvelope,
    OutputFormat,
    print_error,
    print_human,
    print_json,
)


def test_json_envelope_to_dict_has_required_fields() -> None:
    env = JsonEnvelope(command="list purchased", data={"games": []})
    d = env.to_dict()

    assert d["schema_version"] == 1
    assert d["command"] == "list purchased"
    assert "generated_at" in d
    assert d["generated_at"].endswith("Z")
    assert d["data"] == {"games": []}


def test_json_envelope_schema_version_default_is_1() -> None:
    env = JsonEnvelope(command="test", data=None)
    assert env.to_dict()["schema_version"] == 1


def test_json_envelope_custom_schema_version() -> None:
    env = JsonEnvelope(command="test", data=None, schema_version=2)
    assert env.to_dict()["schema_version"] == 2


def test_print_json_writes_valid_json_to_stdout() -> None:
    buf = io.StringIO()
    env = JsonEnvelope(command="list purchased", data={"games": []})
    print_json(env, file=buf)

    parsed = json.loads(buf.getvalue())
    assert parsed["schema_version"] == 1
    assert parsed["command"] == "list purchased"
    assert "generated_at" in parsed
    assert parsed["data"] == {"games": []}


def test_print_json_output_is_indented() -> None:
    buf = io.StringIO()
    env = JsonEnvelope(command="test", data={"key": "value"})
    print_json(env, file=buf)
    # Indented JSON has newlines inside
    assert "\n" in buf.getvalue()


def test_print_human_writes_each_line() -> None:
    buf = io.StringIO()
    print_human(["line one", "line two"], file=buf)
    assert buf.getvalue() == "line one\nline two\n"


def test_print_human_empty_list() -> None:
    buf = io.StringIO()
    print_human([], file=buf)
    assert buf.getvalue() == ""


def test_print_error_writes_to_stderr_not_stdout() -> None:
    err_buf = io.StringIO()
    print_error("something went wrong", file=err_buf)
    assert "something went wrong" in err_buf.getvalue()


def test_output_format_values() -> None:
    assert OutputFormat.HUMAN == "human"
    assert OutputFormat.JSON == "json"


def test_cache_status_constants_are_non_empty_strings() -> None:
    constants = [CACHE_FRESH, CACHE_STALE, CACHE_MISSING, CACHE_CORRUPT, CACHE_UNSUPPORTED]
    assert all(isinstance(c, str) and c for c in constants)
    assert len(set(constants)) == len(constants), "cache status constants must be unique"


def test_game_status_constants_are_non_empty_strings() -> None:
    constants = [GAME_CURRENT, GAME_PARTIAL, GAME_STALE, GAME_MISSING, GAME_UNVERIFIED, GAME_ERROR]
    assert all(isinstance(c, str) and c for c in constants)
    assert len(set(constants)) == len(constants), "game status constants must be unique"


def test_file_status_constants_are_non_empty_strings() -> None:
    constants = [
        FILE_PLANNED,
        FILE_DOWNLOADING,
        FILE_PARTIAL,
        FILE_DOWNLOADED,
        FILE_VERIFIED,
        FILE_FAILED,
        FILE_STALE,
        FILE_MISSING,
    ]
    assert all(isinstance(c, str) and c for c in constants)
    assert len(set(constants)) == len(constants), "file status constants must be unique"
