"""Connects the history (DownloadStore), the engine (DownloadManager) and the table model.

It lives on the main thread. Engine events arrive here through EngineAdapter's queued signal,
so every database write happens on the main thread (ADR-0009).
"""

import logging
import time
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QObject, Signal

from sdm.core.downloads import DownloadRecord, DownloadState
from sdm.core.progress import TransferMeter
from sdm.core.urls import validate_url
from sdm.engine.http_download import is_own_part_file
from sdm.engine.manager import (
    Cancelled,
    DownloadEvent,
    DownloadManager,
    Failed,
    FileInfo,
    Finished,
    PartialSaved,
    Paused,
    Progress,
    Started,
)
from sdm.engine.models import DownloadSettings
from sdm.engine.policy import NetworkPolicy
from sdm.storage.database import DownloadStore
from sdm.ui.download_model import DownloadTableModel
from sdm.ui.engine_adapter import EngineAdapter

log = logging.getLogger(__name__)

SAVE_PROGRESS_EVERY = 1.0  # seconds between progress writes to the database, per download

PolicyFor = Callable[[DownloadRecord], NetworkPolicy]


def _default_policy(record: DownloadRecord) -> NetworkPolicy:
    return NetworkPolicy(allow_local_network=record.allow_local_network)


class DownloadController(QObject):
    summary_changed = Signal(str)  # one line for the status bar

    def __init__(
        self,
        store: DownloadStore,
        *,
        policy_for: PolicyFor = _default_policy,
        settings: DownloadSettings | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.store = store
        self.model = DownloadTableModel(self)
        self.model.set_records(store.list_all())
        self._policy_for = policy_for
        self._adapter = EngineAdapter(self)
        self._adapter.event_received.connect(self._on_event)
        self._manager = DownloadManager(self._adapter, settings=settings)
        self._meters: dict[int, TransferMeter] = {}
        self._latest: dict[int, int] = {}  # bytes received, for writes on the final event
        self._last_saved: dict[int, float] = {}
        self._running = False

    # ----- lifecycle -----

    def start(self) -> None:
        self._manager.start()
        self._running = True
        self._emit_summary()

    def shutdown(self) -> None:
        """Pause running downloads (partial files are kept), record it, stop the engine."""
        if not self._running:
            return
        self._running = False
        self._manager.shutdown()  # waits until every download has stopped
        QCoreApplication.processEvents()  # deliver the events the engine sent while stopping
        self._adapter.event_received.disconnect(self._on_event)
        for record in self.model.records():  # anything whose final event never arrived
            if record.state.is_active:
                self._save_latest(record.id)
                self._move(record.id, self.store.mark_paused)

    # ----- actions from the window -----

    def add(
        self, url: str, folder: str | Path, *, allow_local_network: bool = False
    ) -> DownloadRecord:
        """Add and start a download. Raises InvalidURLError for an unusable URL."""
        url = url.strip()
        validate_url(url)
        record = self.store.add(url, str(folder), allow_local_network=allow_local_network)
        self.model.upsert(record)
        self._manager.submit(record.id, record.url, record.folder, self._policy_for(record))
        self._emit_summary()
        return record

    def pause(self, download_id: int) -> None:
        """Stop a running or waiting download, keeping what has arrived."""
        record = self.model.record(download_id)
        if record is not None and record.state.is_active:
            self._manager.pause(download_id)

    def resume(self, download_id: int) -> None:
        """Continue a paused or interrupted download, or retry a failed one."""
        record = self.store.get(download_id)
        if record is None or not record.state.can_resume:
            return
        self._move(download_id, self.store.mark_queued)
        self._manager.submit(
            record.id,
            record.url,
            record.folder,
            self._policy_for(record),
            resume_from=record.partial(),
        )

    def resume_all(self) -> int:
        """Resume every paused and interrupted download; returns how many."""
        waiting = [
            r.id
            for r in self.model.records()
            if r.state in (DownloadState.PAUSED, DownloadState.INTERRUPTED)
        ]
        for download_id in waiting:
            self.resume(download_id)
        return len(waiting)

    def cancel(self, download_id: int) -> None:
        """Stop for good and delete the partial file (running, waiting or paused)."""
        record = self.store.get(download_id)
        if record is None:
            return
        if record.state.is_active:
            self._manager.cancel(download_id)  # a Cancelled event follows
        elif record.state.can_resume:
            self._delete_partial(record)
            self._move(download_id, self.store.mark_cancelled)

    def remove(self, download_id: int) -> None:
        """Remove an entry from the list. A finished file is kept; a partial file is deleted."""
        record = self.store.get(download_id)
        if record is not None and not record.state.is_active:
            self._delete_partial(record)
        self.store.remove(download_id)
        self.model.remove(download_id)
        self._emit_summary()

    def previous_downloads(self, url: str) -> list[DownloadRecord]:
        return self.store.completed_with_url(url.strip())

    def active_count(self) -> int:
        return sum(1 for record in self.model.records() if record.state.is_active)

    # ----- engine events (main thread) -----

    def _on_event(self, event: DownloadEvent) -> None:
        download_id = event.download_id
        match event:
            case Started():
                self._move(download_id, self.store.mark_downloading)
            case FileInfo(file_name=name, total_bytes=total):
                self._meters[download_id] = TransferMeter()  # a new attempt starts at 0
                self.store.set_file_info(download_id, name, total)
                self._refresh(download_id)
            case PartialSaved(partial=partial):
                self.store.set_partial(download_id, partial)
                self._refresh(download_id)  # the window needs `resumable` (Pause asks if not)
            case Progress(received_bytes=received, total_bytes=total):
                self._on_progress(download_id, received, total)
            case Finished(result=result):
                self._move(
                    download_id,
                    self.store.mark_completed,
                    path=str(result.path),
                    size=result.size,
                    verified_complete=result.verified_complete,
                )
            case Failed(message=message, partial=partial):
                self._save_latest(download_id)
                self._move(
                    download_id, self.store.mark_failed, message, partial_kept=partial is not None
                )
            case Paused():
                self._save_latest(download_id)
                self._move(download_id, self.store.mark_paused)
            case Cancelled():
                self._save_latest(download_id)
                self._move(download_id, self.store.mark_cancelled)

    def _on_progress(self, download_id: int, received: int, total: int | None) -> None:
        meter = self._meters.setdefault(download_id, TransferMeter())
        meter.update(received)
        self._latest[download_id] = received
        self.model.set_live(download_id, received, total, meter.speed, meter.time_left(total))
        now = time.monotonic()
        if now - self._last_saved.get(download_id, 0.0) >= SAVE_PROGRESS_EVERY:
            self._last_saved[download_id] = now
            self.store.set_progress(download_id, received)

    def _delete_partial(self, record: DownloadRecord) -> None:
        partial = record.partial()
        # The path comes from the database: only ever delete SDM's own file in that folder.
        if partial and is_own_part_file(partial.part_path, Path(record.folder)):
            try:
                partial.part_path.unlink(missing_ok=True)
            except OSError:
                log.warning("Couldn't delete the partial file of download %d", record.id)

    def _save_latest(self, download_id: int) -> None:
        if download_id in self._latest:
            self.store.set_progress(download_id, self._latest[download_id])

    def _move(self, download_id: int, mark: Callable, *args, **kwargs) -> None:
        try:
            mark(download_id, *args, **kwargs)
        except (ValueError, KeyError):  # e.g. an event for an entry removed meanwhile
            log.warning("Ignored an out-of-order event for download %d", download_id)
        record = self.store.get(download_id)
        if record is not None and not record.state.is_active:
            for table in (self._meters, self._latest, self._last_saved):
                table.pop(download_id, None)
        self._refresh(download_id)
        self._emit_summary()

    def _refresh(self, download_id: int) -> None:
        record = self.store.get(download_id)
        if record is None:
            return
        shown = self.model.record(download_id)
        if record.state == DownloadState.DOWNLOADING and shown is not None:
            # The database saves progress about once a second; keep the newer live count.
            record = replace(record, received_bytes=shown.received_bytes)
        self.model.upsert(record)

    def _emit_summary(self) -> None:
        self.summary_changed.emit(summarize(self.model.records()))


def summarize(records: list[DownloadRecord]) -> str:
    """Status-bar line, e.g. "2 downloading, 1 waiting, 1 paused · 5 completed"."""
    if not records:
        return "No downloads yet"
    count = {state: 0 for state in DownloadState}
    for record in records:
        count[record.state] += 1
    parts = []
    if count[DownloadState.DOWNLOADING]:
        parts.append(f"{count[DownloadState.DOWNLOADING]} downloading")
    if count[DownloadState.QUEUED]:
        parts.append(f"{count[DownloadState.QUEUED]} waiting")
    if count[DownloadState.PAUSED]:
        parts.append(f"{count[DownloadState.PAUSED]} paused")
    done = f"{count[DownloadState.COMPLETED]} completed"
    return f"{', '.join(parts)} · {done}" if parts else f"Ready · {done}"
