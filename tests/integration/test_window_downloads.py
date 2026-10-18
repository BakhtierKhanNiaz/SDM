"""Downloads through the controller and the window, against the local mock server."""

import hashlib
import os
from pathlib import Path

import pytest

from sdm.core.downloads import DownloadState
from sdm.core.errors import InvalidURLError
from sdm.storage.database import INTERRUPTED_MESSAGE, DownloadStore
from sdm.ui import main_window as main_window_module
from sdm.ui.download_model import SPEED, STATUS
from sdm.ui.main_window import MainWindow

DATA = os.urandom(300_000)


@pytest.fixture
def downloads(tmp_path) -> Path:
    folder = tmp_path / "downloads"
    folder.mkdir()
    return folder


@pytest.fixture
def make_window(qtbot, downloads):
    def make(controller) -> MainWindow:
        window = MainWindow(controller, default_folder=downloads)
        window.confirm_quit = lambda active: True  # a test may override this
        qtbot.addWidget(window)
        return window

    return make


def wait_for_state(qtbot, controller, download_id, state, timeout=15_000):
    qtbot.waitUntil(lambda: controller.store.get(download_id).state == state, timeout=timeout)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def test_download_completes_and_is_recorded(qtbot, make_controller, mock_server, downloads):
    mock_server.add("/files/data.bin", mock_server.file(DATA))
    controller = make_controller()

    record = controller.add(mock_server.url("/files/data.bin"), downloads)
    wait_for_state(qtbot, controller, record.id, DownloadState.COMPLETED)

    saved = controller.store.get(record.id)
    assert saved.file_name == "data.bin"
    assert saved.total_bytes == saved.received_bytes == len(DATA)
    assert saved.verified_complete is True
    assert sha256(Path(saved.path).read_bytes()) == sha256(DATA)
    model = controller.model
    assert model.data(model.index(0, STATUS)) == "Completed"


def test_live_progress_and_speed_reach_the_table(qtbot, make_controller, mock_server, downloads):
    mock_server.add("/slow.bin", mock_server.trickle(DATA, pieces=12, delay=0.15))  # about 1.8 s
    controller = make_controller()
    model = controller.model

    record = controller.add(mock_server.url("/slow.bin"), downloads)

    qtbot.waitUntil(lambda: 0 < model.record(record.id).received_bytes < len(DATA), timeout=5_000)
    qtbot.waitUntil(lambda: model.data(model.index(0, SPEED)) != "", timeout=5_000)
    wait_for_state(qtbot, controller, record.id, DownloadState.COMPLETED)
    assert model.data(model.index(0, SPEED)) == ""  # cleared once finished


def test_failure_is_recorded_with_its_message(qtbot, make_controller, mock_server, downloads):
    mock_server.add("/missing.zip", mock_server.status(404))
    controller = make_controller()

    record = controller.add(mock_server.url("/missing.zip"), downloads)
    wait_for_state(qtbot, controller, record.id, DownloadState.FAILED)

    assert "not found on the server" in controller.store.get(record.id).error


def test_cancel_then_remove_from_the_window(
    qtbot, make_controller, make_window, mock_server, downloads
):
    mock_server.add("/slow", mock_server.stall(b"x" * 4096, declared_length=1_000_000, seconds=5))
    controller = make_controller()
    window = make_window(controller)

    record = controller.add(mock_server.url("/slow"), downloads)
    qtbot.waitUntil(lambda: controller.model.record(record.id).received_bytes == 4096)
    window.download_table.selectRow(0)
    assert window.cancel_action.isEnabled()
    assert not window.remove_action.isEnabled()

    window.cancel_action.trigger()
    wait_for_state(qtbot, controller, record.id, DownloadState.CANCELLED)
    assert list(downloads.iterdir()) == []  # the partial file is gone
    qtbot.waitUntil(window.remove_action.isEnabled)

    window.remove_action.trigger()
    assert controller.model.rowCount() == 0
    assert controller.store.get(record.id) is None


