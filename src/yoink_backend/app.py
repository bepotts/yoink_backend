# Defines the FastAPI application and its health endpoint.
"""HTTP API for Yoink backend services."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from starlette.concurrency import run_in_threadpool

from yoink_backend.uploads import check_s3_connection, router

load_dotenv(".env.local")
load_dotenv(".env")


# Blocks startup until the configured environment's S3 bucket passes its check.
@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncGenerator[None]:
    """Refuse to serve requests if S3 configuration or connectivity fails."""
    await run_in_threadpool(check_s3_connection)
    yield


app = FastAPI(title="Yoink Backend", version="0.1.0", lifespan=lifespan)
app.include_router(router)


# Reports readiness for container health checks and monitoring.
@app.get("/health")
def health() -> dict[str, str]:
    """Return the service's health status."""
    return {"status": "ok"}
