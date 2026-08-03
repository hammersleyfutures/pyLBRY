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
                    json.dumps(dict(claim.raw)),
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

        A path already recorded is kept when this call supplies none, so a
        later state change cannot erase where the media landed.

        Args:
            claim_id: Claim whose download state changes.
            state: The new state.
            path: Filesystem path of the downloaded media, when known.
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
                "UPDATE download SET attempts=attempts+1, updated_at=? "
                "WHERE claim_id=?",
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

    def path_of(self, claim_id: str) -> str | None:
        """Read where a claim's media was written.

        Args:
            claim_id: Claim to inspect.

        Returns:
            The recorded path, or None if there is none.
        """
        with self._lock:
            row = self._db.execute(
                "SELECT path FROM download WHERE claim_id=?", (claim_id,)
            ).fetchone()
        if row is None:
            return None
        return None if row[0] is None else str(row[0])

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
