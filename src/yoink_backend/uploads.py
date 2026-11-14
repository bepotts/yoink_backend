# Receives streamed multipart files and transfers them to the configured S3 bucket.
"""Backend-owned S3 uploads."""

import os
from contextlib import closing
from pathlib import PurePosixPath
from uuid import uuid4

import boto3
import structlog
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import APIRouter, HTTPException, UploadFile

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/uploads/s3", tags=["uploads"])


# Resolves server-side bucket settings without accepting destinations from clients.
def destination() -> tuple[str, str, str]:
    """Resolve the active bucket without falling back to another environment."""
    environment = os.getenv("APP_ENV", "development").strip().lower()
    if environment not in {"development", "production"}:
        raise HTTPException(503, "APP_ENV must be development or production.")
    namespace = "S3_PROD" if environment == "production" else "S3_DEV"
    bucket = os.getenv(f"{namespace}_BUCKET", "").strip()
    region = os.getenv(f"{namespace}_REGION", "").strip()
    prefix = os.getenv(f"{namespace}_PREFIX", "").strip("/")
    if not bucket or not region:
        raise HTTPException(
            503, f"Configure {namespace}_BUCKET and {namespace}_REGION on the backend."
        )
    if (
        os.getenv("S3_DEV_BUCKET", "").strip()
        == os.getenv("S3_PROD_BUCKET", "").strip()
    ):
        raise HTTPException(
            503, "Development and production must use different S3 buckets."
        )
    return bucket, region, prefix


# Checks authenticated bucket access without creating or changing S3 objects.
def check_s3_connection() -> None:
    """Fail when the active bucket cannot be reached with backend credentials."""
    bucket, region, _ = destination()
    try:
        client = boto3.client(
            "s3",
            region_name=region,
            config=Config(
                connect_timeout=5,
                read_timeout=5,
                retries={"total_max_attempts": 2},
            ),
        )
        with closing(client):
            client.head_bucket(Bucket=bucket)
    except (BotoCoreError, ClientError) as error:
        raise RuntimeError(
            "S3 connection check failed. Check backend credentials, bucket, region, "
            "and s3:ListBucket permission."
        ) from error


# Allows the desktop app to check server configuration before downloading videos.
@router.get("")
def ready() -> dict[str, str]:
    """Report whether the upload destination is configured."""
    destination()
    return {"status": "ready"}


# Runs blocking AWS transfers in FastAPI's worker thread using a spooled file.
@router.post("", status_code=201)
def upload(file: UploadFile) -> dict[str, str]:
    """Upload a nonempty file under a unique server-generated S3 key."""
    bucket, region, prefix = destination()
    name = PurePosixPath((file.filename or "").replace("\\", "/")).name
    if not name or name in {".", ".."} or file.size == 0:
        raise HTTPException(400, "Choose a named, nonempty file.")
    key = f"{prefix + '/' if prefix else ''}{uuid4()}-{name}"
    try:
        client = boto3.client("s3", region_name=region)
        with closing(client):
            client.upload_fileobj(
                file.file,
                bucket,
                key,
                ExtraArgs={
                    "ContentType": file.content_type or "application/octet-stream"
                },
            )
    except (BotoCoreError, ClientError) as error:
        logger.exception("s3_upload_failed", region=region)
        raise HTTPException(
            502, "S3 upload failed. Check backend AWS configuration."
        ) from error
    logger.info("s3_upload_completed", region=region, size_bytes=file.size)
    return {"bucket": bucket, "key": key}
