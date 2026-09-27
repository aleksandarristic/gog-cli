from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from gog_cli.aria2c import check_aria2c, default_downloader, download_via_aria2c, find_aria2c
from gog_cli.errors import UsageError

_MIB = 1024 * 1024
_GIB = 1024 * _MIB

# --- find_aria2c / check_aria2c ---


def test_find_aria2c_returns_path_when_found(tmp_path: Path) -> None:
    fake = tmp_path / "aria2c"
    fake.write_text("")
    with patch("shutil.which", return_value=str(fake)):
        result = find_aria2c()
    assert result == fake


def test_find_aria2c_returns_none_when_not_found() -> None:
    with patch("shutil.which", return_value=None):
        result = find_aria2c()
    assert result is None


def test_check_aria2c_raises_when_missing() -> None:
    with patch("shutil.which", return_value=None), pytest.raises(UsageError, match="aria2c"):
        check_aria2c()


def test_check_aria2c_returns_path_when_found(tmp_path: Path) -> None:
    fake = tmp_path / "aria2c"
    fake.write_text("")
    with patch("shutil.which", return_value=str(fake)):
        result = check_aria2c()
    assert result == fake


def test_default_downloader_is_aria2c_when_found() -> None:
    with patch("shutil.which", return_value="/usr/bin/aria2c"):
        assert default_downloader() == "aria2c"


def test_default_downloader_is_direct_when_not_found() -> None:
    with patch("shutil.which", return_value=None):
        assert default_downloader() == "direct"


# --- download_via_aria2c ---


def _aria2c_out_option(cmd: list[str]) -> str:
    """Return the per-URI out= option from the input file of an aria2c command line."""
    input_file = Path(cmd[cmd.index("--input-file") + 1])
    for line in input_file.read_text().splitlines():
        if line.startswith("  out="):
            return line.removeprefix("  out=")
    raise AssertionError("aria2c input file has no out= option")


def _aria2c_output(cmd: list[str]) -> Path:
    """Return the file an aria2c command line writes to."""
    return Path(cmd[cmd.index("--dir") + 1]) / _aria2c_out_option(cmd)


def _make_aria2c_success(dest: Path, content: bytes = b"data") -> MagicMock:
    """Return a mock subprocess.run that writes content where aria2c is told to."""

    def side_effect(cmd, **kwargs):  # noqa: ANN001
        output = _aria2c_output(cmd)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(content)
        return MagicMock(returncode=0, stdout="", stderr="")

    return MagicMock(side_effect=side_effect)


def test_download_success(tmp_path: Path) -> None:
    dest = tmp_path / "games" / "witcher_3" / "installers" / "setup.exe"
    content = b"installer content"
    mock_run = _make_aria2c_success(dest, content)

    with patch("subprocess.run", mock_run):
        result = download_via_aria2c(
            url="https://cdn.example.com/setup.exe",
            dest=dest,
            aria2c_path=Path("/usr/bin/aria2c"),
            expected_size=len(content),
        )

    assert result.status == "downloaded"
    assert result.path == dest
    assert result.bytes_downloaded == len(content)


def test_download_quiet_suppresses_subprocess_output(tmp_path: Path) -> None:
    dest = tmp_path / "setup.exe"
    mock_run = _make_aria2c_success(dest)

    with patch("subprocess.run", mock_run):
        result = download_via_aria2c(
            url="https://cdn.example.com/setup.exe",
            dest=dest,
            aria2c_path=Path("/usr/bin/aria2c"),
            quiet=True,
        )

    assert result.status == "downloaded"
    assert mock_run.call_args.kwargs == {
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }


def test_download_skips_existing(tmp_path: Path) -> None:
    dest = tmp_path / "setup.exe"
    content = b"existing"
    dest.write_bytes(content)
    md5 = hashlib.md5(content).hexdigest()  # noqa: S324

    with patch("subprocess.run") as mock_run:
        result = download_via_aria2c(
            url="https://cdn.example.com/setup.exe",
            dest=dest,
            aria2c_path=Path("/usr/bin/aria2c"),
            expected_md5=md5,
        )

    mock_run.assert_not_called()
    assert result.status == "skipped"
    assert result.checksum_verified is True


