"""The main SDM window: a toolbar, the download list and a status bar."""

from collections import deque
from pathlib import Path

from PySide6.QtCore import QSortFilterProxyModel, Signal
from PySide6.QtGui import QAction, QCloseEvent, QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QHeaderView,
    QMainWindow,
    QMessageBox,
    QTableView,
)

from sdm.bridge.protocol import DownloadRequest
from sdm.core.categories import CATEGORIES
from sdm.core.downloads import BrowserContext, DownloadRecord, DownloadState
from sdm.core.errors import SDMError
from sdm.ui.add_url_dialog import AddUrlDialog
from sdm.ui.controller import DownloadController, summarize
from sdm.ui.download_model import CATEGORY, COLUMNS, NAME, STATUS
from sdm.ui.scheduler_dialog import SchedulerDialog

# Kept for existing imports: the columns of the download list, left to right.
DOWNLOAD_COLUMNS = COLUMNS


def default_download_folder() -> Path:
    return Path.home() / "Downloads"


class MainWindow(QMainWindow):
    # A browser handoff's dialog closed (accepted or not); the receiver frees its slot.
    handoff_closed = Signal()

    def __init__(
        self, controller: DownloadController, *, default_folder: Path | None = None
    ) -> None:
        super().__init__()
        self.controller = controller
        self._default_folder = default_folder or default_download_folder()
        self._handoffs: deque[DownloadRequest] = deque()  # browser links waiting for a dialog
        self.handoff_dialog: AddUrlDialog | None = None
        self.setWindowTitle("SDM - Smart Download Manager")
        self.resize(900, 500)

        # The view shows the model through a filter (the category box); rows on screen are
        # translated back to the model's rows with mapToSource.
        self.proxy = QSortFilterProxyModel(self)
        self.proxy.setSourceModel(controller.model)
        self.proxy.setFilterKeyColumn(CATEGORY)
        self.download_table = QTableView(self)
        self.download_table.setModel(self.proxy)
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
        self.start_now_action = self._action("&Start now", self.start_now_selected)
        self.start_now_action.setToolTip("Start at once, ignoring the limit and the schedule.")
        self.move_actions = {
            where: self._action(text, lambda checked=False, w=where: self.move_selected(w))
            for where, text in (
                ("top", "Move to &top"),
                ("up", "Move &up"),
                ("down", "Move &down"),
                ("bottom", "Move to &bottom"),
            )
        }
        self.scheduler_action = self._action("S&cheduler…", self.open_scheduler)
        self.category_box = QComboBox()
        self.category_box.addItems(["All categories", *CATEGORIES])
        self.category_box.currentTextChanged.connect(self._filter_category)

        file_menu = self.menuBar().addMenu("&File")
        file_menu.addAction(self.add_action)
        file_menu.addSeparator()
        file_menu.addAction(self.exit_action)
        queue_menu = self.menuBar().addMenu("&Queue")
        queue_menu.addAction(self.start_now_action)
        queue_menu.addSeparator()
        for action in self.move_actions.values():
            queue_menu.addAction(action)
        queue_menu.addSeparator()
        queue_menu.addAction(self.scheduler_action)
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
            self.start_now_action,
            self.scheduler_action,
        ):
            toolbar.addAction(action)
        toolbar.addSeparator()
        toolbar.addWidget(self.category_box)

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
            self.add_download(
                dialog.url, dialog.folder, dialog.allow_local_network, start=dialog.start_now
            )

    def receive_handoff(self, request: DownloadRequest | str) -> None:
        """A link from the browser: confirm it in the Add URL dialog, one at a time."""
        if isinstance(request, str):
            request = DownloadRequest(request)
        self._handoffs.append(request)
        if self.isMinimized():
            self.showNormal()
        self.raise_()
        self.activateWindow()
        self._show_next_handoff()

    def _show_next_handoff(self) -> None:
        if self.handoff_dialog is not None or not self._handoffs:
            return
        dialog = AddUrlDialog(
            default_folder=self._default_folder,
            previous_downloads=self.controller.previous_downloads,
            parent=self,
        )
        dialog.setWindowTitle("Add URL from the browser")
        dialog.show_browser_request(self._handoffs.popleft())  # checked again when accepted
        dialog.finished.connect(lambda result, d=dialog: self._handoff_finished(d, result))
        self.handoff_dialog = dialog
        dialog.open()  # not exec(): the window keeps running while the dialog waits

    def _handoff_finished(self, dialog: AddUrlDialog, result: int) -> None:
        self.handoff_dialog = None
        if result == QDialog.DialogCode.Accepted:
            self.add_download(
                dialog.url,
                dialog.folder,
                dialog.allow_local_network,
                start=dialog.start_now,
                context=dialog.browser_context,
            )
        dialog.deleteLater()
        self.handoff_closed.emit()
        self._show_next_handoff()

    def add_download(
        self,
        url: str,
        folder: Path,
        allow_local_network: bool = False,
        *,
        start: bool = True,
        context: BrowserContext | None = None,
    ) -> None:
        try:
            self.controller.add(
                url, folder, allow_local_network=allow_local_network, start=start, context=context
            )
        except SDMError as exc:
            QMessageBox.warning(self, "Can't add this download", str(exc))
            return
        self._default_folder = folder  # next time, offer the same folder

    def selected_record(self) -> DownloadRecord | None:
        rows = self.download_table.selectionModel().selectedRows()
        if not rows:
            return None
        return self.controller.model.record_at(self.proxy.mapToSource(rows[0]).row())

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

    def start_now_selected(self) -> None:
        download_id = self.selected_id()
        if download_id is not None:
            self.controller.start_now(download_id)

    def move_selected(self, where: str) -> None:
        download_id = self.selected_id()
        if download_id is None:
            return
        self.controller.move(download_id, where)
        self.select_id(download_id)  # moving reloads the list: keep the same entry selected

    def select_id(self, download_id: int) -> None:
        for row in range(self.proxy.rowCount()):
            source = self.proxy.mapToSource(self.proxy.index(row, 0))
            if self.controller.model.record_at(source.row()).id == download_id:
                self.download_table.selectRow(row)
                return

    def open_scheduler(self) -> None:
        dialog = SchedulerDialog(self.controller.queue_settings, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.controller.set_queue_settings(dialog.settings())

    def _filter_category(self, text: str) -> None:
        if text == "All categories":
            self.proxy.setFilterFixedString("")
        else:
            self.proxy.setFilterRegularExpression(f"^{text}$")
        self._update_actions()

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
        waiting = record is not None and record.state == DownloadState.QUEUED
        self.start_now_action.setEnabled((waiting or resumable) and not record.forced)
        for action in self.move_actions.values():
            action.setEnabled(active)
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
