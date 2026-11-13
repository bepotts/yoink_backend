# Verifies the installed application's entry point.
"""Tests for the starter command."""

import pytest

from yoink_backend.__main__ import main


# Checks that the starter command reports readiness without errors.
def test_main(capsys: pytest.CaptureFixture[str]) -> None:
    """Verify the entry point's output."""
    main()
    captured = capsys.readouterr()
    assert captured.out == "Yoink backend is ready.\n"
    assert captured.err == ""
