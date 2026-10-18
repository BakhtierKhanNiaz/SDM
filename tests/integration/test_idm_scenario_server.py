"""The IDM scenario server (scripts/idm_scenarios/server.py): routes and its request log.

The log is the evidence for docs/research/behavior-observations.md, so these tests pin what each
field means. The script isn't a package, so it's loaded from its path.
"""

import hashlib
import http.client
import importlib.util
import json
import socket
import struct
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import pytest

SERVER_PY = Path(__file__).parents[2] / "scripts" / "idm_scenarios" / "server.py"
_spec = importlib.util.spec_from_file_location("idm_scenario_server", SERVER_PY)
scenarios = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(scenarios)

MIB = 1024 * 1024


@pytest.fixture
def server(tmp_path):
    srv = scenarios.ScenarioServer(0, str(tmp_path / "requests.jsonl"), echo=False)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv
    srv.shutdown()
    srv.server_close()


def get(server, path: str, method: str = "GET") -> tuple[http.client.HTTPResponse, bytes, int]:
    """One request; returns the response, its body and the client's own port."""
    conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=10)
    conn.request(method, path, headers={"User-Agent": "scenario-test"})
    port = conn.sock.getsockname()[1]
    response = conn.getresponse()
    body = response.read()
    conn.close()
    return response, body, port


def open_raw(server, path: str) -> socket.socket:
    sock = socket.create_connection(("127.0.0.1", server.server_address[1]), timeout=10)
    sock.sendall(
        f"GET {path} HTTP/1.1\r\nHost: 127.0.0.1\r\nUser-Agent: scenario-test\r\n\r\n".encode()
    )
    return sock


def read_body_bytes(sock: socket.socket, count: int) -> tuple[bytes, bytes]:
    """Read the headers and at least `count` body bytes; returns (headers, body so far)."""
    data = b""
    while b"\r\n\r\n" not in data or len(data.split(b"\r\n\r\n", 1)[1]) < count:
        piece = sock.recv(64 * 1024)
        assert piece, "the server closed the connection early"
        data += piece
    head, body = data.split(b"\r\n\r\n", 1)
    return head, body


def hang_up(sock: socket.socket) -> None:
    """Close abruptly (TCP reset), the way a client cancelling a transfer would."""
    linger = struct.pack("HH" if sys.platform == "win32" else "ii", 1, 0)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, linger)
    sock.close()


def wait_for_log(server, count: int, timeout: float = 10.0) -> list[dict]:
    deadline = time.monotonic() + timeout
    while len(server.log) < count:
        assert time.monotonic() < deadline, f"only {len(server.log)} of {count} requests logged"
        time.sleep(0.01)
    return server.log


def parse_stamp(text: str) -> datetime:
    assert len(text) == len("2026-10-18 20:14:26.123"), text  # date, time and milliseconds
    return datetime.fromisoformat(text)


# ----- the existing M2 routes must stay byte-for-byte the same -----


@pytest.mark.parametrize(
    ("path", "size", "digest"),
    [
        ("/dl", MIB, "1f0e3be09c98988ae745875e24e7066766754cd03a00990302b01e49f3a3e712"),
        (
            "/files/sample.zip",
            MIB,
            "b4f2243eeb52627eb31291d1970056d40f185edc108b4908de8d9d710a4c281d",
        ),
        (
            "/files/archive.zip",
            MIB,
            "d077416dd9157053aad0a0efdf998a76caac2c106ffa07fa804b9d50795d57a0",
        ),
        (
            "/stream.bin",
            3 * MIB,
            "405a35ee30d4412eaf8bb29b72697d0c687141fc78f3b52ded04675708b68156",
        ),
    ],
)
def test_m2_payloads_are_unchanged(path, size, digest):
    # These are the hashes the saved IDM files were checked against in OBS-001 to OBS-005.
    assert scenarios.EXPECTED[path] == (size, digest)


def test_cut_payload_is_unchanged():
    digest = "7827d14c6fc119106d8920ed585b21d857ca5c18385b5fda9e7b930a916d4cee"
    assert hashlib.sha256(scenarios.CUT).hexdigest() == digest


# ----- the request log -----


