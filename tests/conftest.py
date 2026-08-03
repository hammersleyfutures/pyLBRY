# ABOUTME: Shared pytest fixtures for pyLBRY tests.
# ABOUTME: Provides a live daemon client and a pinned, seeded test channel.
"""Shared pytest fixtures for pyLBRY tests."""

import os
import time
from collections.abc import Iterator

import pytest

from pylbry.client import Client
from pylbry.models import Claim

# A real 14 MB transfer takes minutes on this network, so the completed-download
# fixture is session scoped and polled rather than repeated per test.
COMPLETION_TIMEOUT = 600.0
POLL_INTERVAL = 5.0

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
    """Pick the claim tests download, preferring one already on disk.

    Downloads here are real and each stream is tens of megabytes, so a claim
    the daemon already holds is reused before any new transfer is started.
    Only when the daemon holds nothing from the channel is the smallest stream
    fetched fresh.

    Args:
        client: Client connected to the daemon under test.
        channel: The pinned test channel.

    Returns:
        A claim from the pinned channel, already downloaded when possible.
    """
    held = client.files.query(page_size=1, completed=True).items
    if held:
        found = client.claims.search(claim_id=held[0].claim_id, page_size=1)
        if found.items and found.items[0].channel_id == channel.claim_id:
            return found.items[0]

    page = client.claims.search(
        channel_ids=[channel.claim_id],
        has_source=True,
        page_size=30,
        order_by="height",
        no_totals=True,
    )
    candidates = [claim for claim in page.items if claim.size is not None]
    return min(candidates, key=lambda claim: claim.size or 0)


@pytest.fixture(scope="session")
def completed_claim(client: Client, smallest_claim: Claim) -> Claim:
    """Ensure the daemon holds one fully downloaded claim.

    Reconciliation needs a completed download to find. The daemon returns from
    a get once the first blob lands, so completion is polled for.

    Args:
        client: Client connected to the daemon under test.
        smallest_claim: The smallest claim in the pinned channel.

    Returns:
        A claim the daemon has downloaded in full.

    Raises:
        AssertionError: If the download does not complete in time.
    """
    already = client.files.query(completed=True, page_size=1).items
    if already:
        found = client.claims.search(claim_id=already[0].claim_id, page_size=1)
        return found.items[0]

    client.files.download(smallest_claim.permanent_url)
    deadline = time.monotonic() + COMPLETION_TIMEOUT
    while time.monotonic() < deadline:
        page = client.files.query(claim_id=smallest_claim.claim_id)
        if page.items and page.items[0].completed:
            return smallest_claim
        time.sleep(POLL_INTERVAL)
    msg = f"{smallest_claim.claim_id} did not finish downloading in time"
    raise AssertionError(msg)
