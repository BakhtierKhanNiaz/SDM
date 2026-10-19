"""SDM performance measurements (M10b), all local: no internet.

    uv run python scripts/perf/measure.py [--size-mib 1024]

A test server runs in a separate process (so it doesn't share the downloader's CPU or GIL)
and serves a deterministic file of the chosen size from memory, with Range support and an
ETag. Measured in this process:

1. One download over 1 and over 8 connections: time, speed, CPU time, peak memory.
2. SHA-256 of the downloaded file.
3. The window with 10,000 history entries: time to open, time to scroll through all of them.
4. The window while 8 downloads run at once: how late a 10 ms timer fires (the window
   freezes if the main thread is busy).

Results are printed as Markdown; temporary files are deleted afterwards.
"""

import argparse
import asyncio
import ctypes
import http.server
import os
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from ctypes import wintypes
from pathlib import Path

MIB = 1024 * 1024


# ----- the test server (separate process) -----


def serve(size: int) -> None:
    block = bytes((i * 131 + 7) % 251 for i in range(MIB))  # deterministic, incompressible-ish

    class Handler(http.server.BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self) -> None:
            match = re.fullmatch(r"bytes=(\d+)-(\d*)", self.headers.get("Range") or "")
            start = int(match.group(1)) if match else 0
            end = int(match.group(2)) if match and match.group(2) else size - 1
            end = min(end, size - 1)
            self.send_response(206 if match else 200)
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("ETag", '"perf-1"')
            if match:
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.send_header("Content-Length", str(end - start + 1))
            self.send_header("Connection", "close")
            self.end_headers()
            position = start
            try:
                while position <= end:
                    offset = position % MIB
                    piece = block[offset : offset + min(MIB - offset, end - position + 1)]
                    self.wfile.write(piece)
                    position += len(piece)
            except OSError:
                pass

        def log_message(self, *args: object) -> None:
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    print(server.server_address[1], flush=True)
    server.serve_forever()


def start_server(size: int) -> tuple[subprocess.Popen, str]:
    process = subprocess.Popen(  # noqa: S603 - this script, fixed arguments
        [sys.executable, __file__, "--serve", str(size)], stdout=subprocess.PIPE, text=True
    )
    port = int(process.stdout.readline())
    return process, f"http://127.0.0.1:{port}"


# ----- process measurements -----


class _Counters(ctypes.Structure):
    _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [
        (name, ctypes.c_size_t)
        for name in ("PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage",
                     "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage",
                     "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage")
    ]  # fmt: skip


def memory_mib() -> tuple[float, float]:
    """(current, peak) working set of this process, in MiB."""
    kernel32, psapi = ctypes.windll.kernel32, ctypes.windll.psapi
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE  # a 64-bit pseudo-handle
    psapi.GetProcessMemoryInfo.argtypes = [
        wintypes.HANDLE, ctypes.POINTER(_Counters), wintypes.DWORD
    ]  # fmt: skip
    counters = _Counters()
    counters.cb = ctypes.sizeof(counters)
    if not psapi.GetProcessMemoryInfo(kernel32.GetCurrentProcess(), counters, counters.cb):
        raise ctypes.WinError()
    return counters.WorkingSetSize / MIB, counters.PeakWorkingSetSize / MIB


# ----- 1 and 2: one download, then its SHA-256 -----


def measure_download(base: str, size: int, folder: Path, connections: int) -> dict:
    from sdm.core.checksums import sha256_of
    from sdm.engine.http_download import download
    from sdm.engine.models import DownloadSettings
    from sdm.engine.policy import NetworkPolicy

    settings = DownloadSettings(max_connections=connections)
    cpu, start = time.process_time(), time.perf_counter()
    result = asyncio.run(
        download(f"{base}/file-{connections}.bin", folder,
                 policy=NetworkPolicy(allow_loopback=True), settings=settings)
    )  # fmt: skip
    seconds = time.perf_counter() - start
    cpu = time.process_time() - cpu
    if result.size != size:
        raise RuntimeError(f"downloaded {result.size} bytes, expected {size}")
    hash_start = time.perf_counter()
    sha256_of(result.path)
    hash_seconds = time.perf_counter() - hash_start
    result.path.unlink()
    return {
        "connections": connections,
        "seconds": seconds,
        "mib_s": size / MIB / seconds,
        "cpu": cpu,
        "hash_seconds": hash_seconds,
        "hash_mib_s": size / MIB / hash_seconds,
    }


# ----- 3 and 4: the window -----


