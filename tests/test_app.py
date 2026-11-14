# Verifies HTTP health reporting and generated API documentation.
"""Tests for the FastAPI application."""

from collections.abc import Iterator
from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient

from yoink_backend.app import app


# Isolates application lifecycle tests from real AWS credentials and networking.
@pytest.fixture(autouse=True)
def s3_check() -> Iterator[Mock]:
    """Provide a successful connection check unless a test overrides it."""
    with patch("yoink_backend.app.check_s3_connection") as check:
        yield check


# Checks that health probes receive a successful JSON response.
def test_health() -> None:
    """Verify the container health endpoint."""
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


# Checks that interactive API documentation and the schema are available.
def test_documentation() -> None:
    """Verify the documented health route is discoverable."""
    with TestClient(app) as client:
        assert client.get("/docs").status_code == 200
        schema = client.get("/openapi.json").json()
    assert "/health" in schema["paths"]


# Verifies startup invokes the connection test before the app serves requests.
def test_startup_checks_s3(s3_check: Mock) -> None:
    """Require successful S3 validation during startup."""
    with TestClient(app) as client:
        s3_check.assert_called_once_with()
        assert client.get("/health").status_code == 200


# Verifies failed S3 validation prevents application startup.
def test_startup_rejects_s3_failure(s3_check: Mock) -> None:
    """Propagate the connection failure instead of serving a healthy API."""
    s3_check.side_effect = RuntimeError("S3 connection check failed")
    with pytest.raises(RuntimeError, match="S3 connection check failed"):
        with TestClient(app):
            pytest.fail("The application started despite an S3 failure")


# Confirms all HTTP outcomes create one database row sharing the response ID.
def test_request_rows(database: Mock) -> None:
    """Persist successful, missing, and invalid requests with safe metadata."""
    with TestClient(app) as client:
        responses = [
            client.get("/health?token=private", headers={"User-Agent": "test-agent"}),
            client.get("/missing"),
            client.post("/uploads/s3"),
        ]
    session = database.begin.return_value.__aenter__.return_value
    calls = session.add.call_args_list
    assert len(calls) == 3
    for response, call in zip(responses, calls, strict=True):
        record = call.args[0]
        assert str(record.request_id) == response.headers["X-Request-ID"]
        assert record.status_code == response.status_code
        assert record.duration_ms >= 0
        assert "private" not in record.path
    assert calls[0].args[0].user_agent == "test-agent"


# Confirms PostgreSQL initialization errors prevent the API from starting.
def test_startup_rejects_database_failure() -> None:
    """Surface missing database connectivity before serving any requests."""
    with patch("yoink_backend.app.open_database") as database:
        database.return_value.__aenter__.side_effect = RuntimeError("database offline")
        with pytest.raises(RuntimeError, match="database offline"):
            with TestClient(app):
                pytest.fail("The application started despite a database failure")
