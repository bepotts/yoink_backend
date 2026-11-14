# Verifies server-owned S3 destination selection, transfers, and failure handling.
"""Tests for S3 uploads without contacting AWS."""

from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import BotoCoreError, ClientError
from fastapi.testclient import TestClient

from yoink_backend.app import app
from yoink_backend.uploads import check_s3_connection, destination


# Supplies isolated backend configuration for each upload test.
@pytest.fixture(autouse=True)
def configure(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set fake bucket settings without credentials."""
    monkeypatch.setattr("yoink_backend.app.check_s3_connection", lambda: None)
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("S3_DEV_BUCKET", "test-bucket")
    monkeypatch.setenv("S3_PROD_BUCKET", "production-bucket")
    monkeypatch.setenv("S3_PROD_REGION", "us-west-2")
    monkeypatch.setenv("S3_PROD_PREFIX", "production/")
    monkeypatch.setenv("S3_DEV_REGION", "us-east-1")
    monkeypatch.setenv("S3_DEV_PREFIX", "videos/")


# Verifies readiness and a successful transfer using only backend settings.
def test_upload() -> None:
    """Check the uploaded bytes, content type, and unique object key."""
    with patch("yoink_backend.uploads.boto3.client") as factory:
        client = factory.return_value
        with TestClient(app) as api:
            assert api.get("/uploads/s3").status_code == 200
            response = api.post(
                "/uploads/s3", files={"file": ("../video.mp4", b"video", "video/mp4")}
            )
        assert response.status_code == 201
        result = response.json()
        assert result["bucket"] == "test-bucket"
        assert result["key"].startswith("videos/")
        assert result["key"].endswith("-video.mp4")
        factory.assert_called_once_with("s3", region_name="us-east-1")
        args, kwargs = client.upload_fileobj.call_args
        assert args[1:] == ("test-bucket", result["key"])
        assert kwargs["ExtraArgs"] == {"ContentType": "video/mp4"}


# Verifies missing configuration is reported without making AWS requests.
def test_missing_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reject uploads when no server bucket is configured."""
    monkeypatch.delenv("S3_DEV_BUCKET")
    with TestClient(app) as api:
        assert api.get("/uploads/s3").status_code == 503
        assert api.post("/uploads/s3", files={"file": ("x", b"x")}).status_code == 503


# Verifies malformed or empty uploads fail before accessing AWS.
@pytest.mark.parametrize("name,data", [("empty.mp4", b""), ("..", b"x"), ("", b"x")])
def test_invalid_upload(name: str, data: bytes) -> None:
    """Reject unusable filenames and empty content."""
    with TestClient(app) as api:
        assert api.post("/uploads/s3", files={"file": (name, data)}).status_code in {
            400,
            422,
        }


# Verifies AWS errors are converted to sanitized backend responses.
@pytest.mark.parametrize(
    "error",
    [BotoCoreError(), ClientError({"Error": {"Code": "AccessDenied"}}, "PutObject")],
)
def test_aws_failure(error: Exception, monkeypatch: pytest.MonkeyPatch) -> None:
    """Hide AWS internals while reporting failed transfers."""
    monkeypatch.setenv("S3_DEV_PREFIX", "")
    with patch("yoink_backend.uploads.boto3.client", side_effect=error):
        with TestClient(app) as api:
            response = api.post("/uploads/s3", files={"file": ("x", b"x")})
    assert response.status_code == 502
    assert "AccessDenied" not in response.text


# Verifies missing MIME metadata falls back to a binary content type.
def test_missing_metadata() -> None:
    """Exercise optional metadata without an HTTP multipart parser."""
    from io import BytesIO

    from fastapi import UploadFile

    from yoink_backend.uploads import upload

    with patch("yoink_backend.uploads.boto3.client", return_value=MagicMock()):
        assert (
            upload(UploadFile(BytesIO(b"x"), filename="x"))["bucket"] == "test-bucket"
        )
        with pytest.raises(Exception, match="Choose a named"):
            upload(UploadFile(BytesIO(b"x")))


# Verifies production uploads use production storage and ignore development settings.
def test_production_upload(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep production object keys and client region separate from development."""
    monkeypatch.setenv("APP_ENV", "production")
    with patch("yoink_backend.uploads.boto3.client") as factory:
        with TestClient(app) as api:
            response = api.post("/uploads/s3", files={"file": ("video.mp4", b"x")})
        assert response.status_code == 201
        assert response.json()["bucket"] == "production-bucket"
        assert response.json()["key"].startswith("production/")
        factory.assert_called_once_with("s3", region_name="us-west-2")
        assert (
            factory.return_value.upload_fileobj.call_args.args[1] == "production-bucket"
        )


# Verifies a missing selector uses only development storage.
def test_default_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Use development by default without requiring production configuration."""
    monkeypatch.delenv("APP_ENV")
    monkeypatch.delenv("S3_PROD_BUCKET")
    assert destination() == ("test-bucket", "us-east-1", "videos")


# Verifies invalid environment settings cannot silently redirect uploads.
@pytest.mark.parametrize(
    "settings",
    [
        {"APP_ENV": "staging"},
        {"APP_ENV": "production", "S3_PROD_BUCKET": ""},
        {"APP_ENV": "production", "S3_PROD_REGION": ""},
        {"S3_DEV_BUCKET": "production-bucket"},
    ],
)
def test_environment_configuration_errors(
    settings: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reject missing active settings, shared buckets, and unknown environments."""
    for key, value in settings.items():
        monkeypatch.setenv(key, value)
    with patch("yoink_backend.uploads.boto3.client") as factory:
        with TestClient(app) as api:
            assert api.get("/uploads/s3").status_code == 503
            assert (
                api.post("/uploads/s3", files={"file": ("x", b"x")}).status_code == 503
            )
        factory.assert_not_called()


# Verifies the startup probe targets the active environment and closes its client.
@pytest.mark.parametrize(
    "environment,bucket",
    [("development", "test-bucket"), ("production", "production-bucket")],
)
def test_connection_check(
    environment: str, bucket: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Use a bounded HeadBucket request without uploading any data."""
    monkeypatch.setenv("APP_ENV", environment)
    with patch("yoink_backend.uploads.boto3.client") as factory:
        check_s3_connection()
        factory.return_value.head_bucket.assert_called_once_with(Bucket=bucket)
        factory.return_value.close.assert_called_once_with()
        config = factory.call_args.kwargs["config"]
        assert config.connect_timeout == 5
        assert config.read_timeout == 5
        assert config.retries == {"total_max_attempts": 2}
        factory.return_value.upload_fileobj.assert_not_called()


# Verifies AWS access and network failures abort the probe and release resources.
@pytest.mark.parametrize(
    "error", [BotoCoreError(), ClientError({"Error": {"Code": "403"}}, "HeadBucket")]
)
def test_connection_failure(error: Exception) -> None:
    """Provide actionable failure messages without treating access denial as success."""
    with patch("yoink_backend.uploads.boto3.client") as factory:
        factory.return_value.head_bucket.side_effect = error
        with pytest.raises(RuntimeError, match="S3 connection check failed"):
            check_s3_connection()
        factory.return_value.close.assert_called_once_with()


# Verifies missing bucket configuration aborts before creating an AWS client.
def test_connection_missing_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reject invalid startup configuration before network activity."""
    from fastapi import HTTPException

    monkeypatch.delenv("S3_DEV_BUCKET")
    with patch("yoink_backend.uploads.boto3.client") as factory:
        with pytest.raises(HTTPException, match="S3_DEV_BUCKET"):
            check_s3_connection()
        factory.assert_not_called()
