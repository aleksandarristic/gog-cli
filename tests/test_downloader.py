"""Tests for the built-in direct downloader."""

from __future__ import annotations

import hashlib

import responses

from gog_cli.downloader import Downloader, fetch_checksum_xml

_URL = "https://cdn.example.com/game/installer.exe"
_CHECKSUM_URL = "https://cdn.example.com/game/installer.exe.xml"
_CONTENT = b"A" * (2 * 1024 * 1024)  # 2 MiB of data
_MD5 = hashlib.md5(_CONTENT).hexdigest()  # noqa: S324
_SIZE = len(_CONTENT)

_CHECKSUM_XML = f"""<?xml version="1.0" encoding="UTF-8"?>
<file name="installer.exe" md5="{_MD5}" total_size="{_SIZE}">
  <chunk method="md5" from="0" to="{_SIZE - 1}">{_MD5}</chunk>
</file>"""


def make_downloader() -> Downloader:
    import requests

    return Downloader(requests.Session())


@responses.activate
def test_fresh_download_size_and_md5_verified(tmp_path) -> None:
    responses.get(_URL, body=_CONTENT, status=200)

    dest = tmp_path / "installer.exe"
    result = make_downloader().download(_URL, dest, expected_size=_SIZE, expected_md5=_MD5)

    assert result.status == "verified"
    assert result.path == dest
    assert dest.exists()
    assert result.checksum_verified is True
    assert not (tmp_path / ".installer.exe.part").exists()


@responses.activate
def test_resume_with_206(tmp_path) -> None:
    partial = _CONTENT[: _SIZE // 2]
    remainder = _CONTENT[_SIZE // 2 :]

    dest = tmp_path / "installer.exe"
    temp = tmp_path / ".installer.exe.part"
    temp.write_bytes(partial)

    responses.get(_URL, body=remainder, status=206)

    result = make_downloader().download(_URL, dest, expected_size=_SIZE, expected_md5=_MD5)

    assert result.status == "verified"
    assert dest.read_bytes() == _CONTENT


@responses.activate
def test_server_ignores_range_falls_back_to_full_download(tmp_path) -> None:
    partial = _CONTENT[:100]
    dest = tmp_path / "installer.exe"
    temp = tmp_path / ".installer.exe.part"
    temp.write_bytes(partial)

    # Server returns 200 even though we sent a Range header
    responses.get(_URL, body=_CONTENT, status=200)

    result = make_downloader().download(_URL, dest, expected_size=_SIZE, expected_md5=_MD5)

    assert result.status == "verified"
    assert dest.read_bytes() == _CONTENT


@responses.activate
def test_oversized_temp_deleted_before_fresh_download(tmp_path) -> None:
    dest = tmp_path / "installer.exe"
    temp = tmp_path / ".installer.exe.part"
    temp.write_bytes(_CONTENT + b"X" * 100)  # larger than expected

    responses.get(_URL, body=_CONTENT, status=200)

    result = make_downloader().download(_URL, dest, expected_size=_SIZE, expected_md5=_MD5)

    assert result.status == "verified"
    assert dest.read_bytes() == _CONTENT


def test_dest_already_exists_returns_skipped(tmp_path) -> None:
    dest = tmp_path / "installer.exe"
    dest.write_bytes(_CONTENT)

    result = make_downloader().download(_URL, dest, expected_size=_SIZE)

    assert result.status == "skipped"
    assert result.path == dest


@responses.activate
def test_size_mismatch_returns_failed(tmp_path) -> None:
    responses.get(_URL, body=_CONTENT, status=200)

    dest = tmp_path / "installer.exe"
    result = make_downloader().download(_URL, dest, expected_size=_SIZE + 1)

    assert result.status == "failed"
    assert result.failure_code == "size_mismatch"
    assert not dest.exists()


@responses.activate
def test_md5_mismatch_returns_failed(tmp_path) -> None:
    responses.get(_URL, body=_CONTENT, status=200)

    dest = tmp_path / "installer.exe"
    result = make_downloader().download(_URL, dest, expected_size=_SIZE, expected_md5="0" * 32)

    assert result.status == "failed"
    assert result.failure_code == "checksum_mismatch"
    assert not dest.exists()


@responses.activate
def test_network_error_before_any_bytes_returns_failed(tmp_path) -> None:
    import requests as req_lib

    responses.get(_URL, body=req_lib.exceptions.ConnectionError("connection refused"))

    dest = tmp_path / "installer.exe"
    result = make_downloader().download(_URL, dest)

    assert result.status == "failed"
    assert result.failure_code == "network_error"


@responses.activate
def test_network_error_after_partial_bytes_returns_partial(tmp_path) -> None:
    import requests as req_lib

    # Write a partial file to simulate a prior interrupted download
    dest = tmp_path / "installer.exe"
    temp = tmp_path / ".installer.exe.part"
    temp.write_bytes(_CONTENT[:500])

    # Range request fails
    responses.get(_URL, body=req_lib.exceptions.ConnectionError("connection reset"))

    result = make_downloader().download(_URL, dest, expected_size=_SIZE, resume=True)

    assert result.status == "partial"
    assert result.failure_code == "network_error"
    assert result.temp_path == temp


@responses.activate
def test_fetch_checksum_xml_happy_path() -> None:
    import requests

    responses.get(_CHECKSUM_URL, body=_CHECKSUM_XML, status=200)

    session = requests.Session()
    md5, size = fetch_checksum_xml(session, _CHECKSUM_URL)

    assert md5 == _MD5
    assert size == _SIZE


@responses.activate
def test_fetch_checksum_xml_bad_xml_returns_none() -> None:
    import requests

    responses.get(_CHECKSUM_URL, body="not xml at all <<<", status=200)

    session = requests.Session()
    md5, size = fetch_checksum_xml(session, _CHECKSUM_URL)

    assert md5 is None
    assert size is None


@responses.activate
def test_fetch_checksum_xml_network_error_returns_none() -> None:
    import requests

    responses.get(_CHECKSUM_URL, body=Exception("timeout"))

    session = requests.Session()
    md5, size = fetch_checksum_xml(session, _CHECKSUM_URL)

    assert md5 is None
    assert size is None
