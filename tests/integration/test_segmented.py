"""Downloads split across several connections (M5): every test ends with a byte-for-byte check.

Small sizes keep the tests fast: files of at least 200,000 bytes are split into parts of at least
100,000 bytes, over up to 4 connections. An 800,000-byte file therefore gets 4 parts:
0-199999, 200000-399999, 400000-599999, 600000-799999.
"""

import asyncio
import dataclasses
import hashlib
import os
import sys
import time

import pytest

from sdm.core.downloads import PartialDownload
from sdm.core.segments import Segment, plan_segments
from sdm.engine.http_download import download
from sdm.engine.models import DownloadSettings
from sdm.engine.segmented import make_sparse

DATA = os.urandom(800_000)
NEW = os.urandom(800_000)
SPLIT = DownloadSettings(
    connect_timeout=5.0,
    read_timeout=10.0,
    backoff_base=0.0,
    max_connections=4,
    min_split_size=200_000,
    min_part_size=100_000,
)
EXTRA_RANGES = ["bytes=200000-399999", "bytes=400000-599999", "bytes=600000-799999"]


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def requested(mock_server) -> list:
    return [headers.get("Range") for headers in mock_server.requests]


def run(coro):
    return asyncio.run(coro)


# ----- splitting and putting the parts back together -----


def test_big_file_is_split_and_assembled(mock_server, fetch):
    log = []
    mock_server.add("/data.bin", mock_server.ranged(DATA, etag='"v1"', log=log))

    result = fetch(mock_server.url("/data.bin"), settings=SPLIT)

    assert sha(result.path.read_bytes()) == sha(DATA)
    ranges = requested(mock_server)
    assert ranges[0] is None  # the first connection is the ordinary request
    assert sorted(ranges[1:]) == EXTRA_RANGES
    assert all(h.get("If-Range") == '"v1"' for h in mock_server.requests[1:])
    assert sorted(status for _, status, _ in log) == [200, 206, 206, 206]
    assert [p.name for p in result.path.parent.iterdir()] == ["data.bin"]


def test_the_parts_map_is_reported_for_resuming(mock_server, tmp_path, loopback_policy):
    mock_server.add("/data.bin", mock_server.ranged(DATA, etag='"v1"'))
    reported = []

    run(
        download(
            mock_server.url("/data.bin"),
            tmp_path,
            policy=loopback_policy,
            settings=SPLIT,
            on_partial=reported.append,
        )
    )

    first = reported[0]
    assert first.segments == tuple(plan_segments(len(DATA), 4, 100_000))
    assert first.part_path.name == "data.bin.sdmpart"


@pytest.mark.parametrize(
    ("why", "route_kwargs", "size"),
    [
        ("file too small", {"etag": '"v1"'}, 150_000),
        ("no version tag", {}, 800_000),
        ("ranges not advertised", {"etag": '"v1"', "accept_ranges": False}, 800_000),
    ],
)
def test_one_connection_when_splitting_isnt_safe_or_useful(
    mock_server, fetch, why, route_kwargs, size
):
    data = DATA[:size]
    mock_server.add("/data.bin", mock_server.ranged(data, **route_kwargs))

    result = fetch(mock_server.url("/data.bin"), settings=SPLIT)

    assert requested(mock_server) == [None], why
    assert sha(result.path.read_bytes()) == sha(data)


# ----- servers that can't be trusted with parts: fall back to one connection -----


def test_server_that_ignores_range_falls_back(mock_server, fetch):
    # Advertises ranges but always sends the whole file (OBS-001's server, plus the headers).
    headers = {"Accept-Ranges": "bytes", "ETag": '"v1"'}
    mock_server.add("/data.bin", mock_server.file(DATA, headers=headers))

    result = fetch(mock_server.url("/data.bin"), settings=SPLIT)

    assert sha(result.path.read_bytes()) == sha(DATA)
    assert requested(mock_server)[0] is None


def test_wrong_content_range_on_one_part_falls_back(mock_server, fetch):
    mock_server.add("/data.bin", mock_server.ranged(DATA, etag='"v1"', wrong_range_at=400_000))

    result = fetch(mock_server.url("/data.bin"), settings=SPLIT)

    assert sha(result.path.read_bytes()) == sha(DATA)


def test_file_changing_right_after_the_first_request_gives_one_consistent_version(
    mock_server, fetch
):
    mock_server.add(
        "/data.bin",
        mock_server.ranged(DATA, etag='"v1"', changed_after=1, new_data=NEW, new_etag='"v2"'),
    )

    result = fetch(mock_server.url("/data.bin"), settings=SPLIT)

    # The extra parts' If-Range "v1" no longer matches, so they get the new file whole (200):
    # SDM falls back and the first connection finishes the version it started.
    assert sha(result.path.read_bytes()) == sha(DATA)


# ----- dropped connections -----


def test_a_dropped_part_retries_only_its_remainder(mock_server, fetch):
    log = []
    mock_server.add(
        "/data.bin", mock_server.ranged(DATA, etag='"v1"', cut_once={400_000: 50_000}, log=log)
    )

    result = fetch(mock_server.url("/data.bin"), settings=SPLIT)

    assert sha(result.path.read_bytes()) == sha(DATA)
    assert "bytes=450000-599999" in requested(mock_server)


def test_two_parts_dropped_at_once(mock_server, fetch):
    mock_server.add(
        "/data.bin",
        mock_server.ranged(DATA, etag='"v1"', cut_once={200_000: 10_000, 600_000: 70_000}),
    )

    result = fetch(mock_server.url("/data.bin"), settings=SPLIT)

    assert sha(result.path.read_bytes()) == sha(DATA)
    ranges = requested(mock_server)
    assert "bytes=210000-399999" in ranges
    assert "bytes=670000-799999" in ranges


