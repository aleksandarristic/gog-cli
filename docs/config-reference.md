# Config Reference

`gog` loads configuration from built-in defaults, a TOML config file, and
environment variables. CLI flags override configuration values when a command
provides an equivalent flag.

## Config File

The config file is loaded from:

```text
$XDG_CONFIG_HOME/gog-cli/config.toml
```

If `XDG_CONFIG_HOME` is not set, the default path is:

```text
~/.config/gog-cli/config.toml
```

All config keys are optional and live under `[defaults]`.

```toml
[defaults]
destination   = "/path/to/backups"
downloader    = "direct"
aria2c_policy = "auto"
platforms     = ["windows", "linux"]
languages     = ["en"]
file_roles    = []
format        = "human"
interactive   = true
```

## Defaults

| Key | Type | Default | Values |
|---|---:|---|---|
| `destination` | path | unset | Any local backup directory path |
| `downloader` | string | `direct` | `direct`, `aria2c` |
| `aria2c_policy` | string | `auto` | `auto`, `conservative`, `aggressive` |
| `platforms` | list | `[]` | GOG platform names, such as `windows`, `linux`, `osx` |
| `languages` | list | `[]` | GOG language codes, such as `en`, `de`, `fr` |
| `file_roles` | list | `[]` | `installer`, `patch`, `language_pack`, `extra`, `manual` |
| `format` | string | `human` | `human`, `json` |
| `interactive` | boolean | `true` | `true`, `false` |

Empty lists mean no default restriction.

## Environment Variables

Environment variables override the config file.

| Variable | Config key | Notes |
|---|---|---|
| `GOG_CLI_DESTINATION` | `destination` | Path to backup root |
| `GOG_CLI_DOWNLOADER` | `downloader` | `direct` or `aria2c` |
| `GOG_CLI_ARIA2C_POLICY` | `aria2c_policy` | `auto`, `conservative`, or `aggressive` |
| `GOG_CLI_PLATFORMS` | `platforms` | Comma-separated, e.g. `windows,linux` |
| `GOG_CLI_LANGUAGES` | `languages` | Comma-separated, e.g. `en,de` |
| `GOG_CLI_FILE_ROLES` | `file_roles` | Comma-separated |
| `GOG_CLI_FORMAT` | `format` | `human` or `json` |
| `GOG_CLI_INTERACTIVE` | `interactive` | `1`/`true`/`yes` or `0`/`false`/`no` |

## aria2c Policy

`aria2c_policy` only affects downloads when `downloader = "aria2c"` or a command
uses `--downloader aria2c`.

The policy controls `aria2c`'s per-file `--split` and
`--max-connection-per-server` values. Downloads are still processed one file at a
time.

| File size | `conservative` | `auto` | `aggressive` |
|---|---:|---:|---:|
| Unknown | 2 | 4 | 8 |
| `<64 MiB` | 1 | 1 | 2 |
| `64-512 MiB` | 1 | 2 | 4 |
| `512 MiB-2 GiB` | 2 | 4 | 8 |
| `2-8 GiB` | 4 | 8 | 16 |
| `8 GiB+` | 8 | 16 | 16 |

Use `conservative` when sharing a connection or when servers react poorly to many
connections. Use `auto` for the default balance. Use `aggressive` when the goal
is to saturate a fast connection and the network can handle more parallel
segments.
