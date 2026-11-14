# Isolates HTTP tests from external PostgreSQL connections.
"""Shared database mocks for API tests."""

from collections.abc import Iterator
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession


# Supplies fake sessions while keeping lifecycle and ORM writes observable.
@pytest.fixture(autouse=True)
def database(monkeypatch: pytest.MonkeyPatch) -> Iterator[MagicMock]:
    """Replace only the application's database context, leaving storage testable."""
    sessions = MagicMock()
    sessions.begin.return_value.__aenter__.return_value = MagicMock(spec=AsyncSession)
    context = MagicMock()
    context.return_value.__aenter__ = AsyncMock(return_value=sessions)
    context.return_value.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr("yoink_backend.app.open_database", context)
    yield sessions


# Isolates settings tests from developer-specific environment variables.
@pytest.fixture(autouse=True)
def database_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Start tests in development without a configured database destination."""
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.delenv("DATABASE_DEV_URL", raising=False)
    monkeypatch.delenv("DATABASE_PROD_URL", raising=False)