def test_complete_request_is_logged_with_times_and_connection(server):
    response, body, port = get(server, "/files/sample.zip")

    assert response.status == 200
    assert hashlib.sha256(body).hexdigest() == scenarios.EXPECTED["/files/sample.zip"][1]
    [entry] = wait_for_log(server, 1)
    assert entry["method"] == "GET"
    assert entry["path"] == "/files/sample.zip"
    assert entry["status"] == 200
    assert entry["bytes_sent"] == MIB
    assert entry["disconnected"] is False
    assert entry["conn"] == 1
    assert entry["client_port"] == port
    assert entry["headers"] == {"User-Agent": "scenario-test", "Accept-Encoding": "identity"}
    start, end = parse_stamp(entry["start"]), parse_stamp(entry["end"])
    assert start <= end
    assert entry["time"] == entry["end"][11:19]  # the old field: end time, whole seconds
    assert 0 <= entry["duration_s"] < 10


def test_log_file_is_only_appended_to(server, tmp_path):
    log_file = tmp_path / "requests.jsonl"
    old_line = '{"time": "21:19:37", "method": "GET", "path": "/cut.bin", "status": 0}\n'
    log_file.write_text(old_line, encoding="utf-8")

    get(server, "/start", method="HEAD")
    get(server, "/missing.zip")
    wait_for_log(server, 2)  # the client can finish reading before the server logs

    lines = log_file.read_text(encoding="utf-8").splitlines(keepends=True)
    assert lines[0] == old_line
    entries = [json.loads(line) for line in lines[1:]]
    assert entries == server.log
    assert sorted((e["conn"], e["method"], e["status"], e["bytes_sent"]) for e in entries) == [
        (1, "HEAD", 302, 0),
        (2, "GET", 404, len(b"Not Found")),
    ]


def test_parallel_connections_can_be_told_apart(server):
    ports: list[int] = []
    threads = [
        threading.Thread(target=lambda: ports.append(get(server, "/dl?id=7")[2])) for _ in range(3)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    entries = wait_for_log(server, 3)
    assert sorted(e["conn"] for e in entries) == [1, 2, 3]
    assert {e["client_port"] for e in entries} == set(ports)
    assert len(set(ports)) == 3


def test_hang_up_records_the_status_and_bytes_really_sent(server):
    sock = open_raw(server, "/stream.bin")
    head, body = read_body_bytes(sock, 64 * 1024)
    hang_up(sock)

    [entry] = wait_for_log(server, 1)
    assert head.startswith(b"HTTP/1.1 200 ")
    assert entry["disconnected"] is True
    assert entry["status"] == 200  # the status line was sent; the old log said 0
    # At least what the client read; less than the whole stream, because it hung up.
    assert len(body) <= entry["bytes_sent"] < len(scenarios.STREAM)


# ----- the slow unknown-size stream -----


def test_slow_stream_is_3_mib_over_about_90_seconds():
    data = scenarios.SLOW_STREAM
    assert len(data) == 3 * MIB
    assert len(data) / scenarios.SLOW_CHUNK * scenarios.SLOW_DELAY == pytest.approx(90)
    assert scenarios.EXPECTED["/slow-stream.bin"] == (len(data), hashlib.sha256(data).hexdigest())
    assert data != scenarios.STREAM  # a saved file shows which stream it came from


def test_slow_stream_has_no_length_and_starts_with_the_payload(server):
    response, _, _ = get(server, "/slow-stream.bin", method="HEAD")
    assert response.status == 200
    assert response.getheader("Content-Length") is None
    assert response.getheader("Content-Type") == "application/octet-stream"

    sock = open_raw(server, "/slow-stream.bin")
    _, body = read_body_bytes(sock, scenarios.SLOW_CHUNK)
    hang_up(sock)

    assert body[: scenarios.SLOW_CHUNK] == scenarios.SLOW_STREAM[: scenarios.SLOW_CHUNK]
    entry = wait_for_log(server, 2)[1]
    assert entry["path"] == "/slow-stream.bin"
    assert entry["disconnected"] is True
    assert entry["status"] == 200
    assert scenarios.SLOW_CHUNK <= entry["bytes_sent"] < len(scenarios.SLOW_STREAM)
