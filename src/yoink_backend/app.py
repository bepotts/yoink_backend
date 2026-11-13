# Defines the FastAPI application and its health endpoint.
"""HTTP API for Yoink backend services."""

from fastapi import FastAPI

app = FastAPI(title="Yoink Backend", version="0.1.0")


# Reports readiness for container health checks and monitoring.
@app.get("/health")
def health() -> dict[str, str]:
    """Return the service's health status."""
    return {"status": "ok"}
