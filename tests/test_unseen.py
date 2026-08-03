# ABOUTME: Tests for the paged-search deduplication helper.
# ABOUTME: Real Claim objects, no daemon and no mocks.
"""Tests for the paged-search deduplication helper."""

from __future__ import annotations

from pylbry.api.claims import unseen
from pylbry.models import Claim


def make_claim(claim_id: str) -> Claim:
    """Build a minimal claim carrying only an identifier.

    Args:
        claim_id: Identifier to give the claim.

    Returns:
        A claim suitable for identity comparisons.
    """
    return Claim(
        claim_id=claim_id,
        name="n",
        canonical_url=f"lbry://n#{claim_id}",
        permanent_url=f"lbry://n#{claim_id}",
        claim_type="stream",
        title=None,
        description=None,
        channel_id=None,
        channel_name=None,
        height=1,
        timestamp=None,
        sd_hash=None,
        media_type=None,
        size=None,
        duration=None,
        raw={},
    )


def test_unseen_yields_every_new_claim() -> None:
    """Claims not seen before are yielded and recorded."""
    seen: set[str] = set()
    result = list(unseen([make_claim("a"), make_claim("b")], seen))
    assert [claim.claim_id for claim in result] == ["a", "b"]
    assert seen == {"a", "b"}


def test_unseen_skips_a_claim_already_yielded() -> None:
    """A claim repeated across pages is yielded only once."""
    seen: set[str] = set()
    first = list(unseen([make_claim("a")], seen))
    second = list(unseen([make_claim("a"), make_claim("b")], seen))
    assert [claim.claim_id for claim in first] == ["a"]
    assert [claim.claim_id for claim in second] == ["b"]
    assert seen == {"a", "b"}
