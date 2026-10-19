"""The native messaging host: in-process with a fake launcher, and as a real process (M7)."""

import io
import os
import struct
import subprocess
import sys

from sdm.bridge.host import handle, run
from sdm.bridge.pipe import BridgeListener, load_or_create_key, pipe_address
from sdm.bridge.protocol import encode_json, read_message, request_message

ORIGIN = "chrome-extension://" + "a" * 32 + "/"
SECRET = "token=s3cr3t-value"  # noqa: S105 - a fake token, to check logs never show it
URL = f"https://example.com/files/a.zip?{SECRET}"


def framed(value) -> bytes:
    body = encode_json(value)
    return struct.pack("<I", len(body)) + body


def stdin_for(url=URL) -> io.BytesIO:
    return io.BytesIO(framed(request_message(url)))


def never_launch():
    raise AssertionError("SDM is running; the host must not start another one")


def test_hands_the_link_to_the_running_app(bridge):
    stdout = io.BytesIO()
    code = run([ORIGIN, "--parent-window=0"], stdin_for(), stdout, key_path=bridge.key_path,
               launch=never_launch)  # fmt: skip
    assert code == 0
    stdout.seek(0)
    assert read_message(stdout) == {"ok": True}
    assert stdout.read() == b""  # one reply and nothing else
    assert bridge.received == [URL]


def test_refuses_a_caller_that_isnt_a_chrome_extension(bridge):
    for args in ([], ["https://evil.example/"], ["chrome-extension://short/"]):
        reply = handle(args, stdin_for(), key_path=bridge.key_path, launch=never_launch)
        assert reply == {"ok": False, "error": "bad_origin"}
    assert bridge.received == []


def test_refuses_a_bad_message(bridge):
    stdin = io.BytesIO(framed({"version": 1, "type": "download", "url": URL, "folder": "C:\\"}))
    reply = handle([ORIGIN], stdin, key_path=bridge.key_path, launch=never_launch)
    assert reply == {"ok": False, "error": "bad_request"}
    assert bridge.received == []


def test_starts_sdm_when_it_isnt_running_and_waits_for_it(tmp_path):
    key_path = tmp_path / "SDM" / "bridge.key"
    received, listeners = [], []

    def launch():  # stands in for starting sdm.exe: the "app" opens its pipe a little later
        listeners.append(None)

    def sleep(seconds):
        if listeners == [None]:
            listener = BridgeListener(
                load_or_create_key(key_path), pipe_address(key_path),
                lambda request: received.append(request.url) or True,
            )  # fmt: skip
            listener.start()
            listeners[0] = listener

    try:
        reply = handle([ORIGIN], stdin_for(), key_path=key_path, launch=launch, sleep=sleep)
    finally:
        for listener in listeners:
            if listener is not None:
                listener.close()
    assert reply == {"ok": True}
    assert received == [URL]


def test_gives_up_if_sdm_never_starts(tmp_path):
    now = [0.0]
    launched = []

    def sleep(seconds):
        now[0] += seconds

    reply = handle([ORIGIN], stdin_for(), key_path=tmp_path / "bridge.key",
                   launch=lambda: launched.append(1), wait=15, clock=lambda: now[0],
                   sleep=sleep)  # fmt: skip
    assert reply == {"ok": False, "error": "not_running"}
    assert launched == [1]
    assert now[0] >= 15


def test_a_launch_failure_is_reported(tmp_path):
    def launch():
        raise OSError("sdm.exe wasn't found")

    reply = handle([ORIGIN], stdin_for(), key_path=tmp_path / "bridge.key", launch=launch)
    assert reply == {"ok": False, "error": "not_running"}


def run_host_process(tmp_path, stdin: bytes, args=(ORIGIN, "--parent-window=0")):
    env = dict(os.environ, LOCALAPPDATA=str(tmp_path))
    return subprocess.run(  # noqa: S603 - our own module with fixed arguments
        [sys.executable, "-P", "-m", "sdm.bridge.host", *args],
        input=stdin, capture_output=True, env=env, timeout=30, cwd=tmp_path,
    )  # fmt: skip


def test_the_host_process_end_to_end(tmp_path):
    key_path = tmp_path / "SDM" / "bridge.key"  # where the host finds it with this LOCALAPPDATA
    received = []
    listener = BridgeListener(load_or_create_key(key_path), pipe_address(key_path),
                              lambda request: received.append(request.url) or True)  # fmt: skip
    listener.start()
    try:
        result = run_host_process(tmp_path, framed(request_message(URL)))
    finally:
        listener.close()
    assert result.returncode == 0, result.stderr
    assert result.stdout == framed({"ok": True})
    assert received == [URL]


def test_the_host_process_refuses_garbage_without_leaking_it(tmp_path):
    hostile = framed({"version": 1, "type": "download", "url": URL, "path": "C:\\"})
    result = run_host_process(tmp_path, hostile)
    assert result.returncode == 1
    assert result.stdout == framed({"ok": False, "error": "bad_request"})
    assert SECRET.encode() not in result.stderr  # logs never contain the link
    assert b"Refused a request" in result.stderr


def test_the_host_process_survives_an_empty_stdin(tmp_path):
    result = run_host_process(tmp_path, b"")
    assert result.returncode == 1
    assert result.stdout == framed({"ok": False, "error": "bad_request"})


def test_a_version_2_message_reaches_the_app_with_all_its_hints(bridge):
    from sdm.bridge.protocol import DownloadRequest

    sent = DownloadRequest(URL, "https://example.com/page", "a.zip", 1234, "application/zip",
                           "capture")  # fmt: skip
    stdout = io.BytesIO()
    code = run([ORIGIN], io.BytesIO(framed(sent.to_message())), stdout,
               key_path=bridge.key_path, launch=never_launch)  # fmt: skip
    assert code == 0
    assert bridge.requests == [sent]
