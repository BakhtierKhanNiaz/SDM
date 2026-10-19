"""Application entry point: opens the history, starts the engine and shows the main window.

Only one SDM runs at a time: the browser bridge's pipe doubles as the single-instance lock,
so a second copy never opens the same history (it would mark the first one's downloads as
interrupted).
"""

import logging
import sys

from PySide6.QtWidgets import QApplication, QMessageBox

from sdm import __version__
from sdm.bridge.host import FROM_BROWSER_FLAG
from sdm.bridge.pipe import (
    AlreadyRunning,
    BridgeListener,
    default_key_path,
    load_or_create_key,
    pipe_address,
)
from sdm.storage.database import DownloadStore, StorageError, default_database_path
from sdm.ui.controller import DownloadController
from sdm.ui.handoff import HandoffReceiver
from sdm.ui.main_window import MainWindow, startup_notices


def main(argv: list[str] | None = None) -> int:
    """Start SDM and return the process exit code."""
    app = QApplication(sys.argv if argv is None else argv)
    app.setApplicationName("SDM")
    app.setApplicationVersion(__version__)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")

    receiver = HandoffReceiver()
    try:
        key_path = default_key_path()
        bridge = BridgeListener(load_or_create_key(key_path), pipe_address(key_path),
                                receiver.offer)  # fmt: skip
    except AlreadyRunning:
        if FROM_BROWSER_FLAG not in app.arguments():  # started by the host: stay quiet
            QMessageBox.information(None, "SDM", "SDM is already running.")
        return 0
    except OSError as exc:
        logging.getLogger(__name__).warning("The browser bridge isn't available: %s", exc)
        bridge = None

    try:
        store = DownloadStore(default_database_path())
    except StorageError as exc:
        QMessageBox.critical(None, "SDM can't start", str(exc))
        if bridge is not None:
            bridge.close()
        return 1
    interrupted = store.mark_interrupted_on_startup()

    controller = DownloadController(store)
    controller.start()
    app.aboutToQuit.connect(controller.shutdown)  # a second safety net besides closeEvent

    window = MainWindow(controller)
    # The window decides when SDM ends (it may only hide to the tray, M9).
    app.setQuitOnLastWindowClosed(False)
    window.quit_confirmed.connect(app.quit)
    window.show()
    receiver.received.connect(window.receive_handoff)
    window.handoff_closed.connect(receiver.done)
    if bridge is not None:
        bridge.start()  # before the notices below, so a waiting host isn't kept waiting
    for notice in startup_notices(store.recovered_from, interrupted):
        QMessageBox.information(window, "SDM", notice)

    try:
        return app.exec()
    finally:
        if bridge is not None:
            bridge.close()
        controller.shutdown()
        store.close()
