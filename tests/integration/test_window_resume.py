"""Pause, resume, retry and crash recovery through the controller (M4)."""

import hashlib
import os
from pathlib import Path

import pytest

from sdm.core.downloads import DownloadState, PartialDownload
from sdm.storage.database import DownloadStore

DATA = os.urandom(300_000)


@pytest.fixture
def downloads(tmp_path) -> Path:
    folder = tmp_path / "downloads"
    folder.mkdir()
    return folder


def wait_for_state(qtbot, controller, download_id, state, timeout=15_000):
    qtbot.waitUntil(lambda: controller.store.get(download_id).state == state, timeout=timeout)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def test_pause_then_resume(qtbot, make_controller, mock_server, downloads):
    log = []
    mock_server.add(
        "/data.bin",
        mock_server.ranged(DATA, etag='"v1"', stall_at=(100_000, 5), log=log),
        mock_server.ranged(DATA, etag='"v1"', log=log),
    )
    controller = make_controller()
    record = controller.add(mock_server.url("/data.bin"), downloads)
    qtbot.waitUntil(lambda: controller.model.record(record.id).received_bytes >= 100_000)

    controller.pause(record.id)
    wait_for_state(qtbot, controller, record.id, DownloadState.PAUSED)
    paused = controller.store.get(record.id)
    assert Path(paused.part_path).read_bytes() == DATA[:100_000]
    assert paused.received_bytes == 100_000
    assert paused.resumable is True

    controller.resume(record.id)
    wait_for_state(qtbot, controller, record.id, DownloadState.COMPLETED)

    done = controller.store.get(record.id)
    assert sha(Path(done.path).read_bytes()) == sha(DATA)
    assert done.part_path is None
    assert log[1] == ("bytes=100000-", 206, 200_000)


def test_cancelling_a_paused_download_deletes_its_partial(
    qtbot, make_controller, mock_server, downloads
):
    mock_server.add("/data.bin", mock_server.ranged(DATA, etag='"v1"', stall_at=(100_000, 5)))
    controller = make_controller()
    record = controller.add(mock_server.url("/data.bin"), downloads)
    qtbot.waitUntil(lambda: controller.model.record(record.id).received_bytes >= 100_000)
    controller.pause(record.id)
    wait_for_state(qtbot, controller, record.id, DownloadState.PAUSED)

    controller.cancel(record.id)

    assert controller.store.get(record.id).state == DownloadState.CANCELLED
    assert list(downloads.iterdir()) == []


def test_removing_a_paused_download_deletes_its_partial(
    qtbot, make_controller, mock_server, downloads
):
    mock_server.add("/data.bin", mock_server.ranged(DATA, etag='"v1"', stall_at=(100_000, 5)))
    controller = make_controller()
    record = controller.add(mock_server.url("/data.bin"), downloads)
    qtbot.waitUntil(lambda: controller.model.record(record.id).received_bytes >= 100_000)
    controller.pause(record.id)
    wait_for_state(qtbot, controller, record.id, DownloadState.PAUSED)

    controller.remove(record.id)

    assert controller.store.get(record.id) is None
    assert list(downloads.iterdir()) == []


def test_retry_after_a_failure_continues_where_it_stopped(
    qtbot, make_controller, mock_server, downloads
):
    log = []
    cut = mock_server.ranged(DATA, etag='"v1"', cut_at=50_000, log=log)
    mock_server.add("/data.bin", cut, cut, cut, mock_server.ranged(DATA, etag='"v1"', log=log))
    controller = make_controller()
    record = controller.add(mock_server.url("/data.bin"), downloads)
    wait_for_state(qtbot, controller, record.id, DownloadState.FAILED)
    failed = controller.store.get(record.id)
    assert "interrupted after" in failed.error
    assert failed.part_path is not None  # kept: this server can resume

    controller.resume(record.id)  # the window's Retry
    wait_for_state(qtbot, controller, record.id, DownloadState.COMPLETED)

    assert sha(Path(controller.store.get(record.id).path).read_bytes()) == sha(DATA)
    assert log[-1] == ("bytes=150000-", 206, 150_000)


def test_resume_after_a_crash(qtbot, make_controller, mock_server, downloads, tmp_path):
    # A previous run "crashed" with 100,000 bytes on disk and the entry still downloading.
    part = downloads / "data.bin.sdmpart"
    part.write_bytes(DATA[:100_000])
    crashed = DownloadStore(tmp_path / "sdm.db")
    download_id = crashed.add(mock_server.url("/data.bin"), str(downloads)).id
    crashed.mark_downloading(download_id)
    crashed.set_partial(
        download_id, PartialDownload(part, "data.bin", len(DATA), '"v1"', None, True)
    )
    crashed.close()
    log = []
    mock_server.add("/data.bin", mock_server.ranged(DATA, etag='"v1"', log=log))

    controller = make_controller(start=False)
    assert controller.store.mark_interrupted_on_startup() == 1
    controller.model.set_records(controller.store.list_all())
    controller.start()
    assert controller.resume_all() == 1
    wait_for_state(qtbot, controller, download_id, DownloadState.COMPLETED)

    assert sha((downloads / "data.bin").read_bytes()) == sha(DATA)
    assert log == [("bytes=100000-", 206, 200_000)]


def test_resume_all_skips_completed_and_running(qtbot, make_controller, mock_server, downloads):
    mock_server.add("/done.bin", mock_server.file(DATA))
    controller = make_controller()
    done = controller.add(mock_server.url("/done.bin"), downloads)
    wait_for_state(qtbot, controller, done.id, DownloadState.COMPLETED)

    assert controller.resume_all() == 0
    assert controller.store.get(done.id).state == DownloadState.COMPLETED
