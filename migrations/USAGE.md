# Database migrations

Run commands from the backend directory. Alembic loads `.env.local` before `.env`,
while existing process environment variables take precedence. `APP_ENV` selects
`DATABASE_DEV_URL` or `DATABASE_PROD_URL`; it never falls back between them.

Each developer runs their own PostgreSQL instance with the same Alembic schema
and permission rules. Alembic requires an existing database; it does not create
the database server or database itself. `docker compose up -d postgres` creates
`yoink_development` using the checked-in Compose configuration.

Copy `.env.example` to `.env.local`. Set `DATABASE_DEV_URL` to the runtime login
`yoink_dev_runtime` with a locally chosen password. Set `DATABASE_DEV_ADMIN_URL`
to an administrator connection to that same database. For the default Homebrew
installation, use your macOS username as administrator; the Docker administrator
is `yoink` with password `yoink`. Keep credentials in ignored environment files.

Apply pending migrations before starting the API:

```sh
make migrate
```

Revision `0002` creates or reconciles the runtime login using the password from
`DATABASE_DEV_URL`. It grants read and insert access to `request_logs`, usage of
sequences, and read/insert access to future tables created by the migration
administrator. It removes public database connection/temporary-table access and
public schema creation access. Runtime users cannot update, delete, create tables,
or access Alembic's version table. Always run later migrations as the same owner
so default grants apply. Runtime login creation requires administrator privileges.

For production, use a separate Amazon RDS for PostgreSQL database and configure `DATABASE_PROD_URL` with
`yoink_prod_runtime` and a distinct password, plus `DATABASE_PROD_ADMIN_URL` for
that same database. Then run:

```sh
APP_ENV=production make migrate
```

Use separate databases for each environment; only the selected environment's role
is granted connection access. Revision `0002` deliberately cannot be downgraded;
removing shared cluster logins requires explicit administrator action. Changing a
password after this migration requires an administrator password rotation as well
as updating the runtime URL.

For Docker, runtime and administrator URLs must use `postgres` as the host rather
than `localhost`. With shell overrides for those URLs, run migrations before the API:

```sh
docker compose run --rm migrate
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
The preview contains no passwords. Before executing exported SQL, an administrator
must set `yoink.runtime_password` in the same transaction as revision `0002`.

## Production Docker with Amazon RDS

Production uses `compose.production.yaml`, which defines no local PostgreSQL
service. Create the RDS instance/database first and allow PostgreSQL traffic from
the application host in the RDS security group. Use the RDS endpoint in both
production URLs; the runtime user is `yoink_prod_runtime`, while migrations use
the RDS administrator/database owner. The role migration works without PostgreSQL
superuser access and refuses to reuse an elevated runtime role or one that owns
database objects. An administrator must transfer ownership before retrying.

Download the public Amazon RDS CA bundle into `certs/global-bundle.pem`:

```sh
mkdir -p certs
curl -fsSL https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem -o certs/global-bundle.pem
```

Set `DATABASE_PROD_URL` and `DATABASE_PROD_ADMIN_URL` in `.env` or the process
environment to the RDS endpoint/database, each with
`?sslmode=verify-full&sslrootcert=/app/certs/global-bundle.pem`. The production
container mounts the CA directory read-only and defaults to verified TLS.
For host-side Alembic commands, use the host's absolute CA path instead.
See [AWS TLS documentation](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/PostgreSQL.Concepts.General.SSL.html).

```sh
make docker-start-production
make docker-logs-production
make docker-down-production
```

The start command builds the API, migrates RDS, and starts the API. It does not
provision AWS resources or start the development PostgreSQL container.

Docker passes administrator URLs only to the one-off `migrate` service. The API
receives an explicit list of runtime settings for its selected environment; it
does not import the complete `.env` file. Compose reads `.env` for interpolation;
use `docker compose --env-file .env.local ...` when using `.env.local` instead.
