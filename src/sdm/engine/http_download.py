"""Single-connection HTTP/HTTPS download (M2).

One attempt: check the URL -> GET, following redirects by hand so every hop is re-checked ->
check the status -> choose a filename -> stream into "<name>.sdmpart" -> verify the size ->
rename to the final name without ever replacing an existing file. When the server gives no
size, the result says that completeness couldn't be confirmed. Failed attempts that might
succeed later (timeouts, 5xx, dropped connections) are retried from the start; resuming from
the middle of a file comes in M4.
"""

import asyncio
import contextlib
import email.utils
import errno
import logging
import os
import shutil
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO
from urllib.parse import urljoin, urlsplit

import aiohttp

from sdm.core.errors import DownloadError, InvalidURLError, SDMError
from sdm.core.filenames import (
    filename_from_content_disposition,
    filename_from_url,
    numbered_name,
    sanitize_filename,
)
from sdm.core.units import format_size
from sdm.core.urls import redact_url, validate_url
from sdm.engine.models import (
    DownloadResult,
    DownloadSettings,
    FileInfoCallback,
    ProgressCallback,
)
from sdm.engine.policy import NetworkPolicy, PolicyResolver

log = logging.getLogger(__name__)

PART_SUFFIX = ".sdmpart"
MAX_NAME_VARIANTS = 1000  # "name.ext" through "name (999).ext"
WINDOWS_MAX_PATH = 259  # characters in a full path, excluding the terminating NUL
_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
_RETRYABLE_STATUSES = frozenset({408, 429})
_WINERROR_DISK_FULL = frozenset({39, 112})
_WINERROR_PATH_TOO_LONG = 206


async def download(
    url: str,
    destination_dir: str | os.PathLike[str],
    *,
    policy: NetworkPolicy | None = None,
    settings: DownloadSettings | None = None,
    on_progress: ProgressCallback | None = None,
    on_file_info: FileInfoCallback | None = None,
) -> DownloadResult:
    """Download `url` into `destination_dir` and return where the file was saved.

    Raises an SDMError subclass (InvalidURLError, BlockedDestinationError, DownloadError)
    whose message is fit to show the user. Cancelling the task stops the download promptly
    and deletes the partial file.
    """
    url = url.strip()
    validate_url(url)
    policy = policy or NetworkPolicy()
    settings = settings or DownloadSettings()
    directory = Path(destination_dir)
    if not directory.is_dir():
        raise DownloadError(f"The download folder does not exist: {directory}")

    log.info("Downloading %s into %s", redact_url(url), directory)
    timeout = aiohttp.ClientTimeout(
        total=None,  # large files may legitimately take hours
        connect=settings.connect_timeout,
        sock_connect=settings.connect_timeout,
        sock_read=settings.read_timeout,
    )
    session = aiohttp.ClientSession(
        connector=aiohttp.TCPConnector(resolver=PolicyResolver(policy)),
        timeout=timeout,
        # "identity" asks for the file exactly as stored, so sizes match Content-Length.
        headers={"User-Agent": settings.user_agent, "Accept-Encoding": "identity"},
        auto_decompress=False,
        trust_env=False,  # ignore proxy environment variables: a proxy would bypass the policy
    )
    async with session:
        attempt = 1
        while True:
            try:
                result = await _attempt(
                    session, url, directory, policy, settings, on_progress, on_file_info
                )
            except DownloadError as exc:
                if not exc.retryable or attempt >= settings.max_attempts:
                    raise
                delay = exc.retry_after
                if delay is None:
                    delay = settings.backoff_base * 2 ** (attempt - 1)
                delay = min(delay, settings.max_retry_after)
                log.warning(
                    "Attempt %d of %d failed (%s); retrying in %.0f s",
                    attempt,
                    settings.max_attempts,
                    exc,
                    delay,
                )
                await asyncio.sleep(delay)
                attempt += 1
            else:
                log.info("Saved %s (%d bytes)", result.path, result.size)
                return result


