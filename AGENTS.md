# AGENTS

## Intent
- Build a CLI application for backing up a user's DRM-free GOG game library.
- The tool should prioritize reliable downloads, resumable operation, clear status output, and safe local file handling.
- Preserve enough metadata to make backups auditable and restorable, such as game titles, build/version details, installer names, checksums when available, and download timestamps.
- Python is the chosen implementation language for the CLI.

## Key behaviors
- Prefer small, reviewable changes and add tests where feasible.
- Keep CLI behavior explicit and scriptable: stable flags, predictable exit codes, useful stderr/stdout separation, and no hidden destructive actions.
- Treat credentials and auth tokens carefully. Do not log secrets, commit secrets, or store them unencrypted unless the user explicitly approves that tradeoff.
- Avoid deleting or overwriting downloaded game files unless the command requires it and the behavior is clearly named.
- Design long-running download workflows to recover from interruption where feasible.
- Favor official or documented GOG interfaces when practical. If relying on an unofficial endpoint or reverse-engineered behavior, document the risk in code or docs near the usage.
- Use the existing Python project conventions unless the user asks to revisit the stack.

## Local runtime environment
- Do not assume every agent run has the same surrounding tooling. At the start
  of any task that needs build, preview, or external CLI verification, check the
  current session for the required commands before deciding which verification
  steps are available.
- If present, `.agent-env.local.md` is a gitignored environment note for quick
  orientation. Treat it as a cache only; verify relevant commands before relying
  on it.

## Commands
- Run tests with `./.venv/bin/pytest` (or `python -m pytest` if the venv is active).
- Run linting with `./.venv/bin/ruff check src/ tests/`.
- Run the CLI locally with `python -m gog_cli.cli --help` or the installed `gog` console script.

## Branch and remote hygiene

All work goes on a branch. `main` is always releasable.

| Prefix | Use |
|--------|-----|
| `feature/` | New user-visible functionality |
| `fix/` | Bug fixes |
| `chore/` | Dependency updates, tooling, CI changes |
| `docs/` | Documentation only |
| `release/` | Version bumps and release prep |

## Notes
- Initial product direction: a personal backup tool for all owned DRM-free GOG games.
- The installed CLI command should be `gog`.
- Core expected workflows include listing owned games and backing up owned games to a local directory.
- Supporting workflows will likely include authentication, library discovery, metadata sync, game selection/filtering, download planning, downloading, verification, and incremental updates.
- Do not assume a public distribution model, cloud sync, or piracy-related behavior. Scope work around backing up the authenticated user's own library.
