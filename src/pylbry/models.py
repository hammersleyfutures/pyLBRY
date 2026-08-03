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

    Booleans are rejected: they are a subclass of int in Python, and the daemon
    never means one where an integer is expected.

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
