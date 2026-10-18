"""Shared pytest setup: off-screen Qt, a scriptable local HTTP server, and download helpers."""

import os

# Draw Qt windows off-screen: tests never pop up windows and also run without a desktop.
# This must be set before pytest-qt creates the QApplication.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import asyncio  # noqa: E402
import http.server  # noqa: E402
import re  # noqa: E402
import threading  # noqa: E402
import time  # noqa: E402
from collections import Counter  # noqa: E402
from collections.abc import Callable  # noqa: E402

import pytest  # noqa: E402

from sdm.engine.http_download import download  # noqa: E402
from sdm.engine.models import DownloadSettings  # noqa: E402
from sdm.engine.policy import NetworkPolicy  # noqa: E402
from sdm.storage.database import DownloadStore  # noqa: E402
from sdm.ui.controller import DownloadController  # noqa: E402

Route = Callable[[http.server.BaseHTTPRequestHandler], None]


class MockServer:
    """A local HTTP server (127.0.0.1, random port) whose responses each test scripts.

    It can misbehave on purpose: lie about sizes, cut connections, go silent, redirect
    anywhere. Each response closes the connection (HTTP/1.0), which keeps it simple.
    """

    def __init__(self) -> None:
        self.routes: dict[str, Route] = {}
        self.hits: Counter[str] = Counter()
        self.requests: list[dict[str, str]] = []  # headers of every request received
        server = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                path = self.path.split("?", 1)[0]
                server.hits[path] += 1
                server.requests.append(dict(self.headers))
                route = server.routes.get(path)
                try:
                    if route is None:
                        self.send_error(404)
                    else:
                        route(self)
                except OSError:
                    pass  # the client went away, e.g. a cancelled download

            def log_message(self, format: str, *args: object) -> None:
                pass  # keep test output quiet

        self._httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self._httpd.server_address[1]
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)

    def url(self, path: str) -> str:
        return f"http://127.0.0.1:{self.port}{path}"

    def add(self, path: str, *routes: Route) -> None:
        """Serve `path` with the given routes: the 1st request gets the 1st, and so on.
        The last route repeats for any further requests."""

        def sequence(handler: http.server.BaseHTTPRequestHandler) -> None:
            routes[min(self.hits[path], len(routes)) - 1](handler)

        self.routes[path] = sequence

    # ----- route builders -----

    @staticmethod
    def file(data: bytes, *, content_length: bool = True, headers: dict | None = None) -> Route:
        def route(h: http.server.BaseHTTPRequestHandler) -> None:
            h.send_response(200)
            for name, value in (headers or {}).items():
                h.send_header(name, value)
            if content_length:
                h.send_header("Content-Length", str(len(data)))
            h.end_headers()
            h.wfile.write(data)

        return route

    @staticmethod
    def status(code: int, *, headers: dict | None = None) -> Route:
        def route(h: http.server.BaseHTTPRequestHandler) -> None:
            h.send_response(code)
            for name, value in (headers or {}).items():
                h.send_header(name, value)
            h.send_header("Content-Length", "0")
            h.end_headers()

        return route

    @staticmethod
    def redirect(location: str, code: int = 302) -> Route:
        return MockServer.status(code, headers={"Location": location})

    @staticmethod
    def truncated(data: bytes) -> Route:
        """Promise len(data) bytes but close the connection halfway through."""

        def route(h: http.server.BaseHTTPRequestHandler) -> None:
            h.send_response(200)
            h.send_header("Content-Length", str(len(data)))
            h.end_headers()
            h.wfile.write(data[: len(data) // 2])

        return route

    @staticmethod
    def chunked(data: bytes, *, cut: bool = False) -> Route:
        """Send data with chunked transfer encoding (no Content-Length). With cut=True, stop
        halfway and close the connection without the final zero-length chunk."""

        def route(h: http.server.BaseHTTPRequestHandler) -> None:
            h.protocol_version = "HTTP/1.1"  # chunked encoding needs an HTTP/1.1 response
            h.send_response(200)
            h.send_header("Transfer-Encoding", "chunked")
            h.send_header("Connection", "close")
            h.end_headers()
            body = data[: len(data) // 2] if cut else data
            for start in range(0, len(body), 64 * 1024):
                piece = body[start : start + 64 * 1024]
                h.wfile.write(f"{len(piece):x}\r\n".encode() + piece + b"\r\n")
            if not cut:
                h.wfile.write(b"0\r\n\r\n")

        return route

    @staticmethod
    def stall(first_bytes: bytes, declared_length: int, seconds: float) -> Route:
        """Send the headers and a little data, then go silent for `seconds`."""

        def route(h: http.server.BaseHTTPRequestHandler) -> None:
            h.send_response(200)
            h.send_header("Content-Length", str(declared_length))
            h.end_headers()
            h.wfile.write(first_bytes)
            h.wfile.flush()
            time.sleep(seconds)

        return route

    @staticmethod
    def ranged(
        data: bytes,
        *,
        etag: str | None = None,
        last_modified: str | None = None,
        accept_ranges: bool = True,
        cut_at: int | None = None,
        stall_at: tuple[int, float] | None = None,
        content_range: str | None = None,
        log: list | None = None,
    ) -> Route:
        """A server that supports `Range: bytes=N-` like most real ones (206 + Content-Range).

        If-Range that doesn't match the current version tag gets the whole file (200), and a
        range past the end gets 416. To misbehave on purpose:
        cut_at: close the connection after sending this many body bytes.
        stall_at: (n, seconds): send n body bytes, then go silent for that long.
        content_range: send this Content-Range instead of the right one.
        log: gets (Range header, status, body bytes the reply sends) for each request,
            written before sending so a test never reads it too early.
        """

        def route(h: http.server.BaseHTTPRequestHandler) -> None:
            requested = h.headers.get("Range")
            if_range = h.headers.get("If-Range")
            match = re.fullmatch(r"bytes=(\d+)-", requested or "")
            start = int(match.group(1)) if match else None
            if start is not None and if_range is not None and if_range not in (etag, last_modified):
                start = None  # the file changed since the client's copy: send it whole
            # The log is written *before* anything is sent: the client may finish and the test
            # read the log before this thread runs again (a race seen once in a full run).
            if start is not None and start >= len(data):
                if log is not None:
                    log.append((requested, 416, 0))
                h.send_response(416)
                h.send_header("Content-Range", f"bytes */{len(data)}")
                h.send_header("Content-Length", "0")
                h.end_headers()
                return
            body = data if start is None else data[start:]
            status = 200 if start is None else 206
            if log is not None:
                planned = len(body) if cut_at is None else min(len(body), cut_at)
                log.append((requested, status, planned))  # body bytes this reply will send
            h.send_response(status)
            if accept_ranges:
                h.send_header("Accept-Ranges", "bytes")
            if etag:
                h.send_header("ETag", etag)
            if last_modified:
                h.send_header("Last-Modified", last_modified)
            if status == 206:
                h.send_header(
                    "Content-Range", content_range or f"bytes {start}-{len(data) - 1}/{len(data)}"
                )
            h.send_header("Content-Length", str(len(body)))
            h.end_headers()
            sent = 0
            if stall_at is not None:
                first, seconds = stall_at
                h.wfile.write(body[:first])
                h.wfile.flush()
                sent = len(body[:first])
                time.sleep(seconds)
                body = body[first:]
            h.wfile.write(body if cut_at is None else body[: max(0, cut_at - sent)])

        return route

    @staticmethod
    def trickle(data: bytes, *, pieces: int, delay: float) -> Route:
        """Send the whole file (with Content-Length) in `pieces` parts, `delay` s apart."""

        def route(h: http.server.BaseHTTPRequestHandler) -> None:
            h.send_response(200)
            h.send_header("Content-Length", str(len(data)))
            h.end_headers()
            step = -(-len(data) // pieces)  # ceiling division
            for start in range(0, len(data), step):
                h.wfile.write(data[start : start + step])
                h.wfile.flush()
                time.sleep(delay)

        return route

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()


@pytest.fixture
def mock_server():
    server = MockServer()
    server.start()
    yield server
    server.stop()


@pytest.fixture
def loopback_policy() -> NetworkPolicy:
    """The default policy, except that this computer (where MockServer runs) is allowed."""
    return NetworkPolicy(allow_loopback=True)


@pytest.fixture
def fast_settings() -> DownloadSettings:
    return DownloadSettings(connect_timeout=5.0, read_timeout=1.0, backoff_base=0.0)


@pytest.fixture
def fetch(tmp_path, loopback_policy, fast_settings):
    """Run one download synchronously; defaults: into tmp_path, loopback allowed, fast."""

    def _fetch(url, *, dest=None, policy=None, settings=None, on_progress=None, on_file_info=None):
        return asyncio.run(
            download(
                url,
                tmp_path if dest is None else dest,
                policy=policy or loopback_policy,
                settings=settings or fast_settings,
                on_progress=on_progress,
                on_file_info=on_file_info,
            )
        )

    return _fetch


@pytest.fixture
def make_controller(qapp, tmp_path, loopback_policy):
    """Build DownloadControllers on a temporary history (loopback allowed, short timeouts).

    Everything made is shut down and closed after the test.
    """
    made = []

    def make(*, start: bool = True, db_name: str = "sdm.db") -> DownloadController:
        store = DownloadStore(tmp_path / db_name)
        controller = DownloadController(
            store,
            policy_for=lambda record: loopback_policy,
            settings=DownloadSettings(connect_timeout=5.0, read_timeout=10.0, backoff_base=0.0),
        )
        if start:
            controller.start()
        made.append((controller, store))
        return controller

    yield make
    for controller, store in made:
        controller.shutdown()
        store.close()


@pytest.fixture(autouse=True)
def no_blocking_dialogs(monkeypatch):
    """A real message box waits for a click forever and would hang the test run.

    Any message box a test didn't plan for fails at once instead. Tests that expect one patch
    it themselves (their monkeypatch.setattr runs after this and wins).
    """
    from PySide6.QtWidgets import QMessageBox

    def unexpected(*args, **kwargs):
        raise AssertionError(f"Unexpected message box: {args[1:3]}")

    for name in ("question", "warning", "information", "critical"):
        monkeypatch.setattr(QMessageBox, name, staticmethod(unexpected))
