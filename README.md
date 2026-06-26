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