async def _attempt(
    session: aiohttp.ClientSession,
    url: str,
    directory: Path,
    policy: NetworkPolicy,
    settings: DownloadSettings,
    on_progress: ProgressCallback | None,
    on_file_info: FileInfoCallback | None,
) -> DownloadResult:
    async with _translated_errors(url, directory):
        response = await _get_following_redirects(session, url, policy, settings)
        async with response:
            _check_status(response)
            total = response.content_length  # None when the server doesn't say
            name = _choose_filename(response, directory)
            _check_free_space(directory, total)
            if on_file_info:
                on_file_info(name, total)
            part_path, part_file = _open_part_file(directory, name)
            try:
                with part_file:
                    received = await _stream_to_file(
                        response, part_file, total, settings, on_progress
                    )
                if total is not None and received != total:
                    raise DownloadError(_interrupted_message(received, total), retryable=True)
                final_path = await _finalize(part_path, directory, name)
            except BaseException:  # includes cancellation: never leave a partial file behind
                with contextlib.suppress(OSError):
                    part_path.unlink(missing_ok=True)
                raise
    # With chunked encoding aiohttp itself fails if the final chunk never arrives.
    chunked = "chunked" in response.headers.get("Transfer-Encoding", "").lower()
    return DownloadResult(
        path=final_path,
        size=received,
        final_url=str(response.url),
        content_type=response.headers.get("Content-Type"),
        verified_complete=total is not None or chunked,
    )


async def _get_following_redirects(
    session: aiohttp.ClientSession, url: str, policy: NetworkPolicy, settings: DownloadSettings
) -> aiohttp.ClientResponse:
    current = url
    for _ in range(settings.max_redirects + 1):
        try:
            parts = validate_url(current)
        except InvalidURLError as exc:
            raise InvalidURLError(
                f"The server redirected to an address SDM refuses: {exc}"
            ) from None
        policy.check_url_host(parts.hostname or "")
        response = await session.get(current, allow_redirects=False)
        if response.status not in _REDIRECT_STATUSES:
            return response
        location = response.headers.get("Location")
        response.release()
        if not location:
            raise DownloadError("The server sent a redirect without a destination.")
        current = urljoin(current, location.strip())
        log.info("Redirected to %s", redact_url(current))
    raise DownloadError(f"Too many redirects (more than {settings.max_redirects}).")


def _check_status(response: aiohttp.ClientResponse) -> None:
    status = response.status
    if status == 200:
        return
    label = f"{status} {_printable(response.reason, 80)}".strip()
    if status in _RETRYABLE_STATUSES or 500 <= status <= 599:
        raise DownloadError(
            f"The server reported a temporary problem ({label}).",
            retryable=True,
            retry_after=parse_retry_after(response.headers.get("Retry-After")),
        )
    if status in (404, 410):
        raise DownloadError(f"The file was not found on the server ({label}).")
    raise DownloadError(f"The server refused the download ({label}).")


def parse_retry_after(value: str | None) -> float | None:
    """Seconds to wait from a Retry-After header (a number or an HTTP date), or None."""
    if not value:
        return None
    value = value.strip()
    if value.isdigit():
        return float(value)
    try:
        when = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    return max(0.0, (when - datetime.now(UTC)).total_seconds())


def _choose_filename(response: aiohttp.ClientResponse, directory: Path) -> str:
    raw = filename_from_content_disposition(
        response.headers.get("Content-Disposition")
    ) or filename_from_url(str(response.url))
    # Leave room in the 260-character path limit for the ".sdmpart" and " (999)" suffixes.
    folder_length = len(os.path.abspath(directory).encode("utf-16-le")) // 2
    budget = WINDOWS_MAX_PATH - folder_length - 1 - len(PART_SUFFIX)
    budget -= len(f" ({MAX_NAME_VARIANTS - 1})")
    if budget < 12:
        raise DownloadError(f"The download folder's path is too long for Windows: {directory}")
    return sanitize_filename(raw, max_length=min(200, budget))


def _check_free_space(directory: Path, total: int | None) -> None:
    if total is None:
        return
    free = shutil.disk_usage(directory).free
    if free < total:
        raise DownloadError(
            f"Not enough disk space: the file needs {total:,} bytes but only {free:,} are free."
        )


def _open_part_file(directory: Path, name: str) -> tuple[Path, BinaryIO]:
    for number in range(MAX_NAME_VARIANTS):
        path = directory / (numbered_name(name, number) + PART_SUFFIX)
        try:
            return path, open(path, "xb")  # "x": fail rather than reuse an existing file
        except FileExistsError:
            continue
    raise DownloadError(f"Too many files named like {name} in {directory}.")


