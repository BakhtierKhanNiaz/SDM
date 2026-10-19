"""The main SDM window: a toolbar, the download list and a status bar."""

import subprocess
from collections import deque
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QByteArray, QPoint, QSortFilterProxyModel, Qt, Signal
from PySide6.QtGui import QAction, QCloseEvent, QGuiApplication, QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QHeaderView,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QStyle,
    QSystemTrayIcon,
    QTableView,
)

from sdm.bridge.protocol import DownloadRequest
from sdm.core.categories import CATEGORIES
from sdm.core.checksums import MISMATCH, MISSING, VERIFIED
from sdm.core.downloads import BrowserContext, DownloadRecord, DownloadState
from sdm.core.errors import SDMError
from sdm.ui.add_url_dialog import AddUrlDialog
from sdm.ui.controller import DownloadController, finished_file, summarize
from sdm.ui.download_model import CATEGORY, COLUMNS, NAME, STATUS
from sdm.ui.scheduler_dialog import SchedulerDialog
from sdm.ui.settings_dialog import SettingsDialog

# Kept for existing imports: the columns of the download list, left to right.
DOWNLOAD_COLUMNS = COLUMNS


def default_download_folder() -> Path:
    return Path.home() / "Downloads"


def reveal_in_explorer(path: Path) -> None:
    """Open File Explorer with `path` selected. Never opens or runs the file itself."""
    # Windows file names can't contain '"', so the quoting can't be broken; the path has been
    # checked by finished_file() to be the entry's own file in its own folder.
    subprocess.Popen(f'explorer.exe /select,"{path}"')  # noqa: S602, S603 - fixed program


_LAYOUT_KEYS = ("ui.geometry", "ui.header")


