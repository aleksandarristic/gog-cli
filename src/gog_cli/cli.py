"""Command-line interface for gog-cli."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from gog_cli import __version__
from gog_cli.auth import handle_auth_login, handle_auth_logout, handle_auth_status
from gog_cli.errors import GogError
from gog_cli.execution import handle_backup, handle_plan, handle_sync
from gog_cli.listing import handle_list_backed_up, handle_list_purchased, handle_search_catalog
from gog_cli.refresh import handle_refresh


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gog",
        description="Back up owned DRM-free GOG games.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    subcommands = parser.add_subparsers(dest="command", required=True)

    _add_auth_parser(subcommands)
    _add_refresh_parser(subcommands)
    _add_list_parser(subcommands)
    _add_search_parser(subcommands)
    _add_plan_parser(subcommands)
    _add_backup_parser(subcommands)
    _add_sync_parser(subcommands)

    return parser


def _add_auth_parser(subcommands: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    auth = subcommands.add_parser("auth", help="Manage GOG credentials.")
    auth_sub = auth.add_subparsers(dest="auth_command", required=True)

    auth_sub.add_parser("login", help="Log in to GOG.").set_defaults(handler=handle_auth_login)
    auth_sub.add_parser("status", help="Show authentication status.").set_defaults(
        handler=handle_auth_status
    )
    auth_sub.add_parser("logout", help="Log out and remove credentials.").set_defaults(
        handler=handle_auth_logout
    )


def _add_refresh_parser(subcommands: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    refresh = subcommands.add_parser(
        "refresh",
        help="Fetch library and download metadata from GOG.",
    )
    refresh.add_argument(
        "--force",
        action="store_true",
        help="Re-fetch all download metadata even if recently cached.",
    )
    refresh.add_argument(
        "--format",
        choices=["human", "json"],
        default="human",
        dest="output_format",
        help="Output format (default: human).",
    )
    refresh.set_defaults(handler=handle_refresh)


def _add_list_parser(subcommands: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    list_cmd = subcommands.add_parser("list", help="List games.")
    list_sub = list_cmd.add_subparsers(dest="list_command", required=True)

    purchased = list_sub.add_parser(
        "purchased",
        help="List owned GOG games.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""examples:
  gog list purchased --search witcher
  gog list purchased --platform windows
  gog list purchased --year 1998..2005
  gog list purchased --year 2010..2020 --include-unknown-year
  gog list purchased --genre strategy
  gog list purchased --genre strategy --include-unknown-genre
  gog list purchased --search "baldurs gate" --platform linux --format json""",
    )
    purchased.add_argument(
        "--format",
        choices=["human", "json"],
        default="human",
        dest="output_format",
        help="Output format (default: human).",
    )
    purchased.add_argument(
        "--platform",
        action="append",
        default=[],
        dest="platforms",
        metavar="PLATFORM",
        help="Filter by platform (windows, mac, linux). Repeatable.",
    )
    purchased.add_argument(
        "--year",
        metavar="RANGE",
        help="Filter by release year, e.g. 1998..2005, 2020.., or ..2000.",
    )
    purchased.add_argument(
        "--include-unknown-year",
        action="store_true",
        help="Keep games with unknown release years when --year is used.",
    )
    purchased.add_argument(
        "--genre",
        action="append",
        default=[],
        dest="genres",
        metavar="GENRE",
        help="Filter by genre/category/tag. Repeatable; comma-separated values allowed.",
    )
    purchased.add_argument(
        "--include-unknown-genre",
        action="store_true",
        help="Keep games with unknown genres when --genre is used.",
    )
    purchased.add_argument(
        "--search",
        metavar="TEXT",
        help="Fuzzy title search.",
    )
    purchased.set_defaults(handler=handle_list_purchased)

    backed_up = list_sub.add_parser("backup", help="List locally backed-up games.")
    backed_up.add_argument(
        "--destination",
        required=False,
        default=None,
        type=Path,
        help="Backup destination directory to inspect (default: from config).",
    )
    backed_up.add_argument(
        "--format",
        choices=["human", "json"],
        default="human",
        dest="output_format",
        help="Output format (default: human).",
    )
    backed_up.set_defaults(handler=handle_list_backed_up)


