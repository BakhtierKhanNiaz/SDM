"""Voice and music for SDM's promo video.

    PIPER_PYTHON=...\\python.exe python scripts/promo/make_promo_audio.py VOICE.onnx SPEAKER

1. Piper (free, open source, runs on this PC) reads each line of NARRATION with the given
   voice and speaker; each line starts with its scene and must end before the next one.
2. make_music.py's track plays underneath, quieter while the voice speaks.
3. The sound is put into dist\\promo\\sdm-<version>-wide.mp4 and -tall.mp4, giving
   ...-wide-sound.mp4 and ...-tall-sound.mp4 (the picture is copied, not re-encoded).

The voice used for SDM's videos is "en_US-libritts_r-medium" (LibriTTS-R, CC BY 4.0): credit
it where the video is published (see YOUTUBE_CREDIT).
"""

import os
import subprocess
import sys
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from sdm import __version__  # noqa: E402
from sdm.media.ffmpeg import find_ffmpeg  # noqa: E402

OUT = ROOT / "dist" / "promo"
SECONDS = 35.0
# (when it starts, at most how long it may last, the words): the scenes of make_promo.py
NARRATION = [
    (0.4, 3.0, "Meet SDM: the free download manager for Windows."),
    (3.8, 5.5, "It splits big files across eight connections, and picks up where it stopped."),
    (9.8, 5.5, "Watching a video? Click the SDM button, choose the quality, and you're done."),
    (15.8, 4.0, "Everything stays organised, at a glance."),
    (20.3, 4.0, "Turn any video into MP3 or MP4, right inside SDM."),
    (24.8, 3.0, "Light or dark, it fits right in."),
    (28.4, 5.5, "SDM is free and open source. Download it today, from GitHub."),
]
# make_tutorial.py's scenes start at 0, 5, 14, 23, 33, 42, 51 and 59 s (67 s in all).
TUTORIAL = [
    (0.5, 4.3, "Here's how to install and use SDM, the free download manager for Windows."),
    (5.5, 8.0, "First, open SDM's releases page on GitHub, and download SDM Setup."),
    (14.5, 8.0, "Run it. If Windows SmartScreen warns you, click More info, then Run anyway."),
    (23.5, 9.0, "The welcome assistant connects your browsers. Press Add to Chrome, "
                "and follow the three steps."),
    (33.5, 8.0, "To download a file, click Add URL, paste the address, and press Download."),
    (42.5, 8.0, "In your browser, downloads open in SDM. On a video, click the SDM button."),
    (51.5, 7.0, "Pause, resume, or convert to MP3 and MP4, whenever you like."),
    (59.5, 7.0, "SDM is free and open source. The link is in the description."),
]  # fmt: skip
# what each script narrates: its lines, its length, and the videos it goes into
SCRIPTS = {
    "promo": (NARRATION, 35.0, ["sdm-{v}-wide", "sdm-{v}-tall"]),
    "tutorial": (TUTORIAL, 67.0, ["sdm-{v}-tutorial-wide"]),
}
YOUTUBE_CREDIT = (
    "Voice: Piper text-to-speech (github.com/OHF-voice/piper1-gpl), voice en_US-libritts_r-medium "
    "trained on LibriTTS-R by Koizumi et al. (openslr.org/141), CC BY 4.0. "
    "Music: composed for SDM."
)


def length(path: Path) -> float:
    with wave.open(str(path)) as w:
        return w.getnframes() / w.getframerate()


def speak(
    piper_python: str, voice: Path, speaker: int, text: str, out: Path, scale: float
) -> float:
    command = [piper_python, "-m", "piper", "-m", str(voice), "-s", str(speaker),
               "--length-scale", str(scale), "-f", str(out), "--", text]  # fmt: skip
    subprocess.run(command, check=True, capture_output=True)  # noqa: S603 - fixed program
    return length(out)


