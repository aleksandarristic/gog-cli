# Security Policy

## Supported versions

| Version | Supported |
|---------|-----------|
| latest  | Yes       |

## Reporting a vulnerability

Please **do not** open a public GitHub issue for security vulnerabilities.

Report vulnerabilities by email to **aleksandar1983@gmail.com**. Include as much detail as you can: what the issue is, how to reproduce it, and what impact you believe it has.

You can expect an acknowledgement within 48 hours and a resolution or update within 14 days.

## Scope

This tool authenticates against GOG using the standard GOG Galaxy OAuth client credentials. Those credentials are intentionally public (used by lgogdownloader, Minigalaxy, Heroic, and others) and rotating them is GOG's responsibility. Reports about them are out of scope.

In-scope issues include:
- Local credential storage vulnerabilities (session file permissions, keyring handling)
- Path traversal or unsafe file writes in backup/download paths
- Any behavior that could expose a user's session token to a third party
