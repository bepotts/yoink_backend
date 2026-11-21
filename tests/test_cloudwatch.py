# Verifies CloudWatch routing, safe startup configuration, and handler shutdown.
"""CloudWatch configuration tests without network calls."""

import logging
from unittest.mock import MagicMock, patch

import pytest

from yoink_backend.observability.cloudwatch import (
    BackendLogFilter,
    close_cloudwatch_logging,
    configure_cloudwatch_logging,
)


# Requires an explicit region and prevents silent remote logging from test defaults.
def test_configuration_disabled_or_missing_region(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CLOUDWATCH_ENABLED", "false")
    with patch("yoink_backend.observability.cloudwatch.boto3.client") as client:
        configure_cloudwatch_logging(logging.Formatter())
        client.assert_not_called()
    monkeypatch.setenv("CLOUDWATCH_ENABLED", "true")
    monkeypatch.delenv("CLOUDWATCH_REGION", raising=False)
    with pytest.raises(ValueError, match="CLOUDWATCH_REGION"):
        configure_cloudwatch_logging(logging.Formatter())


# Checks group isolation, retention, batch settings, and explicit shutdown flushing.
def test_groups_and_shutdown(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLOUDWATCH_ENABLED", "true")
    monkeypatch.setenv("CLOUDWATCH_REGION", "us-east-1")
    monkeypatch.setenv("CLOUDWATCH_LOG_GROUP_PREFIX", "/test/")
    monkeypatch.setenv("APP_ENV", "production")
    handlers = [MagicMock(spec=logging.Handler), MagicMock(spec=logging.Handler)]
    formatter = logging.Formatter()
    with (
        patch("yoink_backend.observability.cloudwatch.boto3.client") as client,
        patch(
            "yoink_backend.observability.cloudwatch.watchtower.CloudWatchLogHandler",
            side_effect=handlers,
        ) as create,
    ):
        configure_cloudwatch_logging(formatter)
        assert client.call_args.args == ("logs",)
        calls = create.call_args_list
        assert [call.kwargs["log_group_name"] for call in calls] == [
            "/test/production/backend",
            "/test/production/frontend",
        ]
        assert all(call.kwargs["log_group_retention_days"] == 30 for call in calls)
        assert all(call.kwargs["send_interval"] == 5 for call in calls)
        handlers[0].addFilter.assert_called_once()
        handlers[1].addFilter.assert_not_called()
        handlers[0].setFormatter.assert_called_once_with(formatter)
        assert logging.getLogger("yoink.frontend").propagate is False
        close_cloudwatch_logging()
        for handler in handlers:
            handler.close.assert_called_once()
            assert handler not in logging.getLogger().handlers
            assert handler not in logging.getLogger("yoink.frontend").handlers
        close_cloudwatch_logging()


# Prevents AWS delivery diagnostics or desktop relays from looping through backend logs.
@pytest.mark.parametrize(
    "name,expected",
    [
        ("yoink_backend.app", True),
        ("yoink.frontend", False),
        ("botocore.client", False),
        ("boto3", False),
        ("urllib3.connectionpool", False),
        ("watchtower", False),
    ],
)
def test_filter(name: str, expected: bool) -> None:
    record = logging.LogRecord(name, logging.INFO, "", 0, "event", (), None)
    assert BackendLogFilter().filter(record) is expected
