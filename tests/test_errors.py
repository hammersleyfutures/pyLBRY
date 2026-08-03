# ABOUTME: Tests for the pyLBRY exception hierarchy.
# ABOUTME: Verifies codes, messages and subclass relationships.
"""Tests for the pyLBRY exception hierarchy."""

from pylbry.errors import (
    DaemonInternalError,
    DaemonUnavailableError,
    InvalidParamsError,
    MethodNotFoundError,
    OperationFailedError,
    PyLBRYError,
    RPCError,
)

METHOD_NOT_FOUND = -32601


def test_rpc_error_carries_code_and_message() -> None:
    """An RPCError exposes the daemon's code and message."""
    error = RPCError(METHOD_NOT_FOUND, "Method Not Found")
    assert error.code == METHOD_NOT_FOUND
    assert error.message == "Method Not Found"
    assert str(error) == "[-32601] Method Not Found"


def test_rpc_subclasses_inherit_from_rpc_error() -> None:
    """Every mapped code class is an RPCError and a PyLBRYError."""
    for subclass in (MethodNotFoundError, InvalidParamsError, DaemonInternalError):
        assert issubclass(subclass, RPCError)
    assert issubclass(RPCError, PyLBRYError)
    assert issubclass(DaemonUnavailableError, PyLBRYError)


def test_operation_failed_error_names_the_method() -> None:
    """An OperationFailedError records which method reported the failure."""
    error = OperationFailedError("get", "Failed to resolve stream")
    assert error.method == "get"
    assert error.message == "Failed to resolve stream"
    assert str(error) == "get: Failed to resolve stream"