def _add_search_parser(subcommands: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    search = subcommands.add_parser(
        "search",
        help="Search the public GOG catalog.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""examples:
  gog search witcher
  gog search "baldurs gate" --platform windows
  gog search strategy --year 2000..2010
  gog search rpg --genre "role-playing" --format json""",
    )
    search.add_argument("query", help="Search query (title keywords).")
    search.add_argument(
        "--format",
        choices=["human", "json"],
        default="human",
        dest="output_format",
        help="Output format (default: human).",
    )
    search.add_argument(
        "--platform",
        action="append",
        default=[],
        dest="platforms",
        metavar="PLATFORM",
        help="Filter by platform (windows, mac, linux). Repeatable.",
    )
    search.add_argument(
        "--year",
        metavar="RANGE",
        help="Filter by release year, e.g. 1998..2005, 2020.., or ..2000.",
    )
    search.add_argument(
        "--genre",
        action="append",
        default=[],
        dest="genres",
        metavar="GENRE",
        help="Filter by genre/category/tag. Repeatable.",
    )
    search.set_defaults(handler=handle_search_catalog)


def _add_selector_flags(parser: argparse.ArgumentParser) -> None:
    grp = parser.add_argument_group("game selection")
    grp.add_argument(
        "--game",
        dest="games",
        metavar="SELECTOR",
        action="append",
        default=[],
        help="Select a game by product id, slug, or exact title. Repeatable.",
    )
    grp.add_argument(
        "--games-from",
        dest="games_from",
        metavar="PATH",
        action="append",
        default=[],
        type=Path,
        help="Read game selectors from a UTF-8 text file, one per line. Repeatable.",
    )
    grp.add_argument(
        "--exclude",
        metavar="SELECTOR",
        action="append",
        default=[],
        help="Exclude a game by product id, slug, or exact title. Repeatable.",
    )
    grp.add_argument(
        "--all",
        dest="all_games",
        action="store_true",
        help="Select all owned games.",
    )
    grp.add_argument(
        "--platform",
        metavar="PLATFORM",
        action="append",
        default=[],
        dest="platforms",
        help="Limit to this platform (e.g. windows, linux, mac). Repeatable.",
    )
    grp.add_argument(
        "--language",
        metavar="LANG",
        action="append",
        default=[],
        dest="languages",
        help="Limit to this language code. Repeatable.",
    )


def _add_interaction_flags(parser: argparse.ArgumentParser) -> None:
    grp = parser.add_argument_group("interaction")
    grp.add_argument(
        "--yes",
        action="store_true",
        help="Skip confirmation prompts.",
    )
    grp.add_argument(
        "--no-interactive",
        dest="no_interactive",
        action="store_true",
        help="Fail rather than prompt when selectors are missing.",
    )
    grp.add_argument(
        "--downloader",
        choices=["direct", "aria2c"],
        default="direct",
        help="Download engine to use (default: direct).",
    )


def _add_backup_parser(subcommands: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    backup = subcommands.add_parser("backup", help="Back up owned GOG games to a local directory.")
    backup.add_argument(
        "--destination",
        type=Path,
        help="Directory where game backups should be stored.",
    )
    backup.add_argument(
        "--dry-run",
        action="store_true",
        help="Show the plan without downloading files.",
    )
    backup.add_argument(
        "--format",
        choices=["human", "json"],
        default="human",
        dest="output_format",
        help="Output format (default: human).",
    )
    backup.add_argument(
        "--check-free-space",
        action="store_true",
        dest="check_free_space",
        help="Fail if available disk space is less than the estimated download size.",
    )
    backup.add_argument(
        "--storage",
        action="store_true",
        help="Show disk usage section in plan output.",
    )
    backup.add_argument(
        "--summary",
        action="store_true",
        help="Print summary only, omit per-game file detail.",
    )
    backup.add_argument(
        "--changed-only",
        action="store_true",
        dest="changed_only",
        help="Show only games with pending downloads in per-game detail.",
    )
    backup.add_argument(
        "--explain-skips",
        action="store_true",
        dest="explain_skips",
        help="Annotate skipped files with their filter reason.",
    )
    _add_selector_flags(backup)
    _add_interaction_flags(backup)
    backup.set_defaults(handler=handle_backup)


def _add_plan_parser(subcommands: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    plan = subcommands.add_parser(
        "plan",
        help="Show the backup plan without downloading files.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""examples:
  gog plan --all --destination /backups/gog
  gog plan cyberpunk-2077 --destination /backups/gog
  gog plan --all --summary
  gog plan --all --format json""",
    )
    plan.add_argument(
        "selectors",
        nargs="*",
        metavar="GAME",
        help="Game selector by product id, slug, or exact title.",
    )
    plan.add_argument(
        "--destination",
        type=Path,
        help="Directory where game backups should be stored.",
    )
    plan.add_argument(
        "--format",
        choices=["human", "json"],
        default="human",
        dest="output_format",
        help="Output format (default: human).",
    )
    plan.add_argument(
        "--check-free-space",
        action="store_true",
        dest="check_free_space",
        help="Fail if available disk space is less than the estimated download size.",
    )
    plan.add_argument(
        "--storage",
        action="store_true",
        help="Show disk usage section in plan output.",
    )
    plan.add_argument(
        "--summary",
        action="store_true",
        help="Print summary only, omit per-game file detail.",
    )
    plan.add_argument(
        "--changed-only",
        action="store_true",
        dest="changed_only",
        help="Show only games with pending downloads in per-game detail.",
    )
    plan.add_argument(
        "--explain-skips",
        action="store_true",
        dest="explain_skips",
        help="Annotate skipped files with their filter reason.",
    )
    _add_selector_flags(plan)
    plan.set_defaults(handler=handle_plan)


def _add_sync_parser(subcommands: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    sync = subcommands.add_parser("sync", help="Update stale local backups.")
    sync.add_argument(
        "--destination",
        type=Path,
        help="Backup destination directory to sync.",
    )
    sync.add_argument(
        "--dry-run",
        action="store_true",
        help="Show the plan without downloading files.",
    )
    _add_selector_flags(sync)
    _add_interaction_flags(sync)
    sync.set_defaults(handler=handle_sync)


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.handler(args)
    except GogError as exc:
        print(str(exc), file=sys.stderr)
        return exc.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
