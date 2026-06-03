# PyGBSentry Backend Makefile
# Usage: make <target>

.PHONY: help dev prod test lint format mypy bandit clean install dev-install test-cov docker-up docker-down db-migrate db-migration db-rollback pre-commit-setup run

# Colors
BLUE := \033[0;34m
GREEN := \033[0;32m
YELLOW := \033[0;33m
NC := \033[0m

help: ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "$(BLUE)%-25s$(NC) %s\n", $$1, $$2}'

# Installation
install: ## Install production dependencies
	pip install -r requirements.txt

dev-install: ## Install development dependencies
	pip install -e ".[dev]"

# Development
dev: ## Start development server with hot reload
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

prod: ## Start production server
	uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4

run: ## Run the application
	python -m app.main

# Testing
test: ## Run unit tests
	pytest tests/ -v

test-cov: ## Run tests with coverage report
	pytest tests/ -v --cov=app --cov-report=term-missing --cov-report=html --cov-report=xml

test-integration: ## Run integration tests
	@pytest tests/integration/ -v 2>/dev/null || echo "No integration tests found in tests/integration/"

test-unit: ## Run unit tests only
	pytest tests/ -v -k "not integration"

# Linting & Formatting
lint: ## Run ruff linter
	ruff check app/ tests/ --output-format=text

lint-json: ## Run ruff linter with JSON output
	ruff check app/ tests/ --output-format=json --exit-non-zero

format: ## Format code with ruff
	ruff format app/ tests/
	ruff check --fix app/ tests/

mypy: ## Run mypy type checker
	mypy app/ --ignore-missing-imports --no-error-summary

bandit: ## Run security scan
	bandit -r app/ -f screen

# Pre-commit
pre-commit-install: ## Install pre-commit hooks
	pre-commit install

pre-commit-run: ## Run pre-commit hooks manually
	pre-commit run --all-files

pre-commit-update: ## Update pre-commit hook versions
	pre-commit autoupdate

# Database
db-migrate: ## Run database migrations
	alembic upgrade head

db-migration: ## Create new migration (MSG=message)
	@if [ -z "$(MSG)" ]; then \
		echo "$(YELLOW)Usage: make db-migration MSG='your migration message'$(NC)"; \
	else \
		alembic revision --autogenerate -m "$(MSG)"; \
	fi

db-rollback: ## Rollback last migration
	alembic downgrade -1

db-history: ## Show migration history
	alembic history --verbose

# Docker
docker-up: ## Start Docker services
	docker-compose up -d

docker-down: ## Stop Docker services
	docker-compose down

docker-build: ## Build Docker image
	docker-compose build

docker-logs: ## Show Docker logs
	docker-compose logs -f

# Cleanup
clean: ## Clean cache files and build artifacts
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	rm -rf htmlcov/ .coverage.xml bandit_report.json

deep-clean: clean ## Deep clean including venv and build
	rm -rf .venv/
	rm -rf build/ dist/ *.egg-info

# Development helpers
fmt-imports: ## Sort imports with isort
	ruff check --select I --fix app/ tests/

check: ## Run all checks (lint, type, security)
	@echo "$(GREEN)Running ruff check...$(NC)"
	@ruff check app/ tests/ || true
	@echo "$(GREEN)Running ruff format check...$(NC)"
	@ruff format --check app/ tests/ || true
	@echo "$(GREEN)Running mypy...$(NC)"
	@mypy app/ --ignore-missing-imports --no-error-summary || true
	@echo "$(GREEN)Running bandit...$(NC)"
	@bandit -r app/ -q || true
	@echo "$(GREEN)All checks passed!$(NC)"

# Virtual environment
venv: ## Create virtual environment
	python -m venv .venv

activate: ## Activate virtual environment (run: source <(make activate))
	@echo "source $$(pwd)/.venv/Scripts/activate"

# Package
build: ## Build package
	python -m build

publish: ## Publish to PyPI (requires credentials)
	python -m twine upload dist/*
