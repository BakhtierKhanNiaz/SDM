"""Single-connection downloads against the local mock server."""

import asyncio
import errno
import hashlib
import os
import shutil
import socket
from types import SimpleNamespace

import pytest

from sdm.core.errors import DownloadError
from sdm.engine import http_download
from sdm.engine.http_download import download
from sdm.engine.models import DownloadSettings

DATA = os.urandom(300_000)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def names(folder) -> list[str]:
    return sorted(p.name for p in folder.iterdir())


# ----- success paths -----


def test_downloads_the_file_byte_for_byte(mock_server, fetch, tmp_path):
    mock_server.add("/files/data.bin", mock_server.file(DATA))
    progress = []

    result = fetch(mock_server.url("/files/data.bin"), on_progress=lambda *p: progress.append(p))

    assert result.path == tmp_path / "data.bin"
    assert sha256(result.path.read_bytes()) == sha256(DATA)
    assert result.size == len(DATA)
    assert result.verified_complete
    assert progress[0] == (0, len(DATA))
    assert progress[-1] == (len(DATA), len(DATA))
    assert names(tmp_path) == ["data.bin"]  # no .sdmpart left behind


def test_sends_identity_encoding_and_user_agent(mock_server, fetch):
    mock_server.add("/f", mock_server.file(DATA))
    fetch(mock_server.url("/f"))
    headers = mock_server.requests[0]
    assert headers["Accept-Encoding"] == "identity"
    assert headers["User-Agent"].startswith("SDM/")


def test_unknown_size(mock_server, fetch):
    mock_server.add("/stream", mock_server.file(DATA, content_length=False))
    progress = []

    result = fetch(mock_server.url("/stream"), on_progress=lambda *p: progress.append(p))

    assert result.path.read_bytes() == DATA
    assert result.path.name == "stream"
    assert all(total is None for _, total in progress)
    # Only the connection closing marked the end, so a cut would have looked the same
    # (IDM warns about this too: OBS-005).
    assert not result.verified_complete


def test_chunked_download_counts_as_complete(mock_server, fetch):
    mock_server.add("/chunked", mock_server.chunked(DATA))

    result = fetch(mock_server.url("/chunked"))

    assert result.path.read_bytes() == DATA
    assert result.verified_complete  # the final zero-length chunk marks the end


def test_chunked_download_cut_before_the_last_chunk_fails(mock_server, fetch, tmp_path):
    mock_server.add("/chunked-cut", mock_server.chunked(DATA, cut=True))
    with pytest.raises(DownloadError, match="interrupted"):
        fetch(mock_server.url("/chunked-cut"))
    assert mock_server.hits["/chunked-cut"] == 3
    assert names(tmp_path) == []


def test_name_from_content_disposition(mock_server, fetch):
    header = {"Content-Disposition": 'attachment; filename="Report 2026.pdf"'}
    mock_server.add("/dl", mock_server.file(DATA, headers=header))
    assert fetch(mock_server.url("/dl?id=7")).path.name == "Report 2026.pdf"


def test_follows_redirects_and_names_the_file_after_the_final_url(mock_server, fetch):
    mock_server.add("/start", mock_server.redirect("/middle"))
    mock_server.add("/middle", mock_server.redirect("files/archive.zip", code=301))  # relative
    mock_server.add("/files/archive.zip", mock_server.file(DATA))

    result = fetch(mock_server.url("/start"))

    assert result.path.name == "archive.zip"
    assert result.final_url.endswith("/files/archive.zip")
    assert result.path.read_bytes() == DATA


# ----- naming and collisions -----


def test_existing_files_are_never_overwritten(mock_server, fetch, tmp_path):
    (tmp_path / "data.bin").write_bytes(b"old")
    (tmp_path / "data (1).bin").write_bytes(b"older")
    mock_server.add("/data.bin", mock_server.file(DATA))

    result = fetch(mock_server.url("/data.bin"))

    assert result.path.name == "data (2).bin"
    assert (tmp_path / "data.bin").read_bytes() == b"old"
    assert (tmp_path / "data (1).bin").read_bytes() == b"older"


