"""SDM's log file, its redaction, the crash safety net and the Help menu (M10)."""

import logging
import sys
import threading

import pytest

from sdm.core import logs
from sdm.core.logs import (
    BACKUPS,
    MAX_BYTES,
    install_crash_handlers,
    redact,
    setup_logging,
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("got https://cdn.example.com/a.zip?token=s3cret now",
         "got https://cdn.example.com/a.zip?<redacted> now"),
        ("http://user:pass@example.com/x", "http://example.com/x"),
        ("see https://example.com/p#frag", "see https://example.com/p"),
        ("'https://a.example/b?c=d'", "'https://a.example/b?<redacted>'"),
        ("no address here", "no address here"),
        ("two: http://a/x?1 and https://b/y?2",
         "two: http://a/x?<redacted> and https://b/y?<redacted>"),
    ],
)  # fmt: skip
def test_redact(text, expected):
    assert redact(text) == expected


@pytest.fixture
def logged(tmp_path):
    path = setup_logging(tmp_path / "logs")
    yield path
    root = logging.getLogger()
    for handler in list(root.handlers):
        if getattr(handler, "_sdm", False):
            root.removeHandler(handler)
            handler.close()


def test_the_log_file_rotates_and_hides_secrets(logged):
    assert logged is not None and logged.name == "sdm.log"
    from logging.handlers import RotatingFileHandler

    ours = [h for h in logging.getLogger().handlers if getattr(h, "_sdm", False)]
    (file_handler,) = [h for h in ours if isinstance(h, RotatingFileHandler)]
    assert (file_handler.maxBytes, file_handler.backupCount) == (MAX_BYTES, BACKUPS)
    log = logging.getLogger("sdm.test")
    log.info("Downloading %s", "https://example.com/a.zip?token=s3cret")
    try:
        raise ValueError("bad https://example.com/b?key=t0ken")
    except ValueError:
        log.exception("Failed")
    text = logged.read_text(encoding="utf-8")
    assert "Downloading https://example.com/a.zip?<redacted>" in text
    assert "s3cret" not in text and "t0ken" not in text
    assert "Traceback" in text  # details are kept, secrets aren't


def test_an_unusable_log_folder_doesnt_stop_sdm(tmp_path):
    blocker = tmp_path / "not-a-folder"
    blocker.write_text("x", encoding="utf-8")
    try:
        assert setup_logging(blocker / "logs") is None
    finally:
        root = logging.getLogger()
        for handler in list(root.handlers):
            if getattr(handler, "_sdm", False):
                root.removeHandler(handler)
                handler.close()


@pytest.fixture
def hooks(monkeypatch):
    monkeypatch.setattr(sys, "excepthook", sys.excepthook)
    monkeypatch.setattr(threading, "excepthook", threading.excepthook)
    shown = []
    install_crash_handlers(shown.append)
    return shown


def test_an_unexpected_error_is_logged_and_shown(hooks, caplog):
    try:
        raise RuntimeError("boom at https://example.com/x?token=s3cret")
    except RuntimeError:
        sys.excepthook(*sys.exc_info())
    assert hooks == ["RuntimeError: boom at https://example.com/x?<redacted>"]
    assert any(r.levelno == logging.CRITICAL for r in caplog.records)


def test_an_error_on_another_thread_is_caught_too(hooks):
    thread = threading.Thread(target=lambda: 1 / 0)
    thread.start()
    thread.join()
    assert hooks == ["ZeroDivisionError: division by zero"]


def test_ctrl_c_is_not_reported_as_a_crash(hooks, monkeypatch):
    passed = []
    monkeypatch.setattr(sys, "__excepthook__", lambda *args: passed.append(args[0]))
    sys.excepthook(KeyboardInterrupt, KeyboardInterrupt(), None)
    assert hooks == [] and passed == [KeyboardInterrupt]


def test_the_crash_dialog_appears_at_most_three_times(qtbot, monkeypatch):
    from sdm import app as app_module

    shown = []
    monkeypatch.setattr(app_module.QMessageBox, "critical", lambda *args: shown.append(args[2]))
    reporter = app_module.CrashReporter()
    for number in range(5):
        reporter.raised.emit(f"Error {number}")
    assert len(shown) == 3 and "Help > Open log folder" in shown[0]


def test_help_menu(qtbot, make_controller, tmp_path, monkeypatch):
    from sdm import __version__
    from sdm.ui import main_window
    from sdm.ui.main_window import MainWindow, about_text

    opened, abouts = [], []
    monkeypatch.setattr(main_window, "open_folder", opened.append)
    monkeypatch.setattr(main_window.QMessageBox, "about", lambda *args: abouts.append(args[2]))
    window = MainWindow(make_controller(start=False), default_folder=tmp_path)
    qtbot.addWidget(window)
    window.open_logs_action.trigger()
    window.about_action.trigger()
    assert opened == [main_window.log_folder()]
    assert abouts == [about_text()] and __version__ in abouts[0]
    assert "LGPL" in abouts[0]


def test_logs_module_imports_nothing_from_the_rest_of_sdm():
    # sdm.core may not import other SDM packages (architecture rule).
    source = logs.__file__
    with open(source, encoding="utf-8") as file:
        assert "from sdm." not in file.read()
