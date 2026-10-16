"""Reproduce the M2 HTTP client evaluation (ADR-0006): benchmark, then hook/cancel checks.

Runs in a throwaway environment, so neither library is added to SDM's dependencies:

    cd scripts/bench_http_clients
    uv run --no-project --with httpx==0.28.1 --with aiohttp==3.14.5 python run.py

Needs about 256 MB of free space in the temp folder for the synthetic test file.
"""

import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).parent


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def wait_for_port(port: int, seconds: float) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                return
        except OSError:
            time.sleep(0.5)
    raise RuntimeError(f"test server did not start on port {port}")


def main() -> None:
    port = free_port()
    with tempfile.TemporaryDirectory() as tmp:
        server = subprocess.Popen(  # noqa: S603 - fixed arguments, our own script
            [sys.executable, str(HERE / "server.py"), str(Path(tmp) / "bench.bin"), str(port)]
        )
        try:
            wait_for_port(port, 60)
            for script in ("client.py", "hooks.py"):
                print(f"\n######## {script} ########", flush=True)
                subprocess.run([sys.executable, str(HERE / script), str(port)], check=True)  # noqa: S603
        finally:
            server.terminate()
            server.wait(timeout=10)


if __name__ == "__main__":
    main()
