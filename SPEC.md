# gog CLI Spec

## Purpose

`gog` is a pip-installable Python CLI for backing up a user's owned DRM-free GOG game library to a local directory.

The tool is for personal archival of legitimately owned games. It should not include piracy-oriented behavior, shared-library downloading, or bypasses for access controls.

## Install And Command Name

- The Python package should be pip installable.
- The installed console command should be `gog`.
- The repository/package may keep the project name `gog-dl`, but user-facing CLI examples should use `gog`.

## Core Commands

### `gog list purchased`

Lists games owned by the authenticated GOG account.

Expected behavior:

- Shows one row per owned game.
- Includes at least title and stable game/product identifier.
- Should support machine-readable output later, likely `--format json`.
- Should work from cached metadata when available, with a clear indicator if data is stale.
- Should not require a backup destination.

Initial examples:

```sh
gog list purchased
gog list purchased --format json
```

### `gog list backed-up`

Lists games already present in the local backup destination.

Expected behavior:

- Requires or discovers a configured backup destination.
- Shows one row per backed-up game.
- Includes title, stable game/product identifier, backed-up installer versions/builds, and last backup timestamp when known.
- Marks incomplete, partially downloaded, or unverifiable backups clearly.
- Should support machine-readable output later, likely `--format json`.

Initial examples:

```sh
gog list backed-up --destination /mnt/backups/gog
gog list backed-up --destination /mnt/backups/gog --format json
```

### `gog refresh`

Refreshes the local cache of purchased games and available download metadata.

Expected behavior:

- Authenticates with GOG as needed.
- Navigates or queries GOG account/library pages or APIs to discover purchased games.
- Parses the relevant GOG website/API responses into local cache metadata.
- Updates the local cache without downloading game installers.
- Reports added, removed, renamed, and changed games when detectable.
- Fails clearly when GOG page structure or response shape is no longer understood.

Initial examples:

```sh
gog refresh
gog refresh --force
```

### `gog backup`

Backs up owned games to a local directory.

Expected behavior:

- Requires a destination directory.
- Creates the destination directory if it does not exist.
- Downloads installers and related offline backup files for owned DRM-free games.
- Preserves metadata next to downloaded files.
- Skips already downloaded files when they match expected metadata.
- Resumes interrupted downloads where feasible.
- Does not delete local files unless a future explicitly named command or flag requires it.
- Can operate interactively by default, allowing users to select games with checkboxes.
- Can operate non-interactively when filters or selection arguments are provided.

Initial examples:

```sh
gog backup --destination /mnt/backups/gog
gog backup --destination /mnt/backups/gog --dry-run
gog backup --destination /mnt/backups/gog --game cyberpunk-2077
gog backup --destination /mnt/backups/gog --all --yes
```

### `gog sync`

Synchronizes a local backup destination with the latest available purchased-game installers.

Expected behavior:

- Compares the purchased-games cache against local backup metadata.
- Detects stale backups, such as games with newer installer builds, patches, extras, or language/platform files.
- Downloads missing or updated files.
- Skips files that are already current and verified.
- Supports dry-run mode to show the sync plan before changing files.
- Can operate interactively by default, allowing users to select stale games with checkboxes.
- Can operate non-interactively with explicit flags for scripts.

Initial examples:

```sh
gog sync --destination /mnt/backups/gog
gog sync --destination /mnt/backups/gog --dry-run
gog sync --destination /mnt/backups/gog --all --yes
```

## Authentication

The CLI needs to let users log in once and maintain a reusable authenticated session for listing, refreshing, backing up, and syncing.

Recommended approach:

- Primary login should use a browser-based GOG login flow.
- The CLI should not ask for or handle the user's GOG password directly.
- After browser login, capture an authorization code through a localhost callback or a manual paste fallback.
- Exchange the authorization code for an access token and refresh token.
- Keep short-lived access tokens in memory or local cache with expiry metadata.
- Store refresh tokens in the OS keyring when available.
- Automatically refresh access tokens before authenticated requests when the refresh token is still valid.
- If refresh fails, mark the session expired and ask the user to run `gog auth login` again.

