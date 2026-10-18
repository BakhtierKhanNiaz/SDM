"""Human-readable sizes, speeds and durations."""

import pytest

from sdm.core.units import format_duration, format_size, format_speed


@pytest.mark.parametrize(
    ("num_bytes", "expected"),
    [(0, "0 bytes"), (1023, "1023 bytes"), (1536, "1.5 KB"), (5 * 1024**3, "5.0 GB")],
)
def test_format_size(num_bytes, expected):
    assert format_size(num_bytes) == expected


def test_format_speed():
    assert format_speed(1536) == "1.5 KB/s"


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [
        (-5, "0 s"),
        (0, "0 s"),
        (42, "42 s"),
        (59.6, "1 min 00 s"),
        (125, "2 min 05 s"),
        (3725, "1 h 02 min"),
    ],
)
def test_format_duration(seconds, expected):
    assert format_duration(seconds) == expected
