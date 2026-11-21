# Verifies monitoring stays optional and uses deployment-specific settings.
"""Tests for Sentry initialization without sending telemetry."""

from unittest.mock import patch

import pytest

from yoink_backend.observability.monitoring import configure_sentry


# Prevents unconfigured checkouts from emitting telemetry.
def test_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    with patch("yoink_backend.observability.monitoring.sentry_sdk.init") as initialize:
        configure_sentry()
    initialize.assert_not_called()


# Checks trace rates, release selection, and restrictions on captured data.
@pytest.mark.parametrize(
    "environment,rate", [("development", 1.0), ("production", 0.1)]
)
@pytest.mark.parametrize("release", ["", "backend@commit123"])
def test_configuration(
    monkeypatch: pytest.MonkeyPatch, environment: str, rate: float, release: str
) -> None:
    monkeypatch.setenv("SENTRY_DSN", "https://public@example.com/1")
    monkeypatch.setenv("APP_ENV", environment)
    monkeypatch.setenv("SENTRY_RELEASE", release)
    with patch("yoink_backend.observability.monitoring.sentry_sdk.init") as initialize:
        configure_sentry()
    options = initialize.call_args.kwargs
    assert options["environment"] == environment
    assert options["traces_sample_rate"] == rate
    assert options["release"] == (release or "yoink-backend@0.1.0")
    assert options["enable_logs"] is False
    assert options["data_collection"] == {"user_info": False, "http_bodies": []}
    assert options["include_local_variables"] is False
    assert options["max_request_body_size"] == "never"
