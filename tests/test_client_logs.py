# Verifies bounded desktop telemetry and rejection of private fields.
"""Tests for the public, write-only log relay."""

import asyncio
import logging
from collections.abc import Iterator
from logging.handlers import BufferingHandler
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import Request
from fastapi.testclient import TestClient

from yoink_backend.app import app
from yoink_backend.observability.client_logs import LogRateLimit, receive_client_logs


# Starts the real routing stack with an isolated in-memory destination and limiter.
@pytest.fixture
def relay(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[tuple[TestClient, BufferingHandler]]:
    monkeypatch.setattr(
        "yoink_backend.observability.client_logs.limiter", LogRateLimit()
    )
    logger = logging.getLogger("yoink.frontend")
    previous, level = logger.handlers[:], logger.level
    with patch("yoink_backend.app.check_s3_connection"), TestClient(app) as client:
        handler = BufferingHandler(1000)
        logger.handlers = [handler]
        logger.setLevel(logging.INFO)
        try:
            yield client, handler
        finally:
            logger.handlers = previous
            logger.setLevel(level)


# Relays supported severities with no arbitrary payload or AWS destination selection.
def test_accepts_labels(relay: tuple[TestClient, BufferingHandler]) -> None:
    client, handler = relay
    response = client.post(
        "/logs",
        json={
            "events": [
                {"level": "info", "message": "Download started"},
                {"level": "warn", "message": "Download rejected"},
                {"level": "error", "message": "Download failed"},
            ]
        },
    )
    assert response.status_code == 202
    assert [record.levelno for record in handler.buffer] == [20, 30, 40]
    assert [record.getMessage() for record in handler.buffer] == [
        "Download started",
        "Download rejected",
        "Download failed",
    ]


# Rejects private messages, extra fields, invalid JSON, and excess events.
@pytest.mark.parametrize(
    "content",
    [
        b"not json",
        b'{"events":[]}',
        b'{"events":[{"level":"info","message":"https://example.com/?token=secret"}]}',
        b'{"events":[{"level":"info","message":"Download started","token":"secret"}]}',
        b'{"events":[{"level":"debug","message":"Download started"}]}',
        b'{"events":['
        + b",".join([b'{"level":"info","message":"Download started"}'] * 21)
        + b"]}",
    ],
)
def test_rejects_invalid(
    relay: tuple[TestClient, BufferingHandler], content: bytes
) -> None:
    client, handler = relay
    response = client.post("/logs", content=content)
    assert response.status_code == 422
    assert "secret" not in response.text
    assert not handler.buffer


# Bounds the streamed body before expensive JSON parsing.
def test_large_body(relay: tuple[TestClient, BufferingHandler]) -> None:
    client, handler = relay
    assert client.post("/logs", content=b"x" * 16_385).status_code == 413
    assert not handler.buffer


# Returns a clear unavailable response when server-side CloudWatch logging is disabled.
def test_unconfigured(relay: tuple[TestClient, BufferingHandler]) -> None:
    client, _ = relay
    logging.getLogger("yoink.frontend").handlers = []
    assert client.post("/logs", json={"events": []}).status_code == 503


# Caps clients and the whole worker, and expires the counters every minute.
def test_rate_windows() -> None:
    limiter = LogRateLimit()
    for _ in range(60):
        assert limiter.allow("same-client")
    assert not limiter.allow("same-client")
    limiter = LogRateLimit()
    for index in range(300):
        assert limiter.allow(str(index))
    assert not limiter.allow("another")
    with patch(
        "yoink_backend.observability.client_logs.monotonic",
        return_value=limiter.started + 61,
    ):
        assert limiter.allow("another")
    assert limiter.total == 1
    assert len(limiter.counts) == 1


# Enforces HTTP rate limits and advertises the retry window.
def test_http_rate_limit(relay: tuple[TestClient, BufferingHandler]) -> None:
    client, _ = relay
    with patch(
        "yoink_backend.observability.client_logs.limiter.allow", return_value=False
    ):
        response = client.post("/logs", json={"events": []})
    assert response.status_code == 429
    assert response.headers["Retry-After"] == "60"


# Handles local ASGI invocations without a client address using the same bounded path.
def test_missing_client(relay: tuple[TestClient, BufferingHandler]) -> None:
    request = Request(
        {"type": "http", "headers": []},
        receive=AsyncMock(
            return_value={
                "type": "http.request",
                "body": b'{"events":[{"level":"info","message":"Application log"}]}',
                "more_body": False,
            }
        ),
    )
    assert asyncio.run(receive_client_logs(request)).status_code == 202


# Exercises real rejection paths through middleware without backend persistence.
@pytest.mark.parametrize("status", [413, 422, 429, 503])
def test_rejections_skip_backend_writes(
    relay: tuple[TestClient, BufferingHandler], status: int
) -> None:
    client, _ = relay
    if status == 503:
        logging.getLogger("yoink.frontend").handlers = []
    with (
        patch(
            "yoink_backend.observability.client_logs.limiter.allow",
            return_value=status != 429,
        ),
        patch(
            "yoink_backend.observability.logging.save_request", new_callable=AsyncMock
        ) as save,
        patch("yoink_backend.observability.logging.structlog.get_logger") as logger,
    ):
        response = client.post("/logs", content=b"x" * (16_385 if status == 413 else 1))
        assert response.status_code == status
        assert response.headers["X-Request-ID"]
        save.assert_not_awaited()
        logger.return_value.info.assert_not_called()
