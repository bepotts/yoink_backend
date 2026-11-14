# Configures structured JSON logs and request-scoped correlation fields.
"""Logging shared by the API and standard-library loggers."""

import logging
import sys
from datetime import UTC, datetime
from time import perf_counter
from uuid import UUID, uuid4

import structlog
from fastapi import Request, Response
from starlette.middleware.base import RequestResponseEndpoint

from yoink_backend.database import save_request
from yoink_backend.schemas import RequestLogCreate


# Routes application and library records through the same JSON processor chain.
def configure_logging() -> None:
    """Emit timestamped JSON records to stdout at INFO level."""
    processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.format_exc_info,
    ]
    structlog.configure(
        processors=[
            *processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=processors,
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                structlog.processors.JSONRenderer(),
            ],
        )
    )
    logging.basicConfig(handlers=[handler], level=logging.INFO, force=True)


# Correlates each request and logs its outcome without headers, bodies, or queries.
async def log_request(request: Request, call_next: RequestResponseEndpoint) -> Response:
    """Record elapsed time and status, preserving unexpected exceptions."""
    structlog.contextvars.clear_contextvars()
    try:
        request_id = UUID(request.headers.get("X-Request-ID", ""))
    except ValueError:
        request_id = uuid4()
    started_at = datetime.now(UTC)
    status_code = 500
    error_type = None
    structlog.contextvars.bind_contextvars(
        request_id=str(request_id), method=request.method, path=request.url.path
    )
    logger = structlog.get_logger(__name__)
    started = perf_counter()
    try:
        response = await call_next(request)
        response.headers["X-Request-ID"] = str(request_id)
        status_code = response.status_code
        logger.info(
            "request_completed",
            status_code=response.status_code,
            duration_ms=round((perf_counter() - started) * 1000, 2),
        )
        return response
    except Exception as error:
        error_type = type(error).__name__
        logger.exception(
            "request_failed",
            status_code=500,
            duration_ms=round((perf_counter() - started) * 1000, 2),
        )
        raise
    finally:
        try:
            await save_request(
                request.app.state.database,
                RequestLogCreate(
                    request_id=request_id,
                    started_at=started_at,
                    method=request.method,
                    path=request.url.path,
                    status_code=status_code,
                    duration_ms=round((perf_counter() - started) * 1000, 2),
                    client_ip=request.client.host if request.client else None,
                    user_agent=request.headers.get("user-agent"),
                    http_version=request.scope.get("http_version", "1.1"),
                    error_type=error_type,
                ),
            )
        except Exception:
            logger.exception("request_log_persistence_failed")
        finally:
            structlog.contextvars.clear_contextvars()
