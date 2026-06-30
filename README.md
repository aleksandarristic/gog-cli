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
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[dev]"
python -m pytest
```

Run the CLI locally:

```sh
gog --help
gog list
gog plan --destination /path/to/backups --all --summary
gog backup --destination /path/to/backups --games-from games.txt --dry-run
```

## Roadmap

See [docs/TODO.md](docs/TODO.md) for planned features and improvements.

## Reference

- [CLI Reference](docs/cli-reference.md)
- [Config Reference](docs/config-reference.md)

## Basic Workflow

```sh
gog auth login
gog refresh
gog list purchased
gog plan --destination /path/to/backups --all --storage --check-free-space
gog backup --destination /path/to/backups --all --yes
gog list backed-up --destination /path/to/backups
gog sync --destination /path/to/backups --all --yes
```

`gog refresh` updates the local purchased-library and download-metadata caches.
It does not download game installers. Run it before browsing or filtering newly
added library metadata.

## Browsing Purchased Games

`gog list purchased` reads the local cache written by `gog refresh`; it does not
contact GOG. Human output includes ID, title, release year, genre/category, and
platforms when those fields are available. JSON output also includes scriptable
metadata such as `owned`, `release_date`, `genres`, and `is_installable`.

Examples:

```sh
gog list purchased
gog list purchased --format json
gog list purchased --search witcher
gog list purchased --search "baldurs gate"
gog list purchased --platform windows
gog list purchased --platform linux --search ftl
gog list purchased --year 1998..2005
gog list purchased --year 2010..2020 --include-unknown-year
gog list purchased --genre strategy
gog list purchased --genre arcade,rts
gog list purchased --genre strategy --include-unknown-genre
gog list purchased --search "baldurs gate" --platform linux --format json
```

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

Game selectors can be product IDs, slugs, or exact titles. Commands that select
games accept repeated `--game` flags:

```sh
gog plan --destination /path/to/backups --game witcher_3 --game cyberpunk_2077
gog backup --destination /path/to/backups --game 123456789 --yes
```

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
gog plan --destination /path/to/backups --games-from games.txt --storage
gog backup --destination /path/to/backups --games-from games.txt --downloader aria2c --yes
gog sync --destination /path/to/backups --games-from games.txt --dry-run
```

`--games-from` is repeatable and combines with repeated `--game` flags. Do not
combine explicit game selectors with `--all`.

## Downloading

`gog backup` defaults to the built-in direct downloader. To use `aria2c`, install
`aria2c` and pass `--downloader aria2c` on an executing backup run:

```sh
gog backup --destination /path/to/backups --games-from games.txt --downloader aria2c --yes
```

When file size metadata is available, `gog` chooses `aria2c` connection settings
by size: very small files use one connection, mid-size files use two or four,
and multi-GB installers use eight or sixteen. Configure
`aria2c_policy = "conservative"` or `aria2c_policy = "aggressive"` to tune this
behavior.

Without `--yes`, backup and sync commands print a dry-run plan and exit without
downloading or modifying backup files.
