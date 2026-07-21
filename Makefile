# =============================================================================
# Ardee RAG ChatBot — Developer Makefile
# =============================================================================
# Usage: make <target>
# =============================================================================

.PHONY: help install dev lint format typecheck test run seed-staging frontend-install frontend-run frontend-lint frontend-typecheck frontend-build docker-up docker-down clean

# Default target
help: ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ── Setup ────────────────────────────────────────────────────────────────────

install: ## Install production dependencies
	cd backend && uv sync --frozen
	cd frontend && npm install

dev: ## Install all dependencies (including dev)
	cd backend && uv sync --frozen --all-extras
	cp -n .env.example .env 2>/dev/null || true
	cd backend && uv run pre-commit install
	cd frontend && npm install

# ── Code Quality ─────────────────────────────────────────────────────────────

lint: ## Run Ruff linter
	cd backend && uv run ruff check app/ tests/

format: ## Format code with Black and fix imports with Ruff
	cd backend && uv run black app/ tests/
	cd backend && uv run ruff check --fix app/ tests/

typecheck: ## Run mypy type checker
	cd backend && uv run mypy app/

check: lint typecheck ## Run all code quality checks

# ── Testing ──────────────────────────────────────────────────────────────────

test: ## Run tests with pytest
	cd backend && uv run pytest tests/ -v

test-cov: ## Run tests with coverage
	cd backend && uv run pytest tests/ -v --cov=app --cov-report=term-missing

# ── Running ──────────────────────────────────────────────────────────────────

run: ## Start FastAPI development server
	cd backend && uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

seed-staging: ## Seed 2 admins + 6 users (idempotent; refuses production)
	cd backend && uv run python -m scripts.seed_staging

frontend-install: ## Install frontend dependencies
	cd frontend && npm install

frontend-run: ## Start Next.js development server
	cd frontend && npm run dev

frontend-lint: ## Run frontend ESLint
	cd frontend && npm run lint

frontend-typecheck: ## Run frontend TypeScript checks
	cd frontend && npm run typecheck

frontend-build: ## Build frontend for production
	cd frontend && npm run build

# ── Docker ───────────────────────────────────────────────────────────────────

docker-up: ## Start infrastructure services (PostgreSQL, Redis)
	docker compose -f docker/docker-compose.yml up -d

docker-down: ## Stop infrastructure services
	docker compose -f docker/docker-compose.yml down

docker-logs: ## View infrastructure logs
	docker compose -f docker/docker-compose.yml logs -f

# ── Cleanup ──────────────────────────────────────────────────────────────────

clean: ## Remove caches and build artifacts
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
