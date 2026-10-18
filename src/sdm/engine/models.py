"""Data passed into and out of the download engine."""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from sdm import __version__

# Called as on_progress(bytes_received, total_bytes); total is None when the size is unknown.
ProgressCallback = Callable[[int, int | None], None]


@dataclass(frozen=True)
class DownloadSettings:
    """Tunable limits for one download. Defaults are for real use; tests shrink them."""

    connect_timeout: float = 15.0  # seconds to look up the server and connect
    read_timeout: float = 30.0  # seconds the server may stay silent mid-download
    max_attempts: int = 3  # first try plus retries
    backoff_base: float = 1.0  # waits 1 s, 2 s, 4 s ... between attempts
    max_retry_after: float = 60.0  # cap on a server's Retry-After request
    max_redirects: int = 10
    chunk_size: int = 64 * 1024
    user_agent: str = f"SDM/{__version__}"


@dataclass(frozen=True)
class DownloadResult:
    """A finished download."""

    path: Path  # where the file was saved
    size: int  # bytes written
    final_url: str  # URL after redirects (may contain tokens: redact before logging)
    content_type: str | None
    # True when the server marked where the file ends (Content-Length or chunked encoding) and
    # every byte arrived. False when it only closed the connection: a connection that dropped
    # early looks exactly like a finished download, so completeness can't be confirmed.
    verified_complete: bool
