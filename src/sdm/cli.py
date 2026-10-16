"""sdm-get: download one file from the command line.

uv run sdm-get URL [--dest FOLDER] [--allow-local-network] [--verbose]
"""

import argparse
import asyncio
import logging
import sys
import time
from pathlib import Path
from typing import TextIO

from sdm.core.errors import SDMError
from sdm.engine.http_download import download
from sdm.engine.policy import NetworkPolicy


def format_size(num_bytes: float) -> str:
    """1536 -> '1.5 KB'. Uses 1024-based units, as Windows Explorer does."""
    if num_bytes < 1024:
        return f"{num_bytes:.0f} bytes"
    size = num_bytes / 1024
    for unit in ("KB", "MB"):
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


class ProgressPrinter:
    """Prints a one-line progress display, at most 10 times a second."""

    def __init__(self, stream: TextIO | None = None) -> None:
        self._stream = stream or sys.stderr
        self._last_print = 0.0
        self._printed = False

    def __call__(self, received: int, total: int | None) -> None:
        now = time.monotonic()
        if now - self._last_print < 0.1 and received != total:
            return
        self._last_print = now
        if total:
            line = f"{received * 100 // total:3d}%  {format_size(received)} of {format_size(total)}"
        else:
            line = f"{format_size(received)} (size unknown)"
        self._stream.write(f"\r{line:<40}")
        self._stream.flush()
        self._printed = True

    def finish(self) -> None:
        if self._printed:
            self._stream.write("\n")
            self._printed = False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sdm-get", description="Download one file with SDM.")
    parser.add_argument("url", help="http:// or https:// address of the file")
    parser.add_argument(
        "--dest",
        type=Path,
        default=Path.home() / "Downloads",
        help="folder to save into (default: your Downloads folder)",
    )
    parser.add_argument(
        "--allow-local-network",
        action="store_true",
        help="allow servers on your local network, e.g. a NAS at 192.168.x.x",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="show what SDM is doing")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s: %(message)s",
    )
    policy = NetworkPolicy(allow_local_network=args.allow_local_network)
    progress = ProgressPrinter()
    try:
        result = asyncio.run(download(args.url, args.dest, policy=policy, on_progress=progress))
    except SDMError as exc:
        progress.finish()
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        progress.finish()
        print("Cancelled. The partial file was deleted.", file=sys.stderr)
        return 130
    progress.finish()
    print(f"Saved {result.path} ({format_size(result.size)})")
    return 0
