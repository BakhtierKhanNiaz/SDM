"""Smoke tests for the main window and package setup."""

import sdm
from sdm.ui.main_window import DOWNLOAD_COLUMNS, MainWindow


def test_package_is_installed():
    # "0.0.0+unknown" means sdm was imported from the source tree without `uv sync`.
    assert sdm.__version__ != "0.0.0+unknown"


def test_main_window_opens_with_empty_download_list(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()

    assert window.isVisible()
    assert "SDM" in window.windowTitle()
    assert window.download_table.rowCount() == 0
    assert window.statusBar().currentMessage() == "No downloads yet"


def test_download_list_has_expected_columns(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    table = window.download_table
    headers = [table.horizontalHeaderItem(i).text() for i in range(table.columnCount())]
    assert headers == list(DOWNLOAD_COLUMNS)


def test_file_exit_closes_window(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()

    window.exit_action.trigger()

    assert not window.isVisible()
