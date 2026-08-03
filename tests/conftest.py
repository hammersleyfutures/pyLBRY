# ABOUTME: Shared pytest fixtures for pyLBRY tests.
# ABOUTME: Provides a live daemon client and a discovered, resolvable claim.
"""Shared pytest fixtures for pyLBRY tests."""

import os
from collections.abc import Iterator

import pytest

from pylbry.client import Client

DAEMON_URL = os.environ.get("PYLBRY_TEST_DAEMON", "http://localhost:5279")


@pytest.fixture(scope="session")
def client() -> Iterator[Client]:
    """Yield a client bound to the live daemon.

    Yields:
        A client connected to the daemon under test.
    """
    with Client(DAEMON_URL) as live_client:
        live_client.call("status")
        yield live_client
