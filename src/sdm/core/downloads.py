"""What a download is, as stored in the history and shown in the window.

States and the moves allowed between them (M4):

    queued ──▶ downloading ──▶ completed
      ▲ │           │
      │ ├───────────┼──▶ paused ──────┐     (partial file kept)
      │ ├───────────┼──▶ failed ──────┤     (partial kept only if the server can resume)
      │ ├───────────┼──▶ interrupted ─┤     (SDM was closed or crashed mid-download)
      │ └───────────┴──▶ cancelled    │     (partial file deleted)
      └───────────────────────────────┘     resume / retry: back to queued

Paused, failed and interrupted entries can also be cancelled, which discards their partial
file. Completed and cancelled are final: downloading the same URL again creates a new entry.
"""

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from sdm.core.segments import Segment, decode_segments


class DownloadState(StrEnum):
    QUEUED = "queued"  # waiting for a free slot (at most 3 run at once)
    DOWNLOADING = "downloading"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"

    @property
    def is_active(self) -> bool:
        """Running or waiting to run: the engine owns it."""
        return self in (DownloadState.QUEUED, DownloadState.DOWNLOADING)

    @property
    def can_resume(self) -> bool:
        return self in (DownloadState.PAUSED, DownloadState.FAILED, DownloadState.INTERRUPTED)


S = DownloadState
ALLOWED_TRANSITIONS: dict[DownloadState, frozenset[DownloadState]] = {
    S.QUEUED: frozenset({S.DOWNLOADING, S.PAUSED, S.FAILED, S.CANCELLED, S.INTERRUPTED}),
    S.DOWNLOADING: frozenset({S.COMPLETED, S.PAUSED, S.FAILED, S.CANCELLED, S.INTERRUPTED}),
    S.PAUSED: frozenset({S.QUEUED, S.CANCELLED}),
    S.FAILED: frozenset({S.QUEUED, S.CANCELLED}),
    S.INTERRUPTED: frozenset({S.QUEUED, S.CANCELLED}),
    S.COMPLETED: frozenset(),
    S.CANCELLED: frozenset(),
}


def check_transition(old: DownloadState, new: DownloadState) -> None:
    """Raise ValueError if a download may not move from `old` to `new`."""
    if new not in ALLOWED_TRANSITIONS[old]:
        raise ValueError(f"A download can't go from {old} to {new}.")


@dataclass(frozen=True)
class BrowserContext:
    """What the browser knew about a download it handed over (M8, ADR-0015).

    Both values are untrusted. The referrer is sent as a Referer header under the browser's
    rules (sdm.core.referrer); the suggested name is used only when the server names no file,
    and is sanitized like any other file name. Cookies are never part of it.
    """

    referrer: str | None = None  # the page the link was on; may hold tokens: never log it
    suggested_name: str | None = None  # a bare file name, never a path


@dataclass(frozen=True)
class PartialDownload:
    """What SDM remembers about an unfinished download, so it can continue it later."""

    part_path: Path  # the "<name>.sdmpart" file in the download folder
    file_name: str  # the name chosen when the download started
    total_bytes: int | None
    etag: str | None  # the server's version tags for the file, used with If-Range
    last_modified: str | None
    resumable: bool  # the server advertised (Accept-Ranges: bytes) or proved (206) it can resume
    # M5: for a download split across connections, which byte ranges have arrived. None means
    # the partial file is a plain prefix: its size is how much arrived (M4).
    segments: tuple[Segment, ...] | None = None


@dataclass(frozen=True)
class DownloadRecord:
    """One row of the download history."""

    id: int
    url: str  # full URL, may contain access tokens: never log it (use redact_url)
    folder: str
    allow_local_network: bool
    state: DownloadState
    file_name: str | None  # known once the server has answered
    path: str | None  # where the finished file was saved
    total_bytes: int | None  # None when the server doesn't say
    received_bytes: int
    verified_complete: bool | None
    error: str | None
    created_at: str  # ISO 8601, UTC
    updated_at: str
    finished_at: str | None
    part_path: str | None = None  # the partial file while unfinished (M4)
    etag: str | None = None
    last_modified: str | None = None
    resumable: bool = False
    segments: str | None = None  # the saved parts map (JSON), for split downloads (M5)
    queue_position: int = 0  # order in the queue, smaller first (M6)
    category: str = "General"  # from the file type (M6)
    retry_count: int = 0  # automatic retries used (M6)
    retry_at: str | None = None  # ISO 8601 UTC: waiting for an automatic retry until then
    forced: bool = False  # "Start now": ignores the limit and the schedule
    referrer: str | None = None  # from the browser (M8); may hold tokens: never log it
    suggested_name: str | None = None  # the browser's file name, used if the server gives none
    expected_sha256: str | None = None  # what the publisher says the file's SHA-256 is (M9)
    checksum_state: str | None = None  # checking, verified, mismatch or missing (M9)

    def context(self) -> BrowserContext | None:
        """The browser's hints for this download, if it came from the browser."""
        if self.referrer is None and self.suggested_name is None:
            return None
        return BrowserContext(self.referrer, self.suggested_name)

    def partial(self) -> PartialDownload | None:
        """What the engine needs to continue this download, if a partial file is recorded."""
        if not self.part_path or not self.file_name:
            return None
        segments = decode_segments(self.segments, self.total_bytes) if self.segments else None
        if self.segments and segments is None:
            # A damaged map can't say which parts arrived: treating the file as complete or as
            # a prefix could produce a file with holes. Start over instead.
            return None
        return PartialDownload(
            part_path=Path(self.part_path),
            file_name=self.file_name,
            total_bytes=self.total_bytes,
            etag=self.etag,
            last_modified=self.last_modified,
            resumable=self.resumable,
            segments=segments,
        )
