"""HTTP/HTTPS download over one connection, with resume (M2, resume added in M4).

One attempt: check the URL -> GET, following redirects by hand so every hop is re-checked ->
check the status -> choose a filename -> stream into "<name>.sdmpart" -> verify the size ->
rename to the final name without ever replacing an existing file.

Resuming (M4). When part of the file is already on disk, the request asks only for the rest:
`Range: bytes=N-`, plus `If-Range` with the server's version tag (ETag or Last-Modified), so a
file that changed on the server comes back whole instead. The reply counts as a continuation
only if it is `206` with a Content-Range starting exactly at N and the expected total size.
Without version tags, SDM asks for 64 bytes more than it needs and checks they match the end
of its partial file (an idea from IDM's behavior in OBS-006). Anything else starts over from
byte 0 in the same partial file. Two versions of a file are never stitched together.

Failed attempts that might succeed later (timeouts, 5xx, dropped connections) are retried and
continue where they stopped when the server can resume.

Splitting (M5). A big enough file from a server that supports ranges and gives a version tag
is downloaded over several connections at once; see sdm.engine.segmented and ADR-0012.
"""

import asyncio
import contextlib
import email.utils
import errno
import logging
import os
import shutil
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO
from urllib.parse import urljoin, urlsplit

import aiohttp

from sdm.core.downloads import BrowserContext, PartialDownload
from sdm.core.errors import DownloadError, InvalidURLError, SDMError
from sdm.core.filenames import (
    filename_from_content_disposition,
    filename_from_url,
    numbered_name,
    sanitize_filename,
)
from sdm.core.referrer import check_redirect, referer_header
from sdm.core.segments import Segment, plan_segments, segments_cover, total_received
from sdm.core.urls import redact_url, validate_url
from sdm.engine.limiter import SpeedLimiter
from sdm.engine.models import (
    DownloadResult,
    DownloadSettings,
    FileInfoCallback,
    PartialCallback,
    ProgressCallback,
)
from sdm.engine.policy import NetworkPolicy, PolicyResolver
from sdm.engine.segmented import (
    SegmentedDownload,
    parse_content_range,
    prepare_part_file,
    tags_match,
)
from sdm.engine.segmented import StartOver as _StartOver
from sdm.engine.segmented import interrupted_message as _interrupted_message

log = logging.getLogger(__name__)

PART_SUFFIX = ".sdmpart"
MAX_NAME_VARIANTS = 1000  # "name.ext" through "name (999).ext"
WINDOWS_MAX_PATH = 259  # characters in a full path, excluding the terminating NUL
OVERLAP = 64  # bytes re-downloaded to check a resume when the server gives no version tags
_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
_RETRYABLE_STATUSES = frozenset({408, 429})
_WINERROR_DISK_FULL = frozenset({39, 112})
_WINERROR_PATH_TOO_LONG = 206


@dataclass
class _Transfer:
    """What one download() call knows about its partial file, across attempts."""

    part_path: Path | None = None
    file_name: str | None = None
    received: int = 0  # bytes at the start of the partial file that belong to this version
    total: int | None = None
    etag: str | None = None
    last_modified: str | None = None
    resumable: bool = False
    segments: list[Segment] | None = None  # set while the download is split (M5)
    no_split: bool = False  # after a failed split, stay on one connection
    context: BrowserContext = BrowserContext()  # what the browser said (M8)
    limiter: SpeedLimiter | None = None  # the shared speed limit (M9)

    @classmethod
    def start(cls, directory: Path, resume_from: PartialDownload | None) -> "_Transfer":
        if resume_from is None:
            return cls()
        part = Path(resume_from.part_path)
        if not is_own_part_file(part, directory):
            # The path came from the database; never let it point SDM somewhere else.
            log.warning("Ignoring a partial file that isn't in the download folder")
            return cls()
        if not part.is_file():
            log.info("The partial file is gone; starting over")
            return cls()
        total = resume_from.total_bytes
        if resume_from.segments is not None:
            segments = list(resume_from.segments)
            if (
                total is None
                or part.stat().st_size != total
                or not segments_cover(segments, total)
                or _if_range_value(resume_from.etag, resume_from.last_modified) is None
            ):
                log.info("The saved parts map doesn't fit the partial file; starting over")
                return cls()
            return cls(
                part_path=part,
                file_name=resume_from.file_name,
                received=total_received(segments),
                total=total,
                etag=resume_from.etag,
                last_modified=resume_from.last_modified,
                resumable=resume_from.resumable,
                segments=segments,
            )
        received = part.stat().st_size
        if total is not None and received > total:
            received = 0  # more data than the file has: don't trust any of it
        return cls(
            part_path=part,
            file_name=resume_from.file_name,
            received=received,
            total=total,
            etag=resume_from.etag,
            last_modified=resume_from.last_modified,
            resumable=resume_from.resumable,
        )

    def partial(self) -> PartialDownload:
        if self.part_path is None or self.file_name is None:
            raise RuntimeError("No partial file yet.")
        return PartialDownload(
            part_path=self.part_path,
            file_name=self.file_name,
            total_bytes=self.total,
            etag=self.etag,
            last_modified=self.last_modified,
            resumable=self.resumable,
            segments=tuple(self.segments) if self.segments is not None else None,
        )

    def start_over(self) -> None:
        """Forget what is on disk and any split; the partial file is reused from byte 0."""
        self.received = 0
        self.segments = None
        self.no_split = True


