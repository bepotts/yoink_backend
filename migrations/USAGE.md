<!-- Explains how to apply and maintain versioned backend database schemas. -->
# Database migrations

Run commands from the backend directory. Alembic loads `.env.local` before `.env`,
while existing process environment variables take precedence. `APP_ENV` selects
`DATABASE_DEV_URL` or `DATABASE_PROD_URL`; it never falls back between them.

Apply pending migrations before starting the API:

```sh
make migrate
```

For production, supply its database URL and select the environment explicitly:

```sh
APP_ENV=production make migrate
```

In Docker, run migrations before starting the backend:

```sh
docker compose run --rm backend alembic upgrade head
```

After changing ORM models, generate and review a revision, then apply it:

```sh
uv run --locked alembic revision --autogenerate -m "Describe schema change"
make migrate
make migration-check
```

For a database that already has `request_logs` from the former `create_all()`
startup behavior, verify every column, constraint, and index matches revision
`0001` before running `uv run --locked alembic stamp 0001`. Stamping records the
revision without creating tables or changing request records. Empty databases
should use `make migrate` directly.

To preview SQL without connecting, run `uv run --locked alembic upgrade head --sql`.
