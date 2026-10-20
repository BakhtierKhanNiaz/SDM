"""The native messaging host that Chrome starts for each "Download with SDM" click.

It reads one request from stdin, hands it to the running SDM app over the pipe (starting
SDM first if it isn't running), writes one reply to stdout and exits. stdout is the protocol
channel, so nothing else may ever be printed to it. Log lines go to stderr, which only
Chrome's debug log shows; they never contain the URL.

Replies are {"ok": true} or {"ok": false, "error": <code>}, where code is one of ERRORS:
generic on purpose, so nothing about this computer leaks back to the browser.
"""

import ctypes
import logging
import os
import re
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import BinaryIO

from sdm.bridge.pipe import (
    BridgeError,
    NotRunning,
    default_key_path,
    load_or_create_key,
    pipe_address,
    send_request,
)
from sdm.bridge.protocol import (
    DownloadRequest,
    ProtocolError,
    parse_request,
    read_message,
    write_message,
)

log = logging.getLogger("sdm.bridge.host")

ERRORS = frozenset({"bad_origin", "bad_request", "busy", "not_running", "failed"})
START_WAIT_SECONDS = 15.0  # how long to wait for a freshly started SDM to open the pipe
_ORIGIN = re.compile(r"chrome-extension://[a-p]{32}/")
FROM_BROWSER_FLAG = "--from-browser"  # tells a second SDM started by us to exit quietly


def run(
    args: list[str],
    stdin: BinaryIO,
    stdout: BinaryIO,
    *,
    key_path: Path,
    launch: Callable[[], None],
    wait: float = START_WAIT_SECONDS,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> int:
    """Handle one request and write the reply; returns the process exit code."""
    reply = handle(args, stdin, key_path=key_path, launch=launch, wait=wait, clock=clock,
                   sleep=sleep)  # fmt: skip
    write_message(stdout, reply)
    return 0 if reply["ok"] else 1


def handle(
    args: list[str],
    stdin: BinaryIO,
    *,
    key_path: Path,
    launch: Callable[[], None],
    wait: float = START_WAIT_SECONDS,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, object]:
    # Chrome passes the calling extension's origin first. Chrome already checks it against
    # allowed_origins; checking its shape here also refuses a host started some other way.
    if not args or not _ORIGIN.fullmatch(args[0]):
        log.warning("Refused: not started by a Chrome extension.")
        return _error("bad_origin")
    try:
        request = parse_request(read_message(stdin))
    except ProtocolError as exc:
        log.warning("Refused a request: %s", exc)
        return _error("bad_request")

    key = load_or_create_key(key_path)
    address = pipe_address(key_path)
    _allow_sdm_to_come_forward()
    try:
        return _pass_on(request, key, address)
    except NotRunning:
        pass
    except BridgeError as exc:
        log.warning("%s", exc)
        return _error("failed")

    try:
        launch()
    except OSError as exc:
        log.warning("Couldn't start SDM: %s", exc)
        return _error("not_running")
    deadline = clock() + wait
    while clock() < deadline:
        sleep(0.25)
        try:
            return _pass_on(request, key, address)
        except NotRunning:
            continue
        except BridgeError as exc:
            log.warning("%s", exc)
            return _error("failed")
    log.warning("SDM didn't start within %.0f seconds.", wait)
    return _error("not_running")


def _pass_on(request: DownloadRequest, key: bytes, address: str) -> dict[str, object]:
    reply = send_request(request, key=key, address=address)
    if reply.get("ok") is True:
        return {"ok": True}
    code = reply.get("error")
    log.warning("SDM declined the request: %s", code if isinstance(code, str) else "no reason")
    return _error(code if isinstance(code, str) and code in ERRORS else "failed")


def _error(code: str) -> dict[str, object]:
    return {"ok": False, "error": code}


def launch_sdm() -> None:
    """Start the SDM window (the sdm.exe that uv installed next to this Python), detached."""
    exe = Path(sys.executable).with_name("sdm.exe")
    if not exe.is_file():
        raise OSError(f"{exe.name} wasn't found next to Python; run 'uv sync' in the project.")
    base = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    # Leave Chrome's job object if allowed, so closing Chrome doesn't close SDM; stdio is not
    # inherited, so Chrome isn't left waiting on SDM's copies of the host's pipes.
    for flags in (base | subprocess.CREATE_BREAKAWAY_FROM_JOB, base):
        try:
            subprocess.Popen(  # noqa: S603 - a fixed program and argument, nothing from the browser
                [str(exe), FROM_BROWSER_FLAG],
                creationflags=flags,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True,
                cwd=exe.parent,
            )
            return
        except PermissionError:  # the job doesn't allow leaving it: start SDM inside it
            continue
    raise OSError("Windows refused to start SDM.")


def _allow_sdm_to_come_forward() -> None:
    """Let the SDM window take the focus when it shows the Add URL dialog (best effort).

    Windows only lets a process bring a window to the front if the foreground process allows
    it; this host was started by Chrome, which the user just clicked.
    """
    try:
        ctypes.windll.user32.AllowSetForegroundWindow(-1)  # ASFW_ANY
    except (AttributeError, OSError):
        pass


def _log_to_file() -> None:
    """Also keep warnings in %LOCALAPPDATA%\\SDM\\logs\\bridge-host.log (M10).

    Chrome shows a host's stderr only in its own hidden log, which made handoff problems hard
    to diagnose. A separate file from the app's sdm.log: two processes must not rotate one file.
    """
    from logging.handlers import RotatingFileHandler

    from sdm.core.logs import RedactingFilter
    from sdm.core.paths import app_data_dir

    try:
        folder = app_data_dir() / "logs"
        folder.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            folder / "bridge-host.log", maxBytes=256 * 1024, backupCount=1, encoding="utf-8"
        )
    except OSError:
        return
    handler.setLevel(logging.WARNING)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    handler.addFilter(RedactingFilter())
    logging.getLogger().addHandler(handler)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.WARNING, format="sdm-bridge: %(levelname)s: %(message)s", stream=sys.stderr
    )
    _log_to_file()
    if sys.platform == "win32":  # make sure no newline translation touches the frames
        import msvcrt

        msvcrt.setmode(sys.stdin.fileno(), os.O_BINARY)
        msvcrt.setmode(sys.stdout.fileno(), os.O_BINARY)
    args = sys.argv[1:] if argv is None else argv
    return run(args, sys.stdin.buffer, sys.stdout.buffer, key_path=default_key_path(),
               launch=launch_sdm)  # fmt: skip


if __name__ == "__main__":
    raise SystemExit(main())
