"""Machine-readable output contracts and status vocabulary."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from enum import StrEnum
from types import TracebackType
from typing import Any

from gog_cli.state import utc_timestamp

# ---------------------------------------------------------------------------
# Format enum
# ---------------------------------------------------------------------------


class OutputFormat(StrEnum):
    HUMAN = "human"
    JSON = "json"


# ---------------------------------------------------------------------------
# JSON envelope
# ---------------------------------------------------------------------------


@dataclass
class JsonEnvelope:
    command: str
    data: Any
    schema_version: int = 1
    generated_at: str = ""

    def __post_init__(self) -> None:
        if not self.generated_at:
            self.generated_at = utc_timestamp()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "command": self.command,
            "generated_at": self.generated_at,
            "data": self.data,
        }


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------


def print_json(envelope: JsonEnvelope, *, file: Any = None) -> None:
    if file is None:
        file = sys.stdout
    print(json.dumps(envelope.to_dict(), indent=2), file=file)


def print_human(lines: list[str], *, file: Any = None) -> None:
    if file is None:
        file = sys.stdout
    for line in lines:
        print(line, file=file)


def print_error(message: str, *, file: Any = None) -> None:
    if file is None:
        file = sys.stderr
    print(message, file=file)


class TransientStatus:
    """Show a temporary one-line status message on TTY stderr."""

    def __init__(self, message: str, *, file: Any = None) -> None:
        self.message = message
        self.file = file if file is not None else sys.stderr
        self.enabled = bool(getattr(self.file, "isatty", lambda: False)())
        self._width = 0

    def __enter__(self) -> TransientStatus:
        if self.enabled:
            text = f"{self.message} "
            self._width = len(text)
            self.file.write(text)
            self.file.flush()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self.enabled:
            self.file.write("\r" + (" " * self._width) + "\r")
            self.file.flush()


# ---------------------------------------------------------------------------
# Status vocabulary constants
# ---------------------------------------------------------------------------

# Cache status (TASK-0006)
CACHE_FRESH = "fresh"
CACHE_STALE = "stale"
CACHE_MISSING = "missing"
CACHE_CORRUPT = "corrupt"
CACHE_UNSUPPORTED = "unsupported"

# Game/backup status (TASK-0002)
GAME_CURRENT = "current"
GAME_PARTIAL = "partial"
GAME_STALE = "stale"
GAME_MISSING = "missing"
GAME_UNVERIFIED = "unverified"
GAME_ERROR = "error"

# File status (TASK-0002)
FILE_PLANNED = "planned"
FILE_DOWNLOADING = "downloading"
FILE_PARTIAL = "partial"
FILE_DOWNLOADED = "downloaded"
FILE_VERIFIED = "verified"
FILE_FAILED = "failed"
FILE_STALE = "stale"
FILE_MISSING = "missing"
