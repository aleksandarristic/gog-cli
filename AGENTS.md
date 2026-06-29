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
- Run linting with `ruff check src/ tests/`.
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

Worktrees are for local parallel work only:
- Never `git push` a worktree or session branch to remote. Worktree branches (prefixed `session/`, `task/`, or similar) are ephemeral and must stay local.
- Never push any branch to remote unless the user explicitly asks.
- Never open a PR unless the user explicitly asks.
- After parallel agent work is done and results are merged back to the working branch, the worktree branch should be deleted locally — do not let it accumulate.

Why instructions rather than permission restrictions? Worktrees are intentionally used for parallel multi-agent workflows. Blocking git push entirely would break legitimate pushes. The instruction approach preserves worktree utility while enforcing correct lifecycle.

### Correct worktree lifecycle

```
Agent(isolation: "worktree") spawned
  → git worktree add  (branch: session/<id> or task/<id>)
  → agent does work, commits locally
  → results merged back to working branch
  → git worktree remove
  → git branch -d session/<id>   ← local delete, never pushed
```

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
