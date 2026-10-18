"""The "Add URL" dialog: address, download folder, and the local-network option."""

from collections.abc import Callable
from datetime import datetime
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
    QVBoxLayout,
    QWidget,
)

from sdm.core.downloads import DownloadRecord
from sdm.core.errors import InvalidURLError
from sdm.core.urls import validate_url

PreviousDownloads = Callable[[str], list[DownloadRecord]]


class AddUrlDialog(QDialog):
    def __init__(
        self,
        *,
        default_folder: Path,
        previous_downloads: PreviousDownloads,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Add URL")
        self.setMinimumWidth(560)
        self._previous_downloads = previous_downloads

        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("https://example.com/file.zip")
        self.folder_edit = QLineEdit(str(default_folder))
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse)
        folder_row = QHBoxLayout()
        folder_row.addWidget(self.folder_edit)
        folder_row.addWidget(browse)
        self.local_network_check = QCheckBox(
            "Allow servers on my local network (for example a NAS at 192.168.x.x)"
        )

        # A gentle warning (already downloaded) and a blocking error (can't continue).
        self.warning_label = QLabel()
        self.warning_label.setWordWrap(True)
        self.warning_label.hide()
        self.error_label = QLabel()
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet("color: #b00020")
        self.error_label.hide()

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Download")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        form = QFormLayout()
        form.addRow("Address:", self.url_edit)
        form.addRow("Save to:", folder_row)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.local_network_check)
        layout.addWidget(self.warning_label)
        layout.addWidget(self.error_label)
        layout.addWidget(buttons)

        self.url_edit.textChanged.connect(self._on_url_changed)

    # ----- results -----

    @property
    def url(self) -> str:
        return self.url_edit.text().strip()

    @property
    def folder(self) -> Path:
        return Path(self.folder_edit.text().strip())

    @property
    def allow_local_network(self) -> bool:
        return self.local_network_check.isChecked()

    # ----- behavior -----

    def accept(self) -> None:
        try:
            validate_url(self.url)
        except InvalidURLError as exc:
            self._show_error(str(exc))
            return
        if not self.folder_edit.text().strip() or not self.folder.is_dir():
            self._show_error(f"The folder doesn't exist: {self.folder_edit.text().strip()}")
            return
        super().accept()

    def _on_url_changed(self, text: str) -> None:
        self.error_label.hide()
        try:
            validate_url(text)
        except InvalidURLError:
            self.warning_label.hide()
            return
        previous = self._previous_downloads(text.strip())
        if not previous:
            self.warning_label.hide()
            return
        last = previous[-1]
        when = _local_time(last.finished_at or last.created_at)
        self.warning_label.setText(
            f"You already downloaded this on {when} as {last.file_name}. "
            "Downloading it again saves a new copy; nothing is overwritten."
        )
        self.warning_label.show()

    def _browse(self) -> None:
        chosen = QFileDialog.getExistingDirectory(self, "Download folder", self.folder_edit.text())
        if chosen:
            self.folder_edit.setText(str(Path(chosen)))

    def _show_error(self, message: str) -> None:
        self.error_label.setText(message)
        self.error_label.show()


def _local_time(iso_utc: str) -> str:
    return datetime.fromisoformat(iso_utc).astimezone().strftime("%Y-%m-%d %H:%M")
