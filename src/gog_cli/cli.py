"""Command-line interface for gog-cli."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from gog_cli import __version__
from gog_cli.auth import handle_auth_login, handle_auth_logout, handle_auth_status
from gog_cli.errors import GogError


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
    _add_list_parser(subcommands)
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


def _add_list_parser(subcommands: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    list_cmd = subcommands.add_parser("list", help="List games.")
    list_sub = list_cmd.add_subparsers(dest="list_command", required=True)

    purchased = list_sub.add_parser("purchased", help="List owned GOG games.")
    purchased.add_argument(
        "--format",
        choices=["human", "json"],
        default="human",
        dest="output_format",
        help="Output format (default: human).",
    )
    purchased.set_defaults(handler=handle_list_purchased)

    backed_up = list_sub.add_parser("backed-up", help="List locally backed-up games.")
    backed_up.add_argument(
        "--destination",
        required=True,
        type=Path,
        help="Backup destination directory to inspect.",
    )
    backed_up.add_argument(
        "--format",
        choices=["human", "json"],
        default="human",
        dest="output_format",
        help="Output format (default: human).",
    )
    backed_up.set_defaults(handler=handle_list_backed_up)


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
    _add_selector_flags(backup)
    _add_interaction_flags(backup)
    backup.set_defaults(handler=handle_backup)


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


def handle_list_purchased(_args: argparse.Namespace) -> int:
    print("gog list purchased is not implemented yet.", file=sys.stderr)
    return 1


def handle_list_backed_up(_args: argparse.Namespace) -> int:
    print("gog list backed-up is not implemented yet.", file=sys.stderr)
    return 1


def handle_backup(args: argparse.Namespace) -> int:
    if args.dry_run:
        dest = args.destination.expanduser() if args.destination else "<configured destination>"
        print(f"Dry run: would back up selected games to {dest}.")
        return 0
    print("gog backup is not implemented yet.", file=sys.stderr)
    return 1


def handle_sync(args: argparse.Namespace) -> int:
    if args.dry_run:
        dest = args.destination.expanduser() if args.destination else "<configured destination>"
        print(f"Dry run: would sync backed-up games at {dest}.")
        return 0
    print("gog sync is not implemented yet.", file=sys.stderr)
    return 1


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
