# AGENTS

## Intent
- This project is a CLI application for backing up a user's DRM-free GOG game
  library.
- Its priorities are reliable downloads, resumable operation, clear status
  output, and safe local file handling.
- Backups retain enough metadata to remain auditable and restorable, including
  game titles, build/version details, installer names, available checksums, and
  download timestamps.
- Python is the chosen implementation language for the CLI.

## Key behaviors
- Changes are small and reviewable, with tests included where feasible.
- CLI behavior is explicit and scriptable: flags are stable, exit codes are
  predictable, stdout and stderr have useful separation, and destructive
  actions are never hidden.
- Credentials and auth tokens receive careful handling. Secrets are never
  logged, committed, or stored unencrypted unless the user explicitly approves
  that tradeoff.
- Downloaded game files are neither deleted nor overwritten unless a command
  requires it and clearly names the behavior.
- Long-running download workflows support recovery from interruption where
  feasible.
- Official or documented GOG interfaces are preferred when practical. Any
  reliance on an unofficial endpoint or reverse-engineered behavior is
  documented near its usage in code or documentation.
- Existing Python project conventions remain in use unless the user asks to
  revisit the stack.

## Local runtime environment
- The surrounding tooling can differ between agent runs. Tasks involving a
  build, preview, or external CLI verification begin with a check for the
  required commands in the current session, which determines the available
  verification steps.
- When present, `.agent-env.local.md` is a gitignored environment note for quick
  orientation. It serves only as a cache; relevant commands are verified before
  use.
- Python is managed with `uv`. The project pins Python in `.python-version`,
  declares dependencies in `pyproject.toml`, and commits the resolved dependency
  graph in `uv.lock`. The project has no `requirements.txt`; dependency changes
  use `uv add` or `uv add --dev`.
- Inside a restricted Codex sandbox, `uv` commands use the
  `UV_CACHE_DIR=.uv-cache` prefix so uv does not try to write under the user's
  home directory.

## Commands
- Dependency sync: `UV_CACHE_DIR=.uv-cache uv sync`
- Tests: `UV_CACHE_DIR=.uv-cache uv run pytest`
- Linting: `UV_CACHE_DIR=.uv-cache uv run ruff check src/ tests/`
- Local CLI: `UV_CACHE_DIR=.uv-cache uv run gog --help` or
  `UV_CACHE_DIR=.uv-cache uv run python -m gog_cli.cli --help`.

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
- The project does not assume a public distribution model, cloud sync, or
  piracy-related behavior. Its scope is the authenticated user's own library.
