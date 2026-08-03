# ABOUTME: Tests for the two-phase archiver against a live lbrynet daemon.
# ABOUTME: Downloads mutate daemon state, so the module is pinned to a worker.
"""Tests for the two-phase archiver against a live lbrynet daemon."""

from pathlib import Path

import pytest

from pylbry.archive.archiver import ArchiveEvent, Archiver, safe_name
from pylbry.archive.store import DownloadState
from pylbry.client import Client
from pylbry.models import Claim

pytestmark = [pytest.mark.live, pytest.mark.xdist_group("daemon_state")]


def test_safe_name_replaces_unsafe_runs() -> None:
    """Characters unsuitable for a path collapse into underscores."""
    assert safe_name("a b/c:d") == "a_b_c_d"


def test_safe_name_falls_back_when_nothing_survives() -> None:
    """A name made entirely of unsafe characters becomes a placeholder."""
    assert safe_name("///") == "unnamed"


def test_index_channel_records_claims_without_downloading(
    client: Client, channel: Claim, tmp_path: Path
) -> None:
    """The index phase persists claims and queues them as pending."""
    with Archiver(client, tmp_path) as archiver:
        indexed = archiver.index_channel(channel.claim_id)
        assert indexed > 0
        assert archiver.store.claim_count() == indexed
        assert archiver.counts()[DownloadState.PENDING] == indexed
        assert not (tmp_path / "media").exists()


def test_fetch_pending_downloads_and_records_outcome(
    client: Client, smallest_claim: Claim, tmp_path: Path
) -> None:
    """The fetch phase attempts queued claims and records the result."""
    with Archiver(client, tmp_path, workers=2) as archiver:
        archiver.store.upsert_claim(smallest_claim)
        tally = archiver.fetch_pending()
        assert sum(tally.values()) == 1
        assert archiver.store.state_of(smallest_claim.claim_id) in {
            DownloadState.COMPLETE,
            DownloadState.RUNNING,
            DownloadState.UNAVAILABLE,
            DownloadState.FAILED,
        }


def test_fetch_pending_respects_a_limit(
    client: Client, channel: Claim, tmp_path: Path
) -> None:
    """A limit caps how many queued claims are attempted."""
    with Archiver(client, tmp_path, workers=2) as archiver:
        page = client.claims.search(
            channel_ids=[channel.claim_id], has_source=True, page_size=3
        )
        for claim in page.items:
            archiver.store.upsert_claim(claim)
        tally = archiver.fetch_pending(limit=1)
        assert sum(tally.values()) == 1


def test_events_are_emitted_not_printed(
    client: Client,
    smallest_claim: Claim,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The archiver reports progress through the callback and prints nothing."""
    events: list[ArchiveEvent] = []
    with Archiver(client, tmp_path, on_event=events.append) as archiver:
        archiver.store.upsert_claim(smallest_claim)
        archiver.fetch_pending()
    assert events
    assert not capsys.readouterr().out


def test_reconcile_marks_daemon_completed_downloads(
    client: Client, completed_claim: Claim, tmp_path: Path
) -> None:
    """Claims the daemon already finished are marked complete, not refetched."""
    with Archiver(client, tmp_path) as archiver:
        archiver.store.upsert_claim(completed_claim)
        assert archiver.store.state_of(completed_claim.claim_id) is (
            DownloadState.PENDING
        )
        marked = archiver.reconcile(page_size=1)
        assert marked >= 1
        assert archiver.store.state_of(completed_claim.claim_id) is (
            DownloadState.COMPLETE
        )


def test_resume_clears_stale_running_rows(
    client: Client, completed_claim: Claim, tmp_path: Path
) -> None:
    """Resume reconciles first, so a stale running row does not stay running."""
    with Archiver(client, tmp_path) as archiver:
        archiver.store.upsert_claim(completed_claim)
        archiver.store.set_state(completed_claim.claim_id, DownloadState.RUNNING)
        archiver.resume()
        assert archiver.store.state_of(completed_claim.claim_id) is (
            DownloadState.COMPLETE
        )


def test_fetch_of_an_unknown_claim_raises(client: Client, tmp_path: Path) -> None:
    """Fetching a claim the store never indexed is a programming error."""
    with Archiver(client, tmp_path) as archiver, pytest.raises(KeyError):
        archiver.store.target_of("0" * 40)


def unresolvable_claim(claim_id: str, url: str) -> Claim:
    """Build a claim record whose URL the daemon cannot resolve.

    The record is real and so is the daemon's failure to resolve it; only the
    URL is chosen to be absent from the network.

    Args:
        claim_id: Identifier to give the claim.
        url: A permanent URL that does not resolve.

    Returns:
        A claim the archiver will fail to download.
    """
    return Claim(
        claim_id=claim_id,
        name="missing",
        canonical_url=url,
        permanent_url=url,
        claim_type="stream",
        title=None,
        description=None,
        channel_id=None,
        channel_name=None,
        height=1,
        timestamp=None,
        sd_hash="sd",
        media_type="video/mp4",
        size=1,
        duration=None,
        raw={},
    )


def test_fetch_records_an_unresolvable_claim_as_unavailable(
    client: Client, tmp_path: Path
) -> None:
    """A claim the daemon cannot fetch is recorded as unavailable, not failed."""
    claim = unresolvable_claim("a" * 40, "lbry://pylbry-does-not-exist-9f3a2b")
    with Archiver(client, tmp_path) as archiver:
        archiver.store.upsert_claim(claim)
        tally = archiver.fetch_pending()
        assert tally == {DownloadState.UNAVAILABLE: 1}
        assert archiver.store.state_of(claim.claim_id) is DownloadState.UNAVAILABLE


def test_fetch_records_a_transport_failure_as_failed(tmp_path: Path) -> None:
    """A daemon that cannot be reached marks the claim failed, so it retries."""
    claim = unresolvable_claim("b" * 40, "lbry://anything")
    with (
        Client("http://127.0.0.1:1") as dead,
        Archiver(dead, tmp_path) as archiver,
    ):
        archiver.store.upsert_claim(claim)
        tally = archiver.fetch_pending()
        assert tally == {DownloadState.FAILED: 1}
        assert archiver.store.state_of(claim.claim_id) is DownloadState.FAILED


def test_reconcile_leaves_already_complete_claims_alone(
    client: Client, completed_claim: Claim, tmp_path: Path
) -> None:
    """A claim already recorded complete is not counted again."""
    with Archiver(client, tmp_path) as archiver:
        archiver.store.upsert_claim(completed_claim)
        archiver.store.set_state(completed_claim.claim_id, DownloadState.COMPLETE)
        assert archiver.reconcile(page_size=1) == 0