def test_another_downloads_partial_file_is_left_alone(mock_server, fetch, tmp_path):
    (tmp_path / "data.bin.sdmpart").write_bytes(b"someone else's partial download")
    mock_server.add("/data.bin", mock_server.file(DATA))

    result = fetch(mock_server.url("/data.bin"))

    assert result.path.name == "data.bin"
    assert (tmp_path / "data.bin.sdmpart").read_bytes() == b"someone else's partial download"


# ----- server errors and retries -----


@pytest.mark.parametrize(("code", "label"), [(404, "404 Not Found"), (410, "410 Gone")])
def test_missing_file_fails_without_retrying(mock_server, fetch, tmp_path, code, label):
    mock_server.add("/missing", mock_server.status(code))
    with pytest.raises(DownloadError, match=rf"not found on the server \({label}\)"):
        fetch(mock_server.url("/missing"))
    assert mock_server.hits["/missing"] == 1
    assert names(tmp_path) == []


def test_other_client_errors_are_refusals(mock_server, fetch):
    mock_server.add("/private", mock_server.status(403))
    with pytest.raises(DownloadError, match=r"refused the download \(403 Forbidden\)"):
        fetch(mock_server.url("/private"))
    assert mock_server.hits["/private"] == 1


def test_temporary_server_error_is_retried(mock_server, fetch):
    mock_server.add("/flaky", mock_server.status(503), mock_server.file(DATA))
    assert fetch(mock_server.url("/flaky")).path.read_bytes() == DATA
    assert mock_server.hits["/flaky"] == 2


def test_gives_up_after_max_attempts(mock_server, fetch, tmp_path):
    mock_server.add("/down", mock_server.status(500))
    with pytest.raises(DownloadError, match=r"temporary problem \(500"):
        fetch(mock_server.url("/down"))
    assert mock_server.hits["/down"] == 3
    assert names(tmp_path) == []


def test_429_with_retry_after_is_retried(mock_server, fetch):
    busy = mock_server.status(429, headers={"Retry-After": "0"})
    mock_server.add("/busy", busy, mock_server.file(DATA))
    assert fetch(mock_server.url("/busy")).path.read_bytes() == DATA
    assert mock_server.hits["/busy"] == 2


def test_redirect_loop_is_stopped(mock_server, fetch):
    mock_server.add("/loop", mock_server.redirect("/loop"))
    with pytest.raises(DownloadError, match="Too many redirects"):
        fetch(mock_server.url("/loop"))
    assert mock_server.hits["/loop"] == 11  # the first request plus 10 redirects


def test_redirect_without_location(mock_server, fetch):
    mock_server.add("/broken", mock_server.status(302))
    with pytest.raises(DownloadError, match="redirect without a destination"):
        fetch(mock_server.url("/broken"))


# ----- broken connections -----


def test_cut_connection_is_retried(mock_server, fetch):
    mock_server.add("/cut-once", mock_server.truncated(DATA), mock_server.file(DATA))
    assert fetch(mock_server.url("/cut-once")).path.read_bytes() == DATA


def test_always_cut_connection_fails_and_cleans_up(mock_server, fetch, tmp_path):
    mock_server.add("/cut", mock_server.truncated(DATA))
    with pytest.raises(DownloadError, match="interrupted|closed early"):
        fetch(mock_server.url("/cut"))
    assert mock_server.hits["/cut"] == 3
    assert names(tmp_path) == []


def test_silent_server_times_out(mock_server, fetch, tmp_path):
    mock_server.add("/stall", mock_server.stall(b"x" * 1024, declared_length=10_000, seconds=3))
    settings = DownloadSettings(read_timeout=0.3, max_attempts=1)
    with pytest.raises(DownloadError, match="took too long"):
        fetch(mock_server.url("/stall"), settings=settings)
    assert names(tmp_path) == []


def test_connection_refused(fetch):
    with socket.socket() as sock:  # find a port with nothing listening on it
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    settings = DownloadSettings(connect_timeout=10, max_attempts=1)
    with pytest.raises(DownloadError, match="Could not connect"):
        fetch(f"http://127.0.0.1:{port}/file", settings=settings)


