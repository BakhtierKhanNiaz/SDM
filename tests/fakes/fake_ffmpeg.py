"""A stand-in for ffmpeg in SDM's tests (M12a): no real media, no real ffmpeg needed.

It reads the arguments SDM gives it, prints a Duration line and -progress lines like ffmpeg,
and writes a small output file. FAKE_FFMPEG_MODE chooses: "ok" (default), "fail" (writes a
partial file, then fails like ffmpeg does when a file has no audio) or "slow" (writes a partial
file and keeps going until it is stopped). FAKE_FFMPEG_LOG, if set, receives the arguments.
"""

import json
import os
import sys
import time

args = sys.argv[1:]
if log := os.environ.get("FAKE_FFMPEG_LOG"):
    with open(log, "w", encoding="utf-8") as file:
        json.dump(args, file)


def path_of(arg: str) -> str:
    return arg.removeprefix("file:")


source = path_of(args[args.index("-i") + 1])
target = path_of(args[-1])
if "-n" in args and os.path.exists(target):
    print(f"File '{target}' already exists. Exiting.", file=sys.stderr)
    sys.exit(1)

print("Input #0, matroska,webm, from 'x':", file=sys.stderr)
print("  Duration: 00:00:10.00, start: 0.000000, bitrate: 128 kb/s", file=sys.stderr, flush=True)
mode = os.environ.get("FAKE_FFMPEG_MODE", "ok")
with open(target, "wb") as out:
    out.write(b"partial")
if mode == "fail":  # real ffmpeg 9.0.2's words for a video without sound
    print("Stream map '' matches no streams.", file=sys.stderr)
    print("Failed to set value '0:a:0' for option 'map': Invalid argument", file=sys.stderr)
    print("Error opening output files: Invalid argument", file=sys.stderr, flush=True)
    sys.exit(1)
for seconds in (2.5, 5):
    print(f"out_time_us={int(seconds * 1_000_000)}\nprogress=continue", flush=True)
if mode == "slow":
    while True:
        time.sleep(0.1)
with open(source, "rb") as src, open(target, "wb") as out:
    out.write(b"converted:" + src.read())
print("out_time_us=10000000\nprogress=end", flush=True)
