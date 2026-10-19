"""Downloading one file over several connections at once (M5, ADR-0012).

The first connection is the ordinary request: it starts at byte 0 while the extra connections
ask for their own parts with `Range: bytes=a-b` and `If-Range`. A part is accepted only from a
`206` whose Content-Range is exactly `a-b/total`, with the same version tags. All parts write
into one pre-sized file at their own offsets through a single file handle: asyncio runs
everything on one thread, so a seek-and-write pair is never interrupted.

Fallback. If an extra connection's first reply can't be trusted, or it can't connect at all,
while the first connection is still open, the extra connections stop and the first one, whose
reply is the whole file, simply carries on to the end. To keep that possible, the first
connection waits at the end of its own part until every extra part has been confirmed.

Once all parts are confirmed, a part that drops retries its own remaining range; the others
keep going. Dynamic splitting (M5b): whenever a connection is free (a part finished, or a
resume has fewer parts than connections allowed), the part with the most bytes left gives
its second half to a new connection, as long as both halves keep at least `min_part_size`.
A reply that can't be trusted after that point (the file changed on the server) raises
StartOver, and the caller downloads the file again on one connection.
"""

import asyncio
import contextlib
import logging
import os
import re
import sys
from collections.abc import Awaitable, Callable, Sequence
from pathlib import Path
from typing import BinaryIO

import aiohttp

from sdm.core.errors import DownloadError
from sdm.core.segments import Segment, pick_split
from sdm.core.units import format_size
from sdm.engine.limiter import SpeedLimiter
from sdm.engine.models import DownloadSettings, ProgressCallback

log = logging.getLogger(__name__)

SNAPSHOT_EVERY = 1.0  # seconds between saving the parts map while downloading
_CONTENT_RANGE = re.compile(r"bytes (\d+)-(\d+)/(\d+)", re.ASCII)
_FSCTL_SET_SPARSE = 0x000900C4

Requester = Callable[[dict[str, str]], Awaitable[aiohttp.ClientResponse]]
SnapshotCallback = Callable[[tuple[Segment, ...]], None]
ConnectionsCallback = Callable[[int], None]


class StartOver(Exception):
    """A reply can't continue what is on disk: download the file from byte 0 instead."""


class NotTrusted(Exception):
    """A reply that can't serve this part (wrong status, range or version tags)."""


def parse_content_range(value: str | None) -> tuple[int, int, int] | None:
    """'bytes 100-199/1000' -> (100, 199, 1000); None for anything malformed or unusable."""
    if not value:
        return None
    match = _CONTENT_RANGE.fullmatch(value.strip())
    if not match:
        return None
    first, last, total = (int(group) for group in match.groups())
    if first > last or last >= total:
        return None
    return first, last, total


def tags_match(
    response: aiohttp.ClientResponse, etag: str | None, last_modified: str | None
) -> bool:
    """False if the reply carries an ETag or Last-Modified that differs from the known one."""
    for header, known in (("ETag", etag), ("Last-Modified", last_modified)):
        sent = response.headers.get(header)
        if sent and known and sent != known:
            return False
    return True


def interrupted_message(received: int, total: int | None) -> str:
    amount = format_size(received)
    if total is not None:
        amount += f" of {format_size(total)}"
    return f"The download was interrupted after {amount}."


def make_sparse(file: BinaryIO) -> bool:
    """Mark a file sparse on NTFS, so writing far into it doesn't zero-fill everything first.

    Without this, the first write near the end of a large pre-sized file makes Windows fill all
    the bytes before it with zeros, which can block for seconds. Harmless if it fails (FAT32).
    """
    if sys.platform != "win32":
        return False
    import ctypes
    import msvcrt
    from ctypes import wintypes

    handle = wintypes.HANDLE(msvcrt.get_osfhandle(file.fileno()))
    returned = wintypes.DWORD()
    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    ok = kernel32.DeviceIoControl(
        handle, _FSCTL_SET_SPARSE, None, 0, None, 0, ctypes.byref(returned), None
    )
    return bool(ok)


