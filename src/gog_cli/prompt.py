"""Interactive and non-interactive selection helpers."""

from __future__ import annotations

import sys

from gog_cli.errors import UsageError


def is_interactive() -> bool:
    """Return True when both stdin and stdout are TTYs."""
    return sys.stdin.isatty() and sys.stdout.isatty()


def numbered_prompt(items: list[str], prompt: str = "Enter selection:") -> list[int]:
    """Print a numbered list to stderr and read a selection from stdin.

    Accepts 'all' to select everything, or comma-separated 1-based numbers.
    Returns a list of 0-based indices. Raises UsageError on invalid input.
    """
    if not items:
        raise UsageError("No items available for selection")

    for i, item in enumerate(items, 1):
        print(f"  {i}. {item}", file=sys.stderr)

    print(f"{prompt} ", end="", file=sys.stderr)
    sys.stderr.flush()

    try:
        raw = sys.stdin.readline().strip()
    except (EOFError, KeyboardInterrupt) as exc:
        raise UsageError("Selection cancelled") from exc

    if not raw:
        raise UsageError("No selection made")

    if raw.lower() == "all":
        return list(range(len(items)))

    indices: list[int] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            n = int(part)
        except ValueError:
            raise UsageError(f"Invalid selection {part!r}: expected a number or 'all'") from None
        if n < 1 or n > len(items):
            raise UsageError(f"Selection {n} is out of range 1–{len(items)}")
        indices.append(n - 1)

    if not indices:
        raise UsageError("No selection made")

    return indices
