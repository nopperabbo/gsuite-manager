# Changelog

All notable changes to this project will be documented in this file.

Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

- Property-based tests using Hypothesis (ledger, models, error humanizer)
- API reference documentation (auto-generated via mkdocstrings)
- `hypothesis>=6.100.0` dev dependency

### Changed

- Bumped version to 0.3.0 for PyPI release
- Fixed `pypa/gh-action-pypi-publish` SHA (was invalid, blocking releases)
- Removed `continue-on-error` from PyPI publish step (fail loudly)

### Removed

- `docs/RESEARCH_GAP_ANALYSIS.md` — internal research notes (not user-facing)
- `docs/QUICK_ROTATE_CF_TOKEN.md` — personal operational note
- `docs/ROADMAP.md` — moved to GitHub Projects
- `docs/CARA_PAKE.md` — consolidated into `docs/usage.md`
- `docs/CARA_TEST.md` — consolidated into CONTRIBUTING.md
- `docs/demo.tape` — VHS recording config (no output in repo)
- `STYLE.md` — consolidated into CONTRIBUTING.md

## [0.2.0] - 2025-05-23
- `health.py` — DNS exceptions no longer swallowed, report specific errors
- `conftest.py` — Consolidated shared fixtures (settings, mock_admin, mock_cf, ledger)

### Infrastructure

- `Makefile` — Added with targets: ci, lint, format, typecheck, test, security, docs, clean
- CI rewritten — SHA-pinned actions, 6 jobs (lint/typecheck/test-matrix/coverage/security/smoke), alls-green gate
- Dynamic versioning via `importlib.metadata`

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
[Unreleased]: https://github.com/nopperabbo/gsuite-manager/compare/v0.1.0...HEAD
