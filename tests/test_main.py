# Verifies the installed application's entry point.
"""Tests for the starter command."""

from unittest.mock import patch

from yoink_backend.__main__ import main


# Checks that invoking the application starts the configured HTTP server.
def test_main() -> None:
    """Verify the server entry point without blocking the test runner."""
    with patch("yoink_backend.__main__.uvicorn.run") as run:
        main()
    run.assert_called_once_with(
        "yoink_backend.app:app", host="0.0.0.0", port=8000, access_log=False
    )
