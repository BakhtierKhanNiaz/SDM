"""The converter's pure logic (M12a, ADR-0020): formats, command line, names, progress."""

from pathlib import Path

from sdm.media.ffmpeg import (
    FORMATS,
    ConversionProgress,
    converted_path,
    explain_failure,
    ffmpeg_arguments,
    find_ffmpeg,
    parse_duration,
)


def test_three_formats_each_with_its_own_extension():
    assert list(FORMATS) == ["mp3", "m4a", "mp4"]
    assert [f.extension for f in FORMATS.values()] == [".mp3", ".m4a", ".mp4"]
    for key in ("mp3", "m4a"):
        assert "-vn" in FORMATS[key].arguments  # audio only


def test_the_command_line_is_fixed_and_never_overwrites(tmp_path):
    source, target = tmp_path / "-i evil.webm", tmp_path / "x.mp3"
    args = ffmpeg_arguments(source, target, FORMATS["mp3"])
    assert args[:3] == ["-hide_banner", "-nostdin", "-n"]
    # a name that looks like an option or a protocol stays a file name
    assert args[args.index("-i") + 1] == f"file:{source.resolve()}"
    assert args[-1] == f"file:{target.resolve()}"
    assert args[args.index("-progress") + 1] == "pipe:1"


def test_the_result_is_a_new_file_next_to_the_source(tmp_path):
    video = tmp_path / "talk.webm"
    video.write_bytes(b"v")
    assert converted_path(video, FORMATS["mp3"]) == tmp_path / "talk.mp3"
    (tmp_path / "talk.mp3").write_bytes(b"old")
    assert converted_path(video, FORMATS["mp3"]) == tmp_path / "talk (1).mp3"
    # converting an MP4 to MP4 never targets the source itself
    mp4 = tmp_path / "clip.mp4"
    mp4.write_bytes(b"v")
    assert converted_path(mp4, FORMATS["mp4"]) == tmp_path / "clip (1).mp4"


def test_the_duration_line():
    line = "  Duration: 01:02:03.50, start: 0.000000, bitrate: 128 kb/s"
    assert parse_duration(line) == 3723.5
    assert parse_duration("  Duration: N/A, bitrate: N/A") is None
    assert parse_duration("Stream #0:0: Audio: opus") is None


def test_progress_from_ffmpegs_output():
    progress = ConversionProgress()
    assert progress.percent is None  # length not known yet
    progress.log_line("  Duration: 00:00:10.00, start: 0.000000")
    progress.progress_line("out_time_us=2500000")
    progress.progress_line("progress=continue")
    assert progress.percent == 25
    progress.progress_line("out_time_us=N/A")  # ffmpeg prints N/A at the very start
    assert progress.percent == 25
    progress.progress_line("progress=end")
    assert progress.percent == 100 and progress.finished


def test_the_last_log_line_explains_an_unknown_failure():
    progress = ConversionProgress()
    progress.log_line("Input #0, matroska,webm, from 'x':")
    progress.log_line("x.webm: Conversion failed!")
    progress.log_line("")
    assert progress.failure_reason == "x.webm: Conversion failed!"
    assert ConversionProgress().failure_reason == ""


# ffmpeg 9.0.2's own words (seen 2026-10-25) when the file lacks the stream SDM maps.
NO_STREAM = [
    "Stream map '' matches no streams.",
    "To ignore this, add a trailing '?' to the map.",
    "Failed to set value '{map}' for option 'map': Invalid argument",
    "Error opening output files: Invalid argument",
]


def test_known_failures_are_explained_in_plain_words():
    no_sound = explain_failure([line.format(map="0:a:0") for line in NO_STREAM])
    assert no_sound == "This file has no sound, so it can't become an audio file."
    no_video = explain_failure([line.format(map="0:v:0") for line in NO_STREAM])
    assert no_video.startswith("This file has no video")
    # ffmpeg 9.0.2 on a text file named like media (seen 2026-10-25)
    not_media = explain_failure([
        "file:C:\\x\\notes.txt: Invalid data found when processing input",
        "Error opening input files: Invalid data found when processing input",
    ])  # fmt: skip
    assert not_media == "This doesn't look like a video or audio file that ffmpeg can read."
    encoder = explain_failure(["Unknown encoder 'libx264'"])
    assert "libx264" in encoder and "winget install Gyan.FFmpeg" in encoder


def test_the_log_keeps_only_the_last_lines():
    progress = ConversionProgress()
    for number in range(100):
        progress.log_line(f"line {number}")
    assert len(progress.log) == ConversionProgress.MAX_LOG_LINES
    assert progress.log[-1] == "line 99"


def _exe(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"MZ")
    return path


def test_finding_ffmpeg(tmp_path):
    empty = {"PATH": str(tmp_path / "nothing"), "LOCALAPPDATA": str(tmp_path / "local")}
    assert find_ffmpeg(environ=empty) is None
    # where WinGet keeps the package, then its Links folder (which wins)
    package = _exe(
        tmp_path / "local/Microsoft/WinGet/Packages/Gyan.FFmpeg_x/ffmpeg-9.0.2/bin/ffmpeg.exe"
    )
    assert find_ffmpeg(environ=empty) == package
    link = _exe(tmp_path / "local/Microsoft/WinGet/Links/ffmpeg.exe")
    assert find_ffmpeg(environ=empty) == link
    # PATH wins over WinGet's folders
    on_path = _exe(tmp_path / "bin/ffmpeg.exe")
    assert find_ffmpeg(environ={**empty, "PATH": str(on_path.parent)}) == on_path
    # a path set in Settings wins over everything, and a wrong one finds nothing
    chosen = _exe(tmp_path / "tools/ffmpeg.exe")
    assert find_ffmpeg(str(chosen), environ=empty) == chosen
    assert find_ffmpeg(str(tmp_path / "missing.exe"), environ=empty) is None
