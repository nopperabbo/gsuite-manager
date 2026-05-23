# Contributing

Thanks for your interest in contributing to gsuite-manager! This guide will help you get started.

Please note that this project follows our [Code of Conduct](CODE_OF_CONDUCT.md). By participating, you agree to uphold it.

## First-Time Contributors

New to open source? Look for issues labeled [`good first issue`](https://github.com/nopperabbo/gsuite-manager/labels/good%20first%20issue) — these are scoped, well-documented tasks designed for newcomers.

**Quick wins to get started:**
- Fix a typo in docs
- Add a test for an uncovered edge case
- Improve an error message in `core/errors.py`

## Development Setup

```bash
git clone https://github.com/nopperabbo/gsuite-manager.git
cd gsuite-manager
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pre-commit install  # optional but recommended
```

## Running Tests

```bash
pytest                    # full suite with coverage
pytest -q --no-cov        # quick run
pytest tests/test_X.py    # single file
pytest -k "test_name"     # single test by name
```

## Code Quality

> [!IMPORTANT]
> Always run `make ci` before submitting a PR. This runs lint + typecheck + tests in one command.

All three must pass before submitting a PR:

```bash
ruff check src tests      # lint
ruff format src tests     # format
mypy src                  # type check (strict mode)
```

Or run everything at once with pre-commit:

```bash
pre-commit run --all-files
```

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

- **Tests required** for new features (target: 90%+ coverage)
- **mypy strict** — no `# type: ignore` without justification
- **Idempotent** — all API operations must handle "already exists" gracefully
- **Atomic writes** — use tmp+rename pattern for file persistence
- **Friendly errors** — add patterns to `core/errors.py` humanizer
- **No secrets in code** — use `.env` + `SecretStr`

## Commit Messages

Format: `<type>(<scope>): <description>`

Types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `perf`, `ci`

Examples:
- `feat(users): add bulk suspend command`
- `fix(dns): handle timeout on propagation check`
- `docs(readme): add architecture diagram`

## Submitting Changes

1. Fork the repo
2. Create a feature branch (`git checkout -b feat/my-feature`)
3. Make changes + add tests
4. Ensure `pytest && ruff check src tests && mypy src` all pass
5. Commit with conventional message
6. Open a PR against `main`

## Reporting Bugs

Use the [bug report template](https://github.com/nopperabbo/gsuite-manager/issues/new?template=bug_report.yml). Include:
- Steps to reproduce
- Expected vs actual behavior
- `gsm --version` output
- OS and Python version

## Requesting Features

Use the [feature request template](https://github.com/nopperabbo/gsuite-manager/issues/new?template=feature_request.yml). Describe:
- The problem you're trying to solve
- Your proposed solution
- Alternatives you've considered
