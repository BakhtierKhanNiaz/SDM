"""Run SDM's engine through the same scenarios IDM sees, and report what happened.

    uv run python scripts/idm_scenarios/run_sdm.py

The engine is called directly with loopback allowed, because the scenario server runs on this
computer and `sdm-get` (correctly) refuses that. Files go to a temporary folder that is deleted
afterwards.
"""

import asyncio
import hashlib
import tempfile
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit

from server import EXPECTED, ScenarioServer

from sdm.core.errors import SDMError
from sdm.engine.http_download import download
from sdm.engine.policy import NetworkPolicy

SCENARIOS = [
    ("1  Content-Disposition name", "/dl?id=7"),
    ("2a Duplicate, first download", "/files/sample.zip"),
    ("2b Duplicate, second download", "/files/sample.zip"),
    ("3  404 Not Found", "/missing.zip"),
    ("4  302 redirect", "/start"),
    ("5  Unknown size", "/stream.bin"),
    ("6  Connection cut halfway", "/cut.bin"),
]


def main() -> None:
    server = ScenarioServer(0, echo=False)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    policy = NetworkPolicy(allow_loopback=True)  # the scenario server runs on this computer

    with tempfile.TemporaryDirectory() as tmp:
        for title, path in SCENARIOS:
            before = len(server.log)
            start = time.perf_counter()
            try:
                result = asyncio.run(download(f"http://127.0.0.1:{port}{path}", tmp, policy=policy))
                size, digest = EXPECTED[urlsplit(result.final_url).path]
                actual = hashlib.sha256(result.path.read_bytes()).hexdigest()
                check = "SHA-256 matches" if (result.size, actual) == (size, digest) else "MISMATCH"
                note = "" if result.verified_complete else ", completeness not confirmed"
                outcome = f"saved '{result.path.name}' ({result.size:,} bytes, {check}{note})"
            except SDMError as exc:
                outcome = f"error: {exc}"
            seconds = time.perf_counter() - start
            requests = server.log[before:]
            print(f"{title}\n    {outcome}  [{seconds:.1f} s]")
            for r in requests:
                headers = ", ".join(f"{k}: {v}" for k, v in r["headers"].items())
                line = f"{r['method']} {r['path']} -> {r['status']} ({r['bytes_sent']:,} bytes)"
                print(f"    {line} {headers}")
        leftovers = sorted(p.name for p in Path(tmp).iterdir())
        print(f"\nFiles left in the download folder: {leftovers}")
    server.shutdown()


if __name__ == "__main__":
    main()
