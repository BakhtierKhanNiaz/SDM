"""Carries browser handoffs from the bridge's worker threads to the main thread (ADR-0014)."""

import threading

from PySide6.QtCore import QObject, Signal

from sdm.bridge.protocol import DownloadRequest


class HandoffReceiver(QObject):
    """`offer` runs on a bridge thread; `received` is delivered on the main (GUI) thread.

    At most MAX_PENDING handoffs wait for the user at once, so a flood of clicks (or a
    misbehaving page script clicking for the user) can't pile up dialogs; extra ones are
    answered "busy".
    """

    MAX_PENDING = 5
    received = Signal(object)  # the whole DownloadRequest (M8), delivered on the main thread

    def __init__(self) -> None:
        super().__init__()
        self._lock = threading.Lock()
        self._pending = 0

    def offer(self, request: DownloadRequest) -> bool:
        with self._lock:
            if self._pending >= self.MAX_PENDING:
                return False
            self._pending += 1
        # Emitted from another thread, so Qt queues it to this object's (the main) thread.
        self.received.emit(request)
        return True

    def done(self) -> None:
        """One handoff's dialog closed (main thread)."""
        with self._lock:
            self._pending = max(0, self._pending - 1)
