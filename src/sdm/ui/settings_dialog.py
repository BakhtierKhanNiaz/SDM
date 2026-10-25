"""The Settings dialog (Tools > Settings, M9): folders, connections, speed limit, tray,
notifications, and where ffmpeg is (M12). The queue and schedule stay in the Scheduler (M6)."""

from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from sdm.media.ffmpeg import INSTALL_HINT, find_ffmpeg
from sdm.media.ytdlp import INSTALL_HINT as YTDLP_HINT
from sdm.media.ytdlp import TERMS_NOTICE, find_ytdlp
from sdm.ui.preferences import MAX_SPEED_LIMIT_KIB, Preferences
from sdm.ui.theme import MODE_LABELS, MODES

_WRAP = "​"  # a zero-width space: lets a long path wrap after each backslash


def _show_tool(label: QLabel, found: Path | None, missing: str) -> None:
    """ "Using <path>" for a tool that was found; WinGet's paths are long and have no spaces,
    so they may wrap at any folder (the tooltip has the path as it is)."""
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setText(f"Using {str(found).replace(chr(92), chr(92) + _WRAP)}" if found else missing)
    label.setToolTip(str(found) if found else "")


def ask_video_terms(parent: QWidget | None) -> bool:
    """The notice before video-page downloads are turned on (ADR-0020); True for Yes."""
    answer = QMessageBox.question(
        parent,
        "Video-page downloads",
        f"{TERMS_NOTICE}\n\nTurn on video-page downloads?",
    )
    return answer == QMessageBox.StandardButton.Yes


