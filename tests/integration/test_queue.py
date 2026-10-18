"""The queue through the controller (M6): order, limit, schedule, Start now, automatic retries.

A fake clock drives the schedule and the retry times, so nothing here waits for real minutes.
"""

import os
from datetime import datetime, time, timedelta
from pathlib import Path

import pytest

from sdm.core.downloads import DownloadState
from sdm.engine.models import DownloadSettings
from sdm.scheduler.queue import QueueSettings, Schedule
from sdm.storage.database import DownloadStore
from sdm.ui.controller import DownloadController

DATA = os.urandom(200_000)
FAST = DownloadSettings(connect_timeout=5.0, read_timeout=10.0, backoff_base=0.0)
NIGHT = Schedule(True, time(1, 0), time(6, 0))  # open 01:00-06:00 every day


class FakeClock:
    def __init__(self) -> None:
        self.now = datetime(2026, 10, 19, 12, 0).astimezone()  # Monday noon

    def __call__(self) -> datetime:
        return self.now

    def set(self, hour: int, minute: int = 0) -> None:
        self.now = self.now.replace(hour=hour, minute=minute)


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def downloads(tmp_path) -> Path:
    folder = tmp_path / "downloads"
    folder.mkdir()
    return folder


@pytest.fixture
def queue(qapp, tmp_path, loopback_policy, clock):
    made = []

    def make() -> DownloadController:
        store = DownloadStore(tmp_path / "sdm.db")
        controller = DownloadController(
            store, policy_for=lambda r: loopback_policy, settings=FAST, clock=clock
        )
        controller.start()
        made.append((controller, store))
        return controller

    yield make
    for controller, store in made:
        controller.shutdown()
        store.close()


def state(controller, download_id):
    return controller.store.get(download_id).state


def wait_for(qtbot, controller, download_id, wanted, timeout=15_000):
    qtbot.waitUntil(lambda: state(controller, download_id) == wanted, timeout=timeout)


def slow(mock_server, path, seconds=5):
    """A resumable route that sends half the data, then goes quiet (keeps a download running)."""
    mock_server.add(path, mock_server.ranged(DATA, etag='"v1"', stall_at=(100_000, seconds)))


def hits(mock_server, path) -> int:
    return mock_server.hits[path]


# ----- order and limit -----


def test_limit_and_queue_order(qtbot, queue, mock_server, downloads):
    for name in ("a", "b", "c"):
        slow(mock_server, f"/{name}.bin")
    controller = queue()
    controller.set_queue_settings(QueueSettings(limit=1))
    a, b, c = (controller.add(mock_server.url(f"/{n}.bin"), downloads).id for n in "abc")

    wait_for(qtbot, controller, a, DownloadState.DOWNLOADING)
    assert state(controller, b) == state(controller, c) == DownloadState.QUEUED
    controller.move(c, "top")  # c should be next
    controller.cancel(a)

    wait_for(qtbot, controller, c, DownloadState.DOWNLOADING)
    assert state(controller, b) == DownloadState.QUEUED
    assert hits(mock_server, "/b.bin") == 0


def test_raising_the_limit_starts_more_at_once(qtbot, queue, mock_server, downloads):
    for name in ("a", "b"):
        slow(mock_server, f"/{name}.bin")
    controller = queue()
    controller.set_queue_settings(QueueSettings(limit=1))
    a, b = (controller.add(mock_server.url(f"/{n}.bin"), downloads).id for n in "ab")
    wait_for(qtbot, controller, a, DownloadState.DOWNLOADING)

    controller.set_queue_settings(QueueSettings(limit=2))

    wait_for(qtbot, controller, b, DownloadState.DOWNLOADING)


def test_lowering_the_limit_sends_the_last_back_to_waiting(qtbot, queue, mock_server, downloads):
    for name in ("a", "b"):
        slow(mock_server, f"/{name}.bin")
    controller = queue()
    a, b = (controller.add(mock_server.url(f"/{n}.bin"), downloads).id for n in "ab")
    qtbot.waitUntil(lambda: controller.model.record(b).received_bytes >= 100_000)

    controller.set_queue_settings(QueueSettings(limit=1))

    qtbot.waitUntil(lambda: controller.store.get(b).part_path is not None)
    wait_for(qtbot, controller, b, DownloadState.QUEUED)  # waiting, not paused
    assert state(controller, a) == DownloadState.DOWNLOADING
    assert Path(controller.store.get(b).part_path).stat().st_size == 100_000  # kept


# ----- the schedule -----


