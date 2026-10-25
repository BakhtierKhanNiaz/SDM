"""The M13 look: toolbar icons, the sidebar with counts, file-type icons, coloured status."""

from dataclasses import replace

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from sdm.core.downloads import BrowserContext, DownloadRecord, DownloadState
from sdm.ui.download_model import NAME, STATUS, STATUS_COLOURS, status_kind
from sdm.ui.glyphs import NAMES, glyph
from sdm.ui.main_window import MainWindow
from sdm.ui.sidebar import VIEWS, matches_view
from sdm.ui.theme import apply_theme, colors_for


def _luminance(hex_color: str) -> float:
    channels = [int(hex_color[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast(a: str, b: str) -> float:
    light, dark = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (light + 0.05) / (dark + 0.05)


@pytest.mark.parametrize("dark", [False, True])
def test_status_colours_are_readable(dark):
    colours = colors_for(dark)
    for kind, colour in STATUS_COLOURS[dark].items():
        for background in ("base", "alt"):
            assert contrast(colour, colours[background]) >= 4.5, (kind, background)


def record(state=DownloadState.COMPLETED, **fields) -> DownloadRecord:
    base = DownloadRecord(1, "https://example.com/a.zip", "D:\\", False, state, "a.zip", None,
                          10, 10, True, None, "t", "t", None)  # fmt: skip
    return replace(base, **fields)


def test_which_downloads_each_view_shows():
    done, running = record(), record(DownloadState.DOWNLOADING)
    paused, failed = record(DownloadState.PAUSED), record(DownloadState.FAILED)
    queued = record(DownloadState.QUEUED)
    assert [matches_view(r, "downloading") for r in (done, running, paused, queued)] == [
        False, True, False, True]  # fmt: skip
    assert [matches_view(r, "finished") for r in (done, running, paused)] == [True, False, False]
    assert [matches_view(r, "unfinished") for r in (done, paused, failed)] == [False, True, True]
    assert matches_view(record(category="Video"), "Video")
    assert not matches_view(record(category="Music"), "Video")
    assert all(matches_view(r, "all") for r in (done, running, paused, failed))


def test_status_kinds():
    assert status_kind(record()) == "done"
    assert status_kind(record(checksum_state="mismatch")) == "failed"
    assert status_kind(record(DownloadState.FAILED)) == "failed"
    assert status_kind(record(DownloadState.PAUSED)) == "waiting"
    assert status_kind(record(DownloadState.DOWNLOADING)) == "active"
    assert status_kind(record(DownloadState.QUEUED)) is None


def test_every_glyph_draws(qapp):
    for name in NAMES:
        icon = glyph(name, "#1f2328", disabled="#5b636e")
        assert not icon.pixmap(24, 24).isNull(), name


@pytest.fixture
def window(qtbot, make_controller, tmp_path):
    window = MainWindow(make_controller(start=False), default_folder=tmp_path)
    window.confirm_quit = lambda active: True
    qtbot.addWidget(window)
    window.show()
    yield window
    apply_theme(QApplication.instance(), "light")


def add_finished(window, tmp_path, name, category):
    store = window.controller.store
    path = tmp_path / name
    path.write_bytes(b"data")
    entry = store.add(f"https://example.com/{name}", str(tmp_path), category=category,
                      context=BrowserContext(None, None))  # fmt: skip
    store.mark_downloading(entry.id)
    store.mark_completed(entry.id, path=str(path), size=4, verified_complete=True)
    store.set_file_info(entry.id, name, 4)
    return entry.id


def test_the_toolbar_has_icons_and_short_labels(window):
    toolbar = window.toolbar
    labels = [a.iconText() for a in toolbar.actions() if not a.isSeparator()]
    assert labels == ["Add URL", "Pause", "Resume", "Resume all", "Cancel", "Remove",
                      "Start now", "Scheduler", "Convert", "Settings"]  # fmt: skip
    assert all(not a.icon().isNull() for a in toolbar.actions() if not a.isSeparator())
    assert toolbar.toolButtonStyle() == Qt.ToolButtonStyle.ToolButtonTextUnderIcon


def test_the_sidebar_counts_and_filters(window, tmp_path):
    add_finished(window, tmp_path, "song.mp3", "Music")
    add_finished(window, tmp_path, "film.mp4", "Video")
    paused = window.controller.store.add("https://example.com/b.zip", str(tmp_path))
    window.controller.store.mark_paused(paused.id)
    window.controller.model.set_records(window.controller.store.list_all())
    assert [window.sidebar.count_text(key) for key, _ in VIEWS] == [
        "All downloads  (3)", "Downloading", "Finished  (2)", "Unfinished  (1)"]  # fmt: skip
    assert window.sidebar.count_text("Video") == "Video  (1)"
    window.sidebar.select_view("Music")
    assert window.proxy.rowCount() == 1
    window.sidebar.select_view("unfinished")
    assert window.proxy.rowCount() == 1
    window.sidebar.select_view("all")
    assert window.proxy.rowCount() == 3


def test_rows_show_a_file_type_icon_and_a_coloured_status(window, tmp_path):
    add_finished(window, tmp_path, "film.mp4", "Video")
    model = window.controller.model
    model.set_records(window.controller.store.list_all())
    assert not model.data(model.index(0, NAME), Qt.ItemDataRole.DecorationRole).isNull()
    colour = model.data(model.index(0, STATUS), Qt.ItemDataRole.ForegroundRole)
    assert colour.name() == STATUS_COLOURS[False]["done"]


def test_icons_follow_the_dark_look(window):
    apply_theme(QApplication.instance(), "dark")
    window.refresh_icons()
    assert window.controller.model.dark is True
    apply_theme(QApplication.instance(), "light")
    window.refresh_icons()
    assert window.controller.model.dark is False


def test_the_sidebar_width_is_remembered(qtbot, make_controller, tmp_path):
    controller = make_controller(start=False)
    first = MainWindow(controller, default_folder=tmp_path)
    qtbot.addWidget(first)
    first.resize(1000, 500)
    first.show()
    first.body.setSizes([260, 740])
    first.save_layout()
    second = MainWindow(controller, default_folder=tmp_path)
    qtbot.addWidget(second)
    second.show()
    assert second.body.sizes()[0] == 260  # the list takes whatever width the window has
