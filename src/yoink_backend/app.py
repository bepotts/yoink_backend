# Defines the FastAPI application and its health endpoint.
"""HTTP API for Yoink backend services."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from dotenv import load_dotenv
from fastapi import FastAPI
from starlette.concurrency import run_in_threadpool

from yoink_backend.database import open_database
from yoink_backend.logging import configure_logging, log_request
from yoink_backend.monitoring import configure_sentry
from yoink_backend.uploads import check_s3_connection, router

load_dotenv(".env.local")
load_dotenv(".env")
configure_sentry()


# Initializes PostgreSQL and checks S3 before accepting requests.
@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncGenerator[None]:
    """Refuse to serve requests if S3 configuration or connectivity fails."""
    configure_logging()
    logger = structlog.get_logger(__name__)
    logger.info("startup_started")
    try:
        async with open_database() as sessions:
            application.state.database = sessions
            await run_in_threadpool(check_s3_connection)
            logger.info("startup_completed")
            try:
                yield
            finally:
                logger.info("shutdown_completed")
    except Exception:
        logger.exception("application_failed")
        raise


app = FastAPI(title="Yoink Backend", version="0.1.0", lifespan=lifespan)
app.middleware("http")(log_request)
app.include_router(router)


# Reports readiness for container health checks and monitoring.
@app.get("/health")
def health() -> dict[str, str]:
    """Return the service's health status."""
    return {"status": "ok"}
