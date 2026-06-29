"""Exit codes and application exception hierarchy."""

from __future__ import annotations

from enum import IntEnum


# TASK-0044 plan/dry-run mapping keeps the TASK-0013 values stable:
# success=0, generated plan but execution would fail=1, invalid args=2,
# auth required=3, target/disk filesystem failures=6, parser failures=7.
# Missing local library/download cache is a refresh-required state and uses 8
# instead of renumbering the existing AUTH=3 code to match the newer plan spec.
class ExitCode(IntEnum):
    SUCCESS = 0
    FAILURE = 1
    USAGE = 2
    AUTH = 3
    NETWORK = 4
    VERIFICATION = 5
    FILESYSTEM = 6
    PARSER = 7
    CACHE = 8


class GogError(Exception):
    exit_code: ExitCode = ExitCode.FAILURE


class UsageError(GogError):
    exit_code = ExitCode.USAGE


class AuthError(GogError):
    exit_code = ExitCode.AUTH


class NetworkError(GogError):
    exit_code = ExitCode.NETWORK


class VerificationError(GogError):
    exit_code = ExitCode.VERIFICATION


class FilesystemError(GogError):
    exit_code = ExitCode.FILESYSTEM


class ParserError(GogError):
    exit_code = ExitCode.PARSER


class CacheError(GogError):
    exit_code = ExitCode.CACHE