Requirements:

- Do not print credentials, access tokens, refresh tokens, cookies, or session secrets.
- Do not commit credentials or put them in repo-local files.
- Prefer OS keyring or another secure local storage approach if practical.
- If plain local token storage is implemented, it must be an explicit documented tradeoff.
- Session state should be user-scoped and should not live under the backup destination.
- Logout should remove stored refresh tokens and cached access tokens.

Expected commands:

```sh
gog auth login
gog auth status
gog auth logout
```

Fallback options:

- Support manual paste of the redirect URL or auth code for headless/remote environments.
- Support a browser-exported Netscape-format cookies file as the worst-case authentication fallback if token login is not sufficient for needed GOG pages.
- Cookie-file auth should accept an explicit path, such as `gog auth import-cookies ./cookies.txt`.
- Imported cookies should be copied into user-scoped app storage with restrictive file permissions, or referenced from the provided path only if the user explicitly asks for that behavior.
- Cookie-file auth must not copy cookies into the backup destination.
- Cookie-file auth must be documented as less desirable because cookies can grant broad website session access, expire unpredictably, and may require manual re-export from the browser.
- `gog auth status` should indicate when the active session is backed by imported cookies instead of refresh-token auth.

Initial fallback example:

```sh
gog auth import-cookies ./gog-cookies.txt
gog auth status
```

Open questions:

- Which exact auth endpoint/client parameters should be treated as supported enough for this tool?
- Should token storage require the Python `keyring` package, or should it be an optional extra with a file-based fallback?
- What should the headless login path look like for SSH-only machines?

## Backup Layout

The exact directory layout is not finalized.

Requirements:

- File names should be stable and safe on common filesystems.
- Metadata should make backups auditable and restorable.
- The layout should tolerate renamed games and updated installers.
- The tool should avoid overwriting existing files unless it can verify the replacement is correct.

Candidate layout:

```text
DESTINATION/
  metadata/
    library.json
  games/
    <game-slug>/
      metadata.json
      installers/
      extras/
```

## Metadata

Metadata should include, when available:

- game title
- stable GOG game/product id
- installer file name
- installer size
- version/build information
- platform
- language
- checksum/hash
- source URL or source descriptor
- download timestamp

## Download Behavior

Requirements:

- Support direct downloads using the CLI's built-in Python downloader.
- Support delegated downloads to an external downloader, with `aria2c` as the first target.
- Prefer resumable downloads.
- Write partial downloads to temporary files before finalizing.
- Verify size and checksum when available.
- Use clear progress output for humans.
- Keep stdout/stderr behavior scriptable.
- Return non-zero exit codes for failed downloads.
- Support dry-run planning before downloading.

Downloader selection:

- Direct download should be the default because it has the fewest external requirements.
- Users should be able to select an external downloader explicitly, for example `--downloader aria2c`.
- The CLI should validate that the selected downloader exists before starting a long-running backup or sync.
- External downloader integration should pass cookies/auth headers safely without printing secrets.
- External downloader integration should still produce metadata and verification results controlled by `gog`.
- The tool should surface the external downloader's failure clearly and return a non-zero exit code.

Initial examples:

```sh
gog backup --destination /mnt/backups/gog --downloader direct
gog backup --destination /mnt/backups/gog --downloader aria2c
gog sync --destination /mnt/backups/gog --downloader aria2c --all --yes
```

## Interactive And Scripted Use

The CLI should support both interactive terminal use and scripted automation.

Interactive behavior:

- When attached to a TTY, commands that select games may present checkbox-style prompts.
- Interactive selectors should support searching/filtering before confirming a selection.
- Interactive commands should preview what will be downloaded or changed before starting a long-running operation.
- Interactive mode must never hide destructive behavior behind an implicit default.

Scripted behavior:

- Every interactive workflow needs equivalent flags for non-interactive use.
- Commands should support explicit selectors such as `--all`, `--game`, `--exclude`, `--platform`, and `--language` where appropriate.
- Commands that make changes should support `--yes` or an equivalent confirmation bypass for automation.
- Commands should support `--no-interactive` to fail instead of prompting.
- Machine-readable output should be available for list and plan workflows.

