.PHONY: help install dev lint format typecheck test test-quick coverage clean docs

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'

install: ## Install package in production mode
	pip install -e .

dev: ## Install package with dev + docs dependencies
	pip install -e ".[dev,docs]"
	pre-commit install

lint: ## Run linter (ruff check + ruff format check)
	ruff check src/ tests/
	ruff format --check src/ tests/

format: ## Auto-format code
	ruff check --fix src/ tests/
	ruff format src/ tests/

typecheck: ## Run mypy strict type checking
	mypy

test: ## Run full test suite with coverage
	pytest

test-quick: ## Run tests without coverage (faster iteration)
	pytest --no-cov -x -q

coverage: ## Generate HTML coverage report
	pytest --cov-report=html
	@echo "Open htmlcov/index.html"

security: ## Run security audit on dependencies
	pip-audit

docs: ## Build documentation locally
	mkdocs build

docs-serve: ## Serve documentation locally
	mkdocs serve

clean: ## Remove build artifacts
	rm -rf build/ dist/ *.egg-info htmlcov/ .coverage .mypy_cache .pytest_cache .ruff_cache
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

ci: lint typecheck test ## Run full CI pipeline locally
