"""Local server for comparing IDM and SDM on identical responses (M2, Stage A/E).

    uv run python scripts/idm_scenarios/server.py [--port 8765] [--log requests.jsonl]

Scenarios, all on http://127.0.0.1:<port>:
  1  /dl?id=7            a file named only by Content-Disposition: "Report 2026.pdf"
  2  /files/sample.zip   a plain file; download it twice to see duplicate handling
  3  /missing.zip        404 Not Found
  4  /start              302 redirect to /files/archive.zip
  5  /stream.bin         no Content-Length; 3 MiB sent over about 6 s
  6  /cut.bin            promises 4 MiB, sends 2 MiB, then closes (every time)

Every request is printed (method, path, Range, User-Agent, ...). Cookie and Authorization
headers are never logged. Range requests are ignored on purpose: the server always sends the
whole file and never advertises Accept-Ranges, so clients must use a single connection.
"""

import argparse
import hashlib
import http.server
import json
import threading
import time

MIB = 1024 * 1024
CHUNK = 64 * 1024
LOGGED_HEADERS = ("Range", "If-Range", "User-Agent", "Accept-Encoding", "Accept", "Connection")


def payload(name: str, size: int) -> bytes:
    """Deterministic test data, so saved files can be checked against a known SHA-256."""
    out = bytearray()
    counter = 0
    while len(out) < size:
        out += hashlib.sha256(f"{name}:{counter}".encode()).digest()
        counter += 1
    return bytes(out[:size])


FILES = {
    "/dl": (
        payload("report", MIB),
        {
            "Content-Type": "application/pdf",
            "Content-Disposition": 'attachment; filename="Report 2026.pdf"',
        },
    ),
    "/files/sample.zip": (payload("sample", MIB), {"Content-Type": "application/zip"}),
    "/files/archive.zip": (payload("archive", MIB), {"Content-Type": "application/zip"}),
}
STREAM = payload("stream", 3 * MIB)
CUT = payload("cut", 4 * MIB)

# Expected size and SHA-256 of every complete file, by the path that finally serves it.
EXPECTED = {
    path: (len(data), hashlib.sha256(data).hexdigest())
    for path, data in [(p, d) for p, (d, _) in FILES.items()] + [("/stream.bin", STREAM)]
}


class ScenarioHandler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "SDM-ScenarioServer/1.0"

    def do_HEAD(self) -> None:
        self._serve(send_body=False)

    def do_GET(self) -> None:
        self._serve(send_body=True)

    def log_message(self, format: str, *args: object) -> None:
        pass  # requests are recorded by ScenarioServer.record instead

    def _serve(self, send_body: bool) -> None:
        self.close_connection = True  # one request per connection keeps the log easy to read
        path = self.path.split("?", 1)[0]
        status, sent = 0, 0
        try:
            status, sent = self._route(path, send_body)
        except OSError:
            pass  # the client hung up
        finally:
            self.server.record(self, status, sent)

    def _start(self, status: int, headers: dict[str, str]) -> None:
        self.send_response(status)
        for name, value in headers.items():
            self.send_header(name, value)
        self.send_header("Connection", "close")
        self.end_headers()

    def _route(self, path: str, send_body: bool) -> tuple[int, int]:
        if path in FILES:
            data, headers = FILES[path]
            self._start(200, {**headers, "Content-Length": str(len(data))})
            if send_body:
                self.wfile.write(data)
                return 200, len(data)
            return 200, 0
        if path == "/start":
            self._start(302, {"Location": "/files/archive.zip", "Content-Length": "0"})
            return 302, 0
        if path == "/stream.bin":
            self._start(200, {"Content-Type": "application/octet-stream"})  # no length
            return 200, self._trickle(STREAM, delay=0.125) if send_body else 0
        if path == "/cut.bin":
            self._start(
                200, {"Content-Type": "application/octet-stream", "Content-Length": str(len(CUT))}
            )
            return 200, self._trickle(CUT[: len(CUT) // 2], delay=0.05) if send_body else 0
        body = b"Not Found"
        self._start(404, {"Content-Type": "text/plain", "Content-Length": str(len(body))})
        if send_body:
            self.wfile.write(body)
        return 404, len(body) if send_body else 0

    def _trickle(self, data: bytes, delay: float) -> int:
        sent = 0
        for start in range(0, len(data), CHUNK):
            self.wfile.write(data[start : start + CHUNK])
            self.wfile.flush()
            sent += len(data[start : start + CHUNK])
            time.sleep(delay)
        return sent


class ScenarioServer(http.server.ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, port: int, log_path: str | None = None, echo: bool = True) -> None:
        super().__init__(("127.0.0.1", port), ScenarioHandler)
        self.log: list[dict] = []
        self._lock = threading.Lock()
        self._log_path = log_path
        self._echo = echo

    def record(self, handler: ScenarioHandler, status: int, sent: int) -> None:
        entry = {
            "time": time.strftime("%H:%M:%S"),
            "method": handler.command,
            "path": handler.path,
            "status": status,
            "bytes_sent": sent,
            "headers": {h: handler.headers[h] for h in LOGGED_HEADERS if handler.headers.get(h)},
        }
        with self._lock:
            self.log.append(entry)
            if self._log_path:
                with open(self._log_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(entry) + "\n")
        if self._echo:
            print(json.dumps(entry), flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--log", help="append every request as a JSON line to this file")
    args = parser.parse_args()

    server = ScenarioServer(args.port, args.log)
    base = f"http://127.0.0.1:{server.server_address[1]}"
    print(f"Scenario server on {base}  (Ctrl+C to stop)\n")
    for url in (
        "/dl?id=7",
        "/files/sample.zip",
        "/missing.zip",
        "/start",
        "/stream.bin",
        "/cut.bin",
    ):
        print(f"  {base}{url}")
    print("\nExpected complete files:")
    for path, (size, digest) in EXPECTED.items():
        print(f"  {path:18} {size:>9,} bytes  SHA-256 {digest}")
    print(flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
