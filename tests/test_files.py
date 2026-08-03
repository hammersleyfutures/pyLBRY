# ABOUTME: Tests for the files namespace against a live lbrynet daemon.
# ABOUTME: Downloads mutate daemon state, so they are pinned to one worker.
"""Tests for the files namespace against a live lbrynet daemon."""

from pathlib import Path

import pytest

from pylbry.client import Client
from pylbry.errors import OperationFailedError
from pylbry.models import Claim

pytestmark = [pytest.mark.live, pytest.mark.xdist_group("daemon_state")]

PAGE_SIZE = 5


def test_query_returns_a_page_of_files(client: Client) -> None:
    """Listing files returns a page, empty or otherwise."""
    page = client.files.query(page_size=PAGE_SIZE)
    assert page.page_size == PAGE_SIZE
    assert len(page.items) <= PAGE_SIZE


def test_download_of_a_junk_uri_raises_operation_failed(client: Client) -> None:
    """A get that fails reports through the in-result error channel."""
    with pytest.raises(OperationFailedError) as caught:
        client.files.download("lbry://pylbry-does-not-exist-9f3a2b")
    assert caught.value.method == "get"


def test_download_writes_a_real_file(
    client: Client, smallest_claim: Claim, tmp_path: Path
) -> None:
    """Downloading a seeded claim writes a real file and returns its path.

    The path is asserted to exist rather than to sit under tmp_path: if the
    daemon already holds the stream it returns the existing file where it
    already lives and ignores the requested directory.
    """
    file_ref = client.files.download(
        smallest_claim.permanent_url, download_directory=str(tmp_path)
    )
    assert file_ref.claim_id == smallest_claim.claim_id
    assert file_ref.download_path is not None
    assert Path(file_ref.download_path).exists()
    assert file_ref.blobs_in_stream > 0


def test_query_finds_the_downloaded_claim(
    client: Client, smallest_claim: Claim, tmp_path: Path
) -> None:
    """A downloaded claim becomes visible through the file listing."""
    client.files.download(
        smallest_claim.permanent_url, download_directory=str(tmp_path)
    )
    page = client.files.query(claim_id=smallest_claim.claim_id)
    assert [item.claim_id for item in page.items] == [smallest_claim.claim_id]
    assert page.items[0].blobs_in_stream > 0


def test_download_accepts_a_file_name_and_timeout(
    client: Client, smallest_claim: Claim, tmp_path: Path
) -> None:
    """The optional file name and daemon timeout are passed through."""
    file_ref = client.files.download(
        smallest_claim.permanent_url,
        download_directory=str(tmp_path),
        file_name="pylbry-named.mp4",
        timeout=120.0,
    )
    assert file_ref.claim_id == smallest_claim.claim_id
    assert file_ref.file_name is not None


def test_query_filters_on_completion(client: Client) -> None:
    """The completed filter restricts the listing to finished downloads."""
    page = client.files.query(completed=True, page_size=PAGE_SIZE)
    assert all(item.completed for item in page.items)
