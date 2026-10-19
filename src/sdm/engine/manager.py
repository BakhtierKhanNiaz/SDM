"""Runs downloads on a background thread with its own asyncio event loop (ADR-0009).

A window freezes if it waits on the network, so all downloading happens on one engine thread.
Other threads talk to it only through submit(), pause(), cancel() and shutdown(), which are safe
to call from any thread. The manager reports back by calling `on_event` with the small event objects
below. That call happens **on the engine thread**: the window's adapter
(sdm.ui.engine_adapter) passes events on to the UI thread through Qt signals. This module never
imports Qt.

At most `max_concurrent` downloads run at once (3 by default); the others wait their turn in the
order they were submitted. Full queue management comes in M6.

Pause keeps the partial file so the download can be resumed later (submit it again with
`resume_from`); cancel deletes it. Shutting down pauses everything (M4).
"""

import asyncio
import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from sdm.core.downloads import BrowserContext, PartialDownload
from sdm.core.errors import SDMError
from sdm.engine.http_download import download, is_own_part_file
from sdm.engine.limiter import SpeedLimiter
from sdm.engine.models import DownloadResult, DownloadSettings
from sdm.engine.policy import NetworkPolicy

log = logging.getLogger(__name__)

MAX_CONCURRENT = 3
PROGRESS_INTERVAL = 0.2  # seconds between progress events for one download


@dataclass(frozen=True)
class Started:
    """A slot became free and the download began."""

    download_id: int


@dataclass(frozen=True)
class FileInfo:
    """The server answered: file name and size (None when unknown) are known."""

    download_id: int
    file_name: str
    total_bytes: int | None


@dataclass(frozen=True)
class PartialSaved:
    """The partial file and the server's version tags are known: enough to resume later."""

    download_id: int
    partial: PartialDownload


@dataclass(frozen=True)
class Progress:
    download_id: int
    received_bytes: int
    total_bytes: int | None
    connections: int = 1  # how many connections are downloading it (M5)


@dataclass(frozen=True)
class Finished:
    download_id: int
    result: DownloadResult


@dataclass(frozen=True)
class Failed:
    download_id: int
    message: str  # fit to show the user
    partial: PartialDownload | None = None  # kept for a retry when the server can resume
    retryable: bool = False  # a temporary problem (network, timeout, 5xx): worth retrying (M6)


@dataclass(frozen=True)
class Paused:
    download_id: int
    partial: PartialDownload | None  # None if nothing had arrived yet


@dataclass(frozen=True)
class Cancelled:
    """Stopped for good; its partial file has been deleted."""

    download_id: int


DownloadEvent = (
    Started | FileInfo | PartialSaved | Progress | Finished | Failed | Paused | Cancelled
)
EventCallback = Callable[[DownloadEvent], None]


