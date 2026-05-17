# Contributing

Thanks for your interest in contributing to gsuite-manager!

## Development Setup

```bash
git clone https://github.com/nopperabbo/gsuite-manager.git
cd gsuite-manager
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Running Tests

```bash
pytest                    # full suite with coverage
pytest -q --no-cov        # quick run
pytest tests/test_X.py    # single file
```

## Code Quality

```bash
ruff check src tests      # lint
ruff format src tests     # format
mypy src                  # type check
```

All three must pass before submitting a PR.

## Project Structure

```
src/gsm/
├── cli/         # Typer commands + interactive menu
├── clients/     # External API wrappers (CF, Google, DNS)
├── core/        # Config, auth, logging, error humanizer
├── models/      # Pydantic data models
├── state/       # JSON ledger (state persistence)
└── workflows/   # Orchestration logic
```

## Guidelines

- **Tests required** for new features (target: 80%+ coverage)
- **mypy strict** — no `# type: ignore` without justification
- **Idempotent** — all API operations must handle "already exists" gracefully
- **Atomic writes** — use tmp+rename pattern for file persistence
- **Friendly errors** — add patterns to `core/errors.py` humanizer
- **No secrets in code** — use `.env` + `SecretStr`

## Commit Messages

Format: `<type>(<scope>): <description>`

Types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`

## Submitting Changes

1. Fork the repo
2. Create a feature branch (`git checkout -b feat/my-feature`)
3. Make changes + add tests
4. Ensure `pytest && ruff check && mypy src` all pass
5. Commit with conventional message
6. Open a PR against `main`
