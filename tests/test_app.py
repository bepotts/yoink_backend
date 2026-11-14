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
