# ABOUTME: JSON value type, narrowing helpers and frozen record types.
# ABOUTME: Narrowing turns untyped daemon JSON into typed values without Any.
"""JSON value type, narrowing helpers and frozen record types."""

from collections.abc import Mapping
from dataclasses import dataclass

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
    raw: Mapping[str, JSONValue]

    @classmethod
    def from_dict(cls, data: Mapping[str, JSONValue]) -> Claim:
        """Build a claim from a daemon payload.

        The stream size arrives as a string, not a number, so it is parsed
        rather than narrowed.

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
    def from_dict(cls, data: Mapping[str, JSONValue]) -> FileRef:
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
