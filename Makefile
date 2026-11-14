# Provides common commands for developing and validating the project.
.DEFAULT_GOAL := help

.PHONY: help install run dev check lint format-check typecheck format test build docker-build docker-up docker-down docker-logs

help:
	@printf '%s\n' \
	  'install       Install locked development dependencies' \
	  'run           Start the API on port 8000' \
	  'dev           Start the API with automatic reload' \
	  'check         Run lint, formatting, types, and tests' \
	  'lint          Run Ruff lint checks' \
	  'format-check  Check formatting without modifying files' \
	  'typecheck     Run strict mypy checks' \
	  'format        Apply lint fixes and formatting' \
	  'test          Run tests with coverage' \
	  'build         Build wheel and source distribution' \
	  'docker-build  Build the Docker image' \
	  'docker-up     Build and start Docker services in the background' \
	  'docker-down   Stop and remove Docker services' \
	  'docker-logs   Follow backend container logs'

install:
	uv sync --locked

run:
	uv run --locked yoink-backend

dev:
	uv run --locked uvicorn yoink_backend.app:app --reload --host 127.0.0.1 --port 8000

check: lint format-check typecheck test

lint:
	uv run --locked ruff check .

format-check:
	uv run --locked ruff format --check .

typecheck:
	uv run --locked mypy

format:
	uv run --locked ruff check --fix .
	uv run --locked ruff format .

test:
	uv run --locked pytest

build:
	uv build

docker-build:
	docker compose build

docker-up:
	docker compose up --build --detach --wait

docker-down:
	docker compose down

docker-logs:
	docker compose logs --follow backend
