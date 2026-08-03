# ABOUTME: Tests for the claims namespace against a live lbrynet daemon.
# ABOUTME: Covers single resolve, batch resolve, search and channel iteration.
"""Tests for the claims namespace against a live lbrynet daemon."""

from __future__ import annotations

import pytest

from pylbry.client import Client
from pylbry.errors import OperationFailedError
from pylbry.models import Claim, ResolveFailure

pytestmark = pytest.mark.live

JUNK_URL = "lbry://pylbry-does-not-exist-9f3a2b"
PAGE_SIZE = 2


def test_search_returns_a_page_of_claims(client: Client) -> None:
    """A search returns claims and echoes the requested page size."""
    page = client.claims.search(page_size=PAGE_SIZE, has_source=True)
    assert page.page_size == PAGE_SIZE
    assert len(page.items) <= PAGE_SIZE
    assert all(isinstance(item, Claim) for item in page.items)


def test_resolve_returns_a_claim(client: Client) -> None:
    """Resolving a URL discovered from search returns that claim."""
    discovered = client.claims.search(page_size=1, has_source=True).items[0]
    claim = client.claims.resolve(discovered.canonical_url)
    assert claim.claim_id == discovered.claim_id


def test_resolve_raises_for_an_unknown_url(client: Client) -> None:
    """Resolving a URL with no claim raises OperationFailedError."""
    with pytest.raises(OperationFailedError):
        client.claims.resolve(JUNK_URL)


def test_resolve_many_records_failures_as_data(client: Client) -> None:
    """A batch resolve returns claims and failures side by side."""
    discovered = client.claims.search(page_size=1, has_source=True).items[0]
    results = client.claims.resolve_many([discovered.canonical_url, JUNK_URL])
    assert isinstance(results[discovered.canonical_url], Claim)
    assert isinstance(results[JUNK_URL], ResolveFailure)


def test_iter_channel_yields_unique_claims(client: Client) -> None:
    """Channel iteration pages transparently and stops when exhausted."""
    seed = next(
        claim
        for claim in client.claims.search(page_size=20, has_source=True).items
        if claim.channel_id is not None
    )
    assert seed.channel_id is not None
    claims = list(client.claims.iter_channel(seed.channel_id, page_size=PAGE_SIZE))
    assert claims
    assert len({claim.claim_id for claim in claims}) == len(claims)
