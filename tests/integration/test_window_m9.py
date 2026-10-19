"""The window's M9 features: Settings, checksum box, list menu, Show in folder, notifications,
the tray option, and the remembered layout and folder."""

from dataclasses import replace

import pytest
from PySide6.QtWidgets import QApplication, QDialog, QSystemTrayIcon

from sdm.core.checksums import MISMATCH, VERIFIED
from sdm.core.downloads import DownloadState
from sdm.ui import main_window as main_window_module
from sdm.ui.add_url_dialog import AddUrlDialog
from sdm.ui.controller import summarize
from sdm.ui.main_window import MainWindow
from sdm.ui.preferences import Preferences
from sdm.ui.settings_dialog import SettingsDialog

GOOD = "d297e5ff019966817ad8502465176139f2d3d840fa4ed84b13bed399a6ab1f15"


@pytest.fixture
def controller(make_controller):
    return make_controller(start=False)


@pytest.fixture
def window(qtbot, controller, tmp_path):
    window = MainWindow(controller, default_folder=tmp_path)
    window.confirm_quit = lambda active: True
    qtbot.addWidget(window)
    window.show()
    return window


@pytest.fixture
def revealed(monkeypatch):
    calls = []
    monkeypatch.setattr(main_window_module, "reveal_in_explorer", calls.append)
    return calls


def completed_entry(controller, folder, name="a.zip"):
    path = folder / name
    path.write_bytes(b"data")
    record = controller.store.add(f"https://example.com/{name}?t=1", str(folder))
    controller.store.mark_downloading(record.id)
    controller.store.mark_completed(record.id, path=str(path), size=4, verified_complete=True)
    controller.model.set_records(controller.store.list_all())
    return controller.store.get(record.id)


# ----- Settings -----


def test_settings_dialog_round_trip(qtbot, tmp_path):
    chosen = Preferences(speed_limit_kib=300, connections=3, default_folder=str(tmp_path),
                         remember_last_folder=False, keep_in_tray=True, notify=False)  # fmt: skip
    dialog = SettingsDialog(chosen, tray_available=True)
    qtbot.addWidget(dialog)
    assert dialog.preferences() == chosen
    dialog.limit_check.setChecked(False)
    dialog.connections_spin.setValue(8)
    assert dialog.preferences() == replace(chosen, speed_limit_kib=0, connections=8)


def test_settings_dialog_refuses_a_missing_folder(qtbot, tmp_path):
    dialog = SettingsDialog(Preferences(), tray_available=True)
    qtbot.addWidget(dialog)
    dialog.folder_edit.setText(str(tmp_path / "nope"))
    dialog.accept()
    assert dialog.result() != QDialog.DialogCode.Accepted
    assert "doesn't exist" in dialog.error_label.text()


def test_without_a_tray_its_options_are_off_limits(qtbot):
    dialog = SettingsDialog(Preferences(), tray_available=False)
    qtbot.addWidget(dialog)
    assert not dialog.tray_check.isEnabled()


def test_applying_settings_saves_them(window, controller, tmp_path):
    window.apply_preferences(Preferences(speed_limit_kib=256, connections=2,
                                         default_folder=str(tmp_path)))  # fmt: skip
    assert controller.preferences.speed_limit_kib == 256
    from sdm.ui.preferences import load_preferences

    assert load_preferences(controller.store).connections == 2


# ----- Add URL's checksum box -----


def test_add_url_checks_the_sha256_box(qtbot, tmp_path):
    dialog = AddUrlDialog(default_folder=tmp_path, previous_downloads=lambda url: [])
    qtbot.addWidget(dialog)
    dialog.url_edit.setText("https://example.com/a.zip")
    dialog.sha256_edit.setText("not a checksum")
    dialog.accept()
    assert dialog.result() != QDialog.DialogCode.Accepted
    assert "64 characters" in dialog.error_label.text()
    dialog.sha256_edit.setText(GOOD[:32] + "\n" + GOOD[32:].upper())  # as python.org prints it
    dialog.accept()
    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.expected_sha256 == GOOD


def test_the_checksum_reaches_the_history(window, controller, tmp_path):
    window.add_download("https://example.com/a.zip", tmp_path, start=False, expected_sha256=GOOD)
    (record,) = controller.store.list_all()
    assert record.expected_sha256 == GOOD


# ----- the list's menu, Show in folder, Copy address, Verify -----


def test_the_right_click_menu(window, controller, tmp_path):
    completed_entry(controller, tmp_path)
    window.download_table.selectRow(0)
    texts = [a.text() for a in window.context_menu().actions() if not a.isSeparator()]
    assert texts[:4] == ["&Pause", "R&esume", "&Start now", "&Cancel download"]
    assert {"Show in &folder", "Copy &address", "&Verify checksum…", "&Remove from list"} <= set(
        texts
    )
    assert "Open" not in " ".join(texts)  # SDM never opens (runs) a downloaded file


def test_show_in_folder_only_for_sdms_own_finished_file(window, controller, tmp_path, revealed):
    record = completed_entry(controller, tmp_path)
    window.select_id(record.id)
    assert window.show_in_folder_action.isEnabled()
    window.show_in_folder_selected()
    assert revealed == [tmp_path / "a.zip"]

    # A history entry pointing outside its folder (tampered) is never shown.
    controller.store._update(record.id, path=str(tmp_path.parent / "elsewhere.zip"))
    controller.model.set_records(controller.store.list_all())
    window.select_id(record.id)
    window.show_in_folder_selected()
    assert revealed == [tmp_path / "a.zip"]
    assert not window.show_in_folder_action.isEnabled()