def test_first_connection_dropped_continues_with_a_range(mock_server, fetch):
    mock_server.add("/data.bin", mock_server.ranged(DATA, etag='"v1"', cut_once={0: 50_000}))

    result = fetch(mock_server.url("/data.bin"), settings=SPLIT)

    assert sha(result.path.read_bytes()) == sha(DATA)
    assert "bytes=50000-199999" in requested(mock_server)


# ----- pausing and resuming a split download -----


def partial_file(tmp_path, segments) -> PartialDownload:
    """A partial file as a paused split download leaves it: pre-sized, with some parts done."""
    part = tmp_path / "data.bin.sdmpart"
    content = bytearray(len(DATA))
    for segment in segments:
        content[segment.start : segment.next_byte] = DATA[segment.start : segment.next_byte]
    part.write_bytes(bytes(content))
    return PartialDownload(part, "data.bin", len(DATA), '"v1"', None, True, segments=segments)


def test_resume_asks_only_for_the_missing_ranges(mock_server, tmp_path, loopback_policy):
    segments = (
        Segment(0, 199_999, 200_000),  # done
        Segment(200_000, 399_999, 50_000),
        Segment(400_000, 599_999, 0),
        Segment(600_000, 799_999, 199_000),
    )
    mock_server.add("/data.bin", mock_server.ranged(DATA, etag='"v1"'))

    result = run(
        download(
            mock_server.url("/data.bin"),
            tmp_path,
            policy=loopback_policy,
            settings=SPLIT,
            resume_from=partial_file(tmp_path, segments),
        )
    )

    assert sha(result.path.read_bytes()) == sha(DATA)
    assert sorted(requested(mock_server)) == [
        "bytes=250000-399999",
        "bytes=400000-599999",
        "bytes=799000-799999",
    ]


def test_resume_when_the_file_changed_starts_over(mock_server, tmp_path, loopback_policy):
    segments = tuple(
        dataclasses.replace(s, received=50_000) for s in plan_segments(800_000, 4, 100_000)
    )
    mock_server.add("/data.bin", mock_server.ranged(NEW, etag='"v2"'))

    result = run(
        download(
            mock_server.url("/data.bin"),
            tmp_path,
            policy=loopback_policy,
            settings=SPLIT,
            resume_from=partial_file(tmp_path, segments),
        )
    )

    assert sha(result.path.read_bytes()) == sha(NEW)  # never a mix of the two versions


def test_pause_and_resume_a_split_download(mock_server, tmp_path, loopback_policy):
    mock_server.add("/data.bin", mock_server.ranged(DATA, etag='"v1"', rate=200_000))
    url = mock_server.url("/data.bin")

    async def pause_midway() -> PartialDownload:
        reported = []
        halfway = asyncio.Event()

        def on_progress(received, total):
            if received >= 300_000:
                halfway.set()

        task = asyncio.create_task(
            download(
                url,
                tmp_path,
                policy=loopback_policy,
                settings=SPLIT,
                on_progress=on_progress,
                on_partial=reported.append,
                keep_partial=True,
            )
        )
        await asyncio.wait_for(halfway.wait(), 10)
        task.cancel()  # what Pause does
        with pytest.raises(asyncio.CancelledError):
            await task
        return reported[-1]

    partial = run(pause_midway())
    assert partial.segments is not None and len(partial.segments) == 4
    assert partial.part_path.stat().st_size == len(DATA)  # pre-sized
    done_so_far = sum(s.received for s in partial.segments)
    assert 300_000 <= done_so_far < len(DATA)

    result = run(
        download(url, tmp_path, policy=loopback_policy, settings=SPLIT, resume_from=partial)
    )

    assert sha(result.path.read_bytes()) == sha(DATA)


def test_damaged_parts_map_is_ignored(mock_server, tmp_path, loopback_policy):
    gap = (Segment(0, 199_999, 200_000), Segment(300_000, 799_999, 0))  # 200000-299999 missing
    mock_server.add("/data.bin", mock_server.ranged(DATA, etag='"v1"'))
    damaged = partial_file(tmp_path, gap)

    result = run(
        download(
            mock_server.url("/data.bin"),
            tmp_path,
            policy=loopback_policy,
            settings=SPLIT,
            resume_from=damaged,
        )
    )

    assert requested(mock_server)[0] is None  # a fresh start, not a resume
    assert sha(result.path.read_bytes()) == sha(DATA)


# ----- the point of it all: speed against per-connection limits -----


def test_split_download_beats_a_per_connection_speed_limit(mock_server, fetch):
    data = DATA[:400_000]
    mock_server.add("/slow.bin", mock_server.ranged(data, etag='"v1"', rate=100_000))
    one = dataclasses.replace(SPLIT, max_connections=1)

    start = time.perf_counter()
    single = fetch(mock_server.url("/slow.bin"), settings=one)
    single_time = time.perf_counter() - start
    single.path.unlink()
    start = time.perf_counter()
    split = fetch(mock_server.url("/slow.bin"), settings=SPLIT)
    split_time = time.perf_counter() - start

    assert sha(split.path.read_bytes()) == sha(data)
    print(f"one connection {single_time:.2f} s, four connections {split_time:.2f} s")
    # Ideal is 4x; ask for 2x so a busy machine (a full test run) does not make it flaky.
    assert split_time < single_time / 2, (single_time, split_time)


@pytest.mark.skipif(sys.platform != "win32", reason="sparse files are an NTFS feature")
def test_partial_files_are_marked_sparse_on_ntfs(tmp_path):
    path = tmp_path / "x.sdmpart"
    with open(path, "wb") as file:
        assert make_sparse(file)
    assert os.stat(path).st_file_attributes & 0x200  # FILE_ATTRIBUTE_SPARSE_FILE
