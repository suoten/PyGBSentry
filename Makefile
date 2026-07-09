# ============================================================================
# PyGBSentry — Makefile for common development tasks
# ============================================================================
# Usage:
#   make help          — show available commands
#   make install       — install all dependencies (backend + frontend)
#   make lint          — run ruff linter
#   make format        — auto-format code with ruff
#   make typecheck     — run mypy type checker
#   make test          — run pytest with coverage
#   make security      — run bandit security scanner
#   make docker-up     — start all services via docker-compose
#   make docker-down   — stop all docker services
# ============================================================================

.PHONY: help install lint format typecheck test security docker-up docker-down clean

PYTHON ?= python
PNPM ?= pnpm

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install:  ## Install all dependencies
	cd backend && $(PYTHON) -m pip install -r requirements.txt
	cd frontend && $(PNPM) install

install-dev:  ## Install development dependencies
	cd backend && $(PYTHON) -m pip install -r requirements.txt ruff mypy bandit pytest pytest-asyncio pytest-cov pytest-mock
	cd frontend && $(PNPM) install

lint:  ## Run ruff linter
	cd backend && ruff check app/ tests/

format:  ## Auto-format code
	cd backend && ruff format app/ tests/
	cd backend && ruff check app/ tests/ --fix

typecheck:  ## Run mypy type checker
	cd backend && mypy app/ --ignore-missing-imports

test:  ## Run tests with coverage
	cd backend && pytest tests/ -v --cov=app --cov-report=term-missing --cov-fail-under=70

test-unit:  ## Run only unit tests (skip integration)
	cd backend && pytest tests/ -v --ignore=tests/integration

test-integration:  ## Run integration tests
	cd backend && pytest tests/integration/ -v

security:  ## Run security scanners
	cd backend && bandit -r app/ -f custom --severity-level medium
	cd backend && pip-audit -r requirements.txt

docker-up:  ## Start all services
	docker-compose up -d

docker-down:  ## Stop all services
	docker-compose down

clean:  ## Clean build artifacts
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true
	rm -f backend/coverage.xml backend/.coverage
	rm -f backend/bandit_report.sarif

migrate:  ## Run database migrations
	cd backend && alembic upgrade head

migrate-rollback:  ## Rollback last migration
	cd backend && alembic downgrade -1
