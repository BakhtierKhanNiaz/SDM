"""Resuming downloads (M4): continue only when it's provably the same file, otherwise restart.

Every test ends by checking the saved file byte for byte: two versions of a file must never be
stitched together.
"""

import asyncio
import hashlib
import os

import pytest

from sdm.core.downloads import PartialDownload
from sdm.core.errors import DownloadError
from sdm.engine.http_download import download
from sdm.engine.models import DownloadSettings

DATA = os.urandom(300_000)
NEW = os.urandom(300_000)  # the "same" file after it changed on the server
SLOW = DownloadSettings(connect_timeout=5.0, read_timeout=10.0, backoff_base=0.0)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def ranges_requested(mock_server) -> list:
    return [headers.get("Range") for headers in mock_server.requests]


# ----- continuing after a cut connection (retries inside one download) -----


def test_cut_download_continues_where_it_stopped(mock_server, fetch):
    log = []
    mock_server.add(
        "/f",
        mock_server.ranged(DATA, etag='"v1"', cut_at=100_000, log=log),
        mock_server.ranged(DATA, etag='"v1"', log=log),
    )

    result = fetch(mock_server.url("/f"))

    assert sha(result.path.read_bytes()) == sha(DATA)
    assert log == [(None, 200, 100_000), ("bytes=100000-", 206, 200_000)]
    assert mock_server.requests[1]["If-Range"] == '"v1"'


def test_retries_only_ask_for_the_missing_bytes(mock_server, fetch):
    # OBS-006 gap: M2 re-downloaded from byte 0 every time.
    log = []
    cut = mock_server.ranged(DATA, etag='"v1"', cut_at=100_000, log=log)
    mock_server.add("/f", cut, cut, cut)

    result = fetch(mock_server.url("/f"))

    assert sha(result.path.read_bytes()) == sha(DATA)
    assert sum(sent for _, _, sent in log) == len(DATA)  # not one byte twice


def test_without_version_tags_the_last_64_bytes_are_checked(mock_server, fetch):
    log = []
    mock_server.add(
        "/f",
        mock_server.ranged(DATA, cut_at=100_000, log=log),
        mock_server.ranged(DATA, log=log),
    )

    result = fetch(mock_server.url("/f"))

    assert sha(result.path.read_bytes()) == sha(DATA)
    assert log[1][0] == "bytes=99936-"  # 64 bytes before the end of what arrived
    assert "If-Range" not in mock_server.requests[1]


def test_last_modified_is_used_when_there_is_no_strong_etag(mock_server, fetch):
    date = "Wed, 21 Oct 2026 07:28:00 GMT"
    mock_server.add(
        "/f",
        mock_server.ranged(DATA, etag='W/"weak"', last_modified=date, cut_at=100_000),
        mock_server.ranged(DATA, etag='W/"weak"', last_modified=date),
    )

    result = fetch(mock_server.url("/f"))

    assert sha(result.path.read_bytes()) == sha(DATA)
    assert mock_server.requests[1]["If-Range"] == date  # weak ETags aren't allowed in If-Range


# ----- replies that must not be trusted -----


def test_server_that_ignores_range_restarts_cleanly(mock_server, fetch):
    mock_server.add(
        "/f", mock_server.ranged(DATA, etag='"v1"', cut_at=100_000), mock_server.file(DATA)
    )

    result = fetch(mock_server.url("/f"))

    assert ranges_requested(mock_server) == [None, "bytes=100000-"]  # asked, got 200
    assert sha(result.path.read_bytes()) == sha(DATA)


def test_wrong_content_range_restarts(mock_server, fetch):
    mock_server.add(
        "/f",
        mock_server.ranged(DATA, etag='"v1"', cut_at=100_000),
        mock_server.ranged(DATA, etag='"v1"', content_range="bytes 0-299999/300000"),
        mock_server.ranged(DATA, etag='"v1"'),
    )

    result = fetch(mock_server.url("/f"))

    assert ranges_requested(mock_server) == [None, "bytes=100000-", None]
    assert sha(result.path.read_bytes()) == sha(DATA)


def test_file_changed_on_the_server_is_downloaded_whole(mock_server, fetch):
    mock_server.add(
        "/f",
        mock_server.ranged(DATA, etag='"v1"', cut_at=100_000),
        mock_server.ranged(NEW, etag='"v2"'),  # If-Range "v1" doesn't match: whole file
    )

    result = fetch(mock_server.url("/f"))

    assert sha(result.path.read_bytes()) == sha(NEW)


def test_silent_change_is_caught_by_the_64_byte_check(mock_server, fetch):
    # No version tags, same size, different content: only the overlap check can notice.
    mock_server.add(
        "/f",
        mock_server.ranged(DATA, cut_at=100_000),
        mock_server.ranged(NEW),
        mock_server.ranged(NEW),
    )

    result = fetch(mock_server.url("/f"))

    assert ranges_requested(mock_server) == [None, "bytes=99936-", None]
    assert sha(result.path.read_bytes()) == sha(NEW)


def test_changed_size_restarts(mock_server, fetch):
    bigger = DATA + b"!" * 1000
    mock_server.add(
        "/f",
        mock_server.ranged(DATA, etag='"v1"', cut_at=100_000),
        mock_server.ranged(bigger, etag='"v1"'),  # same tag, but Content-Range total differs
        mock_server.ranged(bigger, etag='"v1"'),
    )

    result = fetch(mock_server.url("/f"))

    assert sha(result.path.read_bytes()) == sha(bigger)


# ----- resuming in a later download() call (pause, quit, crash) -----