def measure_window(base: str, folder: Path) -> dict:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QElapsedTimer, QTimer
    from PySide6.QtWidgets import QApplication

    from sdm.core.downloads import DownloadState
    from sdm.engine.policy import NetworkPolicy
    from sdm.storage.database import DownloadStore
    from sdm.ui.controller import DownloadController
    from sdm.ui.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    results: dict = {}

    # 10,000 history entries, written straight into a fresh history.
    store = DownloadStore(folder / "big.db")
    now = "2026-10-20T00:00:00+00:00"
    with store._conn:
        store._conn.executemany(
            "INSERT INTO downloads (url, folder, state, file_name, path, total_bytes,"
            " received_bytes, verified_complete, created_at, updated_at, finished_at,"
            " queue_position, category) VALUES (?, ?, 'completed', ?, ?, 1000, 1000, 1, ?, ?, ?,"
            " ?, 'General')",
            [(f"https://example.com/f{i}.zip", str(folder), f"f{i}.zip", str(folder / f"f{i}"),
              now, now, now, i) for i in range(10_000)],
        )  # fmt: skip
    started = time.perf_counter()
    controller = DownloadController(store)
    window = MainWindow(controller, default_folder=folder)
    window.show()
    app.processEvents()
    results["open_10k"] = time.perf_counter() - started
    table = window.download_table
    started = time.perf_counter()
    bar = table.verticalScrollBar()
    step = max(1, bar.pageStep())
    pages = 0
    for value in range(0, bar.maximum() + step, step):
        bar.setValue(value)
        app.processEvents()
        pages += 1
    results["scroll_10k"] = time.perf_counter() - started
    results["pages"] = pages
    window.confirm_quit = lambda active: True
    window.close()
    store.close()

    # 8 downloads at once (64 MiB each) through the window code; a 10 ms timer measures how
    # late the main thread gets to it.
    store = DownloadStore(folder / "eight.db")
    controller = DownloadController(store, policy_for=lambda r: NetworkPolicy(allow_loopback=True))
    controller.start()
    window = MainWindow(controller, default_folder=folder)
    window.show()
    lateness: list[float] = []
    clock = QElapsedTimer()
    clock.start()
    last = [clock.elapsed()]

    def tick() -> None:
        now_ms = clock.elapsed()
        lateness.append(now_ms - last[0] - 10)
        last[0] = now_ms

    timer = QTimer()
    timer.setInterval(10)
    timer.timeout.connect(tick)
    from dataclasses import replace

    controller.set_queue_settings(replace(controller.queue_settings, limit=8))
    ids = [controller.add(f"{base}/eight-{i}.bin?size=64", folder).id for i in range(8)]
    timer.start()
    started = time.perf_counter()
    while not all(store.get(i).state == DownloadState.COMPLETED for i in ids):
        app.processEvents()
        time.sleep(0.002)
        if time.perf_counter() - started > 600:
            raise TimeoutError("8 downloads didn't finish in 10 minutes")
    results["eight_seconds"] = time.perf_counter() - started
    timer.stop()
    results["late_median"] = statistics.median(lateness)
    results["late_p99"] = sorted(lateness)[int(len(lateness) * 0.99)]
    results["late_max"] = max(lateness)
    window.confirm_quit = lambda active: True
    window.close()
    controller.shutdown()
    store.close()
    return results


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--size-mib", type=int, default=1024)
    parser.add_argument("--serve", type=int)
    args = parser.parse_args()
    if args.serve:
        serve(args.serve)
        return
    size = args.size_mib * MIB
    folder = Path(tempfile.mkdtemp(prefix="sdm-perf-"))
    server, base = start_server(size)
    eight_server, eight_base = start_server(64 * MIB)
    try:
        rows = [measure_download(base, size, folder, n) for n in (1, 8)]
        current, peak = memory_mib()
        window = measure_window(eight_base, folder)
    finally:
        server.kill()
        eight_server.kill()
        shutil.rmtree(folder, ignore_errors=True)
    print(f"\n### Downloads of {args.size_mib} MiB from a local server\n")
    print("| Connections | Time | Speed | CPU time | SHA-256 time |")
    print("|---|---|---|---|---|")
    for r in rows:
        print(
            f"| {r['connections']} | {r['seconds']:.1f} s | {r['mib_s']:.0f} MiB/s | "
            f"{r['cpu']:.1f} s | {r['hash_seconds']:.1f} s ({r['hash_mib_s']:.0f} MiB/s) |"
        )
    print(f"\nPeak memory of the downloading process: {peak:.0f} MiB (now {current:.0f} MiB).")
    print("\n### The window\n")
    print(f"- Open with 10,000 history entries: {window['open_10k']:.2f} s")
    per_page = window["scroll_10k"] / window["pages"] * 1000
    print(f"- Scroll through all 10,000 entries: {window['pages']} pages in "
          f"{window['scroll_10k']:.1f} s, {per_page:.0f} ms per page")  # fmt: skip
    print(f"- 8 downloads of 64 MiB at once: {window['eight_seconds']:.1f} s; a 10 ms timer was "
          f"late by {window['late_median']:.0f} ms (median), {window['late_p99']:.0f} ms (99th "
          f"percentile), {window['late_max']:.0f} ms (worst)")  # fmt: skip


if __name__ == "__main__":
    main()
