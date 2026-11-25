# Runs Alembic against the database selected by the backend environment settings.
"""Migration configuration shared by development and production."""

import os

from alembic import context
from dotenv import load_dotenv
from sqlalchemy import create_engine, pool
from sqlalchemy.engine import make_url

from yoink_backend.models import Base
from yoink_backend.settings import DatabaseSettings

load_dotenv(".env.local")
load_dotenv(".env")
target_metadata = Base.metadata


# Produces reviewable PostgreSQL migration SQL without opening a connection.
def run_migrations_offline() -> None:
    """Render migrations using the PostgreSQL dialect."""
    context.configure(
        dialect_name="postgresql",
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


# Applies migrations using the same explicit database selection as the application.
def run_migrations_online() -> None:
    """Run transactional DDL and release connections even when migrations fail."""
    settings = DatabaseSettings()
    runtime_url = make_url(str(settings.database_url))
    suffix = "PROD" if settings.app_env == "production" else "DEV"
    administrator = os.environ.get(f"DATABASE_{suffix}_ADMIN_URL", "")
    if not administrator:
        raise ValueError(f"Configure DATABASE_{suffix}_ADMIN_URL for migrations")
    url = make_url(administrator).set(drivername="postgresql+psycopg")
    if (url.database != runtime_url.database) or (url.host, url.port or 5432) != (
        runtime_url.host,
        runtime_url.port or 5432,
    ):
        raise ValueError("Administrator and runtime URLs must select the same database")
    engine = create_engine(
        url,
        poolclass=pool.NullPool,
        hide_parameters=True,
        connect_args={"connect_timeout": 5, "options": "-c statement_timeout=30000"},
    )
    try:
        with engine.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                compare_type=True,
            )
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
