"""The named pipe between the host and the app: key, refusals and misbehaving clients (M7)."""

import time
from multiprocessing.connection import Client

import pytest

from sdm.bridge import pipe
from sdm.bridge.pipe import (
    AlreadyRunning,
    BridgeError,
    BridgeListener,
    NotRunning,
    load_or_create_key,
    pipe_address,
    send_request,
)
from sdm.bridge.protocol import DownloadRequest, encode_json

URL = "https://example.com/files/a.zip?token=abc"
REQUEST = DownloadRequest(URL)


def send(bridge, request=REQUEST, key=None):
    return send_request(request, key=key or bridge.key, address=bridge.address, timeout=5)


def test_a_request_with_the_right_key_reaches_the_app(bridge):
    assert send(bridge) == {"ok": True}
    assert bridge.received == [URL]


def test_a_busy_app_says_so(bridge):
    bridge.accept = False
    assert send(bridge) == {"ok": False, "error": "busy"}


def test_the_wrong_key_is_refused_and_the_listener_carries_on(bridge):
    with pytest.raises(BridgeError, match="keys don't match"):
        send(bridge, key=b"x" * 32)
    assert bridge.received == []
    assert send(bridge) == {"ok": True}  # still listening


def test_nothing_listening_means_not_running(tmp_path):
    key_path = tmp_path / "bridge.key"
    started = time.monotonic()
    with pytest.raises(NotRunning):
        send_request(REQUEST, key=load_or_create_key(key_path), address=pipe_address(key_path))
    assert time.monotonic() - started < 2  # found out at once, no long wait


def test_only_one_listener_per_pipe(bridge):
    with pytest.raises(AlreadyRunning):
        BridgeListener(bridge.key, bridge.address, lambda request: True)


def test_after_close_the_pipe_is_gone(tmp_path):
    key_path = tmp_path / "bridge.key"
    key = load_or_create_key(key_path)
    listener = BridgeListener(key, pipe_address(key_path), lambda request: True)
    listener.start()
    started = time.monotonic()
    listener.close()
    assert time.monotonic() - started < 3
    with pytest.raises(NotRunning):
        send_request(REQUEST, key=key, address=pipe_address(key_path))


def test_a_listener_that_never_started_closes_cleanly(tmp_path):
    # SDM closes it without starting it when the history can't be opened.
    key_path = tmp_path / "bridge.key"
    listener = BridgeListener(load_or_create_key(key_path), pipe_address(key_path), print)
    listener.close()
    listener.close()  # twice is harmless
    BridgeListener(b"k" * 32, pipe_address(key_path), print).close()  # the name is free again


def test_a_bad_request_gets_a_generic_error(bridge):
    with Client(bridge.address, "AF_PIPE", authkey=bridge.key) as conn:
        conn.send_bytes(encode_json({"version": 1, "type": "download", "url": "file:///C:/x"}))
        assert conn.poll(5)
        assert conn.recv_bytes() == b'{"ok":false,"error":"bad_request"}'
    assert bridge.received == []


def test_pickled_objects_are_never_unpickled(bridge):
    with Client(bridge.address, "AF_PIPE", authkey=bridge.key) as conn:
        conn.send(REQUEST)  # send() pickles; the listener must treat it as bad JSON
        assert conn.poll(5)
        assert conn.recv_bytes() == b'{"ok":false,"error":"bad_request"}'


def test_an_oversized_message_is_dropped(bridge):
    with Client(bridge.address, "AF_PIPE", authkey=bridge.key) as conn:
        with pytest.raises((EOFError, OSError)):  # the listener hangs up, mid-send or after
            conn.send_bytes(b" " * (70 * 1024))
            conn.poll(5)
            conn.recv_bytes()
    assert send(bridge) == {"ok": True}


def test_a_client_that_drops_the_connection_does_no_harm(bridge):
    Client(bridge.address, "AF_PIPE", authkey=bridge.key).close()  # connects, then leaves
    Client(bridge.address, "AF_PIPE").close()  # leaves during the handshake
    assert send(bridge) == {"ok": True}


def test_a_silent_client_doesnt_block_others(bridge):
    silent = Client(bridge.address, "AF_PIPE")  # connects, never answers the challenge
    try:
        assert send(bridge) == {"ok": True}
    finally:
        silent.close()


def test_a_silent_client_is_cut_off(monkeypatch, tmp_path):
    monkeypatch.setattr(pipe, "CONNECTION_SECONDS", 0.5)
    monkeypatch.setattr(pipe, "MAX_CONNECTIONS", 1)
    key_path = tmp_path / "bridge.key"
    key = load_or_create_key(key_path)
    listener = BridgeListener(key, pipe_address(key_path), lambda request: True)
    listener.start()
    try:
        silent = Client(pipe_address(key_path), "AF_PIPE")
        time.sleep(1.0)  # the watchdog closes it and frees the only slot
        assert send_request(REQUEST, key=key, address=pipe_address(key_path)) == {"ok": True}
        silent.close()
    finally:
        listener.close()


def test_the_key_is_created_once_and_reused(tmp_path):
    key_path = tmp_path / "SDM" / "bridge.key"
    key = load_or_create_key(key_path)
    assert len(key) == 32
    assert len(key_path.read_text(encoding="ascii")) == 64  # hex
    assert load_or_create_key(key_path) == key


@pytest.mark.parametrize("content", [b"", b"abc", b"zz" * 32, b"\xff" * 64, b"00" * 16])
def test_a_damaged_key_is_replaced(tmp_path, content):
    key_path = tmp_path / "bridge.key"
    key_path.write_bytes(content)
    key = load_or_create_key(key_path)
    assert len(key) == 32
    assert load_or_create_key(key_path) == key


def test_each_key_location_has_its_own_pipe(tmp_path):
    a = pipe_address(tmp_path / "a" / "bridge.key")
    assert a.startswith("\\\\.\\pipe\\sdm-bridge-")
    assert a == pipe_address(tmp_path / "a" / "bridge.key")
    assert a != pipe_address(tmp_path / "b" / "bridge.key")
