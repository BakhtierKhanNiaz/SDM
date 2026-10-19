"""The download history, stored in SQLite (Python's built-in sqlite3 module).

One DownloadStore owns one connection and must be used from a single thread: the window's
main thread. The schema version lives in SQLite's `PRAGMA user_version`; each entry in
_MIGRATIONS upgrades the database by one version, so later milestones can add columns without
losing history.

If the file is corrupted, it is renamed (never deleted) to "sdm.db.corrupt-<time>" and a fresh
database is started; `recovered_from` then names the renamed file so the window can say so.
"""

import logging
import os
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from sdm.core.categories import category_for
from sdm.core.downloads import (
    BrowserContext,
    DownloadRecord,
    DownloadState,
    PartialDownload,
    check_transition,
)
from sdm.core.errors import SDMError
from sdm.core.paths import app_data_dir
from sdm.core.segments import encode_segments

log = logging.getLogger(__name__)

_MIGRATIONS = [
    # Version 1 (M3)
    """
    CREATE TABLE downloads (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        url                 TEXT    NOT NULL,
        folder              TEXT    NOT NULL,
        allow_local_network INTEGER NOT NULL DEFAULT 0,
        state               TEXT    NOT NULL CHECK (state IN
            ('queued', 'downloading', 'completed', 'failed', 'cancelled', 'interrupted')),
        file_name           TEXT,
        path                TEXT,
        total_bytes         INTEGER,
        received_bytes      INTEGER NOT NULL DEFAULT 0,
        verified_complete   INTEGER,
        error               TEXT,
        created_at          TEXT    NOT NULL,
        updated_at          TEXT    NOT NULL,
        finished_at         TEXT
    );
    CREATE INDEX downloads_by_url ON downloads (url);
    """,
    # Version 2 (M4): the 'paused' state and what resuming needs. SQLite can't change a CHECK
    # constraint in place, so the table is rebuilt and every row copied, ids included.
    """
    CREATE TABLE downloads_v2 (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        url                 TEXT    NOT NULL,
        folder              TEXT    NOT NULL,
        allow_local_network INTEGER NOT NULL DEFAULT 0,
        state               TEXT    NOT NULL CHECK (state IN ('queued', 'downloading',
            'paused', 'completed', 'failed', 'cancelled', 'interrupted')),
        file_name           TEXT,
        path                TEXT,
        total_bytes         INTEGER,
        received_bytes      INTEGER NOT NULL DEFAULT 0,
        verified_complete   INTEGER,
        error               TEXT,
        created_at          TEXT    NOT NULL,
        updated_at          TEXT    NOT NULL,
        finished_at         TEXT,
        part_path           TEXT,
        etag                TEXT,
        last_modified       TEXT,
        resumable           INTEGER NOT NULL DEFAULT 0
    );
    INSERT INTO downloads_v2 (id, url, folder, allow_local_network, state, file_name, path,
        total_bytes, received_bytes, verified_complete, error, created_at, updated_at,
        finished_at)
    SELECT id, url, folder, allow_local_network, state, file_name, path, total_bytes,
        received_bytes, verified_complete, error, created_at, updated_at, finished_at
    FROM downloads;
    DROP TABLE downloads;
    ALTER TABLE downloads_v2 RENAME TO downloads;
    CREATE INDEX downloads_by_url ON downloads (url);
    """,
    # Version 3 (M5): which byte ranges of a split download have arrived (JSON).
    """
    ALTER TABLE downloads ADD COLUMN segments TEXT;
    """,
    # Version 4 (M6): the queue, categories, automatic retries, and settings.
    """
    ALTER TABLE downloads ADD COLUMN queue_position INTEGER NOT NULL DEFAULT 0;
    ALTER TABLE downloads ADD COLUMN category TEXT NOT NULL DEFAULT 'General';
    ALTER TABLE downloads ADD COLUMN retry_count INTEGER NOT NULL DEFAULT 0;
    ALTER TABLE downloads ADD COLUMN retry_at TEXT;
    ALTER TABLE downloads ADD COLUMN forced INTEGER NOT NULL DEFAULT 0;
    UPDATE downloads SET queue_position = id;
    CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
    """,
    # Version 5 (M8): what the browser told SDM about a download it handed over.
    """
    ALTER TABLE downloads ADD COLUMN referrer TEXT;
    ALTER TABLE downloads ADD COLUMN suggested_name TEXT;
    """,
    # Version 6 (M9): checking a finished file against its published SHA-256.
    """
    ALTER TABLE downloads ADD COLUMN expected_sha256 TEXT;
    ALTER TABLE downloads ADD COLUMN checksum_state TEXT;
    """,
]
SCHEMA_VERSION = len(_MIGRATIONS)
_DONE = {"forced": 0, "retry_at": None}  # leaving the queue for good
_NO_PARTIAL = {
    "part_path": None,
    "etag": None,
    "last_modified": None,
    "resumable": 0,
    "segments": None,
}

