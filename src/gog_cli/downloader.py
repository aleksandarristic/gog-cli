"""Built-in direct downloader with resume and verification support."""

from __future__ import annotations

import hashlib
import logging
import os
import xml.etree.ElementTree as ET
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import requests

_CHUNK_SIZE = 1024 * 1024  # 1 MiB
_LOG_INTERVAL = 10 * 1024 * 1024  # log every 10 MiB

DownloadStatus = Literal["verified", "downloaded", "partial", "failed", "skipped"]


@dataclass
class DownloadResult:
    status: DownloadStatus
    path: Path | None = None
    temp_path: Path | None = None
    bytes_downloaded: int = 0
    expected_size: int | None = None
    checksum_verified: bool = False
    failure_code: str | None = None
    failure_message: str | None = None


class Downloader:
    def __init__(
        self,
        session: requests.Session,
        logger: logging.Logger | None = None,
    ) -> None:
        self._session = session
        self._log = logger or logging.getLogger(__name__)

    def download(
        self,
        url: str,
        dest: Path,
        *,
        expected_size: int | None = None,
        expected_md5: str | None = None,
        resume: bool = True,
        progress_callback: Callable[[int, int | None], None] | None = None,
    ) -> DownloadResult:
        if dest.exists():
            return DownloadResult(
                status="skipped",
                path=dest,
                expected_size=expected_size,
            )

        temp_path = dest.parent / f".{dest.name}.part"
        dest.parent.mkdir(parents=True, exist_ok=True)

        # Handle oversized partial file
        if (
            temp_path.exists()
            and expected_size is not None
            and temp_path.stat().st_size > expected_size
        ):
            temp_path.unlink()

        # Determine resume offset
        offset = 0
        if resume and temp_path.exists():
            offset = temp_path.stat().st_size
            if expected_size is not None and offset >= expected_size:
                offset = 0
                temp_path.unlink()

        headers: dict[str, str] = {}
        if offset > 0:
            headers["Range"] = f"bytes={offset}-"

        try:
            response = self._session.get(url, headers=headers, stream=True, timeout=30)
            response.raise_for_status()
        except requests.RequestException as exc:
            existing_bytes = temp_path.stat().st_size if temp_path.exists() else 0
            return DownloadResult(
                status="partial" if existing_bytes > 0 else "failed",
                temp_path=temp_path if existing_bytes > 0 else None,
                bytes_downloaded=0,
                expected_size=expected_size,
                failure_code="network_error",
                failure_message=f"Request failed: {type(exc).__name__}",
            )

        # If we requested a range but got 200, restart from scratch
        if offset > 0 and response.status_code == 200:  # noqa: PLR2004
            offset = 0
            if temp_path.exists():
                temp_path.unlink()

        write_mode = "ab" if offset > 0 else "wb"
        bytes_downloaded = 0
        last_logged = 0

        try:
            with temp_path.open(write_mode) as fh:
                for chunk in response.iter_content(chunk_size=_CHUNK_SIZE):
                    if chunk:
                        fh.write(chunk)
                        bytes_downloaded += len(chunk)
                        if progress_callback is not None:
                            progress_callback(offset + bytes_downloaded, expected_size)
                        if bytes_downloaded - last_logged >= _LOG_INTERVAL:
                            self._log.debug(
                                "downloaded %d MiB", (offset + bytes_downloaded) // (1024 * 1024)
                            )
                            last_logged = bytes_downloaded
        except requests.RequestException as exc:
            existing_bytes = temp_path.stat().st_size if temp_path.exists() else 0
            return DownloadResult(
                status="partial" if existing_bytes > 0 else "failed",
                temp_path=temp_path if existing_bytes > 0 else None,
                bytes_downloaded=bytes_downloaded,
                expected_size=expected_size,
                failure_code="network_error",
                failure_message=f"Transfer interrupted: {type(exc).__name__}",
            )

        total_bytes = offset + bytes_downloaded
        self._log.debug("download complete: %d bytes", total_bytes)

        # Size verification
        if expected_size is not None:
            actual_size = temp_path.stat().st_size
            if actual_size != expected_size:
                return DownloadResult(
                    status="failed",
                    temp_path=temp_path,
                    bytes_downloaded=bytes_downloaded,
                    expected_size=expected_size,
                    failure_code="size_mismatch",
                    failure_message=(f"Expected {expected_size} bytes, got {actual_size}"),
                )

        # MD5 verification
        if expected_md5 is not None:
            actual_md5 = _md5_file(temp_path)
            if actual_md5 != expected_md5.lower():
                return DownloadResult(
                    status="failed",
                    temp_path=temp_path,
                    bytes_downloaded=bytes_downloaded,
                    expected_size=expected_size,
                    failure_code="checksum_mismatch",
                    failure_message="MD5 checksum did not match expected value",
                )

        os.replace(temp_path, dest)
        return DownloadResult(
            status="verified",
            path=dest,
            bytes_downloaded=bytes_downloaded,
            expected_size=expected_size,
            checksum_verified=expected_md5 is not None,
        )


def fetch_checksum_xml(
    session: requests.Session,
    checksum_url: str,
) -> tuple[str | None, int | None]:
    """Fetch GOG checksum XML and return (md5, total_size), or (None, None) on failure."""
    try:
        response = session.get(checksum_url, timeout=15)
        response.raise_for_status()
        root = ET.fromstring(response.text)  # noqa: S314
        md5 = root.get("md5")
        size_str = root.get("total_size")
        total_size = int(size_str) if size_str is not None else None
        return (md5 or None, total_size)
    except Exception:  # noqa: BLE001
        return (None, None)


def _md5_file(path: Path) -> str:
    h = hashlib.md5()  # noqa: S324
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(_CHUNK_SIZE), b""):
            h.update(chunk)
    return h.hexdigest()


# Expose field for convenience
__all__ = ["Downloader", "DownloadResult", "DownloadStatus", "fetch_checksum_xml"]
