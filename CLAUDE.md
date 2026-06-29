# CLAUDE.md

Agent instructions for the gog-cli project.

## Branch and remote hygiene

Worktrees are for local parallel work only.

- Never `git push` a worktree or session branch to remote. Worktree branches
  (prefixed `session/`, `task/`, or similar) are ephemeral and must stay local.
- Never push any branch to remote unless the user explicitly asks.
- Never open a PR unless the user explicitly asks.
- After parallel agent work is done and results are merged back to the working
  branch, the worktree branch should be deleted locally — do not let it accumulate.

Why instructions rather than permission restrictions? Worktrees are intentionally
used for parallel multi-agent workflows. Blocking git push entirely would break
legitimate pushes. The instruction approach preserves worktree utility while
enforcing correct lifecycle.

### Correct worktree lifecycle

```
Agent(isolation: "worktree") spawned
  → git worktree add  (branch: session/<id> or task/<id>)
  → agent does work, commits locally
  → results merged back to working branch
  → git worktree remove
  → git branch -d session/<id>   ← local delete, never pushed
```
