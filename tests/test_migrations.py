# Verifies the initial migration creates and reverses the mapped request schema.
"""Migration regression tests without external PostgreSQL dependencies."""

import io
import runpy
from pathlib import Path

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
