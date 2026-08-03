# ABOUTME: Download enqueueing and file listing.
# ABOUTME: A get returns after the first blob is written, not on completion.
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

    def __init__(self, client: Client) -> None:
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

        The daemon returns as soon as the first blob reaches disk; the rest of
        the transfer continues in the background. Poll :meth:`query` to observe
        completion.

        ``save_file`` is always sent as true. The daemon's own ``save_files``
        setting defaults to false, and without it the daemon fetches blobs but
        writes no file at all, reporting a null download path.

        ``download_directory`` is a request, not a guarantee. If the daemon
        already holds the stream it returns the existing file at its original
        location and ignores the requested directory, so callers must record
        the returned ``download_path`` rather than assume where they asked for
        the file to go.

        Args:
            uri: LBRY URL of the stream.
            download_directory: Directory the daemon should write into, when it
                does not already hold the stream.
            file_name: Filename to use instead of the stream's own.
            timeout: Download timeout in seconds passed to the daemon.

        Returns:
            A reference to the file the daemon is writing.

        Raises:
            OperationFailedError: If the daemon reports a failure in-result.
        """
        params: dict[str, JSONValue] = {"uri": uri, "save_file": True}
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