def test_double_click_shows_a_finished_file(qtbot, window, controller, tmp_path, revealed):
    completed_entry(controller, tmp_path)
    window.download_table.selectRow(0)
    window.download_table.doubleClicked.emit(window.proxy.index(0, 0))
    assert revealed == [tmp_path / "a.zip"]


def test_copy_address(window, controller, tmp_path):
    completed_entry(controller, tmp_path)
    window.download_table.selectRow(0)
    window.copy_address_selected()
    assert QApplication.clipboard().text() == "https://example.com/a.zip?t=1"


def test_verify_from_the_window(qtbot, window, controller, tmp_path, monkeypatch):
    record = completed_entry(controller, tmp_path)
    window.select_id(record.id)
    warnings = []
    monkeypatch.setattr(main_window_module.QMessageBox, "warning",
                        lambda *args: warnings.append(args[1:3]))  # fmt: skip
    window.verify_selected("nonsense")
    assert warnings and warnings[0][0] == "Not a SHA-256"
    import hashlib

    window.verify_selected(hashlib.sha256(b"data").hexdigest())
    qtbot.waitUntil(lambda: controller.store.get(record.id).checksum_state == VERIFIED,
                    timeout=5_000)  # fmt: skip


# ----- notifications -----


def test_notifications_follow_the_downloads(window, controller, tmp_path):
    record = completed_entry(controller, tmp_path)
    controller.download_finished.emit(record.id)
    controller.download_failed.emit(record.id, "The file was not found on the server (404).")
    controller.checksum_checked.emit(record.id, MISMATCH)
    assert [title for title, _ in window.notifications] == [
        "Download complete",
        "Download failed",
        "Checksum doesn't match",
    ]
    assert "a.zip" in window.notifications[0][1]


def test_with_a_checksum_the_notification_waits_for_the_check(window, controller, tmp_path):
    record = completed_entry(controller, tmp_path)
    controller.store.set_checksum(record.id, GOOD, None)
    controller.download_finished.emit(record.id)
    assert window.notifications == []
    controller.checksum_checked.emit(record.id, VERIFIED)
    assert window.notifications[0][0] == "Download complete and verified"


def test_notifications_can_be_switched_off(window, controller, tmp_path):
    record = completed_entry(controller, tmp_path)
    controller.set_preferences(Preferences(notify=False))
    controller.download_finished.emit(record.id)
    assert window.notifications == []


def test_status_bar_shows_the_total_speed():
    from sdm.core.downloads import DownloadRecord

    running = DownloadRecord(1, "https://e/a", "D:\\", False, DownloadState.DOWNLOADING, "a", None,
                             10, 5, None, None, "t", "t", None)  # fmt: skip
    assert summarize([running], 1_500_000) == "1 downloading · 0 completed · 1.4 MB/s"
    assert summarize([running]) == "1 downloading · 0 completed"


# ----- the tray option, quitting, layout -----


@pytest.fixture
def tray_window(qtbot, controller, tmp_path, monkeypatch):
    monkeypatch.setattr(QSystemTrayIcon, "isSystemTrayAvailable", staticmethod(lambda: True))
    window = MainWindow(controller, default_folder=tmp_path)
    window.confirm_quit = lambda active: True
    qtbot.addWidget(window)
    window.show()
    return window


def test_closing_hides_to_the_tray_when_chosen(qtbot, tray_window, controller):
    controller.set_preferences(Preferences(keep_in_tray=True))
    quits = []
    tray_window.quit_confirmed.connect(lambda: quits.append(1))
    tray_window.close()
    assert tray_window.isHidden()
    assert quits == []  # still running
    assert tray_window.notifications[-1][0] == "SDM is still running"
    tray_window.quit_app()  # the tray's Quit
    assert quits == [1]


def test_without_the_option_closing_quits(qtbot, tray_window, controller):
    quits = []
    tray_window.quit_confirmed.connect(lambda: quits.append(1))
    tray_window.close()
    assert quits == [1]


def test_the_window_layout_is_remembered(qtbot, controller, tmp_path):
    first = MainWindow(controller, default_folder=tmp_path)
    qtbot.addWidget(first)
    first.resize(700, 420)  # fits the off-screen test display (about 800 x 600)
    first.download_table.setColumnWidth(1, 123)
    first.save_layout()
    second = MainWindow(controller, default_folder=tmp_path)
    qtbot.addWidget(second)
    assert (second.size().width(), second.size().height()) == (700, 420)
    assert second.download_table.columnWidth(1) == 123


def test_the_last_folder_is_offered_next_time(qtbot, controller, tmp_path):
    folder = tmp_path / "chosen"
    folder.mkdir()
    first = MainWindow(controller)
    qtbot.addWidget(first)
    first.add_download("https://example.com/a.zip", folder, start=False)
    second = MainWindow(controller)
    qtbot.addWidget(second)
    assert second._default_folder == folder

    controller.set_preferences(replace(controller.preferences, remember_last_folder=False,
                                       default_folder=str(tmp_path)))  # fmt: skip
    third = MainWindow(controller)
    qtbot.addWidget(third)
    assert third._default_folder == tmp_path
