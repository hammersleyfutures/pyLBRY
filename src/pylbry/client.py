# ABOUTME: JSON-RPC transport for the lbrynet daemon.
# ABOUTME: Owns the endpoint, pooled session, timeouts and error unwrapping.
"""JSON-RPC transport for the lbrynet daemon."""

from types import TracebackType
from typing import Self

import httpx

from pylbry.errors import (
    DaemonInternalError,
    DaemonUnavailableError,
    InvalidParamsError,
    MethodNotFoundError,
    RPCError,
)
from pylbry.models import JSONValue, as_int, as_object, as_str

DEFAULT_ENDPOINT = "http://localhost:5279"
DEFAULT_TIMEOUT = 10.0
DEFAULT_DOWNLOAD_TIMEOUT = 60.0

_ERROR_CLASSES: dict[int, type[RPCError]] = {
    -32601: MethodNotFoundError,
    -32602: InvalidParamsError,
    -32603: DaemonInternalError,
    -32500: DaemonInternalError,
}


class Client:
    """A synchronous JSON-RPC client for a local lbrynet daemon."""

    def __init__(
        self,
        endpoint: str = DEFAULT_ENDPOINT,
        *,
        timeout: float = DEFAULT_TIMEOUT,
        download_timeout: float = DEFAULT_DOWNLOAD_TIMEOUT,
    ) -> None:
        """Open a pooled session against the daemon.

        Args:
            endpoint: Base URL of the lbrynet daemon.
            timeout: Read timeout in seconds for ordinary calls.
            download_timeout: Read timeout in seconds for download calls. Must
                exceed the daemon's own download_timeout, or we abandon a
                request the daemon is still serving.
        """
        self.endpoint = endpoint
        self.download_timeout = download_timeout
        self._http = httpx.Client(base_url=endpoint, timeout=timeout)

    def call(
        self,
        method: str,
        params: dict[str, JSONValue] | None = None,
        *,
        timeout: float | None = None,
    ) -> JSONValue:
        """Invoke a daemon method and return its result.

        Args:
            method: Daemon method name.
            params: Parameters for the method.
            timeout: Read timeout override in seconds.

        Returns:
            The decoded ``result`` value from the daemon.

        Raises:
            DaemonUnavailableError: If the daemon cannot be reached.
            RPCError: If the daemon returns a JSON-RPC error object. The
                concrete class is chosen from the code, so the raise below is
                dynamic and DOC502 cannot see it.
        """  # ruff: ignore[docstring-extraneous-exception]
        payload: dict[str, JSONValue] = {"method": method, "params": params or {}}
        try:
            response = self._http.post("/", json=payload, timeout=timeout)
        except httpx.HTTPError as exc:
            message = f"cannot reach lbrynet at {self.endpoint}: {exc}"
            raise DaemonUnavailableError(message) from exc
        body = as_object(response.json())
        error = body.get("error")
        if error is not None:
            failure = as_object(error)
            code = as_int(failure["code"])
            raise _ERROR_CLASSES.get(code, RPCError)(code, as_str(failure["message"]))
        return body.get("result")

    def close(self) -> None:
        """Close the underlying HTTP session."""
        self._http.close()

    def __enter__(self) -> Self:
        """Enter a context manager.

        Returns:
            This client.
        """
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Close the session on context exit.

        Args:
            exc_type: Exception type, if one was raised.
            exc_value: Exception instance, if one was raised.
            traceback: Traceback, if an exception was raised.
        """
        self.close()
