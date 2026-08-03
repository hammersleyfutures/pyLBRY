# ABOUTME: Exception hierarchy for pyLBRY.
# ABOUTME: Separates transport, JSON-RPC and in-result daemon failures.
"""Exception hierarchy for pyLBRY."""

from __future__ import annotations


class PyLBRYError(Exception):
    """Base class for every error raised by pyLBRY."""


class DaemonUnavailableError(PyLBRYError):
    """The lbrynet daemon could not be reached."""


class RPCError(PyLBRYError):
    """The daemon returned a JSON-RPC error object."""

    def __init__(self, code: int, message: str) -> None:
        """Record the JSON-RPC code and message.

        Args:
            code: JSON-RPC error code returned by the daemon.
            message: Human-readable message returned by the daemon.
        """
        super().__init__(f"[{code}] {message}")
        self.code = code
        self.message = message


class MethodNotFoundError(RPCError):
    """The daemon does not expose the requested method (-32601)."""


class InvalidParamsError(RPCError):
    """The daemon rejected the parameters for the method (-32602)."""


class DaemonInternalError(RPCError):
    """The daemon failed internally (-32603 or -32500)."""


class OperationFailedError(PyLBRYError):
    """The daemon reported failure inside an otherwise successful result."""

    def __init__(self, method: str, message: str) -> None:
        """Record the failing method and the daemon's raw message.

        Args:
            method: Daemon method that reported the failure.
            message: Raw message text from the daemon.
        """
        super().__init__(f"{method}: {message}")
        self.method = method
        self.message = message
