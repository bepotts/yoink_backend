# Initializes backend error reporting, request tracing, and structured logs.
"""Sentry configuration shared by development and production entry points."""

import logging
import os
from importlib.metadata import version

import sentry_sdk
from sentry_sdk.integrations.logging import LoggingIntegration, ignore_logger


# Enables monitoring only when a destination is configured for this deployment.
def configure_sentry() -> None:
    """Initialize before FastAPI construction using environment-specific sampling."""
    dsn = os.environ.get("SENTRY_DSN", "").strip()
    if not dsn:
        return
    environment = os.environ.get("APP_ENV", "development")
    ignore_logger("yoink.frontend")
    sentry_sdk.init(
        dsn=dsn,
        environment=environment,
        release=os.environ.get("SENTRY_RELEASE")
        or f"yoink-backend@{version('yoink-backend')}",
        traces_sample_rate=0.1 if environment == "production" else 1.0,
        enable_logs=False,
        data_collection={"user_info": False, "http_bodies": []},
        include_local_variables=False,
        max_request_body_size="never",
        integrations=[
            LoggingIntegration(
                level=logging.INFO, event_level=logging.ERROR, sentry_logs_level=None
            ),
        ],
    )