class DownloadManager:
    def __init__(
        self,
        on_event: EventCallback,
        *,
        max_concurrent: int = MAX_CONCURRENT,
        settings: DownloadSettings | None = None,
    ) -> None:
        self._on_event = on_event
        self._settings = settings
        self._limiter = SpeedLimiter()  # one limit for every download (M9); none by default
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, name="sdm-engine", daemon=True)
        self._semaphore = asyncio.Semaphore(max_concurrent)  # binds to the loop on first use
        # The following are touched only on the engine thread.
        self._tasks: dict[int, asyncio.Task[None]] = {}
        self._folders: dict[int, Path] = {}
        self._partials: dict[int, PartialDownload] = {}  # latest known partial file
        self._pausing: set[int] = set()
        self._ready = threading.Event()

    # ----- called from any thread -----

    def start(self) -> None:
        """Start the engine thread and wait until it is ready."""
        self._thread.start()
        self._ready.wait()

    def submit(
        self,
        download_id: int,
        url: str,
        folder: str | Path,
        policy: NetworkPolicy | None = None,
        resume_from: PartialDownload | None = None,
        context: BrowserContext | None = None,
    ) -> None:
        """Queue a download (or a resume). Events for it will carry `download_id`."""
        self._loop.call_soon_threadsafe(
            self._create_task,
            download_id,
            url,
            Path(folder),
            policy or NetworkPolicy(),
            resume_from,
            context,
        )

    def set_speed_limit(self, bytes_per_second: int | None) -> None:
        """Limit all downloads together (None or 0: no limit). Running downloads follow at once."""
        self._loop.call_soon_threadsafe(self._limiter.set_rate, bytes_per_second)

    def set_settings(self, settings: DownloadSettings) -> None:
        """Settings for downloads started from now on (e.g. connections per download)."""
        self._loop.call_soon_threadsafe(setattr, self, "_settings", settings)

    def pause(self, download_id: int) -> None:
        """Stop a waiting or running download but keep its partial file; Paused follows."""
        self._loop.call_soon_threadsafe(self._stop_task, download_id, True)

    def cancel(self, download_id: int) -> None:
        """Stop a waiting or running download and delete its partial file; Cancelled follows."""
        self._loop.call_soon_threadsafe(self._stop_task, download_id, False)

    def shutdown(self, timeout: float = 10.0) -> None:
        """Pause every download, wait for them to stop, then stop the engine thread."""
        if not self._thread.is_alive():
            return
        future = asyncio.run_coroutine_threadsafe(self._pause_all(), self._loop)
        try:
            future.result(timeout)
        except TimeoutError:
            log.warning("Downloads did not stop within %.0f s", timeout)
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout)

    # ----- engine thread -----

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.call_soon(self._ready.set)
        try:
            self._loop.run_forever()
        finally:
            self._loop.close()

    def _create_task(
        self,
        download_id: int,
        url: str,
        folder: Path,
        policy: NetworkPolicy,
        resume_from: PartialDownload | None,
        context: BrowserContext | None = None,
    ) -> None:
        if download_id in self._tasks:
            log.warning("Download %d was submitted twice; ignoring the second time", download_id)
            return
        self._folders[download_id] = folder
        if resume_from is not None:
            self._partials[download_id] = resume_from
        task = self._loop.create_task(
            self._run_one(download_id, url, folder, policy, resume_from, context),
            name=f"download-{download_id}",
        )
        task.add_done_callback(lambda done: self._task_done(download_id, done))
        self._tasks[download_id] = task

    def _task_done(self, download_id: int, task: asyncio.Task[None]) -> None:
        # Reported here rather than inside _run_one: a task cancelled before its first turn
        # never runs any of its code, so an `except CancelledError` there would never fire.
        self._tasks.pop(download_id, None)
        folder = self._folders.pop(download_id, None)
        partial = self._partials.pop(download_id, None)
        pausing = download_id in self._pausing
        self._pausing.discard(download_id)
        if not task.cancelled():
            return
        on_disk = partial is not None and partial.part_path.is_file()
        if pausing:
            self._emit(Paused(download_id, partial if on_disk else None))
            return
        if on_disk and folder is not None and is_own_part_file(partial.part_path, folder):
            try:
                partial.part_path.unlink()
            except OSError:
                log.warning("Couldn't delete the partial file of download %d", download_id)
        self._emit(Cancelled(download_id))

    def _stop_task(self, download_id: int, pause: bool) -> None:
        task = self._tasks.get(download_id)
        if task is None:
            return
        if pause:
            self._pausing.add(download_id)
        else:
            self._pausing.discard(download_id)
        task.cancel()

    async def _pause_all(self) -> None:
        tasks = list(self._tasks.items())
        for download_id, task in tasks:
            self._pausing.add(download_id)
            task.cancel()
        await asyncio.gather(*(task for _, task in tasks), return_exceptions=True)

    async def _run_one(
        self,
        download_id: int,
        url: str,
        folder: Path,
        policy: NetworkPolicy,
        resume_from: PartialDownload | None,
        context: BrowserContext | None = None,
    ) -> None:
        # Chunks arrive many times a second; the window only needs about 5 updates a second.
        # An update held back is sent when its 0.2 s is up, so the last numbers before the
        # server goes quiet still reach the window.
        last_sent = 0.0
        connections = 1
        latest: tuple[int, int | None] = (0, None)
        pending: asyncio.TimerHandle | None = None

        def send_latest() -> None:
            nonlocal last_sent, pending, connections
            pending = None
            last_sent = time.monotonic()
            self._emit(Progress(download_id, *latest, connections))

        def on_progress(received: int, total: int | None) -> None:
            nonlocal latest, pending
            latest = (received, total)
            if received == total:  # the last update goes out at once
                if pending is not None:
                    pending.cancel()
                send_latest()
            elif pending is None:
                wait = PROGRESS_INTERVAL - (time.monotonic() - last_sent)
                if wait <= 0:
                    send_latest()
                else:
                    pending = self._loop.call_later(wait, send_latest)

        def on_file_info(file_name: str, total: int | None) -> None:
            self._emit(FileInfo(download_id, file_name, total))

        def on_connections(count: int) -> None:
            nonlocal connections
            connections = count  # goes out with the next progress update

        def on_partial(partial: PartialDownload) -> None:
            self._partials[download_id] = partial
            self._emit(PartialSaved(download_id, partial))

        try:
            async with self._semaphore:  # wait here while 3 others are running
                self._emit(Started(download_id))
                result = await download(
                    url,
                    folder,
                    policy=policy,
                    settings=self._settings,
                    on_progress=on_progress,
                    on_file_info=on_file_info,
                    on_partial=on_partial,
                    resume_from=resume_from,
                    keep_partial=True,
                    on_connections=on_connections,
                    context=context,
                    limiter=self._limiter,
                )
        except SDMError as exc:
            partial = self._partials.get(download_id)
            kept = partial if partial is not None and partial.part_path.is_file() else None
            retryable = getattr(exc, "retryable", False)
            self._emit(Failed(download_id, str(exc), kept, retryable))
        except Exception as exc:  # a bug: report it rather than lose the download silently
            log.exception("Download %d failed unexpectedly", download_id)
            self._emit(Failed(download_id, f"Unexpected error: {type(exc).__name__}."))
        else:
            self._emit(Finished(download_id, result))
        finally:
            if pending is not None:  # never send progress after the final event
                pending.cancel()

    def _emit(self, event: DownloadEvent) -> None:
        try:
            self._on_event(event)
        except Exception:
            log.exception("The event handler failed for %s", event)
