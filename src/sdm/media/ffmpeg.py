"""Converting a file with ffmpeg (M12a, ADR-0020): where ffmpeg is, which formats SDM offers,
the exact command line, and how far a conversion has got."""

import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from sdm.core.filenames import numbered_name

INSTALL_HINT = "Install it for free with: winget install Gyan.FFmpeg"


@dataclass(frozen=True)
class OutputFormat:
    key: str
    label: str
    extension: str
    arguments: tuple[str, ...]  # what ffmpeg does to the input, between input and output


FORMATS: dict[str, OutputFormat] = {
    f.key: f
    for f in (
        OutputFormat(
            "mp3", "MP3 audio", ".mp3", ("-vn", "-map", "0:a:0", "-c:a", "libmp3lame", "-q:a", "2")
        ),
        OutputFormat(
            "m4a",
            "M4A audio (AAC)",
            ".m4a",
            ("-vn", "-map", "0:a:0", "-c:a", "aac", "-b:a", "192k"),
        ),
        OutputFormat(
            "mp4",
            "MP4 video (H.264)",
            ".mp4",
            (
                "-map",
                "0:v:0",
                "-map",
                "0:a:0?",
                "-c:v",
                "libx264",
                "-preset",
                "medium",
                "-crf",
                "23",
                "-c:a",
                "aac",
                "-b:a",
                "160k",
                "-movflags",
                "+faststart",
            ),
        ),  # fmt: skip
    )
}


def find_ffmpeg(configured: str = "", *, environ: dict[str, str] | None = None) -> Path | None:
    """ffmpeg.exe: the path set in Settings, else PATH, else where WinGet puts it."""
    if configured:
        path = Path(configured)
        return path if path.is_file() else None
    environ = os.environ if environ is None else environ
    found = shutil.which("ffmpeg", path=environ.get("PATH"))
    if found:
        return Path(found)
    # WinGet adds its Links folder to PATH, but only for programs started after the install.
    local = environ.get("LOCALAPPDATA")
    if not local:
        return None
    winget = Path(local) / "Microsoft" / "WinGet"
    link = winget / "Links" / "ffmpeg.exe"
    if link.is_file():
        return link
    for candidate in sorted((winget / "Packages").glob("Gyan.FFmpeg*/*/bin/ffmpeg.exe")):
        return candidate
    return None


def converted_path(source: Path, fmt: OutputFormat) -> Path:
    """A new file next to the source; never an existing file and never the source itself."""
    name = source.stem + fmt.extension
    number = 0
    while True:
        candidate = source.with_name(numbered_name(name, number))
        if not candidate.exists() and candidate != source:
            return candidate
        number += 1


def ffmpeg_arguments(source: Path, target: Path, fmt: OutputFormat) -> list[str]:
    """ffmpeg's arguments (without the program). `file:` keeps a name from being read as a
    protocol or an option; -n refuses to overwrite; progress goes to standard output."""
    return [
        "-hide_banner", "-nostdin", "-n",
        "-i", f"file:{source.resolve()}",
        *fmt.arguments,
        "-progress", "pipe:1", "-nostats",
        f"file:{target.resolve()}",
    ]  # fmt: skip


_DURATION = re.compile(r"Duration:\s*(\d+):(\d\d):(\d\d(?:\.\d+)?)")


def parse_duration(line: str) -> float | None:
    """Seconds from ffmpeg's "Duration: 00:03:21.45, ..." line, or None (also for N/A)."""
    match = _DURATION.search(line)
    if not match:
        return None
    hours, minutes, seconds = match.groups()
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


_UNKNOWN_ENCODER = re.compile(r"Unknown encoder '([^']+)'")


def explain_failure(log: list[str]) -> str:
    """Why ffmpeg failed, in plain words where SDM recognises the case, else its last line.

    Seen with ffmpeg 9.0.2 on a video without sound: "Stream map '' matches no streams.",
    then "Failed to set value '0:a:0' for option 'map': Invalid argument".
    """
    text = "\n".join(log)
    if "matches no streams" in text:
        if "'0:a:0'" in text:
            return "This file has no sound, so it can't become an audio file."
        if "'0:v:0'" in text:
            return "This file has no video, so it can't become an MP4 video. Choose MP3 or M4A."
    if match := _UNKNOWN_ENCODER.search(text):
        return (
            f"This ffmpeg doesn't include the {match.group(1)} encoder. Install the full "
            f"build: winget install Gyan.FFmpeg"
        )
    return log[-1] if log else ""


class ConversionProgress:
    """Reads ffmpeg's output: the duration from its log, the position from -progress."""

    MAX_LOG_LINES = 30

    def __init__(self) -> None:
        self.duration: float | None = None
        self.position = 0.0
        self.finished = False
        self.log: list[str] = []  # ffmpeg's last log lines, to explain a failure

    def log_line(self, line: str) -> None:
        """A line of ffmpeg's log (standard error)."""
        line = line.strip()
        if self.duration is None:
            self.duration = parse_duration(line)
        if line:
            self.log = [*self.log[-(self.MAX_LOG_LINES - 1) :], line]

    @property
    def failure_reason(self) -> str:
        return explain_failure(self.log)

    def progress_line(self, line: str) -> None:
        """A key=value line of -progress (standard output)."""
        key, _, value = line.strip().partition("=")
        if key == "out_time_us" and value.isdigit():
            self.position = int(value) / 1_000_000
        elif key == "progress" and value == "end":
            self.finished = True

    @property
    def percent(self) -> int | None:
        """0-100, or None while the length is unknown."""
        if self.finished:
            return 100
        if not self.duration:
            return None
        return max(0, min(99, int(self.position * 100 / self.duration)))
