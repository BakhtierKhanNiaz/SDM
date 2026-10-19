"""The "Add URL" dialog: address, download folder, and the local-network option."""

from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

from PySide6.QtCore import Qt
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

from sdm.bridge.protocol import DownloadRequest
from sdm.core.downloads import BrowserContext, DownloadRecord
from sdm.core.errors import InvalidURLError
from sdm.core.units import format_size
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
        self._browser_request: DownloadRequest | None = None

        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("https://example.com/file.zip")
        self.folder_edit = QLineEdit(str(default_folder))
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse)
        folder_row = QHBoxLayout()
        folder_row.addWidget(self.folder_edit)
        folder_row.addWidget(browse)
        self.start_check = QCheckBox("Start the download now (otherwise it waits, paused)")
        self.start_check.setChecked(True)
        self.local_network_check = QCheckBox(
            "Allow servers on my local network (for example a NAS at 192.168.x.x)"
        )

        # What the browser said (M8). Plain text: a file name must never be read as HTML.
        self.browser_label = QLabel()
        self.browser_label.setTextFormat(Qt.TextFormat.PlainText)
        self.browser_label.setWordWrap(True)
        self.browser_label.hide()

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
        layout.addWidget(self.browser_label)
        layout.addWidget(self.start_check)
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

    @property
    def start_now(self) -> bool:
        return self.start_check.isChecked()

    @property
    def browser_context(self) -> BrowserContext | None:
        """The browser's hints, kept only while the address is still the browser's own."""
        request = self._browser_request
        if request is None or self.url != request.url:
            return None  # the user typed another address: the page and name may not fit it
        return request.context()

    def show_browser_request(self, request: DownloadRequest) -> None:
        """Fill in a link handed over by the browser and say what the browser knew."""
        self._browser_request = request
        self.url_edit.setText(request.url)
        details = []
        if request.filename:
            details.append(request.filename)
        if request.size:
            details.append(format_size(request.size))
        if request.mime:
            details.append(request.mime)
        page = urlsplit(request.referrer).hostname if request.referrer else None
        if page:
            details.append(f"from a page on {page}")
        intro = "Captured from Chrome" if request.source == "capture" else "From Chrome"
        self.browser_label.setText(f"{intro}: {' · '.join(details)}" if details else intro)
        self.browser_label.show()

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
