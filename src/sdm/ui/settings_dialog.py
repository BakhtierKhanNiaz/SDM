"""The Settings dialog (Tools > Settings, M9): folders, connections, speed limit, tray and
notifications. The queue and schedule stay in the Scheduler dialog (M6)."""

from dataclasses import replace
from pathlib import Path

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from sdm.ui.preferences import MAX_SPEED_LIMIT_KIB, Preferences


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
        general = QWidget()
        general_form = QFormLayout(general)
        general_form.addRow("Default download folder:", folder_row)
        general_form.addRow(self.remember_check)

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

        self.tabs = QTabWidget()
        self.tabs.addTab(general, "General")
        self.tabs.addTab(connections, "Connections")
        self.tabs.addTab(notifications, "Notifications")
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
        )

    def accept(self) -> None:
        folder = self.folder_edit.text().strip()
        if folder and not Path(folder).is_dir():
            self.tabs.setCurrentIndex(0)
            self.error_label.setText(f"The folder doesn't exist: {folder}")
            self.error_label.show()
            return
        super().accept()

    def _browse(self) -> None:
        start = self.folder_edit.text() or str(Path.home() / "Downloads")
        chosen = QFileDialog.getExistingDirectory(self, "Default download folder", start)
        if chosen:
            self.folder_edit.setText(str(Path(chosen)))
