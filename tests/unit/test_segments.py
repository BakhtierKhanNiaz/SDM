"""Planning parts for parallel connections, and checking saved parts maps."""

import pytest

from sdm.core.segments import (
    Segment,
    decode_segments,
    encode_segments,
    plan_segments,
    segments_cover,
    total_received,
)

MIB = 1024 * 1024


def bounds(segments):
    return [(s.start, s.end) for s in segments]


def test_equal_parts_with_the_remainder_in_the_last():
    assert bounds(plan_segments(1000, 3, 100)) == [(0, 332), (333, 665), (666, 999)]


@pytest.mark.parametrize(
    ("total", "connections", "expected_parts"),
    [
        (10 * MIB, 8, 8),  # big file: one part per connection
        (3 * MIB, 8, 3),  # parts of at least 1 MiB
        (MIB + MIB // 2, 8, 1),  # too small to split
        (800_000, 4, 4),
        (800_000, 1, 1),
    ],
)
def test_part_count(total, connections, expected_parts):
    segments = plan_segments(total, connections, MIB if total > MIB else 100_000)
    assert len(segments) == expected_parts
    assert segments_cover(segments, total)


def test_plan_needs_a_size():
    with pytest.raises(ValueError):
        plan_segments(0, 8, MIB)


def test_segment_properties():
    segment = Segment(100, 199, 40)
    assert (segment.size, segment.next_byte, segment.remaining, segment.done) == (
        100,
        140,
        60,
        False,
    )
    assert Segment(100, 199, 100).done
    assert total_received([segment, Segment(200, 299, 5)]) == 45


def test_encode_decode_round_trip():
    segments = (Segment(0, 499, 500), Segment(500, 999, 120))
    assert decode_segments(encode_segments(segments), 1000) == segments


@pytest.mark.parametrize(
    "text",
    [
        "not json",
        '{"a": 1}',
        "[[0, 499]]",  # wrong arity
        "[[0, 499, 0], [600, 999, 0]]",  # gap
        "[[0, 599, 0], [500, 999, 0]]",  # overlap
        "[[0, 999, 1001]]",  # more received than the part holds
        "[[0, 999, -1]]",
        "[[0, 998, 0]]",  # doesn't reach the end
        "[[1, 999, 0]]",  # doesn't start at 0
        "[[0, 999, true]]",  # a bool is not a byte count
        '[[0, 999, "5"]]',
        "[]",
    ],
)
def test_decode_rejects_maps_that_dont_fit(text):
    assert decode_segments(text, 1000) is None


def test_decode_needs_the_total():
    assert decode_segments("[[0, 999, 0]]", None) is None
    assert decode_segments(None, 1000) is None


def test_presizing_a_part_file_writes_nothing(tmp_path):
    """Regression (M10): Python's truncate() grows a file on Windows by writing zeros, which
    wrote a 1 GiB split download's whole file before it could start, on the event loop."""
    import os
    import stat
    import time

    from sdm.engine.segmented import prepare_part_file, set_file_size

    path = tmp_path / "big.sdmpart"
    path.write_bytes(b"old")
    size = 4 * 1024**3  # 4 GiB: zero-filling this would take far longer than a second
    started = time.perf_counter()
    prepare_part_file(path, size)
    assert time.perf_counter() - started < 1.0
    assert path.stat().st_size == size
    attributes = os.stat(path).st_file_attributes
    assert attributes & stat.FILE_ATTRIBUTE_SPARSE_FILE  # no disk space used for the gaps
    with open(path, "rb") as file:
        assert file.read(3) == b"\0\0\0"  # the old content was dropped, as before
    with open(path, "r+b") as file:
        set_file_size(file, 10)  # shrinking works too
    assert path.stat().st_size == 10
