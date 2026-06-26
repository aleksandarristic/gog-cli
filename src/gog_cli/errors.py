"""Exit codes and application exception hierarchy."""

from __future__ import annotations

from enum import IntEnum


class ExitCode(IntEnum):
    SUCCESS = 0
    FAILURE = 1
    USAGE = 2
    AUTH = 3
    NETWORK = 4
    VERIFICATION = 5
    FILESYSTEM = 6
    PARSER = 7


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
