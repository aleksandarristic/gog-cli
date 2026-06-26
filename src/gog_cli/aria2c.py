"""Delegated downloader via aria2c."""

from __future__ import annotations

import contextlib
import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from gog_cli.downloader import DownloadResult, _md5_file
from gog_cli.errors import UsageError


def find_aria2c() -> Path | None:
    """Return path to aria2c binary or None if not found."""
    found = shutil.which("aria2c")
    return Path(found) if found else None


def check_aria2c(required: bool = True) -> Path:
    """Return aria2c path or raise UsageError if not found and required=True."""
    path = find_aria2c()
    if path is None and required:
        raise UsageError(
            "aria2c is not installed or not on PATH. Install it or use --downloader direct."
        )
    if path is None:
        raise UsageError("aria2c not found")
    return path


def download_via_aria2c(
    url: str,
    dest: Path,
    *,
    headers: dict[str, str] | None = None,
    expected_size: int | None = None,
    expected_md5: str | None = None,
    aria2c_path: Path | None = None,
    logger: logging.Logger | None = None,
) -> DownloadResult:
    log = logger or logging.getLogger(__name__)

    aria2_control = Path(str(dest) + ".aria2")
    if dest.exists() and not aria2_control.exists():
        return DownloadResult(status="skipped", path=dest, expected_size=expected_size)

    binary = aria2c_path or check_aria2c()
    dest.parent.mkdir(parents=True, exist_ok=True)

    # Write URL to a temp file so it doesn't appear in process listings.
    # The file is written with restrictive permissions before content is added.
    fd, input_file = tempfile.mkstemp(prefix="gog-aria2c-", suffix=".txt")
    try:
        os.chmod(input_file, 0o600)
        with os.fdopen(fd, "w") as fh:
            fh.write(url + "\n")

        cmd = [
            str(binary),
            "--input-file",
            input_file,
            "--dir",
            str(dest.parent),
            "--out",
            dest.name,
            "--auto-file-renaming=false",
            "--continue=true",
            "--split=4",
            "--max-connection-per-server=4",
        ]

        # Headers appear in process args — unavoidable with aria2c's CLI interface.
        if headers:
            for key, value in headers.items():
                cmd += ["--header", f"{key}: {value}"]

        log.debug("running aria2c for %s", dest.name)
        result = subprocess.run(  # noqa: S603
            cmd,
        )

        if result.returncode != 0:
            return DownloadResult(
                status="failed",
                expected_size=expected_size,
                failure_code="aria2c_error",
                failure_message=f"aria2c exited with code {result.returncode}",
            )

    finally:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(input_file)

    if not dest.exists():
        return DownloadResult(
            status="failed",
            expected_size=expected_size,
            failure_code="aria2c_error",
            failure_message="aria2c reported success but output file is missing",
        )

    actual_size = dest.stat().st_size

    if expected_size is not None and actual_size != expected_size:
        return DownloadResult(
            status="failed",
            path=dest,
            expected_size=expected_size,
            failure_code="size_mismatch",
            failure_message=f"Expected {expected_size} bytes, got {actual_size}",
        )

    checksum_verified = False
    if expected_md5 is not None:
        actual_md5 = _md5_file(dest)
        if actual_md5 != expected_md5.lower():
            return DownloadResult(
                status="failed",
                path=dest,
                expected_size=expected_size,
                failure_code="checksum_mismatch",
                failure_message="MD5 checksum did not match expected value",
            )
        checksum_verified = True

    return DownloadResult(
        status="verified",
        path=dest,
        bytes_downloaded=actual_size,
        expected_size=expected_size,
        checksum_verified=checksum_verified,
    )
