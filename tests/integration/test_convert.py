"""The Convert window and its menu entries (M12a), with a fake ffmpeg (tests/fakes)."""

import json
import sys
from pathlib import Path

import pytest

from sdm.core.downloads import BrowserContext
from sdm.ui.convert_dialog import ConvertDialog
from sdm.ui.main_window import MainWindow

FAKE_FFMPEG = [sys.executable, str(Path(__file__).parent.parent / "fakes" / "fake_ffmpeg.py")]


@pytest.fixture
def source(tmp_path):
    path = tmp_path / "song.webm"
    path.write_bytes(b"media")
    return path


def make_dialog(qtbot, source, *, ffmpeg=FAKE_FFMPEG, fmt="mp3"):
    dialog = ConvertDialog(ffmpeg=ffmpeg, source=source)
    qtbot.addWidget(dialog)
    dialog.format_box.setCurrentIndex(dialog.format_box.findData(fmt))
    return dialog


def test_converting_makes_a_new_file_and_keeps_the_original(qtbot, tmp_path, source, monkeypatch):
    log = tmp_path / "args.json"
    monkeypatch.setenv("FAKE_FFMPEG_LOG", str(log))
    dialog = make_dialog(qtbot, source)
    assert dialog.start()
    qtbot.waitUntil(lambda: not dialog.running, timeout=15000)
    assert dialog.result == tmp_path / "song.mp3"
    assert dialog.result.read_bytes() == b"converted:media"
    assert source.read_bytes() == b"media"
    assert dialog.status_label.text() == "Done: song.mp3"
    assert dialog.bar.value() == 100
    assert not dialog.show_button.isHidden()
    args = json.loads(log.read_text(encoding="utf-8"))
    assert args[args.index("-i") + 1] == f"file:{source.resolve()}"
    assert "-n" in args and "-nostdin" in args
    with qtbot.waitSignal(dialog.show_requested) as shown:
        dialog.show_button.click()
    assert shown.args == [tmp_path / "song.mp3"]


def test_a_second_conversion_gets_a_numbered_name(qtbot, tmp_path, source):
    (tmp_path / "song.mp3").write_bytes(b"earlier")
    dialog = make_dialog(qtbot, source)
    assert dialog.start()
    qtbot.waitUntil(lambda: not dialog.running, timeout=15000)
    assert dialog.result == tmp_path / "song (1).mp3"
    assert (tmp_path / "song.mp3").read_bytes() == b"earlier"


def test_a_failure_shows_ffmpegs_reason_and_deletes_the_partial_file(
    qtbot, tmp_path, source, monkeypatch
):
    monkeypatch.setenv("FAKE_FFMPEG_MODE", "fail")
    dialog = make_dialog(qtbot, source)
    assert dialog.start()
    qtbot.waitUntil(lambda: not dialog.running, timeout=15000)
    assert dialog.result is None
    assert not (tmp_path / "song.mp3").exists()
    assert "matches no streams" in dialog.status_label.text()
    assert dialog.convert_button.isEnabled()


def test_cancel_stops_ffmpeg_and_deletes_the_partial_file(qtbot, tmp_path, source, monkeypatch):
    monkeypatch.setenv("FAKE_FFMPEG_MODE", "slow")
    dialog = make_dialog(qtbot, source)
    assert dialog.start()
    qtbot.waitUntil(lambda: dialog.bar.value() == 50, timeout=15000)  # 5 s of 10 s
    assert (tmp_path / "song.mp3").exists()
    assert dialog.close_button.text() == "Cancel"
    dialog.close_button.click()
    assert not dialog.running
    assert not (tmp_path / "song.mp3").exists()
    assert dialog.status_label.text().startswith("Cancelled")


def test_without_ffmpeg_the_window_says_how_to_get_it(qtbot, source):
    dialog = make_dialog(qtbot, source, ffmpeg=None)
    assert not dialog.convert_button.isEnabled()
    assert "winget install Gyan.FFmpeg" in dialog.status_label.text()
    assert dialog.start() is False


def test_a_missing_file_is_refused(qtbot, tmp_path):
    dialog = make_dialog(qtbot, tmp_path / "gone.webm")
    assert dialog.start() is False
    assert dialog.status_label.text() == "Choose a file that exists."


def test_a_program_that_cant_start_is_reported(qtbot, tmp_path, source):
    dialog = make_dialog(qtbot, source, ffmpeg=[str(tmp_path / "no-ffmpeg.exe")])
    assert dialog.start()
    qtbot.waitUntil(lambda: not dialog.running, timeout=15000)
    assert "couldn't be started" in dialog.status_label.text()


@pytest.fixture
def window(qtbot, make_controller, tmp_path):
    window = MainWindow(make_controller(start=False), default_folder=tmp_path)
    window.confirm_quit = lambda active: True
    qtbot.addWidget(window)
    window.show()
    return window


def test_convert_is_offered_for_finished_files(window, tmp_path, source, monkeypatch):
    store = window.controller.store
    entry = store.add("https://example.com/song.webm", str(tmp_path),
                      context=BrowserContext(None, None))  # fmt: skip
    window.controller.model.set_records(store.list_all())
    window.download_table.selectRow(0)
    assert not window.convert_selected_action.isEnabled()  # not downloaded yet
    store.mark_downloading(entry.id)
    store.mark_completed(entry.id, path=str(source), size=5, verified_complete=True)
    store.set_file_info(entry.id, "song.webm", 5)
    window.controller.model.set_records(store.list_all())
    window.download_table.selectRow(0)
    assert window.convert_selected_action.isEnabled()
    assert window.convert_selected_action in window.context_menu().actions()

    monkeypatch.setattr("sdm.ui.main_window.find_ffmpeg", lambda configured: None)
    window.convert_selected()
    dialog = window.convert_dialog
    assert dialog is not None and dialog.source_edit.text() == str(source)
    assert not dialog.convert_button.isEnabled()  # no ffmpeg here
    dialog.reject()


def test_settings_show_and_keep_where_ffmpeg_is(qtbot, tmp_path):
    from sdm.ui.preferences import Preferences
    from sdm.ui.settings_dialog import SettingsDialog

    fake = tmp_path / "ffmpeg.exe"
    fake.write_bytes(b"MZ")
    dialog = SettingsDialog(Preferences(), tray_available=False)
    qtbot.addWidget(dialog)
    dialog.ffmpeg_edit.setText(str(tmp_path / "missing.exe"))
    assert "wasn't found" in dialog.ffmpeg_status.text()
    dialog.accept()
    assert dialog.result() != dialog.DialogCode.Accepted  # a wrong path isn't saved
    assert "no program" in dialog.error_label.text()
    dialog.ffmpeg_edit.setText(str(fake))
    assert dialog.ffmpeg_status.text() == f"Using {fake}"
    dialog.accept()
    assert dialog.result() == dialog.DialogCode.Accepted
    assert dialog.preferences().ffmpeg_path == str(fake)


def test_tools_menu_opens_an_empty_converter(window, monkeypatch, tmp_path):
    fake = tmp_path / "ffmpeg.exe"
    fake.write_bytes(b"MZ")
    monkeypatch.setattr("sdm.ui.main_window.find_ffmpeg", lambda configured: fake)
    window.convert_action.trigger()
    dialog = window.convert_dialog
    assert dialog.source_edit.text() == ""
    assert dialog.convert_button.isEnabled()
    dialog.reject()
