"""Carries engine events from the engine thread to the window's main thread (ADR-0009)."""

from PySide6.QtCore import QObject, Signal

from sdm.engine.manager import DownloadEvent


class EngineAdapter(QObject):
    """Pass an instance to DownloadManager as its `on_event`.

    The manager calls it on the engine thread. It only re-emits the event as a Qt signal.
    This object lives on the main thread, so Qt queues the signal and delivers it there, where
    slots may safely touch widgets and the database.
    """

    event_received = Signal(object)

    def __call__(self, event: DownloadEvent) -> None:
        self.event_received.emit(event)
