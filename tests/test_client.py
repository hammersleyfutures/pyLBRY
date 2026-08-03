# ABOUTME: Tests for the JSON-RPC transport against a live lbrynet daemon.
# ABOUTME: Error branches are provoked by misusing the real daemon.
"""Tests for the JSON-RPC transport against a live lbrynet daemon."""

import pytest

from pylbry.client import Client
from pylbry.errors import (
    DaemonUnavailableError,
    InvalidParamsError,
    MethodNotFoundError,
)
from pylbry.models import as_object

pytestmark = pytest.mark.live

METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602


def test_status_returns_a_running_daemon(client: Client) -> None:
    """A status call returns an object reporting the daemon is running."""
    result = as_object(client.call("status"))
    assert result["is_running"] is True


def test_unreachable_daemon_raises() -> None:
    """Pointing the client at a closed port raises DaemonUnavailableError."""
    with (
        Client("http://127.0.0.1:1") as dead,
        pytest.raises(DaemonUnavailableError, match="cannot reach"),
    ):
        dead.call("status")


def test_unknown_method_raises_method_not_found(client: Client) -> None:
    """Calling a method the daemon does not expose raises MethodNotFoundError."""
    with pytest.raises(MethodNotFoundError) as caught:
        client.call("no_such_method_exists")
    assert caught.value.code == METHOD_NOT_FOUND


def test_bad_params_raise_invalid_params(client: Client) -> None:
    """Calling resolve with an unknown parameter raises InvalidParamsError."""
    with pytest.raises(InvalidParamsError) as caught:
        client.call("resolve", {"not_a_real_parameter": "x"})
    assert caught.value.code == INVALID_PARAMS
