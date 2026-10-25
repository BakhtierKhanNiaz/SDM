"""A stand-in for yt-dlp in SDM's tests (M12b): no network, no real video site.

It reads the arguments SDM gives it and prints what yt-dlp prints for a video that arrives as
two parts merged by ffmpeg (or, with -x, one part converted to audio), with progress lines in
SDM's --progress-template format. FAKE_YTDLP_MODE: "ok" (default), "fail" (an unsupported
page) or "slow" (writes a partial file and keeps going until stopped). FAKE_YTDLP_LOG receives
the arguments; a run that finds an earlier partial file says so in "<work>/resumed.txt".
"""

import json
import os
import sys
import time
from pathlib import Path

args = sys.argv[1:]
if log := os.environ.get("FAKE_YTDLP_LOG"):
    Path(log).write_text(json.dumps(args), encoding="utf-8")

work = Path(args[args.index("-P") + 1])
url = args[args.index("--") + 1]
mode = os.environ.get("FAKE_YTDLP_MODE", "ok")
audio = "-x" in args
print(f"[generic] Extracting URL: {url}", flush=True)
if mode == "fail":
    print(f"ERROR: Unsupported URL: {url}", flush=True)
    sys.exit(1)

title = "Test Video [abc123]"
first = work / f"{title}.f137.mp4"
part = Path(str(first) + ".part")
if part.exists():
    (work / "resumed.txt").write_text("yes", encoding="utf-8")
print(f"[download] Destination: {first}", flush=True)
part.write_bytes(b"v" * 500)
print("SDMPROGRESS 500 1000 NA", flush=True)
if mode == "slow":
    while True:
        time.sleep(0.1)
part.write_bytes(b"v" * 1000)
print("SDMPROGRESS 1000 1000 NA", flush=True)
part.replace(first)
if audio:
    extension = args[args.index("--audio-format") + 1]
    final = work / f"{title}.{extension}"
    print(f"[ExtractAudio] Destination: {final}", flush=True)
    final.write_bytes(b"audio:" + first.read_bytes()[:10])
    first.unlink()
else:
    second = work / f"{title}.f140.m4a"
    print(f"[download] Destination: {second}", flush=True)
    print("SDMPROGRESS NA NA 300", flush=True)  # yt-dlp prints NA for unknown values
    second.write_bytes(b"a" * 300)
    print("SDMPROGRESS 300 300 NA", flush=True)
    final = work / f"{title}.mp4"
    print(f'[Merger] Merging formats into "{final}"', flush=True)
    final.write_bytes(first.read_bytes() + second.read_bytes())
    first.unlink()
    second.unlink()
