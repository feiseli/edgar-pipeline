.PHONY: setup test lint smoke dev

# Bare `python` does not exist on stock macOS; override with PYTHON=... if needed
PYTHON ?= python3

setup:
	$(PYTHON) -m venv .venv && .venv/bin/pip install -e ".[dev]"

test:
	pytest

lint:
	ruff check src tests && ruff format --check src tests

# End-to-end against live EDGAR for one day (set EDGAR_USER_AGENT first):
#   make smoke DATE=2026-07-15
DATE ?= 2026-07-15
smoke:
	python -m edgar_pipeline.smoke $(DATE) --limit 25

# Local Dagster UI at http://localhost:3000
dev:
	dagster dev -m edgar_pipeline.definitions
