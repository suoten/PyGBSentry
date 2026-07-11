# Contributing to PyGBSentry

Thank you for your interest in contributing to PyGBSentry! This document outlines the development workflow and coding standards.

## Development Setup

### Prerequisites

- Python 3.11+
- Node.js 20+ with pnpm 9+
- PostgreSQL 16+ (or SQLite for development)
- Redis 7+

### Quick Start

```bash
# Clone the repository
git clone <repo-url>
cd PyGBSentry/editions/open-source

# Install backend dependencies
cd backend
python -m pip install -r requirements.txt -r requirements-dev.txt

# Install frontend dependencies
cd ../frontend
pnpm install

# Start development services
cd ..
make docker-up  # Start PostgreSQL and Redis

# Run database migrations
make migrate

# Start the backend
cd backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Start the frontend (in another terminal)
cd frontend
pnpm dev
```

## Code Quality Standards

### Linting & Formatting

```bash
# Run ruff linter
make lint

# Auto-format code
make format

# Type checking
make typecheck
```

All code must pass `ruff check` and `mypy` before merging.

### Testing

```bash
# Run all tests with coverage
make test

# Run only unit tests
make test-unit

# Run integration tests
make test-integration
```

Minimum coverage threshold: 70%

### Security Scanning

```bash
# Run bandit security scanner
make security
```

## Coding Standards

### Python

- Follow PEP 8 (enforced by ruff)
- Use type hints for all public functions
- Add docstrings to all public functions and classes
- Use `loguru` for logging (not `print` or `logging`)
- Use async/await for I/O operations
- Handle exceptions explicitly — no silent `except: pass`

### Vue/TypeScript

- Use Composition API with `<script setup>`
- Use TypeScript strict mode
- Follow ESLint rules (enforced in CI)
- Use i18n for all user-facing strings

### Git Workflow

1. Create a feature branch from `develop`
2. Make your changes following the coding standards
3. Ensure all CI checks pass
4. Create a pull request to `develop`
5. Request review from maintainers

### Commit Messages

Follow conventional commits:

```
feat: add new PTZ control endpoint
fix: resolve device registration race condition
docs: update API documentation
refactor: extract SIP message parsing logic
test: add unit tests for account lockout
chore: upgrade dependencies
```

## Architecture

PyGBSentry follows a microservice-oriented architecture:

- **Backend**: Python FastAPI + SQLAlchemy + Alembic
- **Frontend**: Vue 3 + TypeScript + Element Plus
- **Media**: ZLMediaKit (GB28181 media server)
- **SIP**: Custom SIP stack for GB28181 signaling
- **Database**: PostgreSQL (production) / SQLite (development)
- **Cache**: Redis

### Key Modules

- `app/api/` — REST API endpoints
- `app/sip/` — SIP/GB28181 signaling stack
- `app/services/` — Business logic services
- `app/models/` — SQLAlchemy ORM models
- `app/core/` — Core utilities (config, security, plugins)
- `app/db/` — Database session and migrations

## License

MIT License — see [LICENSE](LICENSE) for details.