def test_download_redownloads_when_existing_size_mismatches(tmp_path: Path) -> None:
    dest = tmp_path / "setup.exe"
    dest.write_bytes(b"stale leftover from a colliding path")
    content = b"real content"
    mock_run = _make_aria2c_success(dest, content)

    with patch("subprocess.run", mock_run):
        result = download_via_aria2c(
            url="https://cdn.example.com/setup.exe",
            dest=dest,
            aria2c_path=Path("/usr/bin/aria2c"),
            expected_size=len(content),
        )

    mock_run.assert_called_once()
    assert result.status == "downloaded"
    assert dest.read_bytes() == content
    assert not (tmp_path / ".setup.exe.part").exists()


def test_download_redownloads_same_size_file_with_wrong_checksum(tmp_path: Path) -> None:
    dest = tmp_path / "setup.exe"
    content = b"real content"
    dest.write_bytes(b"stale bytes!")
    md5 = hashlib.md5(content).hexdigest()  # noqa: S324
    mock_run = _make_aria2c_success(dest, content)

    with patch("subprocess.run", mock_run):
        result = download_via_aria2c(
            url="https://cdn.example.com/setup.exe",
            dest=dest,
            aria2c_path=Path("/usr/bin/aria2c"),
            expected_size=len(content),
            expected_md5=md5,
        )

    mock_run.assert_called_once()
    assert result.status == "verified"
    assert dest.read_bytes() == content


def test_failed_replacement_preserves_existing_file(tmp_path: Path) -> None:
    dest = tmp_path / "setup.exe"
    original = b"previous working installer"
    dest.write_bytes(original)
    mock_run = MagicMock(return_value=MagicMock(returncode=1))

    with patch("subprocess.run", mock_run):
        result = download_via_aria2c(
            url="https://cdn.example.com/setup.exe",
            dest=dest,
            aria2c_path=Path("/usr/bin/aria2c"),
            expected_size=999,
        )

    assert result.status == "failed"
    assert dest.read_bytes() == original


def test_interrupted_download_stays_out_of_final_path(tmp_path: Path) -> None:
    dest = tmp_path / "setup.exe"

    def side_effect(cmd, **kwargs):  # noqa: ANN001
        # aria2c preallocates the full size and records its progress
        output = _aria2c_output(cmd)
        output.write_bytes(b"\0" * 999)
        Path(str(output) + ".aria2").write_bytes(b"progress")
        return MagicMock(returncode=7)

    with patch("subprocess.run", MagicMock(side_effect=side_effect)):
        result = download_via_aria2c(
            url="https://cdn.example.com/setup.exe",
            dest=dest,
            aria2c_path=Path("/usr/bin/aria2c"),
            expected_size=999,
        )

    assert result.status == "failed"
    assert not dest.exists()
    assert result.temp_path == tmp_path / ".setup.exe.part"


def test_download_resumes_part_file_with_control_file(tmp_path: Path) -> None:
    dest = tmp_path / "setup.exe"
    content = b"real content"
    part = tmp_path / ".setup.exe.part"
    partial = b"real" + b"\0" * (len(content) - 4)
    part.write_bytes(partial)
    Path(str(part) + ".aria2").write_bytes(b"progress")
    captured: list[tuple[list[str], str, bytes]] = []

    def side_effect(cmd, **kwargs):  # noqa: ANN001
        captured.append((cmd, _aria2c_out_option(cmd), part.read_bytes()))
        _aria2c_output(cmd).write_bytes(content)
        return MagicMock(returncode=0)

    with patch("subprocess.run", MagicMock(side_effect=side_effect)):
        result = download_via_aria2c(
            url="https://cdn.example.com/setup.exe",
            dest=dest,
            aria2c_path=Path("/usr/bin/aria2c"),
            expected_size=len(content),
        )

    [(cmd, out, part_when_started)] = captured
    # aria2c ignores a command-line --out for --input-file URIs
    assert "--out" not in cmd
    assert out == ".setup.exe.part"
    assert "--continue=true" in cmd
    assert part_when_started == partial
    assert result.status == "downloaded"
    assert dest.read_bytes() == content
    assert not part.exists()


