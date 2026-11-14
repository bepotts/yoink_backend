# Manages SQLAlchemy async sessions and persists validated request metadata.
"""PostgreSQL storage backed by SQLAlchemy and Pydantic."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy import select # pyright: ignore[reportMissingImports]
from sqlalchemy.engine import make_url # pyright: ignore[reportMissingImports]
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # pyright: ignore[reportMissingImports]

from yoink_backend.models import RequestLog
from yoink_backend.schemas import RequestLogCreate
from yoink_backend.settings import DatabaseSettings


# Checks migrated request storage before serving and releases connections on shutdown.
@asynccontextmanager
async def open_database() -> AsyncGenerator[async_sessionmaker[AsyncSession]]:
    """Create one engine and session factory per application lifecycle."""
    settings = DatabaseSettings()  # pyright: ignore[reportCallIssue]
    url = make_url(str(settings.database_url)).set(drivername="postgresql+psycopg")
    engine = create_async_engine(
        url,
        pool_size=5,
        max_overflow=5,
        pool_timeout=5,
        pool_pre_ping=True,
        hide_parameters=True,
        connect_args={"connect_timeout": 5, "options": "-c statement_timeout=5000"},
    )
    try:
        async with engine.begin() as connection:
            await connection.execute(select(RequestLog.request_id).limit(0))
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()


# Uses an independent transaction so request logging cannot commit endpoint work.
async def save_request(
    sessions: async_sessionmaker[AsyncSession], record: RequestLogCreate
) -> None:
    """Commit a validated ORM entity and roll back automatically on failure."""
    async with sessions.begin() as session:
        session.add(RequestLog(**record.model_dump()))
