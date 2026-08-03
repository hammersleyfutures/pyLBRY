# ABOUTME: Shared pytest fixtures for pyLBRY tests.
# ABOUTME: Provides a live daemon client and a pinned, seeded test channel.
"""Shared pytest fixtures for pyLBRY tests."""

import os
from collections.abc import Iterator

import pytest

from pylbry.client import Client
from pylbry.models import Claim

DAEMON_URL = os.environ.get("PYLBRY_TEST_DAEMON", "http://localhost:5279")

# Tests draw from one pinned channel rather than arbitrary network content, so
# runs are predictable and the media is known to be seeded.
TEST_CHANNEL_URL = os.environ.get("PYLBRY_TEST_CHANNEL", "lbry://@KissAnalog:d")


@pytest.fixture(scope="session")
def client() -> Iterator[Client]:
    """Yield a client bound to the live daemon.

    Yields:
        A client connected to the daemon under test.
    """
    with Client(DAEMON_URL) as live_client:
        live_client.call("status")
        yield live_client


@pytest.fixture(scope="session")
def channel(client: Client) -> Claim:
    """Resolve the pinned test channel.

    Args:
        client: Client connected to the daemon under test.

    Returns:
        The channel claim tests draw their content from.
    """
    return client.claims.resolve(TEST_CHANNEL_URL)


@pytest.fixture(scope="session")
def smallest_claim(client: Client, channel: Claim) -> Claim:
    """Find the smallest downloadable claim in the pinned channel.

    Downloads in tests are real, so the smallest stream keeps them affordable.

    Args:
        client: Client connected to the daemon under test.
        channel: The pinned test channel.

    Returns:
        The claim with the smallest source size.
    """
    page = client.claims.search(
        channel_ids=[channel.claim_id],
        has_source=True,
        page_size=30,
        order_by="height",
        no_totals=True,
    )
    candidates = [claim for claim in page.items if claim.size is not None]
    return min(candidates, key=lambda claim: claim.size or 0)
