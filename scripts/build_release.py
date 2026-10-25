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
    # a per-user install of Inno Setup
    Path.home() / "AppData" / "Local" / "Programs" / "Inno Setup 6" / "ISCC.exe",
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


def find_iscc() -> Path | None:
    """Inno Setup's compiler: the usual folders, then wherever its installer recorded itself."""
    for place in ISCC_PLACES:
        if place.is_file():
            return place
    import winreg

    key_name = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6_is1"
    for root, view in (
        (winreg.HKEY_LOCAL_MACHINE, winreg.KEY_WOW64_32KEY),
        (winreg.HKEY_LOCAL_MACHINE, winreg.KEY_WOW64_64KEY),
        (winreg.HKEY_CURRENT_USER, 0),
    ):
        try:
            with winreg.OpenKey(root, key_name, 0, winreg.KEY_READ | view) as key:
                folder, _ = winreg.QueryValueEx(key, "InstallLocation")
        except OSError:
            continue
        candidate = Path(folder) / "ISCC.exe"
        if candidate.is_file():
            return candidate
    found = shutil.which("ISCC")
    return Path(found) if found else None


def build(installer: bool, *, skip_build: bool = False, iscc: Path | None = None) -> int:
    version = metadata.version("sdm")
    if skip_build and (APP / "SDM.exe").is_file():
        print(f"Using the existing {APP}")
    else:
        subprocess.run(  # noqa: S603 - fixed arguments
            [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
             "--distpath", str(DIST), "--workpath", str(ROOT / "build"),
             str(ROOT / "packaging" / "sdm.spec")],
            check=True, cwd=ROOT,
        )  # fmt: skip
        (APP / "THIRD-PARTY-NOTICES.txt").write_text(notices(), encoding="utf-8")
        # M13: the browser extension, unpacked, for the welcome assistant's "Add to Chrome".
        from build_extensions import write_folder

        write_folder(APP / "extension")
        print(f"Built {APP} (SDM {version}, with the browser extension)")
    if not installer:
        return 0
    iscc = iscc or find_iscc()
    if iscc is None or not iscc.is_file():
        print(
            "Inno Setup's ISCC.exe wasn't found. Install Inno Setup 6, or pass its path with "
            '--iscc "C:\\...\\ISCC.exe".',
            file=sys.stderr,
        )
        return 1
    print(f"Using {iscc}")
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
    parser.add_argument(
        "--skip-build", action="store_true", help="reuse an existing dist\\SDM (installer only)"
    )
    parser.add_argument("--iscc", type=Path, help="path to Inno Setup's ISCC.exe")
    args = parser.parse_args()
    return build(args.installer, skip_build=args.skip_build, iscc=args.iscc)


if __name__ == "__main__":
    raise SystemExit(main())
