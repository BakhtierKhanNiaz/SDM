"""SDM's logo (M13): every icon file exists in the right sizes and is used everywhere."""

import json
import struct
from pathlib import Path

from PySide6.QtGui import QImage

from sdm.ui.icons import ASSETS, LOGO_SIZES, app_icon

ROOT = Path(__file__).resolve().parent.parent.parent


def test_the_window_icon_has_every_size(qapp):
    for size in LOGO_SIZES:
        image = QImage(str(ASSETS / f"sdm-{size}.png"))
        assert (image.width(), image.height()) == (size, size)
    icon = app_icon()
    assert not icon.isNull()
    assert sorted(s.width() for s in icon.availableSizes()) == list(LOGO_SIZES)


def test_the_exe_icon_holds_every_size():
    data = (ROOT / "packaging" / "sdm.ico").read_bytes()
    reserved, kind, count = struct.unpack_from("<HHH", data)
    assert (reserved, kind, count) == (0, 1, len(LOGO_SIZES))
    sizes = []
    for index in range(count):
        width, _, _, _, _, _, length, offset = struct.unpack_from("<BBBBHHII", data, 6 + 16 * index)
        assert data[offset : offset + 8] == b"\x89PNG\r\n\x1a\n"  # each one a PNG
        assert offset + length <= len(data)
        sizes.append(width or 256)
    assert sizes == list(LOGO_SIZES)


def test_the_build_and_the_installer_use_it():
    spec = (ROOT / "packaging" / "sdm.spec").read_text(encoding="utf-8")
    assert spec.count("icon=ICON") == 2  # SDM.exe and the browser helper
    assert '"assets", "*.png"' in spec  # the window's PNGs go into the build
    iss = (ROOT / "packaging" / "sdm.iss").read_text(encoding="utf-8")
    assert "SetupIconFile=sdm.ico" in iss
    assert "personal use" not in iss


def test_the_extension_shows_the_logo(qapp):
    folder = ROOT / "extension" / "chrome"
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    for size, path in {**manifest["icons"], **manifest["action"]["default_icon"]}.items():
        image = QImage(str(folder / path))
        assert (image.width(), image.height()) == (int(size), int(size)), path