async def _stream_to_file(
    response: aiohttp.ClientResponse,
    file: BinaryIO,
    total: int | None,
    settings: DownloadSettings,
    on_progress: ProgressCallback | None,
) -> int:
    received = 0
    if on_progress:
        on_progress(received, total)
    try:
        async for chunk in response.content.iter_chunked(settings.chunk_size):
            file.write(chunk)
            received += len(chunk)
            if on_progress:
                on_progress(received, total)
    except (aiohttp.ClientPayloadError, aiohttp.ServerDisconnectedError, ConnectionError) as exc:
        # Say how much arrived, as IDM does (OBS-006: "50.00%").
        raise DownloadError(_interrupted_message(received, total), retryable=True) from exc
    return received


def _interrupted_message(received: int, total: int | None) -> str:
    amount = format_size(received)
    if total is not None:
        amount += f" of {format_size(total)}"
    return f"The download was interrupted after {amount}."


async def _finalize(part_path: Path, directory: Path, name: str) -> Path:
    for number in range(MAX_NAME_VARIANTS):
        target = directory / numbered_name(name, number)
        for delay in (0.1, 0.2, 0.4, 0.8, None):
            try:
                _rename_no_overwrite(part_path, target)
                return target
            except FileExistsError:
                break  # that name is taken: try the next number
            except PermissionError:
                # Antivirus scanners briefly lock freshly written files; wait and retry.
                if delay is None:
                    raise
                await asyncio.sleep(delay)
    raise DownloadError(f"Too many files named like {name} in {directory}.")


def _rename_no_overwrite(src: Path, dst: Path) -> None:
    """Rename src to dst; raise FileExistsError instead of replacing an existing dst."""
    if os.name == "nt":
        os.rename(src, dst)  # on Windows, rename refuses to replace an existing file
    else:
        os.link(src, dst)  # POSIX rename would overwrite silently; link refuses
        os.unlink(src)


@contextlib.asynccontextmanager
async def _translated_errors(url: str, directory: Path) -> AsyncIterator[None]:
    """Turn library and OS exceptions into DownloadErrors with user-readable messages."""
    try:
        yield
    except SDMError:
        raise
    except (TimeoutError, aiohttp.ClientError, OSError) as exc:
        raise _translate(exc, urlsplit(url).hostname or url, directory) from exc


def _translate(exc: BaseException, host: str, directory: Path) -> SDMError:
    # Order matters: several aiohttp errors are also OSErrors, and TimeoutError is one too.
    if isinstance(exc, TimeoutError):
        return DownloadError("The server took too long to respond.", retryable=True)
    if isinstance(exc, aiohttp.ClientSSLError):
        return DownloadError(
            f"Could not set up a secure connection to {host} (certificate or TLS problem)."
        )
    if isinstance(exc, aiohttp.ClientConnectorDNSError):
        return DownloadError(
            f"Could not find the server {host}. Check the address and your connection.",
            retryable=True,
        )
    if isinstance(exc, aiohttp.ClientConnectorError):
        return DownloadError(f"Could not connect to {host}.", retryable=True)
    if isinstance(exc, aiohttp.InvalidURL):
        # e.g. "127.1 - is not a canonical IPv4 address": aiohttp refuses disguised IPs.
        return InvalidURLError(f"The address is not valid ({_printable(str(exc), 120)}).")
    if isinstance(exc, aiohttp.ClientError | ConnectionError):
        return DownloadError("The download was interrupted by a network error.", retryable=True)
    if isinstance(exc, OSError):
        return _file_error(exc, directory)
    return DownloadError(f"Unexpected error: {type(exc).__name__}.")


def _file_error(exc: OSError, directory: Path) -> DownloadError:
    winerror = getattr(exc, "winerror", None)
    if exc.errno == errno.ENOSPC or winerror in _WINERROR_DISK_FULL:
        return DownloadError(f"Not enough disk space in {directory}.")
    # Controlled Folder Access reports a blocked write as "file not found" even though the
    # folder exists (verified on this machine in M2), so treat that like "access denied".
    if isinstance(exc, PermissionError) or (
        isinstance(exc, FileNotFoundError) and directory.is_dir()
    ):
        return DownloadError(
            f"Windows refused to let SDM write to {directory}. If it is a protected folder "
            "(Documents, Desktop, Pictures...), Controlled Folder Access may be blocking SDM: "
            "choose another download folder."
        )
    if exc.errno == errno.ENAMETOOLONG or winerror == _WINERROR_PATH_TOO_LONG:
        return DownloadError("The file path is too long for Windows.")
    return DownloadError(f"Could not write the file: {exc.strerror or exc}.")


def _printable(text: str | None, limit: int) -> str:
    """Server-supplied text, reduced to printable characters before it reaches the user."""
    return "".join(ch for ch in (text or "") if ch.isprintable())[:limit]