def test_schedule_starts_and_stops_the_queue(qtbot, queue, mock_server, downloads, clock):
    slow(mock_server, "/a.bin", seconds=8)
    controller = queue()
    controller.set_queue_settings(QueueSettings(schedule=NIGHT))  # noon: closed
    a = controller.add(mock_server.url("/a.bin"), downloads).id
    controller.pump()
    assert state(controller, a) == DownloadState.QUEUED
    assert hits(mock_server, "/a.bin") == 0

    clock.set(1, 0)  # the window opens
    controller.pump()
    qtbot.waitUntil(lambda: controller.model.record(a).received_bytes >= 100_000)

    clock.set(6, 0)  # the window closes
    controller.pump()
    wait_for(qtbot, controller, a, DownloadState.QUEUED)
    assert controller.store.get(a).part_path is not None  # resumes at the next start


def test_start_now_ignores_a_closed_schedule(qtbot, queue, mock_server, downloads):
    mock_server.add("/a.bin", mock_server.ranged(DATA, etag='"v1"'))
    controller = queue()
    controller.set_queue_settings(QueueSettings(schedule=NIGHT))
    a = controller.add(mock_server.url("/a.bin"), downloads).id
    assert state(controller, a) == DownloadState.QUEUED

    controller.start_now(a)

    wait_for(qtbot, controller, a, DownloadState.COMPLETED)
    assert Path(controller.store.get(a).path).read_bytes() == DATA


# ----- automatic retries -----


def test_temporary_failure_retries_automatically(qtbot, queue, mock_server, downloads, clock):
    down = mock_server.status(503)
    mock_server.add("/a.bin", down, down, down, mock_server.ranged(DATA, etag='"v1"'))
    controller = queue()
    a = controller.add(mock_server.url("/a.bin"), downloads).id

    qtbot.waitUntil(lambda: controller.store.get(a).retry_count == 1, timeout=15_000)
    assert state(controller, a) == DownloadState.QUEUED
    controller.pump()
    assert hits(mock_server, "/a.bin") == 3  # not before its time

    clock.now += timedelta(seconds=61)
    controller.pump()

    wait_for(qtbot, controller, a, DownloadState.COMPLETED)
    assert Path(controller.store.get(a).path).read_bytes() == DATA


def test_missing_file_is_not_retried(qtbot, queue, mock_server, downloads):
    mock_server.add("/missing.zip", mock_server.status(404))
    controller = queue()
    a = controller.add(mock_server.url("/missing.zip"), downloads).id

    wait_for(qtbot, controller, a, DownloadState.FAILED)
    assert controller.store.get(a).retry_count == 0


def test_after_three_retries_it_stays_failed(qtbot, queue, mock_server, downloads, clock):
    mock_server.add("/a.bin", mock_server.status(503))
    controller = queue()
    a = controller.add(mock_server.url("/a.bin"), downloads).id
    for expected in (1, 2, 3):
        qtbot.waitUntil(lambda e=expected: controller.store.get(a).retry_count == e, timeout=15_000)
        clock.now += timedelta(minutes=16)
        controller.pump()

    wait_for(qtbot, controller, a, DownloadState.FAILED)
    assert controller.store.get(a).retry_count == 3


# ----- adding, categories, settings -----


def test_add_without_starting(qtbot, queue, mock_server, downloads):
    mock_server.add("/a.bin", mock_server.ranged(DATA, etag='"v1"'))
    controller = queue()
    a = controller.add(mock_server.url("/a.bin"), downloads, start=False).id
    controller.pump()
    assert state(controller, a) == DownloadState.PAUSED
    assert hits(mock_server, "/a.bin") == 0

    controller.resume(a)
    wait_for(qtbot, controller, a, DownloadState.COMPLETED)


def test_category_and_optional_subfolder(qtbot, queue, mock_server, downloads):
    mock_server.add("/pack.zip", mock_server.ranged(DATA, etag='"v1"'))
    controller = queue()
    controller.set_queue_settings(QueueSettings(category_subfolders=True))
    a = controller.add(mock_server.url("/pack.zip"), downloads).id

    wait_for(qtbot, controller, a, DownloadState.COMPLETED)
    record = controller.store.get(a)
    assert record.category == "Compressed"
    assert Path(record.path) == downloads / "Compressed" / "pack.zip"


def test_subfolders_are_off_by_default(qtbot, queue, mock_server, downloads):
    mock_server.add("/pack.zip", mock_server.ranged(DATA, etag='"v1"'))
    controller = queue()
    a = controller.add(mock_server.url("/pack.zip"), downloads).id
    wait_for(qtbot, controller, a, DownloadState.COMPLETED)
    assert Path(controller.store.get(a).path) == downloads / "pack.zip"


def test_queue_settings_survive_a_restart(queue):
    first = queue()
    first.set_queue_settings(QueueSettings(limit=5, schedule=NIGHT))
    first.shutdown()
    first.store.close()

    second = queue()
    assert second.queue_settings == QueueSettings(limit=5, schedule=NIGHT)
