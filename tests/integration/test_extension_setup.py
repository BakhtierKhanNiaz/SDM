"""The extension comes with SDM, and the welcome assistant guides "Load unpacked" (M13)."""

import json
import sys
from pathlib import Path

from PySide6.QtGui import QGuiApplication

from sdm.bridge import browsers
from sdm.bridge.browsers import BY_KEY, extension_folder, open_extensions_page
from sdm.ui.preferences import Preferences
from sdm.ui.setup_wizard import SetupWizard

ROOT = Path(__file__).resolve().parent.parent.parent


def test_the_extension_folder_is_the_unpacked_extension():
    folder = extension_folder()
    assert folder == ROOT / "extension" / "chrome"  # running from the project folder
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["key"]  # the fixed ID, so SDM's registration matches


def test_the_installed_sdm_finds_it_next_to_sdm_exe(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "SDM.exe"))
    assert extension_folder() == tmp_path / "extension"


def test_the_build_puts_the_extension_next_to_sdm(tmp_path):
    sys.path.insert(0, str(ROOT / "scripts"))
    try:
        from build_extensions import FILES, write_folder
    finally:
        sys.path.remove(str(ROOT / "scripts"))
    target = tmp_path / "SDM" / "extension"
    (target / "old.js").parent.mkdir(parents=True)
    (target / "old.js").write_text("stale", encoding="utf-8")  # from an older SDM
    write_folder(target)
    assert not (target / "old.js").exists()
    for name in ["manifest.json", *FILES]:
        assert (target / name).read_bytes() == (ROOT / "extension" / "chrome" / name).read_bytes()


def test_opening_a_browsers_extensions_page(monkeypatch, tmp_path):
    chrome = tmp_path / "chrome.exe"
    chrome.write_bytes(b"MZ")
    monkeypatch.setattr(browsers, "program_path", lambda b: chrome if b.key == "chrome" else None)
    started = []
    assert open_extensions_page(BY_KEY["chrome"], launch=started.append) is True
    assert started == [[str(chrome), "chrome://extensions"]]
    assert open_extensions_page(BY_KEY["edge"], launch=started.append) is False  # not found
    assert open_extensions_page(BY_KEY["firefox"], launch=started.append) is False  # no unpacked
    assert len(started) == 1


def test_the_assistant_guides_load_unpacked(qtbot, monkeypatch, tmp_path):
    edge = tmp_path / "msedge.exe"
    edge.write_bytes(b"MZ")
    monkeypatch.setattr(browsers, "program_path", lambda b: edge)
    wizard = SetupWizard(Preferences(), installed={"edge", "firefox"}, default_folder=tmp_path)
    qtbot.addWidget(wizard)
    started = []
    wizard.launch = started.append
    assert wizard.add_buttons["edge"].text() == "Add to Edge"
    assert wizard.add_buttons["firefox"].text() == "Get the add-on"
    assert not wizard.add_buttons["chrome"].isEnabled()  # not installed here
    wizard.add_buttons["edge"].click()
    assert started == [[str(edge), "edge://extensions"]]
    assert QGuiApplication.clipboard().text() == str(extension_folder())
    guide = wizard.guide.text()
    for step in ("Developer mode", "Load unpacked", "Ctrl+V", "Select Folder"):
        assert step in guide
    # The owner's report (2026-10-27): Edge and Chrome open a blank new tab, never their
    # extensions page, so the guide must say to type the address, not claim it opened.
    assert "type <b>edge://extensions</b> in the address bar" in guide
    assert "window that opened" not in guide


def test_the_guide_works_when_the_browser_cant_be_started(qtbot, monkeypatch, tmp_path):
    monkeypatch.setattr(browsers, "program_path", lambda b: None)
    wizard = SetupWizard(Preferences(), installed={"chrome"}, default_folder=tmp_path)
    qtbot.addWidget(wizard)
    assert wizard.add_extension(BY_KEY["chrome"]) is False
    assert "In Google Chrome, type <b>chrome://extensions</b>" in wizard.guide.text()


def test_help_opens_the_assistant_at_the_browsers(qtbot, make_controller, tmp_path, monkeypatch):
    from sdm.ui.main_window import MainWindow

    window = MainWindow(make_controller(start=False), default_folder=tmp_path)
    qtbot.addWidget(window)
    monkeypatch.setattr("sdm.bridge.browsers.installed_browsers", lambda: [])
    window.extension_action.trigger()
    wizard = window.setup_wizard
    assert wizard is not None
    assert wizard.currentId() == wizard.pageIds()[-1]
    wizard.reject()
