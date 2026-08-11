# Real Download E2E Test

The real-download test is a standalone authenticated E2E harness at
[`e2e/real_download.py`](../e2e/real_download.py). It is deliberately outside
`tests/`, is not collected by pytest, and is not run by CI. Running the normal
unit suite never contacts GOG or downloads game files.

The harness uses owned, relatively small games and writes each case to a
separate directory beneath a unique `/tmp/gog-cli-real-e2e-*` root. Artifacts
and a machine-readable `e2e-report.json` are always preserved for inspection.

## Test corpus

| Product ID | Title | Windows | macOS | Linux | Extras | Total |
|---:|---|---:|---:|---:|---:|---:|
| 1207658879 | Raptor: Call of the Shadows 2010 Edition | 43 MiB | - | - | 8 MiB | 51 MiB |
| 1315929054 | Warhammer Skulls 2025 Digital Goodie Bag | - | - | - | 50 MiB | 50 MiB |
| 1207667043 | Mortal Kombat 1 | 25 MiB | 21 MiB | - | - | 46 MiB |
| 1207667053 | Mortal Kombat 2 | 23 MiB | 20 MiB | - | - | 43 MiB |
| 1129701343 | Jill of the Jungle: The Complete Trilogy | 12 MiB | 10 MiB | 6 MiB | 5 MiB | 33 MiB |
| 1449569170 | Bio Menace | 13 MiB | 11 MiB | 7 MiB | - | 31 MiB |

The companion [`e2e/real-download-games.txt`](../e2e/real-download-games.txt)
mixes numeric IDs and exact names. Other cases exercise an ID, exact positional
name, fuzzy positional name, exact `--game`, repeated selectors, platform and
role combinations, and unfiltered all-file selection.

## Safety contract

- Downloads require the explicit `--execute` flag.
- Without `--execute`, the harness runs only `gog plan` and validates selection,
  the corpus's rounded display size, exact planned bytes, file count, and free
  space.
- A supplied `--root` must not already exist. The harness never reuses or
  deletes a backup destination.
- Sync always receives the same narrow `--game` or `--games-from` selectors as
  its case. The harness never uses `sync --all`.
- Signed CDN URLs and tokens are not placed in the report.
- Artifacts are retained after success, failure, or interruption.

## Matrix

| Case | Selector coverage | Scope | Downloader | Planned size |
|---|---|---|---|---:|
| `direct-jill-linux` | numeric ID | Linux installer only | direct | 6 MiB |
| `aria-extras` | exact title | extras-only product | aria2c | 50 MiB |
| `direct-raptor-combined` | fuzzy title | Windows installer + extras | direct | 51 MiB |
| `direct-bio-all` | exact `--game` | every available file | direct | 31 MiB |
| `aria-mortal-kombat` | repeated ID + title | two games, every file | aria2c | 89 MiB |
| `aria-list-all` | mixed selector file | all six games, every file | aria2c | 254 MiB |

The full matrix transfers about 481 MiB before the small recovery reruns.

## What is verified

For every case the harness:

1. Runs a JSON dry-run plan and checks selected product IDs, planned bytes,
   planned file count, and destination free space.
2. Executes the backup with the selected downloader.
3. Reads `metadata/manifest.json` and verifies its schema, products, statuses,
   relative-path containment, file existence, and file count.
4. Records every file's role, platform, language, status, expected and actual
   byte count, computed MD5, GOG-provided MD5, and checksum match result.
5. Requires checksum-backed files to match GOG's MD5. Files without a published
   checksum are identified as size-only rather than falsely marked verified.
6. Rejects installer paths without a real filename extension.
7. Runs `gog list --backup` and checks that exactly the selected products appear.
8. Plans and executes the same backup again, requiring zero newly planned files
   and unchanged size/mtime snapshots.
9. Plans and executes narrowly scoped sync, requiring no replacement downloads
   and unchanged current files.

The `direct-jill-linux` case additionally moves the installer aside, proves
sync detects and restores it with the same MD5, then seeds a half-complete
`.part` file and proves the direct downloader completes it to the original MD5.
This also accepts the downloader's intentional full-restart fallback when the
CDN does not honor a byte-range request.

## Running it

Install this branch editable and refresh metadata before the real execution:

```sh
python -m pip install -e .
gog auth status
gog refresh
```

Inspect the matrix:

```sh
python e2e/real_download.py --list-cases
```

Run all plans without downloading:

```sh
python e2e/real_download.py
```

Execute one direct case first:

```sh
python e2e/real_download.py --execute --case direct-jill-linux
```

Execute one aria2c case:

```sh
python e2e/real_download.py --execute --case aria-extras
```

Execute the full single-game and list-driven matrix:

```sh
python e2e/real_download.py --execute
```

Use an explicit new artifact root when desired:

```sh
python e2e/real_download.py --execute --root /tmp/gog-cli-e2e-manual-1
```

Pass `--skip-recovery` only when testing basic download behavior without the
missing-file and resume phase. Pass `--gog /absolute/path/to/gog` to test a
specific installation. The harness requires `gog 1.0.2.dev0` by default; use
`--expected-version` when testing a later release.

## Result review

Open `<artifact-root>/e2e-report.json` after the run. Its summary includes case
count, planned and actual bytes, total files, checksum-verified files, and
size-only files. Each case includes a complete per-file inventory and every CLI
command's exit code, duration, and bounded stdout/stderr tail.

Keep the artifact root until direct and aria2c manifests, paths, byte counts,
and checksums have been compared. Cleanup is intentionally manual.
