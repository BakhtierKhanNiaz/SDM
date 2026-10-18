"""Transfer speed and time left, averaged over the last few seconds.

A download's speed jumps around from one chunk to the next. Averaging over a short window
(3 s by default) gives numbers that are steady enough to read but still react to real changes.
"""

import time
from collections import deque
from collections.abc import Callable

MIN_SPAN = 0.5  # seconds of samples needed before showing a speed at all


class TransferMeter:
    """Feed it (time, bytes received so far); ask it for speed and time left."""

    def __init__(self, window: float = 3.0, clock: Callable[[], float] = time.monotonic) -> None:
        self._window = window
        self._clock = clock
        self._samples: deque[tuple[float, int]] = deque()

    def update(self, received: int, now: float | None = None) -> None:
        now = self._clock() if now is None else now
        self._samples.append((now, received))
        # Keep one sample older than the window, so the span covers the whole window.
        while len(self._samples) > 2 and self._samples[1][0] <= now - self._window:
            self._samples.popleft()

    @property
    def speed(self) -> float | None:
        """Bytes per second over the window, or None until there is enough data."""
        if len(self._samples) < 2:
            return None
        (t0, r0), (t1, r1) = self._samples[0], self._samples[-1]
        if t1 - t0 < MIN_SPAN:
            return None
        return max(0.0, (r1 - r0) / (t1 - t0))

    def time_left(self, total: int | None) -> float | None:
        """Seconds until done at the current speed; None if the size or speed is unknown."""
        speed = self.speed
        if total is None or not speed or not self._samples:
            return None
        return max(0.0, (total - self._samples[-1][1]) / speed)