class SettingsDialog(QDialog):
    def __init__(
        self, preferences: Preferences, *, tray_available: bool, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(480)
        self._original = preferences

        # General
        self.folder_edit = QLineEdit(preferences.default_folder)
        self.folder_edit.setPlaceholderText(str(Path.home() / "Downloads"))
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse)
        folder_row = QHBoxLayout()
        folder_row.addWidget(self.folder_edit)
        folder_row.addWidget(browse)
        self.remember_check = QCheckBox("Offer the folder I used last time in Add URL")
        self.remember_check.setChecked(preferences.remember_last_folder)
        self.theme_box = QComboBox()
        for mode in MODES:
            self.theme_box.addItem(MODE_LABELS[mode], mode)
        self.theme_box.setCurrentIndex(max(0, self.theme_box.findData(preferences.theme)))
        general = QWidget()
        general_form = QFormLayout(general)
        general_form.addRow("Default download folder:", folder_row)
        general_form.addRow(self.remember_check)
        general_form.addRow("Appearance:", self.theme_box)

        # Connections
        self.connections_spin = QSpinBox()
        self.connections_spin.setRange(1, 8)
        self.connections_spin.setValue(preferences.connections)
        self.connections_spin.setToolTip("1 never splits a download. Applies to new downloads.")
        self.limit_check = QCheckBox("Limit the total download speed to")
        self.limit_spin = QSpinBox()
        self.limit_spin.setRange(1, MAX_SPEED_LIMIT_KIB)
        self.limit_spin.setSuffix(" KB/s")
        self.limit_spin.setValue(preferences.speed_limit_kib or 1024)
        self.limit_check.setChecked(preferences.speed_limit_kib > 0)
        self.limit_spin.setEnabled(self.limit_check.isChecked())
        self.limit_check.toggled.connect(self.limit_spin.setEnabled)
        limit_row = QHBoxLayout()
        limit_row.addWidget(self.limit_check)
        limit_row.addWidget(self.limit_spin)
        limit_row.addStretch()
        connections = QWidget()
        connections_form = QFormLayout(connections)
        connections_form.addRow("Connections per download:", self.connections_spin)
        connections_form.addRow(limit_row)
        note = QLabel("The speed limit is shared by all downloads and applies at once.")
        note.setWordWrap(True)
        connections_form.addRow(note)

        # Notifications and tray
        self.notify_check = QCheckBox(
            "Show a Windows notification when a download finishes or fails"
        )
        self.notify_check.setChecked(preferences.notify)
        self.tray_check = QCheckBox("Keep SDM running in the tray when I close the window")
        self.tray_check.setChecked(preferences.keep_in_tray)
        notifications = QWidget()
        notifications_layout = QVBoxLayout(notifications)
        notifications_layout.addWidget(self.notify_check)
        notifications_layout.addWidget(self.tray_check)
        if not tray_available:
            for check in (self.notify_check, self.tray_check):
                check.setEnabled(False)
            notifications_layout.addWidget(QLabel("Windows' notification area isn't available."))
        notifications_layout.addStretch()

        # Media tools (M12)
        self.ffmpeg_edit = QLineEdit(preferences.ffmpeg_path)
        self.ffmpeg_edit.setPlaceholderText("Found automatically")
        browse_ffmpeg = QPushButton("Browse…")
        browse_ffmpeg.clicked.connect(self._browse_ffmpeg)
        ffmpeg_row = QHBoxLayout()
        ffmpeg_row.addWidget(self.ffmpeg_edit)
        ffmpeg_row.addWidget(browse_ffmpeg)
        self.ffmpeg_status = QLabel()
        self.ffmpeg_status.setWordWrap(True)
        self.ffmpeg_edit.textChanged.connect(self._update_ffmpeg_status)
        self._update_ffmpeg_status()
        self.video_check = QCheckBox("Enable video-page downloads (720p, 1080p, 4K or audio)")
        self.video_check.setChecked(preferences.video_enabled)
        self.video_check.toggled.connect(self._video_toggled)
        self.ytdlp_edit = QLineEdit(preferences.ytdlp_path)
        self.ytdlp_edit.setPlaceholderText("Found automatically")
        browse_ytdlp = QPushButton("Browse…")
        browse_ytdlp.clicked.connect(self._browse_ytdlp)
        ytdlp_row = QHBoxLayout()
        ytdlp_row.addWidget(self.ytdlp_edit)
        ytdlp_row.addWidget(browse_ytdlp)
        self.ytdlp_status = QLabel()
        self.ytdlp_status.setWordWrap(True)
        self.ytdlp_edit.textChanged.connect(self._update_ytdlp_status)
        self._update_ytdlp_status()
        video_note = QLabel(
            "Off until you turn it on. Then Add URL can download a video page with yt-dlp. "
            "You're responsible for each site's terms; SDM never signs in or uses cookies."
        )
        video_note.setWordWrap(True)
        media = QWidget()
        media_form = QFormLayout(media)
        media_form.addRow("ffmpeg (for Convert):", ffmpeg_row)
        media_form.addRow(self.ffmpeg_status)
        media_form.addRow(self.video_check)
        media_form.addRow("yt-dlp (for video pages):", ytdlp_row)
        media_form.addRow(self.ytdlp_status)
        media_form.addRow(video_note)

        self.tabs = QTabWidget()
        self.tabs.addTab(general, "General")
        self.tabs.addTab(connections, "Connections")
        self.tabs.addTab(notifications, "Notifications")
        self.tabs.addTab(media, "Media")
        self.error_label = QLabel()
        self.error_label.setStyleSheet("color: #b00020")
        self.error_label.hide()
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(self.tabs)
        layout.addWidget(self.error_label)
        layout.addWidget(buttons)

    def preferences(self) -> Preferences:
        """The values chosen in the dialog."""
        return replace(
            self._original,
            default_folder=self.folder_edit.text().strip(),
            remember_last_folder=self.remember_check.isChecked(),
            connections=self.connections_spin.value(),
            speed_limit_kib=self.limit_spin.value() if self.limit_check.isChecked() else 0,
            notify=self.notify_check.isChecked(),
            keep_in_tray=self.tray_check.isChecked(),
            theme=self.theme_box.currentData(),
            ffmpeg_path=self.ffmpeg_edit.text().strip(),
            video_enabled=self.video_check.isChecked(),
            ytdlp_path=self.ytdlp_edit.text().strip(),
        )

    def accept(self) -> None:
        folder = self.folder_edit.text().strip()
        if folder and not Path(folder).is_dir():
            self.tabs.setCurrentIndex(0)
            self.error_label.setText(f"The folder doesn't exist: {folder}")
            self.error_label.show()
            return
        for edit in (self.ffmpeg_edit, self.ytdlp_edit):
            program = edit.text().strip()
            if program and not Path(program).is_file():
                self.tabs.setCurrentIndex(3)
                self.error_label.setText(f"There's no program at: {program}")
                self.error_label.show()
                return
        super().accept()

    def _video_toggled(self, on: bool) -> None:
        if on and not self._original.video_enabled and not self.confirm_video_terms():
            self.video_check.setChecked(False)

    def confirm_video_terms(self) -> bool:
        """The notice shown when the add-on is turned on (tests replace it)."""
        return ask_video_terms(self)

    def _update_ytdlp_status(self) -> None:
        found = find_ytdlp(self.ytdlp_edit.text().strip())
        _show_tool(
            self.ytdlp_status, found, f"yt-dlp wasn't found. {YTDLP_HINT}, then restart SDM."
        )

    def _browse_ytdlp(self) -> None:
        chosen, _ = QFileDialog.getOpenFileName(self, "yt-dlp", "", "yt-dlp (yt-dlp.exe)")
        if chosen:
            self.ytdlp_edit.setText(str(Path(chosen)))

    def _update_ffmpeg_status(self) -> None:
        found = find_ffmpeg(self.ffmpeg_edit.text().strip())
        _show_tool(
            self.ffmpeg_status, found, f"ffmpeg wasn't found. {INSTALL_HINT}, then restart SDM."
        )

    def _browse_ffmpeg(self) -> None:
        chosen, _ = QFileDialog.getOpenFileName(self, "ffmpeg", "", "ffmpeg (ffmpeg.exe)")
        if chosen:
            self.ffmpeg_edit.setText(str(Path(chosen)))

    def _browse(self) -> None:
        start = self.folder_edit.text() or str(Path.home() / "Downloads")
        chosen = QFileDialog.getExistingDirectory(self, "Default download folder", start)
        if chosen:
            self.folder_edit.setText(str(Path(chosen)))
