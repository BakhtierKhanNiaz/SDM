"""Speed and time left from progress samples (times are passed in, so no real waiting)."""

import pytest

from sdm.core.progress import TransferMeter


def feed(meter: TransferMeter, start: float, end: float, rate: float, received: float) -> float:
    """Simulate `rate` bytes/s from `start` to `end` in 0.1 s steps; return bytes received."""
    steps = round((end - start) / 0.1)
    for step in range(1, steps + 1):
        received += rate * 0.1
        meter.update(round(received), now=start + step * 0.1)
    return received


def test_no_speed_until_there_is_half_a_second_of_data():
    meter = TransferMeter()
    meter.update(0, now=0.0)
    meter.update(1000, now=0.2)
    assert meter.speed is None
    assert meter.time_left(10_000) is None


def test_steady_speed():
    meter = TransferMeter()
    meter.update(0, now=0.0)
    feed(meter, 0.0, 5.0, rate=100_000, received=0)
    assert meter.speed == pytest.approx(100_000, rel=0.01)


def test_speed_follows_the_last_few_seconds():
    meter = TransferMeter(window=3.0)
    meter.update(0, now=0.0)
    received = feed(meter, 0.0, 3.0, rate=100_000, received=0)
    feed(meter, 3.0, 6.0, rate=10_000, received=received)
    assert meter.speed == pytest.approx(10_000, rel=0.02)


def test_time_left():
    meter = TransferMeter()
    meter.update(0, now=0.0)
    feed(meter, 0.0, 5.0, rate=100_000, received=0)  # 500,000 bytes so far
    assert meter.time_left(1_000_000) == pytest.approx(5.0, rel=0.02)
    assert meter.time_left(None) is None  # size unknown


def test_stalled_transfer_has_zero_speed_and_no_time_left():
    meter = TransferMeter()
    for second in range(5):
        meter.update(1000, now=float(second))
    assert meter.speed == 0.0
    assert meter.time_left(10_000) is None
