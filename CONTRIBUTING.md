# Contributing

## Branches

`main` is always releasable — no half-finished work lands here. Branch names use a short kebab-case slug describing the change.

| Prefix | Use |
|--------|-----|
| `feature/` | New user-visible functionality |
| `fix/` | Bug fixes |
| `chore/` | Dependency updates, tooling, CI changes |
| `docs/` | Documentation only |
| `release/` | Version bumps and release prep |

Examples: `feature/list-sort-flags`, `fix/auth-token-refresh`, `chore/bump-requests`.

Branches are short-lived: open → PR → merge → delete.

## Pull requests

A PR is required for anything non-trivial going into `main`. Use your judgement — typos, doc tweaks, and obvious single-line fixes can go directly to `main`; everything else gets a branch and a PR.

**What requires a PR:**
- New features or new CLI flags
- Bug fixes that change observable behavior
- Refactors touching more than one file
- Any dependency change
- CI or release workflow changes
- Version bumps

**PR checklist:**
- Tests pass (`python -m pytest`)
- Linting passes (`ruff check src/ tests/`)
- Description explains *why*, not just *what*
- One logical change per PR (split unrelated changes)

**Merge strategy:** squash merge to keep `main` history linear. The squash commit message should summarize the whole PR, not repeat the branch name.

## Versioning

This project follows [Semantic Versioning](https://semver.org/) with a `0.x` prefix while the CLI surface is still stabilizing.

| Change | Version bump |
|--------|-------------|
| New features, new flags, user-visible behavior | `0.x.0` minor |
| Bug fixes, doc corrections, no new behavior | `0.x.y` patch |
| Breaking CLI changes | `x.0.0` major (after 1.0) |

`1.0.0` marks the first stable release; after that, breaking changes require a major bump.

**Release process:**
1. Open a `release/vX.Y.Z` branch
2. Bump version in `pyproject.toml` and `src/gog_cli/__init__.py`
3. Update `CHANGELOG.md`
4. PR into `main`, squash merge
5. Tag the merge commit: `git tag -a vX.Y.Z -m "vX.Y.Z"`
6. Push the tag: `git push origin vX.Y.Z`
7. CI builds and publishes to PyPI automatically; a GitHub release is created from the tag

## Running tests

```sh
python -m pytest
```

## Code style

Linting is enforced with [Ruff](https://docs.astral.sh/ruff/):

```sh
ruff check src/ tests/
```

## Setting up a development environment

Requires Python 3.12 or newer.

```sh
git clone https://github.com/aleksandarristic/gog-cli.git
cd gog-cli
python3 -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
python -m pytest
```
