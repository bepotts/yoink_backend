# Provides common commands for developing and validating the project.
.DEFAULT_GOAL := help

# Matches GitHub's Linux runners, including when act runs on Apple Silicon.
ACT_FLAGS ?= --workflows .github/workflows/ci.yml --container-architecture linux/amd64 --platform ubuntu-latest=catthehacker/ubuntu:act-latest
# Binds the checkout so the secrets job's nested Docker scan can read it on the host.
ACT_SECURITY_FLAGS ?= --workflows .github/workflows/security.yml --container-architecture linux/amd64 --platform ubuntu-latest=catthehacker/ubuntu:act-latest --bind
# Keeps local application configuration and credentials out of simulated CI jobs.
ACT_INPUTS := --env-file /dev/null --secret-file /dev/null --var-file /dev/null --input-file /dev/null

.PHONY: act-list act-check act-docker act-secrets act-ci migrate migration-check help install run dev check lint format-check typecheck format test build docker-build docker-start docker-start-production docker-down-production docker-logs-production docker-up docker-down docker-logs

help:
	@printf '%s\n' \
	  'act-list      List GitHub Actions jobs available locally' \
	  'act-check     Run lint, types, tests, and packaging with act' \
	  'act-docker    Run the Docker build and smoke test with act' \
	  'act-secrets   Run the GitHub secrets workflow locally with act' \
	  'act-ci        Run the full GitHub Actions workflow with act' \
	  'install       Install locked development dependencies' \
	  'migrate       Apply migrations to the APP_ENV-selected database' \
	  'migration-check Check ORM models against the migrated schema' \
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
	  'docker-start  Build, migrate, and start the API in Docker' \
	  'docker-start-production Build, migrate, and start using Amazon RDS' \
	  'docker-down-production Stop the production API' \
	  'docker-logs-production Follow production API logs' \
	  'docker-up     Alias for docker-start' \
	  'docker-down   Stop and remove Docker services' \
	  'docker-logs   Follow backend container logs'

install:
	uv sync --locked

run:
	uv run --locked yoink-backend

dev:
	uv run --locked uvicorn yoink_backend.app:app --reload --no-access-log --host 127.0.0.1 --port 8000

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

# Builds the API, prepares its database, and waits until the service is healthy.
docker-start:
	docker compose build backend migrate
	docker compose up --detach --wait postgres
	docker compose run --rm --no-deps migrate
	docker compose up --detach --wait backend

# Starts only the API and applies migrations to the configured RDS database.
docker-start-production:
	docker compose -f compose.production.yaml build backend migrate
	docker compose -f compose.production.yaml run --rm --no-deps migrate
	docker compose -f compose.production.yaml up --detach --wait backend

# Stops the production API without changing the RDS database.
docker-down-production:
	docker compose -f compose.production.yaml down

# Follows logs from the production API connected to RDS.
docker-logs-production:
	docker compose -f compose.production.yaml logs --follow backend

# Preserves the existing startup command with the same migration ordering.
docker-up: docker-start

docker-down:
	docker compose down

docker-logs:
	docker compose logs --follow backend

migrate:
	uv run --locked alembic upgrade head

migration-check:
	uv run --locked alembic check

# Lists jobs without starting runner containers.
act-list:
	act push $(ACT_FLAGS) $(ACT_INPUTS) --list

# Runs the Python CI jobs in sequence and stops on the first failure.
act-check:
	act push $(ACT_FLAGS) $(ACT_INPUTS) --job lint
	act push $(ACT_FLAGS) $(ACT_INPUTS) --job checks
	act push $(ACT_FLAGS) $(ACT_INPUTS) --job build

# Exercises the workflow's Docker build and startup smoke test.
act-docker:
	act push $(ACT_FLAGS) $(ACT_INPUTS) --job docker

# Runs every push-triggered job from the backend workflow.
act-ci:
	act push $(ACT_FLAGS) $(ACT_INPUTS)

# Runs only the secrets job, using its checked-in Betterleaks configuration.
act-secrets:
	act push $(ACT_SECURITY_FLAGS) $(ACT_INPUTS) --job secrets
