# CLI Reference

Complete reference for all `gog` commands, flags, configuration, and exit
codes.

---

## Contents

1. [Overview](#overview)
2. [Configuration](#configuration)
3. [Commands](#commands)
   - [gog auth](#gog-auth)
   - [gog refresh](#gog-refresh)
   - [gog list purchased](#gog-list-purchased)
   - [gog list backup](#gog-list-backup)
   - [gog search](#gog-search)
   - [gog plan](#gog-plan)
   - [gog backup](#gog-backup)
   - [gog sync](#gog-sync)
4. [Game Selectors](#game-selectors)
5. [Backup Directory Layout](#backup-directory-layout)
6. [Exit Codes](#exit-codes)
7. [Common Workflows](#common-workflows)

---

## Overview

`gog` backs up owned DRM-free GOG games to a local directory. Commands are
designed to be explicit, scriptable, and non-destructive by default:

- `backup` and `sync` print a dry-run plan and exit without downloading unless
  `--yes` is passed.
- No files in a backup destination are deleted or overwritten unless the
  command explicitly requires it.
- Credentials are stored in app state and never written into backup directories.

The typical lifecycle is: authenticate → refresh local library cache → plan →
backup → sync as updates arrive.

---

## Configuration

Configuration is resolved from three sources in order of increasing priority:

1. Built-in defaults
2. TOML config file
3. Environment variables

CLI flags override all three.

### Config file

The config file is loaded from:

```
$XDG_CONFIG_HOME/gog-cli/config.toml   (default: ~/.config/gog-cli/config.toml)
```

All keys are optional and live under a `[defaults]` table:

```toml
[defaults]
destination  = "/path/to/backups"    # default --destination for backup/sync/plan
downloader   = "direct"              # "direct" or "aria2c"
platforms    = ["windows", "linux"]  # restrict to these platforms by default
languages    = ["en"]                # restrict to these language codes by default
file_roles   = []                    # restrict to these file roles (empty = all)
format       = "human"               # "human" or "json"
interactive  = true                  # false = fail instead of prompting
```

`file_roles` accepts any combination of: `installer`, `patch`, `language_pack`,
`extra`, `manual`.

### Environment variables

| Variable | Equivalent config key | Notes |
|---|---|---|
| `GOG_CLI_DESTINATION` | `destination` | Path to backup root |
| `GOG_CLI_DOWNLOADER` | `downloader` | `direct` or `aria2c` |
| `GOG_CLI_PLATFORMS` | `platforms` | Comma-separated, e.g. `windows,linux` |
| `GOG_CLI_LANGUAGES` | `languages` | Comma-separated, e.g. `en,de` |
| `GOG_CLI_FILE_ROLES` | `file_roles` | Comma-separated |
| `GOG_CLI_FORMAT` | `format` | `human` or `json` |
| `GOG_CLI_INTERACTIVE` | `interactive` | `1`/`true`/`yes` or `0`/`false`/`no` |

### App state directories

gog-cli follows XDG conventions for all state, cache, and config files:

| Purpose | Default path |
|---------|-------------|
| Config file | `~/.config/gog-cli/config.toml` |
| Library cache | `~/.cache/gog-cli/library.json` |
| Download metadata cache | `~/.cache/gog-cli/downloads/<product_id>.json` |
| Session state | `~/.local/share/gog-cli/session.json` |

The `XDG_CONFIG_HOME`, `XDG_CACHE_HOME`, and `XDG_DATA_HOME` environment
variables are respected if set.

---

## Commands

### gog auth

Manages the local GOG session. Tokens are stored in app state directories and
never inside backup destinations.

---

#### gog auth login

```
gog auth login
```

Starts the browser-based GOG login flow. Prints a login URL to open in any
browser. After a successful GOG login, the browser redirects to a GOG URL
containing a `code` parameter. The full redirect URL or the bare `code` value
can be pasted at the prompt.

The access token is stored in session state and permissions are set to `0600`.
The refresh token is stored in the OS keyring if available; otherwise it falls
back to file-only storage with a warning.

**Output:**

```
Open this URL in your browser and log in:

  https://auth.gog.com/auth?client_id=...

After logging in, paste the full redirect URL (or just the code value):
> https://embed.gog.com/on_login_success?origin=client&code=abc123

Logged in as your_username.
```

**Exit codes:** `0` on success, `2` on cancelled input, `3` on token exchange
failure.

---

#### gog auth status

```
gog auth status
```

Shows whether a valid local session exists and when the access token expires.

**Output (logged in):**

```
Logged in as your_username. Token expires 2026-07-01T12:00:00Z.
```

**Output (not logged in or expired):**

```
Not logged in. Run: gog auth login
```

or

```
Token expired. Run: gog auth login
```

**Exit codes:** `0` if a valid session exists, `3` if not logged in or expired.

---

#### gog auth logout

```
gog auth logout
```

Removes the local session state file and deletes the refresh token from the OS
keyring (if present). Does not contact GOG servers.

**Output:**

```
Logged out.
```

**Exit codes:** `0` on success, `6` on filesystem error.

---

### gog refresh

```
gog refresh [--force] [--format {human,json}]
```

Fetches purchased-library and per-game download metadata from GOG into the
local cache. Does not download game installers.

Two network operations are performed:

1. The paginated library endpoint is iterated to build the local game list.
2. For each game, download metadata (installer list, file sizes, downlink URLs)
   is fetched and cached individually. Files cached within the last 24 hours
   are skipped unless `--force` is used.

**Flags:**

| Flag | Description |
|------|-------------|
| `--force` | Re-fetch all download metadata even if recently cached |
| `-f`, `--format` | Output format: `human` (default) or `json` |

**Examples:**

```sh
gog refresh
gog refresh --force
gog refresh --format json
```

**When to run:** Run before browsing the library or planning backups after
adding new games to a GOG account. Does not need to be run before every backup;
the download metadata cache remains valid for 24 hours.

**Exit codes:** `0` on success, `3` if not authenticated, `4` on network
error.

---

### gog list purchased

```
gog list purchased [filters] [--sort COLUMN] [--format {human,json}]
```

Lists owned games from the local cache written by `gog refresh`. Does not
contact GOG.

Human output includes: product ID, title, release year, genre/category,
per-platform size columns (Windows / Mac / Linux), extras size, and total size.
JSON output includes all cached metadata fields plus `owned`, `release_date`,
`genres`, `is_installable`, and download size summaries.

**Flags:**

| Flag | Short | Description |
|------|-------|-------------|
| `--format` | `-f` | `human` (default) or `json` |
| `--platform PLATFORM` | `-p` | Filter by platform: `windows`, `mac`, `linux`. Repeatable. |
| `--year RANGE` | `-y` | Filter by release year. Range format: `1998..2005`, `2010..`, `..2000`. |
| `--include-unknown-year` | | Keep games with unknown release year when `--year` is used. |
| `--genre GENRE` | `-G` | Filter by genre/category/tag. Repeatable; comma-separated values allowed. |
| `--include-unknown-genre` | | Keep games with unknown genre when `--genre` is used. |
| `--search TEXT` | `-s` | Fuzzy title search. |
| `--sort COLUMN` | `-S` | Sort by `title` (A–Z), `year` (oldest first), or `size` (largest first). |

**Year range syntax:**

| Expression | Meaning |
|-----------|---------|
| `1998..2005` | 1998 through 2005 inclusive |
| `2010..` | 2010 and later |
| `..2000` | 2000 and earlier |
| `2020` | Single year (not a range) |

Year filters exclude games with unknown release years by default. Pass
`--include-unknown-year` to keep them.

**Examples:**

```sh
gog list purchased
gog list purchased --search witcher
gog list purchased --search "baldurs gate"
gog list purchased --platform linux
gog list purchased --platform windows --platform linux
gog list purchased --year 1998..2005
gog list purchased --year 2010.. --include-unknown-year
gog list purchased --genre strategy
gog list purchased --genre arcade,rts
gog list purchased --genre rpg --include-unknown-genre
gog list purchased --sort size
gog list purchased --search witcher --platform linux --format json
```

**Exit codes:** `0` on success, `1` if the library cache is missing (run `gog
refresh`), `7` if the cache is corrupt.

---

### gog list backup

```
gog list backup [--destination PATH] [--sort COLUMN] [--format {human,json}]
```

Reads the backup manifest at a destination directory and summarizes the games
and files recorded there. Does not contact GOG or read actual downloaded files.

Human output columns: title, slug, status, file count, total size.
JSON output returns the full manifest game array.

**Flags:**

| Flag | Short | Description |
|------|-------|-------------|
| `--destination PATH` | `-d` | Backup destination to inspect. Falls back to config `destination`. |
| `--format` | `-f` | `human` (default) or `json` |
| `--sort COLUMN` | `-S` | Sort by `title` (A–Z), `size` (largest first), `status` (A–Z), or `files` (most first). |

**Game status values:**

| Status | Meaning |
|--------|---------|
| `current` | All files verified |
| `unverified` | Downloaded but not yet verified |
| `partial` | Some files downloaded, some missing |
| `stale` | Metadata indicates updates are available |
| `error` | One or more files failed |
| `missing` | No files recorded |

**Examples:**

```sh
gog list backup --destination /backups/gog
gog list backup --destination /backups/gog --sort size
gog list backup --destination /backups/gog --format json
```

**Exit codes:** `0` on success, `6` if the manifest is missing, `7` if the
manifest is corrupt or has an unsupported schema version.

---

### gog search

```
gog search QUERY [--platform PLATFORM] [--year RANGE] [--genre GENRE] [--format {human,json}]
```

Searches the public GOG catalog. Results are public catalog entries and are not
filtered by ownership. Use `gog list purchased` for owned-library data.

**Arguments:**

| Argument | Description |
|----------|-------------|
| `QUERY` | Title keywords to search for. |

**Flags:**

| Flag | Short | Description |
|------|-------|-------------|
| `--format` | `-f` | `human` (default) or `json` |
| `--platform PLATFORM` | `-p` | Filter by platform. Repeatable. |
| `--year RANGE` | `-y` | Filter by release year range (same syntax as `list purchased`). |
| `--genre GENRE` | `-G` | Filter by genre/category/tag. Repeatable. |

**Examples:**

```sh
gog search witcher
gog search "baldurs gate" --platform windows
gog search strategy --year 2000..2010
gog search rpg --genre "role-playing" --format json
```

**Exit codes:** `0` on success, `4` on network error.

---

### gog plan

```
gog plan [--destination PATH] [selectors...] [game selection flags] [output flags]
```

Shows a non-destructive backup plan without downloading files or creating
backup directories. Equivalent to `gog backup --dry-run`. Useful for
estimating download size, inspecting filter effects, and checking disk space
before a long backup run.

**Arguments:**

| Argument | Description |
|----------|-------------|
| `GAME` (positional, repeatable) | Game selector by product ID, slug, or exact title. |

**Flags:**

| Flag | Short | Description |
|------|-------|-------------|
| `--destination PATH` | `-d` | Backup destination directory. Falls back to config. |
| `--format` | `-f` | `human` (default) or `json` |
| `--storage` | | Show disk usage line (required, free, and OK/INSUFFICIENT). |
| `--check-free-space` | | Fail with exit code 6 if free disk space is less than estimated download size. Also implies `--storage`. |
| `--summary` | | Print summary header only; omit per-game file detail. |
| `--changed-only` | | In per-game detail, show only games with pending downloads. |
| `--explain-skips` | | Annotate skipped files with their filter reason. |

Game selection flags (`--all`, `--game`, `--games-from`, `--exclude`,
`--platform`, `--language`) are described in [Game Selectors](#game-selectors).

**Human output sections:**

```
Backup plan — /backups/gog
Policy: platforms=all  languages=all  roles=all
Scope: 120 owned | 120 selected | 98 complete | 22 need downloads | 5 missing locally

Downloads: 47 file(s)  •  18.3 GB estimated
Local state: 312 already present  •  0 orphaned
─────────────────────────────────────────────────────────────────────────
witcher_3 — The Witcher 3: Wild Hunt
  +  setup_the_witcher_3_1.3.6.exe         installer    windows    22.1 GB
  =  witcher3_ost.zip                      extra        -          (present)
cyberpunk_2077 — Cyberpunk 2077  (complete)
  =  setup_cyberpunk_2077_2.1.exe          installer    windows    (present)
─────────────────────────────────────────────────────────────────────────

Dry run — no files were downloaded. Re-run with --yes to execute.
```

Line prefixes in per-game detail:

| Prefix | Meaning |
|--------|---------|
| `+` | Will be downloaded |
| `=` | Already present, no action needed |
| `-` | Skipped by filter |

**JSON output shape:**

```json
{
  "command": "backup plan",
  "data": {
    "target_directory": "/backups/gog",
    "mode": "dry_run",
    "scope": "all",
    "summary": {
      "owned_games": 120,
      "selected_games": 120,
      "complete_games": 98,
      "games_needing_updates": 22,
      "games_missing_locally": 5,
      "already_present_files": 312,
      "new_files": 47,
      "total_download_files": 47,
      "total_download_bytes": 19654058278,
      "orphaned_local_files": 0
    },
    "disk": {
      "free_bytes": 107374182400,
      "required_bytes": 19654058278,
      "enough_space": true
    },
    "actions": [
      {
        "game_id": "1207664663",
        "slug": "witcher_3",
        "title": "The Witcher 3: Wild Hunt",
        "actions": [
          {
            "action": "download",
            "source_id": "en1installer1",
            "filename": "setup_the_witcher_3_1.3.6.exe",
            "role": "installer",
            "platform": "windows",
            "language": "en",
            "size_bytes": 23748239360
          }
        ]
      }
    ],
    "skipped": []
  }
}
```

**Examples:**

```sh
gog plan --destination /backups/gog --all
gog plan --destination /backups/gog --all --storage
gog plan --destination /backups/gog --all --check-free-space
gog plan --destination /backups/gog --all --summary
gog plan --destination /backups/gog --all --changed-only
gog plan --destination /backups/gog --all --format json
gog plan --destination /backups/gog --all --platform linux --storage
gog plan --destination /backups/gog --all --platform windows --language en
gog plan --destination /backups/gog cyberpunk_2077
gog plan --destination /backups/gog --games-from games.txt --summary
```

**Exit codes:** `0` on success, `2` on usage error, `6` if `--check-free-space`
fails, `8` if the library cache is missing (run `gog refresh`).

---

### gog backup

```
gog backup --destination PATH [game selection flags] [interaction flags] [output flags]
```

Plans or executes a local backup. Without `--yes`, prints a dry-run plan and
exits without downloading files or modifying the backup destination. With
`--yes`, executes the plan and updates the backup manifest after each file.

**Required flags:**

| Flag | Short | Description |
|------|-------|-------------|
| `--destination PATH` | `-d` | Directory where game backups are stored. Required unless set in config. |

**Output flags:**

| Flag | Short | Description |
|------|-------|-------------|
| `--format` | `-f` | `human` (default) or `json` |
| `--storage` | | Show disk usage section in plan output. |
| `--check-free-space` | | Fail before downloading if free space is less than estimated size. |
| `--summary` | | Print summary only in the plan; omit per-game file detail. |
| `--changed-only` | | Show only games with pending downloads in per-game detail. |
| `--explain-skips` | | Annotate skipped files with their filter reason in per-game detail. |
| `--dry-run` | | Show the plan and exit without downloading. Implied when `--yes` is absent. |

**Interaction flags:**

| Flag | Short | Description |
|------|-------|-------------|
| `--yes` | | Execute the plan; skip confirmation. Without this flag, backup always dry-runs. |
| `--no-interactive` | `-n` | Fail rather than prompt when no games are selected. |
| `--downloader` | `-D` | Download engine: `direct` (default) or `aria2c`. |

Game selection flags are described in [Game Selectors](#game-selectors).

**Downloader behaviour:**

- `direct`: built-in streaming downloader using `requests`. Supports HTTP range
  resumption (`Range: bytes=N-`). No additional dependencies required.
- `aria2c`: delegates to the `aria2c` binary, which must be installed and on
  `PATH`. Supports multi-connection downloads. Pass
  `--downloader aria2c` to enable.

**Execution output (human):**

During execution each file is printed on completion:

```
downloaded  The Witcher 3: Wild Hunt / installer / windows
verified    Cyberpunk 2077 / extra / -
failed      Control / installer / linux — resolve_failed: ...
```

Followed by a summary:

```
Summary: 46 succeeded, 1 failed.
```

**Execution output (JSON):**

With `--format json` the output is a JSON envelope containing one entry per
processed file:

```json
{
  "command": "backup",
  "data": [
    {
      "product_id": "1207664663",
      "title": "The Witcher 3: Wild Hunt",
      "source_id": "en1installer1",
      "name": "setup_the_witcher_3_1.3.6.exe",
      "role": "installer",
      "platform": "windows",
      "language": "en",
      "status": "downloaded",
      "path": "/backups/gog/games/witcher_3/installers/setup_the_witcher_3_1.3.6.exe",
      "failure_code": null,
      "failure_message": null
    }
  ]
}
```

**Manifest:** The backup manifest (`<destination>/metadata/manifest.json`) is
updated atomically after each file. If the process is interrupted, completed
files are recorded and a resumed run will skip them.

**Examples:**

```sh
# Dry run for all games (default — no --yes)
gog backup --destination /backups/gog --all

# Execute backup for all games
gog backup --destination /backups/gog --all --yes

# Execute with aria2c for games in a selector file
gog backup --destination /backups/gog --games-from games.txt --downloader aria2c --yes

# Linux-only installers, English only
gog backup --destination /backups/gog --all --platform linux --language en --yes

# Check disk space before downloading
gog backup --destination /backups/gog --all --check-free-space --yes

# Exclude a game from --all
gog backup --destination /backups/gog --all --exclude cyberpunk_2077 --yes

# JSON output for scripting
gog backup --destination /backups/gog --all --yes --format json
```

**Exit codes:** `0` on success, `1` if any file failed, `2` on usage error,
`3` on authentication failure, `4` on network error, `6` if disk space check
fails or destination is not a directory, `8` if the library cache is missing.

---

### gog sync

```
gog sync --destination PATH [game selection flags] [interaction flags]
```

Compares cached source metadata against the backup manifest and plans updates
for stale or missing files. Without `--yes`, prints a dry-run plan and exits.
With `--yes`, executes the plan.

`gog sync` requires an existing backup manifest (i.e., `gog backup` must have
been run at least once for the destination).

**Required flags:**

| Flag | Short | Description |
|------|-------|-------------|
| `--destination PATH` | `-d` | Backup destination directory to sync. Required unless set in config. |

**Flags:**

| Flag | Description |
|------|-------------|
| `--dry-run` | Print the plan and exit. Implied when `--yes` is absent. |
| `--yes` | Execute the sync. |
| `--no-interactive` / `-n` | Fail rather than prompt when no games are selected. |
| `--downloader` / `-D` | `direct` (default) or `aria2c`. |

Game selection flags are described in [Game Selectors](#game-selectors).

**Plan output:**

```
Plan: 12 files to download, 3 to verify.
38 files current. 15 files need work.
Estimated bytes: 4831838208.
```

**Examples:**

```sh
# Dry run (default)
gog sync --destination /backups/gog --all

# Execute sync for all games
gog sync --destination /backups/gog --all --yes

# Sync a curated list
gog sync --destination /backups/gog --games-from games.txt --yes

# Dry run with aria2c ready
gog sync --destination /backups/gog --all --downloader aria2c --dry-run
```

**Exit codes:** `0` on success, `1` if any file failed, `2` on usage error,
`3` on authentication failure, `6` if the manifest is missing.

---

## Game Selectors

The `plan`, `backup`, and `sync` commands share a common set of game selection
flags. Selectors are matched against the local library cache written by
`gog refresh`.

### Selection flags

| Flag | Short | Description |
|------|-------|-------------|
| `--all` | `-a` | Select all owned games. |
| `--game SELECTOR` | `-g` | Select a game by product ID, slug, or exact title. Repeatable. |
| `--games-from PATH` | `-F` | Read selectors from a UTF-8 text file, one per line. Repeatable. |
| `--exclude SELECTOR` | `-x` | Exclude a game. Repeatable. Combinable with `--all`. |
| `--platform PLATFORM` | `-p` | Restrict downloads to this platform (`windows`, `mac`, `linux`). Repeatable. |
| `--language LANG` | `-l` | Restrict downloads to this language code (e.g. `en`, `de`, `fr`). Repeatable. |

`--all` and explicit selectors (`--game`, `--games-from`) are mutually
exclusive. The `--exclude` flag is combinable with any selection method.

When no selector flags are provided and the terminal is interactive, a numbered
prompt is shown to select from the full library. Pass `--no-interactive` or set
`interactive = false` in config to fail instead.

### Selector matching

A selector is matched against a game in order:

1. Exact numeric product ID (e.g. `1207664663`)
2. Exact slug match (e.g. `witcher_3`)
3. Case-insensitive exact title match (e.g. `The Witcher 3: Wild Hunt`)

If no game matches a selector, the command exits with a usage error.

### Selector files

A selector file is a UTF-8 text file, one selector per line. Blank lines and
lines whose first non-whitespace character is `#` are ignored.

```text
# NAS batch 1
witcher_3
cyberpunk_2077
1207664663
```

Multiple `--games-from` files are combined with repeated `--game` flags:

```sh
gog plan --destination /backups/gog \
  --games-from priority.txt \
  --games-from extras.txt \
  --game 1207664663
```

### Filter interaction

`--platform` and `--language` filter the download files within selected games,
not the games themselves. Specifying `--platform linux` selects all games but
only includes their Linux installer files.

If a specified platform or language has no matching files across the selected
games, the command exits with a usage error listing the unmatched values.

---

## Backup Directory Layout

```
<destination>/
├── metadata/
│   ├── manifest.json       # authoritative backup record; updated after each file
│   └── library.json        # snapshot of the library at last backup time
└── games/
    └── <slug>/             # e.g. witcher_3
        ├── metadata.json   # per-game metadata
        ├── installers/     # installer files
        ├── patches/        # patch files
        ├── extras/         # bonus content (soundtracks, artbooks, wallpapers, etc.)
        ├── language-packs/ # language pack files
        └── manuals/        # manual files
```

Directory names under `games/` are derived from the game's slug, with
characters unsafe for cross-platform filenames replaced by `_`. Filenames
within each subdirectory are taken from the `Content-Disposition` response
header when available, falling back to the source file ID.

### manifest.json

The manifest records every file that has been processed by a `backup` or `sync`
run. It is updated atomically (via a temp-file replace) after each individual
file download or verification, so partial runs leave a consistent state.

Top-level fields:

| Field | Description |
|-------|-------------|
| `schema_version` | Integer schema version (currently `1`) |
| `created_at` | ISO 8601 UTC timestamp of first write |
| `updated_at` | ISO 8601 UTC timestamp of last write |
| `tool.name` | `"gog-cli"` |
| `tool.version` | Version that wrote the manifest |
| `backup_root_marker` | Unique identifier for this backup root (UUID) |
| `games` | Array of game records (see below) |

Per-game record fields:

| Field | Description |
|-------|-------------|
| `product_id` | GOG product ID |
| `title` | Game title at backup time |
| `slug` | URL-safe slug |
| `directory` | Relative path under destination (e.g. `games/witcher_3`) |
| `last_backed_up_at` | Timestamp of last file operation for this game |
| `status` | Aggregate game status (see status values in `gog list backup`) |
| `files` | Array of file records |

Per-file record fields:

| Field | Description |
|-------|-------------|
| `file_id` | Stable composite key: `role:platform:language:source_id` |
| `role` | `installer`, `patch`, `extra`, `language_pack`, `manual` |
| `source_id` | Source file identifier from GOG metadata |
| `name` | Local filename |
| `relative_path` | Path relative to backup root |
| `size_bytes` | File size in bytes |
| `expected_md5` | MD5 checksum if available from GOG checksum XML |
| `platform` | `windows`, `osx`, `linux`, or `null` |
| `language` | ISO 639-1 language code or `null` |
| `version` | Installer version string or `null` |
| `status` | `downloaded`, `verified`, `partial`, `failed`, or `stale` |
| `downloaded_at` | ISO 8601 UTC timestamp |
| `verified_at` | ISO 8601 UTC timestamp or `null` |

---

## Exit Codes

All `gog` commands return one of these exit codes:

| Code | Name | Meaning |
|------|------|---------|
| `0` | `SUCCESS` | Command completed successfully |
| `1` | `FAILURE` | One or more files failed to download or verify |
| `2` | `USAGE` | Invalid arguments or missing required input |
| `3` | `AUTH` | Not authenticated, token expired, or auth call failed |
| `4` | `NETWORK` | Network connection error or HTTP failure |
| `5` | `VERIFICATION` | Checksum or size verification failed |
| `6` | `FILESYSTEM` | Destination not a directory, disk space insufficient, or I/O error |
| `7` | `PARSER` | Local cache or manifest is corrupt or has an unexpected shape |
| `8` | `CACHE` | Required local cache is missing (run `gog refresh`) |

Exit codes are stable and suitable for use in scripts and CI pipelines.

---

## Common Workflows

### First-time setup

```sh
pip install gog-cli
gog auth login           # authenticate with GOG
gog refresh              # populate local library and download metadata caches
gog list purchased       # verify the library is populated
```

### Plan before a large backup

```sh
# See what will be downloaded and how much disk space is needed
gog plan --destination /backups/gog --all --storage --check-free-space

# Summary only — skip per-game file detail
gog plan --destination /backups/gog --all --summary
```

### First full backup

```sh
gog backup --destination /backups/gog --all --yes
```

### Incremental sync after new purchases

```sh
gog refresh              # pick up newly purchased games
gog sync --destination /backups/gog --all --yes
```

### Backup a curated list of games

```sh
# Create games.txt
cat > games.txt <<EOF
# Priority games
witcher_3
cyberpunk_2077
1207664663
EOF

gog plan --destination /backups/gog --games-from games.txt --storage
gog backup --destination /backups/gog --games-from games.txt --yes
```

### Linux-only backups

```sh
gog plan --destination /backups/gog --all --platform linux --storage
gog backup --destination /backups/gog --all --platform linux --yes
```

### Multi-platform, single language

```sh
gog backup --destination /backups/gog \
  --all \
  --platform windows \
  --platform linux \
  --language en \
  --yes
```

### Use aria2c for faster downloads

```sh
gog backup --destination /backups/gog --all --downloader aria2c --yes
```

### Inspect what's already backed up

```sh
gog list backup --destination /backups/gog
gog list backup --destination /backups/gog --sort size
gog list backup --destination /backups/gog --format json | jq '.data[] | select(.status != "current")'
```

### Scripting with JSON output

```sh
# Export the full purchased library as JSON
gog list purchased --format json > library.json

# Get the plan as JSON and check if space is sufficient
gog plan --destination /backups/gog --all --format json \
  | jq '.data.disk.enough_space'

# Run backup and capture per-file results
gog backup --destination /backups/gog --all --yes --format json \
  | jq '.data[] | select(.status == "failed")'
```

### Re-check after interrupted run

```sh
# The manifest records what completed. A fresh run skips already-present files.
gog backup --destination /backups/gog --all --yes

# Or inspect what still needs work
gog plan --destination /backups/gog --all --changed-only
```
