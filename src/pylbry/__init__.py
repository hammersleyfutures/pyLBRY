# ABOUTME: Public API for pyLBRY.
# ABOUTME: Re-exports the errors that callers are expected to catch.
"""Public API for pyLBRY."""

from pylbry.errors import (
    DaemonInternalError,
    DaemonUnavailableError,
    InvalidParamsError,
    MethodNotFoundError,
    OperationFailedError,
    PyLBRYError,
    RPCError,
)

__all__ = [
    "DaemonInternalError",
    "DaemonUnavailableError",
    "InvalidParamsError",
    "MethodNotFoundError",
    "OperationFailedError",
    "PyLBRYError",
    "RPCError",
]
