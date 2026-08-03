# ABOUTME: Guards the documented public API surface.
# ABOUTME: Prevents accidental removal or renaming of exported names.
"""Guards the documented public API surface."""

from __future__ import annotations

import pylbry

EXPECTED = {
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


def test_public_api_exports_the_documented_names() -> None:
    """Every documented name is importable from the package root."""
    assert set(pylbry.__all__) == EXPECTED
    for name in EXPECTED:
        assert hasattr(pylbry, name)


def test_public_api_is_sorted() -> None:
    """The export list stays sorted so diffs stay readable."""
    assert pylbry.__all__ == sorted(pylbry.__all__)
