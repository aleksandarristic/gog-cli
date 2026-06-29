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

_TOP_LEVEL_EXAMPLES = """examples:
  gog auth login
  gog refresh
  gog list purchased --search witcher
  gog plan --destination /backups/gog --all --storage
  gog backup --destination /backups/gog --games-from games.txt --downloader aria2c --yes
  gog sync --destination /backups/gog --all --dry-run"""

_AUTH_EXAMPLES = """examples:
  gog auth login
  gog auth status
  gog auth logout"""

_REFRESH_EXAMPLES = """examples:
  gog refresh
  gog refresh --force
  gog refresh --format json"""

_LIST_EXAMPLES = """examples:
  gog list purchased
  gog list purchased --search witcher --platform linux
  gog list backup --destination /backups/gog
  gog list backup --destination /backups/gog --format json"""

_LIST_PURCHASED_EXAMPLES = """examples:
  gog list purchased --search witcher
  gog list purchased --platform windows
  gog list purchased --year 1998..2005
  gog list purchased --year 2010..2020 --include-unknown-year
  gog list purchased --genre strategy
  gog list purchased --genre strategy --include-unknown-genre
  gog list purchased --search "baldurs gate" --platform linux --format json"""

_LIST_BACKUP_EXAMPLES = """examples:
  gog list backup --destination /backups/gog
  gog list backup --destination /backups/gog --format json"""

_SEARCH_EXAMPLES = """examples:
  gog search witcher
  gog search "baldurs gate" --platform windows
  gog search strategy --year 2000..2010
  gog search rpg --genre "role-playing" --format json"""

_PLAN_EXAMPLES = """examples:
  gog plan --destination /backups/gog --all --storage
  gog plan --destination /backups/gog --all --check-free-space
  gog plan --destination /backups/gog --games-from games.txt --summary
  gog plan --destination /backups/gog cyberpunk-2077
  gog plan --destination /backups/gog --all --format json"""

_BACKUP_EXAMPLES = """examples:
  gog backup --destination /backups/gog --all
  gog backup --destination /backups/gog --all --yes
  gog backup --destination /backups/gog --games-from games.txt --downloader aria2c --yes
  gog backup --destination /backups/gog --platform linux --language en --all --yes
  gog backup --destination /backups/gog --all --format json"""

_SYNC_EXAMPLES = """examples:
  gog sync --destination /backups/gog --all
  gog sync --destination /backups/gog --all --dry-run
  gog sync --destination /backups/gog --games-from games.txt --yes"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gog",
        description=(
            "Back up owned DRM-free GOG games. Commands are explicit and "
            "non-destructive by default; backup and sync print a dry-run plan "
            "unless --yes is passed."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=_TOP_LEVEL_EXAMPLES,
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
    auth = subcommands.add_parser(
        "auth",
        help="Manage GOG credentials.",
        description=(
            "Manage the local GOG session used by refresh and download commands. "
            "Tokens are stored in app state, not inside backup destinations."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=_AUTH_EXAMPLES,
    )
    auth_sub = auth.add_subparsers(dest="auth_command", required=True)

    auth_sub.add_parser(
        "login",
        help="Log in to GOG.",
        description="Start the browser-based GOG login flow and store a local session.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="examples:\n  gog auth login",
    ).set_defaults(handler=handle_auth_login)
    auth_sub.add_parser(
        "status",
        help="Show authentication status.",
        description="Show whether a local GOG session is available and when it expires.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="examples:\n  gog auth status",
    ).set_defaults(handler=handle_auth_status)
    auth_sub.add_parser(
        "logout",
        help="Log out and remove credentials.",
        description="Remove the local GOG session from app state.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="examples:\n  gog auth logout",
    ).set_defaults(
        handler=handle_auth_logout
    )


def _add_refresh_parser(subcommands: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    refresh = subcommands.add_parser(
        "refresh",
        help="Fetch library and download metadata from GOG.",
        description=(
            "Fetch purchased-library and download metadata into the local cache. "
            "This does not download game installers."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=_REFRESH_EXAMPLES,
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
    list_cmd = subcommands.add_parser(
        "list",
        help="List games.",
        description="List cached purchased games or games already recorded in a backup manifest.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=_LIST_EXAMPLES,
    )
    list_sub = list_cmd.add_subparsers(dest="list_command", required=True)

    purchased = list_sub.add_parser(
        "purchased",
        help="List owned GOG games.",
        description=(
            "List owned games from the local cache written by `gog refresh`. "
            "This command does not contact GOG."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=_LIST_PURCHASED_EXAMPLES,
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

    backed_up = list_sub.add_parser(
        "backup",
        help="List locally backed-up games.",
        description="Read the backup manifest at a destination and summarize recorded games/files.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=_LIST_BACKUP_EXAMPLES,
    )
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
        description=(
            "Search public GOG catalog data. Results are public catalog entries; "
            "use `gog list purchased` for owned-library data."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=_SEARCH_EXAMPLES,
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
    backup = subcommands.add_parser(
        "backup",
        help="Back up owned GOG games to a local directory.",
        description=(
            "Plan or execute a local backup. Without --yes this command prints "
            "a dry-run plan and exits without downloading or modifying backup files."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=_BACKUP_EXAMPLES,
    )
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
        description=(
            "Show a non-destructive backup plan. This is equivalent to "
            "`gog backup --dry-run` and does not download files or create backup "
            "directories."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=_PLAN_EXAMPLES,
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
    sync = subcommands.add_parser(
        "sync",
        help="Update stale local backups.",
        description=(
            "Compare cached source metadata to a backup manifest and plan updates. "
            "Without --yes this command prints a dry-run plan and exits without "
            "downloading or modifying backup files."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=_SYNC_EXAMPLES,
    )
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
