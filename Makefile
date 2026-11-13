# Provides common commands for developing and validating the project.
.PHONY: install run check format test build

install:
	uv sync --locked

run:
	uv run --locked yoink-backend

check:
	uv run --locked ruff check .
	uv run --locked ruff format --check .
	uv run --locked mypy
	uv run --locked pytest

format:
	uv run --locked ruff check --fix .
	uv run --locked ruff format .

test:
	uv run --locked pytest

build:
	uv build
