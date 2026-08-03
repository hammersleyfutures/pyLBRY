# ABOUTME: Claim resolution, search and channel enumeration.
# ABOUTME: Batch resolve records per-URL failures instead of raising.
"""Claim resolution, search and channel enumeration."""

from collections.abc import Iterable, Iterator, Mapping, Sequence
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


def _error_message(error: Mapping[str, JSONValue]) -> str:
    """Extract a human-readable message from a resolve error entry.

    Args:
        error: The ``error`` object from a resolve result.

    Returns:
        The daemon's message text.
    """
    return as_str(error.get("text") or error.get("name") or "resolve failed")


def unseen(claims: Iterable[Claim], seen: set[str]) -> Iterator[Claim]:
    """Yield only claims not already seen, recording each one.

    Paged claim searches can return the same claim twice: the daemon offers no
    unique sort key, so claims tied on the sort field can shuffle between page
    requests.

    Args:
        claims: Claims from one page of results.
        seen: Claim IDs already yielded. Updated in place.

    Yields:
        Each claim whose ID had not been seen before.
    """
    for claim in claims:
        if claim.claim_id in seen:
            continue
        seen.add(claim.claim_id)
        yield claim


class ClaimsAPI:
    """Claim reads: resolution, search and channel enumeration."""

    def __init__(self, client: Client) -> None:
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
            **filters: Additional claim_search filters, such as ``has_source``
                or ``channel_ids``.

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

        Results are ordered by height so paging is as stable as the daemon
        allows, and duplicates are filtered. The daemon exposes no unique sort
        key -- 'name', 'height' and 'amount' all have ties -- so a claim
        published while paging can still be missed. Re-running the index is
        idempotent and picks up stragglers.

        Args:
            channel_id: Claim ID of the channel.
            has_source: Restrict to claims that have downloadable content.
            page_size: Claims requested per page.

        Yields:
            Each distinct claim in the channel.
        """
        seen: set[str] = set()
        page = 1
        while True:
            result = self.search(
                page=page,
                page_size=page_size,
                channel_ids=[channel_id],
                has_source=has_source,
                order_by="height",
                no_totals=True,
            )
            yield from unseen(result.items, seen)
            if len(result.items) < page_size:
                return
            page += 1
