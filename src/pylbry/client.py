# ABOUTME: JSON-RPC transport for the lbrynet daemon.
# ABOUTME: Owns the endpoint, pooled session, timeouts and error unwrapping.
"""JSON-RPC transport for the lbrynet daemon."""

from __future__ import annotations

import time
from types import TracebackType
from typing import Self

import httpx

from pylbry.api.claims import ClaimsAPI
from pylbry.api.files import FilesAPI
from pylbry.errors import (
    DaemonInternalError,
    DaemonUnavailableError,
    InvalidParamsError,
    MethodNotFoundError,
    PyLBRYError,
    RPCError,
)
from pylbry.models import JSONValue, as_int, as_object, as_str

DEFAULT_ENDPOINT = "http://localhost:5279"
DEFAULT_TIMEOUT = 10.0
DEFAULT_DOWNLOAD_TIMEOUT = 60.0

MAX_ATTEMPTS = 3
BASE_DELAY = 0.25
MAX_DELAY = 4.0

# Only reads safe to repeat. A get is excluded on purpose: repeating it costs a
# download_timeout each time, and whether a dead stream is worth another try is
# an archiving decision, not a transport one.
RETRYABLE_METHODS = frozenset({"resolve", "claim_search", "file_list"})

_ERROR_CLASSES: dict[int, type[RPCError]] = {
    -32601: MethodNotFoundError,
    -32602: InvalidParamsError,
    -32603: DaemonInternalError,
    -32500: DaemonInternalError,
}


def should_retry(
    method: str, attempt: int, max_attempts: int, error: Exception
) -> bool:
    """Decide whether a failed call is worth attempting again.

    Retryable failures are the ones that say nothing about the request: the
    daemon was unreachable, or it failed internally and answered 5xx. A daemon
    that read the request and rejected it will reject it identically next time.

    Args:
        method: Daemon method that failed.
        attempt: One-based number of the attempt that just failed.
        max_attempts: Total attempts allowed for one call.
        error: Failure raised by that attempt.

    Returns:
        True if the call should be attempted again.
    """
    if method not in RETRYABLE_METHODS:
        return False
    if attempt >= max_attempts:
        return False
    return isinstance(error, DaemonUnavailableError | DaemonInternalError)


def backoff_delay(attempt: int) -> float:
    """Compute how long to wait before the attempt after this one.

    Args:
        attempt: One-based number of the attempt that just failed.

    Returns:
        Seconds to wait, doubling per attempt up to a ceiling.
    """
    return min(BASE_DELAY * 2 ** (attempt - 1), MAX_DELAY)


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
        self.claims = ClaimsAPI(self)
        self.files = FilesAPI(self)

    def call(
        self,
        method: str,
        params: dict[str, JSONValue] | None = None,
        *,
        timeout: float | None = None,
    ) -> JSONValue:
        """Invoke a daemon method and return its result.

        Idempotent reads are retried with backoff when the daemon is
        unreachable or fails internally; every other method and every other
        failure is raised on the first attempt.

        Args:
            method: Daemon method name.
            params: Parameters for the method.
            timeout: Read timeout override in seconds.

        Returns:
            The decoded ``result`` value from the daemon.

        Raises:
            PyLBRYError: The last failure, once retries are exhausted or the
                failure is one we do not retry.
        """
        attempt = 1
        while True:
            try:
                return self._attempt(method, params, timeout)
            except PyLBRYError as error:
                if not should_retry(method, attempt, MAX_ATTEMPTS, error):
                    raise
            time.sleep(backoff_delay(attempt))
            attempt += 1

    def _attempt(
        self,
        method: str,
        params: dict[str, JSONValue] | None,
        timeout: float | None,
    ) -> JSONValue:
        """Make one HTTP request to the daemon and unwrap its response.

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
