from __future__ import annotations

from pathlib import Path

from gog_cli.backup import FileSpec
from gog_cli.layout import BackupLayout
from gog_cli.sync import compare_file, plan_sync


def make_spec(
    source_id: str = "en1installer1",
    role: str = "installer",
    platform: str = "windows",
    language: str = "en",
    version: str = "1.0",
    size: int = 1000,
    md5: str | None = None,
) -> FileSpec:
    return FileSpec(
        source_id=source_id,
        role=role,
        platform=platform,
        language=language,
        version=version,
        expected_size=size,
        expected_md5=md5,
        downlink_url="https://api.gog.com/products/1111/downlink/installer/en1installer1",
        checksum_url=None,
    )


def current_record(spec: FileSpec, status: str = "verified") -> dict:
    return {
        "source_id": spec.source_id,
        "version": spec.version,
        "expected_size": spec.expected_size,
        "expected_md5": spec.expected_md5,
        "status": status,
    }


# --- compare_file ---


def test_compare_missing_when_no_record() -> None:
    spec = make_spec()
    result = compare_file(spec, None)
    assert result.status == "missing"


def test_compare_current_when_record_matches() -> None:
    spec = make_spec()
    result = compare_file(spec, current_record(spec, "verified"))
    assert result.status == "current"


def test_compare_stale_source_id_changed() -> None:
    spec = make_spec(source_id="new_id")
    record = current_record(spec, "verified")
    record["source_id"] = "old_id"
    result = compare_file(spec, record)
    assert result.status == "stale"
    assert result.stale_reason == "id_changed"


def test_compare_stale_version_changed() -> None:
    spec = make_spec(version="2.0")
    record = current_record(spec, "verified")
    record["version"] = "1.0"
    result = compare_file(spec, record)
    assert result.status == "stale"
    assert result.stale_reason == "version_changed"


def test_compare_stale_size_changed() -> None:
    spec = make_spec(size=2000)
    record = current_record(spec, "verified")
    record["expected_size"] = 1000
    result = compare_file(spec, record)
    assert result.status == "stale"
    assert result.stale_reason == "size_changed"


def test_compare_stale_checksum_changed() -> None:
    spec = make_spec(md5="abc123")
    record = current_record(spec, "verified")
    record["expected_md5"] = "def456"
    result = compare_file(spec, record)
    assert result.status == "stale"
    assert result.stale_reason == "checksum_changed"


def test_compare_partial_when_partial_status() -> None:
    spec = make_spec()
    record = current_record(spec, "partial")
    result = compare_file(spec, record)
    assert result.status == "partial"


def test_compare_unverified_when_downloaded_status() -> None:
    spec = make_spec()
    record = current_record(spec, "downloaded")
    result = compare_file(spec, record)
    assert result.status == "unverified"


# --- plan_sync ---


def test_plan_sync_missing_goes_to_download(tmp_path: Path) -> None:
    layout = BackupLayout(root=tmp_path)
    games = [{"id": 1111, "title": "Witcher 3", "slug": "witcher_3"}]
    specs = {"1111": [make_spec()]}
    manifest: dict = {"games": []}

    plan = plan_sync(tmp_path, games, specs, manifest, layout)

    assert len(plan.to_download) == 1
    assert len(plan.to_verify) == 0
    assert len(plan.current) == 0
    assert plan.estimated_bytes == 1000


def test_plan_sync_current_goes_to_current_list(tmp_path: Path) -> None:
    layout = BackupLayout(root=tmp_path)
    spec = make_spec()
    games = [{"id": 1111, "title": "Witcher 3", "slug": "witcher_3"}]
    specs = {"1111": [spec]}
    manifest = {
        "games": [
            {
                "product_id": 1111,
                "files": [
                    {
                        "role": spec.role,
                        "platform": spec.platform,
                        "language": spec.language,
                        **current_record(spec, "verified"),
                    }
                ],
            }
        ]
    }

    plan = plan_sync(tmp_path, games, specs, manifest, layout)

    assert len(plan.current) == 1
    assert plan.estimated_bytes == 0


def test_plan_sync_stale_goes_to_download(tmp_path: Path) -> None:
    layout = BackupLayout(root=tmp_path)
    spec = make_spec(version="2.0")
    games = [{"id": 1111, "title": "Witcher 3", "slug": "witcher_3"}]
    specs = {"1111": [spec]}
    old_record = current_record(spec, "verified")
    old_record["version"] = "1.0"
    manifest = {
        "games": [
            {
                "product_id": 1111,
                "files": [
                    {
                        "role": spec.role,
                        "platform": spec.platform,
                        "language": spec.language,
                        **old_record,
                    }
                ],
            }
        ]
    }

    plan = plan_sync(tmp_path, games, specs, manifest, layout)

    assert len(plan.to_download) == 1
    assert plan.to_download[0].spec.version == "2.0"


def test_plan_sync_unverified_goes_to_verify(tmp_path: Path) -> None:
    layout = BackupLayout(root=tmp_path)
    spec = make_spec()
    games = [{"id": 1111, "title": "Witcher 3", "slug": "witcher_3"}]
    specs = {"1111": [spec]}
    manifest = {
        "games": [
            {
                "product_id": 1111,
                "files": [
                    {
                        "role": spec.role,
                        "platform": spec.platform,
                        "language": spec.language,
                        **current_record(spec, "downloaded"),
                    }
                ],
            }
        ]
    }

    plan = plan_sync(tmp_path, games, specs, manifest, layout)

    assert len(plan.to_verify) == 1
    assert plan.estimated_bytes == 0


def test_plan_sync_platform_filter(tmp_path: Path) -> None:
    layout = BackupLayout(root=tmp_path)
    games = [{"id": 1111, "title": "Witcher 3", "slug": "witcher_3"}]
    specs = {
        "1111": [
            make_spec(source_id="win", platform="windows"),
            make_spec(source_id="lin", platform="linux"),
        ]
    }
    manifest: dict = {"games": []}

    plan = plan_sync(tmp_path, games, specs, manifest, layout, platforms=["linux"])

    assert len(plan.to_download) == 1
    assert plan.to_download[0].spec.source_id == "lin"
