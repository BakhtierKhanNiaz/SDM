"""Build the installable SDM (M10, ADR-0018).

    uv run python scripts/build_release.py              # dist\\SDM (the program folder)
    uv run python scripts/build_release.py --installer  # also dist\\SDM-Setup-<version>.exe

1. PyInstaller builds dist\\SDM\\ from packaging\\sdm.spec (SDM.exe + sdm-bridge-host.exe).
2. THIRD-PARTY-NOTICES.txt is written next to them: the licence of Python and of every
   library inside the build, copied from the libraries themselves.
3. With --installer, Inno Setup's compiler (ISCC.exe, installed separately) turns the folder
   into a per-user installer from packaging\\sdm.iss.
"""

import argparse
import importlib.metadata as metadata
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
APP = DIST / "SDM"
# The libraries that end up inside the build (SDM's runtime dependencies and theirs).
RUNTIME = ["aiohttp", "aiohappyeyeballs", "aiosignal", "attrs", "frozenlist", "idna",
           "multidict", "propcache", "yarl", "typing_extensions", "pyside6-essentials",
           "shiboken6"]  # fmt: skip
ISCC_PLACES = [
    Path(r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"),
    Path(r"C:\Program Files\Inno Setup 6\ISCC.exe"),
]


def notices() -> str:
    parts = [
        "SDM (Smart Download Manager) includes the following software. Their licences follow.",
        "",
    ]
    python_license = Path(sys.base_prefix) / "LICENSE.txt"
    parts.append(f"===== Python {sys.version.split()[0]} (PSF License) =====")
    if python_license.is_file():
        parts.append(python_license.read_text(encoding="utf-8", errors="replace").strip())
    for name in RUNTIME:
        dist = metadata.distribution(name)
        info = dist.metadata
        licence = (info.get("License-Expression") or info.get("License") or "").strip()
        summary = licence.splitlines()[0][:80] if licence else "licence: see below"
        parts += ["", f"===== {info['Name']} {dist.version} ({summary}) ====="]
        words = ("LICENSE", "LICENCE", "COPYING", "NOTICE")
        texts = [f for f in dist.files or [] if any(w in f.name.upper() for w in words)]
        for file in texts:
            text = Path(file.locate()).read_text(encoding="utf-8", errors="replace").strip()
            parts += [f"--- {file.name}", text]
        if not texts:
            home = info.get("Home-page") or info.get("Project-URL") or "its project page"
            parts.append(f"Licence: {licence or 'not stated in its metadata'}; see {home}")
    return "\n".join(parts) + "\n"


def build(installer: bool) -> int:
    version = metadata.version("sdm")
    subprocess.run(  # noqa: S603 - fixed arguments
        [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
         "--distpath", str(DIST), "--workpath", str(ROOT / "build"),
         str(ROOT / "packaging" / "sdm.spec")],
        check=True, cwd=ROOT,
    )  # fmt: skip
    (APP / "THIRD-PARTY-NOTICES.txt").write_text(notices(), encoding="utf-8")
    print(f"Built {APP} (SDM {version})")
    if not installer:
        return 0
    iscc = next((p for p in ISCC_PLACES if p.is_file()), None) or (
        Path(found) if (found := shutil.which("ISCC")) else None
    )
    if iscc is None:
        print("Inno Setup's ISCC.exe wasn't found: install Inno Setup 6 first.", file=sys.stderr)
        return 1
    subprocess.run(  # noqa: S603 - fixed arguments
        [str(iscc), f"/DAppVersion={version}", f"/DSourceDir={APP}", f"/O{DIST}",
         str(ROOT / "packaging" / "sdm.iss")],
        check=True, cwd=ROOT,
    )  # fmt: skip
    print(f"Built {DIST / f'SDM-Setup-{version}.exe'}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the installable SDM.")
    parser.add_argument("--installer", action="store_true", help="also build the installer")
    return build(parser.parse_args().installer)


if __name__ == "__main__":
    raise SystemExit(main())
