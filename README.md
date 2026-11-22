# Yoink Backend

Python 3.13+ project with a `src/` package layout. Uses uv, Ruff, pytest,
pytest-cov, mypy, and pre-commit.

The frontend lives in [yoink](https://github.com/bepotts/yoink).
See that repository for frontend setup instructions.

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

## S3 uploads

Copy `.env.example` to `.env`. Set `APP_ENV=development` (the default) or
`APP_ENV=production`. Configure `S3_DEV_BUCKET`, `S3_DEV_REGION`, and optional
`S3_DEV_PREFIX` for development; use `S3_PROD_BUCKET`, `S3_PROD_REGION`, and
`S3_PROD_PREFIX` for production. Use different buckets for each environment.
Missing settings never fall back to the other environment. Existing
`S3_BUCKET`, `S3_REGION`, and `S3_PREFIX` settings are replaced by these names.
Supply AWS credentials there or use the standard AWS credential
chain (such as a local profile or an IAM role). Never commit `.env`.
Local runs also load `.env.local`, with process environment values taking priority.
Restart the backend after changing settings.

Startup checks access to the active bucket with S3 `HeadBucket` and fails if
configuration, credentials, or bucket access is invalid. Grant the backend
`s3:ListBucket` on the bucket for this check. It does not create an object or
verify upload permissions.

The desktop app uses `YOINK_BACKEND_URL` (default `http://127.0.0.1:8000`)
and sends multipart files to `POST /uploads/s3`. The backend generates unique
object keys and returns the bucket and key after S3 completes. AWS settings
belong only on the backend. Grant its AWS identity `s3:PutObject` and
`s3:AbortMultipartUpload` for the destination prefix.

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
with safe placeholders in `.env.example`.
