"""Application entry point: creates the Qt application and shows the main window."""

import sys

from PySide6.QtWidgets import QApplication

from sdm import __version__
from sdm.ui.main_window import MainWindow


def main(argv: list[str] | None = None) -> int:
    """Start SDM and return the process exit code."""
    app = QApplication(sys.argv if argv is None else argv)
    app.setApplicationName("SDM")
    app.setApplicationVersion(__version__)

    window = MainWindow()
    window.show()
    return app.exec()
