"""Register SDM's native messaging host with Chrome for this Windows user, or remove it.

    uv run python -m sdm.bridge.install --extension-id <the extension's 32-letter ID>
    uv run python -m sdm.bridge.install --uninstall

Installing writes two files into %LOCALAPPDATA%\\SDM\\bridge (the host manifest and the
launcher Chrome runs) and sets one registry value:
HKCU\\Software\\Google\\Chrome\\NativeMessagingHosts\\com.sdm.bridge = the manifest's path.
Only the extension with the given ID may start the host (allowed_origins). Uninstalling
removes exactly that key and those two files.
"""

import argparse
import json
import re
import sys
import winreg
from pathlib import Path

from sdm.core.errors import SDMError
from sdm.core.paths import app_data_dir

HOST_NAME = "com.sdm.bridge"
CHROME_HOSTS_KEY = "Software\\Google\\Chrome\\NativeMessagingHosts"
MANIFEST_NAME = f"{HOST_NAME}.json"
LAUNCHER_NAME = "sdm-bridge-host.bat"
HOST_EXE_NAME = "sdm-bridge-host.exe"  # the installed SDM's host, next to SDM.exe (M10)
_EXTENSION_ID = re.compile(r"[a-p]{32}")


class InstallError(SDMError):
    pass


def host_folder() -> Path:
    return app_data_dir() / "bridge"


def host_manifest(extension_id: str, launcher: Path) -> dict[str, object]:
    if not _EXTENSION_ID.fullmatch(extension_id):
        raise InstallError(
            "An extension ID is 32 letters from a to p; copy it from chrome://extensions."
        )
    return {
        "name": HOST_NAME,
        "description": "SDM (Smart Download Manager) browser bridge",
        "path": str(launcher),
        "type": "stdio",
        "allowed_origins": [f"chrome-extension://{extension_id}/"],
    }


def launcher_text(python: Path) -> str:
    """The .bat file Chrome runs. -P keeps the current folder off Python's import path."""
    if any(ch in str(python) for ch in '%"'):  # would break the quoting in a .bat file
        raise InstallError(f"The Python path can't be used in a launcher: {python}")
    return f'@echo off\r\n"{python}" -P -m sdm.bridge.host %*\r\n'


def install(
    extension_id: str,
    *,
    folder: Path | None = None,
    python: Path | None = None,
    root: int = winreg.HKEY_CURRENT_USER,
    hosts_key: str = CHROME_HOSTS_KEY,
    frozen_host: Path | None = None,
) -> Path:
    """Write the launcher and manifest, register the manifest, and return its path.

    In the installed (PyInstaller) SDM, Chrome starts `sdm-bridge-host.exe` directly and no
    .bat launcher is written (M10); `frozen_host` defaults to that exe when SDM is frozen.
    """
    folder = folder or host_folder()
    if frozen_host is None and getattr(sys, "frozen", False):
        frozen_host = Path(sys.executable).with_name(HOST_EXE_NAME)
    launcher = frozen_host or folder / LAUNCHER_NAME
    manifest = host_manifest(extension_id, launcher)  # checks the ID before writing anything
    folder.mkdir(parents=True, exist_ok=True)
    if frozen_host is None:
        launcher.write_bytes(launcher_text(python or Path(sys.executable)).encode("ascii"))
    else:
        (folder / LAUNCHER_NAME).unlink(missing_ok=True)  # a source checkout's old launcher
    manifest_path = folder / MANIFEST_NAME
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    with winreg.CreateKeyEx(root, f"{hosts_key}\\{HOST_NAME}", 0, winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, "", 0, winreg.REG_SZ, str(manifest_path))
    return manifest_path


def uninstall(
    *,
    folder: Path | None = None,
    root: int = winreg.HKEY_CURRENT_USER,
    hosts_key: str = CHROME_HOSTS_KEY,
) -> bool:
    """Remove the registry key and the two files; returns False if nothing was installed."""
    folder = folder or host_folder()
    removed = False
    try:
        winreg.DeleteKey(root, f"{hosts_key}\\{HOST_NAME}")
        removed = True
    except FileNotFoundError:
        pass
    for name in (MANIFEST_NAME, LAUNCHER_NAME):
        try:
            (folder / name).unlink()
            removed = True
        except FileNotFoundError:
            pass
    return removed


def registered_manifest(
    *, root: int = winreg.HKEY_CURRENT_USER, hosts_key: str = CHROME_HOSTS_KEY
) -> str | None:
    try:
        with winreg.OpenKey(root, f"{hosts_key}\\{HOST_NAME}") as key:
            value, _kind = winreg.QueryValueEx(key, "")
    except FileNotFoundError:
        return None
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m sdm.bridge.install",
        description="Let SDM's Chrome extension hand links to SDM (for this Windows user).",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--extension-id", help="the ID chrome://extensions shows for SDM")
    group.add_argument("--uninstall", action="store_true", help="remove the registration")
    args = parser.parse_args(argv)
    if args.uninstall:
        removed = uninstall()
        print("Removed SDM's browser bridge." if removed else "Nothing to remove.")
        return 0
    try:
        manifest_path = install(args.extension_id.strip())
    except (InstallError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"Registered {HOST_NAME} for extension {args.extension_id.strip()}.")
    print(f"Manifest: {manifest_path}")
    print("Now quit Chrome completely (every window, and its tray icon if it has one) and")
    print("open it again: a Chrome that was already running won't find the new host.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
