# ═══════════════════════════════════════════════════════════════════════════
# RAG Platform — Makefile
# One-command operations for development and deployment.
# ═══════════════════════════════════════════════════════════════════════════

.PHONY: help up down restart logs install dev test lint format

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ── Docker ────────────────────────────────────────────────────────────────

up: ## Start all services (production)
	docker compose up -d --build

down: ## Stop all services
	docker compose down

restart: ## Restart all services
	docker compose restart

logs: ## Tail logs from all services
	docker compose logs -f

logs-api: ## Tail API logs only
	docker compose logs -f api

# ── Development ───────────────────────────────────────────────────────────

dev: ## Start development server with hot-reload
	docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build

install: ## Install Python dependencies
	pip install -r requirements.txt

run: ## Run API server locally (no Docker)
	uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload

# ── Testing ───────────────────────────────────────────────────────────────

test: ## Run test suite
	pytest tests/ -v --tb=short

test-api: ## Smoke test the API
	curl -s http://localhost:8000/health | python -m json.tool

# ── Code Quality ──────────────────────────────────────────────────────────

lint: ## Run linter
	ruff check backend/ tests/

format: ## Format code
	ruff format backend/ tests/

# ── Database ──────────────────────────────────────────────────────────────

db-reset: ## Reset database (DANGER: drops all data)
	docker compose exec postgres psql -U postgres -d ragplatform -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"

# ── Utilities ─────────────────────────────────────────────────────────────

shell: ## Open Python shell
	python -i -c "from backend.core.config import get_settings; print(get_settings())"

version: ## Show current version
	@grep 'APP_VERSION' backend/core/config.py | head -1
