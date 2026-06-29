# Contributing

## Versioning

This project follows [Semantic Versioning](https://semver.org/) with a `0.x` prefix while the CLI surface is still stabilizing.

- `0.x.0` — new features, new flags, user-visible behavior changes
- `0.x.y` — bug fixes, documentation corrections, no new behavior
- `1.0.0` — first stable release; after that, breaking changes require a major bump

Every version bump gets an annotated `vX.Y.Z` tag on `main` and a corresponding GitHub release with notes summarizing what changed since the previous tag.

## Branches

- `main` is always releasable — no half-finished work lands here.
- Feature branches: `feature/<short-slug>`
- Bug fix branches: `fix/<short-slug>`
- Branches are short-lived: open, get merged, get deleted.

## Pull requests

- Required for anything non-trivial going into `main`.
- One logical change per PR — keeps history clean and makes reverts straightforward.
- Direct commits to `main` are fine for small things: typos, doc tweaks, single-file fixes that don't need review.

## Running tests

```sh
python -m pytest
```

## Code style

Linting is enforced with [Ruff](https://docs.astral.sh/ruff/):

```sh
ruff check src/ tests/
```
