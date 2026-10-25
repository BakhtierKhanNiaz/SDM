"""The sidebar (M13): which downloads the list shows, with how many there are of each.

All, Downloading (running or waiting), Finished, Unfinished (paused, failed, interrupted), then
one entry per file type. It replaces M6's small category box.
"""

from PySide6.QtCore import (
    QModelIndex,
    QPersistentModelIndex,
    QSize,
    QSortFilterProxyModel,
    Qt,
    Signal,
)
from PySide6.QtWidgets import QListWidget, QListWidgetItem

from sdm.core.categories import CATEGORIES
from sdm.core.downloads import DownloadRecord, DownloadState
from sdm.ui.glyphs import CATEGORY_COLOURS, glyph

VIEWS = (
    ("all", "All downloads"),
    ("downloading", "Downloading"),
    ("finished", "Finished"),
    ("unfinished", "Unfinished"),
)
VIEW_KEY = Qt.ItemDataRole.UserRole + 10


def matches_view(record: DownloadRecord, view: str) -> bool:
    """Whether the list shows `record` when `view` is chosen in the sidebar."""
    if view == "all":
        return True
    if view == "downloading":
        return record.state.is_active
    if view == "finished":
        return record.state == DownloadState.COMPLETED
    if view == "unfinished":
        return record.state.can_resume
    return record.category == view  # a file type


class DownloadFilter(QSortFilterProxyModel):
    """Shows the download list's rows that match the sidebar's choice."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.view = "all"

    def set_view(self, view: str) -> None:
        self.beginFilterChange()
        self.view = view
        self.endFilterChange()

    def refilter(self) -> None:
        """Check every row again (a download finished, so it moves to Finished)."""
        self.beginFilterChange()
        self.endFilterChange()

    def filterAcceptsRow(
        self, source_row: int, source_parent: QModelIndex | QPersistentModelIndex
    ) -> bool:
        record = self.sourceModel().record_at(source_row)
        return matches_view(record, self.view)


class Sidebar(QListWidget):
    view_changed = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setIconSize(QSize(20, 20))
        self.setMinimumWidth(170)
        self._items: dict[str, QListWidgetItem] = {}
        self._labels: dict[str, str] = {}
        for key, label in VIEWS:
            self._add(key, label)
        heading = QListWidgetItem("FILE TYPES")
        heading.setFlags(Qt.ItemFlag.NoItemFlags)  # a label, not a choice
        heading.setData(Qt.ItemDataRole.UserRole, "heading")
        self.addItem(heading)
        for category in CATEGORIES:
            self._add(category, category)
        self.setCurrentItem(self._items["all"])
        self.currentItemChanged.connect(self._chosen)

    def _add(self, key: str, label: str) -> None:
        item = QListWidgetItem(label)
        item.setData(VIEW_KEY, key)
        self.addItem(item)
        self._items[key] = item
        self._labels[key] = label

    @property
    def view(self) -> str:
        item = self.currentItem()
        return item.data(VIEW_KEY) if item is not None else "all"

    def select_view(self, view: str) -> None:
        self.setCurrentItem(self._items[view])

    def _chosen(self, item: QListWidgetItem | None, _previous: object) -> None:
        if item is not None and item.data(VIEW_KEY):
            self.view_changed.emit(item.data(VIEW_KEY))

    def update_counts(self, records: list[DownloadRecord]) -> None:
        for key, item in self._items.items():
            count = sum(1 for record in records if matches_view(record, key))
            text = f"{self._labels[key]}  ({count})" if count else self._labels[key]
            if item.text() != text:
                item.setText(text)

    def count_text(self, view: str) -> str:
        return self._items[view].text()

    def set_colours(self, text: str) -> None:
        """Redraw the icons for the light or dark look."""
        for key, item in self._items.items():
            if key in CATEGORY_COLOURS:
                item.setIcon(glyph(key, CATEGORY_COLOURS[key]))
            else:
                item.setIcon(glyph(key, text))