def main() -> int:
    voice, speaker = Path(sys.argv[1]), int(sys.argv[2])
    kind = sys.argv[3] if len(sys.argv) > 3 else "promo"
    narration, seconds_total, stems = SCRIPTS[kind]
    piper_python = os.environ.get("PIPER_PYTHON", sys.executable)
    ffmpeg = str(find_ffmpeg())
    work = OUT / "audio" / kind
    work.mkdir(parents=True, exist_ok=True)
    lines = []
    for number, (start, room, words) in enumerate(narration):
        out = work / f"line-{number}.wav"
        scale = 1.15  # a calm narration pace (Piper's default is brisk)
        seconds = speak(piper_python, voice, speaker, words, out, scale)
        while seconds > room and scale > 0.8:  # a little quicker until it fits its scene
            scale -= 0.05
            seconds = speak(piper_python, voice, speaker, words, out, scale)
        print(f"line {number + 1}: {seconds:.1f} s of {room:.1f} (speed x{1 / scale:.2f})")
        if seconds > room:
            print("  too long for its scene: shorten the words", file=sys.stderr)
            return 1
        lines.append((start, out))
    music = work / "music.wav"  # its own length per script
    if not music.exists():
        # Piper's Python has numpy, which make_music.py needs (SDM's own environment doesn't)
        command = [piper_python, str(Path(__file__).with_name("make_music.py")), str(music),
                   str(seconds_total)]  # fmt: skip
        subprocess.run(command, check=True)  # noqa: S603 - fixed program
    # The voice lines, each delayed to its start; then the music, ducked while the voice talks.
    inputs, chains = ["-i", str(music)], []
    for index, (start, path) in enumerate(lines, 1):
        inputs += ["-i", str(path)]
        delay = int(start * 1000)
        chains.append(f"[{index}:a]aresample=44100,aformat=channel_layouts=stereo,"
                      f"adelay={delay}|{delay}[v{index}]")  # fmt: skip
    joined = "".join(f"[v{i}]" for i in range(1, len(lines) + 1))
    # Padded to the whole video: the ducking ends when its key (the voice) ends, which cut the
    # sound, and with it the video's last scene, to 31.6 s (seen 2026-10-26).
    chains.append(f"{joined}amix=inputs={len(lines)}:normalize=0,volume=1.6,"
                  f"apad=whole_dur={seconds_total},asplit=2[voice][key]")  # fmt: skip
    chains.append("[0:a]volume=0.4[bed]")  # music about 20 dB down: the voice stays clear
    chains.append(
        "[bed][key]sidechaincompress=threshold=0.03:ratio=6:attack=20:release=400[ducked]"
    )
    chains.append("[ducked][voice]amix=inputs=2:normalize=0,alimiter=limit=0.95[mix]")
    mixed = work / "mix.wav"
    command = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", *inputs,
               "-filter_complex", ";".join(chains), "-map", "[mix]", "-t", str(seconds_total),
               str(mixed)]  # fmt: skip
    subprocess.run(command, check=True)  # noqa: S603 - fixed program
    videos = [OUT / (stem.format(v=__version__) + ".mp4") for stem in stems]
    if not any(video.exists() for video in videos):
        # e.g. run with Piper's own Python, which doesn't know SDM's version: use uv run
        print(f"No video for SDM {__version__} in {OUT}: run make_promo.py first, and this "
              "script with uv run (PIPER_PYTHON for Piper).", file=sys.stderr)  # fmt: skip
        return 1
    for video in videos:
        if not video.exists():
            continue
        target = video.with_name(video.stem + "-sound.mp4")
        command = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(video),
                   "-i", str(mixed), "-map", "0:v", "-map", "1:a", "-c:v", "copy",
                   "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart",
                   str(target)]  # fmt: skip
        subprocess.run(command, check=True)  # noqa: S603 - fixed program
        print(f"Made {target}")
    print(f"Credit for the description: {YOUTUBE_CREDIT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
