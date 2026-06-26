"""Command-line interface for gog-dl."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from gog_dl import __version__


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

    list_games = subcommands.add_parser("list", help="List owned GOG games.")
    list_games.set_defaults(handler=handle_list_games)

    backup = subcommands.add_parser("backup", help="Back up owned GOG games.")
    backup.add_argument(
        "--destination",
        required=True,
        type=Path,
        help="Directory where game backups should be stored.",
    )
    backup.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be backed up without downloading files.",
    )
    backup.set_defaults(handler=handle_backup)

    return parser


def handle_list_games(_args: argparse.Namespace) -> int:
    print("Listing games is not implemented yet.")
    return 1


def handle_backup(args: argparse.Namespace) -> int:
    destination = args.destination.expanduser()
    if args.dry_run:
        print(f"Would back up owned games to {destination}.")
        return 0

    print(f"Backing up games is not implemented yet. Destination: {destination}")
    return 1


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
