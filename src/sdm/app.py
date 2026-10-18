"""Application entry point: opens the history, starts the engine and shows the main window."""

import logging
import sys

from PySide6.QtWidgets import QApplication, QMessageBox

from sdm import __version__
from sdm.storage.database import DownloadStore, StorageError, default_database_path
from sdm.ui.controller import DownloadController
from sdm.ui.main_window import MainWindow, startup_notices


def main(argv: list[str] | None = None) -> int:
    """Start SDM and return the process exit code."""
    app = QApplication(sys.argv if argv is None else argv)
    app.setApplicationName("SDM")
    app.setApplicationVersion(__version__)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")

    try:
        store = DownloadStore(default_database_path())
    except StorageError as exc:
        QMessageBox.critical(None, "SDM can't start", str(exc))
        return 1
    interrupted = store.mark_interrupted_on_startup()

    controller = DownloadController(store)
    controller.start()
    app.aboutToQuit.connect(controller.shutdown)  # a second safety net besides closeEvent

    window = MainWindow(controller)
    window.show()
    for notice in startup_notices(store.recovered_from, interrupted):
        QMessageBox.information(window, "SDM", notice)

    try:
        return app.exec()
    finally:
        controller.shutdown()
        store.close()
