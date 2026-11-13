# Yoink Backend

Python 3.13+ project with a `src/` package layout. Uses uv, Ruff, pytest,
pytest-cov, mypy, and pre-commit.

## Setup

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then run:

```sh
uv sync --locked
uv run --locked yoink-backend
```

uv installs the selected Python version when needed and creates `.venv`.
Commit `uv.lock` to keep dependency versions reproducible.

The command starts FastAPI on port 8000. Open [API docs](http://localhost:8000/docs)
or check [service health](http://localhost:8000/health). Stop with Ctrl+C.
`python -m yoink_backend` also starts the server inside the project environment.

## Docker

With Docker and Compose installed, run:

```sh
docker compose up --build
```

The API is available at the same local URLs. Stop with Ctrl+C, then run
`docker compose down` to remove the container. The image runs as a non-root user
and includes a health check. Compose binds the published port to localhost.

## Development

```sh
make check     # Lint, format check, type check, and tests with coverage
make format    # Apply lint fixes and formatting
make test      # Run tests with coverage
make build     # Build wheel and source distribution
```

Add runtime dependencies with `uv add PACKAGE`; add development tools with
`uv add --dev PACKAGE`. Commit the updated `pyproject.toml` and `uv.lock`.

After initializing Git, enable commit checks with `uv run pre-commit install`.
Keep private environment values in `.env.local` and document any added variables
with safe placeholders in `.env.example`. No environment variables are needed yet.
