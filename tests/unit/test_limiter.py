"""The shared speed limit, on a simulated clock: instant and exact (M9)."""

import asyncio

import pytest

from sdm.engine import limiter as limiter_module
from sdm.engine.limiter import MIN_RATE, SpeedLimiter

KIB = 1024


@pytest.fixture
def clock(monkeypatch):
    """A fake clock that asyncio.sleep inside the limiter advances instead of waiting."""
    now = [0.0]
    real_sleep = asyncio.sleep

    async def fake_sleep(seconds):
        now[0] += seconds
        await real_sleep(0)  # let the other readers run

    monkeypatch.setattr(limiter_module.asyncio, "sleep", fake_sleep)
    return now


def run(coroutine):
    return asyncio.run(coroutine)


async def read(limiter, total, chunk=64 * KIB):
    sent = 0
    while sent < total:
        await limiter.take(chunk)
        sent += chunk


def test_no_limit_never_waits(clock):
    limiter = SpeedLimiter(None, clock=lambda: clock[0])
    run(read(limiter, 10 * 1024 * KIB))
    assert clock[0] == 0


def test_one_reader_gets_the_rate(clock):
    limiter = SpeedLimiter(256 * KIB, clock=lambda: clock[0])
    run(read(limiter, 1024 * KIB))
    assert clock[0] == pytest.approx(4.0, abs=0.3)  # 1 MiB at 256 KiB/s


def test_eight_connections_share_one_limit(clock):
    limiter = SpeedLimiter(256 * KIB, clock=lambda: clock[0])

    async def eight():
        await asyncio.gather(*(read(limiter, 128 * KIB) for _ in range(8)))

    run(eight())
    assert clock[0] == pytest.approx(4.0, abs=0.3)  # 8 x 128 KiB together, not 8 times faster


def test_turning_the_limit_off_releases_waiting_readers(clock):
    limiter = SpeedLimiter(MIN_RATE, clock=lambda: clock[0])

    async def scenario():
        reader = asyncio.ensure_future(read(limiter, 1024 * KIB))
        for _ in range(5):
            await asyncio.sleep(0)
        limiter.set_rate(None)
        await reader

    run(scenario())
    assert clock[0] < 2  # 1 MiB at 1 KiB/s would have taken about 17 minutes


def test_a_new_limit_applies_from_the_next_chunk(clock):
    limiter = SpeedLimiter(128 * KIB, clock=lambda: clock[0])

    async def scenario():
        await read(limiter, 256 * KIB)  # about 2 s
        start = clock[0]
        limiter.set_rate(512 * KIB)
        await read(limiter, 1024 * KIB)  # about 2 s more
        return clock[0] - start

    assert run(scenario()) == pytest.approx(2.0, abs=0.3)


def test_tiny_or_silly_limits(clock):
    assert SpeedLimiter(1).rate == MIN_RATE
    assert SpeedLimiter(0).rate is None
    assert SpeedLimiter(-5).rate is None
