"""The main window and package setup."""

from pathlib import Path

import pytest
from PySide6.QtCore import Qt

import sdm
from sdm.ui.main_window import DOWNLOAD_COLUMNS, MainWindow, startup_notices


def test_package_is_installed():
    # "0.0.0+unknown" means sdm was imported from the source tree without `uv sync`.
    assert sdm.__version__ != "0.0.0+unknown"


@pytest.fixture
def window(qtbot, make_controller, tmp_path):
    window = MainWindow(make_controller(), default_folder=tmp_path)
    window.confirm_quit = lambda active: True  # never block a test on a message box
    qtbot.addWidget(window)
    return window


def test_opens_with_an_empty_list(window):
    window.show()
    assert window.isVisible()
    assert "SDM" in window.windowTitle()
    assert window.download_table.model().rowCount() == 0
    assert window.status_label.text() == "No downloads yet"


def test_download_list_has_expected_columns(window):
    model = window.download_table.model()
    headers = [
        model.headerData(i, Qt.Orientation.Horizontal, Qt.ItemDataRole.DisplayRole)
        for i in range(model.columnCount())
    ]
    assert headers == list(DOWNLOAD_COLUMNS)


def test_cancel_and_remove_need_a_selection(window):
    assert window.add_action.isEnabled()
    assert not window.cancel_action.isEnabled()
    assert not window.remove_action.isEnabled()


def test_file_exit_closes_window(window):
    window.show()
    window.exit_action.trigger()
    assert not window.isVisible()


def test_startup_notices():
    assert startup_notices(None, 0) == []
    recovered = Path("C:/x/sdm.db.corrupt-20261019-101500")
    notices = startup_notices(recovered, 2)
    assert str(recovered) in notices[0]
    assert notices[1].startswith("2 downloads were interrupted when SDM last closed.")
    assert "Resume all" in notices[1]
    assert startup_notices(None, 1)[0].startswith("1 download was interrupted")