INTERRUPTED_MESSAGE = "SDM was closed before this download finished."


class StorageError(SDMError):
    """The history database can't be used."""


def default_database_path() -> Path:
    """%LOCALAPPDATA%\\SDM\\sdm.db: per-user, outside Controlled Folder Access's folders."""
    return app_data_dir() / "sdm.db"


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class DownloadStore:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.recovered_from: Path | None = None
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._conn = self._open()
        except sqlite3.DatabaseError as exc:  # "file is not a database", "malformed", ...
            log.warning("History database is unreadable (%s); starting a fresh one", exc)
            self.recovered_from = self._set_aside_corrupt_file()
            self._conn = self._open()

    def _open(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        try:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode = WAL")  # survives crashes mid-write better
            conn.execute("PRAGMA synchronous = NORMAL")
            if conn.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise sqlite3.DatabaseError("integrity check failed")
            self._migrate(conn)
        except BaseException:
            conn.close()
            raise
        return conn

    def _migrate(self, conn: sqlite3.Connection) -> None:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        if version > SCHEMA_VERSION:
            raise StorageError(
                f"The history database at {self.path} was made by a newer version of SDM."
            )
        for number in range(version, SCHEMA_VERSION):
            with conn:  # one transaction per step: a failed upgrade changes nothing
                conn.executescript(f"BEGIN; {_MIGRATIONS[number]}")
                if number + 1 == 4:  # label existing entries from their file names (M6)
                    rows = conn.execute("SELECT id, file_name FROM downloads").fetchall()
                    for download_id, file_name in rows:
                        conn.execute(
                            "UPDATE downloads SET category = ? WHERE id = ?",
                            (category_for(file_name), download_id),
                        )
                conn.execute(f"PRAGMA user_version = {number + 1}")

    def _set_aside_corrupt_file(self) -> Path:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        target = self.path.with_name(f"{self.path.name}.corrupt-{stamp}")
        os.replace(self.path, target)
        for suffix in ("-wal", "-shm"):  # SQLite's side files belong to the old database
            side = self.path.with_name(self.path.name + suffix)
            if side.exists():
                os.replace(side, target.with_name(target.name + suffix))
        return target

    def close(self) -> None:
        self._conn.close()

    # ----- reading -----

    def get(self, download_id: int) -> DownloadRecord | None:
        row = self._conn.execute("SELECT * FROM downloads WHERE id = ?", (download_id,)).fetchone()
        return _record(row) if row else None

    def list_all(self) -> list[DownloadRecord]:
        rows = self._conn.execute("SELECT * FROM downloads ORDER BY queue_position, id").fetchall()
        return [_record(row) for row in rows]

    def completed_with_url(self, url: str) -> list[DownloadRecord]:
        """Earlier finished downloads of the same URL (for the "already downloaded" warning)."""
        rows = self._conn.execute(
            "SELECT * FROM downloads WHERE url = ? AND state = ? ORDER BY id",
            (url, DownloadState.COMPLETED),
        ).fetchall()
        return [_record(row) for row in rows]

    # ----- writing -----

    def add(
        self,
        url: str,
        folder: str,
        *,
        allow_local_network: bool = False,
        start: bool = True,
        category: str = "General",
        context: BrowserContext | None = None,
        expected_sha256: str | None = None,
    ) -> DownloadRecord:
        """A new entry at the end of the queue; `start=False` adds it paused (M6).

        `context` keeps what the browser said about it (M8), so a resume sends the same Referer.
        """
        now = _now()
        context = context or BrowserContext()
        state = DownloadState.QUEUED if start else DownloadState.PAUSED
        with self._conn:
            (last,) = self._conn.execute(
                "SELECT COALESCE(MAX(queue_position), 0) FROM downloads"
            ).fetchone()
            cursor = self._conn.execute(
                "INSERT INTO downloads (url, folder, allow_local_network, state, created_at,"
                " updated_at, queue_position, category, referrer, suggested_name,"
                " expected_sha256) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    url,
                    folder,
                    int(allow_local_network),
                    state,
                    now,
                    now,
                    last + 1,
                    category,
                    context.referrer,
                    context.suggested_name,
                    expected_sha256,
                ),
            )
        record = self.get(cursor.lastrowid)
        if record is None:
            raise StorageError("The new history entry could not be read back.")
        return record

    def set_checksum(
        self, download_id: int, expected_sha256: str | None, state: str | None
    ) -> None:
        """The SHA-256 to check against and the result so far (M9)."""
        self._update(download_id, expected_sha256=expected_sha256, checksum_state=state)

    def set_file_info(self, download_id: int, file_name: str, total_bytes: int | None) -> None:
        self._update(download_id, file_name=file_name, total_bytes=total_bytes)

    def set_progress(self, download_id: int, received_bytes: int) -> None:
        self._update(download_id, received_bytes=received_bytes)

    def set_partial(self, download_id: int, partial: PartialDownload) -> None:
        """Remember the partial file and the server's version tags, for resuming."""
        self._update(
            download_id,
            part_path=str(partial.part_path),
            file_name=partial.file_name,
            total_bytes=partial.total_bytes,
            etag=partial.etag,
            last_modified=partial.last_modified,
            resumable=int(partial.resumable),
            segments=encode_segments(partial.segments) if partial.segments else None,
        )

    def set_category(self, download_id: int, category: str) -> None:
        self._update(download_id, category=category)

    def set_forced(self, download_id: int, forced: bool) -> None:
        self._update(download_id, forced=int(forced))

    def set_retry(self, download_id: int, count: int, at: str | None) -> None:
        self._update(download_id, retry_count=count, retry_at=at)

    def set_positions(self, order: list[int]) -> None:
        """Renumber the given entries in this order, keeping them where they were overall."""
        positions = sorted(
            row[0]
            for row in self._conn.execute(
                f"SELECT queue_position FROM downloads WHERE id IN ({','.join('?' * len(order))})",  # noqa: S608
                order,
            )
        )
        with self._conn:
            for download_id, position in zip(order, positions, strict=True):
                self._conn.execute(
                    "UPDATE downloads SET queue_position = ? WHERE id = ?", (position, download_id)
                )

    def get_setting(self, key: str) -> str | None:
        row = self._conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row[0] if row else None

    def set_setting(self, key: str, value: str) -> None:
        with self._conn:
            self._conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?)"
                " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )

    def mark_downloading(self, download_id: int) -> None:
        self._move(download_id, DownloadState.DOWNLOADING)

    def mark_queued(self, download_id: int) -> None:
        """Resume a paused or interrupted entry, or retry a failed one."""
        self._move(download_id, DownloadState.QUEUED, error=None, finished_at=None)

    def mark_paused(self, download_id: int) -> None:
        self._move(download_id, DownloadState.PAUSED, error=None)

    def mark_completed(
        self, download_id: int, *, path: str, size: int, verified_complete: bool
    ) -> None:
        self._move(
            download_id,
            DownloadState.COMPLETED,
            path=path,
            file_name=Path(path).name,  # may include a " (1)" added at the end
            received_bytes=size,
            verified_complete=int(verified_complete),
            error=None,
            **_NO_PARTIAL,
            **_DONE,
        )

    def mark_failed(self, download_id: int, error: str, *, partial_kept: bool = False) -> None:
        """Failed. The partial file stays recorded only if it was kept for a later retry."""
        extra = {} if partial_kept else _NO_PARTIAL
        self._move(download_id, DownloadState.FAILED, error=error, **extra)

    def mark_cancelled(self, download_id: int) -> None:
        self._move(download_id, DownloadState.CANCELLED, **_NO_PARTIAL, **_DONE)

    def mark_interrupted_on_startup(self) -> int:
        """Entries a crash or forced exit left queued or downloading become "interrupted".

        Returns how many changed. Their partial files stay recorded, so they can be resumed.
        """
        now = _now()
        with self._conn:
            cursor = self._conn.execute(
                "UPDATE downloads SET state = ?, error = ?, updated_at = ?, finished_at = ?"
                " WHERE state IN (?, ?)",
                (
                    DownloadState.INTERRUPTED,
                    INTERRUPTED_MESSAGE,
                    now,
                    now,
                    DownloadState.QUEUED,
                    DownloadState.DOWNLOADING,
                ),
            )
        return cursor.rowcount

    def remove(self, download_id: int) -> None:
        """Remove an entry from the history. The downloaded file itself is not touched."""
        record = self.get(download_id)
        if record and record.state.is_active:
            raise ValueError("Cancel the download before removing it from the list.")
        with self._conn:
            self._conn.execute("DELETE FROM downloads WHERE id = ?", (download_id,))

    def _move(self, download_id: int, new_state: DownloadState, **fields: object) -> None:
        record = self.get(download_id)
        if record is None:
            raise KeyError(download_id)
        check_transition(record.state, new_state)
        if not new_state.is_active:
            fields.setdefault("finished_at", _now())  # for paused: when it stopped
        self._update(download_id, state=new_state, **fields)

    def _update(self, download_id: int, **fields: object) -> None:
        fields["updated_at"] = _now()
        # Column names come only from this module's own keyword arguments, never from input.
        assignments = ", ".join(f"{name} = ?" for name in fields)
        with self._conn:
            self._conn.execute(
                f"UPDATE downloads SET {assignments} WHERE id = ?",  # noqa: S608
                (*fields.values(), download_id),
            )


def _record(row: sqlite3.Row) -> DownloadRecord:
    verified = row["verified_complete"]
    return DownloadRecord(
        id=row["id"],
        url=row["url"],
        folder=row["folder"],
        allow_local_network=bool(row["allow_local_network"]),
        state=DownloadState(row["state"]),
        file_name=row["file_name"],
        path=row["path"],
        total_bytes=row["total_bytes"],
        received_bytes=row["received_bytes"],
        verified_complete=None if verified is None else bool(verified),
        error=row["error"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        finished_at=row["finished_at"],
        part_path=row["part_path"],
        etag=row["etag"],
        last_modified=row["last_modified"],
        resumable=bool(row["resumable"]),
        segments=row["segments"],
        queue_position=row["queue_position"],
        category=row["category"],
        retry_count=row["retry_count"],
        retry_at=row["retry_at"],
        forced=bool(row["forced"]),
        referrer=row["referrer"],
        suggested_name=row["suggested_name"],
        expected_sha256=row["expected_sha256"],
        checksum_state=row["checksum_state"],
    )
