# AGENTS.md — gsuite-manager

Instructions for AI coding agents working on this repository.

## Overview

Python CLI tool (Typer + Pydantic + structlog + Rich) for automating Google Workspace + Cloudflare domain & user management.

## Architecture

```
src/gsm/
├── cli/         # Typer commands + interactive menu (dict dispatch)
├── clients/     # CF, Google Admin (@google_api_call decorator), DNS, Faker
├── core/        # Config (Pydantic Settings), OAuth2, logging, error humanizer
├── models/      # Pydantic schemas (domain, user, results)
├── state/       # JSON ledger (atomic writes, corrupt recovery)
└── workflows/   # Domain onboarding, user creation orchestration
```

## Commands

```bash
make ci          # Full quality gate (lint + typecheck + test)
make lint        # ruff check + ruff format --check
make typecheck   # mypy --strict
make test        # pytest with coverage
make security    # pip-audit
make docs        # mkdocs serve (local preview)
```

## Conventions

- **Type safety**: mypy strict mode, no `type: ignore` without justification
- **Error handling**: Use `@google_api_call` decorator for Google API methods
- **Commits**: `<type>(<scope>): <description>` (feat, fix, refactor, docs, ci, test, chore)
- **Tests**: pytest, fixtures in `tests/conftest.py`, mock external APIs
- **Formatting**: ruff (line-length=100, flat-square badge style)

## Key Patterns

- `clients/_decorators.py` — `@google_api_call(action, duplicate_ok, not_found_ok)` wraps all Google Admin SDK calls
- `cli/commands/menu.py` — Dict dispatch `_DISPATCH` table maps menu choices to handlers
- `state/ledger.py` — Atomic JSON writes with tmp+rename, corrupt entry recovery with logging
- `core/config.py` — Pydantic Settings with env var loading + validators

## Do NOT

- Add `type: ignore` or `# noqa` without explaining why
- Suppress exceptions silently (always log)
- Add dependencies without checking existing alternatives
- Modify tests to make them pass (fix the code instead)
