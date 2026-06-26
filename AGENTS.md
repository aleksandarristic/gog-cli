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

## Commands
- Run tests with `python -m pytest`.
- Run the CLI locally with `python -m gog_cli.cli --help` or the installed `gog` console script.

## Task management
- Use `.task-management/` for durable task tracking.
- Use stable task IDs in the form `TASK-####`; never reuse IDs.
- Keep immediate work in `.task-management/TODO.md` and deferred work in `.task-management/BACKLOG.md`.
- Keep larger task details in `.task-management/TASK-####-slug.md`.
- Move completed tasks to `.task-management/DONE.md` with completion date and notes.
- Move dropped tasks to `.task-management/REMOVED.md` with removal date and reason.
- Keep transferring durable decisions from `SPEC.md` and `missing_pieces.md` into task files gradually; do not delete those source docs until the transferred content has a clear home.

## Multi-agent dispatch
- Agent roles:
  - Codex is the default implementation agent for focused code changes, tests, and repo maintenance.
  - Claude is useful for planning, implementation, and review on broader or riskier changes.
  - Gemini is useful for UI and frontend-oriented tasks.
- Trigger dispatch from Discord by naming one or more agent handles in a prompt, for example:
  - `!c @claude plan the auth refactor, dispatch @codex`
  - `!c @codex @gemini implement the dashboard updates`
- A task branch is created on first dispatch and reused for follow-up commands in the same task lifecycle.
- Finish the task with `!c done`. Use `!c done --merge` when the branch should be merged locally instead of opened as a PR.
- Dispatch output may appear as per-agent status messages, an aggregate summary, or both depending on bridge configuration.
- Keep repo intent, constraints, commands, and conventions in this `AGENTS.md` file so every agent has the same operating context.

## Notes
- Initial product direction: a personal backup tool for all owned DRM-free GOG games.
- The installed CLI command should be `gog`.
- Core expected workflows include listing owned games and backing up owned games to a local directory.
- Supporting workflows will likely include authentication, library discovery, metadata sync, game selection/filtering, download planning, downloading, verification, and incremental updates.
- Do not assume a public distribution model, cloud sync, or piracy-related behavior. Scope work around backing up the authenticated user's own library.