def test_download_discards_complete_part_file_without_control_file(tmp_path: Path) -> None:
    dest = tmp_path / "setup.exe"
    part = tmp_path / ".setup.exe.part"
    part.write_bytes(b"failed verification")
    seen_part: list[bool] = []

    def side_effect(cmd, **kwargs):  # noqa: ANN001
        seen_part.append(part.exists())
        _aria2c_output(cmd).write_bytes(b"fresh bytes here!!!")
        return MagicMock(returncode=0)

    with patch("subprocess.run", MagicMock(side_effect=side_effect)):
        download_via_aria2c(
            url="https://cdn.example.com/setup.exe",
            dest=dest,
            aria2c_path=Path("/usr/bin/aria2c"),
            expected_size=len(b"failed verification"),
        )

    assert seen_part == [False]


def test_download_refuses_file_name_that_would_inject_aria2c_options(tmp_path: Path) -> None:
    dest = tmp_path / "setup.exe\n  allow-overwrite=true"

    with patch("subprocess.run") as mock_run:
        result = download_via_aria2c(
            url="https://cdn.example.com/setup.exe",
            dest=dest,
            aria2c_path=Path("/usr/bin/aria2c"),
        )

    mock_run.assert_not_called()
    assert result.status == "failed"
    assert result.failure_code == "unsafe_filename"


def test_download_size_mismatch_accepted_when_not_strict(tmp_path: Path) -> None:
    dest = tmp_path / "bonus.pdf"
    content = b"bonus content"

    with patch("subprocess.run", _make_aria2c_success(dest, content)):
        result = download_via_aria2c(
            url="https://cdn.example.com/bonus.pdf",
            dest=dest,
            aria2c_path=Path("/usr/bin/aria2c"),
            expected_size=len(content) + 100,
            strict_size=False,
        )

    assert result.status == "downloaded"
    assert result.expected_size == len(content)


def test_download_fails_on_nonzero_exit(tmp_path: Path) -> None:
    dest = tmp_path / "setup.exe"
    mock_run = MagicMock(return_value=MagicMock(returncode=1, stdout="", stderr="Download failed"))

    with patch("subprocess.run", mock_run):
        result = download_via_aria2c(
            url="https://cdn.example.com/setup.exe",
            dest=dest,
            aria2c_path=Path("/usr/bin/aria2c"),
        )

    assert result.status == "failed"
    assert result.failure_code == "aria2c_error"


def test_download_fails_on_size_mismatch(tmp_path: Path) -> None:
    dest = tmp_path / "setup.exe"
    content = b"short"

    def side_effect(cmd, **kwargs):  # noqa: ANN001
        _aria2c_output(cmd).write_bytes(content)
        return MagicMock(returncode=0, stdout="", stderr="")

    with patch("subprocess.run", MagicMock(side_effect=side_effect)):
        result = download_via_aria2c(
            url="https://cdn.example.com/setup.exe",
            dest=dest,
            aria2c_path=Path("/usr/bin/aria2c"),
            expected_size=9999,
        )

    assert result.status == "failed"
    assert result.failure_code == "size_mismatch"


def test_download_fails_on_checksum_mismatch(tmp_path: Path) -> None:
    dest = tmp_path / "setup.exe"
    content = b"real content"

    def side_effect(cmd, **kwargs):  # noqa: ANN001
        _aria2c_output(cmd).write_bytes(content)
        return MagicMock(returncode=0, stdout="", stderr="")

    with patch("subprocess.run", MagicMock(side_effect=side_effect)):
        result = download_via_aria2c(
            url="https://cdn.example.com/setup.exe",
            dest=dest,
            aria2c_path=Path("/usr/bin/aria2c"),
            expected_size=len(content),
            expected_md5="wronghash",
        )

    assert result.status == "failed"
    assert result.failure_code == "checksum_mismatch"


