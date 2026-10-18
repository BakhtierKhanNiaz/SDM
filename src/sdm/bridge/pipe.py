"""The named pipe between the native host and the running SDM app (ADR-0014).

SDM never listens on a network port (security rule 13). The host and the app talk over a
Windows named pipe instead, and both sides must prove they know a per-user secret key
(HMAC challenge-response from `multiprocessing.connection`) before a request is read. The
key lives in %LOCALAPPDATA%\\SDM\\bridge.key, which only this Windows user can read.

Only JSON bytes cross the pipe (`send_bytes`/`recv_bytes`), never pickled objects, because
unpickling runs code. Every request is checked again with `parse_request` on the app side.
"""

import hashlib
import logging
import os
import secrets
import threading
from collections.abc import Callable
from multiprocessing import AuthenticationError
from multiprocessing.connection import (
    Client,
    Connection,
    Listener,
    answer_challenge,
    deliver_challenge,
)
from pathlib import Path

from sdm.bridge.protocol import (
    MAX_MESSAGE_BYTES,
    DownloadRequest,
    ProtocolError,
    decode_json,
    encode_json,
    parse_request,
    request_message,
)
from sdm.core.errors import SDMError
from sdm.core.paths import app_data_dir

log = logging.getLogger(__name__)

KEY_BYTES = 32
# A connection must finish the handshake and its one request within this time, so a client
# that connects and goes silent can't hold a slot for ever.
CONNECTION_SECONDS = 5.0
MAX_CONNECTIONS = 4  # connections handled at the same time; extra ones are closed at once
_PIPE_PREFIX = "\\\\.\\pipe\\sdm-bridge-"
_WAKE_UP = b"stop"  # sent by close() to itself, only to end the accept() wait


class BridgeError(SDMError):
    """The host couldn't hand the request to SDM."""


class NotRunning(BridgeError):
    """No SDM app is listening on the pipe."""


class AlreadyRunning(BridgeError):
    """Another SDM app already owns the pipe."""


def default_key_path() -> Path:
    return app_data_dir() / "bridge.key"


def pipe_address(key_path: Path) -> str:
    """The pipe's name, derived from the key's location so each user (and each test) differs."""
    digest = hashlib.sha256(os.path.abspath(key_path).lower().encode("utf-8")).hexdigest()
    return _PIPE_PREFIX + digest[:16]


def load_or_create_key(path: Path) -> bytes:
    """Read the 32-byte key (stored as hex), creating it with a strong random value if needed."""
    try:
        text = path.read_bytes().decode("ascii").strip()
    except FileNotFoundError:
        return _create_key(path)
    except UnicodeDecodeError:
        text = ""
    try:
        key = bytes.fromhex(text)
    except ValueError:
        key = b""
    if len(key) == KEY_BYTES:
        return key
    log.warning("The bridge key file is damaged; making a new one.")
    key = secrets.token_bytes(KEY_BYTES)
    temporary = path.with_name(path.name + ".new")
    temporary.write_text(key.hex(), encoding="ascii")
    os.replace(temporary, path)
    return key


def _create_key(path: Path) -> bytes:
    path.parent.mkdir(parents=True, exist_ok=True)
    key = secrets.token_bytes(KEY_BYTES)
    try:
        with path.open("x", encoding="ascii") as file:  # "x": fail if it appeared meanwhile
            file.write(key.hex())
    except FileExistsError:  # the app and the host raced to create it: use the winner's key
        return load_or_create_key(path)
    return key


RequestHandler = Callable[[DownloadRequest], bool]


