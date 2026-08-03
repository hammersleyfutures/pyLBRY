# ABOUTME: Tests for the retry policy that guards idempotent daemon reads.
# ABOUTME: Real exception objects, no daemon and no mocks.
"""Tests for the retry policy that guards idempotent daemon reads."""

from __future__ import annotations

from pylbry.client import (
    BASE_DELAY,
    MAX_ATTEMPTS,
    MAX_DELAY,
    backoff_delay,
    should_retry,
)
from pylbry.errors import (
    DaemonInternalError,
    DaemonUnavailableError,
    MethodNotFoundError,
)

UNREACHABLE = DaemonUnavailableError("cannot reach lbrynet")
INTERNAL = DaemonInternalError(-32603, "internal error")
NOT_FOUND = MethodNotFoundError(-32601, "method not found")


def test_an_unreachable_daemon_is_retried_for_a_read() -> None:
    """A transport failure on an idempotent read is worth another attempt."""
    assert should_retry("resolve", 1, MAX_ATTEMPTS, UNREACHABLE) is True


def test_an_internal_daemon_failure_is_retried_for_a_read() -> None:
    """A 5xx from the daemon on an idempotent read is worth another attempt."""
    assert should_retry("claim_search", 1, MAX_ATTEMPTS, INTERNAL) is True


def test_a_download_is_never_retried() -> None:
    """A get is left to the archiver, which owns dead-stream policy."""
    assert should_retry("get", 1, MAX_ATTEMPTS, UNREACHABLE) is False


def test_the_final_attempt_is_not_retried() -> None:
    """Retries are bounded, so the last attempt raises instead of looping."""
    assert should_retry("file_list", MAX_ATTEMPTS, MAX_ATTEMPTS, UNREACHABLE) is False


def test_a_rejected_request_is_not_retried() -> None:
    """A daemon that answered and refused the request will refuse it again."""
    assert should_retry("resolve", 1, MAX_ATTEMPTS, NOT_FOUND) is False


def test_backoff_grows_with_each_attempt() -> None:
    """Each attempt waits longer than the one before it."""
    assert backoff_delay(1) == BASE_DELAY
    assert backoff_delay(2) == BASE_DELAY * 2
    assert backoff_delay(3) == BASE_DELAY * 4


def test_backoff_stops_growing_at_the_ceiling() -> None:
    """Backoff is capped so a long retry budget cannot stall a caller."""
    assert backoff_delay(50) == MAX_DELAY
