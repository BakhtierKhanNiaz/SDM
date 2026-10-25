"""Tools > Convert file… and the list's Convert… (M12a, ADR-0020).

ffmpeg runs as a separate program through QProcess, so the window stays responsive and Cancel
can stop it. The source is only read; the result is a new file next to it. A failed or
cancelled conversion's partial file is deleted.
"""

from pathlib import Path

from PySide6.QtCore import QProcess, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from sdm.media.ffmpeg import (
    FORMATS,
    INSTALL_HINT,
    ConversionProgress,
    converted_path,
    ffmpeg_arguments,
)

MAX_ERROR_LENGTH = 300


class _Lines:
    """Splits a process's output into whole lines (a read can end mid-line)."""

    def __init__(self) -> None:
        self._rest = ""

    def feed(self, data: bytes) -> list[str]:
        text = self._rest + data.decode("utf-8", errors="replace")
        *lines, self._rest = text.replace("\r", "\n").split("\n")
        return lines


class ConvertDialog(QDialog):
    # The finished file, so the main window can show it in File Explorer.
    show_requested = Signal(Path)

    def __init__(
        self,
        *,
        ffmpeg: list[str] | None,
        source: Path | None = None,
        parent: QWidget | None = None,
    ) -> None:
        """`ffmpeg` is the command to run (normally just ffmpeg.exe), or None if not found."""
        super().__init__(parent)
        self.setWindowTitle("Convert file")
        self.setMinimumWidth(520)
        self._ffmpeg = ffmpeg
        self.process: QProcess | None = None
        self.target: Path | None = None
        self.result: Path | None = None  # the converted file, once done
        self.progress = ConversionProgress()

        self.source_edit = QLineEdit(str(source) if source else "")
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse)
        source_row = QHBoxLayout()
        source_row.addWidget(self.source_edit)
        source_row.addWidget(browse)
        self.format_box = QComboBox()
        for fmt in FORMATS.values():
            self.format_box.addItem(fmt.label, fmt.key)
        form = QFormLayout()
        form.addRow("File:", source_row)
        form.addRow("Convert to:", self.format_box)
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setValue(0)
        self.status_label = QLabel(
            "SDM makes a new file next to the original; the original stays as it is."
        )
        self.status_label.setWordWrap(True)
        self.convert_button = QPushButton("Convert")
        self.convert_button.setDefault(True)
        self.convert_button.clicked.connect(self.start)
        self.show_button = QPushButton("Show in folder")
        self.show_button.hide()
        self.show_button.clicked.connect(lambda: self.show_requested.emit(self.result))
        self.close_button = QPushButton("Close")
        self.close_button.clicked.connect(self.close_or_cancel)
        buttons = QHBoxLayout()
        buttons.addStretch()
        for button in (self.show_button, self.convert_button, self.close_button):
            buttons.addWidget(button)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.bar)
        layout.addWidget(self.status_label)
        layout.addLayout(buttons)

        if ffmpeg is None:
            self.convert_button.setEnabled(False)
            self.status_label.setText(
                f"Converting needs ffmpeg, which wasn't found. {INSTALL_HINT}"
            )

    @property
    def running(self) -> bool:
        return self.process is not None

    def start(self) -> bool:
        """Starts ffmpeg; False (with the reason shown) if it can't start."""
        if self._ffmpeg is None or self.running:
            return False
        source = Path(self.source_edit.text().strip().strip('"'))
        if not source.is_absolute() or not source.is_file():
            self.status_label.setText("Choose a file that exists.")
            return False
        fmt = FORMATS[self.format_box.currentData()]
        self.target = converted_path(source, fmt)
        self.progress = ConversionProgress()
        self._out, self._err = _Lines(), _Lines()
        process = QProcess(self)
        process.setProgram(self._ffmpeg[0])
        process.setArguments([*self._ffmpeg[1:], *ffmpeg_arguments(source, self.target, fmt)])
        process.readyReadStandardOutput.connect(self._read_progress)
        process.readyReadStandardError.connect(self._read_log)
        process.finished.connect(self._finished)
        process.errorOccurred.connect(self._error)
        self.process = process
        self.result = None
        self.show_button.hide()
        self.convert_button.setEnabled(False)
        self.close_button.setText("Cancel")
        self.bar.setRange(0, 0)  # busy until ffmpeg says how long the file is
        self.status_label.setText(f"Converting to {self.target.name}…")
        process.start()
        return True

    def close_or_cancel(self) -> None:
        if self.running:
            self.cancel()
        else:
            self.reject()

    def cancel(self) -> None:
        if self.process is None:
            return
        process, self.process = self.process, None
        process.finished.disconnect(self._finished)
        process.errorOccurred.disconnect(self._error)
        process.kill()
        process.waitForFinished(5000)
        self._remove_partial()
        self._ready_again("Cancelled. The partial file was deleted.")

    def reject(self) -> None:
        if self.running:
            self.cancel()
        super().reject()

    # ----- ffmpeg's output -----

    def _read_progress(self) -> None:
        if self.process is None:
            return
        for line in self._out.feed(bytes(self.process.readAllStandardOutput().data())):
            self.progress.progress_line(line)
        self._show_progress()

    def _read_log(self) -> None:
        if self.process is None:
            return
        for line in self._err.feed(bytes(self.process.readAllStandardError().data())):
            self.progress.log_line(line)
        self._show_progress()

    def _show_progress(self) -> None:
        percent = self.progress.percent
        if percent is not None:
            self.bar.setRange(0, 100)
            self.bar.setValue(percent)

    def _finished(self, exit_code: int, exit_status: QProcess.ExitStatus) -> None:
        if self.process is None:
            return
        self._read_progress()
        self._read_log()
        self.process = None
        ok = exit_status == QProcess.ExitStatus.NormalExit and exit_code == 0
        if ok and self.target is not None and self.target.is_file():
            self.result = self.target
            self.bar.setRange(0, 100)
            self.bar.setValue(100)
            self._ready_again(f"Done: {self.target.name}")
            self.show_button.show()
            return
        self._remove_partial()
        reason = self.progress.failure_reason[:MAX_ERROR_LENGTH] or f"exit code {exit_code}"
        self._ready_again(f"ffmpeg couldn't convert the file: {reason}")

    def _error(self, error: QProcess.ProcessError) -> None:
        if error != QProcess.ProcessError.FailedToStart or self.process is None:
            return  # a crash also ends in finished(), which reports it
        self.process = None
        self._ready_again(f"ffmpeg couldn't be started. {INSTALL_HINT}")

    def _remove_partial(self) -> None:
        # The target didn't exist before (converted_path), so whatever is there is ffmpeg's.
        if self.target is not None:
            self.target.unlink(missing_ok=True)

    def _ready_again(self, text: str) -> None:
        if self.result is None:
            self.bar.setRange(0, 100)
            self.bar.setValue(0)
        self.status_label.setText(text)
        self.convert_button.setEnabled(self._ffmpeg is not None)
        self.close_button.setText("Close")

    def _browse(self) -> None:
        chosen, _ = QFileDialog.getOpenFileName(
            self, "Convert file", self.source_edit.text(), "Media files (*.*)"
        )
        if chosen:
            self.source_edit.setText(str(Path(chosen)))
