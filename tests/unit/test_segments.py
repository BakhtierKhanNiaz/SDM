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
