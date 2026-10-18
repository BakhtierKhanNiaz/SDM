"""Dynamic splitting (M5b): free connections take over half of the part with the most left."""

import asyncio
import hashlib
import os

from sdm.core.downloads import PartialDownload
from sdm.core.segments import Segment, pick_split
from sdm.engine.http_download import download
from sdm.engine.models import DownloadSettings

DATA = os.urandom(800_000)
DYNAMIC = DownloadSettings(
    connect_timeout=5.0,
    read_timeout=10.0,
    backoff_base=0.0,
    max_connections=4,
    min_split_size=200_000,
    min_part_size=100_000,
)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def requested(mock_server) -> list:
    return [headers.get("Range") for headers in mock_server.requests]


def partial_file(tmp_path, segments) -> PartialDownload:
    part = tmp_path / "data.bin.sdmpart"
    content = bytearray(len(DATA))
    for segment in segments:
        content[segment.start : segment.next_byte] = DATA[segment.start : segment.next_byte]
    part.write_bytes(bytes(content))
    return PartialDownload(part, "data.bin", len(DATA), '"v1"', None, True, segments=segments)


def test_pick_split_halves_the_part_with_the_most_left():
    assert pick_split([(0, 99_999), (200_000, 799_999)], 100_000) == (1, 500_000)
    assert pick_split([(0, 299_999), (300_000, 599_999)], 100_000) == (0, 150_000)  # tie
    assert pick_split([(0, 150_000)], 100_000) is None  # halves would be too small


def test_a_resume_fills_free_connections_by_halving(mock_server, tmp_path, loopback_policy):
    # One unfinished part of 600,000 bytes and 4 connections allowed: it is halved, then the
    # biggest remaining piece is halved again, until 4 connections are busy.
    segments = (Segment(0, 199_999, 200_000), Segment(200_000, 799_999, 0))
    mock_server.add("/data.bin", mock_server.ranged(DATA, etag='"v1"'))

    result = asyncio.run(
        download(
            mock_server.url("/data.bin"),
            tmp_path,
            policy=loopback_policy,
            settings=DYNAMIC,
            resume_from=partial_file(tmp_path, segments),
        )
    )

    assert sha(result.path.read_bytes()) == sha(DATA)
    assert sorted(requested(mock_server)) == [
        "bytes=200000-349999",
        "bytes=350000-499999",
        "bytes=500000-649999",
        "bytes=650000-799999",
    ]


def test_a_connection_that_finishes_early_helps_the_slowest(mock_server, tmp_path, loopback_policy):
    # Part 1 needs only 1,000 bytes; part 2 needs 700,000 at 200 KB/s. When part 1 is done, its
    # connection takes over the second half of part 2.
    # Regression: part 2's reply was once checked against its *new* end (shrunk by the split
    # while its request was in flight), looked wrong, and the whole file restarted.
    segments = (Segment(0, 99_999, 99_000), Segment(100_000, 799_999, 0))
    mock_server.add("/data.bin", mock_server.ranged(DATA, etag='"v1"', rate=200_000))
    two = DownloadSettings(**{**DYNAMIC.__dict__, "max_connections": 2})
    counts = []

    result = asyncio.run(
        download(
            mock_server.url("/data.bin"),
            tmp_path,
            policy=loopback_policy,
            settings=two,
            resume_from=partial_file(tmp_path, segments),
            on_connections=counts.append,
        )
    )

    assert sha(result.path.read_bytes()) == sha(DATA)
    ranges = requested(mock_server)
    assert "bytes=99000-99999" in ranges
    helper = [r for r in ranges if r.endswith("-799999") and r != "bytes=100000-799999"]
    assert len(helper) == 1
    start = int(helper[0].removeprefix("bytes=").split("-")[0])
    assert 400_000 < start < 500_000  # about halfway through what part 2 still needed
    assert max(counts) == 2


def test_connection_count_is_reported(mock_server, tmp_path, loopback_policy):
    mock_server.add("/data.bin", mock_server.ranged(DATA, etag='"v1"'))
    counts = []

    asyncio.run(
        download(
            mock_server.url("/data.bin"),
            tmp_path,
            policy=loopback_policy,
            settings=DYNAMIC,
            on_connections=counts.append,
        )
    )

    assert max(counts) == 4
    assert counts[0] == 1  # the first connection starts alone
