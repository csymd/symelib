.PHONY: help setup setup-agents install install-cli sync test lint format check clean db-up db-down db-migrate rebuild pre-commit-install pre-commit-run

help:
	@echo "Available commands for elib:"
	@echo "  make help              Show this help"
	@echo "  make setup             Interactive setup (NCBI email/API key → config + env)"
	@echo "  make sync              Sync dependencies with uv (core + dev + all extras)"
	@echo "  make install-cli       Install 'elib' onto PATH via uv tool (~/.local/bin)"
	@echo "  make install           Install package in editable mode with uv pip (+ extras)"
	@echo "  make db-up             Start Postgres + pgvector (for agents/RAG only; see compose.yaml)"
	@echo "  make db-down           Stop DB containers"
	@echo "  make db-migrate        Run Alembic migrations (Postgres path)"
	@echo "  make rebuild           Rebuild FTS index (+ --embeddings into PGVector; supports --reset)"
	@echo "  make test              Run tests"
	@echo "  make lint              Lint with Ruff (checks only)"
	@echo "  make format            Format code with Ruff (applies fixes)"
	@echo "  make check             Run all checks (lint + format + tests)"
	@echo "  make pre-commit-install  Install git pre-commit hooks (once per clone)"
	@echo "  make pre-commit-run      Run pre-commit on all files"
	@echo "  make clean             Remove build artifacts and caches"

sync:
	uv sync --all-extras

setup:
	@bash scripts/setup.sh

install-cli:
	uv tool install --force --editable .
	@echo "Installed elib → ensure ~/.local/bin is on PATH"
	@echo "  export PATH=\"\$$HOME/.local/bin:\$$PATH\""
	@command -v elib >/dev/null && elib --help | head -5 || true

install:
	uv pip install -e ".[db,agents]"

db-up:
	@if [ ! -f compose.yaml ]; then \
		echo "ERROR: compose.yaml is missing. See QUICKSTART.md."; \
		echo "       Postgres + pgvector is only required for the optional [agents] path."; \
		echo "       Core functionality uses SQLite and does not need 'make db-up'."; \
		exit 1; \
	fi
	podman compose -f compose.yaml up -d postgres

db-down:
	@if [ ! -f compose.yaml ]; then \
		echo "compose.yaml not present — nothing to bring down."; \
		exit 0; \
	fi
	podman compose -f compose.yaml down

db-migrate:
	@echo "db-migrate: Sets up the Postgres vector store for agents/RAG (pgvector extension + data_document_nodes table)."
	@echo "            See src/symworx_elibrary/migrations/README.md and migration 0001_initial_vector_store."
	@echo "            Safe to run after 'make db-up'. Uses the same connection as the app."
	uv run --extra db alembic upgrade head || echo "Note: alembic upgrade encountered an issue (check connection / DATABASE_URL)."

rebuild:
	uv run --extra agents elib rebuild-index --embeddings || \
		( echo "Note: --embeddings support is WIP. Running basic FTS rebuild instead..."; \
		  uv run --extra agents elib rebuild-index )

test:
	uv run --group dev pytest

lint:
	uv run --group dev ruff check .

format:
	uv run --group dev ruff format .
	uv run --group dev ruff check --fix-only .

lint-check:
	uv run --group dev ruff check .
	uv run --group dev ruff format --check .

check: lint-check test
	@echo "All checks passed!"

pre-commit-install:
	uv run --group dev pre-commit install
	@echo "pre-commit hooks installed (ruff format + lint on git commit)"

pre-commit-run:
	uv run --group dev pre-commit run --all-files

clean:
	rm -rf build/ dist/ *.egg-info htmlcov/ .coverage .pytest_cache/ .ruff_cache/ .venv/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@echo "Clean completed."

# Full agents stack (optional; not for day-to-day SQLite use)
setup-agents: sync db-up db-migrate rebuild
	@echo "Agents stack setup complete (Postgres + migrate + rebuild)!"
