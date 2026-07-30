.PHONY: install format lint type test bench check build scan

install:
	python -m pip install -e '.[dev]'

format:
	ruff format src tests
	ruff check --fix src tests

lint:
	ruff format --check src tests
	ruff check src tests

type:
	mypy src

test:
	pytest --cov=agentguard --cov-report=term-missing --cov-fail-under=85

bench:
	python -m tools.bench
	python -m tools.bench --field-only

check: lint type test bench

build:
	python -m build

scan:
	agentguard scan src --fail-on medium
