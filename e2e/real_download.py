#!/usr/bin/env python3
"""Opt-in authenticated end-to-end tests against real GOG downloads."""

from __future__ import annotations

import argparse
import hashlib
import json
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

MIB = 1024 * 1024
REPO_ROOT = Path(__file__).resolve().parents[1]
SELECTOR_FILE = Path(__file__).with_name("real-download-games.txt")
SUCCESS_FILE_STATUSES = {"downloaded", "verified", "skipped"}


class E2EError(RuntimeError):
    """A real-download acceptance check failed."""


@dataclass(frozen=True)
class Case:
    name: str
    description: str
    plan_selection: tuple[str, ...]
    sync_selection: tuple[str, ...]
    filters: tuple[str, ...]
    downloader: str
    expected_product_ids: tuple[str, ...]
    expected_display_mib: int
    exercise_recovery: bool = False


CASES = (
    Case(
        name="direct-jill-linux",
        description="numeric ID; one Linux installer; direct downloader",
        plan_selection=("1129701343",),
        sync_selection=("--game", "1129701343"),
        filters=("--linux", "--role", "installer"),
        downloader="direct",
        expected_product_ids=("1129701343",),
        expected_display_mib=6,
        exercise_recovery=True,
    ),
    Case(
        name="aria-extras",
        description="exact title; extras-only product; aria2c",
        plan_selection=("Warhammer Skulls 2025 Digital Goodie Bag",),
        sync_selection=("--game", "1315929054"),
        filters=("--role", "extra"),
        downloader="aria2c",
        expected_product_ids=("1315929054",),
        expected_display_mib=50,
    ),
    Case(
        name="direct-raptor-combined",
        description="fuzzy title; Windows installer plus extras; direct downloader",
        plan_selection=("raptor call shadows",),
        sync_selection=("--game", "1207658879"),
        filters=("--windows", "--role", "installer", "--role", "extra"),
        downloader="direct",
        expected_product_ids=("1207658879",),
        expected_display_mib=51,
    ),
    Case(
        name="direct-bio-all",
        description="exact --game title; all files; direct downloader",
        plan_selection=("--game", "Bio Menace"),
        sync_selection=("--game", "1449569170"),
        filters=(),
        downloader="direct",
        expected_product_ids=("1449569170",),
        expected_display_mib=31,
    ),
    Case(
        name="aria-mortal-kombat",
        description="repeated ID and title selectors; all files; aria2c",
        plan_selection=("1207667043", "Mortal Kombat 2"),
        sync_selection=("--game", "1207667043", "--game", "1207667053"),
        filters=(),
        downloader="aria2c",
        expected_product_ids=("1207667043", "1207667053"),
        expected_display_mib=89,
    ),
    Case(
        name="aria-list-all",
        description="mixed ID/title selector file; all six games and files; aria2c",
        plan_selection=("--games-from", str(SELECTOR_FILE)),
        sync_selection=("--games-from", str(SELECTOR_FILE)),
        filters=(),
        downloader="aria2c",
        expected_product_ids=(
            "1207658879",
            "1315929054",
            "1207667043",
            "1207667053",
            "1129701343",
            "1449569170",
        ),
        expected_display_mib=254,
    ),
)


@dataclass
class CommandRecord:
    argv: list[str]
    returncode: int
    elapsed_seconds: float
    stdout_tail: str
    stderr_tail: str


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run isolated real-download E2E checks. Without --execute, only "
            "non-destructive plan commands are run."
        )
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Perform authenticated downloads, reruns, sync checks, and recovery tests.",
    )
    parser.add_argument(
        "--case",
        action="append",
        choices=[case.name for case in CASES],
        dest="case_names",
        help="Run only this case. Repeatable; defaults to the full matrix.",
    )
    parser.add_argument(
        "--gog",
        default="gog",
        help="Installed gog executable to test (default: gog from PATH).",
    )
    parser.add_argument(
        "--expected-version",
        default="1.0.2.dev0",
        help="Version required from gog --version; pass an empty value to disable.",
    )
    parser.add_argument(
        "--root",
        type=Path,
        help="New artifact root to create; defaults to a unique directory under /tmp.",
    )
    parser.add_argument(
        "--skip-recovery",
        action="store_true",
        help="Skip missing-file sync recovery and direct resume checks.",
    )
    parser.add_argument(
        "--list-cases",
        action="store_true",
        help="Print the matrix without running commands.",
    )
    return parser


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise E2EError(message)


