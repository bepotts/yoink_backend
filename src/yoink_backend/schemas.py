# Validates request metadata before it enters persistent storage.
"""Pydantic schemas for backend request logs."""

from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class RequestLogCreate(BaseModel):
    """Validate one request outcome independently of its database mapping."""

    # Accepts ORM instances for validated reads and rejects unexpected fields.
    model_config = ConfigDict(from_attributes=True, extra="forbid")
    # Correlates the row with the request's log events.
    request_id: UUID
    # Requires a timezone-aware request start time.
    started_at: AwareDatetime
    # Identifies the HTTP verb.
    method: str = Field(min_length=1)
    # Stores the path without query parameters.
    path: str
    # Restricts outcomes to valid HTTP status codes.
    status_code: int = Field(ge=100, le=599)
    # Rejects negative or nonfinite processing durations.
    duration_ms: float = Field(ge=0, allow_inf_nan=False)
    # Stores the server-observed client address when available.
    client_ip: str | None = None
    # Records the declared client software when available.
    user_agent: str | None = None
    # Identifies the HTTP protocol version.
    http_version: str
    # Identifies an unexpected exception without storing its message.
    error_type: str | None = None
