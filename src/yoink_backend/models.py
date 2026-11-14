# Defines SQLAlchemy mappings for backend database tables.
"""Typed database entities."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, Double, Index, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Collect SQLAlchemy mappings in shared metadata."""


class RequestLog(Base):
    """Store one HTTP request outcome without payloads or credentials."""

    # Preserves the existing PostgreSQL table name.
    __tablename__ = "request_logs"
    # Enforces valid outcomes and supports chronological queries.
    __table_args__ = (
        CheckConstraint("status_code BETWEEN 100 AND 599"),
        CheckConstraint("duration_ms >= 0"),
        Index("request_logs_started_at_idx", "started_at"),
    )
    # Correlates the database row with structlog and response headers.
    request_id: Mapped[UUID] = mapped_column(primary_key=True)
    # Records the UTC time at which processing began.
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # Identifies the HTTP verb.
    method: Mapped[str] = mapped_column(Text)
    # Stores the URL path without its query string.
    path: Mapped[str] = mapped_column(Text)
    # Records the resulting HTTP status.
    status_code: Mapped[int]
    # Measures processing time in milliseconds.
    duration_ms: Mapped[float] = mapped_column(Double)
    # Identifies the client address supplied by the ASGI server.
    client_ip: Mapped[str | None] = mapped_column(Text)
    # Records the client's declared software identifier.
    user_agent: Mapped[str | None] = mapped_column(Text)
    # Identifies the HTTP protocol version.
    http_version: Mapped[str] = mapped_column(Text)
    # Records the exception class for unexpected failures.
    error_type: Mapped[str | None] = mapped_column(Text)
