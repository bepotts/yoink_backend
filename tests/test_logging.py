# Verifies structured output, request correlation, and exception propagation.
"""Tests for backend logging."""

import asyncio
import io
import json
import logging
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
import structlog
from fastapi import Request, Response

from yoink_backend.logging import configure_logging, log_request


# Confirms application and standard library logs share timestamped JSON formatting.
def test_json_logging() -> None:
    """Render both logging APIs and preserve exception details."""
    stream = io.StringIO()
    root = logging.getLogger()
    handlers, level = root.handlers[:], root.level
    try:
        with patch("yoink_backend.logging.sys.stdout", stream):
            configure_logging()
        structlog.get_logger("test").info("structured", count=2)
        logging.getLogger("library").warning("standard")
        try:
            raise ValueError("failure")
        except ValueError:
            structlog.get_logger("test").exception("failed")
        records = [json.loads(line) for line in stream.getvalue().splitlines()]
        assert records[0]["count"] == 2
        assert records[0]["level"] == "info"
        assert records[0]["timestamp"].endswith("Z")
        assert records[1]["logger"] == "library"
        assert records[1]["event"] == "standard"
        assert "ValueError: failure" in records[2]["exception"]
    finally:
        root.handlers = handlers
        root.setLevel(level)


# Exercises request IDs, safe metadata, cleanup, and re-raised request failures.
def test_request_logging() -> None:
    """Keep concurrent request context isolated and omit query secrets."""

    # Serves a successful response through the middleware test.
    async def success(request: Request) -> Response:
        await asyncio.sleep(0)
        return Response(status_code=201)

    # Simulates an unhandled application failure.
    async def failure(request: Request) -> Response:
        raise RuntimeError("broken")

    # Runs concurrent successful requests and a failing request in an event loop.
    async def exercise() -> None:
        request = Request(
            {
                "type": "http",
                "method": "POST",
                "path": "/test",
                "query_string": b"token=secret",
                "headers": [],
                "app": MagicMock(),
            }
        )
        with (
            structlog.testing.capture_logs() as records,
            patch("yoink_backend.logging.save_request", new_callable=AsyncMock) as save,
        ):
            responses = await asyncio.gather(
                log_request(request, success), log_request(request, success)
            )
            assert (
                responses[0].headers["X-Request-ID"]
                != responses[1].headers["X-Request-ID"]
            )
            with pytest.raises(RuntimeError, match="broken"):
                await log_request(request, failure)
        assert save.await_count == 3
        assert save.call_args.args[1].error_type == "RuntimeError"
        assert [record["status_code"] for record in records] == [201, 201, 500]
        assert records[-1]["event"] == "request_failed"
        assert "secret" not in str(records)
        assert structlog.contextvars.get_contextvars() == {}

    asyncio.run(exercise())


# Ensures a database failure does not replace the original response or exception.
def test_database_failure() -> None:
    """Retain JSON failure evidence and always clear request context."""

    # Simulates an HTTP response when storage is unavailable.
    async def respond(request: Request) -> Response:
        return Response(status_code=204)

    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/health",
            "headers": [],
            "client": ("127.0.0.1", 123),
            "app": MagicMock(),
        }
    )
    with (
        patch(
            "yoink_backend.logging.save_request", side_effect=RuntimeError("offline")
        ),
        structlog.testing.capture_logs() as records,
    ):
        response = asyncio.run(log_request(request, respond))
    assert response.status_code == 204
    assert records[-1]["event"] == "request_log_persistence_failed"
    assert structlog.contextvars.get_contextvars() == {}


# Preserves valid client IDs across response headers, structured logs, and storage.
@pytest.mark.parametrize("supplied", [str(uuid4()), "invalid-id", ""])
def test_client_request_id(supplied: str) -> None:
    """Use client UUIDs and generate a safe fallback for malformed headers."""

    # Returns a response through the request logging middleware.
    async def respond(request: Request) -> Response:
        return Response(status_code=200)

    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/health",
            "headers": [(b"x-request-id", supplied.encode())],
            "app": MagicMock(),
        }
    )
    with (
        patch("yoink_backend.logging.save_request", new_callable=AsyncMock) as save,
        patch("yoink_backend.logging.structlog.get_logger") as logger,
    ):
        response = asyncio.run(log_request(request, respond))
        with_context = structlog.contextvars.get_contextvars()
    request_id = response.headers["X-Request-ID"]
    assert str(UUID(request_id)) == request_id
    if supplied not in {"invalid-id", ""}:
        assert request_id == supplied
    else:
        assert request_id != supplied
    assert str(save.call_args.args[1].request_id) == request_id
    logger.return_value.info.assert_called_once()
    assert with_context == {}
