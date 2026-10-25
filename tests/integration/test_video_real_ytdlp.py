"""Video pages with the real yt-dlp and ffmpeg (M12b), when both are installed; skipped
otherwise. Everything comes from a test server on this computer (127.0.0.1): synthetic media
made by ffmpeg and an HTML page that embeds one, never a real video site.
"""

import json
import subprocess
import threading
from dataclasses import replace
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from sdm.core.downloads import DownloadState
from sdm.media.ffmpeg import find_ffmpeg
from sdm.media.ytdlp import find_ytdlp

FFMPEG, YTDLP = find_ffmpeg(), find_ytdlp()
pytestmark = pytest.mark.skipif(
    FFMPEG is None or YTDLP is None, reason="yt-dlp and ffmpeg aren't both installed"
)


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args) -> None:
        pass


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    folder = tmp_path_factory.mktemp("site")
    subprocess.run(  # noqa: S603
        [str(FFMPEG), "-hide_banner", "-loglevel", "error", "-nostdin",
         "-f", "lavfi", "-i", "testsrc=duration=5:size=1280x720:rate=25",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=5",
         "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", str(folder / "clip.mp4")],
        check=True, capture_output=True,
    )  # fmt: skip
    (folder / "page.html").write_text(
        "<html><head><title>Local Test Page</title></head><body>"
        '<video controls><source src="clip.mp4" type="video/mp4"></video></body></html>',
        encoding="utf-8",
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(_QuietHandler, directory=str(folder)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


@pytest.fixture
def controller(make_controller, tmp_path):
    controller = make_controller()
    controller.set_preferences(replace(controller.preferences, video_enabled=True))
    folder = tmp_path / "out"
    folder.mkdir()
    return controller, folder


def probe(path: Path) -> dict[str, str]:
    out = subprocess.run(  # noqa: S603
        [str(FFMPEG.with_name("ffprobe.exe")), "-v", "error", "-show_entries",
         "stream=codec_type,codec_name", "-of", "json", str(path)],
        check=True, capture_output=True, text=True,
    ).stdout  # fmt: skip
    return {s["codec_type"]: s["codec_name"] for s in json.loads(out)["streams"]}


def finish(qtbot, controller, record):
    store = controller[0].store
    qtbot.waitUntil(
        lambda: store.get(record.id).state in (DownloadState.COMPLETED, DownloadState.FAILED),
        timeout=120000,
    )
    return store.get(record.id)


@pytest.mark.parametrize(
    ("page", "quality", "codecs"),
    [
        ("page.html", "1080p", {"video": "h264", "audio": "aac"}),
        ("page.html", "mp3", {"audio": "mp3"}),
        ("clip.mp4", "720p", {"video": "h264", "audio": "aac"}),
    ],  # fmt: skip
)
def test_real_yt_dlp_downloads_a_local_page(qtbot, site, controller, page, quality, codecs):
    record = controller[0].add(f"{site}/{page}", controller[1], video=quality)
    done = finish(qtbot, controller, record)
    assert done.state == DownloadState.COMPLETED, done.error
    assert probe(Path(done.path)) == codecs
    assert [p.name for p in controller[1].iterdir()] == [Path(done.path).name]


def test_a_missing_page_is_explained_and_leaves_nothing(qtbot, site, controller):
    record = controller[0].add(f"{site}/missing.html", controller[1], video="720p")
    done = finish(qtbot, controller, record)
    assert done.state == DownloadState.FAILED
    assert done.error == "The page wasn't found (HTTP 404)."
    assert list(controller[1].iterdir()) == []
