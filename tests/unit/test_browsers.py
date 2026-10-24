"""Every browser's registration, Firefox's caller check, and the extension packages (M11)."""

import io
import json
import struct
import sys
import uuid
import winreg
import zipfile
from pathlib import Path

import pytest

from sdm.bridge.browsers import (
    BROWSERS,
    BY_KEY,
    CHROMIUM_EXTENSION_ID,
    FIREFOX_EXTENSION_ID,
    chromium_origins,
)
from sdm.bridge.host import handle, started_by_browser
from sdm.bridge.install import (
    FIREFOX_MANIFEST_NAME,
    HOST_NAME,
    MANIFEST_NAME,
    register_browsers,
    unregister_browsers,
)

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def prefix():
    """Registry keys go under HKCU\\Software\\SDM-tests\\<random>\\ and are deleted after."""
    base = f"Software\\SDM-tests\\{uuid.uuid4().hex}\\"
    yield base

    def delete_tree(path: str) -> None:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as key:
                children = []
                index = 0
                while True:
                    try:
                        children.append(winreg.EnumKey(key, index))
                        index += 1
                    except OSError:
                        break
            for child in children:
                delete_tree(f"{path}\\{child}")
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, path)
        except OSError:
            pass

    delete_tree(base.rstrip("\\"))


def registered(prefix: str, browser_key: str) -> str | None:
    path = f"{prefix}{BY_KEY[browser_key].hosts_key}\\{HOST_NAME}"
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as key:
            return winreg.QueryValueEx(key, "")[0]
    except OSError:
        return None


def test_every_browser_is_registered_without_typing_an_id(tmp_path, prefix):
    names = register_browsers(folder=tmp_path, python=Path("C:\\py\\python.exe"),
                              key_prefix=prefix)  # fmt: skip
    assert names == ["Google Chrome", "Microsoft Edge", "Brave", "Mozilla Firefox"]
    for key in ("chrome", "edge", "brave"):
        assert registered(prefix, key) == str(tmp_path / MANIFEST_NAME)
    assert registered(prefix, "firefox") == str(tmp_path / FIREFOX_MANIFEST_NAME)
    chromium = json.loads((tmp_path / MANIFEST_NAME).read_text(encoding="utf-8"))
    firefox = json.loads((tmp_path / FIREFOX_MANIFEST_NAME).read_text(encoding="utf-8"))
    assert chromium["allowed_origins"] == chromium_origins()
    assert f"chrome-extension://{CHROMIUM_EXTENSION_ID}/" in chromium["allowed_origins"]
    assert firefox["allowed_extensions"] == [FIREFOX_EXTENSION_ID]
    assert "allowed_origins" not in firefox  # Firefox's format differs
    assert chromium["path"] == firefox["path"]


def test_only_the_chosen_browsers(tmp_path, prefix):
    register_browsers([BY_KEY["edge"]], folder=tmp_path, python=Path("C:\\py\\python.exe"),
                      key_prefix=prefix)  # fmt: skip
    assert registered(prefix, "edge") and not registered(prefix, "chrome")
    assert not (tmp_path / FIREFOX_MANIFEST_NAME).exists()


def test_unregistering_removes_everything(tmp_path, prefix):
    register_browsers(folder=tmp_path, python=Path("C:\\py\\python.exe"), key_prefix=prefix)
    assert unregister_browsers(folder=tmp_path, key_prefix=prefix) is True
    assert all(registered(prefix, browser.key) is None for browser in BROWSERS)
    assert list(tmp_path.iterdir()) == []
    assert unregister_browsers(folder=tmp_path, key_prefix=prefix) is False


def test_the_installed_app_registers_its_exe(tmp_path, prefix, monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "SDM" / "SDM.exe"))
    register_browsers(folder=tmp_path / "bridge", key_prefix=prefix)
    manifest = json.loads((tmp_path / "bridge" / MANIFEST_NAME).read_text(encoding="utf-8"))
    assert manifest["path"] == str(tmp_path / "SDM" / "sdm-bridge-host.exe")


@pytest.mark.parametrize(
    ("args", "allowed"),
    [
        ([f"chrome-extension://{CHROMIUM_EXTENSION_ID}/", "--parent-window=0"], True),
        (["C:\\x\\com.sdm.bridge.firefox.json", FIREFOX_EXTENSION_ID], True),  # Firefox's way
        (["C:\\x\\com.sdm.bridge.firefox.json", "evil@example.com"], False),
        (["C:\\x\\notes.txt", FIREFOX_EXTENSION_ID], False),
        ([FIREFOX_EXTENSION_ID], False),
        ([], False),
        (["https://evil.example/"], False),
    ],
)
def test_who_may_start_the_host(args, allowed):
    assert started_by_browser(args) is allowed


def test_a_firefox_call_reaches_the_request_check(tmp_path):
    body = json.dumps({"version": 2, "type": "download", "url": "file:///C:/x"}).encode()
    stdin = io.BytesIO(struct.pack("<I", len(body)) + body)
    reply = handle(["C:\\x\\com.sdm.bridge.firefox.json", FIREFOX_EXTENSION_ID], stdin,
                   key_path=tmp_path / "bridge.key", launch=lambda: None)  # fmt: skip
    assert reply == {"ok": False, "error": "bad_request"}  # past the caller check


def test_the_extension_packages(tmp_path):
    sys.path.insert(0, str(ROOT / "scripts"))
    try:
        import build_extensions
    finally:
        sys.path.pop(0)
    monkeypatch_out = tmp_path / "extension"
    build_extensions.OUT = monkeypatch_out
    chromium, edge, firefox = build_extensions.build()

    def read(path, name):
        with zipfile.ZipFile(path) as archive:
            return archive.read(name).decode("utf-8")

    chromium_manifest = json.loads(read(chromium, "manifest.json"))
    assert "key" in chromium_manifest  # fixed ID for developer-mode installs
    assert "key" not in json.loads(read(edge, "manifest.json"))  # the store assigns its ID
    firefox_manifest = json.loads(read(firefox, "manifest.json"))
    assert firefox_manifest["browser_specific_settings"]["gecko"]["id"] == FIREFOX_EXTENSION_ID
    assert firefox_manifest["background"] == {"scripts": ["background.js"]}
    assert "key" not in firefox_manifest
    background = read(firefox, "background.js")
    import re

    assert not re.search(r"^\s*import\s", background, re.MULTILINE)  # one classic script
    assert 'from "./' not in background
    assert "export " not in background
    for permissions in (chromium_manifest["permissions"], firefox_manifest["permissions"]):
        assert sorted(permissions) == ["contextMenus", "nativeMessaging"]


def test_the_fixed_extension_id_matches_the_manifest_key():
    import base64
    import hashlib

    manifest = json.loads((ROOT / "extension" / "chrome" / "manifest.json").read_text("utf-8"))
    digest = hashlib.sha256(base64.b64decode(manifest["key"])).hexdigest()[:32]
    assert "".join(chr(ord("a") + int(c, 16)) for c in digest) == CHROMIUM_EXTENSION_ID