def test_download_verifies_correct_checksum(tmp_path: Path) -> None:
    dest = tmp_path / "setup.exe"
    content = b"exact content"
    md5 = hashlib.md5(content).hexdigest()  # noqa: S324

    def side_effect(cmd, **kwargs):  # noqa: ANN001
        _aria2c_output(cmd).write_bytes(content)
        return MagicMock(returncode=0, stdout="", stderr="")

    with patch("subprocess.run", MagicMock(side_effect=side_effect)):
        result = download_via_aria2c(
            url="https://cdn.example.com/setup.exe",
            dest=dest,
            aria2c_path=Path("/usr/bin/aria2c"),
            expected_size=len(content),
            expected_md5=md5,
        )

    assert result.status == "verified"
    assert result.checksum_verified is True


def test_download_passes_auth_header(tmp_path: Path) -> None:
    dest = tmp_path / "setup.exe"
    content = b"data"
    captured_cmd: list[list[str]] = []

    def side_effect(cmd, **kwargs):  # noqa: ANN001
        captured_cmd.append(cmd)
        _aria2c_output(cmd).write_bytes(content)
        return MagicMock(returncode=0, stdout="", stderr="")

    with patch("subprocess.run", MagicMock(side_effect=side_effect)):
        download_via_aria2c(
            url="https://cdn.example.com/setup.exe",
            dest=dest,
            aria2c_path=Path("/usr/bin/aria2c"),
            headers={"Authorization": "Bearer token123"},
        )

    assert any("Authorization: Bearer token123" in arg for arg in captured_cmd[0])


@pytest.mark.parametrize(
    ("policy", "expected_size", "split", "connections"),
    [
        ("auto", None, "4", "4"),
        ("auto", 32 * _MIB, "1", "1"),
        ("auto", 128 * _MIB, "2", "2"),
        ("auto", 1 * _GIB, "4", "4"),
        ("auto", 4 * _GIB, "8", "8"),
        ("auto", 10 * _GIB, "16", "16"),
        ("conservative", None, "2", "2"),
        ("conservative", 128 * _MIB, "1", "1"),
        ("conservative", 1 * _GIB, "2", "2"),
        ("conservative", 4 * _GIB, "4", "4"),
        ("conservative", 10 * _GIB, "8", "8"),
        ("aggressive", None, "8", "8"),
        ("aggressive", 32 * _MIB, "2", "2"),
        ("aggressive", 128 * _MIB, "4", "4"),
        ("aggressive", 1 * _GIB, "8", "8"),
        ("aggressive", 4 * _GIB, "16", "16"),
    ],
)
def test_download_chooses_aria2c_options_by_size(
    tmp_path: Path,
    policy: str,
    expected_size: int | None,
    split: str,
    connections: str,
) -> None:
    dest = tmp_path / "setup.exe"
    captured_cmd: list[list[str]] = []

    def side_effect(cmd, **kwargs):  # noqa: ANN001
        captured_cmd.append(cmd)
        dest.write_bytes(b"data")
        return MagicMock(returncode=0, stdout="", stderr="")

    with patch("subprocess.run", MagicMock(side_effect=side_effect)):
        download_via_aria2c(
            url="https://cdn.example.com/setup.exe",
            dest=dest,
            aria2c_path=Path("/usr/bin/aria2c"),
            expected_size=expected_size,
            aria2c_policy=policy,
        )

    assert f"--split={split}" in captured_cmd[0]
    assert f"--max-connection-per-server={connections}" in captured_cmd[0]


def test_download_temp_file_cleaned_up(tmp_path: Path) -> None:
    dest = tmp_path / "setup.exe"
    content = b"data"
    temp_files_seen: list[str] = []

    original_mkstemp = __import__("tempfile").mkstemp

    def spy_mkstemp(**kwargs):  # noqa: ANN001
        fd, path = original_mkstemp(**kwargs)
        temp_files_seen.append(path)
        return fd, path

    def run_side_effect(cmd, **kwargs):  # noqa: ANN001
        _aria2c_output(cmd).write_bytes(content)
        return MagicMock(returncode=0, stdout="", stderr="")

    with (
        patch("tempfile.mkstemp", side_effect=spy_mkstemp),
        patch("subprocess.run", MagicMock(side_effect=run_side_effect)),
    ):
        download_via_aria2c(
            url="https://cdn.example.com/setup.exe",
            dest=dest,
            aria2c_path=Path("/usr/bin/aria2c"),
        )

    for path in temp_files_seen:
        assert not Path(path).exists(), f"Temp file {path} was not cleaned up"