## Output And Exit Codes

Output should be useful for both people and scripts.

Requirements:

- Human-readable output by default.
- Machine-readable output should be added for list/plan workflows.
- Errors should go to stderr.
- Successful command output should go to stdout.
- Non-zero exit codes should distinguish user errors, auth failures, network failures, and verification failures once those cases exist.

## GOG Website/API Understanding

The tool must be able to discover and understand the user's GOG library well enough to present it through the CLI.

Requirements:

- Prefer official or stable documented interfaces where they exist.
- If GOG website parsing is required, isolate parser code from command logic.
- Parser failures should explain which page or response type was not understood without printing secrets.
- Keep captured fixtures or sanitized sample responses for parser tests when legally and practically acceptable.
- Treat GOG HTML/API shape changes as expected maintenance events and make failures diagnosable.

## Python Engineering Standards

The Python implementation should follow current CLI application best practices and keep operational behavior predictable.

Project structure:

- Use a `src/` layout.
- Keep the import package named `gog_dl` unless there is a strong reason to rename it.
- Keep the installed console command named `gog`.
- Keep command parsing thin; put business logic in testable modules outside the CLI entrypoint.
- Keep dependencies conservative and purposeful.

CLI hygiene:

- Use clear command names, stable flags, and helpful `--help` text.
- Support `--version`.
- Support `--verbose` and/or `--quiet` once logging is wired.
- Prefer explicit flags over implicit environment-dependent behavior.
- Ensure commands are safe in both TTY and non-TTY contexts.

Logging:

- Use Python's `logging` module for diagnostics.
- Do not use logging for primary command output; reserve stdout for user-requested results.
- Send logs and errors to stderr.
- Default logging should be quiet enough for normal CLI use.
- Verbose/debug logging must not print secrets, tokens, cookies, auth headers, or signed download URLs.
- Long-running operations should have useful progress/status output without making scripted output hard to parse.

Formatting and linting:

- Use Ruff for linting and formatting.
- Store Ruff configuration in `pyproject.toml`.
- Prefer a strict but practical Ruff rule set.
- Run Ruff in CI once CI exists.
- Keep generated caches such as `.ruff_cache/` gitignored.

Typing:

- Use type hints for public functions and core domain objects.
- Prefer `pathlib.Path` for filesystem paths.
- Prefer dataclasses or typed models for metadata structures.
- Avoid passing unstructured dictionaries deep into the application when a typed object would be clearer.

Testing:

- Use pytest.
- Keep CLI tests focused on command behavior, exit codes, stdout, and stderr.
- Unit-test parsers with sanitized fixtures.
- Unit-test download planning separately from actual network transfers.
- Integration tests that hit GOG should be opt-in and skipped by default.

Packaging:

- Keep the package pip installable with `pyproject.toml`.
- The console script should be declared through project scripts.
- Avoid import-time network calls, filesystem writes, or logging configuration side effects.

Filesystem hygiene:

- Use platform-appropriate user config/cache/state directories instead of writing hidden state into the repo.
- Keep auth/session state separate from backup data.
- Write files atomically where practical.
- Use temporary files for partial downloads.
- Be careful with cross-platform filename safety even if the first target environment is Linux.

## Non-Goals For Now

- Cloud backup integration.
- GUI or TUI.
- Multi-account library merging.
- Sharing downloaded games.
- Circumventing GOG access controls.
- Deleting local backups as part of normal backup runs.

## Open Decisions

- Authentication strategy.
- Exact GOG API/interface to use.
- Whether to store metadata in JSON only or also use SQLite for local cache/indexing.
- Whether `backup` should back up all games by default or require explicit interactive/flag selection.
- Filtering flags for game, platform, language, installer type, and updated-since behavior.
- Final backup directory layout.
- Exact Ruff rule set.
- Whether to use only `argparse` or adopt a CLI framework such as Typer or Click.
