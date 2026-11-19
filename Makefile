.DEFAULT_GOAL := help
.PHONY: help setup env hooks fmt lint typecheck test-unit test-integration test check db-up db-down up down migrate smoke clean

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-18s %s\n", $$1, $$2}'

setup: ## Install dependencies (creates uv.lock on first run: commit it)
	uv sync

env: ## Create .env with a generated database password (refuses to overwrite)
	./scripts/gen-dev-env.sh

hooks: ## Install pre-commit hooks
	uv run pre-commit install

fmt: ## Auto-format and fix lint issues
	uv run ruff format .
	uv run ruff check --fix .

lint: ## Lint and format check (no changes)
	uv run ruff check .
	uv run ruff format --check .

typecheck: ## Static type check
	uv run mypy

test-unit: ## Unit tests (no Docker needed)
	uv run pytest -m unit

test-integration: ## Integration tests (needs PostgreSQL: run `make db-up` first)
	uv run pytest -m integration

test: ## All tests
	uv run pytest

check: lint typecheck test-unit ## Everything that needs no Docker

db-up: ## Start PostgreSQL only
	docker compose up -d --wait postgres

db-down: ## Stop PostgreSQL (keeps data volume)
	docker compose stop postgres

up: ## Build and start the full stack (postgres, migrate, api)
	docker compose up -d --build

down: ## Stop the stack and delete volumes
	docker compose down -v

migrate: ## Apply migrations to the configured database
	uv run alembic upgrade head

smoke: ## Compose smoke test (stack must be up)
	./scripts/smoke-compose.sh

clean: ## Remove caches
	rm -rf .pytest_cache .mypy_cache .ruff_cache .coverage htmlcov
