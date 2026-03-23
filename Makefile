.PHONY: install dev test lint format clean

install:
	pip install -e .

dev:
	pip install -e ".[dev]"

test:
	pytest tests/unit -v

test-all:
	pytest -v

test-e2e:
	pytest tests/e2e -v -m e2e

lint:
	ruff check src/ tests/
	ruff format --check src/ tests/

format:
	ruff check --fix src/ tests/
	ruff format src/ tests/

typecheck:
	mypy src/agent_forge

clean:
	rm -rf build/ dist/ *.egg-info .pytest_cache .mypy_cache .ruff_cache
	find . -type d -name __pycache__ -exec rm -rf {} +
