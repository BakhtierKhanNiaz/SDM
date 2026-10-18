"""A split download paused and resumed through the controller, as the window does it (M5)."""

import hashlib
import os
from pathlib import Path

import pytest

from sdm.core.downloads import DownloadState
from sdm.engine.models import DownloadSettings
from sdm.storage.database import DownloadStore
from sdm.ui.controller import DownloadController

DATA = os.urandom(800_000)
SPLIT = DownloadSettings(
    connect_timeout=5.0,
    read_timeout=10.0,
    backoff_base=0.0,
    max_connections=4,
    min_split_size=200_000,
    min_part_size=100_000,
)


@pytest.fixture
def downloads(tmp_path) -> Path:
    folder = tmp_path / "downloads"
    folder.mkdir()
    return folder


@pytest.fixture
def split_controller(qapp, tmp_path, loopback_policy):
    made = []

    def make() -> DownloadController:
        store = DownloadStore(tmp_path / "sdm.db")
        controller = DownloadController(
            store, policy_for=lambda record: loopback_policy, settings=SPLIT
        )
        controller.start()
        made.append((controller, store))
        return controller

    yield make
    for controller, store in made:
        controller.shutdown()
        store.close()


def wait_for_state(qtbot, controller, download_id, state, timeout=15_000):
    qtbot.waitUntil(lambda: controller.store.get(download_id).state == state, timeout=timeout)


def test_pause_quit_restart_and_resume_a_split_download(
    qtbot, split_controller, mock_server, downloads
):
    mock_server.add("/data.bin", mock_server.ranged(DATA, etag='"v1"', rate=150_000))
    first = split_controller()
    record = first.add(mock_server.url("/data.bin"), downloads)
    qtbot.waitUntil(lambda: first.model.record(record.id).received_bytes >= 250_000, timeout=10_000)

    first.shutdown()  # quitting pauses it, keeping the parts map
    first.store.close()
    paused = DownloadStore(downloads.parent / "sdm.db")
    saved = paused.get(record.id)
    paused.close()
    assert saved.state == DownloadState.PAUSED
    partial = saved.partial()
    assert partial is not None and partial.segments is not None and len(partial.segments) == 4

    second = split_controller()  # SDM starts again
    second.resume(record.id)
    wait_for_state(qtbot, second, record.id, DownloadState.COMPLETED)

    done = second.store.get(record.id)
    assert hashlib.sha256(Path(done.path).read_bytes()).digest() == hashlib.sha256(DATA).digest()
    assert done.segments is None and done.part_path is None
