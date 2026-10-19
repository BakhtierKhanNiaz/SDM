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


def test_help_menu_sets_up_chrome(qtbot, make_controller, tmp_path, monkeypatch):
    from sdm.bridge import install as install_module
    from sdm.ui.main_window import MainWindow

    calls = []
    monkeypatch.setattr(install_module, "install", lambda extension_id: calls.append(extension_id))
    window = MainWindow(make_controller(start=False), default_folder=tmp_path)
    qtbot.addWidget(window)
    title, message, ok = window.register_chrome(EXTENSION_ID)
    assert ok and calls == [EXTENSION_ID] and "Quit Chrome completely" in message
    assert window.chrome_setup_action.text() == "Set up &Chrome integration…"


def test_help_menu_reports_a_bad_extension_id(qtbot, make_controller, tmp_path, hosts_key):
    from sdm.ui.main_window import MainWindow

    window = MainWindow(make_controller(start=False), default_folder=tmp_path)
    qtbot.addWidget(window)
    title, message, ok = window.register_chrome("not-an-id")
    assert not ok and "32 letters" in message


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
