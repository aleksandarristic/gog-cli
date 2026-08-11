# gog-cli

[![CI](https://github.com/aleksandarristic/gog-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/aleksandarristic/gog-cli/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/gog-cli)](https://pypi.org/project/gog-cli/)
[![Python](https://img.shields.io/badge/python-3.12%2B-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

`gog` is a Python CLI for backing up a user's owned DRM-free GOG game library.

It is focused on safe, scriptable workflows:

- list owned games with filtering and fuzzy search
- plan and execute backups to a local directory
- preserve metadata needed to audit and restore backups
- download installers and related files with resumable behavior
- verify downloaded files when checksums are available

It's also comfortable as a quick, interactive tool:

```sh
gog list                    # your purchased library
gog list civilization       # fuzzy title search
gog search "baldurs gate"   # public catalog, with an "owned" column
gog dl "civilization iv" --yes  # download by fuzzy name to the current directory
gog dl 1760534591 --win --role installer --yes  # Windows installers by exact id
gog help dl                 # contextual help for any command
```

## Install

Requires Python 3.12 or newer.

```sh
pip install gog-cli
```

To install the latest development version directly from GitHub:

```sh
pip install git+https://github.com/aleksandarristic/gog-cli.git
```

## Development

```sh
uv sync
uv run pytest
uv run ruff check src/ tests/
```

Run the CLI locally:

```sh
uv run gog --help
uv run gog list
uv run gog plan --all --summary
uv run gog dl --games-from games.txt --dry-run
```

## Roadmap

See [docs/TODO.md](docs/TODO.md) for planned features and improvements.

## Reference

- [CLI Reference](docs/cli-reference.md)
- [Config Reference](docs/config-reference.md)
- [Real Download Test Plan](docs/real-download-test-plan.md)

## Basic Workflow

```sh
gog auth login
gog refresh
gog list
gog plan --destination /path/to/backups --all --storage --check-free-space
gog backup --destination /path/to/backups --all --yes
gog list --backup --destination /path/to/backups
gog sync --destination /path/to/backups --all --yes
```

`gog refresh` updates the local purchased-library and download-metadata caches.
It does not download game installers. Run it before browsing or filtering newly
added library metadata.

`--destination` is optional everywhere above — it defaults to the current
directory, so `cd` into a backup folder and drop it from every command.

## Browsing Purchased Games

`gog list` reads the local cache written by `gog refresh`; it does not contact
GOG. Human output includes ID, title, release year, genre/category, and
platforms when those fields are available. JSON output also includes scriptable
metadata such as `owned`, `release_date`, `genres`, and `is_installable`.

`gog list` alone lists everything; `gog list TEXT` fuzzy-searches by title.
Neither `purchased` nor `backup` is a reserved word — a game actually titled
either one is never shadowed. `gog list --backup`/`--back` lists games
recorded in a backup manifest instead.

Examples:

```sh
gog list
gog list --format json
gog list witcher
gog list "baldurs gate"
gog list --platform windows
gog list ftl --platform linux
gog list --year 1998..2005
gog list --year 2010..2020 --include-unknown-year
gog list --genre strategy
gog list --genre arcade,rts
gog list --genre strategy --include-unknown-genre
gog list "baldurs gate" --platform linux --format json
```

Use `gog search TEXT` to search the public GOG catalog instead of your local
library — results include an `owned` column/field so you can see at a glance
whether you already have a game.

Year filters omit games with unknown years by default; use
`--include-unknown-year` to keep them. Genre filters similarly omit unknown
genres by default; use `--include-unknown-genre` to keep those rows.

## Planning Backups

`gog plan` shows the same dry-run plan as `gog backup --dry-run` without
downloading files or creating backup directories. Use it before long backup runs
to estimate size, inspect filters, and check destination free space.

Examples:

```sh
gog plan --destination /path/to/backups --all
gog plan --destination /path/to/backups --all --summary
gog plan --destination /path/to/backups --all --storage
gog plan --destination /path/to/backups --all --check-free-space
gog plan --destination /path/to/backups --all --format json
gog plan --destination /path/to/backups cyberpunk_2077
```

Platform and language filters can reduce backup size:

```sh
gog plan --destination /path/to/backups --all --platform linux --storage
gog plan --destination /path/to/backups --all --platform windows --language en --storage
```

## Selecting Games

The simplest way to select a game is a bare positional argument — a product
ID, slug, or title. Titles don't need to be exact: if there's no exact
id/slug/title match, the selector falls back to fuzzy title matching.

```sh
gog dl "civilization iv"          # fuzzy title match
gog dl 1760534591                 # exact id, never ambiguous
gog backup witcher_3 --yes
```

If a fuzzy selector matches more than one game, `gog` prompts you to pick one
at an interactive terminal, or exits with an error listing the candidates
otherwise (scripts, `--no-interactive`, or CI). Use an exact id or slug to
sidestep ambiguity entirely.

`--game`/`-g` behaves the same but only ever matches exactly (product id,
slug, or exact title) — no fuzzy fallback — which is what you want for
scripts and `games.txt` files where the match must be deterministic. It's
repeatable:

```sh
gog plan --destination /path/to/backups --game witcher_3 --game cyberpunk_2077
gog backup --destination /path/to/backups --game 123456789 --yes
```

Platform and role filters have shortcut flags on top of the general
`--platform`/`--role` options:

```sh
gog plan "civilization iv" --win
gog dl "civilization iv" --win --role installer --yes
gog dl "civilization iv" --win --role installer --role extra --yes
```

`--win` is a shortcut for `--platform windows`; `--mac`, `--lin`, and
`--linux` work the same way for their platforms. Platform filters keep
platform-neutral files eligible, so use `--role installer` when you want only
installers. Repeat `--role` to include extras or other roles explicitly.

For larger curated lists, put selectors in a UTF-8 text file and pass
`--games-from`. Blank lines and lines whose first non-whitespace character is
`#` are ignored.

Example `games.txt`:

```text
# first NAS batch
witcher_3
cyberpunk_2077
123456789
```

Use the selector file in plan, backup, or sync workflows:

```sh
gog plan --destination /path/to/backups --games-from games.txt --win --role installer --role extra --storage
gog backup --destination /path/to/backups --games-from games.txt --win --role installer --role extra --downloader aria2c --yes
gog sync --destination /path/to/backups --games-from games.txt --dry-run
```

`--games-from` is repeatable and combines with repeated `--game` flags. Do not
combine explicit game selectors with `--all`.

## Downloading

`gog backup`/`gog download`/`gog dl` are the same command. If `aria2c` is
installed and on `PATH`, it's used automatically; otherwise the built-in
direct downloader is used. Pass `--downloader` explicitly to override either
way:

```sh
gog dl "civilization iv" --win --role installer --yes
gog dl "civilization iv" --win --role installer --role extra --yes
gog dl --games-from games.txt --win --role installer --role extra --yes
gog dl --games-from games.txt --downloader direct --yes
```

Downloaded artifacts keep their GOG-provided filenames, including every part
of split installers. Files with published checksums must pass MD5 verification;
files without one are retained as size-checked downloads in the backup manifest.

When file size metadata is available, `gog` chooses `aria2c` connection settings
by size: very small files use one connection, mid-size files use two or four,
and multi-GB installers use eight or sixteen. Configure
`aria2c_policy = "conservative"` or `aria2c_policy = "aggressive"` to tune this
behavior.

Without `--yes`, backup and sync commands print a dry-run plan and exit without
downloading or modifying backup files.