def _run(
    argv: list[str],
    command_records: list[CommandRecord],
    *,
    expect_json: bool = False,
) -> dict[str, Any] | None:
    print(f"$ {shlex.join(argv)}", flush=True)
    started = time.monotonic()
    completed = subprocess.run(  # noqa: S603
        argv,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    elapsed = time.monotonic() - started
    command_records.append(
        CommandRecord(
            argv=argv,
            returncode=completed.returncode,
            elapsed_seconds=round(elapsed, 3),
            stdout_tail=completed.stdout[-20000:],
            stderr_tail=completed.stderr[-20000:],
        )
    )
    if completed.stderr:
        print(completed.stderr.rstrip(), file=sys.stderr)
    _require(
        completed.returncode == 0,
        f"command failed with exit code {completed.returncode}: {shlex.join(argv)}",
    )
    if not expect_json:
        if completed.stdout:
            print(completed.stdout.rstrip())
        return None
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise E2EError(
            f"command did not produce one JSON document: {shlex.join(argv)}"
        ) from exc
    _require(isinstance(payload, dict), "CLI JSON output must be an object")
    return payload


def _resolve_gog(command: str) -> str:
    candidate = Path(command).expanduser()
    if candidate.parent != Path(".") or candidate.is_absolute():
        _require(candidate.is_file(), f"gog executable does not exist: {candidate}")
        return str(candidate)
    resolved = shutil.which(command)
    _require(resolved is not None, f"gog executable is not on PATH: {command}")
    return str(resolved)


def _create_root(requested: Path | None) -> Path:
    if requested is None:
        return Path(tempfile.mkdtemp(prefix="gog-cli-real-e2e-"))
    root = requested.expanduser().resolve()
    _require(not root.exists(), f"refusing to reuse existing artifact root: {root}")
    root.mkdir(parents=True)
    return root


def _plan_command(gog: str, case: Case, destination: Path) -> list[str]:
    return [
        gog,
        "plan",
        *case.plan_selection,
        "--destination",
        str(destination),
        *case.filters,
        "--format",
        "json",
    ]


def _backup_command(gog: str, case: Case, destination: Path) -> list[str]:
    return [
        gog,
        "backup",
        *case.plan_selection,
        "--destination",
        str(destination),
        *case.filters,
        "--downloader",
        case.downloader,
        "--check-free-space",
        "--format",
        "json",
        "--no-interactive",
        "--yes",
    ]


def _sync_command(
    gog: str,
    case: Case,
    destination: Path,
    *,
    execute: bool,
) -> list[str]:
    argv = [
        gog,
        "sync",
        "--destination",
        str(destination),
        *case.sync_selection,
        *case.filters,
        "--format",
        "json",
        "--no-interactive",
    ]
    argv.append("--yes" if execute else "--dry-run")
    return argv


def _validate_plan(payload: dict[str, Any], case: Case) -> tuple[int, int]:
    _require(payload.get("command") == "backup plan", "unexpected plan command name")
    data = payload.get("data")
    _require(isinstance(data, dict), "plan data must be an object")
    summary = data.get("summary")
    _require(isinstance(summary, dict), "plan summary must be an object")
    _require(
        summary.get("selected_games") == len(case.expected_product_ids),
        f"{case.name}: selected game count differs from the matrix",
    )
    planned_bytes = summary.get("total_download_bytes")
    _require(isinstance(planned_bytes, int), f"{case.name}: plan has no byte count")
    displayed_mib = f"{planned_bytes / MIB:.1f}"
    _require(
        displayed_mib == f"{case.expected_display_mib:.1f}",
        f"{case.name}: planned size is {displayed_mib} MiB; "
        f"expected {case.expected_display_mib:.1f} MiB",
    )
    file_count = summary.get("total_download_files")
    _require(isinstance(file_count, int) and file_count > 0, f"{case.name}: empty plan")
    actions = data.get("actions")
    _require(isinstance(actions, list), "plan actions must be a list")
    planned_ids = {str(item.get("game_id")) for item in actions if isinstance(item, dict)}
    _require(
        planned_ids == set(case.expected_product_ids),
        f"{case.name}: planned products differ: {sorted(planned_ids)}",
    )
    disk = data.get("disk")
    _require(isinstance(disk, dict) and disk.get("enough_space") is True, "insufficient space")
    return file_count, planned_bytes


def _md5(path: Path) -> str:
    digest = hashlib.md5()  # noqa: S324 - GOG publishes MD5 integrity metadata.
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(MIB), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _manifest(destination: Path) -> dict[str, Any]:
    path = destination / "metadata" / "manifest.json"
    _require(path.is_file(), f"manifest was not created: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise E2EError(f"manifest is unreadable: {path}") from exc
    _require(isinstance(data, dict), "manifest must contain an object")
    _require(data.get("schema_version") == 1, "unexpected manifest schema")
    return data


def _validate_manifest(
    destination: Path,
    case: Case,
    expected_file_count: int,
) -> tuple[dict[str, Any], dict[str, tuple[int, int]], list[dict[str, Any]]]:
    manifest = _manifest(destination)
    games = manifest.get("games")
    _require(isinstance(games, list), "manifest games must be a list")
    game_ids = {str(game.get("product_id")) for game in games if isinstance(game, dict)}
    _require(game_ids == set(case.expected_product_ids), f"unexpected manifest games: {game_ids}")

    records = [
        (game, record)
        for game in games
        if isinstance(game, dict)
        for record in game.get("files", [])
        if isinstance(record, dict)
    ]
    _require(
        len(records) == expected_file_count,
        f"manifest has {len(records)} files; plan expected {expected_file_count}",
    )

    root = destination.resolve()
    snapshot: dict[str, tuple[int, int]] = {}
    file_checks: list[dict[str, Any]] = []
    for game, record in records:
        status = record.get("status")
        _require(status in {"downloaded", "verified"}, f"unsuccessful file status: {status}")
        relative_path = record.get("relative_path")
        _require(isinstance(relative_path, str) and relative_path, "missing relative_path")
        path = (destination / relative_path).resolve()
        _require(path.is_relative_to(root), f"manifest path escapes destination: {relative_path}")
        _require(path.is_file(), f"manifest file is missing: {relative_path}")
        if record.get("role") == "installer":
            _require(path.suffix != "", f"installer has no real filename extension: {path.name}")
        stat = path.stat()
        expected_size = record.get("expected_size")
        if isinstance(expected_size, int):
            _require(stat.st_size == expected_size, f"size mismatch: {relative_path}")
        checksum = record.get("checksum")
        actual_md5 = _md5(path)
        expected_md5: str | None = None
        checksum_matches: bool | None = None
        if status == "verified" and isinstance(checksum, dict):
            _require(checksum.get("algorithm") == "md5", "unsupported checksum algorithm")
            expected_md5 = checksum.get("value")
            _require(isinstance(expected_md5, str), "verified file has no checksum value")
            checksum_matches = actual_md5 == expected_md5.lower()
            _require(checksum_matches, f"checksum mismatch: {relative_path}")
        snapshot[relative_path] = (stat.st_size, stat.st_mtime_ns)
        file_checks.append({
            "product_id": str(game.get("product_id", "")),
            "title": str(game.get("title", "")),
            "role": record.get("role"),
            "platform": record.get("platform"),
            "language": record.get("language"),
            "status": status,
            "relative_path": relative_path,
            "actual_bytes": stat.st_size,
            "expected_bytes": expected_size,
            "actual_md5": actual_md5,
            "expected_md5": expected_md5,
            "checksum_matches": checksum_matches,
        })
        match_label = "size-only" if checksum_matches is None else "md5-ok"
        print(
            f"  {match_label:<9} {stat.st_size:>10} bytes  "
            f"{actual_md5}  {relative_path}"
        )
    return manifest, snapshot, file_checks


def _validate_execution(payload: dict[str, Any], expected_file_count: int) -> None:
    data = payload.get("data")
    _require(isinstance(data, list), "execution data must be a list")
    _require(len(data) == expected_file_count, "execution result count differs from plan")
    failures = [
        item for item in data
        if not isinstance(item, dict) or item.get("status") not in SUCCESS_FILE_STATUSES
    ]
    _require(not failures, f"one or more file operations failed: {failures}")


def _validate_list(payload: dict[str, Any], case: Case) -> None:
    _require(payload.get("command") == "list backup", "unexpected list command name")
    data = payload.get("data")
    _require(isinstance(data, list), "list backup data must be a list")
    listed_ids = {str(item.get("product_id")) for item in data if isinstance(item, dict)}
    _require(listed_ids == set(case.expected_product_ids), f"unexpected listed games: {listed_ids}")


def _exercise_recovery(
    gog: str,
    case: Case,
    destination: Path,
    artifact_root: Path,
    command_records: list[CommandRecord],
) -> None:
    manifest = _manifest(destination)
    installers = [
        record
        for game in manifest.get("games", [])
        if isinstance(game, dict)
        for record in game.get("files", [])
        if isinstance(record, dict) and record.get("role") == "installer"
    ]
    _require(bool(installers), f"{case.name}: recovery test needs an installer")
    relative_path = installers[0].get("relative_path")
    _require(isinstance(relative_path, str), "installer has no relative path")
    installed = destination / relative_path
    expected_md5 = _md5(installed)

    recovery_dir = artifact_root / "recovery-copies" / case.name
    recovery_dir.mkdir(parents=True)
    missing_copy = recovery_dir / f"{installed.name}.missing-source"
    installed.replace(missing_copy)

    sync_plan = _run(
        _sync_command(gog, case, destination, execute=False),
        command_records,
        expect_json=True,
    )
    _require(sync_plan is not None, "missing sync plan output")
    sync_data = sync_plan.get("data")
    _require(
        isinstance(sync_data, dict) and sync_data.get("download_files", 0) >= 1,
        "sync did not detect the moved installer",
    )
    sync_result = _run(
        _sync_command(gog, case, destination, execute=True),
        command_records,
        expect_json=True,
    )
    _require(sync_result is not None, "missing sync execution output")
    _require(installed.is_file(), "sync did not restore the missing installer")
    _require(_md5(installed) == expected_md5, "restored installer differs from original")

    resume_source = recovery_dir / f"{installed.name}.resume-source"
    installed.replace(resume_source)
    part_path = installed.parent / f".{installed.name}.part"
    seed_size = max(1, resume_source.stat().st_size // 2)
    part_path.parent.mkdir(parents=True, exist_ok=True)
    with resume_source.open("rb") as source, part_path.open("wb") as partial:
        partial.write(source.read(seed_size))

    resumed = _run(
        _backup_command(gog, case, destination),
        command_records,
        expect_json=True,
    )
    _require(resumed is not None, "missing resumed backup output")
    _require(installed.is_file(), "direct downloader did not complete the partial file")
    _require(_md5(installed) == expected_md5, "resumed installer differs from original")
    _require(not part_path.exists(), "partial file remains after successful resume")


def _run_case(
    gog: str,
    case: Case,
    artifact_root: Path,
    command_records: list[CommandRecord],
    *,
    execute: bool,
    skip_recovery: bool,
) -> dict[str, Any]:
    print(f"\n== {case.name}: {case.description} ==")
    destination = artifact_root / case.name
    plan = _run(_plan_command(gog, case, destination), command_records, expect_json=True)
    _require(plan is not None, "missing plan output")
    expected_file_count, planned_bytes = _validate_plan(plan, case)
    result: dict[str, Any] = {
        "name": case.name,
        "description": case.description,
        "destination": str(destination),
        "planned_files": expected_file_count,
        "expected_display_mib": case.expected_display_mib,
        "planned_bytes": planned_bytes,
        "executed": execute,
    }
    if not execute:
        return result

    execution = _run(
        _backup_command(gog, case, destination),
        command_records,
        expect_json=True,
    )
    _require(execution is not None, "missing backup execution output")
    _validate_execution(execution, expected_file_count)
    _, initial_snapshot, file_checks = _validate_manifest(
        destination, case, expected_file_count
    )
    result["actual_files"] = len(file_checks)
    result["actual_bytes"] = sum(item["actual_bytes"] for item in file_checks)
    result["planned_vs_actual_delta_bytes"] = result["actual_bytes"] - planned_bytes
    result["verified_files"] = sum(item["status"] == "verified" for item in file_checks)
    result["size_only_files"] = sum(item["status"] == "downloaded" for item in file_checks)
    result["files"] = file_checks

    listed = _run(
        [gog, "list", "--backup", "--destination", str(destination), "--format", "json"],
        command_records,
        expect_json=True,
    )
    _require(listed is not None, "missing list backup output")
    _validate_list(listed, case)

    repeat_plan = _run(_plan_command(gog, case, destination), command_records, expect_json=True)
    _require(repeat_plan is not None, "missing repeat plan output")
    repeat_summary = repeat_plan.get("data", {}).get("summary", {})
    _require(
        isinstance(repeat_summary, dict) and repeat_summary.get("total_download_files") == 0,
        f"{case.name}: repeat plan still schedules downloads",
    )
    repeated = _run(
        _backup_command(gog, case, destination),
        command_records,
        expect_json=True,
    )
    _require(repeated is not None, "missing repeated backup output")
    _validate_execution(repeated, expected_file_count)
    _, repeated_snapshot, _ = _validate_manifest(destination, case, expected_file_count)
    _require(initial_snapshot == repeated_snapshot, "backup rerun modified game files")

    sync_plan = _run(
        _sync_command(gog, case, destination, execute=False),
        command_records,
        expect_json=True,
    )
    _require(sync_plan is not None, "missing sync plan output")
    sync_data = sync_plan.get("data")
    _require(
        isinstance(sync_data, dict) and sync_data.get("download_files") == 0,
        f"{case.name}: sync unexpectedly schedules downloads",
    )
    synced = _run(
        _sync_command(gog, case, destination, execute=True),
        command_records,
        expect_json=True,
    )
    _require(synced is not None, "missing sync execution output")
    _, synced_snapshot, _ = _validate_manifest(destination, case, expected_file_count)
    _require(repeated_snapshot == synced_snapshot, "sync modified current game files")

    if case.exercise_recovery and not skip_recovery:
        _exercise_recovery(gog, case, destination, artifact_root, command_records)
        _validate_manifest(destination, case, expected_file_count)
        result["recovery_exercised"] = True
    else:
        result["recovery_exercised"] = False
    return result


def _write_report(
    artifact_root: Path,
    *,
    status: str,
    cases: list[dict[str, Any]],
    commands: list[CommandRecord],
    error: str | None = None,
) -> Path:
    executed_cases = [case for case in cases if case.get("executed")]
    report = {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "status": status,
        "error": error,
        "summary": {
            "cases_completed": len(cases),
            "cases_executed": len(executed_cases),
            "planned_bytes": sum(int(case.get("planned_bytes", 0)) for case in cases),
            "actual_bytes": sum(int(case.get("actual_bytes", 0)) for case in cases),
            "actual_files": sum(int(case.get("actual_files", 0)) for case in cases),
            "verified_files": sum(int(case.get("verified_files", 0)) for case in cases),
            "size_only_files": sum(int(case.get("size_only_files", 0)) for case in cases),
        },
        "cases": cases,
        "commands": [asdict(command) for command in commands],
    }
    path = artifact_root / "e2e-report.json"
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.list_cases:
        for case in CASES:
            print(
                f"{case.name:<26} {case.description} "
                f"({case.expected_display_mib} MiB displayed)"
            )
        return 0

    selected_names = set(args.case_names or [])
    selected = [case for case in CASES if not selected_names or case.name in selected_names]
    gog = _resolve_gog(args.gog)
    artifact_root = _create_root(args.root)
    print(f"Artifacts: {artifact_root}")

    command_records: list[CommandRecord] = []
    case_results: list[dict[str, Any]] = []
    try:
        version_result = subprocess.run(  # noqa: S603
            [gog, "--version"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        _require(version_result.returncode == 0, "gog --version failed")
        version_output = version_result.stdout.strip()
        print(version_output)
        if args.expected_version:
            _require(
                args.expected_version in version_output,
                f"expected gog {args.expected_version}, got: {version_output}",
            )
        if args.execute:
            _run([gog, "auth", "status"], command_records)
            if any(case.downloader == "aria2c" for case in selected):
                _require(shutil.which("aria2c") is not None, "aria2c is required by the matrix")

        for case in selected:
            case_results.append(
                _run_case(
                    gog,
                    case,
                    artifact_root,
                    command_records,
                    execute=args.execute,
                    skip_recovery=args.skip_recovery,
                )
            )
    except (E2EError, KeyboardInterrupt) as exc:
        report_path = _write_report(
            artifact_root,
            status="failed",
            cases=case_results,
            commands=command_records,
            error=str(exc),
        )
        print(f"E2E failed: {exc}", file=sys.stderr)
        print(f"Artifacts preserved at {artifact_root}", file=sys.stderr)
        print(f"Report: {report_path}", file=sys.stderr)
        return 1

    report_path = _write_report(
        artifact_root,
        status="passed",
        cases=case_results,
        commands=command_records,
    )
    print(f"\nE2E passed. Artifacts preserved at {artifact_root}")
    print(f"Report: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
