# Verifies typed database mappings, validated inputs, and transaction cleanup.
"""Tests for SQLAlchemy and Pydantic request storage."""

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from yoink_backend.database import open_database, save_request
from yoink_backend.models import RequestLog
from yoink_backend.schemas import RequestLogCreate
from yoink_backend.settings import DatabaseSettings


# Supplies valid metadata that can be varied to exercise validation constraints.
def request_record() -> RequestLogCreate:
    """Build a valid request with SQL-like text treated as ordinary data."""
    return RequestLogCreate(
        request_id=uuid4(),
        started_at=datetime.now(UTC),
        method="GET",
        path="/'; DROP TABLE request_logs; --",
        status_code=404,
        duration_ms=1.5,
        client_ip="127.0.0.1",
        user_agent="test",
        http_version="1.1",
    )


# Requires PostgreSQL configuration and hides malformed credential-bearing input.
@pytest.mark.parametrize("url", [None, "", "sqlite:///test", "not-a-url"])
def test_invalid_url(monkeypatch: pytest.MonkeyPatch, url: str | None) -> None:
    """Reject missing or invalid PostgreSQL URLs before engine creation."""
    if url is None:
        monkeypatch.delenv("DATABASE_DEV_URL", raising=False)
    else:
        monkeypatch.setenv("DATABASE_DEV_URL", url)

    # Enters the database lifecycle with invalid settings.
    async def exercise() -> None:
        async with open_database():
            pytest.fail("Invalid configuration was accepted")

    with pytest.raises(ValueError):
        asyncio.run(exercise())


# Preserves existing URL configuration while selecting the async psycopg driver.
def test_database_lifecycle(monkeypatch: pytest.MonkeyPatch) -> None:
    """Check migrated tables and always dispose the engine."""
    monkeypatch.setenv("DATABASE_DEV_URL", "postgresql://user:secret@localhost/test")
    engine = MagicMock()
    engine.dispose = AsyncMock()
    connection = engine.begin.return_value.__aenter__.return_value
    connection.execute = AsyncMock()

    # Raises after startup to verify shutdown still releases connections.
    async def exercise() -> None:
        async with open_database() as sessions:
            assert isinstance(sessions, async_sessionmaker)
            assert sessions.kw["bind"] is engine
            raise RuntimeError("application failure")

    with patch(
        "yoink_backend.database.create_async_engine", return_value=engine
    ) as make:
        with pytest.raises(RuntimeError, match="application failure"):
            asyncio.run(exercise())
    assert make.call_args.args[0].drivername == "postgresql+psycopg"
    assert "secret" not in repr(DatabaseSettings())
    connection.execute.assert_awaited_once()
    assert "request_logs" in str(connection.execute.call_args.args[0])
    engine.dispose.assert_awaited_once()


# Confirms initialization failures release the engine as well.
def test_initialization_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """Propagate unavailable PostgreSQL rather than serving without storage."""
    monkeypatch.setenv("DATABASE_DEV_URL", "postgresql://localhost/test")
    engine = MagicMock()
    engine.dispose = AsyncMock()
    engine.begin.return_value.__aenter__.side_effect = RuntimeError("offline")

    # Attempts to initialize the database with a failing connection.
    async def exercise() -> None:
        async with open_database():
            pytest.fail("Initialization failure was ignored")

    with patch("yoink_backend.database.create_async_engine", return_value=engine):
        with pytest.raises(RuntimeError, match="offline"):
            asyncio.run(exercise())
    engine.dispose.assert_awaited_once()


# Writes ORM entities in their own commit-or-rollback session context.
def test_save_request() -> None:
    """Convert validated fields into an ORM entity without interpolating SQL."""
    sessions = MagicMock(spec=async_sessionmaker[AsyncSession])
    context = sessions.begin.return_value
    context.__aenter__.return_value = MagicMock(spec=AsyncSession)
    session = context.__aenter__.return_value
    record = request_record()
    asyncio.run(save_request(sessions, record))
    stored = session.add.call_args.args[0]
    assert isinstance(stored, RequestLog)
    assert RequestLogCreate.model_validate(stored) == record
    context.__aexit__.assert_awaited_once_with(None, None, None)


# Ensures insert errors escape the transaction context for automatic rollback.
def test_save_failure() -> None:
    """Let the session manager roll back rather than suppressing insert errors."""
    sessions = MagicMock(spec=async_sessionmaker[AsyncSession])
    context = sessions.begin.return_value
    context.__aenter__.return_value = MagicMock(spec=AsyncSession)
    context.__aenter__.return_value.add.side_effect = RuntimeError("failed")
    with pytest.raises(RuntimeError, match="failed"):
        asyncio.run(save_request(sessions, request_record()))
    assert context.__aexit__.await_args.args[0] is RuntimeError


# Prevents impossible HTTP outcomes and nonfinite durations from reaching storage.
@pytest.mark.parametrize(
    "field,value",
    [
        ("status_code", 99),
        ("status_code", 600),
        ("duration_ms", -1),
        ("duration_ms", float("nan")),
        ("duration_ms", float("inf")),
        ("started_at", "2026-11-14T12:00:00"),
        ("method", ""),
        ("unexpected", True),
    ],
)
def test_request_validation(field: str, value: object) -> None:
    """Reject invalid metadata before constructing SQLAlchemy entities."""
    values = request_record().model_dump()
    values[field] = value
    with pytest.raises(ValidationError):
        RequestLogCreate.model_validate(values)


# Verifies environment selection, no cross-environment fallback, and isolation.
@pytest.mark.parametrize("environment", ["development", "production"])
def test_environment_selection(
    monkeypatch: pytest.MonkeyPatch, environment: str
) -> None:
    """Select only the active environment's database."""
    monkeypatch.setenv("APP_ENV", environment)
    monkeypatch.setenv("DATABASE_DEV_URL", "postgresql://localhost/yoink_development")
    monkeypatch.setenv("DATABASE_PROD_URL", "postgresql://localhost/yoink_production")
    settings = DatabaseSettings()
    assert str(settings.database_url).endswith(f"/yoink_{environment}")
    active = "DATABASE_PROD_URL" if environment == "production" else "DATABASE_DEV_URL"
    monkeypatch.delenv(active)
    with pytest.raises(ValueError, match=active):
        _ = DatabaseSettings().database_url


# Ignores different credentials and drivers when checking database identity.
def test_shared_database_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prevent accidental writes to the same PostgreSQL database."""
    monkeypatch.setenv("DATABASE_DEV_URL", "postgresql://dev@localhost/shared")
    monkeypatch.setenv(
        "DATABASE_PROD_URL", "postgresql+psycopg://prod@localhost:5432/shared"
    )
    with pytest.raises(ValueError, match="different databases"):
        _ = DatabaseSettings().database_url


# Rejects unrecognized environments before creating any database connection.
def test_invalid_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep misspelled environments from silently selecting development."""
    monkeypatch.setenv("APP_ENV", "staging")
    with pytest.raises(ValidationError):
        DatabaseSettings()
