"""The window's queue features (M6b): Category column and filter, Start now, moving, Scheduler."""

import os
from datetime import time
from pathlib import Path

import pytest
from PySide6.QtWidgets import QDialog

from sdm.core.downloads import DownloadState
from sdm.engine.models import DownloadSettings
from sdm.scheduler.queue import QueueSettings, Schedule
from sdm.storage.database import DownloadStore
from sdm.ui.add_url_dialog import AddUrlDialog
from sdm.ui.controller import DownloadController
from sdm.ui.download_model import CATEGORY
from sdm.ui.main_window import MainWindow
from sdm.ui.scheduler_dialog import SchedulerDialog

DATA = os.urandom(200_000)
FAST = DownloadSettings(connect_timeout=5.0, read_timeout=10.0, backoff_base=0.0)


@pytest.fixture
def downloads(tmp_path) -> Path:
    folder = tmp_path / "downloads"
    folder.mkdir()
    return folder


@pytest.fixture
def window(qtbot, qapp, tmp_path, loopback_policy, downloads):
    store = DownloadStore(tmp_path / "sdm.db")
    controller = DownloadController(store, policy_for=lambda r: loopback_policy, settings=FAST)
    controller.start()
    window = MainWindow(controller, default_folder=downloads)
    window.confirm_quit = lambda active: True
    qtbot.addWidget(window)
    yield window
    controller.shutdown()
    store.close()


def slow(mock_server, path):
    mock_server.add(path, mock_server.ranged(DATA, etag='"v1"', stall_at=(100_000, 5)))


def test_category_column_and_filter(qtbot, window, mock_server, downloads):
    controller = window.controller
    controller.set_queue_settings(QueueSettings(limit=1))
    slow(mock_server, "/a.bin")
    for name in ("b.zip", "c.pdf"):
        mock_server.add(f"/{name}", mock_server.ranged(DATA, etag='"v1"'))
    a = controller.add(mock_server.url("/a.bin"), downloads).id
    b = controller.add(mock_server.url("/b.zip"), downloads).id
    c = controller.add(mock_server.url("/c.pdf"), downloads).id

    model = controller.model
    categories = [model.data(model.index(row, CATEGORY)) for row in range(model.rowCount())]
    assert categories == ["General", "Compressed", "Documents"]

    window.sidebar.select_view("Documents")  # M13: the sidebar replaced the category box
    assert window.proxy.rowCount() == 1
    window.download_table.selectRow(0)
    assert window.selected_id() == c  # the filtered row maps to the right download

    window.sidebar.select_view("all")
    assert window.proxy.rowCount() == 3
    assert {a, b, c} == {r.id for r in model.records()}


def test_start_now_and_move_from_the_window(qtbot, window, mock_server, downloads):
    controller = window.controller
    controller.set_queue_settings(QueueSettings(limit=1))
    for name in ("a", "b", "c"):
        slow(mock_server, f"/{name}.bin")
    a, b, c = (controller.add(mock_server.url(f"/{n}.bin"), downloads).id for n in "abc")
    qtbot.waitUntil(lambda: controller.store.get(a).state == DownloadState.DOWNLOADING)

    window.select_id(c)
    assert window.move_actions["top"].isEnabled()
    window.move_actions["top"].trigger()
    assert window.selected_id() == c  # still selected after the list was reordered
    assert [r.id for r in controller.store.list_all()][0] == c

    assert window.start_now_action.isEnabled()
    window.start_now_action.trigger()
    qtbot.waitUntil(lambda: controller.store.get(c).state == DownloadState.DOWNLOADING)
    assert controller.store.get(b).state == DownloadState.QUEUED  # the limit still holds for b


def test_add_url_dialog_can_add_without_starting(qtbot, tmp_path):
    dialog = AddUrlDialog(default_folder=tmp_path, previous_downloads=lambda url: [])
    qtbot.addWidget(dialog)
    assert dialog.start_now is True  # the default
    dialog.start_check.setChecked(False)
    assert dialog.start_now is False


def test_scheduler_dialog_round_trip(qtbot):
    settings = QueueSettings(
        limit=4,
        schedule=Schedule(True, time(23, 0), time(6, 0), frozenset({4, 5})),
        category_subfolders=True,
    )
    dialog = SchedulerDialog(settings)
    qtbot.addWidget(dialog)
    assert dialog.settings() == settings


def test_scheduler_dialog_needs_a_day_when_on(qtbot):
    dialog = SchedulerDialog(QueueSettings())
    qtbot.addWidget(dialog)
    assert not dialog.start_edit.isEnabled()  # greyed out while the schedule is off
    dialog.schedule_check.setChecked(True)
    assert dialog.start_edit.isEnabled()
    for check in dialog.day_checks:
        check.setChecked(False)

    dialog.accept()

    assert dialog.result() != QDialog.DialogCode.Accepted
    assert "at least one day" in dialog.error_label.text()
