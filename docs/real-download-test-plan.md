# Real Download Test Plan

This is a deferred, authenticated smoke-test plan. It intentionally downloads
small owned games into isolated temporary directories. Do not run it in CI.

## Test corpus

| Product ID | Title | Windows | macOS | Linux | Extras | Total |
|---:|---|---:|---:|---:|---:|---:|
| 1207658879 | Raptor: Call of the Shadows 2010 Edition | 43 MiB | - | - | 8 MiB | 51 MiB |
| 1315929054 | Warhammer Skulls 2025 Digital Goodie Bag | - | - | - | 50 MiB | 50 MiB |
| 1207667043 | Mortal Kombat 1 | 25 MiB | 21 MiB | - | - | 46 MiB |
| 1207667053 | Mortal Kombat 2 | 23 MiB | 20 MiB | - | - | 43 MiB |
| 1129701343 | Jill of the Jungle: The Complete Trilogy | 12 MiB | 10 MiB | 6 MiB | 5 MiB | 33 MiB |
| 1449569170 | Bio Menace | 13 MiB | 11 MiB | 7 MiB | - | 31 MiB |

The companion [real-download-games.txt](real-download-games.txt) deliberately
mixes numeric IDs and exact titles for selector-file coverage.

## Preparation

Run from the repository checkout after installing the branch editable:

```sh
python -m pip install -e .
gog --version
gog auth status
gog refresh
command -v aria2c
TEST_ROOT="$(mktemp -d /tmp/gog-cli-real-test.XXXXXX)"
```

Record `TEST_ROOT`; every case below must remain inside it. Run every `plan`
command before its matching `backup` command and confirm the selected games,
roles, platforms, file count, and estimated bytes.

## Single-game cases

1. Numeric ID, one platform and one role, direct downloader:

   ```sh
   gog plan 1129701343 -d "$TEST_ROOT/direct-jill-linux" --linux --role installer
   gog backup 1129701343 -d "$TEST_ROOT/direct-jill-linux" --linux --role installer --downloader direct --yes
   ```

2. Exact title, extras-only product, aria2c:

   ```sh
   gog plan "Warhammer Skulls 2025 Digital Goodie Bag" -d "$TEST_ROOT/aria-extras" --role extra
   gog backup "Warhammer Skulls 2025 Digital Goodie Bag" -d "$TEST_ROOT/aria-extras" --role extra --downloader aria2c --yes
   ```

3. Fuzzy positional title, combined installer and extras roles, direct
   downloader:

   ```sh
   gog plan "raptor call shadows" -d "$TEST_ROOT/direct-raptor-combined" --windows --role installer --role extra
   gog backup "raptor call shadows" -d "$TEST_ROOT/direct-raptor-combined" --windows --role installer --role extra --downloader direct --yes
   ```

4. Exact `--game` title with all available files, direct downloader:

   ```sh
   gog plan --game "Bio Menace" -d "$TEST_ROOT/direct-bio-all"
   gog backup --game "Bio Menace" -d "$TEST_ROOT/direct-bio-all" --downloader direct --yes
   ```

## Multi-game cases

5. Repeated selectors using one ID and one exact title, aria2c:

   ```sh
   gog plan 1207667043 "Mortal Kombat 2" -d "$TEST_ROOT/aria-mortal-kombat"
   gog backup 1207667043 "Mortal Kombat 2" -d "$TEST_ROOT/aria-mortal-kombat" --downloader aria2c --yes
   ```

6. Mixed selector file containing all six games, aria2c:

   ```sh
   gog plan --games-from docs/real-download-games.txt -d "$TEST_ROOT/aria-list-all" --summary --storage --check-free-space
   gog backup --games-from docs/real-download-games.txt -d "$TEST_ROOT/aria-list-all" --downloader aria2c --check-free-space --yes
   ```

## Verification and reruns

After each executed case, inspect its manifest and run sync with the same exact
selection used for that case. For example:

```sh
gog list --backup --destination "$CASE_ROOT"
gog sync --destination "$TEST_ROOT/direct-jill-linux" --game 1129701343 --dry-run
gog sync --destination "$TEST_ROOT/aria-list-all" --games-from docs/real-download-games.txt --dry-run
```

Do not substitute `--all` for these checks: that would select the entire owned
library rather than only this test corpus.

Check that installer filenames retain their real extensions, manifest paths
match files on disk, and statuses are `verified` when GOG supplied checksums or
`downloaded` when verification is size-only.

Rerun each backup command against the same destination. It should verify or
skip existing files without downloading replacements. Then move one installer
to a sibling `.removed-for-sync-test` path and run `gog sync --yes` with that
case's exact `--game` or `--games-from` selection; sync must restore the missing
recorded file. Move the saved copy back only after comparing it with the
restored file.

Keep all test directories until manifests, filenames, sizes, checksums, direct
downloads, and aria2c downloads have been compared. Remove the temporary root
only after the results are recorded.
