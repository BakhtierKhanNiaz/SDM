"""The Scheduler dialog: how many downloads at once, when the queue may run, subfolders (M6)."""

from datetime import time

from PySide6.QtCore import QTime
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QSpinBox,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from sdm.scheduler.queue import MAX_LIMIT, MIN_LIMIT, QueueSettings, Schedule

DAY_NAMES = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


class SchedulerDialog(QDialog):
    def __init__(self, settings: QueueSettings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Queue and scheduler")
        schedule = settings.schedule

        self.limit_spin = QSpinBox()
        self.limit_spin.setRange(MIN_LIMIT, MAX_LIMIT)
        self.limit_spin.setValue(settings.limit)
        self.schedule_check = QCheckBox("Only run the queue at these times:")
        self.schedule_check.setChecked(schedule.enabled)
        self.start_edit = QTimeEdit(QTime(schedule.start.hour, schedule.start.minute))
        self.stop_edit = QTimeEdit(QTime(schedule.stop.hour, schedule.stop.minute))
        for edit in (self.start_edit, self.stop_edit):
            edit.setDisplayFormat("HH:mm")
        self.day_checks = [QCheckBox(name) for name in DAY_NAMES]
        for index, check in enumerate(self.day_checks):
            check.setChecked(index in schedule.days)
        self.subfolder_check = QCheckBox(
            "Save each download into a folder for its category (for example Downloads\\Compressed)"
        )
        self.subfolder_check.setChecked(settings.category_subfolders)
        self.error_label = QLabel()
        self.error_label.setStyleSheet("color: #b00020")
        self.error_label.hide()

        times = QHBoxLayout()
        times.addWidget(QLabel("from"))
        times.addWidget(self.start_edit)
        times.addWidget(QLabel("to"))
        times.addWidget(self.stop_edit)
        times.addStretch()
        days = QHBoxLayout()
        for check in self.day_checks:
            days.addWidget(check)
        form = QFormLayout()
        form.addRow("Downloads at once:", self.limit_spin)
        note = QLabel(
            "Outside these times, running downloads go back to waiting (what arrived is kept)."
            " A window like 23:00 to 06:00 runs overnight. Start now ignores the schedule."
        )
        note.setWordWrap(True)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.schedule_check)
        layout.addLayout(times)
        layout.addLayout(days)
        layout.addWidget(note)
        layout.addWidget(self.subfolder_check)
        layout.addWidget(self.error_label)
        layout.addWidget(buttons)

        self.schedule_check.toggled.connect(self._update_enabled)
        self._update_enabled()

    def settings(self) -> QueueSettings:
        start, stop = self.start_edit.time(), self.stop_edit.time()
        return QueueSettings(
            limit=self.limit_spin.value(),
            schedule=Schedule(
                enabled=self.schedule_check.isChecked(),
                start=time(start.hour(), start.minute()),
                stop=time(stop.hour(), stop.minute()),
                days=frozenset(i for i, check in enumerate(self.day_checks) if check.isChecked()),
            ),
            category_subfolders=self.subfolder_check.isChecked(),
        )

    def accept(self) -> None:
        settings = self.settings()
        if settings.schedule.enabled and not settings.schedule.days:
            self.error_label.setText("Choose at least one day, or turn the schedule off.")
            self.error_label.show()
            return
        super().accept()

    def _update_enabled(self) -> None:
        on = self.schedule_check.isChecked()
        for widget in (self.start_edit, self.stop_edit, *self.day_checks):
            widget.setEnabled(on)
