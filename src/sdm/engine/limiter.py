"""One speed limit shared by every connection of every download (M9, ADR-0016).

A "token bucket": the bucket fills at `rate` bytes per second, up to half a second's worth.
Each chunk read from the network takes its size from the bucket; when the bucket goes below
zero, the reader sleeps until it is back above. Slow reading makes TCP slow the sender down,
so the limit holds on the wire too. Readers that arrive while the bucket is in debt add to the
debt, so all connections together never exceed the rate.

Everything here runs on the engine's event loop thread; `set_rate` is called there too
(the manager forwards it with call_soon_threadsafe).
"""

import asyncio
import time
from collections.abc import Callable

BURST_SECONDS = 0.5  # how much unused allowance may build up while idle
CHECK_EVERY = 0.25  # seconds: a sleeper looks again this often, so a new limit acts quickly
MIN_RATE = 1024  # bytes per second: anything lower is treated as this


class SpeedLimiter:
    def __init__(
        self, rate: int | None = None, *, clock: Callable[[], float] | None = None
    ) -> None:
        self._clock = clock
        self._rate: int | None = None
        self._tokens = 0.0
        self._last = 0.0
        self.set_rate(rate)

    @property
    def rate(self) -> int | None:
        """Bytes per second, or None for no limit."""
        return self._rate

    def set_rate(self, rate: int | None) -> None:
        self._rate = None if not rate or rate <= 0 else max(int(rate), MIN_RATE)
        self._tokens = 0.0  # a new limit starts from an empty bucket, never with a burst
        self._last = self._now()

    async def take(self, size: int) -> None:
        """Wait until `size` more bytes fit under the limit (returns at once when unlimited)."""
        if self._rate is None or size <= 0:
            return
        self._refill()
        self._tokens -= size
        while self._rate is not None:
            self._refill()
            if self._tokens >= 0:
                return
            await asyncio.sleep(min(CHECK_EVERY, -self._tokens / self._rate))
        self._tokens = 0.0  # the limit was switched off while waiting

    def _refill(self) -> None:
        now = self._now()
        if self._rate is not None:
            self._tokens = min(
                self._tokens + (now - self._last) * self._rate, self._rate * BURST_SECONDS
            )
        self._last = now

    def _now(self) -> float:
        return self._clock() if self._clock is not None else time.monotonic()
