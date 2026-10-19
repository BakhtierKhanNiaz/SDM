"""SDM's log file and its safety nets (M10).

The window runs without a console, so before M10 its warnings went nowhere. Now they go to
%LOCALAPPDATA%\\SDM\\logs\\sdm.log (rotated at 1 MB, three old files kept). Code already logs
addresses through redact_url; RedactingFilter is a second line of defence that strips query
strings and user names from any http(s) address that still reaches a log line.
"""

import logging
import re
import sys
import threading
from collections.abc import Callable
from logging.handlers import RotatingFileHandler
from pathlib import Path
from types import TracebackType

LOG_NAME = "sdm.log"
MAX_BYTES = 1024 * 1024
BACKUPS = 3
_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
# An http(s) address: optional user info, then everything up to whitespace or a quote.
_URL = re.compile(r"(?i)\b(https?://)(?:[^/\s@'\"<>]*@)?([^\s?#'\"<>]*)(\?[^\s#'\"<>]*)?(#\S*)?")


def redact(text: str) -> str:
    """Remove query strings, fragments and user names from every http(s) address in text."""

    def clean(match: re.Match[str]) -> str:
        query = "?<redacted>" if match.group(3) else ""
        return f"{match.group(1)}{match.group(2)}{query}"

    return _URL.sub(clean, text)


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        cleaned = redact(message)
        if cleaned != message:
            record.msg, record.args = cleaned, None
        if record.exc_info and record.exc_info[1] is not None and not record.exc_text:
            record.exc_text = redact(logging.Formatter().formatException(record.exc_info))
        elif record.exc_text:
            record.exc_text = redact(record.exc_text)
        return True


def setup_logging(folder: Path, *, level: int = logging.INFO) -> Path | None:
    """Log to `folder`/sdm.log (and warnings to stderr). Returns the file, or None if the folder
    can't be used; SDM then still runs, logging to stderr only."""
    root = logging.getLogger()
    root.setLevel(level)
    for handler in list(root.handlers):
        if getattr(handler, "_sdm", False):
            root.removeHandler(handler)
            handler.close()
    console = logging.StreamHandler()
    console.setLevel(logging.WARNING)
    handlers: list[logging.Handler] = [console]
    path: Path | None = folder / LOG_NAME
    try:
        folder.mkdir(parents=True, exist_ok=True)
        handlers.append(
            RotatingFileHandler(path, maxBytes=MAX_BYTES, backupCount=BACKUPS, encoding="utf-8")
        )
    except OSError:
        path = None
    for handler in handlers:
        handler._sdm = True  # type: ignore[attr-defined]  # ours, replaced on the next setup
        handler.setFormatter(logging.Formatter(_FORMAT))
        handler.addFilter(RedactingFilter())
        root.addHandler(handler)
    return path


Notifier = Callable[[str], None]


def install_crash_handlers(notify: Notifier | None = None) -> None:
    """Log any unexpected error with its details, then tell the user (once per error).

    Covers the main thread (including errors inside Qt slots, which PySide6 reports through
    sys.excepthook) and other threads.
    """
    log = logging.getLogger("sdm.crash")

    def report(
        kind: type[BaseException], error: BaseException, trace: TracebackType | None
    ) -> None:
        if issubclass(kind, KeyboardInterrupt):
            sys.__excepthook__(kind, error, trace)
            return
        log.critical("Unexpected error", exc_info=(kind, error, trace))
        if notify is not None:
            try:
                notify(f"{kind.__name__}: {redact(str(error))}"[:300])
            except Exception:  # never let the safety net itself crash
                log.exception("Couldn't show the error message")

    def report_thread(args: threading.ExceptHookArgs) -> None:
        if args.exc_value is not None:
            report(args.exc_type, args.exc_value, args.exc_traceback)

    sys.excepthook = report
    threading.excepthook = report_thread
