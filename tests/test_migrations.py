# Verifies the initial migration creates and reverses the mapped request schema.
"""Migration regression tests without external PostgreSQL dependencies."""

import io
import runpy
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect

from yoink_backend.models import Base

ROOT = Path(__file__).resolve().parents[1]


# Exercises upgrade and downgrade independently of SQLAlchemy's create_all.
def test_request_log_migration() -> None:
    """Require the revision to match ORM metadata and remove its schema cleanly."""
    revision = runpy.run_path(
        str(ROOT / "migrations/versions/0001_create_request_logs.py")
    )
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            revision["upgrade"]()
            assert compare_metadata(context, Base.metadata) == []
            assert inspect(connection).get_pk_constraint("request_logs")[
                "constrained_columns"
            ] == ["request_id"]
            assert len(inspect(connection).get_check_constraints("request_logs")) == 2
            revision["downgrade"]()
            assert not inspect(connection).has_table("request_logs")
    engine.dispose()


# Confirms deployments can inspect SQL without database access or credentials.
def test_offline_migration() -> None:
    """Render complete PostgreSQL DDL from the configured revision chain."""
    output = io.StringIO()
    config = Config(str(ROOT / "alembic.ini"), output_buffer=output)
    command.upgrade(config, "head", sql=True)
    sql = output.getvalue()
    assert "CREATE TABLE request_logs" in sql
    assert "request_id UUID NOT NULL" in sql
    assert "TIMESTAMP WITH TIME ZONE" in sql
    assert "CREATE INDEX request_logs_started_at_idx" in sql
    assert "INSERT INTO alembic_version" in sql


# Requires each environment to render its own restricted role without leaking secrets.
@pytest.mark.parametrize(
    ("environment", "role", "other_role"),
    [
        ("development", "yoink_dev_runtime", "yoink_prod_runtime"),
        ("production", "yoink_prod_runtime", "yoink_dev_runtime"),
    ],
)
def test_runtime_permissions_sql(
    monkeypatch: pytest.MonkeyPatch, environment: str, role: str, other_role: str
) -> None:
    """Verify exported DDL selects one login and grants only runtime access."""
    monkeypatch.setenv("APP_ENV", environment)
    monkeypatch.setenv(
        "DATABASE_DEV_URL",
        "postgresql://yoink_dev_runtime:private-secret@localhost/dev",
    )
    monkeypatch.setenv(
        "DATABASE_PROD_URL",
        "postgresql://yoink_prod_runtime:private-secret@localhost/prod",
    )
    output = io.StringIO()
    config = Config(str(ROOT / "alembic.ini"), output_buffer=output)
    command.upgrade(config, "0001:head", sql=True)
    sql = output.getvalue()
    assert f"CREATE ROLE {role}" in sql
    assert other_role not in sql
    assert "private-secret" not in sql
    assert f"GRANT SELECT, INSERT ON TABLE public.request_logs TO {role}" in sql
    assert f"REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {role}" in sql
    assert "NOCREATEROLE NOINHERIT" in sql
    assert "rolsuper OR rolreplication OR rolbypassrls" in sql
    assert "ALTER DEFAULT PRIVILEGES" in sql
