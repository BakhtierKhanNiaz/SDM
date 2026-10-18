"""Registering the native messaging host, against a throwaway registry key (M7).

The tests write under HKCU\\Software\\SDM-tests\\<random>, never Chrome's real key, and
delete what they created.
"""

import json
import uuid
import winreg
from pathlib import Path

import pytest

from sdm.bridge.install import (
    CHROME_HOSTS_KEY,
    HOST_NAME,
    InstallError,
    install,
    launcher_text,
    registered_manifest,
    uninstall,
)

EXTENSION_ID = "abcdefghijklmnopabcdefghijklmnop"
PYTHON = Path("D:\\Projects\\SDM\\.venv\\Scripts\\python.exe")


@pytest.fixture
def hosts_key():
    parent = "Software\\SDM-tests"
    key = f"{parent}\\{uuid.uuid4().hex}"
    yield key
    for path in (f"{key}\\{HOST_NAME}", key, parent):
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, path)
        except OSError:
            pass  # already gone, or (for the parent) another run's key is still inside


def test_install_writes_the_manifest_launcher_and_registry_value(tmp_path, hosts_key):
    manifest_path = install(EXTENSION_ID, folder=tmp_path, python=PYTHON, hosts_key=hosts_key)
    assert registered_manifest(hosts_key=hosts_key) == str(manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest == {
        "name": "com.sdm.bridge",
        "description": "SDM (Smart Download Manager) browser bridge",
        "path": str(tmp_path / "sdm-bridge-host.bat"),
        "type": "stdio",
        "allowed_origins": [f"chrome-extension://{EXTENSION_ID}/"],  # only this extension
    }
    launcher = (tmp_path / "sdm-bridge-host.bat").read_bytes()  # bytes: keep the \r\n
    assert launcher == f'@echo off\r\n"{PYTHON}" -P -m sdm.bridge.host %*\r\n'.encode("ascii")


def test_uninstall_removes_exactly_what_install_made(tmp_path, hosts_key):
    other = tmp_path / "keep-me.txt"
    other.write_text("not ours", encoding="utf-8")
    install(EXTENSION_ID, folder=tmp_path, python=PYTHON, hosts_key=hosts_key)
    assert uninstall(folder=tmp_path, hosts_key=hosts_key) is True
    assert registered_manifest(hosts_key=hosts_key) is None
    assert sorted(p.name for p in tmp_path.iterdir()) == ["keep-me.txt"]
    assert uninstall(folder=tmp_path, hosts_key=hosts_key) is False  # nothing left to remove


@pytest.mark.parametrize(
    "extension_id",
    ["", "short", "ABCDEFGHIJKLMNOPABCDEFGHIJKLMNOP", "qrstuvwxyzabcdefqrstuvwxyzabcdef",
     EXTENSION_ID + "a", "abcdefghijklmnop/../../../../../../", "*"],
)  # fmt: skip
def test_a_bad_extension_id_writes_nothing(tmp_path, hosts_key, extension_id):
    with pytest.raises(InstallError):
        install(extension_id, folder=tmp_path / "bridge", python=PYTHON, hosts_key=hosts_key)
    assert not (tmp_path / "bridge").exists()
    assert registered_manifest(hosts_key=hosts_key) is None


@pytest.mark.parametrize("python", ['C:\\a"b\\python.exe', "C:\\100%\\python.exe"])
def test_a_python_path_that_would_break_the_launcher_is_refused(python):
    with pytest.raises(InstallError):
        launcher_text(Path(python))


def test_the_real_key_is_chromes_per_user_key():
    assert CHROME_HOSTS_KEY == "Software\\Google\\Chrome\\NativeMessagingHosts"
