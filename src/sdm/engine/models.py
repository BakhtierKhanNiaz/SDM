"""Data passed into and out of the download engine."""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from sdm import __version__
from sdm.core.downloads import PartialDownload

# Called as on_progress(bytes_received, total_bytes); total is None when the size is unknown.
ProgressCallback = Callable[[int, int | None], None]
# Called as on_file_info(file_name, total_bytes) once the server has answered, before any data
# arrives. The final name can still gain a " (1)" suffix if the file already exists by then.
FileInfoCallback = Callable[[str, int | None], None]
# Called with what is needed to resume, each time an attempt has its partial file ready.
PartialCallback = Callable[[PartialDownload], None]


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
    # Splitting a download across connections (M5, ADR-0012).
    max_connections: int = 8  # as IDM used in OBS-001
    min_split_size: int = 2 * 1024 * 1024  # smaller files use one connection
    min_part_size: int = 1024 * 1024
    dynamic_splitting: bool = True  # free connections take over half of the biggest part (M5b)
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
