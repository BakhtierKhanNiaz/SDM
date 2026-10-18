"""The main SDM window: a toolbar, the download list and a status bar."""

from pathlib import Path

from PySide6.QtGui import QAction, QCloseEvent, QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHeaderView,
    QMainWindow,
    QMessageBox,
    QTableView,
)

from sdm.core.downloads import DownloadRecord, DownloadState
from sdm.core.errors import SDMError
from sdm.ui.add_url_dialog import AddUrlDialog
from sdm.ui.controller import DownloadController, summarize
from sdm.ui.download_model import COLUMNS, NAME, STATUS

# Kept for existing imports: the columns of the download list, left to right.
DOWNLOAD_COLUMNS = COLUMNS


def default_download_folder() -> Path:
    return Path.home() / "Downloads"


class MainWindow(QMainWindow):
    def __init__(
        self, controller: DownloadController, *, default_folder: Path | None = None
    ) -> None:
        super().__init__()
        self.controller = controller
        self._default_folder = default_folder or default_download_folder()
        self.setWindowTitle("SDM - Smart Download Manager")
        self.resize(900, 500)

        self.download_table = QTableView(self)
        self.download_table.setModel(controller.model)
        self.download_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.download_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.download_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.download_table.verticalHeader().setVisible(False)
        self.download_table.setAlternatingRowColors(True)
        header = self.download_table.horizontalHeader()
        header.setSectionResizeMode(NAME, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(STATUS, QHeaderView.ResizeMode.ResizeToContents)
        self.setCentralWidget(self.download_table)

        self.add_action = self._action("&Add URL…", self.open_add_dialog)
        self.add_action.setShortcut(QKeySequence.StandardKey.New)
        self.pause_action = self._action("&Pause", self.pause_selected)
        self.pause_action.setToolTip("Stop for now and keep what has arrived.")
        self.resume_action = self._action("R&esume", self.resume_selected)
        self.resume_action.setToolTip("Continue a paused or interrupted download, or retry.")
        self.resume_all_action = self._action("Resume a&ll", self.resume_all)
        self.resume_all_action.setToolTip("Resume every paused and interrupted download.")
        self.cancel_action = self._action("&Cancel download", self.cancel_selected)
        self.cancel_action.setToolTip("Stop for good and delete the partial file.")
        self.remove_action = self._action("&Remove from list", self.remove_selected)
        self.remove_action.setToolTip(
            "Remove the entry from the list. A finished file is kept; a partial file is deleted."
        )
        self.exit_action = self._action("E&xit", self.close)

        file_menu = self.menuBar().addMenu("&File")
        file_menu.addAction(self.add_action)
        file_menu.addSeparator()
        file_menu.addAction(self.exit_action)
        downloads_menu = self.menuBar().addMenu("&Downloads")
        for action in (
            self.pause_action,
            self.resume_action,
            self.resume_all_action,
            self.cancel_action,
            self.remove_action,
        ):
            downloads_menu.addAction(action)
        toolbar = self.addToolBar("Main")
        toolbar.setMovable(False)
        for action in (
            self.add_action,
            self.pause_action,
            self.resume_action,
            self.resume_all_action,
            self.cancel_action,
            self.remove_action,
        ):
            toolbar.addAction(action)

        controller.summary_changed.connect(self.statusBar().showMessage)
        self.download_table.selectionModel().selectionChanged.connect(self._update_actions)
        controller.model.dataChanged.connect(self._update_actions)
        controller.model.rowsInserted.connect(self._update_actions)
        controller.model.rowsRemoved.connect(self._update_actions)
        controller.model.modelReset.connect(self._update_actions)
        self._update_actions()
        self.statusBar().showMessage(summarize(controller.model.records()))

    def _action(self, text: str, slot) -> QAction:
        action = QAction(text, self)
        action.triggered.connect(slot)
        return action

    # ----- actions -----

    def open_add_dialog(self) -> None:
        dialog = AddUrlDialog(
            default_folder=self._default_folder,
            previous_downloads=self.controller.previous_downloads,
            parent=self,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.add_download(dialog.url, dialog.folder, dialog.allow_local_network)

    def add_download(self, url: str, folder: Path, allow_local_network: bool = False) -> None:
        try:
            self.controller.add(url, folder, allow_local_network=allow_local_network)
        except SDMError as exc:
            QMessageBox.warning(self, "Can't add this download", str(exc))
            return
        self._default_folder = folder  # next time, offer the same folder

    def selected_record(self) -> DownloadRecord | None:
        rows = self.download_table.selectionModel().selectedRows()
        if not rows:
            return None
        return self.controller.model.record_at(rows[0].row())

    def selected_id(self) -> int | None:
        record = self.selected_record()
        return None if record is None else record.id

    def pause_selected(self) -> None:
        record = self.selected_record()
        if record is None or not record.state.is_active:
            return
        known_unresumable = record.file_name is not None and not record.resumable
        if known_unresumable and not self.confirm_pause_unresumable():
            return
        self.controller.pause(record.id)

    def resume_selected(self) -> None:
        download_id = self.selected_id()
        if download_id is not None:
            self.controller.resume(download_id)

    def resume_all(self) -> None:
        self.controller.resume_all()

    def cancel_selected(self) -> None:
        download_id = self.selected_id()
        if download_id is not None:
            self.controller.cancel(download_id)

    def remove_selected(self) -> None:
        download_id = self.selected_id()
        if download_id is not None:
            self.controller.remove(download_id)

    def _update_actions(self, *_args: object) -> None:
        record = self.selected_record()
        active = record is not None and record.state.is_active
        resumable = record is not None and record.state.can_resume
        self.pause_action.setEnabled(active)
        self.resume_action.setEnabled(resumable)
        self.resume_action.setText(
            "R&etry" if record is not None and record.state == DownloadState.FAILED else "R&esume"
        )
        self.cancel_action.setEnabled(active or resumable)
        self.remove_action.setEnabled(record is not None and not active)
        self.resume_all_action.setEnabled(
            any(
                r.state in (DownloadState.PAUSED, DownloadState.INTERRUPTED)
                for r in self.controller.model.records()
            )
        )

    def confirm_pause_unresumable(self) -> bool:
        answer = QMessageBox.question(
            self,
            "This server can't resume",
            "This server doesn't support resuming downloads, so resuming later will start "
            "over from the beginning.\n\nPause anyway?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return answer == QMessageBox.StandardButton.Yes

    # ----- closing -----

    def closeEvent(self, event: QCloseEvent) -> None:  # Qt calls this when the window closes
        active = self.controller.active_count()
        if active and not self.confirm_quit(active):
            event.ignore()
            return
        self.controller.shutdown()
        event.accept()

    def confirm_quit(self, active: int) -> bool:
        noun = "download is" if active == 1 else "downloads are"
        answer = QMessageBox.question(
            self,
            "Downloads in progress",
            f"{active} {noun} still running. Quit and pause them?\n\n"
            "What has arrived is kept: click Resume next time to continue.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return answer == QMessageBox.StandardButton.Yes


def startup_notices(recovered_from: Path | None, interrupted: int) -> list[str]:
    """Messages to show once at startup."""
    notices = []
    if recovered_from is not None:
        notices.append(
            "SDM's download history was damaged and couldn't be read, so a new, empty history "
            f"was started. The damaged file was kept as:\n{recovered_from}"
        )
    if interrupted:
        noun = "download was" if interrupted == 1 else "downloads were"
        notices.append(
            f"{interrupted} {noun} interrupted when SDM last closed. "
            "Select one and click Resume, or click Resume all, to continue."
        )
    return notices