class MainWindow(QMainWindow):
    # A browser handoff's dialog closed (accepted or not); the receiver frees its slot.
    handoff_closed = Signal()
    # The user confirmed quitting (File > Exit, the tray's Quit, or closing without the tray).
    quit_confirmed = Signal()

    def __init__(
        self, controller: DownloadController, *, default_folder: Path | None = None
    ) -> None:
        super().__init__()
        self.controller = controller
        self._default_folder = default_folder or self._preferred_folder()
        self._quitting = False  # File > Exit or Quit: really close, even with the tray option
        self._told_about_tray = False
        self.notifications: list[tuple[str, str]] = []  # (title, text), newest last
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
        self.download_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.download_table.customContextMenuRequested.connect(self._show_context_menu)
        self.download_table.doubleClicked.connect(lambda index: self.show_in_folder_selected())
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
        self.remove_action.setShortcut(QKeySequence.StandardKey.Delete)
        self.exit_action = self._action("E&xit", self.quit_app)
        self.show_in_folder_action = self._action("Show in &folder", self.show_in_folder_selected)
        self.show_in_folder_action.setToolTip("Open File Explorer at the finished file.")
        self.copy_address_action = self._action("Copy &address", self.copy_address_selected)
        self.verify_action = self._action("&Verify checksum…", self.ask_verify_selected)
        self.verify_action.setToolTip("Check the finished file against a SHA-256 you paste.")
        self.settings_action = self._action("&Settings…", self.open_settings)
        self.settings_action.setShortcut(QKeySequence("Ctrl+,"))
        self.pause_all_action = self._action("Pa&use all", self.controller.pause_all)
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
            self.pause_all_action,
            self.cancel_action,
            self.remove_action,
        ):
            downloads_menu.addAction(action)
        downloads_menu.addSeparator()
        for action in (self.show_in_folder_action, self.copy_address_action, self.verify_action):
            downloads_menu.addAction(action)
        tools_menu = self.menuBar().addMenu("&Tools")
        tools_menu.addAction(self.settings_action)
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

        # A permanent label, not showMessage(): Qt replaces a status *message* with the (empty)
        # hint of any toolbar button or menu item the mouse passes over, which left the status
        # bar blank until the next change (seen in the owner's M9 demo).
        self.status_label = QLabel()
        self.statusBar().addWidget(self.status_label, 1)
        controller.summary_changed.connect(self.status_label.setText)
        controller.download_finished.connect(self._on_finished)
        controller.download_failed.connect(self._on_failed)
        controller.checksum_checked.connect(self._on_checksum)
        icon = self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowDown)
        self.setWindowIcon(icon)
        self.tray = self._make_tray(icon) if QSystemTrayIcon.isSystemTrayAvailable() else None
        self._restore_layout()
        self.download_table.selectionModel().selectionChanged.connect(self._update_actions)
        controller.model.dataChanged.connect(self._update_actions)
        controller.model.rowsInserted.connect(self._update_actions)
        controller.model.rowsRemoved.connect(self._update_actions)
        controller.model.modelReset.connect(self._update_actions)
        self._update_actions()
        self.status_label.setText(summarize(controller.model.records()))

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
                dialog.url,
                dialog.folder,
                dialog.allow_local_network,
                start=dialog.start_now,
                expected_sha256=dialog.expected_sha256,
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
                expected_sha256=dialog.expected_sha256,
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
        expected_sha256: str | None = None,
    ) -> None:
        try:
            self.controller.add(
                url,
                folder,
                allow_local_network=allow_local_network,
                start=start,
                context=context,
                expected_sha256=expected_sha256,
            )
        except SDMError as exc:
            QMessageBox.warning(self, "Can't add this download", str(exc))
            return
        preferences = self.controller.preferences
        if preferences.remember_last_folder:
            self._default_folder = folder  # next time, offer the same folder
            self.controller.set_preferences(replace(preferences, last_folder=str(folder)))

    def _preferred_folder(self) -> Path:
        preferences = self.controller.preferences
        candidates = [preferences.default_folder]
        if preferences.remember_last_folder:
            candidates.insert(0, preferences.last_folder)
        for folder in candidates:
            if folder and Path(folder).is_dir():
                return Path(folder)
        return default_download_folder()

    def open_settings(self) -> None:
        dialog = SettingsDialog(
            self.controller.preferences, tray_available=self.tray is not None, parent=self
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.apply_preferences(dialog.preferences())

    def apply_preferences(self, preferences) -> None:
        old_default = self.controller.preferences.default_folder
        self.controller.set_preferences(preferences)
        if preferences.default_folder != old_default:
            self._default_folder = self._preferred_folder()

    # ----- finished files -----

    def show_in_folder_selected(self) -> None:
        record = self.selected_record()
        path = finished_file(record) if record is not None else None
        if path is not None:
            reveal_in_explorer(path)

    def copy_address_selected(self) -> None:
        record = self.selected_record()
        if record is not None:
            QGuiApplication.clipboard().setText(record.url)

    def ask_verify_selected(self) -> None:
        if self.selected_record() is None:
            return
        text, ok = QInputDialog.getText(
            self, "Verify checksum", "Paste the SHA-256 the publisher lists for this file:"
        )
        if ok:
            self.verify_selected(text)

    def verify_selected(self, text: str) -> None:
        record = self.selected_record()
        if record is None or finished_file(record) is None:
            return
        try:
            self.controller.verify(record.id, text)
        except SDMError as exc:
            QMessageBox.warning(self, "Not a SHA-256", str(exc))

    def context_menu(self) -> QMenu:
        """The list's right-click menu for the selected entry."""
        menu = QMenu(self)
        for action in (
            self.pause_action,
            self.resume_action,
            self.start_now_action,
            self.cancel_action,
            None,
            self.show_in_folder_action,
            self.copy_address_action,
            self.verify_action,
            None,
            *self.move_actions.values(),
            None,
            self.remove_action,
        ):
            if action is None:
                menu.addSeparator()
            else:
                menu.addAction(action)
        return menu

    def _show_context_menu(self, position: QPoint) -> None:
        index = self.download_table.indexAt(position)
        if not index.isValid():
            return
        self.download_table.selectRow(index.row())
        self.context_menu().exec(self.download_table.viewport().mapToGlobal(position))

    # ----- tray and notifications -----

    def _make_tray(self, icon) -> QSystemTrayIcon:
        tray = QSystemTrayIcon(icon, self)
        tray.setToolTip("SDM")
        menu = QMenu(self)
        show = menu.addAction("Show SDM")
        show.triggered.connect(self.show_from_tray)
        menu.addAction(self.add_action)
        menu.addSeparator()
        menu.addAction(self.pause_all_action)
        menu.addAction(self.resume_all_action)
        menu.addSeparator()
        quit_action = menu.addAction("Quit")
        quit_action.triggered.connect(self.quit_app)
        tray.setContextMenu(menu)
        tray.activated.connect(self._tray_activated)
        self.controller.summary_changed.connect(lambda text: tray.setToolTip(f"SDM · {text}"))
        tray.show()
        return tray

    def _tray_activated(self, reason) -> None:
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self.show_from_tray()

    def show_from_tray(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def notify(self, title: str, text: str, *, warning: bool = False) -> None:
        """A Windows notification (if switched on). Never a dialog: it can't interrupt."""
        if not self.controller.preferences.notify:
            return
        self.notifications.append((title, text))
        if self.tray is not None:
            icon = (
                QSystemTrayIcon.MessageIcon.Warning
                if warning
                else QSystemTrayIcon.MessageIcon.Information
            )
            self.tray.showMessage(title, text, icon, 6000)

    def _name(self, download_id: int) -> str:
        record = self.controller.store.get(download_id)
        return (record.file_name or "a download") if record else "a download"

    def _on_finished(self, download_id: int) -> None:
        record = self.controller.store.get(download_id)
        if record is not None and not record.expected_sha256:  # else: after the check
            self.notify("Download complete", self._name(download_id))

    def _on_failed(self, download_id: int, message: str) -> None:
        self.notify("Download failed", f"{self._name(download_id)}: {message}", warning=True)

    def _on_checksum(self, download_id: int, state: str) -> None:
        name = self._name(download_id)
        if state == VERIFIED:
            self.notify("Download complete and verified", f"{name}: the SHA-256 matches.")
        elif state == MISMATCH:
            self.notify("Checksum doesn't match", f"{name} was kept, but don't run it.",
                        warning=True)  # fmt: skip
        elif state == MISSING:
            self.notify("Couldn't check the file", f"{name} wasn't found.", warning=True)

    # ----- layout -----

    def _restore_layout(self) -> None:
        geometry, header = (self.controller.store.get_setting(k) for k in _LAYOUT_KEYS)
        if geometry:
            self.restoreGeometry(QByteArray.fromBase64(geometry.encode("ascii")))
        if header:
            self.download_table.horizontalHeader().restoreState(
                QByteArray.fromBase64(header.encode("ascii"))
            )

    def save_layout(self) -> None:
        geometry = self.saveGeometry().toBase64().data().decode("ascii")
        header = self.download_table.horizontalHeader().saveState().toBase64().data()
        self.controller.store.set_setting(_LAYOUT_KEYS[0], geometry)
        self.controller.store.set_setting(_LAYOUT_KEYS[1], header.decode("ascii"))

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
        finished = record is not None and finished_file(record) is not None
        self.show_in_folder_action.setEnabled(finished)
        self.verify_action.setEnabled(finished)
        self.copy_address_action.setEnabled(record is not None)
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

    def quit_app(self) -> None:
        """File > Exit and the tray's Quit: close for real, even with the tray option on."""
        self._quitting = True
        if self.isHidden():
            self.show_from_tray()  # so a question about running downloads can be seen
        if not self.close():
            self._quitting = False

    def closeEvent(self, event: QCloseEvent) -> None:  # Qt calls this when the window closes
        keep = self.controller.preferences.keep_in_tray and self.tray is not None
        if keep and not self._quitting:
            event.ignore()
            self.hide()
            if not self._told_about_tray:
                self._told_about_tray = True
                self.notify("SDM is still running", "Right-click its tray icon to quit.")
            return
        active = self.controller.active_count()
        if active and not self.confirm_quit(active):
            event.ignore()
            return
        self.save_layout()
        self.controller.shutdown()
        if self.tray is not None:
            self.tray.hide()
        event.accept()
        self.quit_confirmed.emit()

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