class BridgeListener:
    """Accepts handoffs on the pipe (in the app) and passes valid ones to `on_request`.

    `on_request` runs on a worker thread and returns False when SDM is too busy to take
    the request. The listener owns the pipe: creating a second one raises AlreadyRunning.
    """

    def __init__(self, key: bytes, address: str, on_request: RequestHandler) -> None:
        self.address = address
        self._key = key
        self._on_request = on_request
        try:
            # No authkey here: each connection's handshake runs on its own thread (below), so
            # one silent client can't block the accept loop.
            self._listener = Listener(address, "AF_PIPE")
        except PermissionError:  # FILE_FLAG_FIRST_PIPE_INSTANCE: someone already owns it
            raise AlreadyRunning("Another SDM is already running.") from None
        self._slots = threading.BoundedSemaphore(MAX_CONNECTIONS)
        self._stopping = threading.Event()
        self._thread = threading.Thread(target=self._serve, name="sdm-bridge", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def close(self) -> None:
        if self._stopping.is_set():
            return
        self._stopping.set()
        if self._thread.is_alive():  # it may never have been started (startup failed)
            try:  # accept() can't be interrupted, so connect once to end its wait
                with Client(self.address, "AF_PIPE") as conn:
                    conn.send_bytes(_WAKE_UP)
            except OSError:
                pass
            self._thread.join(timeout=2)
        self._listener.close()

    def _serve(self) -> None:
        while not self._stopping.is_set():
            try:
                conn = self._listener.accept()
            except OSError as exc:
                if self._stopping.is_set():
                    return
                log.warning("The browser bridge couldn't accept a connection: %s", exc)
                self._stopping.wait(0.1)
                continue
            if self._stopping.is_set():
                _close_quietly(conn)
                return
            if not self._slots.acquire(blocking=False):
                log.warning("Too many browser connections at once; one was refused.")
                _close_quietly(conn)
                continue
            threading.Thread(target=self._handle, args=(conn,), daemon=True).start()

    def _handle(self, conn: Connection) -> None:
        watchdog = threading.Timer(CONNECTION_SECONDS, _close_quietly, args=(conn,))
        watchdog.daemon = True
        watchdog.start()
        try:
            deliver_challenge(conn, self._key)
            answer_challenge(conn, self._key)
            data = conn.recv_bytes(MAX_MESSAGE_BYTES)
            try:
                request = parse_request(decode_json(data))
            except ProtocolError as exc:
                log.warning("Refused a browser request: %s", exc)
                reply = {"ok": False, "error": "bad_request"}
            else:
                accepted = self._on_request(request)
                reply = {"ok": True} if accepted else {"ok": False, "error": "busy"}
            conn.send_bytes(encode_json(reply))
        except AuthenticationError:
            if not self._stopping.is_set():
                log.warning("Refused a browser bridge connection: the key didn't match.")
        except (OSError, EOFError):
            pass  # the other side went away, or the watchdog closed a silent connection
        finally:
            watchdog.cancel()
            _close_quietly(conn)
            self._slots.release()


def send_request(
    request: DownloadRequest, *, key: bytes, address: str, timeout: float = 10.0
) -> dict[str, object]:
    """Hand a request to the running app and return its reply, e.g. {"ok": True}."""
    try:
        conn = Client(address, "AF_PIPE", authkey=key)
    except FileNotFoundError:
        raise NotRunning("SDM isn't running.") from None
    except AuthenticationError:
        raise BridgeError("SDM refused the connection: the bridge keys don't match.") from None
    except (OSError, EOFError) as exc:
        raise BridgeError(f"Couldn't connect to SDM: {exc}") from None
    try:
        with conn:
            conn.send_bytes(encode_json(request_message(request.url)))
            if not conn.poll(timeout):
                raise BridgeError("SDM didn't answer in time.")
            reply = decode_json(conn.recv_bytes(MAX_MESSAGE_BYTES))
    except (OSError, EOFError, ProtocolError) as exc:
        raise BridgeError(f"The connection to SDM failed: {exc}") from None
    if not isinstance(reply, dict) or not isinstance(reply.get("ok"), bool):
        raise BridgeError("SDM sent an unexpected reply.")
    return reply


def _close_quietly(conn: Connection) -> None:
    try:
        conn.close()
    except OSError:
        pass
