# Changelog

All notable changes to this project will be documented in this file.

Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

- Dynamic Codecov coverage badge
- Windows support in CI matrix
- `.editorconfig` for contributor consistency
- `.pre-commit-config.yaml` for automated code quality
- PyPI publish step in release workflow
- VHS tape file for terminal demo recording
- English usage documentation (`docs/USAGE.md`)
- "Why gsuite-manager?" comparison section in README
- Dark/light mode responsive Star History chart

### Changed

- Improved CONTRIBUTING.md with Code of Conduct link and first-timer guide

## [0.1.0] - 2026-05-16

### Added

- **Domain onboarding pipeline** — `gsm domains add` (7-step: Workspace → CF zone → Email Routing disable → DNS inject → propagation check → verify)
- **User management** — `gsm users add`, `gen`, `delete`, `suspend`, `unsuspend`, `reset-password`, `audit`, `move`, `update`
- **Email aliases** — `gsm users alias-add`, `alias-list`, `alias-remove`
- **Groups/mailing lists** — `gsm groups create`, `list`, `add-member`, `remove-member`, `members`
- **Auto-generate users** — Faker-based, locale-aware, collision-safe (`gsm users gen --apply`)
- **License assignment** — `--license education|gmail-only` on user creation
- **Interactive menu** — bare `gsm` invocation shows numbered menu
- **All-in-one shortcut** — `gsm go` auto-detects files and runs everything
- **Audit** — `gsm audit` reconciles CF zones vs Workspace domains
- **DNS health check** — `gsm health` verifies MX/TXT/NS records
- **Domain expiry** — `gsm check-expiry` alerts via RDAP
- **DNS template** — `gsm dns-apply` bulk applies records from YAML
- **Setup wizard** — `gsm setup` interactive first-time configuration
- **Doctor** — `gsm doctor` runs 5 connectivity checks
- **Friendly errors** — technical errors translated to actionable hints
- **Progress bar + ETA** — Rich progress for batch operations
- **CF retry** — 3 attempts with backoff on 502/503/429
- **Pre-flight validation** — domain syntax checked before API calls
- **Idempotent state machine** — JSON ledger tracks per-domain/user status
- **Atomic writes** — tmp+rename pattern prevents corruption
- **Email Routing auto-disable** — detects and disables CF Email Routing before MX inject

### Security

- All credentials stored with mode 0o600
- SecretStr for tokens (prevents accidental logging)
- OAuth scopes minimized (3 scopes only)
- `.gitignore` blocks all sensitive files

[0.1.0]: https://github.com/nopperabbo/gsuite-manager/releases/tag/v0.1.0
