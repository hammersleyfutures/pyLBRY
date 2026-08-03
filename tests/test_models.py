# ABOUTME: Tests for JSON narrowing helpers and record types.
# ABOUTME: Covers both the success and failure path of every helper.
"""Tests for JSON narrowing helpers and record types."""

from __future__ import annotations

import pytest

from pylbry.errors import DaemonInternalError
from pylbry.models import (
    Claim,
    FileRef,
    JSONValue,
    Page,
    ResolveFailure,
    as_bool,
    as_int,
    as_list,
    as_object,
    as_str,
    opt_int,
    opt_str,
)

TWO = 2
THREE = 3
CLAIM_SIZE = 42
CLAIM_HEIGHT = 1000
CLAIM_DURATION = 90
CLAIM_TIMESTAMP = 1600000000
BLOBS = 2


def test_as_object_returns_a_mapping() -> None:
    """as_object passes a JSON object through unchanged."""
    assert as_object({"a": 1}) == {"a": 1}


def test_as_object_rejects_a_non_object() -> None:
    """as_object raises when the value is not a JSON object."""
    with pytest.raises(DaemonInternalError, match="expected object"):
        as_object("nope")


def test_as_list_returns_a_sequence() -> None:
    """as_list passes a JSON array through unchanged."""
    assert as_list([1, 2]) == [1, 2]


def test_as_list_rejects_a_non_list() -> None:
    """as_list raises when the value is not a JSON array."""
    with pytest.raises(DaemonInternalError, match="expected list"):
        as_list({})


def test_as_str_returns_a_string() -> None:
    """as_str passes a string through unchanged."""
    assert as_str("x") == "x"


def test_as_str_rejects_a_non_string() -> None:
    """as_str raises when the value is not a string."""
    with pytest.raises(DaemonInternalError, match="expected str"):
        as_str(1)


def test_as_int_returns_an_integer() -> None:
    """as_int passes an integer through unchanged."""
    assert as_int(THREE) == THREE


def test_as_int_rejects_a_non_integer() -> None:
    """as_int raises when the value is not an integer."""
    with pytest.raises(DaemonInternalError, match="expected int"):
        as_int("3")


def test_as_int_rejects_a_boolean() -> None:
    """as_int rejects booleans, which are a subclass of int in Python."""
    with pytest.raises(DaemonInternalError, match="expected int"):
        as_int(True)


def test_as_bool_returns_a_boolean() -> None:
    """as_bool passes a boolean through unchanged."""
    assert as_bool(True) is True


def test_as_bool_rejects_a_non_boolean() -> None:
    """as_bool raises when the value is not a boolean."""
    with pytest.raises(DaemonInternalError, match="expected bool"):
        as_bool(1)


def test_opt_str_maps_none_to_none() -> None:
    """opt_str returns None for a missing value and passes strings through."""
    assert opt_str(None) is None
    assert opt_str("x") == "x"


def test_opt_str_rejects_a_non_string() -> None:
    """opt_str raises when a present value is not a string."""
    with pytest.raises(DaemonInternalError, match="expected str"):
        opt_str(1)


def test_opt_int_maps_none_to_none() -> None:
    """opt_int returns None for a missing value and passes integers through."""
    assert opt_int(None) is None
    assert opt_int(TWO) == TWO


def test_opt_int_rejects_a_non_integer() -> None:
    """opt_int raises when a present value is not an integer."""
    with pytest.raises(DaemonInternalError, match="expected int"):
        opt_int("2")


def test_claim_parses_a_stream_claim() -> None:
    """Claim.from_dict reads identity, channel and stream fields."""
    data: dict[str, JSONValue] = {
        "claim_id": "abc123",
        "name": "a-video",
        "canonical_url": "lbry://@chan#a/a-video#b",
        "permanent_url": "lbry://a-video#abc123",
        "value_type": "stream",
        "height": CLAIM_HEIGHT,
        "timestamp": CLAIM_TIMESTAMP,
        "signing_channel": {"claim_id": "chan1", "name": "@chan"},
        "value": {
            "title": "A Video",
            "description": "Words",
            "source": {
                "sd_hash": "deadbeef",
                "media_type": "video/mp4",
                "size": "42",
            },
            "video": {"duration": CLAIM_DURATION},
        },
    }
    claim = Claim.from_dict(data)
    assert claim.claim_id == "abc123"
    assert claim.channel_id == "chan1"
    assert claim.channel_name == "@chan"
    assert claim.sd_hash == "deadbeef"
    assert claim.media_type == "video/mp4"
    assert claim.size == CLAIM_SIZE
    assert claim.duration == CLAIM_DURATION
    assert claim.raw == data


def test_claim_parses_a_claim_without_a_source_or_channel() -> None:
    """Claim.from_dict tolerates absent channel, source and video sections."""
    data: dict[str, JSONValue] = {
        "claim_id": "x",
        "name": "n",
        "canonical_url": "lbry://n",
        "permanent_url": "lbry://n#x",
        "value_type": "channel",
        "height": 1,
        "value": {},
    }
    claim = Claim.from_dict(data)
    assert claim.channel_id is None
    assert claim.sd_hash is None
    assert claim.size is None
    assert claim.duration is None
    assert claim.timestamp is None


def test_file_ref_parses_a_file_entry() -> None:
    """FileRef.from_dict reads progress and completion fields."""
    data: dict[str, JSONValue] = {
        "claim_id": "abc123",
        "sd_hash": "deadbeef",
        "file_name": "a-video.mp4",
        "download_path": "/tmp/a-video.mp4",
        "status": "finished",
        "completed": True,
        "written_bytes": CLAIM_SIZE,
        "total_bytes": CLAIM_SIZE,
        "blobs_completed": BLOBS,
        "blobs_in_stream": BLOBS,
    }
    file_ref = FileRef.from_dict(data)
    assert file_ref.completed is True
    assert file_ref.written_bytes == CLAIM_SIZE
    assert file_ref.blobs_in_stream == BLOBS


def test_page_holds_items_and_pagination() -> None:
    """A Page carries its items alongside pagination metadata."""
    page: Page[str] = Page(items=["a"], page=1, page_size=20, total_pages=None)
    assert page.items == ["a"]
    assert page.total_pages is None


def test_resolve_failure_records_the_url_and_message() -> None:
    """A ResolveFailure records which URL failed and why."""
    failure = ResolveFailure(url="lbry://missing", message="Could not find claim")
    assert failure.url == "lbry://missing"
    assert failure.message == "Could not find claim"
