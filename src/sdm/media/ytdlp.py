"""Video pages with yt-dlp (M12b, ADR-0020): where yt-dlp is, the qualities SDM offers, the
exact command line, reading its output, and where the finished file is.

yt-dlp downloads into a private work folder next to the destination (".sdm-video-<id>"), so a
paused download continues from its partial files, Cancel removes everything it made, and the
finished file is moved out under SDM's own no-overwrite naming (ADR-0008).
"""

import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from sdm.core.filenames import numbered_name, sanitize_filename

INSTALL_HINT = "Install it for free with: winget install yt-dlp.yt-dlp"
TERMS_NOTICE = (
    "SDM will use yt-dlp to download from video pages you choose. You are responsible for "
    "following each site's terms of use and copyright. SDM never signs in, never uses your "
    "browser's cookies, and never downloads DRM-protected or paid-only videos."
)
PROGRESS_MARK = "SDMPROGRESS"
WORK_PREFIX = ".sdm-video-"
MEDIA_SUFFIXES = frozenset({".mp4", ".mkv", ".webm", ".mp3", ".m4a", ".opus", ".ogg", ".mov"})


@dataclass(frozen=True)
class VideoQuality:
    key: str
    label: str
    arguments: tuple[str, ...]


def _video(height: int) -> tuple[str, ...]:
    # The best video up to this height plus the best audio, merged into an MP4 by ffmpeg;
    # a site that has only single files gets the best single file up to that height.
    return ("-f", "bv*+ba/b", "-S", f"res:{height}", "--merge-output-format", "mp4")


QUALITIES: dict[str, VideoQuality] = {
    q.key: q
    for q in (
        VideoQuality("720p", "Video 720p (MP4)", _video(720)),
        VideoQuality("1080p", "Video 1080p (MP4)", _video(1080)),
        VideoQuality("2160p", "Video 4K (MP4)", _video(2160)),
        VideoQuality(
            "mp3",
            "Audio only (MP3)",
            ("-f", "ba/b", "-x", "--audio-format", "mp3", "--audio-quality", "0"),
        ),  # fmt: skip
        VideoQuality("m4a", "Audio only (M4A)", ("-f", "ba/b", "-x", "--audio-format", "m4a")),
    )
}


def find_ytdlp(configured: str = "", *, environ: dict[str, str] | None = None) -> Path | None:
    """yt-dlp.exe: the path set in Settings, else PATH, else where WinGet puts it."""
    if configured:
        path = Path(configured)
        return path if path.is_file() else None
    environ = os.environ if environ is None else environ
    found = shutil.which("yt-dlp", path=environ.get("PATH"))
    if found:
        return Path(found)
    local = environ.get("LOCALAPPDATA")
    if not local:
        return None
    winget = Path(local) / "Microsoft" / "WinGet"
    link = winget / "Links" / "yt-dlp.exe"
    if link.is_file():
        return link
    for candidate in sorted((winget / "Packages").glob("yt-dlp.yt-dlp*/yt-dlp.exe")):
        return candidate
    return None


def work_folder(folder: Path, download_id: int) -> Path:
    return Path(folder) / f"{WORK_PREFIX}{download_id}"


def is_own_work_folder(path: Path, folder: Path) -> bool:
    """Only ".sdm-video-<number>" directly inside the download's folder (paths may come from
    the database, so never delete anything else)."""
    try:
        inside = path.parent.resolve() == Path(folder).resolve()
    except OSError:
        return False
    suffix = path.name.removeprefix(WORK_PREFIX)
    return inside and path.name.startswith(WORK_PREFIX) and suffix.isdigit()


def ytdlp_arguments(
    url: str, quality: VideoQuality, work: Path, *, ffmpeg: Path | None = None
) -> list[str]:
    """yt-dlp's arguments (without the program). --ignore-config first: a config file could
    otherwise add options such as --exec. The address comes last, after "--"."""
    return [
        "--ignore-config",
        "--no-playlist",
        "--no-cookies",
        "--no-cookies-from-browser",
        "--no-exec",
        "--newline",
        "--color", "never",
        "--no-mtime",
        "--windows-filenames",
        "--progress-template",
        f"download:{PROGRESS_MARK} %(progress.downloaded_bytes)s %(progress.total_bytes)s "
        "%(progress.total_bytes_estimate)s",
        "-P", str(work),
        "-o", "%(title).100B [%(id)s].%(ext)s",
        *(["--ffmpeg-location", str(ffmpeg)] if ffmpeg else []),
        *quality.arguments,
        "--",
        url,
    ]  # fmt: skip


