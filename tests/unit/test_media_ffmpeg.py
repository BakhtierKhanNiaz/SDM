"""The converter's pure logic (M12a, ADR-0020): formats, command line, names, progress."""

from pathlib import Path

from sdm.media.ffmpeg import (
    FORMATS,
    ConversionProgress,
    converted_path,
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


def test_the_last_log_line_explains_a_failure():
    progress = ConversionProgress()
    progress.log_line("Input #0, matroska,webm, from 'x':")
    progress.log_line("Stream map '0:a:0' matches no streams.")
    progress.log_line("")
    assert progress.last_error == "Stream map '0:a:0' matches no streams."


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
