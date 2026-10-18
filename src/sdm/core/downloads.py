"""What a download is, as stored in the history and shown in the window.

States and the moves allowed between them (M3; M4 adds pausing and resuming):

    queued ──▶ downloading ──▶ completed
       │            │
       ├────────────┼──▶ failed
       ├────────────┼──▶ cancelled
       └────────────┴──▶ interrupted   (SDM was closed or crashed mid-download)

Finished states are final: downloading the same URL again creates a new entry.
"""

from dataclasses import dataclass
from enum import StrEnum


class DownloadState(StrEnum):
    QUEUED = "queued"  # waiting for a free slot (at most 3 run at once)
    DOWNLOADING = "downloading"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"

    @property
    def is_active(self) -> bool:
        return self in (DownloadState.QUEUED, DownloadState.DOWNLOADING)


ALLOWED_TRANSITIONS: dict[DownloadState, frozenset[DownloadState]] = {
    DownloadState.QUEUED: frozenset(
        {
            DownloadState.DOWNLOADING,
            DownloadState.FAILED,
            DownloadState.CANCELLED,
            DownloadState.INTERRUPTED,
        }
    ),
    DownloadState.DOWNLOADING: frozenset(
        {
            DownloadState.COMPLETED,
            DownloadState.FAILED,
            DownloadState.CANCELLED,
            DownloadState.INTERRUPTED,
        }
    ),
    DownloadState.COMPLETED: frozenset(),
    DownloadState.FAILED: frozenset(),
    DownloadState.CANCELLED: frozenset(),
    DownloadState.INTERRUPTED: frozenset(),
}


def check_transition(old: DownloadState, new: DownloadState) -> None:
    """Raise ValueError if a download may not move from `old` to `new`."""
    if new not in ALLOWED_TRANSITIONS[old]:
        raise ValueError(f"A download can't go from {old} to {new}.")


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
