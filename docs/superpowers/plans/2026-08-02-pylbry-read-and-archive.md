# pyLBRY Read and Archive Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a strictly-typed Python library that reads from the LBRY network through a local `lbrynet` daemon and archives claims and media with durable, resumable state, plus a thin CLI over it.

**Architecture:** A `Client` owns JSON-RPC transport and error unwrapping; typed verb namespaces (`client.claims`, `client.files`) sit on top; an archiver above those indexes a channel into SQLite and then fetches media through a bounded thread pool. Dependencies run strictly one way: `cli → archive → api → client → {errors, models}`.

**Tech Stack:** Python 3.14, uv, httpx (only runtime dependency), stdlib `sqlite3` and `argparse`, ruff, ty, pytest with pytest-cov and pytest-xdist.

**Spec:** `docs/superpowers/specs/2026-08-02-pylbry-design.md`

## Global Constraints

Every task's requirements implicitly include this section.

- Python `>=3.14`. Environment is `uv venv` + `uv sync`. All commands run via `uv run`.
- Runtime dependencies: **`httpx` only**. Everything else is stdlib.
- Every file starts with exactly two `# ABOUTME: ` comment lines, then a module docstring. **Verified:** putting the ABOUTME lines inside the docstring trips ruff `D205` (`missing-blank-line-after-summary`).
- Every function and class carries a Google-style docstring. `DOC` rules are active and check that `Args`/`Returns`/`Raises` match the signature.
- Ruff select list is fixed in Task 1 and must not be narrowed. `ty` runs with `all = "error"`.
- **No mocks, ever.** Network paths use a live `lbrynet` daemon. Non-network code (`store.py`, CLI parsing) uses real SQLite and real temp directories — that is not mocking.
- 100% branch coverage on the full suite. Do not write a branch you cannot provoke for real; delete it instead. `# pragma: no cover` requires a justification comment and the target is zero.
- `JSONValue` is written wrapped in parentheses with `None` **last** — RUF036 (`none-not-at-end-of-union`) rejects `None` mid-union, and the one-line form exceeds 88 characters:

```python
type JSONValue = (
    str | int | float | bool | list[JSONValue] | dict[str, JSONValue] | None
)
```

- **Never name a method `list`.** Inside a class body `list[str]` then resolves to the method and `ty` fails with `invalid-type-form`. The file-listing verb is `client.files.query()`.
- Daemon endpoint for tests comes from `PYLBRY_TEST_DAEMON`, defaulting to `http://localhost:5279`.

**Commands:**

| Purpose | Command |
| --- | --- |
| Full gate (what CI and commits must pass) | `uv run pytest --cov-fail-under=100` |
| Fast iteration on one test | `uv run pytest tests/path.py::name -n0 --no-cov -v` |
| Lint / format / types | `uv run ruff check` · `uv run ruff format` · `uv run ty check` |

**Note on the coverage gate:** `--cov-fail-under=100` is deliberately **not** in `addopts`. With it there, every single-test TDD run would fail the threshold and make incremental development impossible. The threshold is applied to full-suite runs only.

---

## File Structure

| File | Responsibility |
| --- | --- |
| `pyproject.toml` | Dependencies, ruff/ty/pytest/coverage configuration |
| `.github/workflows/checks.yml` | CI: lint, format, types (no daemon available) |
| `src/pylbry/errors.py` | Exception hierarchy |
| `src/pylbry/models.py` | `JSONValue`, narrowing helpers, frozen record types |
| `src/pylbry/client.py` | Transport: endpoint, session, `call()`, namespace wiring |
| `src/pylbry/api/claims.py` | `resolve`, `resolve_many`, `search`, `iter_channel` |
| `src/pylbry/api/files.py` | `download`, `query` |
| `src/pylbry/archive/store.py` | SQLite schema and queries |
| `src/pylbry/archive/archiver.py` | Index phase, fetch phase, reconcile, resume |
| `src/pylbry/cli.py` | argparse shell; the only module allowed to `print` |
| `tests/conftest.py` | Daemon fixtures, discovered test claim |

---

### Task 1: Tooling, gates and the error hierarchy

Establishes every quality gate before any logic exists, and proves the gates work against real code. `errors.py` is pure and daemon-free, so it can be fully covered immediately.

**Files:**
- Modify: `pyproject.toml`
- Create: `src/pylbry/errors.py`
- Create: `tests/test_errors.py`
- Modify: `src/pylbry/__init__.py`
- Create: `.github/workflows/checks.yml`
- Modify: `README.md`

**Interfaces:**
- Consumes: nothing.
- Produces: `PyLBRYError`, `DaemonUnavailableError`, `RPCError(code: int, message: str)` with `.code`/`.message`, `MethodNotFoundError`, `InvalidParamsError`, `DaemonInternalError`, `OperationFailedError(method: str, message: str)` with `.method`/`.message`.

- [ ] **Step 1: Write the full `pyproject.toml`**

```toml
[project]
name = "pylbry"
version = "0.1.0"
description = "A modern python library for interacting with the LBRY network."
readme = "README.md"
authors = [
    { name = "Ben Hammersley", email = "ben@hammersleyfutures.com" }
]
requires-python = ">=3.14"
dependencies = ["httpx>=0.28.1,<0.29.0"]

[project.scripts]
pylbry = "pylbry.cli:main"

[build-system]
requires = ["uv_build>=0.11.32,<0.12.0"]
build-backend = "uv_build"

[dependency-groups]
dev = [
  "ruff>=0.16.1,<0.17.0",
  "ty>=0.0.65,<0.1.0",
  "pytest>=9.1.1,<10.0.0",
  "pytest-cov>=7.1.0,<8.0.0",
  "pytest-xdist>=3.8.0,<4.0.0",
]

[tool.ty.environment]
python-version = "3.14"

[tool.ty.rules]
all = "error"

[tool.ruff]
target-version = "py314"

[tool.ruff.lint]
preview = true
select = ["E","W","F","I","N","D","UP","B","A","C4","SIM","RUF",
          "ANN","PYI","PTH","TID","ERA","PL","T20","DOC"]

[tool.ruff.lint.pydocstyle]
convention = "google"

[tool.ruff.lint.per-file-ignores]
"src/pylbry/cli.py" = ["T20"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-q --strict-markers --strict-config -n auto --dist loadgroup --cov --cov-report=term-missing"
markers = ["live: requires a running lbrynet daemon"]

[tool.coverage.run]
branch = true
source = ["src/pylbry"]

[tool.coverage.report]
exclude_also = ["if TYPE_CHECKING:", "@overload"]
```

- [ ] **Step 2: Create the environment**

Run: `uv venv && uv sync`
Expected: `.venv/` created, `uv.lock` written, dev group installed.

- [ ] **Step 3: Write the failing test**

Create `tests/test_errors.py`:

```python
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


def test_rpc_error_carries_code_and_message() -> None:
    """An RPCError exposes the daemon's code and message."""
    error = RPCError(-32601, "Method Not Found")
    assert error.code == -32601
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
```

- [ ] **Step 4: Run test to verify it fails**

Run: `uv run pytest tests/test_errors.py -n0 --no-cov -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pylbry.errors'`

- [ ] **Step 5: Write `src/pylbry/errors.py`**

```python
# ABOUTME: Exception hierarchy for pyLBRY.
# ABOUTME: Separates transport, JSON-RPC and in-result daemon failures.
"""Exception hierarchy for pyLBRY."""


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
```

- [ ] **Step 6: Replace `src/pylbry/__init__.py`**

```python
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
```

- [ ] **Step 7: Run the full gate**

Run: `uv run ruff format && uv run ruff check && uv run ty check && uv run pytest --cov-fail-under=100`
Expected: all clean, tests pass, coverage 100%.

- [ ] **Step 8: Write `.github/workflows/checks.yml`**

CI cannot run the test suite — it needs a live daemon. It runs the static gates only.

```yaml
name: checks

on:
  push:
  pull_request:

jobs:
  static:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5
      - uses: astral-sh/setup-uv@v7
        with:
          python-version: "3.14"
      - run: uv sync
      - run: uv run ruff check
      - run: uv run ruff format --check
      - run: uv run ty check
```

- [ ] **Step 9: Write `README.md`**

