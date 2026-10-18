"""Shared pytest setup: off-screen Qt, a scriptable local HTTP server, and download helpers."""

import os

# Draw Qt windows off-screen: tests never pop up windows and also run without a desktop.
# This must be set before pytest-qt creates the QApplication.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import asyncio  # noqa: E402
import http.server  # noqa: E402
import threading  # noqa: E402
import time  # noqa: E402
from collections import Counter  # noqa: E402
from collections.abc import Callable  # noqa: E402

import pytest  # noqa: E402

from sdm.engine.http_download import download  # noqa: E402
from sdm.engine.models import DownloadSettings  # noqa: E402
from sdm.engine.policy import NetworkPolicy  # noqa: E402

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

    def _fetch(url, *, dest=None, policy=None, settings=None, on_progress=None):
        return asyncio.run(
            download(
                url,
                tmp_path if dest is None else dest,
                policy=policy or loopback_policy,
                settings=settings or fast_settings,
                on_progress=on_progress,
            )
        )

    return _fetch
