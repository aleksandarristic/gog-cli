# gog-cli

`gog` is a Python CLI for backing up a user's owned DRM-free GOG game library.

The project is intentionally early. The initial shape is focused on safe, scriptable workflows:

- list owned games
- back up owned games to a local directory
- preserve metadata needed to audit and restore backups
- download installers and related files with resumable behavior where feasible
- verify downloaded files when checksums are available

## Development

Requires Python 3.12 or newer.

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
gog backup --destination /path/to/backups
gog backup --destination /path/to/backups --dry-run
```

## Basic Workflow

```sh
gog auth login
gog refresh
gog list purchased
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