```markdown
# pyLBRY

A Python library for reading from and archiving the LBRY network.

Requires a running `lbrynet` daemon. See
`docs/superpowers/specs/2026-08-02-pylbry-design.md` for the design.

## Development

    uv venv && uv sync
    uv run pytest --cov-fail-under=100
    uv run ruff check && uv run ty check

The test suite requires a reachable `lbrynet` daemon. Set `PYLBRY_TEST_DAEMON`
if it is not at `http://localhost:5279`.
```

- [ ] **Step 10: Remove the empty `lib/` directory**

Run: `rmdir lib`
(It is empty and untracked; git never recorded it.)

- [ ] **Step 11: Commit**

```bash
git add pyproject.toml uv.lock src/pylbry tests README.md .github
git commit -m "Add tooling gates and error hierarchy"
```

---

### Task 2: JSON value type, narrowing helpers and transport

`Client.call()` handles error channels 1 and 2. The narrowing helpers are what make strict typing possible without `Any`, and each is directly unit-testable in both directions — which is how the 100% branch target stays reachable.

**Files:**
- Create: `src/pylbry/models.py`
- Create: `src/pylbry/client.py`
- Create: `tests/conftest.py`
- Create: `tests/test_models.py`
- Create: `tests/test_client.py`

**Interfaces:**
- Consumes: `pylbry.errors` (all classes from Task 1).
- Produces: `JSONValue`; `as_object(value) -> dict[str, JSONValue]`, `as_list(value) -> list[JSONValue]`, `as_str(value) -> str`, `as_int(value) -> int`, `as_bool(value) -> bool`, `opt_str(value) -> str | None`, `opt_int(value) -> int | None`; `Client(endpoint=..., *, timeout=..., download_timeout=...)` with `.call(method, params=None, *, timeout=None) -> JSONValue`, `.close()`, context-manager support, and `.endpoint`/`.download_timeout` attributes.

- [ ] **Step 1: Write the failing helper tests**

Create `tests/test_models.py`:

```python
# ABOUTME: Tests for JSON narrowing helpers and record types.
# ABOUTME: Covers both the success and failure path of every helper.
"""Tests for JSON narrowing helpers and record types."""

import pytest

from pylbry.errors import DaemonInternalError
from pylbry.models import (
    as_bool,
    as_int,
    as_list,
    as_object,
    as_str,
    opt_int,
    opt_str,
)


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
    assert as_int(3) == 3


def test_as_int_rejects_a_non_integer() -> None:
    """as_int raises when the value is not an integer."""
    with pytest.raises(DaemonInternalError, match="expected int"):
        as_int("3")


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
    assert opt_int(2) == 2


def test_opt_int_rejects_a_non_integer() -> None:
    """opt_int raises when a present value is not an integer."""
    with pytest.raises(DaemonInternalError, match="expected int"):
        opt_int("2")
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_models.py -n0 --no-cov -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pylbry.models'`

- [ ] **Step 3: Write `src/pylbry/models.py`**

Note `as_bool` checks `bool` before `int` matters nowhere here, but `as_int` must
reject `bool` explicitly because `bool` is a subclass of `int` in Python.

```python
# ABOUTME: JSON value type, narrowing helpers and frozen record types.
# ABOUTME: Narrowing turns untyped daemon JSON into typed values without Any.
"""JSON value type, narrowing helpers and frozen record types."""

from pylbry.errors import DaemonInternalError

type JSONValue = (
    str | int | float | bool | list[JSONValue] | dict[str, JSONValue] | None
)

_NARROWING_CODE = -32603


def as_object(value: JSONValue) -> dict[str, JSONValue]:
    """Narrow a JSON value to an object.

    Args:
        value: Value returned by the daemon.

    Returns:
        The value as a mapping.

    Raises:
        DaemonInternalError: If the value is not a JSON object.
    """
    if isinstance(value, dict):
        return value
    raise DaemonInternalError(
        _NARROWING_CODE, f"expected object, got {type(value).__name__}"
    )


def as_list(value: JSONValue) -> list[JSONValue]:
    """Narrow a JSON value to an array.

    Args:
        value: Value returned by the daemon.

    Returns:
        The value as a list.

    Raises:
        DaemonInternalError: If the value is not a JSON array.
    """
    if isinstance(value, list):
        return value
    raise DaemonInternalError(
        _NARROWING_CODE, f"expected list, got {type(value).__name__}"
    )


def as_str(value: JSONValue) -> str:
    """Narrow a JSON value to a string.

    Args:
        value: Value returned by the daemon.

    Returns:
        The value as a string.

    Raises:
        DaemonInternalError: If the value is not a string.
    """
    if isinstance(value, str):
        return value
    raise DaemonInternalError(
        _NARROWING_CODE, f"expected str, got {type(value).__name__}"
    )


def as_int(value: JSONValue) -> int:
    """Narrow a JSON value to an integer.

    Args:
        value: Value returned by the daemon.

    Returns:
        The value as an integer.

    Raises:
        DaemonInternalError: If the value is not an integer.
    """
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    raise DaemonInternalError(
        _NARROWING_CODE, f"expected int, got {type(value).__name__}"
    )


def as_bool(value: JSONValue) -> bool:
    """Narrow a JSON value to a boolean.

    Args:
        value: Value returned by the daemon.

    Returns:
        The value as a boolean.

    Raises:
        DaemonInternalError: If the value is not a boolean.
    """
    if isinstance(value, bool):
        return value
    raise DaemonInternalError(
        _NARROWING_CODE, f"expected bool, got {type(value).__name__}"
    )


def opt_str(value: JSONValue) -> str | None:
    """Narrow an optional JSON value to a string.

    Args:
        value: Value returned by the daemon, possibly absent.

    Returns:
        The string, or None when the value is absent.
    """
    if value is None:
        return None
    return as_str(value)


def opt_int(value: JSONValue) -> int | None:
    """Narrow an optional JSON value to an integer.

    Args:
        value: Value returned by the daemon, possibly absent.

    Returns:
        The integer, or None when the value is absent.
    """
    if value is None:
        return None
    return as_int(value)
```

- [ ] **Step 4: Run to verify the helper tests pass**

Run: `uv run pytest tests/test_models.py -n0 --no-cov -v`
Expected: PASS (14 tests)

- [ ] **Step 5: Write `tests/conftest.py`**

```python
# ABOUTME: Shared pytest fixtures for pyLBRY tests.
# ABOUTME: Provides a live daemon client and a discovered, resolvable claim.
"""Shared pytest fixtures for pyLBRY tests."""

import os
from collections.abc import Iterator

import pytest

from pylbry.client import Client

DAEMON_URL = os.environ.get("PYLBRY_TEST_DAEMON", "http://localhost:5279")


@pytest.fixture(scope="session")
def client() -> Iterator[Client]:
    """Yield a client bound to the live daemon.

    Yields:
        A client connected to the daemon under test.
    """
    with Client(DAEMON_URL) as live_client:
        live_client.call("status")
        yield live_client
```

- [ ] **Step 6: Write the failing transport tests**

Create `tests/test_client.py`. Every error here comes from a real daemon
behaving correctly in response to incorrect use.

```python
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


def test_status_returns_a_running_daemon(client: Client) -> None:
    """A status call returns an object reporting the daemon is running."""
    result = as_object(client.call("status"))
    assert result["is_running"] is True


def test_unreachable_daemon_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pointing the client at a closed port raises DaemonUnavailableError."""
    with Client("http://127.0.0.1:1") as dead:
        with pytest.raises(DaemonUnavailableError, match="cannot reach"):
            dead.call("status")


def test_unknown_method_raises_method_not_found(client: Client) -> None:
    """Calling a method the daemon does not expose raises MethodNotFoundError."""
    with pytest.raises(MethodNotFoundError) as caught:
        client.call("no_such_method_exists")
    assert caught.value.code == -32601


def test_bad_params_raise_invalid_params(client: Client) -> None:
    """Calling resolve with an unknown parameter raises InvalidParamsError."""
    with pytest.raises(InvalidParamsError) as caught:
        client.call("resolve", {"not_a_real_parameter": "x"})
    assert caught.value.code == -32602
```

Delete the unused `monkeypatch` parameter if ruff flags it — the test needs no
fixture. It is listed here only to show the signature shape; prefer:
`def test_unreachable_daemon_raises() -> None:`

- [ ] **Step 7: Run to verify it fails**

Run: `uv run pytest tests/test_client.py -n0 --no-cov -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pylbry.client'`

- [ ] **Step 8: Write `src/pylbry/client.py`**

The `claims` and `files` namespaces are wired in Tasks 4 and 5; this version has
`call()` only.

```python
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
            RPCError: If the daemon returns a JSON-RPC error object.
        """
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
```

- [ ] **Step 9: Run to verify it passes**

Run: `uv run pytest tests/test_client.py -n0 --no-cov -v`
Expected: PASS (4 tests). Requires a running daemon.

- [ ] **Step 10: Run the full gate**

Run: `uv run ruff format && uv run ruff check && uv run ty check && uv run pytest --cov-fail-under=100`
Expected: all clean, coverage 100%.

- [ ] **Step 11: Commit**

```bash
git add src/pylbry/models.py src/pylbry/client.py tests/
git commit -m "Add JSON narrowing helpers and daemon transport"
```

---

### Task 3: Record types

Frozen dataclasses parsed from real daemon payloads. `raw` preserves the complete
claim JSON so nothing is lost if content later goes dark.

**Files:**
- Modify: `src/pylbry/models.py`
- Modify: `tests/test_models.py`

**Interfaces:**
- Consumes: narrowing helpers and `JSONValue` from Task 2.
- Produces: `Claim.from_dict(data) -> Claim`, `FileRef.from_dict(data) -> FileRef`, `Page[T](items, page, page_size, total_pages)`, `ResolveFailure(url, message)`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_models.py`:

```python
def test_claim_parses_a_stream_claim() -> None:
    """Claim.from_dict reads identity, channel and stream fields."""
    data = {
        "claim_id": "abc123",
        "name": "a-video",
        "canonical_url": "lbry://@chan#a/a-video#b",
        "permanent_url": "lbry://a-video#abc123",
        "value_type": "stream",
        "height": 1000,
        "timestamp": 1600000000,
        "signing_channel": {"claim_id": "chan1", "name": "@chan"},
        "value": {
            "title": "A Video",
            "description": "Words",
            "source": {"sd_hash": "deadbeef", "media_type": "video/mp4", "size": "42"},
            "video": {"duration": 90},
        },
    }
    claim = Claim.from_dict(data)
    assert claim.claim_id == "abc123"
    assert claim.channel_id == "chan1"
    assert claim.channel_name == "@chan"
    assert claim.sd_hash == "deadbeef"
    assert claim.media_type == "video/mp4"
    assert claim.size == 42
    assert claim.duration == 90
    assert claim.raw == data