# ----- cancellation -----


def test_cancelling_deletes_the_partial_file(mock_server, tmp_path, loopback_policy):
    mock_server.add("/slow", mock_server.stall(b"x" * 4096, declared_length=1_000_000, seconds=5))

    async def scenario():
        started = asyncio.Event()

        def on_progress(received, total):
            if received:
                started.set()

        task = asyncio.create_task(
            download(
                mock_server.url("/slow"),
                tmp_path,
                policy=loopback_policy,
                settings=DownloadSettings(read_timeout=10),
                on_progress=on_progress,
            )
        )
        await asyncio.wait_for(started.wait(), timeout=5)
        assert names(tmp_path) == ["slow.sdmpart"]
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(scenario())
    assert names(tmp_path) == []


# ----- local disk problems -----


def test_missing_destination_folder(mock_server, fetch, tmp_path):
    mock_server.add("/f", mock_server.file(DATA))
    with pytest.raises(DownloadError, match="does not exist"):
        fetch(mock_server.url("/f"), dest=tmp_path / "missing")
    assert mock_server.hits["/f"] == 0


def test_not_enough_disk_space_is_detected_before_writing(
    mock_server, fetch, tmp_path, monkeypatch
):
    monkeypatch.setattr(shutil, "disk_usage", lambda path: SimpleNamespace(free=10))
    mock_server.add("/f", mock_server.file(DATA))
    with pytest.raises(DownloadError, match="Not enough disk space"):
        fetch(mock_server.url("/f"))
    assert names(tmp_path) == []


def test_disk_filling_up_while_writing(mock_server, fetch, tmp_path, monkeypatch):
    real_open = open

    class FullDisk:
        def __init__(self, path, mode):
            self._file = real_open(path, mode)

        def write(self, data):
            raise OSError(errno.ENOSPC, "No space left on device")

        def __enter__(self):
            return self

        def __exit__(self, *exc_info):
            self._file.close()

    monkeypatch.setattr(http_download, "open", FullDisk, raising=False)
    mock_server.add("/f", mock_server.file(DATA))
    with pytest.raises(DownloadError, match="Not enough disk space"):
        fetch(mock_server.url("/f"))
    assert names(tmp_path) == []


@pytest.mark.parametrize(
    "blocked_error",
    [
        PermissionError(errno.EACCES, "Permission denied"),
        # What Controlled Folder Access actually raises (observed on this machine in M2).
        FileNotFoundError(errno.ENOENT, "No such file or directory"),
    ],
)
def test_blocked_writes_are_explained(mock_server, fetch, monkeypatch, blocked_error):
    def refuse(path, mode):
        raise blocked_error

    monkeypatch.setattr(http_download, "open", refuse, raising=False)
    mock_server.add("/f", mock_server.file(DATA))
    with pytest.raises(DownloadError, match="Controlled Folder Access"):
        fetch(mock_server.url("/f"))


# ----- M3: early file info and how much arrived -----


def test_file_info_is_reported_before_any_data(mock_server, fetch):
    header = {"Content-Disposition": 'attachment; filename="Report 2026.pdf"'}
    mock_server.add("/dl", mock_server.file(DATA, headers=header))
    calls = []

    fetch(
        mock_server.url("/dl"),
        on_progress=lambda received, total: calls.append(("progress", received, total)),
        on_file_info=lambda name, total: calls.append(("info", name, total)),
    )

    assert calls[0] == ("info", "Report 2026.pdf", len(DATA))
    assert calls[1] == ("progress", 0, len(DATA))


def test_cut_download_says_how_much_arrived(mock_server, fetch):
    mock_server.add("/cut", mock_server.truncated(DATA))  # sends 150,000 of 300,000 bytes
    with pytest.raises(DownloadError, match=r"interrupted after 146\.5 KB of 293\.0 KB"):
        fetch(mock_server.url("/cut"), settings=DownloadSettings(max_attempts=1))
