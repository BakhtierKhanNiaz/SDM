"""Build SDM's browser extension packages from extension/chrome (M11).

    uv run python scripts/build_extensions.py      # -> dist\\extension\\*.zip

- sdm-chromium-<v>.zip: Chrome, Brave and other Chromium browsers, loaded in developer mode.
  It keeps the manifest's public "key", so its ID is always klbnhggmneoiamogpgbkajkdklfacohb.
- sdm-edge-store-<v>.zip: for Microsoft Edge Add-ons, which assigns its own ID (no "key").
- sdm-firefox-<v>.zip: for Firefox Add-ons. Firefox runs background scripts, not service
  workers, so the three modules are joined into one classic background.js, and the manifest
  gets Firefox's add-on ID.
"""

import json
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "extension" / "chrome"
OUT = ROOT / "dist" / "extension"
sys.path.insert(0, str(ROOT / "src"))
from sdm.bridge.browsers import FIREFOX_EXTENSION_ID  # noqa: E402

FILES = ["background.js", "capture.js", "handoff.js", "popup.html", "popup.js"]
_IMPORT = re.compile(r"^import\s[\s\S]*?\sfrom\s+\"[^\"]+\";\s*$", re.MULTILINE)


def classic_background() -> str:
    """handoff.js + capture.js + background.js as one script without import/export."""
    parts = ["// Built from handoff.js, capture.js and background.js for Firefox."]
    for name in ("handoff.js", "capture.js", "background.js"):
        code = (SOURCE / name).read_text(encoding="utf-8")
        code = _IMPORT.sub("", code)
        code = re.sub(r"^export\s+", "", code, flags=re.MULTILINE)
        parts.append(f"// ----- {name} -----\n{code.strip()}\n")
    return "(() => {\n" + "\n".join(parts) + "})();\n"


def firefox_manifest(manifest: dict) -> dict:
    result = {key: value for key, value in manifest.items()
              if key not in ("key", "minimum_chrome_version", "background")}  # fmt: skip
    result["background"] = {"scripts": ["background.js"]}
    result["browser_specific_settings"] = {
        "gecko": {
            "id": FIREFOX_EXTENSION_ID,
            "strict_min_version": "121.0",  # background scripts in MV3 (MDN)
            "data_collection_permissions": {"required": ["none"]},  # SDM collects nothing
        }
    }
    return result


def write_zip(path: Path, manifest: dict, replace: dict[str, str] | None = None) -> None:
    replace = replace or {}
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest, indent=2) + "\n")
        for name in FILES:
            if name in replace:
                archive.writestr(name, replace[name])
            else:
                archive.write(SOURCE / name, name)


def build() -> list[Path]:
    manifest = json.loads((SOURCE / "manifest.json").read_text(encoding="utf-8"))
    version = manifest["version"]
    OUT.mkdir(parents=True, exist_ok=True)
    chromium = OUT / f"sdm-chromium-{version}.zip"
    edge = OUT / f"sdm-edge-store-{version}.zip"
    firefox = OUT / f"sdm-firefox-{version}.zip"
    write_zip(chromium, manifest)
    write_zip(edge, {key: value for key, value in manifest.items() if key != "key"})
    write_zip(firefox, firefox_manifest(manifest), {"background.js": classic_background()})
    return [chromium, edge, firefox]


if __name__ == "__main__":
    for path in build():
        print(f"Built {path} ({path.stat().st_size:,} bytes)")
