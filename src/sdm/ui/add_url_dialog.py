"""The "Add URL" dialog: address, download folder, the local-network option, and (M12b, once
turned on) whether the address is a video page for yt-dlp."""

from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from sdm.bridge.protocol import DownloadRequest
from sdm.core.checksums import InvalidChecksumError, normalize_sha256
from sdm.core.downloads import BrowserContext, DownloadRecord
from sdm.core.errors import InvalidURLError
from sdm.core.units import format_size
from sdm.core.urls import validate_url
from sdm.media.ytdlp import QUALITIES

PreviousDownloads = Callable[[str], list[DownloadRecord]]
# M13: what "Download as" offers, as buttons (None: an ordinary file).
KIND_BUTTONS = (
    (None, "File"),
    ("720p", "720p"),
    ("1080p", "1080p"),
    ("2160p", "4K"),
    ("mp3", "MP3"),
    ("m4a", "M4A"),
)


class AddUrlDialog(QDialog):
    def __init__(
        self,
        *,
        default_folder: Path,
        previous_downloads: PreviousDownloads,
        video_enabled: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Add URL")
        self.setMinimumWidth(560)
        self._previous_downloads = previous_downloads
        self._browser_request: DownloadRequest | None = None
        self._video_enabled = video_enabled

        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("https://example.com/file.zip")
        # M12b: a video page through yt-dlp, only once the add-on is on (Settings > Media).
        self.kind_box = QComboBox()
        self.kind_box.addItem("File (a direct link)", None)
        for quality in QUALITIES.values():
            self.kind_box.addItem(f"Video page: {quality.label}", quality.key)
        self.kind_box.currentIndexChanged.connect(self._kind_changed)
        self.folder_edit = QLineEdit(str(default_folder))
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse)
        folder_row = QHBoxLayout()
        folder_row.addWidget(self.folder_edit)
        folder_row.addWidget(browse)
        self.sha256_edit = QLineEdit()
        self.sha256_edit.setPlaceholderText("Optional: the SHA-256 the publisher lists")
        self.sha256_edit.setToolTip(
            "When the download finishes, SDM checks the file against this value (M9)."
        )
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
        self.download_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.download_button.setText("Download")
        self.download_button.setObjectName("primary")  # the accent-coloured button (M13)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        # M13: a cleaner card. The address first and large; the kind of download as buttons;
        # the SHA-256 and the local-network option folded away under "More options".
        self.url_edit.setObjectName("bigAddress")
        self.url_edit.setMinimumHeight(34)
        self.kind_box.hide()  # the buttons below choose; the box keeps the choice
        self.kind_buttons: dict[str | None, QPushButton] = {}
        kind_row = QHBoxLayout()
        kind_row.setSpacing(6)
        group = QButtonGroup(self)
        for key, text in KIND_BUTTONS:
            button = QPushButton(text)
            button.setCheckable(True)
            button.setObjectName("choice")
            button.clicked.connect(lambda _=False, k=key: self._choose_kind(k))
            group.addButton(button)
            kind_row.addWidget(button)
            self.kind_buttons[key] = button
        kind_row.addStretch()
        self.kind_buttons[None].setChecked(True)
        self.kind_box.currentIndexChanged.connect(self._sync_kind_buttons)

        self.more_button = QToolButton()
        self.more_button.setText("More options")
        self.more_button.setCheckable(True)
        self.more_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.more_button.setArrowType(Qt.ArrowType.RightArrow)
        self.more_button.toggled.connect(self._show_more)
        self.more = QWidget()
        more_form = QFormLayout(self.more)
        more_form.setContentsMargins(0, 0, 0, 0)
        more_form.addRow("SHA-256:", self.sha256_edit)
        more_form.addRow(self.local_network_check)
        self.more.hide()

        title = QLabel("Download from an address")
        title.setObjectName("dialogTitle")
        form = QFormLayout()
        form.setVerticalSpacing(10)
        form.addRow("Address:", self.url_edit)
        if video_enabled:
            form.addRow("Download as:", kind_row)
        else:
            for button in self.kind_buttons.values():
                button.hide()
        form.addRow("Save to:", folder_row)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 14)
        layout.setSpacing(10)
        layout.addWidget(title)
        layout.addLayout(form)
        layout.addWidget(self.browser_label)
        layout.addWidget(self.start_check)
        layout.addWidget(self.more_button)
        layout.addWidget(self.more)
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
    def expected_sha256(self) -> str | None:
        """The checksum typed in, normalized, or None (accept() has checked it)."""
        try:
            return normalize_sha256(self.sha256_edit.text())
        except InvalidChecksumError:
            return None

    @property
    def video(self) -> str | None:
        """The chosen video quality key, or None for an ordinary file download."""
        return self.kind_box.currentData() if self._video_enabled else None

    def _choose_kind(self, key: str | None) -> None:
        self.kind_box.setCurrentIndex(max(0, self.kind_box.findData(key)))

    def _sync_kind_buttons(self) -> None:
        button = self.kind_buttons.get(self.kind_box.currentData())
        if button is not None:
            button.setChecked(True)

    def _show_more(self, shown: bool) -> None:
        self.more.setVisible(shown)
        self.more_button.setArrowType(Qt.ArrowType.DownArrow if shown else Qt.ArrowType.RightArrow)
        self.adjustSize()

    def _kind_changed(self) -> None:
        video = self.kind_box.currentData() is not None
        self.sha256_edit.setEnabled(not video)  # a video's file is made by yt-dlp: no checksum
        if video:
            self.sha256_edit.clear()
        self.url_edit.setPlaceholderText(
            "https://video.example.com/watch?v=…" if video else "https://example.com/file.zip"
        )

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
        intro = {"capture": "Captured from the browser", "video": "Video page from the browser"}
        intro = intro.get(request.source, "From the browser")
        if request.source == "video":
            host = urlsplit(request.url).hostname
            details = [f"on {host}"] if host else []
        self.browser_label.setText(f"{intro}: {' · '.join(details)}" if details else intro)
        self.browser_label.show()

    def choose_video(self, quality: str) -> None:
        """Start in "Video page" mode with this quality (the one used last time)."""
        index = self.kind_box.findData(quality)
        self.kind_box.setCurrentIndex(index if index > 0 else self.kind_box.findData("1080p"))
        self.kind_box.setFocus()

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
        try:
            normalize_sha256(self.sha256_edit.text())
        except InvalidChecksumError as exc:
            self.more_button.setChecked(True)  # the problem is in the folded part: show it
            self._show_error(str(exc))
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
