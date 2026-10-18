"""The window's Pause, Resume, Resume all and Cancel buttons (M4b)."""

import hashlib
import os
from pathlib import Path

import pytest
from PySide6.QtCore import Qt

from sdm.core.downloads import DownloadState
from sdm.ui import main_window as main_window_module
from sdm.ui.controller import summarize
from sdm.ui.download_model import STATUS
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
        window.confirm_quit = lambda active: True
        qtbot.addWidget(window)
        return window

    return make


def wait_for_state(qtbot, controller, download_id, state, timeout=15_000):
    qtbot.waitUntil(lambda: controller.store.get(download_id).state == state, timeout=timeout)


def test_pause_and_resume_buttons(qtbot, make_controller, make_window, mock_server, downloads):
    mock_server.add(
        "/data.bin",
        mock_server.ranged(DATA, etag='"v1"', stall_at=(100_000, 5)),
        mock_server.ranged(DATA, etag='"v1"'),
    )
    controller = make_controller()
    window = make_window(controller)
    record = controller.add(mock_server.url("/data.bin"), downloads)
    qtbot.waitUntil(lambda: controller.model.record(record.id).received_bytes >= 100_000)
    window.download_table.selectRow(0)
    assert window.pause_action.isEnabled()
    assert not window.resume_action.isEnabled()

    window.pause_action.trigger()
    wait_for_state(qtbot, controller, record.id, DownloadState.PAUSED)
    qtbot.waitUntil(window.resume_action.isEnabled)
    assert not window.pause_action.isEnabled()
    assert window.cancel_action.isEnabled()  # a paused download can still be discarded
    assert window.resume_all_action.isEnabled()
    tooltip = controller.model.data(controller.model.index(0, STATUS), Qt.ItemDataRole.ToolTipRole)
    assert "continues from where it stopped" in tooltip

    window.resume_action.trigger()
    wait_for_state(qtbot, controller, record.id, DownloadState.COMPLETED)
    saved = Path(controller.store.get(record.id).path)
    assert hashlib.sha256(saved.read_bytes()).digest() == hashlib.sha256(DATA).digest()


def test_pausing_on_a_server_that_cant_resume_asks_first(
    qtbot, make_controller, make_window, mock_server, downloads
):
    # stall: no Accept-Ranges, so the server can't resume.
    mock_server.add("/slow", mock_server.stall(b"x" * 4096, declared_length=1_000_000, seconds=5))
    controller = make_controller()
    window = make_window(controller)
    record = controller.add(mock_server.url("/slow"), downloads)
    qtbot.waitUntil(lambda: controller.model.record(record.id).received_bytes == 4096)
    window.download_table.selectRow(0)

    asked = []
    window.confirm_pause_unresumable = lambda: asked.append(True) or False  # "No"
    window.pause_action.trigger()
    assert asked == [True]
    assert controller.store.get(record.id).state == DownloadState.DOWNLOADING

    window.confirm_pause_unresumable = lambda: True  # "Yes"
    window.pause_action.trigger()
    wait_for_state(qtbot, controller, record.id, DownloadState.PAUSED)


def test_failed_download_offers_retry(qtbot, make_controller, make_window, mock_server, downloads):
    mock_server.add("/missing.zip", mock_server.status(404))
    controller = make_controller()
    window = make_window(controller)
    record = controller.add(mock_server.url("/missing.zip"), downloads)
    wait_for_state(qtbot, controller, record.id, DownloadState.FAILED)

    window.download_table.selectRow(0)

    assert window.resume_action.isEnabled()
    assert window.resume_action.text() == "R&etry"


def test_resume_all_button(qtbot, make_controller, make_window, mock_server, downloads):
    for name in ("a.bin", "b.bin"):
        mock_server.add(
            f"/{name}",
            mock_server.ranged(DATA, etag='"v1"', stall_at=(100_000, 5)),
            mock_server.ranged(DATA, etag='"v1"'),
        )
    controller = make_controller()
    window = make_window(controller)
    ids = [controller.add(mock_server.url(f"/{n}"), downloads).id for n in ("a.bin", "b.bin")]
    for download_id in ids:
        qtbot.waitUntil(lambda i=download_id: controller.model.record(i).received_bytes >= 100_000)
        controller.pause(download_id)
        wait_for_state(qtbot, controller, download_id, DownloadState.PAUSED)
    assert summarize(controller.model.records()) == "2 paused · 0 completed"

    window.resume_all_action.trigger()

    for download_id in ids:
        wait_for_state(qtbot, controller, download_id, DownloadState.COMPLETED)
    assert not window.resume_all_action.isEnabled()


def test_quit_question_says_downloads_will_be_paused(make_controller, downloads, monkeypatch):
    asked = []
    monkeypatch.setattr(
        main_window_module.QMessageBox,
        "question",
        lambda parent, title, text, *rest: asked.append(text) or rest[1],  # default button: No
    )
    window = MainWindow(make_controller(), default_folder=downloads)

    assert window.confirm_quit(2) is False
    assert "Quit and pause them?" in asked[0]
    assert "deleted" not in asked[0]
