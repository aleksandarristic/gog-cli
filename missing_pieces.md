# Missing Spec Pieces

The current `SPEC.md` is a solid product-direction spec, but the following areas need more detail before deep implementation work.

## 1. State And Cache Model

Define where local state lives, what files exist, and what each one means.

Needed decisions:

- purchased library cache location and format
- download metadata cache location and format
- auth/session state location and format
- backup manifest location and format
- per-game backup metadata location and format
- cache invalidation and refresh behavior

## 2. Backup Manifest Contract

The backup manifest should become the local source of truth for `list backed-up`, `sync`, verification, and stale detection.

Needed fields may include:

- stable GOG game/product id
- game title
- game slug
- installer id or source identifier
- installer file name
- installer version/build
- installer size
- checksum/hash when available
- local path
- platform
- language
- downloaded timestamp
- verified timestamp
- source metadata version or refresh timestamp

## 3. Exact Command Semantics

Pin down the default behavior for each command.

Needed decisions:

- Does `gog backup` back up all games by default, or prompt interactively?
- Does `gog sync` refresh the purchased-games cache first, or require `gog refresh`?
- Does `gog list purchased` use cache by default, or always hit GOG?
- Can `--destination` be stored in config?
- What should commands do when cache is missing, stale, or corrupted?

## 4. Selection And Filter Flags

Define how game selection works.

Needed decisions:

- Should `--game` match slug, title, product id, or all of these?
- Can `--game` be provided multiple times?
- How do `--game`, `--exclude`, `--all`, and interactive selection interact?
- What are the default platform and language choices?
- How should installer type filtering work?
- How should `--updated-since` or similar stale/update filters work?

## 5. Config

Define configuration sources and precedence.

Suggested precedence:

1. CLI arguments
2. Environment variables
3. User config file
4. Defaults

Needed decisions:

- config file location
- config file format
- environment variable naming convention
- whether backup destination can be configured globally
- whether downloader, platform, and language defaults can be configured

## 6. Exit Codes

Define an initial exit-code table.

Candidate table:

- `0`: success
- `1`: generic failure
- `2`: bad CLI usage
- `3`: auth/session expired
- `4`: network or download failure
- `5`: verification failure
- `6`: local filesystem failure
- `7`: parser failure due to unexpected GOG response/page shape

## 7. Downloader Interface

Define the contract between `gog` and direct/external downloaders.

Needed decisions:

- how URLs are passed to external downloaders
- how cookies or auth headers are passed without leaking secrets
- whether temporary input files are used for `aria2c`
- retry and concurrency controls
- partial file naming
- who owns final verification
- how external downloader stdout/stderr is captured or displayed
- how external downloader failures map to `gog` exit codes

## 8. Interactive Dependency Choice

Checkbox-style prompts imply an interactive prompt library.

Candidate options:

- `questionary`
- `InquirerPy`
- simple built-in fallback with numbered prompts

Needed decisions:

- which dependency to use
- whether interactive support should be optional
- how the CLI behaves when stdin/stdout are not TTYs
- how search/filtering works inside interactive selection

## 9. GOG Parser Test Strategy

Parser behavior should be tested against sanitized fixtures.

Needed fixtures:

- purchased library response or page
- game downloads response or page
- expired session response
- missing entitlement response
- changed or unsupported page shape
- direct download metadata response

Needed decisions:

- where fixtures live
- how to sanitize fixtures
- whether fixture updates require manual review

## 10. Implementation Phases

Define milestones so implementation stays incremental.

Suggested phases:

1. CLI skeleton, config loading, logging, Ruff, and tests
2. state/cache directories and manifest models
3. auth/session commands
4. refresh purchased cache
5. list purchased and list backed-up
6. direct download backup
7. verification and stale detection
8. sync
9. `aria2c` delegated downloader
10. interactive selection