def _number(text: str) -> int | None:
    try:
        value = int(float(text))
    except ValueError:  # yt-dlp prints NA for values it doesn't know
        return None
    return value if value >= 0 else None


_DESTINATION = re.compile(r"^\[(?:download|ExtractAudio)\] Destination: (.+)$")
_MERGING = re.compile(r'^\[Merger\] Merging formats into "(.+)"$')


class VideoProgress:
    """Reads yt-dlp's output. A video in 1080p or 4K usually arrives as two parts (video, then
    audio) that ffmpeg merges; each part counts from zero."""

    MAX_LOG_LINES = 30

    def __init__(self) -> None:
        self.part_name: str | None = None  # the file yt-dlp is writing now
        self.parts = 0
        self.received = 0
        self.total: int | None = None
        self.stage = "starting"  # starting, downloading, merging, converting
        self.log: list[str] = []

    def line(self, text: str) -> str | None:
        """Takes one line; returns "part" when a new part starts, "progress" when bytes
        arrived, else None."""
        text = text.strip()
        if not text:
            return None
        if text.startswith(PROGRESS_MARK):
            fields = text.split()[1:4]
            if len(fields) < 3:
                return None
            received, total, estimate = (_number(f) for f in fields)
            if received is None:
                return None
            self.received = received
            self.total = total or estimate
            self.stage = "downloading"
            return "progress"
        self.log = [*self.log[-(self.MAX_LOG_LINES - 1) :], text]
        if match := _DESTINATION.match(text):
            converting = text.startswith("[ExtractAudio]")
            self.stage = "converting" if converting else "downloading"
            self.part_name = Path(match.group(1)).name
            if not converting:
                self.parts += 1
                self.received, self.total = 0, None
            return "part"
        if _MERGING.match(text):
            self.stage = "merging"
        return None

    @property
    def failure_reason(self) -> str:
        return explain_failure(self.log)


_EXPLAINED = (
    ("Unsupported URL", "yt-dlp doesn't know how to download from this page."),
    ("Requested format is not available",
     "This video isn't available in the chosen quality. Try a lower one."),
    ("DRM", "This video is DRM-protected. SDM doesn't download protected videos."),
    ("Sign in", "This video needs a login. SDM doesn't sign in to sites."),
    ("login", "This video needs a login. SDM doesn't sign in to sites."),
    ("Private video", "This video is private."),
    ("members-only", "This video is for paying members only."),
    ("ffmpeg is not installed",
     "Merging video and audio needs ffmpeg. Install it with: winget install Gyan.FFmpeg"),
    ("ffprobe and ffmpeg not found",
     "Converting the audio needs ffmpeg. Install it with: winget install Gyan.FFmpeg"),
)  # fmt: skip


def explain_failure(log: list[str]) -> str:
    """Why yt-dlp failed, in plain words where SDM recognises the case, else its last error."""
    errors = [line.removeprefix("ERROR:").strip() for line in log if line.startswith("ERROR:")]
    text = "\n".join(errors or log)
    for needle, explanation in _EXPLAINED:
        if needle in text:
            return explanation
    if errors:
        return errors[-1]
    return log[-1] if log else ""


def finished_media(work: Path) -> Path | None:
    """The finished file yt-dlp left in its work folder: the largest media file that isn't
    a partial or intermediate part (".part", or "name.f137.mp4" before merging)."""
    try:
        files = [p for p in work.iterdir() if p.is_file()]
    except OSError:
        return None
    candidates = [
        p for p in files if p.suffix.lower() in MEDIA_SUFFIXES and not re.search(r"\.f\d+$", p.stem)
    ]
    return max(candidates, key=lambda p: p.stat().st_size, default=None)


def final_path(folder: Path, name: str) -> Path:
    """Where a finished video goes: its sanitized name in the folder, numbered if taken."""
    safe = sanitize_filename(name)
    number = 0
    while (Path(folder) / numbered_name(safe, number)).exists():
        number += 1
    return Path(folder) / numbered_name(safe, number)