def test_three_at_once_the_rest_wait(qtbot, make_controller, mock_server, downloads):
    for n in range(4):
        mock_server.add(f"/f{n}.bin", mock_server.trickle(DATA, pieces=10, delay=0.2))
    controller = make_controller()
    summaries = []
    controller.summary_changed.connect(summaries.append)

    ids = [controller.add(mock_server.url(f"/f{n}.bin"), downloads).id for n in range(4)]

    def states():
        return [controller.model.record(i).state for i in ids]

    qtbot.waitUntil(lambda: states().count(DownloadState.DOWNLOADING) == 3, timeout=5_000)
    assert states().count(DownloadState.QUEUED) == 1
    assert "3 downloading, 1 waiting · 0 completed" in summaries
    for download_id in ids:
        wait_for_state(qtbot, controller, download_id, DownloadState.COMPLETED)


def test_history_survives_a_restart(qtbot, make_controller, mock_server, downloads):
    mock_server.add("/a.zip", mock_server.file(DATA))
    first = make_controller(db_name="history.db")
    record = first.add(mock_server.url("/a.zip"), downloads)
    wait_for_state(qtbot, first, record.id, DownloadState.COMPLETED)
    first.shutdown()
    first.store.close()

    second = make_controller(db_name="history.db")

    restored = second.model.record(record.id)
    assert restored.state == DownloadState.COMPLETED
    assert restored.file_name == "a.zip"


def test_a_crash_leaves_entries_interrupted(qtbot, make_controller, tmp_path):
    crashed = DownloadStore(tmp_path / "sdm.db")
    download_id = crashed.add("https://example.com/big.iso", "D:\\Downloads").id
    crashed.mark_downloading(download_id)
    crashed.close()  # SDM "crashed" mid-download

    controller = make_controller(start=False)
    assert controller.store.mark_interrupted_on_startup() == 1
    controller.model.set_records(controller.store.list_all())

    model = controller.model
    assert model.data(model.index(0, STATUS)) == "Interrupted"
    assert controller.store.get(download_id).error == INTERRUPTED_MESSAGE


def test_closing_with_downloads_running_asks_first(
    qtbot, make_controller, make_window, mock_server, downloads
):
    mock_server.add("/slow", mock_server.stall(b"x" * 4096, declared_length=1_000_000, seconds=5))
    controller = make_controller()
    window = make_window(controller)
    window.show()
    record = controller.add(mock_server.url("/slow"), downloads)
    qtbot.waitUntil(lambda: controller.model.record(record.id).received_bytes == 4096)

    asked = []
    window.confirm_quit = lambda active: asked.append(active) or False  # "No"
    window.close()
    assert window.isVisible()
    assert asked == [1]
    assert controller.store.get(record.id).state == DownloadState.DOWNLOADING

    window.confirm_quit = lambda active: True  # "Yes"
    window.close()
    assert not window.isVisible()
    saved = controller.store.get(record.id)
    assert saved.state == DownloadState.PAUSED  # M4: quitting pauses; resume next time
    assert [p.name for p in downloads.iterdir()] == ["slow.sdmpart"]
    assert Path(saved.part_path) == downloads / "slow.sdmpart"


def test_unsafe_urls_are_refused_before_anything_is_saved(
    make_controller, make_window, downloads, monkeypatch
):
    controller = make_controller()
    with pytest.raises(InvalidURLError):
        controller.add("file:///C:/Windows/win.ini", downloads)
    assert controller.store.list_all() == []

    shown = []
    monkeypatch.setattr(
        main_window_module.QMessageBox, "warning", lambda parent, title, text: shown.append(text)
    )
    make_window(controller).add_download("ftp://example.com/x.zip", downloads)
    assert "Only http:// and https://" in shown[0]
    assert controller.store.list_all() == []