@dataclass(frozen=True)
class _RangePlan:
    """How to ask for the rest of the file."""

    start: int  # first byte requested
    overlap: int  # bytes before `received` re-requested to check the file hasn't changed
    if_range: str | None  # version tag sent with If-Range, if any

    def headers(self) -> dict[str, str]:
        headers = {"Range": f"bytes={self.start}-"}
        if self.if_range:
            headers["If-Range"] = self.if_range
        return headers


async def download(
    url: str,
    destination_dir: str | os.PathLike[str],
    *,
    policy: NetworkPolicy | None = None,
    settings: DownloadSettings | None = None,
    on_progress: ProgressCallback | None = None,
    on_file_info: FileInfoCallback | None = None,
    on_partial: PartialCallback | None = None,
    resume_from: PartialDownload | None = None,
    keep_partial: bool = False,
    on_connections: Callable[[int], None] | None = None,
    context: BrowserContext | None = None,
    limiter: SpeedLimiter | None = None,
) -> DownloadResult:
    """Download `url` into `destination_dir` and return where the file was saved.

    `context` carries what the browser said about the link (M8): its page becomes the Referer
    of every request, under the browser's rules, and its suggested name is used when the server
    names no file. `limiter` is the speed limit shared with other downloads (M9).

    `resume_from` continues an earlier partial file. With `keep_partial` (the window's download
    manager), the partial file is kept when the download is cancelled (the caller decides
    whether that was a pause) or fails on a server that can resume; otherwise (`sdm-get`) any
    failure deletes it.

    Raises an SDMError subclass (InvalidURLError, BlockedDestinationError, DownloadError)
    whose message is fit to show the user.
    """
    url = url.strip()
    validate_url(url)
    policy = policy or NetworkPolicy()
    settings = settings or DownloadSettings()
    directory = Path(destination_dir)
    if not directory.is_dir():
        raise DownloadError(f"The download folder does not exist: {directory}")
    transfer = _Transfer.start(directory, resume_from)
    transfer.context = context or BrowserContext()
    transfer.limiter = limiter

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
    try:
        async with session:
            attempt = 1
            while True:
                try:
                    result = await _attempt(
                        session,
                        url,
                        directory,
                        policy,
                        settings,
                        transfer,
                        on_progress,
                        on_file_info,
                        on_partial,
                        on_connections,
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
    except BaseException as exc:  # includes cancellation
        if transfer.part_path is not None and not _keep_partial(exc, transfer, keep_partial):
            with contextlib.suppress(OSError):
                transfer.part_path.unlink(missing_ok=True)
        raise


def _keep_partial(exc: BaseException, transfer: _Transfer, keep_partial: bool) -> bool:
    if not keep_partial:
        return False
    if isinstance(exc, asyncio.CancelledError):
        return True  # the manager deletes it afterwards unless this was a pause
    return transfer.resumable and transfer.received > 0


async def _attempt(
    session: aiohttp.ClientSession,
    url: str,
    directory: Path,
    policy: NetworkPolicy,
    settings: DownloadSettings,
    transfer: _Transfer,
    on_progress: ProgressCallback | None,
    on_file_info: FileInfoCallback | None,
    on_partial: PartialCallback | None,
    on_connections: Callable[[int], None] | None,
) -> DownloadResult:
    async with _translated_errors(url, directory):
        if transfer.segments is not None:  # continue a split download, part by part
            try:
                await _run_segmented(
                    session,
                    url,
                    policy,
                    settings,
                    transfer,
                    None,
                    on_progress,
                    on_partial,
                    on_connections,
                )
            except _StartOver as reason:
                log.info("Can't resume the parts (%s); downloading from the start", reason)
                transfer.start_over()
            else:
                return await _finish_segmented(transfer, directory, url, None)
        plan = _range_plan(transfer)
        while True:
            extra = plan.headers() if plan else None
            response = await _get_following_redirects(
                session, url, policy, settings, extra, transfer.context.referrer
            )
            async with response:
                try:
                    offset = await _accept_response(response, plan, transfer, directory)
                except _StartOver as reason:
                    log.info("Can't resume (%s); downloading from the start", reason)
                    plan = None
                    transfer.received = 0
                    continue
                if transfer.part_path is None or transfer.file_name is None:  # pragma: no cover
                    raise DownloadError("Internal error: no partial file.")
                split = offset == 0 and _should_split(transfer, settings)
                if split and transfer.total is not None:
                    transfer.segments = plan_segments(
                        transfer.total, settings.max_connections, settings.min_part_size
                    )
                    prepare_part_file(transfer.part_path, transfer.total)
                if on_file_info:
                    on_file_info(transfer.file_name, transfer.total)
                if on_partial:
                    on_partial(transfer.partial())
                if split:
                    try:
                        await _run_segmented(
                            session,
                            str(response.url),
                            policy,
                            settings,
                            transfer,
                            response,
                            on_progress,
                            on_partial,
                            on_connections,
                        )
                    except _StartOver as reason:
                        log.info(
                            "Can't continue the parts (%s); downloading from the start", reason
                        )
                        transfer.start_over()
                        plan = None
                        continue
                    return await _finish_segmented(
                        transfer, directory, str(response.url), response.headers.get("Content-Type")
                    )
                if offset is None:  # 416: everything was already there
                    received = transfer.received
                else:
                    with open(transfer.part_path, "r+b") as part_file:
                        part_file.seek(offset)
                        part_file.truncate()  # drop anything after the trusted bytes
                        received = await _stream_to_file(
                            response, part_file, transfer, settings, on_progress
                        )
                total = transfer.total
                if total is not None and received != total:
                    raise DownloadError(_interrupted_message(received, total), retryable=True)
                final_path = await _finalize(transfer.part_path, directory, transfer.file_name)
                # With chunked encoding aiohttp itself fails if the final chunk never arrives.
                chunked = "chunked" in response.headers.get("Transfer-Encoding", "").lower()
                transfer.part_path = None  # renamed: nothing left to clean up
                return DownloadResult(
                    path=final_path,
                    size=received,
                    final_url=str(response.url),
                    content_type=response.headers.get("Content-Type"),
                    verified_complete=total is not None or chunked or response.status == 206,
                )


def _if_range_value(etag: str | None, last_modified: str | None) -> str | None:
    """The version tag to send with If-Range: a strong ETag, else Last-Modified, else None."""
    strong_etag = etag if etag and not etag.startswith("W/") else None
    return strong_etag or last_modified


def _should_split(transfer: _Transfer, settings: DownloadSettings) -> bool:
    """Split only big files from servers that support ranges and give a version tag."""
    total = transfer.total
    return (
        not transfer.no_split
        and settings.max_connections > 1
        and total is not None
        and total >= settings.min_split_size
        and transfer.resumable
        and _if_range_value(transfer.etag, transfer.last_modified) is not None
        and len(plan_segments(total, settings.max_connections, settings.min_part_size)) > 1
    )


async def _run_segmented(
    session: aiohttp.ClientSession,
    url: str,
    policy: NetworkPolicy,
    settings: DownloadSettings,
    transfer: _Transfer,
    first_response: aiohttp.ClientResponse | None,
    on_progress: ProgressCallback | None,
    on_partial: PartialCallback | None,
    on_connections: Callable[[int], None] | None = None,
) -> None:
    if_range = _if_range_value(transfer.etag, transfer.last_modified)
    if transfer.part_path is None or transfer.total is None or transfer.segments is None:
        raise _StartOver("nothing to continue")  # pragma: no cover
    if if_range is None:
        raise _StartOver("no version tag")

    def on_snapshot(segments: tuple[Segment, ...]) -> None:
        transfer.segments = list(segments)
        transfer.received = total_received(segments)
        if on_partial:
            on_partial(transfer.partial())

    async def request(headers: dict[str, str]) -> aiohttp.ClientResponse:
        # Every part request goes through the same redirect checks and network policy.
        return await _get_following_redirects(
            session, url, policy, settings, headers, transfer.context.referrer
        )

    await SegmentedDownload(
        request=request,
        part_path=transfer.part_path,
        total=transfer.total,
        if_range=if_range,
        etag=transfer.etag,
        last_modified=transfer.last_modified,
        segments=transfer.segments,
        settings=settings,
        on_progress=on_progress,
        on_snapshot=on_snapshot,
        on_connections=on_connections,
        limiter=transfer.limiter,
    ).run(first_response)


async def _finish_segmented(
    transfer: _Transfer, directory: Path, final_url: str, content_type: str | None
) -> DownloadResult:
    if transfer.part_path is None or transfer.file_name is None or transfer.total is None:
        raise DownloadError("Internal error: no partial file.")  # pragma: no cover
    final_path = await _finalize(transfer.part_path, directory, transfer.file_name)
    transfer.part_path = None  # renamed: nothing left to clean up
    return DownloadResult(
        path=final_path,
        size=transfer.total,
        final_url=final_url,
        content_type=content_type,
        verified_complete=True,
    )


def _range_plan(transfer: _Transfer) -> _RangePlan | None:
    """How to ask for the rest of a plain (unsplit) partial file, or None to download it whole."""
    if transfer.part_path is None or transfer.received <= 0 or transfer.segments is not None:
        return None
    validator = _if_range_value(transfer.etag, transfer.last_modified)
    if validator:
        return _RangePlan(start=transfer.received, overlap=0, if_range=validator)
    if transfer.received >= OVERLAP:
        return _RangePlan(start=transfer.received - OVERLAP, overlap=OVERLAP, if_range=None)
    return None  # too little to check: cheaper to start over


async def _accept_response(
    response: aiohttp.ClientResponse,
    plan: _RangePlan | None,
    transfer: _Transfer,
    directory: Path,
) -> int | None:
    """Check the reply and prepare the partial file.

    Returns the offset to write from, or None if the file is already complete (416).
    Raises _StartOver when a resume reply can't be trusted.
    """
    status = response.status
    if plan is not None and status == 416:
        if plan.overlap == 0 and transfer.total == transfer.received:
            return None
        raise _StartOver("the server refused the range")
    if plan is not None and status == 206:
        await _check_continuation(response, plan, transfer)
        transfer.resumable = True  # proven
        _check_free_space(directory, (transfer.total or 0) - transfer.received)
        return transfer.received
    _check_status(response)  # anything but 200 raises here (including 206 we didn't ask for)

    # 200: the whole file, from byte 0.
    if transfer.received:
        log.info("The server sent the whole file instead of the rest; starting over")
    transfer.received = 0
    transfer.total = response.content_length  # None when the server doesn't say
    transfer.etag = response.headers.get("ETag")
    transfer.last_modified = response.headers.get("Last-Modified")
    transfer.resumable = response.headers.get("Accept-Ranges", "").strip().lower() == "bytes"
    if transfer.part_path is None:
        transfer.file_name = _choose_filename(response, directory, transfer.context.suggested_name)
    _check_free_space(directory, transfer.total)
    if transfer.part_path is None:
        transfer.part_path = _create_part_file(directory, transfer.file_name or "download")
    return 0


async def _check_continuation(
    response: aiohttp.ClientResponse, plan: _RangePlan, transfer: _Transfer
) -> None:
    """A 206 reply continues the partial file only if everything about it matches."""
    content_range = parse_content_range(response.headers.get("Content-Range"))
    if content_range is None:
        raise _StartOver("missing or invalid Content-Range")
    first, last, total = content_range
    if first != plan.start or last != total - 1:
        raise _StartOver(f"the server sent bytes {first}-{last}, not {plan.start}-{total - 1}")
    if transfer.total is not None and total != transfer.total:
        raise _StartOver("the file's size changed")
    if not tags_match(response, transfer.etag, transfer.last_modified):
        raise _StartOver("the file's version tags changed")
    transfer.total = total
    if plan.overlap:
        try:
            fresh = await response.content.readexactly(plan.overlap)
        except asyncio.IncompleteReadError as exc:
            raise DownloadError(
                _interrupted_message(transfer.received, transfer.total), retryable=True
            ) from exc
        if transfer.part_path is None:  # a plan always has a partial file; be safe anyway
            raise _StartOver("no partial file")
        with open(transfer.part_path, "rb") as part_file:
            part_file.seek(transfer.received - plan.overlap)
            on_disk = part_file.read(plan.overlap)
        if fresh != on_disk:
            raise _StartOver("the last bytes on disk don't match the server's file")


async def _get_following_redirects(
    session: aiohttp.ClientSession,
    url: str,
    policy: NetworkPolicy,
    settings: DownloadSettings,
    extra_headers: dict[str, str] | None = None,
    referrer: str | None = None,
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
        headers = dict(extra_headers or {})
        referer = referer_header(referrer, current)  # recomputed for every hop, like a browser
        if referer is not None:
            headers["Referer"] = referer
        response = await session.get(current, allow_redirects=False, headers=headers or None)
        if response.status not in _REDIRECT_STATUSES:
            return response
        location = response.headers.get("Location")
        response.release()
        if not location:
            raise DownloadError("The server sent a redirect without a destination.")
        try:
            following = urljoin(current, location.strip())
        except ValueError:  # e.g. "Location: http://[" (found by fuzzing, M10)
            raise InvalidURLError(
                "The server redirected to an address SDM refuses: it is malformed."
            ) from None
        if not check_redirect(current, following):
            raise DownloadError(
                "The server redirected from a secure (https) address to an insecure (http) one."
                " SDM refuses that, as browsers do."
            )
        current = following
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


def _choose_filename(
    response: aiohttp.ClientResponse, directory: Path, suggested: str | None = None
) -> str:
    # The server's own name first, then the browser's suggestion (M8), then the URL's last part.
    raw = (
        filename_from_content_disposition(response.headers.get("Content-Disposition"))
        or (suggested or "").strip()
        or filename_from_url(str(response.url))
    )
    # Leave room in the 260-character path limit for the ".sdmpart" and " (999)" suffixes.
    folder_length = len(os.path.abspath(directory).encode("utf-16-le")) // 2
    budget = WINDOWS_MAX_PATH - folder_length - 1 - len(PART_SUFFIX)
    budget -= len(f" ({MAX_NAME_VARIANTS - 1})")
    if budget < 12:
        raise DownloadError(f"The download folder's path is too long for Windows: {directory}")
    return sanitize_filename(raw, max_length=min(200, budget))


def _check_free_space(directory: Path, needed: int | None) -> None:
    if not needed or needed <= 0:
        return
    free = shutil.disk_usage(directory).free
    if free < needed:
        raise DownloadError(
            f"Not enough disk space: the file needs {needed:,} bytes but only {free:,} are free."
        )


def _create_part_file(directory: Path, name: str) -> Path:
    for number in range(MAX_NAME_VARIANTS):
        path = directory / (numbered_name(name, number) + PART_SUFFIX)
        try:
            with open(path, "xb"):  # "x": fail rather than reuse another download's file
                return path
        except FileExistsError:
            continue
    raise DownloadError(f"Too many files named like {name} in {directory}.")


def is_own_part_file(part: Path, directory: Path) -> bool:
    """True if `part` is a .sdmpart file directly inside `directory`."""
    try:
        return part.name.endswith(PART_SUFFIX) and part.parent.resolve() == directory.resolve()
    except OSError:
        return False


async def _stream_to_file(
    response: aiohttp.ClientResponse,
    file: BinaryIO,
    transfer: _Transfer,
    settings: DownloadSettings,
    on_progress: ProgressCallback | None,
) -> int:
    if on_progress:
        on_progress(transfer.received, transfer.total)
    try:
        async for chunk in response.content.iter_chunked(settings.chunk_size):
            if transfer.limiter is not None:
                await transfer.limiter.take(len(chunk))
            file.write(chunk)
            transfer.received += len(chunk)  # a retry continues from here
            if on_progress:
                on_progress(transfer.received, transfer.total)
    except (aiohttp.ClientPayloadError, aiohttp.ServerDisconnectedError, ConnectionError) as exc:
        # Say how much arrived, as IDM does (OBS-006: "50.00%").
        raise DownloadError(
            _interrupted_message(transfer.received, transfer.total), retryable=True
        ) from exc
    return transfer.received


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
