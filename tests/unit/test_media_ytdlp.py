"""The video add-on's pure logic (M12b, ADR-0020): qualities, command line, progress, files."""

from pathlib import Path

from sdm.media.ytdlp import (
    PROGRESS_MARK,
    QUALITIES,
    VideoProgress,
    explain_failure,
    final_path,
    find_ytdlp,
    finished_media,
    is_own_work_folder,
    work_folder,
    ytdlp_arguments,
)

URL = "https://video.example.com/watch?v=abc"


def test_the_qualities_offered():
    assert list(QUALITIES) == ["720p", "1080p", "2160p", "mp3", "m4a"]
    assert "res:2160" in QUALITIES["2160p"].arguments
    assert "-x" in QUALITIES["mp3"].arguments and "-x" in QUALITIES["m4a"].arguments
    for key in ("720p", "1080p", "2160p"):
        args = QUALITIES[key].arguments
        assert args[args.index("--merge-output-format") + 1] == "mp4"


def test_the_command_line_is_locked_down(tmp_path):
    ffmpeg = tmp_path / "ffmpeg.exe"
    args = ytdlp_arguments(URL, QUALITIES["1080p"], tmp_path / ".sdm-video-1", ffmpeg=ffmpeg)
    assert args[0] == "--ignore-config"  # first, so no config file can add --exec
    for option in ("--no-playlist", "--no-cookies", "--no-cookies-from-browser", "--no-exec"):
        assert option in args
    assert args[-2:] == ["--", URL]  # the address can't be read as an option
    assert args[args.index("-P") + 1] == str(tmp_path / ".sdm-video-1")
    assert args[args.index("--ffmpeg-location") + 1] == str(ffmpeg)
    assert args[args.index("--progress-template") + 1].startswith(f"download:{PROGRESS_MARK} ")
    assert "--ffmpeg-location" not in ytdlp_arguments(URL, QUALITIES["mp3"], tmp_path)
    # nothing that signs in or reads cookies is ever passed
    for risky in ("--cookies", "--cookies-from-browser", "--username", "--password", "--exec"):
        assert risky not in args


def test_reading_progress_and_parts():
    progress = VideoProgress()
    assert progress.line("[youtube] abc: Downloading webpage") is None
    assert progress.line("[download] Destination: C:\\w\\Clip [abc].f137.mp4") == "part"
    assert progress.part_name == "Clip [abc].f137.mp4" and progress.parts == 1
    assert progress.line(f"{PROGRESS_MARK} 250 1000 NA") == "progress"
    assert (progress.received, progress.total) == (250, 1000)
    assert progress.line(f"{PROGRESS_MARK} 300 NA 2000.5") == "progress"  # an estimate only
    assert progress.total == 2000
    assert progress.line(f"{PROGRESS_MARK} NA NA NA") is None
    assert progress.line("[download] Destination: C:\\w\\Clip [abc].f140.m4a") == "part"
    assert (progress.parts, progress.received, progress.total) == (2, 0, None)
    progress.line('[Merger] Merging formats into "C:\\w\\Clip [abc].mp4"')
    assert progress.stage == "merging"


def test_failures_in_plain_words():
    assert explain_failure(["ERROR: Unsupported URL: https://x"]).startswith("yt-dlp doesn't")
    assert "lower one" in explain_failure(["ERROR: Requested format is not available."])
    assert "DRM" in explain_failure(["ERROR: [x] abc: This video is DRM protected"])
    assert "login" in explain_failure(["ERROR: [y] abc: Sign in to confirm your age."])
    assert "ffmpeg" in explain_failure(["ERROR: ffmpeg is not installed; can't merge"])
    # yt-dlp 2026.10.21's own words for a missing page (seen with SDM's local test server)
    missing = (
        "ERROR: [generic] missing: Unable to download webpage: HTTP Error 404: File not found "
        "(caused by <HTTPError 404: File not found>)"
    )
    assert explain_failure(["WARNING: slow", missing]) == "The page wasn't found (HTTP 404)."
    assert explain_failure(["ERROR: HTTP Error 403: Forbidden"]).startswith("The site refused")
    assert explain_failure(["ERROR: HTTP Error 500: Oops"]).endswith("(HTTP 500).")
    # anything else: the last error, without yt-dlp's prefix and internal cause
    assert (
        explain_failure(
            ["ERROR: [generic] abc: Unable to extract title (caused by <Internal thing>)"]
        )
        == "Unable to extract title"
    )
    assert explain_failure([]) == ""


def test_the_finished_file_is_the_merged_one(tmp_path):
    (tmp_path / "Clip [abc].f137.mp4").write_bytes(b"x" * 900)  # a part left before merging
    (tmp_path / "Clip [abc].mp4.part").write_bytes(b"x" * 999)
    (tmp_path / "Clip [abc].mp4").write_bytes(b"x" * 100)
    (tmp_path / "notes.txt").write_bytes(b"x" * 5000)
    assert finished_media(tmp_path) == tmp_path / "Clip [abc].mp4"
    assert finished_media(tmp_path / "missing") is None


def test_the_final_name_never_overwrites(tmp_path):
    assert final_path(tmp_path, "Clip [abc].mp4") == tmp_path / "Clip [abc].mp4"
    (tmp_path / "Clip [abc].mp4").write_bytes(b"old")
    assert final_path(tmp_path, "Clip [abc].mp4") == tmp_path / "Clip [abc] (1).mp4"
    assert final_path(tmp_path, "con.mp4").name == "_con.mp4"  # sanitized like any name


def test_only_sdms_own_work_folder_counts(tmp_path):
    work = work_folder(tmp_path, 12)
    assert work == tmp_path / ".sdm-video-12"
    assert is_own_work_folder(work, tmp_path)
    assert not is_own_work_folder(tmp_path / ".sdm-video-x", tmp_path)
    assert not is_own_work_folder(tmp_path / "Videos", tmp_path)
    assert not is_own_work_folder(tmp_path / "sub" / ".sdm-video-12", tmp_path)


def _exe(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"MZ")
    return path


def test_finding_ytdlp(tmp_path):
    empty = {"PATH": str(tmp_path / "nothing"), "LOCALAPPDATA": str(tmp_path / "local")}
    assert find_ytdlp(environ=empty) is None
    package = _exe(tmp_path / "local/Microsoft/WinGet/Packages/yt-dlp.yt-dlp_x/yt-dlp.exe")
    assert find_ytdlp(environ=empty) == package
    link = _exe(tmp_path / "local/Microsoft/WinGet/Links/yt-dlp.exe")
    assert find_ytdlp(environ=empty) == link
    chosen = _exe(tmp_path / "tools/yt-dlp.exe")
    assert find_ytdlp(str(chosen), environ=empty) == chosen
    assert find_ytdlp(str(tmp_path / "nope.exe"), environ=empty) is None
