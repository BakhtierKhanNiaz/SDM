"""The browsers SDM's extension works in, and where each looks for native messaging hosts (M11).

Sources (checked 2026-10-20):
- Chrome: HKCU\\Software\\Google\\Chrome\\NativeMessagingHosts (developer.chrome.com).
- Edge: HKCU\\SOFTWARE\\Microsoft\\Edge\\NativeMessagingHosts, then Chromium's and Chrome's keys
  as fallbacks (learn.microsoft.com, "Native messaging").
- Firefox: HKCU\\SOFTWARE\\Mozilla\\NativeMessagingHosts, with "allowed_extensions" (add-on
  IDs) instead of "allowed_origins"; Firefox starts the host with the manifest's path and the
  add-on ID as arguments (developer.mozilla.org, "Native manifests", "Native messaging").
- Brave: no documented location, and it doesn't fall back to Chrome's key (Brave community
  forum). It uses the key Chromium-based browsers derive from their own registry path,
  Software\\BraveSoftware\\Brave-Browser: to confirm on a PC with Brave.
"""

import winreg
from dataclasses import dataclass

# The Chromium extension's ID is fixed by the public "key" in extension/chrome/manifest.json,
# wherever it is unpacked (checked by loading it in Chrome: test_the_fixed_extension_id).
CHROMIUM_EXTENSION_ID = "klbnhggmneoiamogpgbkajkdklfacohb"
# Assigned by Microsoft Edge Add-ons when SDM's extension is published there; add it here then.
EDGE_STORE_EXTENSION_ID: str | None = None
# Firefox add-on IDs are chosen by the developer (browser_specific_settings.gecko.id).
FIREFOX_EXTENSION_ID = "sdm@sdm-download-manager"


@dataclass(frozen=True)
class Browser:
    key: str
    name: str
    kind: str  # "chromium" or "firefox"
    hosts_key: str  # under HKEY_CURRENT_USER
    exe: str  # its program, for detecting whether it is installed


BROWSERS = (
    Browser("chrome", "Google Chrome", "chromium",
            "Software\\Google\\Chrome\\NativeMessagingHosts", "chrome.exe"),
    Browser("edge", "Microsoft Edge", "chromium",
            "Software\\Microsoft\\Edge\\NativeMessagingHosts", "msedge.exe"),
    Browser("brave", "Brave", "chromium",
            "Software\\BraveSoftware\\Brave-Browser\\NativeMessagingHosts", "brave.exe"),
    Browser("firefox", "Mozilla Firefox", "firefox",
            "Software\\Mozilla\\NativeMessagingHosts", "firefox.exe"),
)  # fmt: skip
BY_KEY = {browser.key: browser for browser in BROWSERS}
_APP_PATHS = "SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\App Paths\\"


def chromium_origins() -> list[str]:
    ids = [CHROMIUM_EXTENSION_ID, EDGE_STORE_EXTENSION_ID]
    return [f"chrome-extension://{extension_id}/" for extension_id in ids if extension_id]


def is_installed(browser: Browser) -> bool:
    """Windows' "App Paths" registry lists installed programs by their exe name."""
    for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            winreg.OpenKey(root, _APP_PATHS + browser.exe).Close()
            return True
        except OSError:
            continue
    return False


def installed_browsers() -> list[Browser]:
    return [browser for browser in BROWSERS if is_installed(browser)]
