"""Runs yt-dlp for video-page downloads (M12b, ADR-0020) and reports what happens as the same
events the download engine sends (Started, FileInfo, Progress, Finished, Failed, Paused,
Cancelled), so the controller treats a video like any other download: the queue, pause and
resume, the history, notifications.

Pause stops yt-dlp and keeps its work folder; resuming starts it again there and yt-dlp
continues its partial files. Cancel stops it and deletes the work folder. Before yt-dlp starts,
the page's host must pass SDM's network policy (ADR-0007); yt-dlp's own later requests can't be
checked (ADR-0020).
"""

import ipaddress
import logging
import re
import shutil
import socket
import subprocess
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from PySide6.QtCore import QObject, QProcess, Signal

from sdm.core.downloads import DownloadRecord
from sdm.core.errors import BlockedDestinationError
from sdm.engine.manager import (
    Cancelled,
    DownloadEvent,
    Failed,
    FileInfo,
    Finished,
    Paused,
    Progress,
    Started,
)
from sdm.engine.models import DownloadResult
from sdm.engine.policy import NetworkPolicy
from sdm.media.ytdlp import (
    INSTALL_HINT,
    QUALITIES,
    VideoProgress,
    final_path,
    finished_media,
    is_own_work_folder,
    work_folder,
    ytdlp_arguments,
)

log = logging.getLogger(__name__)
MAX_MESSAGE_LENGTH = 300


@dataclass
class _Job:
    record: DownloadRecord
    command: list[str]
    ffmpeg: Path | None
    work: Path
    process: QProcess | None = None
    progress: VideoProgress = field(default_factory=VideoProgress)
    rest: str = ""  # an unfinished output line
    stopping: str | None = None  # "pause" or "cancel" once the user asked


def remove_work_folder(work: Path, folder: Path) -> None:
    """Delete a video's work folder, but only SDM's own ".sdm-video-<id>" in that folder."""
    if is_own_work_folder(work, folder) and work.is_dir():
        shutil.rmtree(work, ignore_errors=True)
        if work.exists():
            log.warning("Couldn't delete all of %s", work.name)


def _display_name(part_name: str, quality_key: str) -> str:
    """The finished file's likely name from the part yt-dlp is writing: "Title [id].f137.mp4"
    becomes "Title [id].mp4" (or .mp3/.m4a for audio)."""
    stem = re.sub(r"\.f\d+$", "", Path(part_name).stem)
    extension = f".{quality_key}" if quality_key in ("mp3", "m4a") else ".mp4"
    return stem + extension


