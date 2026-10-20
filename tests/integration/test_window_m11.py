"""The M11 look: themes, progress bars, the details panel, the remembered split."""

from dataclasses import replace

import pytest
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication

from sdm.core.checksums import VERIFIED
from sdm.core.downloads import BrowserContext, DownloadRecord, DownloadState
from sdm.ui.download_model import PROGRESS, PROGRESS_ROLE, progress_percent
from sdm.ui.main_window import MainWindow
from sdm.ui.preferences import Preferences, load_preferences, save_preferences
from sdm.ui.settings_dialog import SettingsDialog
from sdm.ui.theme import apply_theme, colors_for


def _luminance(hex_color: str) -> float:
    channels = [int(hex_color[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast(a: str, b: str) -> float:
    light, dark = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (light + 0.05) / (dark + 0.05)


@pytest.mark.parametrize("dark", [False, True])
def test_text_colours_meet_wcag_aa(dark):
    c = colors_for(dark)
    for text, background in [("text", "window"), ("text", "base"), ("text", "alt"),
                             ("muted", "window"), ("muted", "base"),
                             ("accent_text", "accent"), ("text", "header")]:  # fmt: skip
        assert contrast(c[text], c[background]) >= 4.5, (text, background)


@pytest.fixture
def restore_theme(qapp):
    yield
    apply_theme(qapp, "light")


def test_light_and_dark_themes(qapp, restore_theme):
    assert apply_theme(qapp, "dark") is True
    assert qapp.palette().color(QPalette.ColorRole.Window).name() == colors_for(True)["window"]
    assert apply_theme(qapp, "light") is False
    assert qapp.palette().color(QPalette.ColorRole.Window).name() == colors_for(False)["window"]


def test_an_unknown_mode_follows_windows(qapp, restore_theme):
    apply_theme(qapp, "neon")
    assert qapp.property("sdm_theme_mode") == "system"


def test_the_theme_setting_is_saved_and_checked(tmp_path):
    from sdm.storage.database import DownloadStore

    store = DownloadStore(tmp_path / "sdm.db")
    try:
        save_preferences(store, Preferences(theme="dark"))
        assert load_preferences(store).theme == "dark"
        store.set_setting("prefs.theme", "purple")
        assert load_preferences(store).theme == "system"
    finally:
        store.close()


def test_settings_offer_the_appearance(qtbot):
    dialog = SettingsDialog(Preferences(theme="light"), tray_available=True)
    qtbot.addWidget(dialog)
    assert dialog.theme_box.currentData() == "light"
    dialog.theme_box.setCurrentIndex(dialog.theme_box.findData("dark"))
    assert dialog.preferences().theme == "dark"


def record(**fields) -> DownloadRecord:
    when = "2026-10-20T10:00:00+00:00"
    base = DownloadRecord(1, "https://example.com/a.zip?token=s3cret", "D:\\", False,
                          DownloadState.DOWNLOADING, "a.zip", None, 200, 50, None, None,
                          when, when, None)  # fmt: skip
    return replace(base, **fields)


def test_progress_values():
    assert progress_percent(record()) == 25
    assert progress_percent(record(total_bytes=None)) is None  # size unknown: text instead
    assert progress_percent(record(state=DownloadState.COMPLETED, total_bytes=None)) == 100
    assert progress_percent(record(received_bytes=500)) == 100


@pytest.fixture
def window(qtbot, make_controller, tmp_path, restore_theme):
    window = MainWindow(make_controller(start=False), default_folder=tmp_path)
    window.confirm_quit = lambda active: True
    qtbot.addWidget(window)
    window.show()
    return window


def finished(window, tmp_path):
    store = window.controller.store
    path = tmp_path / "a.zip"
    path.write_bytes(b"data")
    entry = store.add("https://example.com/a.zip?token=s3cret", str(tmp_path),
                      context=BrowserContext("https://www.example.com/page", None))  # fmt: skip
    store.mark_downloading(entry.id)
    store.mark_completed(entry.id, path=str(path), size=4, verified_complete=True)
    store.set_file_info(entry.id, "a.zip", 4)
    store.set_checksum(entry.id, "a" * 64, VERIFIED)
    window.controller.model.set_records(store.list_all())
    return entry.id


def test_the_list_draws_progress_bars(window, tmp_path):
    finished(window, tmp_path)
    assert window.download_table.itemDelegateForColumn(PROGRESS) is not None
    index = window.controller.model.index(0, PROGRESS)
    assert window.controller.model.data(index, PROGRESS_ROLE) == 100
    assert not window.grab().isNull()  # painting the bar doesn't fail
    apply_theme(QApplication.instance(), "dark")
    assert not window.grab().isNull()


def test_the_details_panel_follows_the_selection(window, tmp_path):
    panel = window.details
    assert panel.title.text() == "No download selected"
    download_id = finished(window, tmp_path)
    window.select_id(download_id)
    values = {name: label.text() for name, label in panel.values.items()}
    assert panel.title.text() == "a.zip"
    assert values["Address"] == "https://example.com/a.zip?<redacted>"  # no token on screen
    assert values["Checksum"].endswith("verified")
    assert values["From the browser"] == "page on www.example.com"
    assert panel.folder_button.isEnabled()
    assert not panel.values["Speed"].isVisible()  # nothing to say for a finished download
    panel.copy_button.click()
    assert QApplication.clipboard().text() == "https://example.com/a.zip?token=s3cret"
    window.download_table.clearSelection()
    assert panel.title.text() == "No download selected"


def test_the_split_between_list_and_details_is_remembered(qtbot, make_controller, tmp_path):
    controller = make_controller(start=False)
    first = MainWindow(controller, default_folder=tmp_path)
    qtbot.addWidget(first)
    first.resize(700, 500)
    first.show()
    first.splitter.setSizes([400, 60])
    sizes = first.splitter.sizes()
    first.save_layout()
    second = MainWindow(controller, default_folder=tmp_path)
    qtbot.addWidget(second)
    second.show()
    assert second.splitter.sizes() == sizes
