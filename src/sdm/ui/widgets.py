"""Widgets for the main window (M11): the list's progress bars and the details panel."""

from datetime import datetime
from urllib.parse import urlsplit

from PySide6.QtCore import QModelIndex, QRect, Qt, Signal
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import (
    QApplication,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionProgressBar,
    QStyleOptionViewItem,
    QVBoxLayout,
    QWidget,
)

from sdm.core.downloads import DownloadRecord, DownloadState
from sdm.core.units import format_duration, format_size, format_speed
from sdm.core.urls import redact_url
from sdm.ui.download_model import CHECKSUM_LABELS, PROGRESS_ROLE, STATE_LABELS


class ProgressDelegate(QStyledItemDelegate):
    """Draws the Progress column as a bar; unknown sizes keep the plain text."""

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        percent = index.data(PROGRESS_ROLE)
        if percent is None:
            super().paint(painter, option, index)
            return
        if option.state & QStyle.StateFlag.State_Selected:
            painter.fillRect(option.rect, option.palette.highlight())
        bar = QStyleOptionProgressBar()
        bar.rect = QRect(option.rect.adjusted(6, 6, -6, -6))
        bar.minimum, bar.maximum, bar.progress = 0, 100, int(percent)
        bar.text = f"{int(percent)}%"
        bar.textVisible = True
        bar.textAlignment = Qt.AlignmentFlag.AlignCenter
        bar.state = QStyle.StateFlag.State_Enabled | QStyle.StateFlag.State_Horizontal
        style = option.widget.style() if option.widget else QApplication.style()
        style.drawControl(QStyle.ControlElement.CE_ProgressBar, bar, painter, option.widget)


ALWAYS_SHOWN = frozenset({"File", "Address", "Folder", "Status"})


class DetailsPanel(QFrame):
    """Everything about the selected download, under the list."""

    show_in_folder = Signal()
    copy_address = Signal()

    FIELDS = ("File", "Address", "Folder", "Size", "Progress", "Speed", "Connections",
              "Status", "Checksum", "From the browser", "Added", "Finished")  # fmt: skip

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("details")
        self.title = QLabel("No download selected")
        self.title.setObjectName("detailsTitle")
        self.title.setTextFormat(Qt.TextFormat.PlainText)
        self.values: dict[str, QLabel] = {}
        self.form = form = QFormLayout()
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(4)
        for name in self.FIELDS:
            value = QLabel("")
            value.setTextFormat(Qt.TextFormat.PlainText)  # names and addresses are never HTML
            value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            value.setWordWrap(True)
            label = QLabel(name)
            label.setProperty("muted", True)
            form.addRow(label, value)
            self.values[name] = value
        self.folder_button = QPushButton("Show in folder")
        self.folder_button.clicked.connect(self.show_in_folder)
        self.copy_button = QPushButton("Copy address")
        self.copy_button.clicked.connect(self.copy_address)
        buttons = QHBoxLayout()
        buttons.addWidget(self.folder_button)
        buttons.addWidget(self.copy_button)
        buttons.addStretch()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.addWidget(self.title)
        layout.addLayout(form)
        layout.addLayout(buttons)
        self.show_record(None)

    def show_record(
        self,
        record: DownloadRecord | None,
        *,
        speed: float | None = None,
        time_left: float | None = None,
        connections: int = 1,
        finished_file_ok: bool = False,
    ) -> None:
        if record is None:
            self.title.setText("No download selected")
            for value in self.values.values():
                value.setText("")
            self.folder_button.setEnabled(False)
            self.copy_button.setEnabled(False)
            return
        downloading = record.state == DownloadState.DOWNLOADING
        self.title.setText(record.file_name or redact_url(record.url))
        total, received = record.total_bytes, record.received_bytes
        progress = (
            f"{format_size(received)} of {format_size(total)}"
            if total is not None
            else format_size(received)
        )
        if downloading and time_left is not None:
            progress += f", {format_duration(time_left)} left"
        status = STATE_LABELS[record.state]
        if record.error:
            status += f": {record.error}"
        page = urlsplit(record.referrer).hostname if record.referrer else None
        browser = ", ".join(
            part
            for part in (
                f"page on {page}" if page else "",
                f"named {record.suggested_name}" if record.suggested_name else "",
            )
            if part
        )
        texts = {
            "File": record.path or record.file_name or "(not known yet)",
            # The query string may hold an access token: the panel shows the address without
            # it; Copy address copies the full address, which is the user's own.
            "Address": redact_url(record.url),
            "Folder": record.folder,
            "Size": format_size(total) if total is not None else "Unknown",
            "Progress": progress,
            "Speed": format_speed(speed) if downloading and speed is not None else "",
            "Connections": str(connections) if downloading else "",
            "Status": status,
            "Checksum": _checksum_text(record),
            "From the browser": browser or "No",
            "Added": _local(record.created_at),
            "Finished": _local(record.finished_at) if record.finished_at else "",
        }
        for name, text in texts.items():
            self.values[name].setText(text)
            # Rows with nothing to say (speed of a finished download...) are hidden.
            self.form.setRowVisible(self.values[name], bool(text) or name in ALWAYS_SHOWN)
        self.folder_button.setEnabled(finished_file_ok)
        self.copy_button.setEnabled(True)


def _checksum_text(record: DownloadRecord) -> str:
    if not record.expected_sha256:
        return "Not checked"
    result = CHECKSUM_LABELS.get(record.checksum_state or "", "waiting for the download")
    return f"SHA-256 {record.expected_sha256[:16]}…: {result}"


def _local(iso_utc: str | None) -> str:
    if not iso_utc:
        return ""
    try:
        return datetime.fromisoformat(iso_utc).astimezone().strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return ""
