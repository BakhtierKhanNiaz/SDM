"""Application entry point: opens the history, starts the engine and shows the main window.

Only one SDM runs at a time: the browser bridge's pipe doubles as the single-instance lock,
so a second copy never opens the same history (it would mark the first one's downloads as
interrupted).
"""

import logging
import sys

from PySide6.QtCore import QObject, Signal
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
from sdm.core.logs import install_crash_handlers, setup_logging
from sdm.storage.database import DownloadStore, StorageError, default_database_path
from sdm.ui.controller import DownloadController
from sdm.ui.handoff import HandoffReceiver
from sdm.ui.main_window import MainWindow, log_folder, running_elevated, startup_notices
from sdm.ui.theme import apply_theme, follow_windows


class CrashReporter(QObject):
    """Shows "unexpected error" on the main thread, whichever thread the error happened on."""

    raised = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self._shown = 0
        self.raised.connect(self._show)

    def _show(self, text: str) -> None:
        if self._shown >= 3:  # never bury the user in dialogs; the log has every error
            return
        self._shown += 1
        QMessageBox.critical(
            None,
            "SDM hit an unexpected error",
            f"{text}\n\nDetails were saved to SDM's log (Help > Open log folder). SDM keeps "
            "running, but if something looks wrong, restart it.",
        )


def main(argv: list[str] | None = None) -> int:
    """Start SDM and return the process exit code."""
    app = QApplication(sys.argv if argv is None else argv)
    app.setApplicationName("SDM")
    app.setApplicationVersion(__version__)
    log_file = setup_logging(log_folder())
    reporter = CrashReporter()
    install_crash_handlers(reporter.raised.emit)  # any thread; the dialog opens on this one
    logging.getLogger(__name__).info("SDM %s starting (log: %s)", __version__, log_file)

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
    apply_theme(app, controller.preferences.theme)  # M11: light/dark, following Windows
    follow_windows(app)
    controller.start()
    app.aboutToQuit.connect(controller.shutdown)  # a second safety net besides closeEvent

    window = MainWindow(controller)
    # The window decides when SDM ends (it may only hide to the tray, M9).
    app.setQuitOnLastWindowClosed(False)
    window.quit_confirmed.connect(app.quit)
    window.show()
    if not controller.preferences.setup_done:  # first start: the welcome assistant (M11)
        window.open_setup_wizard()
    receiver.received.connect(window.receive_handoff)
    window.handoff_closed.connect(receiver.done)
    if bridge is not None:
        bridge.start()  # before the notices below, so a waiting host isn't kept waiting
    elevated = running_elevated()
    if elevated:
        logging.getLogger(__name__).warning("SDM is running as administrator")
    for notice in startup_notices(store.recovered_from, interrupted, elevated=elevated):
        QMessageBox.information(window, "SDM", notice)

    try:
        return app.exec()
    finally:
        if bridge is not None:
            bridge.close()
        controller.shutdown()
        store.close()