def test_claim_parses_a_claim_without_a_source_or_channel() -> None:
    """Claim.from_dict tolerates absent channel, source and video sections."""
    data = {
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
    data = {
        "claim_id": "abc123",
        "sd_hash": "deadbeef",
        "file_name": "a-video.mp4",
        "download_path": "/tmp/a-video.mp4",
        "status": "finished",
        "completed": True,
        "written_bytes": 42,
        "total_bytes": 42,
        "blobs_completed": 2,
        "blobs_in_stream": 2,
    }
    file_ref = FileRef.from_dict(data)
    assert file_ref.completed is True
    assert file_ref.written_bytes == 42
    assert file_ref.blobs_in_stream == 2


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
```

Add to the imports at the top of `tests/test_models.py`:

```python
from pylbry.models import Claim, FileRef, Page, ResolveFailure
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_models.py -n0 --no-cov -v`
Expected: FAIL with `ImportError: cannot import name 'Claim'`

- [ ] **Step 3: Append the record types to `src/pylbry/models.py`**

Add these imports at the top of the file:

```python
from dataclasses import dataclass
```

Then append:

```python
@dataclass(frozen=True, slots=True)
class Claim:
    """A resolved claim from the LBRY network."""

    claim_id: str
    name: str
    canonical_url: str
    permanent_url: str
    claim_type: str
    title: str | None
    description: str | None
    channel_id: str | None
    channel_name: str | None
    height: int
    timestamp: int | None
    sd_hash: str | None
    media_type: str | None
    size: int | None
    duration: int | None
    raw: dict[str, JSONValue]

    @classmethod
    def from_dict(cls, data: dict[str, JSONValue]) -> "Claim":
        """Build a claim from a daemon payload.

        Args:
            data: A single claim object as returned by the daemon.

        Returns:
            The parsed claim, retaining the original payload in ``raw``.
        """
        value = as_object(data.get("value") or {})
        source = as_object(value.get("source") or {})
        video = as_object(value.get("video") or {})
        channel = as_object(data.get("signing_channel") or {})
        size = source.get("size")
        return cls(
            claim_id=as_str(data["claim_id"]),
            name=as_str(data["name"]),
            canonical_url=as_str(data["canonical_url"]),
            permanent_url=as_str(data["permanent_url"]),
            claim_type=as_str(data["value_type"]),
            title=opt_str(value.get("title")),
            description=opt_str(value.get("description")),
            channel_id=opt_str(channel.get("claim_id")),
            channel_name=opt_str(channel.get("name")),
            height=as_int(data["height"]),
            timestamp=opt_int(data.get("timestamp")),
            sd_hash=opt_str(source.get("sd_hash")),
            media_type=opt_str(source.get("media_type")),
            size=None if size is None else int(as_str(size)),
            duration=opt_int(video.get("duration")),
            raw=data,
        )


@dataclass(frozen=True, slots=True)
class FileRef:
    """A file the daemon knows about, downloaded or in progress."""

    claim_id: str
    sd_hash: str
    file_name: str | None
    download_path: str | None
    status: str
    completed: bool
    written_bytes: int
    total_bytes: int | None
    blobs_completed: int
    blobs_in_stream: int

    @classmethod
    def from_dict(cls, data: dict[str, JSONValue]) -> "FileRef":
        """Build a file reference from a daemon payload.

        Args:
            data: A single file object as returned by ``file_list``.

        Returns:
            The parsed file reference.
        """
        return cls(
            claim_id=as_str(data["claim_id"]),
            sd_hash=as_str(data["sd_hash"]),
            file_name=opt_str(data.get("file_name")),
            download_path=opt_str(data.get("download_path")),
            status=as_str(data["status"]),
            completed=as_bool(data["completed"]),
            written_bytes=as_int(data["written_bytes"]),
            total_bytes=opt_int(data.get("total_bytes")),
            blobs_completed=as_int(data["blobs_completed"]),
            blobs_in_stream=as_int(data["blobs_in_stream"]),
        )


@dataclass(frozen=True, slots=True)
class Page[T]:
    """One page of results from a paginated daemon method."""

    items: list[T]
    page: int
    page_size: int
    total_pages: int | None


@dataclass(frozen=True, slots=True)
class ResolveFailure:
    """A URL that could not be resolved, recorded rather than raised."""

    url: str
    message: str
```

**Note on `size`:** the daemon serialises stream size as a *string*, not a
number, which is why it is parsed with `int(as_str(size))` rather than `as_int`.

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_models.py -n0 --no-cov -v`
Expected: PASS

- [ ] **Step 5: Verify the parser against real daemon output**

Add to `tests/test_client.py`:

```python
def test_claim_parses_real_daemon_output(client: Client) -> None:
    """A claim from a live claim_search parses without error."""
    result = as_object(
        client.call("claim_search", {"page_size": 1, "has_source": True})
    )
    items = as_list(result["items"])
    claim = Claim.from_dict(as_object(items[0]))
    assert claim.claim_id
    assert claim.sd_hash is not None
```

Add `Claim`, `as_list` to that file's imports from `pylbry.models`.

- [ ] **Step 6: Run the full gate**

Run: `uv run ruff format && uv run ruff check && uv run ty check && uv run pytest --cov-fail-under=100`
Expected: all clean, coverage 100%.

- [ ] **Step 7: Commit**

```bash
git add src/pylbry/models.py tests/
git commit -m "Add claim, file and page record types"
```

---

### Task 4: Claims API

**Files:**
- Create: `src/pylbry/api/__init__.py`
- Create: `src/pylbry/api/claims.py`
- Modify: `src/pylbry/client.py`
- Create: `tests/api/__init__.py` *(not needed if using rootdir-relative test paths; create only if imports fail)*
- Create: `tests/test_claims.py`

**Interfaces:**
- Consumes: `Client.call`, `Claim`, `Page`, `ResolveFailure`, narrowing helpers.
- Produces: `client.claims.resolve(url) -> Claim`; `client.claims.resolve_many(urls) -> dict[str, Claim | ResolveFailure]`; `client.claims.search(*, page=1, page_size=20, **filters) -> Page[Claim]`; `client.claims.iter_channel(channel_id, *, has_source=True, page_size=50) -> Iterator[Claim]`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_claims.py`:

```python
# ABOUTME: Tests for the claims namespace against a live lbrynet daemon.
# ABOUTME: Covers single resolve, batch resolve, search and channel iteration.
"""Tests for the claims namespace against a live lbrynet daemon."""

import pytest

from pylbry.client import Client
from pylbry.errors import OperationFailedError
from pylbry.models import Claim, ResolveFailure

pytestmark = pytest.mark.live

JUNK_URL = "lbry://pylbry-does-not-exist-9f3a2b"


def test_search_returns_a_page_of_claims(client: Client) -> None:
    """A search returns claims and echoes the requested page size."""
    page = client.claims.search(page_size=2, has_source=True)
    assert page.page_size == 2
    assert len(page.items) <= 2
    assert all(isinstance(item, Claim) for item in page.items)


def test_resolve_returns_a_claim(client: Client) -> None:
    """Resolving a URL discovered from search returns that claim."""
    discovered = client.claims.search(page_size=1, has_source=True).items[0]
    claim = client.claims.resolve(discovered.canonical_url)
    assert claim.claim_id == discovered.claim_id


def test_resolve_raises_for_an_unknown_url(client: Client) -> None:
    """Resolving a URL with no claim raises OperationFailedError."""
    with pytest.raises(OperationFailedError):
        client.claims.resolve(JUNK_URL)


def test_resolve_many_records_failures_as_data(client: Client) -> None:
    """A batch resolve returns claims and failures side by side."""
    discovered = client.claims.search(page_size=1, has_source=True).items[0]
    results = client.claims.resolve_many([discovered.canonical_url, JUNK_URL])
    assert isinstance(results[discovered.canonical_url], Claim)
    assert isinstance(results[JUNK_URL], ResolveFailure)


def test_iter_channel_yields_claims_across_pages(client: Client) -> None:
    """Channel iteration pages transparently and stops when exhausted."""
    seed = client.claims.search(page_size=1, has_source=True).items[0]
    assert seed.channel_id is not None
    claims = list(client.claims.iter_channel(seed.channel_id, page_size=2))
    assert claims
    assert len({claim.claim_id for claim in claims}) == len(claims)
```

If the seeded claim has no channel, the assertion will fail loudly rather than
skip — that is intended; it means the discovery query needs a `channel_ids`
filter, not that the test should be softened.

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_claims.py -n0 --no-cov -v`
Expected: FAIL with `AttributeError: 'Client' object has no attribute 'claims'`

- [ ] **Step 3: Create `src/pylbry/api/__init__.py`**

```python
# ABOUTME: Typed verb namespaces over the daemon transport.
# ABOUTME: Each module owns one group of related daemon methods.
"""Typed verb namespaces over the daemon transport."""
```

- [ ] **Step 4: Write `src/pylbry/api/claims.py`**

```python
# ABOUTME: Claim resolution, search and channel enumeration.
# ABOUTME: Batch resolve records per-URL failures instead of raising.
"""Claim resolution, search and channel enumeration."""

from collections.abc import Iterator, Sequence
from typing import TYPE_CHECKING

from pylbry.errors import OperationFailedError
from pylbry.models import (
    Claim,
    JSONValue,
    Page,
    ResolveFailure,
    as_list,
    as_object,
    as_str,
    opt_int,
)

if TYPE_CHECKING:
    from pylbry.client import Client


class ClaimsAPI:
    """Claim reads: resolution, search and channel enumeration."""

    def __init__(self, client: "Client") -> None:
        """Bind the namespace to a transport.

        Args:
            client: Transport used for every call.
        """
        self._client = client

    def resolve(self, url: str) -> Claim:
        """Resolve a single URL to a claim.

        Args:
            url: An LBRY URL.

        Returns:
            The resolved claim.

        Raises:
            OperationFailedError: If the daemon could not resolve the URL.
        """
        resolved = self.resolve_many([url])[url]
        if isinstance(resolved, ResolveFailure):
            raise OperationFailedError("resolve", resolved.message)
        return resolved

    def resolve_many(self, urls: Sequence[str]) -> dict[str, Claim | ResolveFailure]:
        """Resolve several URLs, recording failures rather than raising.

        Args:
            urls: LBRY URLs to resolve.

        Returns:
            A mapping of URL to either a claim or a failure record.
        """
        raw = as_object(self._client.call("resolve", {"urls": list(urls)}))
        results: dict[str, Claim | ResolveFailure] = {}
        for url, entry in raw.items():
            payload = as_object(entry)
            error = payload.get("error")
            if error is None:
                results[url] = Claim.from_dict(payload)
            else:
                results[url] = ResolveFailure(
                    url=url, message=_error_message(as_object(error))
                )
        return results

    def search(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        **filters: JSONValue,
    ) -> Page[Claim]:
        """Search claims.

        Args:
            page: Page number, one-based.
            page_size: Number of claims per page.
            **filters: Additional claim_search filters, such as
                ``has_source`` or ``channel_ids``.

        Returns:
            One page of matching claims.
        """
        params: dict[str, JSONValue] = {
            "page": page,
            "page_size": page_size,
            **filters,
        }
        result = as_object(self._client.call("claim_search", params))
        items = [Claim.from_dict(as_object(item)) for item in as_list(result["items"])]
        return Page(
            items=items,
            page=page,
            page_size=page_size,
            total_pages=opt_int(result.get("total_pages")),
        )

    def iter_channel(
        self,
        channel_id: str,
        *,
        has_source: bool = True,
        page_size: int = 50,
    ) -> Iterator[Claim]:
        """Iterate every claim in a channel, paging transparently.

        Totals are suppressed because counting matching claims is expensive
        server-side and an archiver only needs to know when a page runs short.

        Args:
            channel_id: Claim ID of the channel.
            has_source: Restrict to claims that have downloadable content.
            page_size: Claims requested per page.

        Yields:
            Each claim in the channel.
        """
        page = 1
        while True:
            result = self.search(
                page=page,
                page_size=page_size,
                channel_ids=[channel_id],
                has_source=has_source,
                no_totals=True,
            )
            yield from result.items
            if len(result.items) < page_size:
                return
            page += 1


def _error_message(error: dict[str, JSONValue]) -> str:
    """Extract a human-readable message from a resolve error entry.

    Args:
        error: The ``error`` object from a resolve result.

    Returns:
        The daemon's message text.
    """
    return as_str(error.get("text") or error.get("name") or "resolve failed")
```

- [ ] **Step 5: Wire the namespace into `src/pylbry/client.py`**

Add the import:

```python
from pylbry.api.claims import ClaimsAPI
```

And at the end of `Client.__init__`:

```python
        self.claims = ClaimsAPI(self)
```

- [ ] **Step 6: Run to verify it passes**

Run: `uv run pytest tests/test_claims.py -n0 --no-cov -v`
Expected: PASS (5 tests)

- [ ] **Step 7: Run the full gate**

Run: `uv run ruff format && uv run ruff check && uv run ty check && uv run pytest --cov-fail-under=100`
Expected: all clean, coverage 100%.

- [ ] **Step 8: Commit**

```bash
git add src/pylbry/api src/pylbry/client.py tests/
git commit -m "Add claim resolution, search and channel iteration"
```

---

### Task 5: Files API

Handles error channel 3 — `get` returns `{"error": ...}` inside a *successful*
result, so a failed download is invisible at the HTTP layer.

**Files:**
- Create: `src/pylbry/api/files.py`
- Modify: `src/pylbry/client.py`
- Create: `tests/test_files.py`

**Interfaces:**
- Consumes: `Client.call`, `Client.download_timeout`, `FileRef`, `Page`.
- Produces: `client.files.download(uri, *, download_directory=None, file_name=None, timeout=None) -> FileRef`; `client.files.query(*, claim_id=None, completed=None, page=1, page_size=20) -> Page[FileRef]`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_files.py`:

```python
# ABOUTME: Tests for the files namespace against a live lbrynet daemon.
# ABOUTME: Downloads mutate daemon state, so they are pinned to one worker.
"""Tests for the files namespace against a live lbrynet daemon."""

from pathlib import Path

import pytest

from pylbry.client import Client
from pylbry.errors import OperationFailedError

pytestmark = [pytest.mark.live, pytest.mark.xdist_group("daemon_state")]


def test_query_returns_a_page_of_files(client: Client) -> None:
    """Listing files returns a page, empty or otherwise."""
    page = client.files.query(page_size=5)
    assert page.page_size == 5
    assert len(page.items) <= 5


def test_download_of_a_junk_uri_raises_operation_failed(client: Client) -> None:
    """A get that fails reports through the in-result error channel."""
    with pytest.raises(OperationFailedError) as caught:
        client.files.download("lbry://pylbry-does-not-exist-9f3a2b")
    assert caught.value.method == "get"


def test_download_writes_a_real_file(client: Client, tmp_path: Path) -> None:
    """Downloading a small image claim enqueues it and returns a reference."""
    claim = client.claims.search(
        page_size=1, has_source=True, stream_types=["image"]
    ).items[0]
    file_ref = client.files.download(
        claim.permanent_url, download_directory=str(tmp_path)
    )
    assert file_ref.claim_id == claim.claim_id
    assert file_ref.sd_hash


def test_download_with_a_tiny_timeout_reports_failure(client: Client) -> None:
    """A one-second download timeout surfaces as an operation failure."""
    claim = client.claims.search(page_size=1, has_source=True).items[0]
    with pytest.raises(OperationFailedError):
        client.files.download(claim.permanent_url, timeout=1.0)
```

The last test relies on the daemon's own `timeout` parameter, not our HTTP
timeout — we pass `timeout=1` through to `get` so the *daemon* gives up and
returns an in-result error. If a claim starts within one second the test will
fail; re-run against a less well-seeded claim rather than widening the timeout.

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_files.py -n0 --no-cov -v`
Expected: FAIL with `AttributeError: 'Client' object has no attribute 'files'`

- [ ] **Step 3: Write `src/pylbry/api/files.py`**

```python
# ABOUTME: Download enqueueing and file listing.
# ABOUTME: A get returns after the first bytes are written, not on completion.
"""Download enqueueing and file listing."""

from typing import TYPE_CHECKING

from pylbry.errors import OperationFailedError
from pylbry.models import (
    FileRef,
    JSONValue,
    Page,
    as_list,
    as_object,
    as_str,
    opt_int,
)

if TYPE_CHECKING:
    from pylbry.client import Client


class FilesAPI:
    """Download enqueueing and inspection of files the daemon holds."""

    def __init__(self, client: "Client") -> None:
        """Bind the namespace to a transport.

        Args:
            client: Transport used for every call.
        """
        self._client = client

    def download(
        self,
        uri: str,
        *,
        download_directory: str | None = None,
        file_name: str | None = None,
        timeout: float | None = None,
    ) -> FileRef:
        """Start downloading a stream and return once writing has begun.

        The daemon returns as soon as the first bytes reach disk; the rest of
        the transfer continues in the background. Poll :meth:`query` to observe
        completion.

        Args:
            uri: LBRY URL of the stream.
            download_directory: Directory the daemon should write into.
            file_name: Filename to use instead of the stream's own.
            timeout: Download timeout in seconds passed to the daemon.

        Returns:
            A reference to the file the daemon is writing.

        Raises:
            OperationFailedError: If the daemon reports a failure in-result.
        """
        params: dict[str, JSONValue] = {"uri": uri}
        if download_directory is not None:
            params["download_directory"] = download_directory
        if file_name is not None:
            params["file_name"] = file_name
        if timeout is not None:
            params["timeout"] = int(timeout)
        result = as_object(
            self._client.call("get", params, timeout=self._client.download_timeout)
        )
        error = result.get("error")
        if error is not None:
            raise OperationFailedError("get", as_str(error))
        return FileRef.from_dict(result)

    def query(
        self,
        *,
        claim_id: str | None = None,
        completed: bool | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Page[FileRef]:
        """List files the daemon knows about.

        Args:
            claim_id: Restrict to a single claim.
            completed: Restrict to completed or incomplete downloads.
            page: Page number, one-based.
            page_size: Number of files per page.

        Returns:
            One page of file references.
        """
        params: dict[str, JSONValue] = {"page": page, "page_size": page_size}
        if claim_id is not None:
            params["claim_id"] = claim_id
        if completed is not None:
            params["completed"] = completed
        result = as_object(self._client.call("file_list", params))
        items = [
            FileRef.from_dict(as_object(item)) for item in as_list(result["items"])
        ]
        return Page(
            items=items,
            page=page,
            page_size=page_size,
            total_pages=opt_int(result.get("total_pages")),
        )
```

- [ ] **Step 4: Wire the namespace into `src/pylbry/client.py`**

Add the import:

```python
from pylbry.api.files import FilesAPI
```

And at the end of `Client.__init__`:

```python
        self.files = FilesAPI(self)
```

- [ ] **Step 5: Run to verify it passes**

Run: `uv run pytest tests/test_files.py -n0 --no-cov -v`
Expected: PASS (4 tests)

- [ ] **Step 6: Run the full gate**

Run: `uv run ruff format && uv run ruff check && uv run ty check && uv run pytest --cov-fail-under=100`
Expected: all clean, coverage 100%.

- [ ] **Step 7: Commit**

```bash
git add src/pylbry/api/files.py src/pylbry/client.py tests/
git commit -m "Add download enqueueing and file listing"
```

---

### Task 6: Archive store

Pure SQLite. No daemon needed — real database in a real temp directory.

**Files:**
- Create: `src/pylbry/archive/__init__.py`
- Create: `src/pylbry/archive/store.py`
- Create: `tests/test_store.py`

**Interfaces:**
- Consumes: `Claim` from Task 3.
- Produces: `DownloadState` (StrEnum with `PENDING`, `RUNNING`, `COMPLETE`, `FAILED`, `UNAVAILABLE`); `Store(path: Path)` with `.upsert_claim(claim) -> None`, `.claim_count() -> int`, `.pending(limit: int, max_attempts: int) -> list[str]`, `.set_state(claim_id, state, *, path=None, error=None) -> None`, `.bump_attempts(claim_id) -> None`, `.state_of(claim_id) -> DownloadState | None`, `.reset_running() -> int`, `.counts() -> dict[DownloadState, int]`, `.close() -> None`, context-manager support.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_store.py`:

```python
# ABOUTME: Tests for the SQLite archive store.
# ABOUTME: Uses a real database in a temp directory; no daemon required.
"""Tests for the SQLite archive store."""

from pathlib import Path

from pylbry.archive.store import DownloadState, Store
from pylbry.models import Claim


def make_claim(claim_id: str) -> Claim:
    """Build a minimal claim for store tests.

    Args:
        claim_id: Identifier to give the claim.

    Returns:
        A claim with only the fields the store persists.
    """
    return Claim(
        claim_id=claim_id,
        name="n",
        canonical_url=f"lbry://n#{claim_id}",
        permanent_url=f"lbry://n#{claim_id}",
        claim_type="stream",
        title="T",
        description=None,
        channel_id="chan",
        channel_name="@chan",
        height=1,
        timestamp=None,
        sd_hash="sd",
        media_type="image/png",
        size=10,
        duration=None,
        raw={"claim_id": claim_id},
    )


def test_upsert_claim_inserts_once(tmp_path: Path) -> None:
    """Upserting the same claim twice stores a single row."""
    with Store(tmp_path / "a.db") as store:
        store.upsert_claim(make_claim("a"))
        store.upsert_claim(make_claim("a"))
        assert store.claim_count() == 1
        assert store.state_of("a") is DownloadState.PENDING


def test_pending_returns_claims_awaiting_download(tmp_path: Path) -> None:
    """Pending selects claims that are not yet complete."""
    with Store(tmp_path / "a.db") as store:
        store.upsert_claim(make_claim("a"))
        store.upsert_claim(make_claim("b"))
        store.set_state("b", DownloadState.COMPLETE, path="/tmp/b.png")
        assert store.pending(limit=10, max_attempts=3) == ["a"]


def test_pending_respects_the_attempt_ceiling(tmp_path: Path) -> None:
    """A claim that has exhausted its attempts is no longer pending."""
    with Store(tmp_path / "a.db") as store:
        store.upsert_claim(make_claim("a"))
        store.set_state("a", DownloadState.FAILED, error="boom")
        store.bump_attempts("a")
        assert store.pending(limit=10, max_attempts=1) == []


def test_unavailable_claims_are_not_retried(tmp_path: Path) -> None:
    """Unavailable means nothing is seeding it, so it is never re-queued."""
    with Store(tmp_path / "a.db") as store:
        store.upsert_claim(make_claim("a"))
        store.set_state("a", DownloadState.UNAVAILABLE, error="no peers")
        assert store.pending(limit=10, max_attempts=99) == []


def test_reset_running_requeues_stale_rows(tmp_path: Path) -> None:
    """Rows left running by a crashed process return to pending."""
    with Store(tmp_path / "a.db") as store:
        store.upsert_claim(make_claim("a"))
        store.set_state("a", DownloadState.RUNNING)
        assert store.reset_running() == 1
        assert store.state_of("a") is DownloadState.PENDING


def test_counts_reports_each_state(tmp_path: Path) -> None:
    """Counts groups rows by download state."""
    with Store(tmp_path / "a.db") as store:
        store.upsert_claim(make_claim("a"))
        store.upsert_claim(make_claim("b"))
        store.set_state("b", DownloadState.COMPLETE, path="/tmp/b.png")
        assert store.counts() == {
            DownloadState.PENDING: 1,
            DownloadState.COMPLETE: 1,
        }


def test_state_of_returns_none_for_an_unknown_claim(tmp_path: Path) -> None:
    """Asking about a claim the store has never seen returns None."""
    with Store(tmp_path / "a.db") as store:
        assert store.state_of("missing") is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_store.py -n0 --no-cov -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pylbry.archive'`

- [ ] **Step 3: Create `src/pylbry/archive/__init__.py`**

```python
# ABOUTME: Bulk archiving of claims and media.
# ABOUTME: Holds the SQLite store and the two-phase archiver.
"""Bulk archiving of claims and media."""
```

- [ ] **Step 4: Write `src/pylbry/archive/store.py`**

```python
# ABOUTME: SQLite persistence for archived claims and download state.
# ABOUTME: Single connection behind a lock, because SQLite serialises writes.
"""SQLite persistence for archived claims and download state."""

import json
import sqlite3
import threading
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from types import TracebackType
from typing import Self

from pylbry.models import Claim

SCHEMA = """
CREATE TABLE IF NOT EXISTS claim (
    claim_id      TEXT PRIMARY KEY,
    canonical_url TEXT NOT NULL,
    channel_id    TEXT,
    channel_name  TEXT,
    name          TEXT NOT NULL,
    title         TEXT,
    sd_hash       TEXT,
    media_type    TEXT,
    size          INTEGER,
    height        INTEGER NOT NULL,
    timestamp     INTEGER,
    raw           TEXT NOT NULL,
    first_seen    TEXT NOT NULL,
    last_seen     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS download (
    claim_id      TEXT PRIMARY KEY REFERENCES claim(claim_id),
    state         TEXT NOT NULL,
    path          TEXT,
    bytes_total   INTEGER,
    bytes_written INTEGER,
    attempts      INTEGER NOT NULL DEFAULT 0,
    last_error    TEXT,
    updated_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS channel_sync (
    channel_id  TEXT PRIMARY KEY,
    last_run_at TEXT,
    last_height INTEGER
);

CREATE INDEX IF NOT EXISTS download_state ON download(state);
CREATE INDEX IF NOT EXISTS claim_channel ON claim(channel_id);
"""


class DownloadState(StrEnum):
    """Lifecycle of a single claim's media download."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"
    UNAVAILABLE = "unavailable"


def _now() -> str:
    """Return the current UTC time as an ISO 8601 string.

    Returns:
        Timestamp in ISO 8601 format.
    """
    return datetime.now(UTC).isoformat()


class Store:
    """Durable archive state backed by SQLite."""

    def __init__(self, path: Path) -> None:
        """Open the database, creating the schema if absent.

        Args:
            path: Filesystem path to the SQLite database.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.executescript(SCHEMA)
        self._db.commit()

    def upsert_claim(self, claim: Claim) -> None:
        """Record a claim and queue it for download if it is new.

        Args:
            claim: The claim to persist.
        """
        now = _now()
        with self._lock, self._db:
            self._db.execute(
                """
                INSERT INTO claim (claim_id, canonical_url, channel_id,
                    channel_name, name, title, sd_hash, media_type, size,
                    height, timestamp, raw, first_seen, last_seen)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(claim_id) DO UPDATE SET last_seen=excluded.last_seen
                """,
                (
                    claim.claim_id,
                    claim.canonical_url,
                    claim.channel_id,
                    claim.channel_name,
                    claim.name,
                    claim.title,
                    claim.sd_hash,
                    claim.media_type,
                    claim.size,
                    claim.height,
                    claim.timestamp,
                    json.dumps(claim.raw),
                    now,
                    now,
                ),
            )
            self._db.execute(
                """
                INSERT INTO download (claim_id, state, attempts, updated_at)
                VALUES (?,?,0,?)
                ON CONFLICT(claim_id) DO NOTHING
                """,
                (claim.claim_id, DownloadState.PENDING, now),
            )

    def claim_count(self) -> int:
        """Count claims held in the store.

        Returns:
            The number of claim rows.
        """
        with self._lock:
            row = self._db.execute("SELECT COUNT(*) FROM claim").fetchone()
        return int(row[0])

    def pending(self, limit: int, max_attempts: int) -> list[str]:
        """Select claims still awaiting a successful download.

        Unavailable claims are excluded permanently: nothing is seeding them,
        so retrying only burns the daemon's download timeout.

        Args:
            limit: Maximum number of claim IDs to return.
            max_attempts: Attempt ceiling above which a claim is abandoned.

        Returns:
            Claim IDs to attempt, oldest first.
        """
        with self._lock:
            rows = self._db.execute(
                """
                SELECT claim_id FROM download
                WHERE state IN (?,?) AND attempts < ?
                ORDER BY updated_at
                LIMIT ?
                """,
                (
                    DownloadState.PENDING,
                    DownloadState.FAILED,
                    max_attempts,
                    limit,
                ),
            ).fetchall()
        return [str(row[0]) for row in rows]

    def set_state(
        self,
        claim_id: str,
        state: DownloadState,
        *,
        path: str | None = None,
        error: str | None = None,
    ) -> None:
        """Move a claim's download to a new state.

        Args:
            claim_id: Claim whose download state changes.
            state: The new state.
            path: Filesystem path of the downloaded media, when complete.
            error: Error text, when the attempt failed.
        """
        with self._lock, self._db:
            self._db.execute(
                """
                UPDATE download
                SET state=?, path=COALESCE(?, path), last_error=?, updated_at=?
                WHERE claim_id=?
                """,
                (state, path, error, _now(), claim_id),
            )

    def bump_attempts(self, claim_id: str) -> None:
        """Increment the attempt counter for a claim.

        Args:
            claim_id: Claim whose attempt count increases.
        """
        with self._lock, self._db:
            self._db.execute(
                "UPDATE download SET attempts=attempts+1, updated_at=? WHERE claim_id=?",
                (_now(), claim_id),
            )

    def state_of(self, claim_id: str) -> DownloadState | None:
        """Read a claim's current download state.

        Args:
            claim_id: Claim to inspect.

        Returns:
            The state, or None if the store has never seen the claim.
        """
        with self._lock:
            row = self._db.execute(
                "SELECT state FROM download WHERE claim_id=?", (claim_id,)
            ).fetchone()
        if row is None:
            return None
        return DownloadState(row[0])

    def reset_running(self) -> int:
        """Return rows left running by a crashed process to pending.

        Returns:
            The number of rows reset.
        """
        with self._lock, self._db:
            cursor = self._db.execute(
                "UPDATE download SET state=?, updated_at=? WHERE state=?",
                (DownloadState.PENDING, _now(), DownloadState.RUNNING),
            )
        return cursor.rowcount

    def counts(self) -> dict[DownloadState, int]:
        """Count downloads grouped by state.

        Returns:
            A mapping of state to row count, omitting states with no rows.
        """
        with self._lock:
            rows = self._db.execute(
                "SELECT state, COUNT(*) FROM download GROUP BY state"
            ).fetchall()
        return {DownloadState(row[0]): int(row[1]) for row in rows}

    def close(self) -> None:
        """Close the database connection."""
        self._db.close()

    def __enter__(self) -> Self:
        """Enter a context manager.

        Returns:
            This store.
        """
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Close the connection on context exit.

        Args:
            exc_type: Exception type, if one was raised.
            exc_value: Exception instance, if one was raised.
            traceback: Traceback, if an exception was raised.
        """
        self.close()
```

- [ ] **Step 5: Run to verify it passes**

Run: `uv run pytest tests/test_store.py -n0 --no-cov -v`
Expected: PASS (7 tests)

- [ ] **Step 6: Run the full gate**

Run: `uv run ruff format && uv run ruff check && uv run ty check && uv run pytest --cov-fail-under=100`
Expected: all clean, coverage 100%.

- [ ] **Step 7: Commit**

```bash
git add src/pylbry/archive tests/test_store.py
git commit -m "Add SQLite archive store"
```

---

### Task 7: Archiver

Two phases, and reconcile-before-resume. Our database is always a lagging view of
the daemon's truth, because `get` returns before a download completes.

**Files:**
- Create: `src/pylbry/archive/archiver.py`
- Create: `tests/test_archiver.py`

**Interfaces:**
- Consumes: `Client`, `Store`, `DownloadState`, `Claim`.
- Produces: `ArchiveEvent(kind: str, claim_id: str, detail: str)`; `Archiver(client, root, *, workers=8, max_attempts=3, on_event=None)` with `.index_channel(channel_id) -> int`, `.reconcile() -> int`, `.fetch_pending(limit=None) -> dict[DownloadState, int]`, `.resume() -> dict[DownloadState, int]`, `.counts() -> dict[DownloadState, int]`, `.close() -> None`, context-manager support.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_archiver.py`:

```python
# ABOUTME: Tests for the two-phase archiver against a live lbrynet daemon.
# ABOUTME: Downloads mutate daemon state, so the module is pinned to a worker.
"""Tests for the two-phase archiver against a live lbrynet daemon."""

from pathlib import Path

import pytest

from pylbry.archive.archiver import ArchiveEvent, Archiver
from pylbry.archive.store import DownloadState
from pylbry.client import Client

pytestmark = [pytest.mark.live, pytest.mark.xdist_group("daemon_state")]


def test_index_channel_records_claims_without_downloading(
    client: Client, tmp_path: Path
) -> None:
    """The index phase persists claims and queues them as pending."""
    seed = client.claims.search(page_size=1, has_source=True).items[0]
    assert seed.channel_id is not None
    with Archiver(client, tmp_path) as archiver:
        indexed = archiver.index_channel(seed.channel_id)
        assert indexed > 0
        assert archiver.counts()[DownloadState.PENDING] == indexed


def test_fetch_pending_downloads_small_media(client: Client, tmp_path: Path) -> None:
    """The fetch phase downloads queued claims and records the outcome."""
    seed = client.claims.search(
        page_size=1, has_source=True, stream_types=["image"]
    ).items[0]
    with Archiver(client, tmp_path, workers=2) as archiver:
        archiver.store.upsert_claim(seed)
        results = archiver.fetch_pending()
        assert sum(results.values()) == 1
        assert archiver.store.state_of(seed.claim_id) in {
            DownloadState.COMPLETE,
            DownloadState.RUNNING,
            DownloadState.UNAVAILABLE,
            DownloadState.FAILED,
        }


def test_events_are_emitted_not_printed(
    client: Client, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The archiver reports progress through the callback and prints nothing."""
    seed = client.claims.search(page_size=1, has_source=True).items[0]
    events: list[ArchiveEvent] = []
    with Archiver(client, tmp_path, on_event=events.append) as archiver:
        archiver.store.upsert_claim(seed)
        archiver.fetch_pending()
    assert events
    assert capsys.readouterr().out == ""


def test_resume_reconciles_against_the_daemon(client: Client, tmp_path: Path) -> None:
    """Resume resets stale running rows and re-checks the daemon first."""
    seed = client.claims.search(page_size=1, has_source=True).items[0]
    with Archiver(client, tmp_path) as archiver:
        archiver.store.upsert_claim(seed)
        archiver.store.set_state(seed.claim_id, DownloadState.RUNNING)
        archiver.resume()
        assert archiver.store.state_of(seed.claim_id) is not DownloadState.RUNNING


def test_reconcile_marks_daemon_completed_downloads(
    client: Client, tmp_path: Path
) -> None:
    """Claims the daemon already finished are marked complete without refetching."""
    with Archiver(client, tmp_path) as archiver:
        completed = client.files.query(completed=True, page_size=1).items
        if not completed:
            pytest.fail(
                "no completed downloads on the daemon; run the fetch test first"
            )
        claim = client.claims.resolve(f"lbry://#{completed[0].claim_id}")
        archiver.store.upsert_claim(claim)
        assert archiver.reconcile() == 1
        assert archiver.store.state_of(claim.claim_id) is DownloadState.COMPLETE
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_archiver.py -n0 --no-cov -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pylbry.archive.archiver'`

- [ ] **Step 3: Write `src/pylbry/archive/archiver.py`**

```python
# ABOUTME: Two-phase channel archiving with durable, resumable state.
# ABOUTME: Indexes claims first, then fetches media through a bounded pool.
"""Two-phase channel archiving with durable, resumable state."""

import re
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import Self

from pylbry.archive.store import DownloadState, Store
from pylbry.client import Client
from pylbry.errors import OperationFailedError, PyLBRYError

UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


@dataclass(frozen=True, slots=True)
class ArchiveEvent:
    """Something the archiver did, reported to the caller."""

    kind: str
    claim_id: str
    detail: str


def _safe(name: str) -> str:
    """Reduce a name to characters safe for a filesystem path.

    Args:
        name: Arbitrary channel or claim name.

    Returns:
        The name with unsafe runs replaced by underscores.
    """
    return UNSAFE.sub("_", name).strip("_") or "unnamed"


class Archiver:
    """Archives a channel's claims and media into a durable local store."""

    def __init__(
        self,
        client: Client,
        root: Path,
        *,
        workers: int = 8,
        max_attempts: int = 3,
        on_event: Callable[[ArchiveEvent], None] | None = None,
    ) -> None:
        """Open an archive rooted at a directory.

        Args:
            client: Transport used for claim and file calls.
            root: Directory holding the database and media tree.
            workers: Concurrent download enqueues. The daemon performs the
                transfers, so this only hides dead-stream stalls.
            max_attempts: Attempts allowed per claim before abandoning it.
            on_event: Callback receiving progress events. The archiver never
                prints; rendering belongs to the caller.
        """
        self.root = root
        self.client = client
        self.workers = workers
        self.max_attempts = max_attempts
        self.store = Store(root / "pylbry.db")
        self._on_event = on_event

    def _emit(self, kind: str, claim_id: str, detail: str) -> None:
        """Report an event to the caller, if a callback was supplied.

        Args:
            kind: Short event name.
            claim_id: Claim the event concerns.
            detail: Human-readable detail.
        """
        if self._on_event is not None:
            self._on_event(ArchiveEvent(kind=kind, claim_id=claim_id, detail=detail))

    def index_channel(self, channel_id: str) -> int:
        """Record every claim in a channel without downloading media.

        Args:
            channel_id: Claim ID of the channel to index.

        Returns:
            The number of claims indexed.
        """
        indexed = 0
        for claim in self.client.claims.iter_channel(channel_id):
            self.store.upsert_claim(claim)
            indexed += 1
            self._emit("indexed", claim.claim_id, claim.name)
        return indexed

    def reconcile(self) -> int:
        """Mark claims the daemon has already finished as complete.

        A crashed run may have left downloads the daemon went on to finish, so
        the daemon is consulted before any work is re-queued.

        Returns:
            The number of claims marked complete.
        """
        marked = 0
        page = 1
        while True:
            listing = self.client.files.query(completed=True, page=page, page_size=50)
            for file_ref in listing.items:
                if self.store.state_of(file_ref.claim_id) in {
                    DownloadState.PENDING,
                    DownloadState.RUNNING,
                    DownloadState.FAILED,
                }:
                    self.store.set_state(
                        file_ref.claim_id,
                        DownloadState.COMPLETE,
                        path=file_ref.download_path,
                    )
                    marked += 1
                    self._emit("reconciled", file_ref.claim_id, "already complete")
            if len(listing.items) < listing.page_size:
                return marked
            page += 1

    def _fetch_one(self, claim_id: str) -> DownloadState:
        """Enqueue one claim's download and record the outcome.

        Args:
            claim_id: Claim to download.

        Returns:
            The state the claim ended in.
        """
        self.store.bump_attempts(claim_id)
        self.store.set_state(claim_id, DownloadState.RUNNING)
        claim = self.client.claims.resolve(f"lbry://#{claim_id}")
        directory = self.root / "media" / _safe(claim.channel_name or "unsigned")
        directory.mkdir(parents=True, exist_ok=True)
        try:
            file_ref = self.client.files.download(
                claim.permanent_url,
                download_directory=str(directory),
                file_name=f"{claim.claim_id}__{_safe(claim.name)}",
            )
        except OperationFailedError as exc:
            self.store.set_state(claim_id, DownloadState.UNAVAILABLE, error=str(exc))
            self._emit("unavailable", claim_id, exc.message)
            return DownloadState.UNAVAILABLE
        except PyLBRYError as exc:
            self.store.set_state(claim_id, DownloadState.FAILED, error=str(exc))
            self._emit("failed", claim_id, str(exc))
            return DownloadState.FAILED
        state = DownloadState.COMPLETE if file_ref.completed else DownloadState.RUNNING
        self.store.set_state(claim_id, state, path=file_ref.download_path)
        self._emit("fetched", claim_id, state)
        return state

    def fetch_pending(self, limit: int | None = None) -> dict[DownloadState, int]:
        """Download every claim still awaiting media.

        Args:
            limit: Maximum number of claims to attempt.

        Returns:
            A count of claims per resulting state.
        """
        claim_ids = self.store.pending(
            limit=limit or 10_000, max_attempts=self.max_attempts
        )
        tally: dict[DownloadState, int] = {}
        with ThreadPoolExecutor(max_workers=self.workers) as pool:
            for state in pool.map(self._fetch_one, claim_ids):
                tally[state] = tally.get(state, 0) + 1
        return tally

    def resume(self) -> dict[DownloadState, int]:
        """Reconcile against the daemon, then continue outstanding downloads.

        Returns:
            A count of claims per resulting state.
        """
        self.reconcile()
        self.store.reset_running()
        return self.fetch_pending()

    def counts(self) -> dict[DownloadState, int]:
        """Report how many claims sit in each state.

        Returns:
            A mapping of state to claim count.
        """
        return self.store.counts()

    def close(self) -> None:
        """Close the underlying store."""
        self.store.close()

    def __enter__(self) -> Self:
        """Enter a context manager.

        Returns:
            This archiver.
        """
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Close the store on context exit.

        Args:
            exc_type: Exception type, if one was raised.
            exc_value: Exception instance, if one was raised.
            traceback: Traceback, if an exception was raised.
        """
        self.close()
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_archiver.py -n0 --no-cov -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Run the full gate**

Run: `uv run ruff format && uv run ruff check && uv run ty check && uv run pytest --cov-fail-under=100`
Expected: all clean, coverage 100%.

- [ ] **Step 6: Commit**

```bash
git add src/pylbry/archive/archiver.py tests/test_archiver.py
git commit -m "Add two-phase archiver with reconcile and resume"
```

---

### Task 8: CLI

The only module permitted to print. Thin — it parses arguments, calls the public
API and renders events.

**Files:**
- Create: `src/pylbry/cli.py`
- Create: `tests/test_cli.py`

**Interfaces:**
- Consumes: `Client`, `Archiver`, `ArchiveEvent`, `DownloadState`.
- Produces: `build_parser() -> argparse.ArgumentParser`; `main(argv: Sequence[str] | None = None) -> int`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_cli.py`:

```python
# ABOUTME: Tests for the pyLBRY command line interface.
# ABOUTME: Parser tests need no daemon; command tests are marked live.
"""Tests for the pyLBRY command line interface."""

from pathlib import Path

import pytest

from pylbry.cli import build_parser, main


def test_parser_reads_archive_channel_arguments() -> None:
    """The archive channel command captures its URL and worker count."""
    args = build_parser().parse_args(
        ["archive", "channel", "lbry://@chan", "--workers", "4"]
    )
    assert args.command == "archive"
    assert args.url == "lbry://@chan"
    assert args.workers == 4


def test_parser_defaults_the_archive_root() -> None:
    """The archive root defaults to the current directory."""
    args = build_parser().parse_args(["status"])
    assert args.root == Path()


def test_parser_rejects_an_unknown_command() -> None:
    """An unrecognised command exits with a usage error."""
    with pytest.raises(SystemExit):
        build_parser().parse_args(["nonsense"])


def test_main_without_a_command_prints_help(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Running with no command prints usage and exits non-zero."""
    assert main([]) == 2
    assert "usage" in capsys.readouterr().out


@pytest.mark.live
@pytest.mark.xdist_group("daemon_state")
def test_status_reports_counts(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Status prints the archive's state counts."""
    assert main(["status", "--root", str(tmp_path)]) == 0
    assert "claims" in capsys.readouterr().out


@pytest.mark.live
@pytest.mark.xdist_group("daemon_state")
def test_resolve_prints_a_claim_title(capsys: pytest.CaptureFixture[str]) -> None:
    """Resolve prints the resolved claim's identity."""
    from pylbry.client import Client

    with Client() as client:
        url = client.claims.search(page_size=1, has_source=True).items[0].canonical_url
    assert main(["resolve", url]) == 0
    assert capsys.readouterr().out.strip()


@pytest.mark.live
@pytest.mark.xdist_group("daemon_state")
def test_resolve_reports_a_failure(capsys: pytest.CaptureFixture[str]) -> None:
    """Resolving an unknown URL prints an error and exits non-zero."""
    assert main(["resolve", "lbry://pylbry-does-not-exist-9f3a2b"]) == 1
    assert "error" in capsys.readouterr().err.lower()
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_cli.py -n0 --no-cov -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pylbry.cli'`

- [ ] **Step 3: Write `src/pylbry/cli.py`**

```python
# ABOUTME: Command line shell over the pyLBRY public API.
# ABOUTME: The only module permitted to print; rendering lives here alone.
"""Command line shell over the pyLBRY public API."""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from pylbry.archive.archiver import ArchiveEvent, Archiver
from pylbry.client import Client
from pylbry.errors import PyLBRYError


def build_parser() -> argparse.ArgumentParser:
    """Build the command line parser.

    Returns:
        A parser covering every pylbry command.
    """
    parser = argparse.ArgumentParser(prog="pylbry")
    parser.add_argument(
        "--endpoint", default="http://localhost:5279", help="lbrynet daemon URL"
    )
    parser.add_argument(
        "--root", type=Path, default=Path(), help="archive root directory"
    )
    commands = parser.add_subparsers(dest="command")

    archive = commands.add_parser("archive", help="archive claims and media")
    archive_commands = archive.add_subparsers(dest="subcommand", required=True)

    channel = archive_commands.add_parser("channel", help="archive a whole channel")
    channel.add_argument("url", help="channel URL or claim ID")
    channel.add_argument("--workers", type=int, default=8)
    channel.add_argument("--limit", type=int, default=None)

    archive_commands.add_parser("resume", help="continue an interrupted archive")

    commands.add_parser("status", help="report archive state counts")

    resolve = commands.add_parser("resolve", help="resolve a single URL")
    resolve.add_argument("url", help="LBRY URL to resolve")

    return parser


def _render(event: ArchiveEvent) -> None:
    """Print one archive event.

    Args:
        event: The event to render.
    """
    print(f"{event.kind:>12}  {event.claim_id[:8]}  {event.detail}")


def _archive(args: argparse.Namespace, client: Client) -> int:
    """Run an archive subcommand.

    Args:
        args: Parsed arguments.
        client: Connected daemon client.

    Returns:
        Process exit code.
    """
    with Archiver(
        client, args.root, workers=getattr(args, "workers", 8), on_event=_render
    ) as archiver:
        if args.subcommand == "resume":
            tally = archiver.resume()
        else:
            channel = client.claims.resolve(args.url)
            indexed = archiver.index_channel(channel.claim_id)
            print(f"indexed {indexed} claims")
            tally = archiver.fetch_pending(limit=args.limit)
        for state, count in sorted(tally.items()):
            print(f"{state}: {count}")
    return 0


def _status(args: argparse.Namespace) -> int:
    """Print archive state counts.

    Args:
        args: Parsed arguments.

    Returns:
        Process exit code.
    """
    from pylbry.archive.store import Store

    with Store(args.root / "pylbry.db") as store:
        print(f"claims: {store.claim_count()}")
        for state, count in sorted(store.counts().items()):
            print(f"{state}: {count}")
    return 0


def _resolve(args: argparse.Namespace, client: Client) -> int:
    """Resolve one URL and print its identity.

    Args:
        args: Parsed arguments.
        client: Connected daemon client.

    Returns:
        Process exit code.
    """
    claim = client.claims.resolve(args.url)
    print(f"{claim.claim_id}  {claim.claim_type}  {claim.title or claim.name}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command line interface.

    Args:
        argv: Argument vector, defaulting to ``sys.argv[1:]``.

    Returns:
        Process exit code.
    """
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 2
    if args.command == "status":
        return _status(args)
    try:
        with Client(args.endpoint) as client:
            if args.command == "archive":
                return _archive(args, client)
            return _resolve(args, client)
    except PyLBRYError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_cli.py -n0 --no-cov -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Run the full gate**

Run: `uv run ruff format && uv run ruff check && uv run ty check && uv run pytest --cov-fail-under=100`
Expected: all clean, coverage 100%. If any line in `cli.py` is uncovered, add a
test that drives it — do not add a `pragma`.

- [ ] **Step 6: Commit**

```bash
git add src/pylbry/cli.py tests/test_cli.py
git commit -m "Add command line interface"
```

---

### Task 9: Public API surface and final verification

**Files:**
- Modify: `src/pylbry/__init__.py`
- Modify: `README.md`
- Create: `tests/test_public_api.py`

**Interfaces:**
- Consumes: everything above.
- Produces: the documented public surface.

- [ ] **Step 1: Write the failing test**

Create `tests/test_public_api.py`:

```python
# ABOUTME: Guards the documented public API surface.
# ABOUTME: Prevents accidental removal or renaming of exported names.
"""Guards the documented public API surface."""

import pylbry


def test_public_api_exports_the_documented_names() -> None:
    """Every documented name is importable from the package root."""
    expected = {
        "ArchiveEvent",
        "Archiver",
        "Claim",
        "Client",
        "DaemonInternalError",
        "DaemonUnavailableError",
        "DownloadState",
        "FileRef",
        "InvalidParamsError",
        "MethodNotFoundError",
        "OperationFailedError",
        "Page",
        "PyLBRYError",
        "RPCError",
        "ResolveFailure",
        "Store",
    }
    assert set(pylbry.__all__) == expected
    for name in expected:
        assert hasattr(pylbry, name)
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_public_api.py -n0 --no-cov -v`
Expected: FAIL — `__all__` currently lists only the error classes.

- [ ] **Step 3: Rewrite `src/pylbry/__init__.py`**

```python
# ABOUTME: Public API for pyLBRY.
# ABOUTME: Re-exports the client, models, archiver and errors.
"""Public API for pyLBRY."""

from pylbry.archive.archiver import ArchiveEvent, Archiver
from pylbry.archive.store import DownloadState, Store
from pylbry.client import Client
from pylbry.errors import (
    DaemonInternalError,
    DaemonUnavailableError,
    InvalidParamsError,
    MethodNotFoundError,
    OperationFailedError,
    PyLBRYError,
    RPCError,
)
from pylbry.models import Claim, FileRef, Page, ResolveFailure

__all__ = [
    "ArchiveEvent",
    "Archiver",
    "Claim",
    "Client",
    "DaemonInternalError",
    "DaemonUnavailableError",
    "DownloadState",
    "FileRef",
    "InvalidParamsError",
    "MethodNotFoundError",
    "OperationFailedError",
    "Page",
    "PyLBRYError",
    "RPCError",
    "ResolveFailure",
    "Store",
]
```

- [ ] **Step 4: Extend `README.md` with usage**

Append:

```markdown
## Usage

    from pathlib import Path
    from pylbry import Archiver, Client

    with Client() as client:
        channel = client.claims.resolve("lbry://@example")
        with Archiver(client, Path("archive")) as archiver:
            archiver.index_channel(channel.claim_id)
            archiver.fetch_pending()

Or from the command line:

    pylbry archive channel lbry://@example --root archive
    pylbry archive resume --root archive
    pylbry status --root archive
```

- [ ] **Step 5: Run the full gate, in parallel this time**

Run: `uv run ruff format && uv run ruff check && uv run ty check && uv run pytest --cov-fail-under=100`
Expected: all clean, coverage 100%, xdist grouping keeps daemon-state tests serial.

- [ ] **Step 6: Verify the installed CLI entry point works**

Run: `uv run pylbry status --root /tmp/pylbry-check`
Expected: prints `claims: 0` and exits 0.

- [ ] **Step 7: Commit**

```bash
git add src/pylbry/__init__.py README.md tests/test_public_api.py
git commit -m "Export public API surface"
```

---

## Self-Review

**Spec coverage:**

| Spec section | Task |
| --- | --- |
| Layering and one dependency | 1 (config), enforced throughout |
| Error channels 1 and 2 | 2 |
| Error channel 3 (`{"error"}` in result) | 5 |
| Error channel 4 (per-item batch) | 4 |
| Unmapped codes fall through to `RPCError` | 2 (`_ERROR_CLASSES.get(code, RPCError)`) |
| Timeout inversion | 2 (`download_timeout`), 5 (passed to `get`) |
| Retries for idempotent reads | **Gap — see below** |
| `JSONValue`, no `Any` | 2 |
| Records with `raw` retained | 3 |
| Batch/single resolve split | 4 |
| `iter_channel` with `no_totals`/`has_source` | 4 |
| SQLite schema and states | 6 |
| `failed` vs `unavailable` | 6 (store), 7 (archiver classifies) |
| Reconcile before resume | 7 |
| Bounded pool, events not prints | 7, enforced by `T20` |
| Disk layout with `claim_id` prefix | 7 |
| CLI commands | 8 |
| Standards, gates, CI | 1 |
| Live-daemon testing, provocation table | 2, 4, 5 |
| `xdist_group` pinning | 5, 7, 8 |

**Known gap, deliberately deferred:** the spec calls for bounded retry with backoff on
connection errors and 5xx for idempotent reads. No task implements it. Adding it now
would introduce a branch that is hard to provoke against a healthy local daemon,
which conflicts with the 100% coverage rule. Recommend implementing it only when a
real failure motivates it, at which point the failure itself becomes the test. Raise
this with Ben rather than silently adding an untested retry loop.

**Placeholder scan:** no TBDs. Two judgement notes are marked inline (the unused
`monkeypatch` parameter in Task 2 Step 6, and the `tests/api/__init__.py` conditional
in Task 4) — both state the decision rather than deferring it.

**Type consistency:** `files.query` (never `list`) is used consistently in Tasks 5,
7 and 8. `DownloadState` members are referenced identically in Tasks 6, 7 and 8.
`Claim.from_dict`/`FileRef.from_dict` signatures match their call sites in Tasks 4
and 5. `ArchiveEvent(kind, claim_id, detail)` matches `_render` in Task 8.
