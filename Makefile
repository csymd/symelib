# Makefile
.PHONY: help install test lint format check clean

help:
	@echo "Available commands:"
	@echo "  make install     Install package and dependencies"
	@echo "  make test        Run tests with coverage"
	@echo "  make lint        Run ruff linter"
	@echo "  make format      Format code with ruff"
	@echo "  make check       Run all checks (lint + format check + tests)"
	@echo "  make clean       Remove build artifacts"

install:
	pip install -e ".[dev]"

test:
	pytest

lint:
	ruff check .

format:
	ruff format .

format-check:
	ruff format . --check

check: lint format-check test
	@echo "All checks passed!"

clean:
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info
	rm -rf htmlcov/
	rm -rf .coverage
	rm -rf .pytest_cache/
	rm -rf .ruff_cache/
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
#+END_SRC

Then you can run:

#+BEGIN_SRC bash
make install
make check
make format
