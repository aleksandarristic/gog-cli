# Changelog

All notable changes to this project will be documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versions follow [Semantic Versioning](https://semver.org/).

---

## [Unreleased]

### Fixed
- Download entry display names are no longer mistaken for local filenames;
  actual artifact names come from explicit metadata, GOG response headers, or
  the final signed CDN URL. This preserves every part of split installers.
- OAuth tokens are redacted from refresh errors and real-test command reports.
- Missing checksum XML documents advertised by GOG are treated as unavailable
  checksums instead of blocking bonus-content downloads; malformed documents
  and other fetch failures remain errors.
- Sync no longer treats a checksum XML's exact verified size as stale merely
  because cached product metadata contains a rounded size estimate.
- `gog sync` retries failed records and restores files that are recorded in the
  manifest but missing from disk.
- Sync checks files at their manifest-recorded paths, including filenames that
  were supplied by GOG at download time.
- Free-space checks use the nearest existing parent when the requested backup
  destination has not been created yet.
- `gog auth status` refreshes an expired access token when the stored refresh
  token is still valid.
- Unknown `--role` values now return a usage error instead of silently selecting
  no files.

### Documentation
- Added an opt-in real-download E2E matrix covering single-game and selector-
  file workflows, platform-specific installers, extras, direct downloads, and
  `aria2c` downloads.

---

## [1.0.1] — 2026-08-02

### Fixed
- Existing installers remain intact until replacement downloads complete and
  pass verification, for both direct and `aria2c` downloads.
- Sanitized game-directory and installer-name collisions are disambiguated or
  rejected before they can overwrite another backup.
- Per-game download metadata now expires after two weeks instead of remaining
  cached indefinitely.
- CLI flags correctly override configuration defaults, non-interactive mode is
  honored, and JSON output stays valid for complete backup and sync workflows.
- Refresh tokens are omitted from session JSON when OS-keyring storage succeeds.
- Network, verification, and filesystem failures return their documented exit
  codes instead of generic failures or uncaught tracebacks.

### Added
- JSON output support for `gog sync` plans and execution.

---

## [1.0.0] — 2026-07-25

### Fixed
- Multi-file installer entries lacking a per-file id collided on the same
  destination path and manifest `file_id`, silently dropping every part but
  the first.
- `Downloader.download()`/`download_via_aria2c()` treated any pre-existing
  destination file as done without checking size, masking the collision
  above (and any other stale/partial file).
- Bonus-content files with no real checksum were hard-failing on GOG's
  imprecise declared size.
- `aria2c` is now used automatically when present on `PATH`, falling back to
  the direct downloader otherwise.

### Added
- `gog download`/`gog dl` aliases for `backup`; `gog help <command>`.
- Fuzzy, positional `GAME` selector on `plan`/`backup`/`download`/`dl`/`sync`,
  with interactive disambiguation when a fuzzy match is ambiguous.
- `gog list` alone lists purchased games; `gog list TEXT` is fuzzy-search
  shorthand. `--backup`/`--back` list the backup manifest.
- `--win`/`--windows`, `--mac`, `--lin`/`--linux` platform shortcuts and
  `-r`/`--role`/`--extras` file-role filter.

### Changed
- `--destination` defaults to the current directory instead of erroring
  when omitted.
- Neither `purchased` nor `backup` is a reserved word under `gog list`
  anymore — a game actually titled either one is never shadowed.

---

## [0.3.0] — 2026-06-30

### Added
- Size-aware `aria2c` download option policies with `auto`, `conservative`, and
  `aggressive` modes.
- `aria2c_policy` config file key and `GOG_CLI_ARIA2C_POLICY` environment
  variable.
- Dedicated config reference documentation.

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