def test_pause_and_resume_in_a_later_call(mock_server, tmp_path, loopback_policy):
    log = []
    mock_server.add(
        "/f",
        mock_server.ranged(DATA, etag='"v1"', stall_at=(100_000, 5), log=log),
        mock_server.ranged(DATA, etag='"v1"', log=log),
    )
    url = mock_server.url("/f")

    async def first_part() -> PartialDownload:
        saved = []
        arrived = asyncio.Event()

        def on_progress(received, total):
            if received >= 100_000:
                arrived.set()

        task = asyncio.create_task(
            download(url, tmp_path, policy=loopback_policy, settings=SLOW,
                     on_progress=on_progress, on_partial=saved.append, keep_partial=True)
        )  # fmt: skip
        await asyncio.wait_for(arrived.wait(), 5)
        task.cancel()  # what pausing does
        with pytest.raises(asyncio.CancelledError):
            await task
        return saved[-1]

    partial = asyncio.run(first_part())
    assert partial.part_path.read_bytes() == DATA[:100_000]
    assert (partial.etag, partial.total_bytes, partial.resumable) == ('"v1"', len(DATA), True)

    result = asyncio.run(
        download(url, tmp_path, policy=loopback_policy, settings=SLOW, resume_from=partial)
    )

    assert sha(result.path.read_bytes()) == sha(DATA)
    assert log[1] == ("bytes=100000-", 206, 200_000)
    assert [p.name for p in tmp_path.iterdir()] == ["f"]


def test_everything_already_there_finishes_on_416(mock_server, tmp_path, loopback_policy):
    log = []
    mock_server.add("/data.bin", mock_server.ranged(DATA, etag='"v1"', log=log))
    part = tmp_path / "data.bin.sdmpart"
    part.write_bytes(DATA)
    partial = PartialDownload(part, "data.bin", len(DATA), '"v1"', None, True)

    result = asyncio.run(
        download(mock_server.url("/data.bin"), tmp_path, policy=loopback_policy,
                 settings=SLOW, resume_from=partial)
    )  # fmt: skip

    assert log == [("bytes=300000-", 416, 0)]
    assert result.path == tmp_path / "data.bin"
    assert sha(result.path.read_bytes()) == sha(DATA)


def test_missing_partial_file_starts_over(mock_server, tmp_path, loopback_policy):
    mock_server.add("/data.bin", mock_server.ranged(DATA, etag='"v1"'))
    gone = PartialDownload(tmp_path / "data.bin.sdmpart", "data.bin", len(DATA), '"v1"', None, True)

    result = asyncio.run(
        download(mock_server.url("/data.bin"), tmp_path, policy=loopback_policy,
                 settings=SLOW, resume_from=gone)
    )  # fmt: skip

    assert ranges_requested(mock_server) == [None]
    assert sha(result.path.read_bytes()) == sha(DATA)


# ----- keeping or deleting the partial file when a download fails -----


def test_failure_keeps_the_partial_file_when_the_server_can_resume(mock_server, tmp_path,
                                                                   loopback_policy):  # fmt: skip
    cut = mock_server.ranged(DATA, etag='"v1"', cut_at=50_000)
    mock_server.add("/data.bin", cut, cut, cut)

    with pytest.raises(DownloadError, match=r"interrupted after 146\.5 KB of 293\.0 KB"):
        asyncio.run(
            download(mock_server.url("/data.bin"), tmp_path, policy=loopback_policy,
                     settings=SLOW, keep_partial=True)
        )  # fmt: skip

    part = tmp_path / "data.bin.sdmpart"
    assert part.read_bytes() == DATA[:150_000]  # kept for a later retry


def test_failure_deletes_the_partial_file_when_the_server_cant_resume(mock_server, tmp_path,
                                                                      loopback_policy):  # fmt: skip
    mock_server.add("/data.bin", mock_server.truncated(DATA))  # no Accept-Ranges, ignores Range

    with pytest.raises(DownloadError):
        asyncio.run(
            download(mock_server.url("/data.bin"), tmp_path, policy=loopback_policy,
                     settings=SLOW, keep_partial=True)
        )  # fmt: skip

    assert list(tmp_path.iterdir()) == []


def test_sdm_get_style_calls_always_clean_up(mock_server, fetch, tmp_path):
    cut = mock_server.ranged(DATA, etag='"v1"', cut_at=50_000)
    mock_server.add("/data.bin", cut, cut, cut)

    with pytest.raises(DownloadError):
        fetch(mock_server.url("/data.bin"))  # keep_partial defaults to False

    assert list(tmp_path.iterdir()) == []


# ----- partial-file paths come from the database: never trust them blindly -----


@pytest.mark.parametrize("where", ["outside the folder", "not a .sdmpart file"])
def test_partial_path_outside_the_download_folder_is_ignored(mock_server, tmp_path,
                                                             loopback_policy, where):  # fmt: skip
    downloads = tmp_path / "downloads"
    downloads.mkdir()
    if where == "outside the folder":
        victim = tmp_path / "important.sdmpart"
    else:
        victim = downloads / "important.txt"
    victim.write_bytes(b"precious data, not SDM's")
    mock_server.add("/data.bin", mock_server.ranged(DATA, etag='"v1"'))
    tampered = PartialDownload(victim, "data.bin", len(DATA), '"v1"', None, True)

    result = asyncio.run(
        download(mock_server.url("/data.bin"), downloads, policy=loopback_policy,
                 settings=SLOW, resume_from=tampered)
    )  # fmt: skip

    assert victim.read_bytes() == b"precious data, not SDM's"
    assert ranges_requested(mock_server) == [None]
    assert sha(result.path.read_bytes()) == sha(DATA)
