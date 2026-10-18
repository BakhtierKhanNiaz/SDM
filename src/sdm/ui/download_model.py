"""The download list's table model: one row per history entry, plus live speed and time left.

Qt's model/view design: the model holds the data and says how each cell reads; the QTableView
only draws. When a row changes, the model emits dataChanged and the view repaints that row.
"""

from dataclasses import dataclass, replace

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QPersistentModelIndex, Qt

from sdm.core.downloads import DownloadRecord, DownloadState
from sdm.core.units import format_duration, format_size, format_speed
from sdm.core.urls import redact_url

COLUMNS = ("File name", "Category", "Size", "Progress", "Speed", "Time left", "Status")
NAME, CATEGORY, SIZE, PROGRESS, SPEED, TIME_LEFT, STATUS = range(len(COLUMNS))

STATE_LABELS = {
    DownloadState.QUEUED: "Queued",
    DownloadState.DOWNLOADING: "Downloading",
    DownloadState.PAUSED: "Paused",
    DownloadState.COMPLETED: "Completed",
    DownloadState.FAILED: "Failed",
    DownloadState.CANCELLED: "Cancelled",
    DownloadState.INTERRUPTED: "Interrupted",
}
UNCONFIRMED = (
    "The server didn't say how big the file is, so SDM can't confirm that the whole file arrived."
)

Index = QModelIndex | QPersistentModelIndex


@dataclass
class _Row:
    record: DownloadRecord
    speed: float | None = None  # bytes per second, while downloading
    time_left: float | None = None  # seconds, while downloading with a known size
    connections: int = 1  # while downloading (M5)


class DownloadTableModel(QAbstractTableModel):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._rows: list[_Row] = []

    # ----- Qt's model interface -----

    def rowCount(self, parent: Index = QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent: Index = QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else len(COLUMNS)

    def headerData(self, section: int, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return COLUMNS[section]
        return None

    def data(self, index: Index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row = self._rows[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            return cell_text(row.record, index.column(), row.speed, row.time_left, row.connections)
        if role == Qt.ItemDataRole.ToolTipRole:
            return _tooltip(row.record, index.column())
        if role == Qt.ItemDataRole.TextAlignmentRole and index.column() in (
            SIZE,
            PROGRESS,
            SPEED,
            TIME_LEFT,
        ):
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        return None

    # ----- updating -----

    def set_records(self, records: list[DownloadRecord]) -> None:
        self.beginResetModel()
        self._rows = [_Row(record) for record in records]
        self.endResetModel()

    def upsert(self, record: DownloadRecord) -> None:
        """Add the record as a new row, or replace the row with the same id."""
        position = self._position(record.id)
        if position is None:
            self.beginInsertRows(QModelIndex(), len(self._rows), len(self._rows))
            self._rows.append(_Row(record))
            self.endInsertRows()
            return
        row = self._rows[position]
        row.record = record
        if record.state != DownloadState.DOWNLOADING:
            row.speed = row.time_left = None
            row.connections = 1
        self._changed(position)

    def set_live(
        self,
        download_id: int,
        received: int,
        total: int | None,
        speed: float | None,
        time_left: float | None,
        connections: int = 1,
    ) -> None:
        position = self._position(download_id)
        if position is None:
            return
        row = self._rows[position]
        row.record = replace(row.record, received_bytes=received, total_bytes=total)
        row.speed, row.time_left, row.connections = speed, time_left, connections
        self._changed(position)

    def remove(self, download_id: int) -> None:
        position = self._position(download_id)
        if position is not None:
            self.beginRemoveRows(QModelIndex(), position, position)
            del self._rows[position]
            self.endRemoveRows()

    # ----- reading -----

    def record(self, download_id: int) -> DownloadRecord | None:
        position = self._position(download_id)
        return None if position is None else self._rows[position].record

    def record_at(self, row: int) -> DownloadRecord:
        return self._rows[row].record

    def records(self) -> list[DownloadRecord]:
        return [row.record for row in self._rows]

    def _position(self, download_id: int) -> int | None:
        for position, row in enumerate(self._rows):
            if row.record.id == download_id:
                return position
        return None

    def _changed(self, position: int) -> None:
        self.dataChanged.emit(self.index(position, 0), self.index(position, len(COLUMNS) - 1))


def cell_text(
    record: DownloadRecord,
    column: int,
    speed: float | None = None,
    time_left: float | None = None,
    connections: int = 1,
) -> str:
    """What one cell of the download list says."""
    state, total, received = record.state, record.total_bytes, record.received_bytes
    downloading = state == DownloadState.DOWNLOADING
    if column == NAME:
        return record.file_name or redact_url(record.url)
    if column == CATEGORY:
        return record.category
    if column == SIZE:
        if total is not None:
            return format_size(total)
        # "Unknown" only once the server has answered without a size (file name is known).
        return "Unknown" if record.file_name else ""
    if column == PROGRESS:
        if total:
            return f"{min(100, received * 100 // total)}%"
        if total == 0 and state == DownloadState.COMPLETED:
            return "100%"
        return format_size(received) if received else ""
    if column == SPEED:
        return format_speed(speed) if downloading and speed is not None else ""
    if column == TIME_LEFT:
        return format_duration(time_left) if downloading and time_left is not None else ""
    if column == STATUS:
        label = STATE_LABELS[state]
        if state == DownloadState.QUEUED and record.retry_at:
            label = f"Retry {record.retry_count} of 3 at {_local_clock(record.retry_at)}"
        elif state == DownloadState.QUEUED and record.forced:
            label = "Starting now"
        if downloading and connections > 1:
            label += f" · {connections} connections"
        if state == DownloadState.COMPLETED and record.verified_complete is False:
            label += " (size unconfirmed)"
        return label
    return ""


def _tooltip(record: DownloadRecord, column: int) -> str | None:
    if column == NAME:
        return record.path or redact_url(record.url)
    if column == STATUS:
        lines = [record.error] if record.error else []
        if record.state == DownloadState.COMPLETED and record.verified_complete is False:
            lines.append(UNCONFIRMED)
        if record.state.can_resume:
            if record.part_path and record.resumable:
                lines.append("Resume continues from where it stopped.")
            elif record.part_path:
                lines.append("This server can't resume, so Resume starts over.")
            else:
                lines.append("Resume starts from the beginning.")
        return "\n".join(lines) or None
    return None


def _local_clock(iso_utc: str) -> str:
    from datetime import datetime

    try:
        return datetime.fromisoformat(iso_utc).astimezone().strftime("%H:%M")
    except ValueError:
        return "?"
