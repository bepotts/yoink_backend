# Verifies HTTP health reporting and generated API documentation.
"""Tests for the FastAPI application."""

from fastapi.testclient import TestClient

from yoink_backend.app import app


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
