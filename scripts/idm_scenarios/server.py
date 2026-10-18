"""Local server for comparing IDM and SDM on identical responses (M2, Stage A/E).

    uv run python scripts/idm_scenarios/server.py [--port 8765] [--log requests.jsonl]

Scenarios, all on http://127.0.0.1:<port>:
  1  /dl?id=7            a file named only by Content-Disposition: "Report 2026.pdf"
  2  /files/sample.zip   a plain file; download it twice to see duplicate handling
  3  /missing.zip        404 Not Found
  4  /start              302 redirect to /files/archive.zip
  5  /stream.bin         no Content-Length; 3 MiB sent over about 6 s
  5b /slow-stream.bin    no Content-Length; 3 MiB sent over about 90 s, to watch progress
  6  /cut.bin            promises 4 MiB, sends 2 MiB, then closes (every time)

Every request is printed as one JSON line when it ends: when it started and ended (with
milliseconds), a connection number and the client's port, the status line sent, the body bytes
Windows accepted for sending, whether the client hung up first, and some request headers
(Range, User-Agent, ...). Cookie and Authorization headers are never logged. Range requests are
ignored on purpose: the server always sends the whole file and never advertises Accept-Ranges,
so clients must use a single connection.
"""

import argparse
import hashlib
import http.server
import json
import threading
import time
from datetime import datetime

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
# Small pieces, so a progress display has something to show about twice a second.
SLOW_STREAM = payload("slow-stream", 3 * MIB)
SLOW_CHUNK = 16 * 1024
SLOW_DELAY = 90 / (len(SLOW_STREAM) / SLOW_CHUNK)  # 192 pieces, 0.47 s apart: about 90 s

# Expected size and SHA-256 of every complete file, by the path that finally serves it.
EXPECTED = {
    path: (len(data), hashlib.sha256(data).hexdigest())
    for path, data in [(p, d) for p, (d, _) in FILES.items()]
    + [("/stream.bin", STREAM), ("/slow-stream.bin", SLOW_STREAM)]
}


def stamp(moment: datetime) -> str:
    return moment.isoformat(sep=" ", timespec="milliseconds")


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
        self.conn, self.started, self.clock = self.server.arrived()
        self.status, self.sent, self.disconnected = 0, 0, False
        path = self.path.split("?", 1)[0]
        try:
            self._route(path, send_body)
        except OSError:
            self.disconnected = True  # the client hung up; status and sent show how far we got
        finally:
            self.server.record(self)

    def _start(self, status: int, headers: dict[str, str]) -> None:
        self.send_response(status)
        for name, value in headers.items():
            self.send_header(name, value)
        self.send_header("Connection", "close")
        self.end_headers()
        self.status = status  # only once the status line and headers were handed to Windows

    def _route(self, path: str, send_body: bool) -> None:
        if path in FILES:
            data, headers = FILES[path]
            self._start(200, {**headers, "Content-Length": str(len(data))})
            if send_body:
                self._send(data)
        elif path == "/start":
            self._start(302, {"Location": "/files/archive.zip", "Content-Length": "0"})
        elif path == "/stream.bin":
            self._start(200, {"Content-Type": "application/octet-stream"})  # no length
            if send_body:
                self._send(STREAM, delay=0.125)
        elif path == "/slow-stream.bin":
            self._start(200, {"Content-Type": "application/octet-stream"})  # no length
            if send_body:
                self._send(SLOW_STREAM, chunk=SLOW_CHUNK, delay=SLOW_DELAY)
        elif path == "/cut.bin":
            self._start(
                200, {"Content-Type": "application/octet-stream", "Content-Length": str(len(CUT))}
            )
            if send_body:
                self._send(CUT[: len(CUT) // 2], delay=0.05)
        else:
            body = b"Not Found"
            self._start(404, {"Content-Type": "text/plain", "Content-Length": str(len(body))})
            if send_body:
                self._send(body)

    def _send(self, data: bytes, chunk: int = CHUNK, delay: float = 0.0) -> None:
        """Send data in pieces, pausing `delay` seconds after each one. Every byte Windows
        accepts is counted at once in self.sent, so a hang-up halfway leaves the real count."""
        for start in range(0, len(data), chunk):
            piece = memoryview(data[start : start + chunk])
            while piece:
                accepted = self.connection.send(piece)
                self.sent += accepted
                piece = piece[accepted:]
            if delay:
                time.sleep(delay)


class ScenarioServer(http.server.ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, port: int, log_path: str | None = None, echo: bool = True) -> None:
        super().__init__(("127.0.0.1", port), ScenarioHandler)
        self.log: list[dict] = []
        self._lock = threading.Lock()
        self._log_path = log_path
        self._echo = echo
        self._requests = 0

    def arrived(self) -> tuple[int, datetime, float]:
        """Number a new request and note when it arrived: wall clock for the log, and a
        monotonic clock for its duration (immune to Windows correcting the clock)."""
        with self._lock:  # numbers follow arrival order, even across threads
            self._requests += 1
            return self._requests, datetime.now(), time.perf_counter()

    def record(self, handler: ScenarioHandler) -> None:
        end = datetime.now()
        entry = {
            "time": end.strftime("%H:%M:%S"),  # the end time, as in the first M2 log lines
            "start": stamp(handler.started),
            "end": stamp(end),
            "duration_s": round(time.perf_counter() - handler.clock, 3),
            "conn": handler.conn,
            "client_port": handler.client_address[1],
            "method": handler.command,
            "path": handler.path,
            "status": handler.status,
            "bytes_sent": handler.sent,
            "disconnected": handler.disconnected,
            "headers": {h: handler.headers[h] for h in LOGGED_HEADERS if handler.headers.get(h)},
        }
        with self._lock:
            if self._log_path:
                with open(self._log_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(entry) + "\n")
            self.log.append(entry)  # after the file, so anything in self.log is on disk too
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
        "/slow-stream.bin",
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