class VideoRunner(QObject):
    # The engine's event types. Connect it queued, as the engine's events arrive: the
    # controller then never handles an event in the middle of starting a download.
    event = Signal(object)
    _resolved = Signal(int, object)  # lookup thread -> main thread: addresses or an error

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._deliver: Callable[[DownloadEvent], None] = self.event.emit
        self._jobs: dict[int, _Job] = {}
        self._lookups = ThreadPoolExecutor(max_workers=2, thread_name_prefix="sdm-video-dns")
        self._resolved.connect(self._on_resolved)
        self._policies: dict[int, NetworkPolicy] = {}

    def owns(self, download_id: int) -> bool:
        return download_id in self._jobs

    def start(
        self,
        record: DownloadRecord,
        *,
        command: list[str],
        ffmpeg: Path | None,
        policy: NetworkPolicy,
    ) -> None:
        """Start (or continue) a video download. `command` runs yt-dlp."""
        download_id = record.id
        work = work_folder(Path(record.folder), download_id)
        self._jobs[download_id] = _Job(record, command, ffmpeg, work)
        self._deliver(Started(download_id))
        if record.video not in QUALITIES:
            self._fail(download_id, "This video download has no valid quality.")
            return
        host = urlsplit(record.url).hostname or ""
        try:
            policy.check_url_host(host)
        except BlockedDestinationError as exc:
            self._fail(download_id, str(exc))
            return
        try:
            ipaddress.ip_address(host.split("%", 1)[0])
        except ValueError:  # a host name: look it up off the main thread, then check it
            self._policies[download_id] = policy
            self._lookups.submit(self._lookup, download_id, host)
            return
        self._spawn(download_id)

    def _lookup(self, download_id: int, host: str) -> None:
        """Runs on a lookup thread."""
        try:
            infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
            result: object = [info[4][0] for info in infos]
        except OSError as exc:
            result = exc
        try:
            self._resolved.emit(download_id, result)
        except RuntimeError:  # SDM closed meanwhile
            pass

    def _on_resolved(self, download_id: int, result: object) -> None:
        job = self._jobs.get(download_id)
        policy = self._policies.pop(download_id, None)
        if job is None or policy is None:
            return
        if job.stopping:  # paused or cancelled while looking up
            self._stopped(job)
            return
        host = urlsplit(job.record.url).hostname or ""
        if isinstance(result, OSError):
            self._fail(download_id, f"Couldn't find the server {host}.")
            return
        try:
            for address in result:
                policy.check_ip(address, host)
        except BlockedDestinationError as exc:
            self._fail(download_id, str(exc))
            return
        self._spawn(download_id)

    def _spawn(self, download_id: int) -> None:
        job = self._jobs[download_id]
        try:
            job.work.mkdir(exist_ok=True)
        except OSError as exc:
            self._fail(download_id, f"Couldn't create a folder for the video: {exc.strerror}")
            return
        quality = QUALITIES[job.record.video]
        process = QProcess(self)
        process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        process.setProgram(job.command[0])
        process.setArguments(
            [*job.command[1:],
             *ytdlp_arguments(job.record.url, quality, job.work, ffmpeg=job.ffmpeg)]
        )  # fmt: skip
        process.readyReadStandardOutput.connect(lambda: self._read(download_id))
        process.finished.connect(lambda code, status: self._finished(download_id, code, status))
        process.errorOccurred.connect(lambda error: self._error(download_id, error))
        job.process = process
        process.start()

    def _read(self, download_id: int) -> None:
        job = self._jobs.get(download_id)
        if job is None or job.process is None:
            return
        text = job.rest + bytes(job.process.readAllStandardOutput().data()).decode(
            "utf-8", errors="replace"
        )
        *lines, job.rest = text.replace("\r", "\n").split("\n")
        for line in lines:
            kind = job.progress.line(line)
            if kind == "part" and job.progress.part_name:
                name = _display_name(job.progress.part_name, job.record.video or "")
                self._deliver(FileInfo(download_id, name, None))
            elif kind == "progress":
                self._deliver(Progress(download_id, job.progress.received, job.progress.total))

    def _finished(self, download_id: int, exit_code: int, status: QProcess.ExitStatus) -> None:
        job = self._jobs.get(download_id)
        if job is None:
            return
        self._read(download_id)
        if job.stopping:
            self._stopped(job)
            return
        media = finished_media(job.work)
        if status == QProcess.ExitStatus.NormalExit and exit_code == 0 and media is not None:
            folder = Path(job.record.folder)
            try:
                target = final_path(folder, media.name)
                media.replace(target)  # same drive: the work folder is inside the folder
            except OSError as exc:
                self._fail(download_id, f"Couldn't move the finished video: {exc.strerror}")
                return
            remove_work_folder(job.work, folder)
            del self._jobs[download_id]
            size = target.stat().st_size
            self._deliver(Finished(download_id, DownloadResult(
                path=target, size=size, final_url=job.record.url, content_type=None,
                verified_complete=True,
            )))  # fmt: skip
            return
        reason = job.progress.failure_reason or f"yt-dlp stopped (exit code {exit_code})."
        self._fail(download_id, reason)

    def _error(self, download_id: int, error: QProcess.ProcessError) -> None:
        job = self._jobs.get(download_id)
        if job is None or error != QProcess.ProcessError.FailedToStart:
            return  # a crash also ends in finished(), which reports it
        self._fail(download_id, f"yt-dlp couldn't be started. {INSTALL_HINT}")

    def _fail(self, download_id: int, message: str) -> None:
        # The work folder stays, so a retry continues from yt-dlp's partial files; an empty
        # one (nothing arrived, e.g. a missing page) is only clutter in the folder.
        job = self._jobs.pop(download_id, None)
        if job is not None:
            try:
                job.work.rmdir()  # only succeeds while it is empty
            except OSError:
                pass
        self._policies.pop(download_id, None)
        self._deliver(Failed(download_id, message[:MAX_MESSAGE_LENGTH]))

    # ----- the user's actions -----

    def pause(self, download_id: int) -> None:
        self._stop(download_id, "pause")

    def cancel(self, download_id: int) -> None:
        self._stop(download_id, "cancel")

    def _stop(self, download_id: int, how: str) -> None:
        job = self._jobs.get(download_id)
        if job is None or job.stopping:
            return
        job.stopping = how
        if job.process is None:
            if download_id not in self._policies:  # not waiting for a lookup either
                self._stopped(job)
            return  # the lookup's answer finishes it
        _kill_tree(job.process)  # finished() follows and reports it

    def _stopped(self, job: _Job) -> None:
        download_id = job.record.id
        self._jobs.pop(download_id, None)
        if job.stopping == "cancel":
            remove_work_folder(job.work, Path(job.record.folder))
            self._deliver(Cancelled(download_id))
        else:
            self._deliver(Paused(download_id, None))

    def shutdown(self) -> None:
        """Pause everything (SDM is closing); waits until yt-dlp has stopped."""
        self._lookups.shutdown(wait=False, cancel_futures=True)
        for download_id, job in list(self._jobs.items()):
            job.stopping = "pause"
            if job.process is not None:
                _kill_tree(job.process)
                job.process.waitForFinished(5000)
            if download_id in self._jobs:
                self._stopped(job)


def _kill_tree(process: QProcess) -> None:
    """Stop yt-dlp and the ffmpeg it may have started (merging), so no file stays locked."""
    pid = process.processId()
    if pid:
        subprocess.run(  # noqa: S603 - fixed Windows program, a number as argument
            ["taskkill", "/F", "/T", "/PID", str(pid)],  # noqa: S607
            capture_output=True,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    process.kill()
