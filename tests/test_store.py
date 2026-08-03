# ABOUTME: Tests for the SQLite archive store.
# ABOUTME: Uses a real database in a temp directory; no daemon required.
"""Tests for the SQLite archive store."""

from __future__ import annotations

from pathlib import Path

from pylbry.archive.store import DownloadState, Store
from pylbry.models import Claim

CLAIM_SIZE = 10


def make_claim(claim_id: str) -> Claim:
    """Build a minimal claim for store tests.

    Args:
        claim_id: Identifier to give the claim.

    Returns:
        A claim carrying only the fields the store persists.
    """
    return Claim(
        claim_id=claim_id,
        name="n",
        canonical_url=f"lbry://n#{claim_id}",
        permanent_url=f"lbry://n#{claim_id}",
        claim_type="stream",
        title="T",
        description=None,
        channel_id="chan",
        channel_name="@chan",
        height=1,
        timestamp=None,
        sd_hash="sd",
        media_type="image/png",
        size=CLAIM_SIZE,
        duration=None,
        raw={"claim_id": claim_id},
    )


def test_upsert_claim_inserts_once(tmp_path: Path) -> None:
    """Upserting the same claim twice stores a single row."""
    with Store(tmp_path / "a.db") as store:
        store.upsert_claim(make_claim("a"))
        store.upsert_claim(make_claim("a"))
        assert store.claim_count() == 1
        assert store.state_of("a") is DownloadState.PENDING


def test_pending_returns_claims_awaiting_download(tmp_path: Path) -> None:
    """Pending selects claims that are not yet complete."""
    with Store(tmp_path / "a.db") as store:
        store.upsert_claim(make_claim("a"))
        store.upsert_claim(make_claim("b"))
        store.set_state("b", DownloadState.COMPLETE, path="/tmp/b.png")
        assert store.pending(limit=10, max_attempts=3) == ["a"]


def test_pending_respects_the_attempt_ceiling(tmp_path: Path) -> None:
    """A claim that has exhausted its attempts is no longer pending."""
    with Store(tmp_path / "a.db") as store:
        store.upsert_claim(make_claim("a"))
        store.set_state("a", DownloadState.FAILED, error="boom")
        store.bump_attempts("a")
        assert store.pending(limit=10, max_attempts=1) == []


def test_unavailable_claims_are_not_retried(tmp_path: Path) -> None:
    """Unavailable means nothing is seeding it, so it is never re-queued."""
    with Store(tmp_path / "a.db") as store:
        store.upsert_claim(make_claim("a"))
        store.set_state("a", DownloadState.UNAVAILABLE, error="no peers")
        assert store.pending(limit=10, max_attempts=99) == []


def test_reset_running_requeues_stale_rows(tmp_path: Path) -> None:
    """Rows left running by a crashed process return to pending."""
    with Store(tmp_path / "a.db") as store:
        store.upsert_claim(make_claim("a"))
        store.set_state("a", DownloadState.RUNNING)
        assert store.reset_running() == 1
        assert store.state_of("a") is DownloadState.PENDING


def test_counts_reports_each_state(tmp_path: Path) -> None:
    """Counts groups rows by download state."""
    with Store(tmp_path / "a.db") as store:
        store.upsert_claim(make_claim("a"))
        store.upsert_claim(make_claim("b"))
        store.set_state("b", DownloadState.COMPLETE, path="/tmp/b.png")
        assert store.counts() == {
            DownloadState.PENDING: 1,
            DownloadState.COMPLETE: 1,
        }


def test_state_of_returns_none_for_an_unknown_claim(tmp_path: Path) -> None:
    """Asking about a claim the store has never seen returns None."""
    with Store(tmp_path / "a.db") as store:
        assert store.state_of("missing") is None


def test_set_state_preserves_a_recorded_path(tmp_path: Path) -> None:
    """A later state change without a path keeps the path already recorded."""
    with Store(tmp_path / "a.db") as store:
        store.upsert_claim(make_claim("a"))
        store.set_state("a", DownloadState.COMPLETE, path="/tmp/a.png")
        store.set_state("a", DownloadState.RUNNING)
        assert store.path_of("a") == "/tmp/a.png"


def test_store_creates_missing_parent_directories(tmp_path: Path) -> None:
    """Opening a store creates the directory tree it lives in."""
    store = Store(tmp_path / "nested" / "deeper" / "a.db")
    store.close()
    assert (tmp_path / "nested" / "deeper" / "a.db").exists()


def test_path_of_returns_none_for_an_unknown_claim(tmp_path: Path) -> None:
    """Asking for the path of a claim the store never saw returns None."""
    with Store(tmp_path / "a.db") as store:
        assert store.path_of("missing") is None


def test_path_of_returns_none_before_a_download_lands(tmp_path: Path) -> None:
    """A queued claim has no recorded path until its media is written."""
    with Store(tmp_path / "a.db") as store:
        store.upsert_claim(make_claim("a"))
        assert store.path_of("a") is None
