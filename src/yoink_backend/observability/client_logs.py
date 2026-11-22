# Accepts bounded desktop logs without exposing AWS credentials or arbitrary text.
"""Write-only telemetry ingestion for the public desktop application."""

import logging
from time import monotonic
from typing import Literal

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

CLIENT_LOG_MESSAGES = frozenset(
    {
        "Application log",
        "Application starting",
        "Application ready",
        "Application quitting",
        "Creating main window",
        "Child process exited",
        "Renderer exited",
        "Preload failed",
        "Window failed to load",
        "Main window is unresponsive",
        "React uncaught error",
        "React caught error",
        "React recovered from an error",
        "Download rejected",
        "Download started",
        "Download completed",
        "Download destination unavailable",
        "Download failed",
        "Cloud upload failed",
        "Could not clean up download temporary files",
        "Could not load Dropbox folders",
        "Could not open the Dropbox folder",
        "Could not load OneDrive folders",
        "Could not open the OneDrive folder",
        "Could not open the Google Drive folder",
        "Could not open the download folder",
        "Amazon S3 video upload failed",
        "Google Drive upload started",
        "Google Drive upload completed",
        "Google Drive upload failed",
    }
)
router = APIRouter()


class ClientLog(BaseModel):
    """Only known event labels and a severity may cross the telemetry boundary."""

    # Rejects fields that could carry URLs, credentials, or arbitrary provider payloads.
    model_config = ConfigDict(extra="forbid")
    # Limits severity to the levels forwarded by the desktop logger.
    level: Literal["info", "warn", "error"]
    # Constrains input size before the label allowlist is applied.
    message: str = Field(min_length=1, max_length=120)

    # Rejects arbitrary log text instead of trusting client-side redaction.
    @field_validator("message")
    @classmethod
    def known_label(cls, value: str) -> str:
        if value not in CLIENT_LOG_MESSAGES:
            raise ValueError("Unknown application log label.")
        return value


class ClientLogBatch(BaseModel):
    """Bounds each public write to a small number of short log labels."""

    # Disallows unexpected fields in incoming batches.
    model_config = ConfigDict(extra="forbid")
    # Bounds records and per-request CloudWatch ingestion cost.
    events: list[ClientLog] = Field(min_length=1, max_length=20)


class LogRateLimit:
    """Caps telemetry globally and per source with bounded memory per worker."""

    # Remembers only the current minute's request counts.
    counts: dict[str, int]
    # Marks the beginning of the active counting window.
    started: float
    # Tracks accepted batches independently of their source address.
    total: int

    # Initializes a fresh limiter for each application process or test.
    def __init__(self) -> None:
        self.counts = {}
        self.started = monotonic()
        self.total = 0

    # Applies limits without awaiting, keeping updates atomic within the event loop.
    def allow(self, source: str) -> bool:
        if monotonic() - self.started >= 60:
            self.counts.clear()
            self.started = monotonic()
            self.total = 0
        if self.total >= 300 or self.counts.get(source, 0) >= 60:
            return False
        self.total += 1
        self.counts[source] = self.counts.get(source, 0) + 1
        return True


limiter = LogRateLimit()


# Queues validated telemetry without letting clients choose AWS destinations.
@router.post("/logs", status_code=202)
async def receive_client_logs(request: Request) -> Response:
    """Apply body/rate limits before parsing, then send only allowlisted messages."""
    logger = logging.getLogger("yoink.frontend")
    if not logger.handlers:
        raise HTTPException(503, "CloudWatch log delivery is not configured.")
    if not limiter.allow(request.client.host if request.client else "unknown"):
        raise HTTPException(
            429, "Log rate limit exceeded.", headers={"Retry-After": "60"}
        )
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > 16_384:
            raise HTTPException(413, "Log batch is too large.")
        body.extend(chunk)
    try:
        batch = ClientLogBatch.model_validate_json(body)
    except ValidationError:
        raise HTTPException(422, "Invalid log batch.") from None
    for event in batch.events:
        level = {"info": logging.INFO, "warn": logging.WARNING, "error": logging.ERROR}[
            event.level
        ]
        logger.log(level, event.message)
    return Response(status_code=202)
