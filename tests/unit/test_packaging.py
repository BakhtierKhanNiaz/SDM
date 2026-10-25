"""The installed (PyInstaller) SDM: Chrome registration, Help menu, notices, build files (M10)."""

import json
import sys
import uuid
import winreg
from pathlib import Path

import pytest

from sdm.bridge.install import HOST_NAME, LAUNCHER_NAME, install, registered_manifest

EXTENSION_ID = "abcdefghijklmnopabcdefghijklmnop"
ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def hosts_key():
    parent = "Software\\SDM-tests"
    key = f"{parent}\\{uuid.uuid4().hex}"
    yield key
    for path in (f"{key}\\{HOST_NAME}", key, parent):
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, path)
        except OSError:
            pass


def test_the_installed_sdm_registers_its_exe_directly(tmp_path, hosts_key, monkeypatch):
    app = tmp_path / "Programs" / "SDM"
    app.mkdir(parents=True)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(app / "SDM.exe"))
    folder = tmp_path / "bridge"
    folder.mkdir()
    (folder / LAUNCHER_NAME).write_text("old source-checkout launcher", encoding="utf-8")
    manifest_path = install(EXTENSION_ID, folder=folder, hosts_key=hosts_key)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["path"] == str(app / "sdm-bridge-host.exe")  # no .bat, no Python
    assert not (folder / LAUNCHER_NAME).exists()  # the old launcher is gone
    assert registered_manifest(hosts_key=hosts_key) == str(manifest_path)


def test_a_source_checkout_still_uses_the_launcher(tmp_path, hosts_key, monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    manifest_path = install(EXTENSION_ID, folder=tmp_path, python=Path("C:\\py\\python.exe"),
                            hosts_key=hosts_key)  # fmt: skip
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["path"] == str(tmp_path / LAUNCHER_NAME)


def make_window(qtbot, make_controller, tmp_path):
    from sdm.ui.main_window import MainWindow

    window = MainWindow(make_controller(start=False), default_folder=tmp_path)
    qtbot.addWidget(window)
    return window


def test_the_setup_assistant_saves_choices_and_connects_browsers(
    qtbot, make_controller, tmp_path, monkeypatch
):
    from PySide6.QtWidgets import QDialog

    from sdm.bridge import browsers
    from sdm.bridge import install as install_module

    monkeypatch.setattr(browsers, "installed_browsers",
                        lambda: [browsers.BY_KEY["chrome"], browsers.BY_KEY["edge"]])  # fmt: skip
    registered = []

    def fake_register(chosen):
        registered.extend(browser.name for browser in chosen)
        return registered

    monkeypatch.setattr(install_module, "register_browsers", fake_register)
    window = make_window(qtbot, make_controller, tmp_path)
    assert window.setup_action.text() == "&Setup assistant…"
    wizard = window.open_setup_wizard()
    # Installed browsers are ticked; the others can't be.
    assert wizard.browser_checks["chrome"].isChecked() and wizard.browser_checks["edge"].isChecked()
    assert not wizard.browser_checks["firefox"].isEnabled()
    wizard.browser_checks["edge"].setChecked(False)
    folder = tmp_path / "downloads"
    folder.mkdir()
    wizard.folder_edit.setText(str(folder))
    wizard.theme_box.setCurrentIndex(wizard.theme_box.findData("dark"))
    names = window.finish_setup(wizard, QDialog.DialogCode.Accepted)
    assert names == ["Google Chrome"] and registered == ["Google Chrome"]
    preferences = window.controller.preferences
    assert (preferences.default_folder, preferences.theme, preferences.setup_done) == (
        str(folder), "dark", True)  # fmt: skip
    assert window.status_label.text() == "Connected to: Google Chrome"
    from PySide6.QtWidgets import QApplication

    from sdm.ui.theme import apply_theme

    apply_theme(QApplication.instance(), "light")  # don't leave other tests in dark mode


def test_cancelling_the_assistant_isnt_asked_again(qtbot, make_controller, tmp_path):
    from PySide6.QtWidgets import QDialog

    window = make_window(qtbot, make_controller, tmp_path)
    wizard = window.open_setup_wizard()
    assert window.finish_setup(wizard, QDialog.DialogCode.Rejected) == []
    assert window.controller.preferences.setup_done is True


def test_extension_links_point_at_the_release_until_the_stores_list_it():
    from sdm.core import links

    assert links.extension_page("chrome") == links.RELEASES_URL
    assert links.extension_page("edge") == (links.EDGE_STORE_URL or links.RELEASES_URL)


def test_links_name_the_real_repository():
    from sdm.core import links

    assert links.PROJECT_URL == "https://github.com/Conditions-tech/SDM"
    assert links.RELEASES_URL == f"{links.PROJECT_URL}/releases/latest"


def test_third_party_notices_cover_every_library_in_the_build():
    sys.path.insert(0, str(ROOT / "scripts"))
    try:
        import build_release
    finally:
        sys.path.pop(0)
    text = build_release.notices()
    for name in ("Python", "aiohttp", "PySide6_Essentials", "shiboken6", "yarl", "idna"):
        assert f"===== {name} " in text
    assert "LGPL" in text  # Qt's licence text is included


def test_build_files_agree():
    spec = (ROOT / "packaging" / "sdm.spec").read_text(encoding="utf-8")
    iss = (ROOT / "packaging" / "sdm.iss").read_text(encoding="utf-8")
    assert 'name="SDM"' in spec and 'name="sdm-bridge-host"' in spec
    assert "PrivilegesRequired=lowest" in iss  # per user, no administrator rights
    assert "NativeMessagingHosts\\com.sdm.bridge" in iss and "uninsdeletekey" in iss
    from sdm.bridge.host import launch_sdm  # the host starts "sdm.exe" next to itself

    assert launch_sdm.__doc__ and "sdm.exe" in launch_sdm.__doc__


def test_installer_cleans_up_every_browser():
    from sdm.bridge.browsers import BROWSERS
    from sdm.bridge.install import FIREFOX_MANIFEST_NAME, HOST_NAME

    iss = (ROOT / "packaging" / "sdm.iss").read_text(encoding="utf-8")
    for browser in BROWSERS:
        line = f'Subkey: "{browser.hosts_key}\\{HOST_NAME}"; Flags: uninsdeletekey dontcreatekey'
        assert line in iss, browser.name
    assert FIREFOX_MANIFEST_NAME in iss
