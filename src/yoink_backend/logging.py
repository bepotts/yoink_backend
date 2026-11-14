# Configures structured JSON logs and request-scoped correlation fields.
"""Logging shared by the API and standard-library loggers."""

import logging
import sys
from time import perf_counter
from uuid import uuid4

import structlog
from fastapi import Request, Response
from starlette.middleware.base import RequestResponseEndpoint


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
    request_id = str(uuid4())
    structlog.contextvars.bind_contextvars(
        request_id=request_id, method=request.method, path=request.url.path
    )
    logger = structlog.get_logger(__name__)
    started = perf_counter()
    try:
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        logger.info(
            "request_completed",
            status_code=response.status_code,
            duration_ms=round((perf_counter() - started) * 1000, 2),
        )
        return response
    except Exception:
        logger.exception(
            "request_failed",
            status_code=500,
            duration_ms=round((perf_counter() - started) * 1000, 2),
        )
        raise
    finally:
        structlog.contextvars.clear_contextvars()
