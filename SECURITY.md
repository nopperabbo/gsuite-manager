# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in gsuite-manager, please report it responsibly:

1. **DO NOT** open a public GitHub issue for security vulnerabilities
2. Email: [create a private security advisory](https://github.com/nopperabbo/gsuite-manager/security/advisories/new)
3. Include: description, steps to reproduce, potential impact

We will respond within 72 hours and provide a fix timeline.

## Security Design

### Credential Handling

| Asset | Protection |
|---|---|
| Cloudflare API Token | `SecretStr` (Pydantic), never logged, `.env` mode 0o600 |
| Google OAuth token | Atomic write, mode 0o600, thread-safe refresh |
| Generated passwords | Output files written with mode 0o600 |
| `.env` file | Mode 0o600, blocked by `.gitignore` |

### Principles

- **Minimal OAuth scopes** — only 3 scopes requested (siteverification, admin.directory.domain, admin.directory.user)
- **No secrets in code** — all credentials via environment variables
- **Atomic file writes** — tmp+rename pattern prevents corruption
- **No network exfiltration** — tool only communicates with Google APIs and Cloudflare API
- **Input validation** — domain syntax validated before any API call

## Supported Versions

| Version | Supported |
|---|---|
| 0.1.x | ✅ |
