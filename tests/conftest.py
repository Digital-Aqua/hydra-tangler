""" Pytest hooks for the tangler tests.

Registers the ``slow`` marker without editing ``pyproject.toml``.
"""

import pytest


def pytest_configure(config: pytest.Config) -> None:
    """ Register markers used by the suite. """
    config.addinivalue_line("markers", "slow: runs a real checker subprocess")
