# Routes backend and relayed desktop logs into separate CloudWatch log groups.
"""Batched CloudWatch delivery using only server-side AWS credentials."""

import logging
import os
from typing import cast

import boto3
import watchtower
from botocore.config import Config

_handlers: list[tuple[logging.Logger, watchtower.CloudWatchLogHandler]] = []


# Excludes relayed desktop records and AWS delivery diagnostics from backend ingestion.
class BackendLogFilter(logging.Filter):
    # Prevents duplicate desktop records and recursive AWS logging.
    def filter(self, record: logging.LogRecord) -> bool:
        return not record.name.startswith(
            ("yoink.frontend", "botocore", "boto3", "urllib3", "watchtower")
        )


# Installs independent batched destinations when CloudWatch is explicitly enabled.
def configure_cloudwatch_logging(formatter: logging.Formatter) -> None:
    """Use the standard AWS credential chain; never accept credentials from clients."""
    close_cloudwatch_logging()
    if os.environ.get("CLOUDWATCH_ENABLED", "").lower() != "true":
        return
    region = os.environ.get("CLOUDWATCH_REGION", "").strip()
    if not region:
        raise ValueError("Configure CLOUDWATCH_REGION when CloudWatch is enabled.")
    prefix = os.environ.get("CLOUDWATCH_LOG_GROUP_PREFIX", "/yoink").rstrip("/")
    environment = os.environ.get("APP_ENV", "development")
    client = boto3.client(
        "logs",
        region_name=region,
        config=Config(connect_timeout=3, read_timeout=3, retries={"max_attempts": 2}),
    )
    frontend = logging.getLogger("yoink.frontend")
    frontend.setLevel(logging.INFO)
    frontend.propagate = False
    try:
        for source, logger in (
            ("backend", logging.getLogger()),
            ("frontend", frontend),
        ):
            handler = watchtower.CloudWatchLogHandler(
                boto3_client=client,
                log_group_name=f"{prefix}/{environment}/{source}",
                log_stream_name="{machine_name}/{process_id}",
                create_log_group=True,
                log_group_retention_days=30,
                send_interval=5,
                max_batch_count=100,
            )
            handler.setLevel(logging.INFO)
            handler.setFormatter(formatter)
            if source == "backend":
                handler.addFilter(BackendLogFilter())
            logger.addHandler(handler)
            _handlers.append((logger, handler))
    except Exception:
        close_cloudwatch_logging()
        raise


# Flushes queued events and detaches delivery handlers on shutdown or reconfiguration.
def close_cloudwatch_logging() -> None:
    """Preserve standard output logging while closing only remote handlers."""
    for logger, handler in _handlers:
        logger.removeHandler(handler)
        cast(logging.Handler, handler).close()
    _handlers.clear()
