"""The DownloadManager: downloads on the engine thread, events, cancel, the 3-at-once limit."""

import hashlib
import os
import threading

import pytest

from sdm.engine.manager import (
    Cancelled,
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

DATA = os.urandom(300_000)
SETTINGS = DownloadSettings(connect_timeout=5.0, read_timeout=10.0, backoff_base=0.0)
TERMINAL = (Finished, Failed, Cancelled)


class Recorder:
    """Collects events (they arrive on the engine thread) and lets a test wait for them."""

    def __init__(self) -> None:
        self.events: list = []
        self.threads: set[str] = set()
        self._cond = threading.Condition()

    def __call__(self, event) -> None:
        with self._cond:
            self.events.append(event)
            self.threads.add(threading.current_thread().name)
            self._cond.notify_all()

    def wait_for(self, predicate, timeout: float = 15.0) -> None:
        with self._cond:
            ok = self._cond.wait_for(lambda: predicate(self.events), timeout)
        assert ok, f"timed out; events so far: {self.events}"

    def wait_done(self, *download_ids: int) -> None:
        self.wait_for(lambda events: all(self.terminal(i, events) for i in download_ids))

    @staticmethod
    def terminal(download_id, events):
        return next(
            (e for e in events if isinstance(e, TERMINAL) and e.download_id == download_id), None
        )

    def of(self, download_id: int) -> list:
        with self._cond:
            return [e for e in self.events if e.download_id == download_id]


@pytest.fixture
def recorder():
    return Recorder()


@pytest.fixture
def make_manager(recorder):
    managers = []

    def make(max_concurrent: int = 3) -> DownloadManager:
        manager = DownloadManager(recorder, max_concurrent=max_concurrent, settings=SETTINGS)
        manager.start()
        managers.append(manager)
        return manager

    yield make
    for manager in managers:
        manager.shutdown()


def test_reports_started_file_info_progress_and_finished(
    mock_server, make_manager, recorder, tmp_path, loopback_policy
):
    mock_server.add("/files/data.bin", mock_server.file(DATA))
    manager = make_manager()

    manager.submit(1, mock_server.url("/files/data.bin"), tmp_path, loopback_policy)
    recorder.wait_done(1)

    events = recorder.of(1)
    assert isinstance(events[0], Started)
    assert events[1] == FileInfo(1, "data.bin", len(DATA))
    progress = [e for e in events if isinstance(e, Progress)]
    assert progress and progress[-1] == Progress(1, len(DATA), len(DATA))
    finished = events[-1]
    assert isinstance(finished, Finished)
    assert (
        hashlib.sha256(finished.result.path.read_bytes()).digest() == hashlib.sha256(DATA).digest()
    )
    assert recorder.threads == {"sdm-engine"}  # events come from the engine thread


def test_failure_is_reported_with_a_readable_message(
    mock_server, make_manager, recorder, tmp_path, loopback_policy
):
    mock_server.add("/missing.zip", mock_server.status(404))
    manager = make_manager()

    manager.submit(1, mock_server.url("/missing.zip"), tmp_path, loopback_policy)
    recorder.wait_done(1)

    failed = recorder.of(1)[-1]
    assert isinstance(failed, Failed)
    assert "not found on the server" in failed.message


def test_default_policy_blocks_this_computer(mock_server, make_manager, recorder, tmp_path):
    mock_server.add("/f", mock_server.file(DATA))
    manager = make_manager()

    manager.submit(1, mock_server.url("/f"), tmp_path)  # no policy given: the safe default
    recorder.wait_done(1)

    assert "this computer" in recorder.of(1)[-1].message
    assert mock_server.hits["/f"] == 0


def test_cancelling_a_running_download_deletes_the_partial_file(
    mock_server, make_manager, recorder, tmp_path, loopback_policy
):
    mock_server.add("/slow", mock_server.stall(b"x" * 4096, declared_length=1_000_000, seconds=5))
    manager = make_manager()

    manager.submit(1, mock_server.url("/slow"), tmp_path, loopback_policy)
    recorder.wait_for(
        lambda events: any(isinstance(e, Progress) and e.received_bytes > 0 for e in events)
    )
    manager.cancel(1)
    recorder.wait_done(1)

    assert isinstance(recorder.of(1)[-1], Cancelled)
    assert list(tmp_path.iterdir()) == []


def test_cancelling_a_waiting_download(
    mock_server, make_manager, recorder, tmp_path, loopback_policy
):
    mock_server.add("/slow", mock_server.stall(b"x" * 4096, declared_length=1_000_000, seconds=5))
    mock_server.add("/f", mock_server.file(DATA))
    manager = make_manager(max_concurrent=1)

    manager.submit(1, mock_server.url("/slow"), tmp_path, loopback_policy)
    recorder.wait_for(lambda events: any(isinstance(e, Started) for e in events))
    manager.submit(2, mock_server.url("/f"), tmp_path, loopback_policy)
    manager.cancel(2)
    recorder.wait_done(2)

    assert recorder.of(2) == [Cancelled(2)]  # it never started
    assert mock_server.hits["/f"] == 0
    manager.cancel(1)
    recorder.wait_done(1)


def test_at_most_n_downloads_run_at_once(
    mock_server, make_manager, recorder, tmp_path, loopback_policy
):
    for n in range(4):
        mock_server.add(f"/f{n}.bin", mock_server.trickle(DATA, pieces=4, delay=0.1))
    manager = make_manager(max_concurrent=2)

    for n in range(4):
        manager.submit(n, mock_server.url(f"/f{n}.bin"), tmp_path, loopback_policy)
    recorder.wait_done(0, 1, 2, 3)

    running, most = 0, 0
    for event in recorder.events:
        if isinstance(event, Started):
            running += 1
            most = max(most, running)
        elif isinstance(event, TERMINAL):
            running -= 1
    assert most == 2  # never more than the limit, and the limit is really used
    assert all(isinstance(recorder.of(n)[-1], Finished) for n in range(4))


def test_shutdown_pauses_everything_and_stops_the_thread(
    mock_server, recorder, tmp_path, loopback_policy
):
    mock_server.add("/slow", mock_server.stall(b"x" * 4096, declared_length=1_000_000, seconds=5))
    manager = DownloadManager(recorder, settings=SETTINGS)
    manager.start()

    manager.submit(1, mock_server.url("/slow"), tmp_path, loopback_policy)
    recorder.wait_for(
        lambda events: any(isinstance(e, Progress) and e.received_bytes > 0 for e in events)
    )
    manager.shutdown()

    paused = recorder.of(1)[-1]
    assert isinstance(paused, Paused)  # M4: quitting pauses, so it can be resumed later
    assert paused.partial.part_path.read_bytes() == b"x" * 4096
    assert [p.name for p in tmp_path.iterdir()] == ["slow.sdmpart"]
    assert not any(t.name == "sdm-engine" for t in threading.enumerate())


def test_progress_catches_up_when_the_server_goes_quiet(
    mock_server, make_manager, recorder, tmp_path, loopback_policy
):
    # Regression: an update held back by the 0.2 s limit used to be lost if no more data came,
    # so the window showed 0 bytes while 4 KB had arrived.
    mock_server.add("/slow", mock_server.stall(b"x" * 4096, declared_length=1_000_000, seconds=5))
    manager = make_manager()

    manager.submit(1, mock_server.url("/slow"), tmp_path, loopback_policy)
    recorder.wait_for(lambda events: Progress(1, 4096, 1_000_000) in events, timeout=2.0)
    manager.cancel(1)
    recorder.wait_done(1)
    events = recorder.of(1)
    assert isinstance(events[-1], Cancelled)  # and nothing after it


# ----- M4: pause, resume, keep or delete partial files -----


def test_pause_keeps_the_partial_file_and_resume_finishes(
    mock_server, make_manager, recorder, tmp_path, loopback_policy
):
    log = []
    mock_server.add(
        "/data.bin",
        mock_server.ranged(DATA, etag='"v1"', stall_at=(100_000, 5), log=log),
        mock_server.ranged(DATA, etag='"v1"', log=log),
    )
    manager = make_manager()
    url = mock_server.url("/data.bin")

    manager.submit(1, url, tmp_path, loopback_policy)
    recorder.wait_for(
        lambda events: any(isinstance(e, Progress) and e.received_bytes >= 100_000 for e in events)
    )
    manager.pause(1)
    recorder.wait_for(lambda events: any(isinstance(e, Paused) for e in events))
    paused = recorder.of(1)[-1]
    assert isinstance(paused, Paused)
    assert paused.partial.part_path.read_bytes() == DATA[:100_000]
    assert any(isinstance(e, PartialSaved) for e in recorder.of(1))

    manager.submit(1, url, tmp_path, loopback_policy, resume_from=paused.partial)
    recorder.wait_for(lambda events: isinstance(events[-1], Finished))

    result = recorder.of(1)[-1].result
    assert hashlib.sha256(result.path.read_bytes()).digest() == hashlib.sha256(DATA).digest()
    assert log[1] == ("bytes=100000-", 206, 200_000)


def test_failed_download_keeps_its_partial_when_the_server_can_resume(
    mock_server, make_manager, recorder, tmp_path, loopback_policy
):
    cut = mock_server.ranged(DATA, etag='"v1"', cut_at=50_000)
    mock_server.add("/data.bin", cut, cut, cut)
    manager = make_manager()

    manager.submit(1, mock_server.url("/data.bin"), tmp_path, loopback_policy)
    recorder.wait_done(1)

    failed = recorder.of(1)[-1]
    assert isinstance(failed, Failed)
    assert failed.partial is not None
    assert failed.partial.part_path.read_bytes() == DATA[:150_000]


def test_cancelling_a_resumed_download_deletes_its_partial_file(
    mock_server, make_manager, recorder, tmp_path, loopback_policy
):
    from sdm.core.downloads import PartialDownload

    part = tmp_path / "data.bin.sdmpart"
    part.write_bytes(DATA[:100_000])
    partial = PartialDownload(part, "data.bin", len(DATA), '"v1"', None, True)
    mock_server.add("/data.bin", mock_server.ranged(DATA, etag='"v1"', stall_at=(1000, 5)))
    manager = make_manager()

    manager.submit(1, mock_server.url("/data.bin"), tmp_path, loopback_policy, resume_from=partial)
    recorder.wait_for(
        lambda events: any(isinstance(e, Progress) and e.received_bytes > 100_000 for e in events)
    )
    manager.cancel(1)
    recorder.wait_done(1)

    assert isinstance(recorder.of(1)[-1], Cancelled)
    assert list(tmp_path.iterdir()) == []


def test_pausing_a_waiting_download(mock_server, make_manager, recorder, tmp_path, loopback_policy):
    mock_server.add("/slow", mock_server.stall(b"x" * 4096, declared_length=1_000_000, seconds=5))
    mock_server.add("/f", mock_server.file(DATA))
    manager = make_manager(max_concurrent=1)

    manager.submit(1, mock_server.url("/slow"), tmp_path, loopback_policy)
    recorder.wait_for(lambda events: any(isinstance(e, Started) for e in events))
    manager.submit(2, mock_server.url("/f"), tmp_path, loopback_policy)
    manager.pause(2)
    recorder.wait_for(lambda events: Paused(2, None) in events)

    assert recorder.of(2) == [Paused(2, None)]  # never started, nothing to keep
    manager.cancel(1)
    recorder.wait_done(1)