def prepare_part_file(path: Path, total: int) -> None:
    """Size the partial file to the whole download, ready for parts written at any offset."""
    with open(path, "r+b") as file:
        file.truncate(0)
        make_sparse(file)
        file.truncate(total)


class _Part:
    """One segment while it downloads (a mutable copy of a Segment)."""

    __slots__ = ("start", "end", "received")

    def __init__(self, start: int, end: int, received: int = 0) -> None:
        self.start, self.end, self.received = start, end, received

    @property
    def next_byte(self) -> int:
        return self.start + self.received

    @property
    def done(self) -> bool:
        return self.next_byte > self.end

    def frozen(self) -> Segment:
        return Segment(self.start, self.end, self.received)


class SegmentedDownload:
    def __init__(
        self,
        *,
        request: Requester,
        part_path: Path,
        total: int,
        if_range: str,
        etag: str | None,
        last_modified: str | None,
        segments: Sequence[Segment],
        settings: DownloadSettings,
        on_progress: ProgressCallback | None,
        on_snapshot: SnapshotCallback,
        on_connections: ConnectionsCallback | None = None,
        limiter: SpeedLimiter | None = None,
    ) -> None:
        self._request = request
        self._limiter = limiter  # the speed limit shared by every download (M9)
        self._part_path = part_path
        self._total = total
        self._if_range = if_range
        self._etag = etag
        self._last_modified = last_modified
        self._parts = [_Part(s.start, s.end, s.received) for s in segments]
        self._settings = settings
        self._on_progress = on_progress
        self._on_snapshot = on_snapshot
        self._on_connections = on_connections
        self._reported_connections = 0
        self._file: BinaryIO | None = None
        self._tasks: list[asyncio.Task[None]] = []
        self._task_parts: dict[asyncio.Task[None], _Part] = {}
        self._first: _Part | None = None
        self._first_task: asyncio.Task[None] | None = None
        self._first_alive = False
        self._fallen_back = False
        self._unconfirmed = 0
        self._confirmed = asyncio.Event()
        self._stop_saving = asyncio.Event()

    @property
    def received(self) -> int:
        return sum(part.received for part in self._parts)

    @property
    def connections(self) -> int:
        """How many parts are downloading right now."""
        return sum(1 for t, p in self._task_parts.items() if not t.done() and not p.done)

    def snapshot(self) -> tuple[Segment, ...]:
        return tuple(part.frozen() for part in sorted(self._parts, key=lambda p: p.start))

    async def run(self, first_response: aiohttp.ClientResponse | None = None) -> None:
        """Download every unfinished part. Raises StartOver or DownloadError on failure."""
        with open(self._part_path, "r+b") as file:
            self._file = file
            ticker = asyncio.create_task(self._save_regularly())
            try:
                await self._run_parts(first_response)
            finally:
                # Stop the saver gently (not cancel()): it may be in the middle of a disk sync on
                # a worker thread, and the file must stay open until that has finished.
                self._stop_saving.set()
                with contextlib.suppress(asyncio.CancelledError):
                    await ticker
                self._save()  # also on pause/cancel: what arrived must be resumable
                self._file = None
        if not all(part.done for part in self._parts):
            raise DownloadError(interrupted_message(self.received, self._total), retryable=True)

    # ----- coordinating the parts -----

    async def _run_parts(self, first_response: aiohttp.ClientResponse | None) -> None:
        for part in self._parts:
            if part.done:
                continue
            response = None
            if first_response is not None and self._first is None and part.next_byte == 0:
                self._first, response = part, first_response
            task = self._start_part(part, response)
            if response is not None:
                self._first_task, self._first_alive = task, True
        self._unconfirmed = sum(1 for task in self._tasks if task is not self._first_task)
        if self._unconfirmed == 0 or first_response is None:
            # With no whole-file first connection (a resume) there is nothing to fall back to,
            # so there is nothing to wait for either.
            self._confirmed.set()
        self._help()  # a resume may have fewer unfinished parts than connections allowed
        try:
            while pending := [task for task in self._tasks if not task.done()]:
                done, _ = await asyncio.wait(pending, return_when=asyncio.FIRST_EXCEPTION)
                for task in done:
                    if not task.cancelled() and task.exception() is not None:
                        raise task.exception()  # type: ignore[misc]
        finally:
            for task in self._tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*self._tasks, return_exceptions=True)

    async def _run_part(self, part: _Part, response: aiohttp.ClientResponse | None) -> None:
        is_first = response is not None
        confirmed = is_first  # the first connection's reply needs no confirmation
        attempt = 0
        while not part.done:
            try:
                if response is None:
                    try:
                        response = await self._request_part(part)
                    except NotTrusted as reason:
                        if not confirmed and self._can_fall_back():
                            self._fall_back(str(reason))
                            return
                        raise StartOver(str(reason)) from None
                    if not confirmed:
                        confirmed = True
                        self._confirm()
                async with response:
                    await self._stream(part, response, may_wait=is_first)
                response = None
                if part.done:
                    self._help(finishing=True)  # this connection is free: lend a hand
                    return
                if not part.done:
                    raise DownloadError(
                        interrupted_message(self.received, self._total), retryable=True
                    )
            except (
                aiohttp.ClientError,
                TimeoutError,
                ConnectionError,
                asyncio.IncompleteReadError,
                DownloadError,
            ) as exc:
                if isinstance(exc, DownloadError) and not exc.retryable:
                    raise
                response = None
                if is_first:  # the whole-file reply is gone: no more fallback from here
                    is_first = self._first_alive = False
                if not confirmed and self._can_fall_back():
                    self._fall_back(f"an extra connection failed ({type(exc).__name__})")
                    return
                attempt += 1
                if attempt >= self._settings.max_attempts:
                    raise DownloadError(
                        interrupted_message(self.received, self._total), retryable=True
                    ) from exc
                delay = self._settings.backoff_base * 2 ** (attempt - 1)
                await asyncio.sleep(min(delay, self._settings.max_retry_after))

    def _start_part(
        self, part: _Part, response: aiohttp.ClientResponse | None
    ) -> asyncio.Task[None]:
        task = asyncio.create_task(self._run_part(part, response))
        self._task_parts[task] = part
        task.add_done_callback(lambda _: self._report_connections())
        self._tasks.append(task)
        self._report_connections()
        return task

    def _help(self, *, finishing: bool = False) -> None:
        """Give free connections the second half of the part with the most bytes left."""
        if not self._settings.dynamic_splitting:
            return
        if self._fallen_back or not self._confirmed.is_set():
            return  # only once every part is confirmed, so fallback stays simple
        active = sum(1 for task in self._tasks if not task.done()) - (1 if finishing else 0)
        while active < self._settings.max_connections:
            candidates = [part for part in self._parts if not part.done]
            choice = pick_split(
                [(part.next_byte, part.end) for part in candidates], self._settings.min_part_size
            )
            if choice is None:
                break
            index, middle = choice
            old = candidates[index]
            new = _Part(middle, old.end)
            old.end = middle - 1  # the old connection stops there (it hasn't reached it yet)
            self._parts.append(new)
            self._start_part(new, None)
            active += 1

    def _report_connections(self) -> None:
        # Parts still downloading on a running task. A part that just finished hands its
        # connection to a new part a moment before its own task ends: it is not counted twice.
        count = sum(
            1 for task, part in self._task_parts.items() if not task.done() and not part.done
        )
        if count and count != self._reported_connections:
            self._reported_connections = count
            if self._on_connections:
                self._on_connections(count)

    def _can_fall_back(self) -> bool:
        # Possible only while the first connection still holds the whole-file reply, which it
        # keeps open until every extra part is confirmed.
        return self._first_alive and not self._fallen_back and not self._confirmed.is_set()

    def _fall_back(self, reason: str) -> None:
        log.info("Can't split this download (%s); continuing on one connection", reason)
        first = self._first
        if first is None:  # pragma: no cover - _can_fall_back guarantees a first part
            raise StartOver(reason)
        self._fallen_back = True
        first.end = self._total - 1  # the first connection now owns the whole file
        self._parts = [first]
        current = asyncio.current_task()
        for task in self._tasks:
            if task is not self._first_task and task is not current and not task.done():
                task.cancel()
        self._confirmed.set()  # wakes the first connection if it is waiting at its boundary

    def _confirm(self) -> None:
        self._unconfirmed -= 1
        if self._unconfirmed <= 0:
            self._confirmed.set()

    # ----- one connection -----

    async def _request_part(self, part: _Part) -> aiohttp.ClientResponse:
        # Remember exactly what was asked: while this request is in flight, dynamic splitting
        # may shrink `part.end`, and the reply must be checked against the request.
        first, last = part.next_byte, part.end
        headers = {"Range": f"bytes={first}-{last}", "If-Range": self._if_range}
        response = await self._request(headers)
        status = response.status
        if status in (408, 429) or 500 <= status <= 599:  # temporary: retry this part
            response.release()
            raise DownloadError(
                f"The server reported a temporary problem ({status}).", retryable=True
            )
        try:
            if status != 206:
                raise NotTrusted(f"the server answered {response.status} to a range request")
            expected = (first, last, self._total)
            if parse_content_range(response.headers.get("Content-Range")) != expected:
                raise NotTrusted("the server sent a different range than requested")
            if not tags_match(response, self._etag, self._last_modified):
                raise NotTrusted("the file's version tags changed")
        except NotTrusted:
            response.release()
            raise
        return response

    async def _stream(
        self, part: _Part, response: aiohttp.ClientResponse, *, may_wait: bool
    ) -> None:
        async for chunk in response.content.iter_chunked(self._settings.chunk_size):
            if self._limiter is not None:
                await self._limiter.take(len(chunk))
            while chunk:
                room = part.end + 1 - part.next_byte
                if room <= 0:
                    if may_wait and not self._confirmed.is_set():
                        await self._confirmed.wait()  # until the extras are confirmed
                        continue  # after a fallback, `part.end` has moved to the file's end
                    return  # this part is complete: stop reading (the connection closes)
                piece = chunk[:room]
                self._write(part.next_byte, piece)
                part.received += len(piece)
                chunk = chunk[len(piece) :]
                if self._on_progress:
                    self._on_progress(self.received, self._total)

    def _write(self, offset: int, data: bytes) -> None:
        if self._file is None:  # pragma: no cover
            raise RuntimeError("The partial file isn't open.")
        self._file.seek(offset)
        self._file.write(data)

    # ----- saving the parts map -----

    async def _save_regularly(self) -> None:
        """Every second: make the data durable, then report the parts map.

        The disk sync runs on a worker thread: on a busy disk it can take hundreds of
        milliseconds, and on this thread it would freeze every connection meanwhile. The map
        is captured *before* the sync, so it only ever claims bytes that are already synced.
        """
        while not self._stop_saving.is_set():
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._stop_saving.wait(), SNAPSHOT_EVERY)
            if self._stop_saving.is_set() or self._file is None:
                return
            snapshot = self.snapshot()
            with contextlib.suppress(OSError):
                self._file.flush()  # Python's buffer -> Windows: quick
                await asyncio.to_thread(os.fsync, self._file.fileno())
            self._on_snapshot(snapshot)

    def _save(self) -> None:
        """Make written data durable, then report the parts map (never the other way round)."""
        if self._file is not None:
            with contextlib.suppress(OSError):
                self._file.flush()
                os.fsync(self._file.fileno())
        self._on_snapshot(self.snapshot())
