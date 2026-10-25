"""The Convert window with the real ffmpeg (M12a), when one is installed; skipped otherwise.

The media are synthetic: ffmpeg's own test pattern and sine tone, made in a temporary folder.
ffprobe (installed with ffmpeg) checks what came out.
"""

import json
import subprocess

import pytest

from sdm.media.ffmpeg import find_ffmpeg
from sdm.ui.convert_dialog import ConvertDialog

FFMPEG = find_ffmpeg()
pytestmark = pytest.mark.skipif(FFMPEG is None, reason="ffmpeg isn't installed")


def run(*args):
    subprocess.run([str(FFMPEG), "-hide_banner", "-loglevel", "error", "-nostdin", *args],  # noqa: S603
                   check=True, capture_output=True)  # fmt: skip


def probe(path):
    ffprobe = FFMPEG.with_name("ffprobe.exe")
    out = subprocess.run(  # noqa: S603
        [str(ffprobe), "-v", "error", "-show_entries",
         "format=duration:stream=codec_type,codec_name,width,height", "-of", "json", str(path)],
        check=True, capture_output=True, text=True,
    ).stdout  # fmt: skip
    info = json.loads(out)
    streams = {s["codec_type"]: s for s in info["streams"]}
    return float(info["format"]["duration"]), streams


@pytest.fixture(scope="module")
def media(tmp_path_factory):
    folder = tmp_path_factory.mktemp("media")
    run(
        "-f",
        "lavfi",
        "-i",
        "testsrc=duration=6:size=640x360:rate=25",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=440:duration=6",
        "-c:v",
        "libvpx-vp9",
        "-b:v",
        "300k",
        "-c:a",
        "libopus",
        str(folder / "clip test.webm"),
    )
    run("-f", "lavfi", "-i", "testsrc=duration=3:size=320x240:rate=25",
        "-c:v", "libx264", str(folder / "silent.mkv"))  # fmt: skip
    return folder


def convert(qtbot, source, fmt, *, timeout=120000):
    dialog = ConvertDialog(ffmpeg=[str(FFMPEG)], source=source)
    qtbot.addWidget(dialog)
    dialog.format_box.setCurrentIndex(dialog.format_box.findData(fmt))
    values = set()
    dialog.bar.valueChanged.connect(values.add)
    assert dialog.start()
    qtbot.waitUntil(lambda: not dialog.running, timeout=timeout)
    return dialog, values


@pytest.mark.parametrize(
    ("fmt", "codecs"),
    [
        ("mp3", {"audio": "mp3"}),
        ("m4a", {"audio": "aac"}),
        ("mp4", {"video": "h264", "audio": "aac"}),
    ],  # fmt: skip
)
def test_real_conversions(qtbot, media, fmt, codecs):
    dialog, _ = convert(qtbot, media / "clip test.webm", fmt)
    assert dialog.result is not None, dialog.status_label.text()
    assert dialog.result.name.startswith("clip test")
    duration, streams = probe(dialog.result)
    assert abs(duration - 6.0) < 0.2
    assert {kind: s["codec_name"] for kind, s in streams.items()} == codecs
    if fmt == "mp4":
        assert (streams["video"]["width"], streams["video"]["height"]) == (640, 360)


def test_a_video_without_sound_is_explained(qtbot, media):
    dialog, _ = convert(qtbot, media / "silent.mkv", "mp3")
    assert dialog.result is None
    assert dialog.status_label.text().endswith(
        "This file has no sound, so it can't become an audio file."
    )
    assert not (media / "silent.mp3").exists()


def test_the_bar_moves_during_a_longer_conversion(qtbot, tmp_path):
    source = tmp_path / "long.mkv"
    run("-f", "lavfi", "-i", "testsrc2=duration=30:size=1280x720:rate=30",
        "-f", "lavfi", "-i", "sine=duration=30", "-c:v", "libx264", "-preset", "ultrafast",
        "-c:a", "aac", str(source))  # fmt: skip
    dialog, values = convert(qtbot, source, "mp4")
    assert dialog.result is not None
    assert any(0 < value < 100 for value in values), sorted(values)
