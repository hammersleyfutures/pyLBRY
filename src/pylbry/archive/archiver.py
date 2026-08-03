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

from pylbry.archive.store import ArchiveTarget, DownloadState, Store
from pylbry.client import Client
from pylbry.errors import OperationFailedError, PyLBRYError

UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")
DEFAULT_WORKERS = 8
DEFAULT_MAX_ATTEMPTS = 3
RECONCILE_PAGE_SIZE = 50
UNFINISHED = frozenset(
    {DownloadState.PENDING, DownloadState.RUNNING, DownloadState.FAILED}
)


@dataclass(frozen=True, slots=True)
class ArchiveEvent:
    """Something the archiver did, reported to the caller."""

    kind: str
    claim_id: str
    detail: str


def safe_name(name: str) -> str:
    """Reduce a name to characters safe for a filesystem path.

    Args:
        name: Arbitrary channel or claim name.

    Returns:
        The name with unsafe runs replaced by underscores, never empty.
    """
    cleaned = UNSAFE.sub("_", name).strip("_")
    return cleaned or "unnamed"


class Archiver:
    """Archives a channel's claims and media into a durable local store."""

    def __init__(
        self,
        client: Client,
        root: Path,
        *,
        workers: int = DEFAULT_WORKERS,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
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

    def reconcile(self, *, page_size: int = RECONCILE_PAGE_SIZE) -> int:
        """Mark claims the daemon has already finished as complete.

        A crashed run may have left downloads the daemon went on to finish, so
        the daemon is consulted before any work is re-queued. Our database is
        always a lagging view of the daemon's truth, because a get returns
        before the transfer completes.

        Args:
            page_size: Files requested per file_list page.

        Returns:
            The number of claims marked complete.
        """
        marked = 0
        page = 1
        while True:
            listing = self.client.files.query(
                completed=True, page=page, page_size=page_size
            )
            for file_ref in listing.items:
                if self.store.state_of(file_ref.claim_id) in UNFINISHED:
                    self.store.set_state(
                        file_ref.claim_id,
                        DownloadState.COMPLETE,
                        path=file_ref.download_path,
                    )
                    marked += 1
                    self._emit("reconciled", file_ref.claim_id, "already complete")
            if len(listing.items) < page_size:
                return marked
            page += 1

    def _destination(self, target: ArchiveTarget) -> Path:
        """Build and create the directory a claim's media belongs in.

        Args:
            target: The claim being fetched.

        Returns:
            The directory to ask the daemon to write into.
        """
        directory = self.root / "media" / safe_name(target.channel_name or "unsigned")
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    def _fetch_one(self, claim_id: str) -> DownloadState:
        """Enqueue one claim's download and record the outcome.

        Args:
            claim_id: Claim to download.

        Returns:
            The state the claim ended in.
        """
        target = self.store.target_of(claim_id)
        self.store.bump_attempts(claim_id)
        self.store.set_state(claim_id, DownloadState.RUNNING)
        directory = self._destination(target)
        try:
            file_ref = self.client.files.download(
                target.permanent_url,
                download_directory=str(directory),
                file_name=f"{target.claim_id}__{safe_name(target.name)}",
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
            limit=limit if limit is not None else 10_000,
            max_attempts=self.max_attempts,
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
