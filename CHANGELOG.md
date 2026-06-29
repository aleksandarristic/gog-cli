# Changelog

All notable changes to this project will be documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versions follow [Semantic Versioning](https://semver.org/).

---

## [0.2.1] — 2026-06-29

### Fixed
- Lint errors (line length, import sort) that caused CI to fail on 0.2.0.

### Changed
- CI badge added to README.

---

## [0.2.0] — 2026-06-29

### Added
- Short flag aliases across all commands (`-d`, `-f`, `-p`, `-s`, `-y`, `-G`, `-S`, `-a`, `-g`, `-F`, `-x`, `-l`, `-D`, `-n`).
- Totals row at the bottom of `list purchased` and `list backup` output.
- Platform-filtered size columns: `list purchased --platform linux` shows only the Linux size column.
- `pip install git+https://...` install instructions in README.
- `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`, `CHANGELOG.md`.
- GitHub Actions CI (test + lint on push/PR) and release workflow (PyPI publish + GitHub release on tag).
- `[project.urls]` in `pyproject.toml`.
- MIT `LICENSE` file.

### Changed
- GOG OAuth credentials (`_CLIENT_ID`, `_CLIENT_SECRET`, `_TOKEN_URL`) deduplicated — defined in `api.py` only, imported by `auth.py`.
- `AGENTS.md` is now the single source of agent instructions; `CLAUDE.md` is a thin pointer to it.

### Fixed
- `project.urls` section was misplaced in `pyproject.toml`, causing `pip install` from git to fail.

---

## [0.1.0] — 2026-06-27

### Added
- `gog auth login / status / logout` — browser-based GOG OAuth flow, token stored locally.
- `gog refresh` — fetch purchased library and per-game download metadata into local cache.
- `gog list purchased` — browse owned games with filtering (platform, year, genre, search) and size columns.
- `gog list backup` — inspect a backup manifest.
- `gog search` — search the public GOG catalog without authentication.
- `gog plan` — show a dry-run backup plan without downloading anything.
- `gog backup` — download game installers to a local directory with manifest tracking.
- `gog sync` — update stale backups incrementally.
- `--games-from` selector file support.
- `--sort` on list commands.
- JSON output format (`--format json`) on all read commands.
- Resumable downloads and checksum verification where GOG provides checksums.
- `aria2c` downloader backend (`--downloader aria2c`).
- XDG-compliant state/cache paths; optional OS keyring for refresh token.
