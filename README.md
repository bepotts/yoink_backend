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
