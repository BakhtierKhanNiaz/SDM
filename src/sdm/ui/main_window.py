"""The main SDM window."""

from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QMainWindow, QTableWidget

# Columns of the download list, left to right.
DOWNLOAD_COLUMNS = ("File name", "Size", "Progress", "Speed", "Time left", "Status")


class MainWindow(QMainWindow):
    """Top-level window: a download list, a File menu and a status bar.

    The list stays empty in M1; rows arrive in M3 once downloads and history exist.
    """

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("SDM - Smart Download Manager")
        self.resize(900, 500)

        self.download_table = QTableWidget(0, len(DOWNLOAD_COLUMNS), self)
        self.download_table.setHorizontalHeaderLabels(DOWNLOAD_COLUMNS)
        self.download_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.download_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.download_table.verticalHeader().setVisible(False)
        self.download_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self.setCentralWidget(self.download_table)

        file_menu = self.menuBar().addMenu("&File")
        self.exit_action = file_menu.addAction("E&xit")
        self.exit_action.triggered.connect(self.close)

        self.statusBar().showMessage("No downloads yet")
