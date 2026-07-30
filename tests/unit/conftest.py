"""
tests/conftest.py
"""

import json

import pytest

# ================================================= #
# Logging Fixtures                                  #
# ================================================= #


@pytest.fixture
def logger():
    """Provide a test logger."""
    from symworx_elibrary.utils.logging import eLibLogger

    return eLibLogger(name="test", level="DEBUG")


@pytest.fixture
def capture_logs(monkeypatch):
    """Capture log output for assertions."""
    logs = []

    def mock_print(msg, **kwargs):
        logs.append(json.loads(msg))

    monkeypatch.setattr("builtins.print", mock_print)
    return logs


@pytest.fixture(autouse=True)
def reset_logger():
    """Reset global logger instance between tests."""
    import symworx_elibrary.utils.logging as logging_module

    logging_module._logger_instance = None
    yield
    logging_module._logger_instance = None
